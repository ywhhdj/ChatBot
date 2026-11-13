import asyncio
from typing import List
from ...core.pipeline.models import ToolFunction, ToolFunctionParameters
from ...logger import logger
from ..manager import Service
from ..base import BaseService, ServiceState
from ... import keys

# 假设使用第三方库 pip install mcrcon
try:
    from mcrcon import MCRcon # typing: ignore
except ImportError:
    MCRcon = None

@Service(id=keys.ServiceKeys.Game.MINECRAFT)
class MinecraftGameService(BaseService):
    name = "Minecraft"
    description = "控制 Minecraft 服务器，执行指令、查询状态"

    def __init__(self, host="127.0.0.1", port=25575, password="", timeout=5):
        super().__init__()
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    def start(self):
        if MCRcon is None:
            raise RuntimeError("未安装 mcrcon 库，请执行 pip install mcrcon")
        self.set_status(ServiceState.RUNNING)
        logger.info("[MC] 服务已启动")

    def stop(self):
        self.set_status(ServiceState.STOPPED)

    async def execute_command(self, command: str) -> str:
        """通过 RCON 异步执行指令 (在独立线程池中跑，避免阻塞)"""
        if self.state != ServiceState.RUNNING:
            return "MC 服务未启动"
        
        def _run():
            with MCRcon(self.host, self.password, port=self.port) as mcr: # typing: ignore
                return mcr.command(command)

        try:
            # 放到线程池防止阻塞事件循环
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, _run)
            return resp
        except Exception as e:
            logger.error(f"[MC] 执行指令失败: {e}")
            return f"执行失败: {e}"

    def get_tools(self) -> List[ToolFunction]:
        """暴露给 LLM 调用的能力"""
        return [
            ToolFunction(
                name="run_mc_command",
                description="在 Minecraft 服务器后台执行指令 (如 op, say, time set day 等)",
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "command": {"type": "string", "description": "原生的 Minecraft 指令，不带斜杠"}
                    },
                    required=["command"]
                )
            )
        ]