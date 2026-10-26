"""命令解析与校验。"""

from json import loads
import re
import shlex
from typing import Any, List, Optional, Tuple

from .models import CommandData, CommandResult, CommandStatus


class CommandParser:
    """将 LLM 输出的多行文本解析为结构化命令列表。

    支持的格式:
        obs_switch_scene --name "游戏画面"
        obs -switch_scene --name "游戏画面"
        obs switch_scene --name "游戏画面"
        skill --name xxx --des "..."
        error --reason "..."

    规则:
        - 空行忽略
        - 以 # 开头的行视为注释
        - 参数支持 --key value 和 --key=value 两种形式
        - 值含空格必须用双引号包裹
        - 纯布尔标志: --verbose (等同 --verbose=true)

    skill 命令固定使用 --id 指定技能 id（--des 为需求描述）:
        skill --id weather --des "查天气"
    """

    _pattern = re.compile(
        r'^\s*'
        r'(?P<service>[A-Za-z_][A-Za-z0-9_]*?)'
        r'(?:_|\s*-\s*|\s+)'
        r'(?P<method>[A-Za-z_][A-Za-z0-9_]*)'
        r'(?:\s+(?P<params>.*))?\s*$'
    )

    # 已知的内置命令名（不是 service.method 形态）
    _BUILTIN = {
        "error",
        "skill"
    }

    # skill 统一用 --id 指定技能 id。
    _SKILL_REQUIRED_PARAMS = {"id"}

    @classmethod
    def parse(cls, text: str) -> List[CommandData]:
        commands: List[CommandData] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            cmd = cls.parse_line(line)
            if cmd is not None:
                commands.append(cmd)
        return commands

    @classmethod
    def parse_line(cls, line: str) -> Optional[CommandData]:
        """解析单行。返回 None 表示这行不是命令（应作为自然语言保留）。"""
        stripped = line.strip()
        if not stripped:
            return None

        first_token = stripped.split()[0] if stripped.split() else ""

        # 内置命令：skill / error
        if first_token in cls._BUILTIN or stripped.startswith("skill") or stripped.startswith("error"):
            return cls._parse_builtin(stripped, first_token)

        # 改为"能否被命令正则匹配 + 参数形态是否像命令"两步判定。
        match = cls._pattern.match(stripped)
        if not match:
            return None

        params_text = (match.group("params") or "").strip()
        # C59：普通英文句子（"hello world how are you"）也能被上面的正则匹配，
        # 这里用"参数必须为空或以 -- 开头"把它挡掉。
        if params_text and not params_text.startswith("--"):
            return None

        return CommandData(
            service=match.group("service"),
            method=match.group("method"),
            params=cls._parse_params(params_text),
            raw=line,
        )

    @classmethod
    def _parse_builtin(cls, stripped: str, first_token: str) -> Optional[CommandData]:
        if first_token == "skill":
            parts = stripped.split(maxsplit=1)
            params = cls._parse_params(parts[1] if len(parts) > 1 else "")
            # 缺少 --id 也不是合法 skill 命令
            if not cls._SKILL_REQUIRED_PARAMS <= set(params.keys()):
                return None
            return CommandData(
                service="skill",
                method="run",
                params=params,
                raw=stripped,
            )
        if first_token == "error":
            parts = stripped.split(maxsplit=2)
            params: dict[str, Any] = {}
            if len(parts) >= 3 and parts[1] == "--reason":
                params["reason"] = parts[2].strip().strip('"').strip("'")
            elif len(parts) >= 2:
                # LLM 偶尔写成 `error 无法理解`，直接把剩余当原因
                params["reason"] = parts[1].strip().strip('"').strip("'")
            return CommandData(
                service="error",
                method="error",
                params=params,
                raw=stripped,
            )
        return None

    @classmethod
    def _parse_params(cls, text: str) -> dict[str, Any]:
        if not text or not text.strip():
            return {}
        try:
            tokens = shlex.split(text)
        except ValueError:
            # 引号不匹配时降级为空白切分
            tokens = text.split()

        params: dict[str, Any] = {}
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.startswith("--") and "=" in token:
                key, val = token[2:].split("=", 1)
                params[key.strip()] = cls._cast(val)
                i += 1
            elif token.startswith("--"):
                key = token[2:]
                if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                    i += 1
                    params[key.strip()] = cls._cast(tokens[i])
                else:
                    params[key.strip()] = True
                i += 1
            else:
                # 位置参数 → 收集到 _args
                if "_args" not in params:
                    params["_args"] = []
                params["_args"].append(cls._cast(token))
                i += 1
        return params

    @classmethod
    def _cast(cls, value: str) -> Any:
        """智能类型转换"""
        text = value.strip()
        if text == "":
            return ""
        if text in ("true", "false", "null"):
            return loads(text)
        if text.startswith("{") or text.startswith("["):
            try:
                return loads(text)
            except Exception:
                pass
        # 只转换"规范"的数字字面量。
        if re.fullmatch(r'-?\d+', text):
            if len(text) > 1 and (text[0] == '0' or (text[0] == '-' and text[1:2] == '0')):
                return text
            return int(text)
        if re.fullmatch(r'-?\d+\.\d+', text):
            return float(text)
        return text


class CommandValidator:
    """校验命令合法性：服务是否注册 / 方法是否存在 / 必填参数是否齐全。

    C61：服务声明 tools 的方式在代码库里不统一 ——
        - `CommandValidator` 侧看到的是 dict: {method: {required_args: [...]}}
        - `PromptBuilder.build_commands_prompt` 侧看到的是 list
    这里统一兼容两种形态。
    """

    def __init__(self, service_manager: Any):
        self._sm = service_manager

    def validate(self, commands: List[CommandData]) -> List[CommandResult]:
        """返回与 commands 等长的检查结果；不抛异常，错误记为 SKIPPED。"""
        return [self._validate_one(cmd) for cmd in commands]

    def _validate_one(self, cmd: CommandData) -> CommandResult:
        service_name = cmd["service"]
        method_name = cmd["method"]

        if service_name == "error":
            return CommandResult(
                ok=False, service=service_name, method=method_name,
                status=CommandStatus.ERROR.value,
                data=None, error=cmd["params"].get("reason", "未知错误"),
                elapsed_ms=0, raw=cmd["raw"],
            )

        # 服务注册检查（兼容没有 is_registered 的实现）
        try:
            registered = self._sm.is_registered(service_name)
        except Exception:
            registered = False
        if not registered:
            return CommandResult(
                ok=False, service=service_name, method=method_name,
                status=CommandStatus.SKIPPED.value,
                data=None, error=f"服务未注册: {service_name}",
                elapsed_ms=0, raw=cmd["raw"],
            )

        service = self._sm.get_service(service_name)
        if service is None or not hasattr(service, method_name):
            return CommandResult(
                ok=False, service=service_name, method=method_name,
                status=CommandStatus.SKIPPED.value,
                data=None, error=f"方法不存在: {service_name}.{method_name}",
                elapsed_ms=0, raw=cmd["raw"],
            )

        # 同时接受 dict / list / 对象三种 tools 形态
        method_cfg = self._find_method_config(service, method_name)
        required = self._required_args(method_cfg)

        params = dict(cmd["params"])
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

        return CommandResult(
            ok=True, service=service_name, method=method_name,
            status=CommandStatus.PENDING.value,
            data=None, error=None, elapsed_ms=0, raw=cmd["raw"],
        )

    @staticmethod
    def _find_method_config(service: Any, method_name: str) -> Any:
        tools_cfg = getattr(service, "tools", None)
        if not tools_cfg:
            return None
        # 形态 A：dict，key 是方法名
        if isinstance(tools_cfg, dict):
            return tools_cfg.get(method_name)
        # 形态 B：list，元素是 dict/对象，含 name
        if isinstance(tools_cfg, (list, tuple)):
            for item in tools_cfg:
                name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
                if name == method_name:
                    return item
        return None

    @staticmethod
    def _required_args(method_cfg: Any) -> List[str]:
        if not method_cfg:
            return []
        if isinstance(method_cfg, dict):
            required = method_cfg.get("required_args")
            if required is None:
                # 也兼容 OpenAI schema 风格的 parameters.required
                parameters = method_cfg.get("parameters")
                if isinstance(parameters, dict):
                    required = parameters.get("required")
            return list(required or [])
        return list(getattr(method_cfg, "required_args", None) or [])
