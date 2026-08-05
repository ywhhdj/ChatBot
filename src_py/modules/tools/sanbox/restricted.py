from dataclasses import dataclass
import gc
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

@dataclass
class SandboxConfig:
    max_execution_time: float = 5.0  # 最大执行时间(秒)
    max_memory_mb: int = 128  # 最大内存(MB)
    max_output_size: int = 1024 * 100  # 最大输出大小(100KB)

class ResourceLimiter:
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._start_time: Optional[float] = None
    
    def start_monitoring(self):
        self._start_time = time.time()
        # 设置内存限制（仅Unix系统）
        try:
            if sys.platform != 'win32':
                memory_bytes = self.config.max_memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, 
                                  (memory_bytes, memory_bytes))
        except (AttributeError, resource.error):
            pass  # 不支持的系统忽略
    
    def check_timeout(self):
        """检查是否超时"""
        if self._start_time is None:
            return
        
        elapsed = time.time() - self._start_time
        if elapsed > self.config.max_execution_time:
            raise SandboxTimeoutError(
                f"执行超时 ({elapsed:.2f}s > {self.config.max_execution_time}s)"
            )
    
    def check_memory(self):
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            if memory_mb > self.config.max_memory_mb:
                raise SandboxMemoryError(
                    f"内存超限 ({memory_mb:.1f}MB > {self.config.max_memory_mb}MB)"
                )
        except ImportError:
            pass


class RestrictedCodeExecutor:    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._validator = CodeValidator(self.config)
        self._limiter = ResourceLimiter(self.config)
        self._safe_builtins = self._create_safe_builtins()
        self._execution_count = 0
        self._last_error: Optional[str] = None
    
    def _create_safe_builtins(self) -> Dict[str, Any]:
        """创建安全的builtins字典"""
        safe_builtins = {}
        
        # 白名单builtins
        allowed = {
            'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray',
            'bytes', 'callable', 'chr', 'complex', 'dict', 'dir',
            'divmod', 'enumerate', 'filter', 'float', 'format',
            'frozenset', 'hash', 'help', 'hex', 'id', 'int', 'isinstance',
            'issubclass', 'iter', 'len', 'list', 'map', 'max', 'min',
            'next', 'object', 'oct', 'ord', 'pow', 'print', 'range',
            'repr', 'reversed', 'round', 'set', 'slice', 'sorted',
            'str', 'sum', 'super', 'tuple', 'type', 'zip',
            'True', 'False', 'None', '__import__'
        }
        
        for name in allowed:
            if hasattr(builtins, name):
                safe_builtins[name] = getattr(builtins, name)
        
        # 自定义安全的print
        safe_builtins['print'] = self._safe_print
        
        return safe_builtins
    
    def _safe_print(self, *args, **kwargs):
        output = []
        for arg in args:
            output.append(str(arg))
        print(" ".join(output))
    
    def execute_code(
        self, 
        code: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        在沙盒中执行代码
        
        Args:
            code: 要执行的Python代码
            context: 额外的上下文变量
            
        Returns:
            执行结果字典
        """
        self._execution_count += 1
        result = {
            "success": False,
            "output": "",
            "error": None,
            "execution_time": 0.0
        }
        
        start_time = time.time()
        
        try:
            # 1. 代码验证
            is_safe, error_msg = self._validator.validate_code(code)
            if not is_safe:
                raise ValueError(error_msg)
            
            # 2. 准备执行环境
            local_vars = context or {}
            local_vars.update({
                "__builtins__": self._safe_builtins,
                "_sandbox_result": None
            })
            
            # 3. 开始资源监控
            self._limiter.start_monitoring()
            
            # 4. 编译代码
            compiled_code = compile(code, '<sandbox>', 'exec')
            
            # 5. 在线程中执行（用于超时控制）
            execution_result = {"exception": None}
            
            def execute_target():
                try:
                    exec(compiled_code, self._safe_builtins, local_vars)
                except Exception as e:
                    execution_result["exception"] = e
            
            thread = threading.Thread(target=execute_target)
            thread.daemon = True
            thread.start()
            
            # 等待执行完成或超时
            thread.join(timeout=self.config.max_execution_time)
            
            if thread.is_alive():
                raise TimeoutError(
                    f"执行超时 ({self.config.max_execution_time}s)"
                )
            
            if execution_result["exception"]:
                raise execution_result["exception"]
            
            # 6. 收集输出
            result["success"] = True
            result["output"] = local_vars.get("_sandbox_result", "")
            result["local_vars"] = self._filter_output(local_vars)
            
        except SandboxSecurityError as e:
            result["error"] = f"安全错误: {str(e)}"
            self._last_error = str(e)
            
        except SandboxTimeoutError as e:
            result["error"] = f"超时错误: {str(e)}"
            
        except SandboxMemoryError as e:
            result["error"] = f"内存错误: {str(e)}"
            
        except Exception as e:
            result["error"] = f"执行错误: {str(e)}"
            self._last_error = str(e)
        
        finally:
            # 计算执行时间
            result["execution_time"] = time.time() - start_time
            # 限制输出大小
            if len(str(result.get("output", ""))) > self.config.max_output_size:
                result["output"] = str(result["output"])[:self.config.max_output_size] + "..."
            # 清理
            gc.collect()
        
        return result
    
    def _filter_output(self, local_vars):
        """过滤输出，移除敏感信息"""
        filtered = {}
        sensitive_keys = {
            '__builtins__',
              '__builtin__'
        }
        
        for key, value in local_vars.items():
            if key in sensitive_keys:
                continue
            # 限制输出大小
            try:
                str_value = str(value)
                if len(str_value) > 1000:
                    filtered[key] = str_value[:1000] + "..."
                else:
                    filtered[key] = value
            except:
                filtered[key] = "<unprintable>"
        return filtered
    
    def get_stats(self):
        """获取执行统计"""
        return {
            "total_executions": self._execution_count,
            "last_error": self._last_error,
            "config": {
                "max_execution_time": self.config.max_execution_time,
                "max_memory_mb": self.config.max_memory_mb
            }
        }

    