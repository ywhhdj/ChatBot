from json import loads
import re
import shlex
from typing import Any, List, Optional
from ...tools.services.models import CommandData, CommandResult, CommandStatus


class CommandParser:
    """
    将 LLM 输出的多行文本解析为结构化命令列表。

    支持的格式:
        obs_switch_scene --name "游戏画面"
        browser_open --url https://example.com
        live2d_say --text "你好世界"
        error --reason "无法理解意图"

    规则:
        - 空行忽略
        - 以 # 开头的行视为注释
        - 参数支持 --key value 和 --key=value 两种形式
        - 值含空格必须用双引号包裹
        - 纯布尔标志: --verbose (等同 --verbose=true)
    """

    # 匹配两种格式:
    #   service_method --params...     (下划线连接: obs_switch_scene)
    #   service -method --params...    (短横线连接: obs -switch_scene)
    #   service method --params...     (空格连接:   obs switch_scene)
    _pattern = re.compile(
        r'^\s*'
        r'(?P<service>[A-Za-z_][A-Za-z0-9_]*?)'          # service (非贪婪)
        r'(?:_|(?=-)|(?=\s))'                              # 分隔符: _ 或 - 或空格
        r'(?P<method>[A-Za-z_][A-Za-z0-9_]*)'              # method
        r'(?:\s+(?P<params>.*))?\s*$'
    )

    @classmethod
    def parse(cls, text: str) -> List[CommandData]:
        """解析多行命令文本 → 命令字典列表"""
        commands: List[CommandData] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # 跳过明显不是命令的行 (模型偶尔会输出说明文字)
            if not cls._looks_like_command(line):
                continue
            cmd = cls._parse_line(line)
            if cmd is not None:
                commands.append(cmd)
        return commands

    @classmethod
    def _looks_like_command(cls, line: str) -> bool:
        """快速判断一行是否像命令

        支持格式:
            obs_switch_scene --name xxx
            browser_open --url xxx
            live2d_say --text xxx
            error --reason xxx
        """
        first = line.split()[0] if line.split() else ""
        if first in {"error", "skill"}:
            return True
        # service_method 格式: 小写字母开头, 含下划线
        return bool(re.match(r'^[a-z][a-z0-9_]*$', first)) and '_' in first

    @classmethod
    def _parse_line(cls, line: str) -> Optional[CommandData]:
        # 特殊处理: error --reason "..."
        stripped = line.strip()
        if stripped.startswith("skill"):
            parts = stripped.split(maxsplit=1)
            params = cls._parse_params(parts[1] if len(parts) > 1 else "")
            return CommandData(
                service="skill",
                method="run",
                params=params,
                raw=line,
            )
        if stripped.startswith("error"):
            # 直接用 split 解析
            parts = stripped.split(maxsplit=2)
            params = {}
            if len(parts) >= 3 and parts[1] == "--reason":
                params["reason"] = parts[2].strip().strip('"').strip("'")
            return CommandData(
                service="error",
                method="error",
                params=params,
                raw=line,
            )
        m = cls._pattern.match(line)
        if not m:
            return None
        service = m.group("service")
        method  = m.group("method")
        params_text = m.group("params") or ""
        params = cls._parse_params(params_text)
        return CommandData(
            service=service,
            method=method,
            params=params,
            raw=line,
        )

    @classmethod
    def _parse_params(cls, text: str) -> dict[str, Any]:
        if not text.strip():
            return {}
        try:
            tokens = shlex.split(text)
        except ValueError:
            # 引号不匹配时降级
            tokens = text.split()

        params: dict[str, Any] = {}
        i = 0
        while i < len(tokens):
            token = tokens[i]
            # --key=value
            if token.startswith("--") and "=" in token:
                key, val = token[2:].split("=", 1)
                params[key.strip()] = cls._cast(val)
                i += 1
            # --key value
            elif token.startswith("--"):
                key = token[2:]
                if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                    i += 1
                    params[key.strip()] = cls._cast(tokens[i])
                else:
                    params[key.strip()] = True
                i += 1
            # 位置参数 (无 -- 前缀) → 用 _args 列表收集
            else:
                if "_args" not in params:
                    params["_args"] = []
                params["_args"].append(cls._cast(token))
                i += 1
        return params

    @classmethod
    def _cast(cls, value: str) -> Any:
        """智能类型转换: str → int/float/bool/list/dict"""
        text = value.strip()
        if text == "":
            return ""
        # JSON 字面量
        if text in ("true", "false", "null"):
            return loads(text)
        if text.startswith("{") or text.startswith("["):
            try:
                return loads(text)
            except Exception:
                pass
        # 数字
        if re.match(r'^-?\d+$', text):
            return int(text)
        if re.match(r'^-?\d+\.\d+$', text):
            return float(text)
        return text  # 保持字符串

class CommandValidator:
    """
    校验命令合法性:
        1. 服务是否注册
        2. 方法是否存在
        3. 必填参数是否齐全
        4. 参数类型是否匹配 (可选, 按 schema)
    """

    def __init__(self, service_manager: Any):
        self._sm = service_manager

    def validate(self, commands: List[CommandData]) -> List[CommandResult]:
        """
        返回与 commands 等长的检查结果列表。
        不抛异常, 所有错误以 CommandResult(status=SKIPPED) 记录。
        """
        results: List[CommandResult] = []
        for cmd in commands:
            res = self._validate_one(cmd)
            results.append(res)
        return results

    def _validate_one(self, cmd: CommandData) -> CommandResult:
        service_name = cmd["service"]
        method_name  = cmd["method"]

        # 1. 特殊命令: error --reason "..."
        if service_name == "error":
            return CommandResult(
                ok=False, service=service_name, method=method_name,
                status=CommandStatus.ERROR.value,
                data=None, error=cmd["params"].get("reason", "未知错误"),
                elapsed_ms=0, raw=cmd["raw"],
            )

        # 2. 服务注册检查
        if not self._sm.is_registered(service_name):
            return CommandResult(
                ok=False, service=service_name, method=method_name,
                status=CommandStatus.SKIPPED.value,
                data=None, error=f"服务未注册: {service_name}",
                elapsed_ms=0, raw=cmd["raw"],
            )

        # 3. 方法存在检查
        service = self._sm.get_service(service_name)
        if not hasattr(service, method_name):
            return CommandResult(
                ok=False, service=service_name, method=method_name,
                status=CommandStatus.SKIPPED.value,
                data=None, error=f"方法不存在: {service_name}.{method_name}",
                elapsed_ms=0, raw=cmd["raw"],
            )

        # 4. 必填参数检查 (基于服务 self.tools 配置)
        tools_cfg = getattr(service, "tools", {})
        method_cfg = tools_cfg.get(method_name, {})
        required  = method_cfg.get("required_args", [])
        params    = cmd["params"]
        position_args = params.pop("_args", None)

        for i, req_name in enumerate(required):
            if req_name in params:
                continue
            if position_args is not None and i < len(position_args):
                params[req_name] = position_args[i]
                continue
            return CommandResult(
                ok=False, service=service_name, method=method_name,
                status=CommandStatus.SKIPPED.value,
                data=None, error=f"缺少必填参数: {req_name}",
                elapsed_ms=0, raw=cmd["raw"],
            )

        # 校验通过 → 返回 pending 状态, 等待执行
        return CommandResult(
            ok=True, service=service_name, method=method_name,
            status=CommandStatus.PENDING.value,
            data=None, error=None, elapsed_ms=0, raw=cmd["raw"],
        )
