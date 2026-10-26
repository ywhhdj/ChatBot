"""把所有 HTTP 端点注册成网关 op（K10–K12）。

注册后：
  * HTTP 控制器 → `await gateway.call("system.info")` （薄壳）
  * 桌面端 Bridge → `gateway.call_sync("system.info")` （进程内，零网络）

两端拿到的信封字段完全一致。

注意：这里只做**注册**，不改各控制器的业务逻辑。
控制器函数签名保持原样（有的无参、有的接 pydantic 模型、有的接 Query 参数），
网关按签名自适应调用（见 `gateway._call_handler`）。
"""

from __future__ import annotations

from typing import Any, Dict

from ..logger import logger

_REGISTERED = False


def register_all() -> int:
    """注册全部 op。幂等，返回注册数量。"""
    global _REGISTERED
    if _REGISTERED:
        from .gateway import get_gateway

        return len(get_gateway().ops())

    from .gateway import register_ops

    mapping: Dict[str, Any] = {}

    # ---- 系统 ----
    try:
        from .controllers import system as c_system

        mapping.update({
            "system.health": c_system.health,
            "system.info": c_system.info,
            "system.stats": c_system.stats,
            "system.gc": c_system.gc,
            "system.ping": c_system.ping,
        })
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ops] system 注册失败: {e}")

    # ---- 角色 ----
    try:
        from .controllers import character as c_character

        mapping.update({
            "character.list": c_character.list_characters,
            "character.presets": c_character.presets,
            "character.current": c_character.current,
            "character.get": c_character.get_character,
            "character.create": c_character.create_character,
            "character.update": c_character.update_character,
            "character.delete": c_character.delete_character,
            "character.switch": c_character.switch_character,
            "character.state.get": c_character.get_state,
            "character.state.update": c_character.update_state,
        })
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ops] character 注册失败: {e}")

    # ---- 技能 ----
    try:
        from .controllers import skill as c_skill

        mapping.update({
            "skill.list": c_skill.list_skills,
            "skill.get": c_skill.get_skill,
            "skill.execute": c_skill.execute,
        })
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ops] skill 注册失败: {e}")

    # ---- 服务 ----
    try:
        from .controllers import service as c_service

        mapping.update({
            "service.list": c_service.list_services,
            "service.get": c_service.get_service,
            "service.start": c_service.start_service,
            "service.stop": c_service.stop_service,
            "service.config.get": c_service.get_config,
            "service.config.update": c_service.update_config,
            "service.tools": c_service.list_tools,
        })
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ops] service 注册失败: {e}")

    # ---- 会话 / 存档 / 记忆 / 配置 / 日志 / 任务 / 管道 ----
    for mod_name, prefix, names in (
        ("session", "session", ("list_sessions", "get_session", "create_session",
                                "delete_session", "messages", "append_message",
                                "clear_messages", "flush")),
        # save：op 名显式指定，`_short()` 的自动推导会把
        # `create_slot` 拆成 `save.create.slot`，既不好看也容易撞名。
        ("save", "save", ()),
        ("memory", "memory", ("layers", "search", "stats", "clear", "compress")),
        ("config", "config", ("get_config", "patch_config", "save_config",
                              "reload_config", "schema")),
        ("logger", "logger", ("records", "stats", "set_level", "flush")),
        ("task", "task", ("status", "cancel", "stats")),
        ("pipline", "pipeline", ("switch", "current", "providers", "abilities")),
    ):
        try:
            import importlib

            mod = importlib.import_module(f".controllers.{mod_name}", __package__)
            for fn_name in names:
                fn = getattr(mod, fn_name, None)
                if fn is not None:
                    op = f"{prefix}.{_short(fn_name, prefix)}"
                    mapping[op] = fn
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[ops] {mod_name} 注册失败: {e}")

    # ---- 存档（SV17：显式 op 名） ----
    try:
        from .controllers import save as c_save

        mapping.update({
            "save.slots": c_save.all_slots,
            "save.slot.get": c_save.get_slot,
            "save.slot.create": c_save.create_slot,
            "save.slot.delete": c_save.delete_slot,
            "save.slot.toggle": c_save.toggle_slot,
            "save.slot.save": c_save.save_slot,
            "save.slot.load": c_save.load_slot,
        })
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ops] save 注册失败: {e}")

    # ---- 审计（TD13） ----
    try:
        from .controllers import audit as c_audit

        mapping.update({
            "audit.tree": c_audit.tree,
            "audit.tools": c_audit.tools,
        })
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ops] audit 注册失败: {e}")

    # ---- PPT（新增） ----
    try:
        from .controllers import ppt as c_ppt

        mapping.update({
            "ppt.templates": c_ppt.templates,
            "ppt.outline": c_ppt.outline,
            "ppt.render": c_ppt.render,
            "ppt.status": c_ppt.job_status,
            "ppt.download": c_ppt.download,
            "ppt.render_async": c_ppt.render_async,
        })
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ops] ppt 注册失败: {e}")

    register_ops(mapping)
    _REGISTERED = True
    logger.info(f"[Gateway] 已注册 {len(mapping)} 个 op")
    return len(mapping)


def _short(fn_name: str, prefix: str) -> str:
    """`list_sessions` + `session` → `list`；`get_session` → `get`。"""
    name = fn_name
    for p in (prefix, f"{prefix}s"):
        if name == p:
            return "get"
        if name.startswith(p + "_"):
            name = name[len(p) + 1:]
            break
        if name.endswith("_" + p) or name.endswith("_" + p.rstrip("s")):
            name = name.rsplit("_", 1)[0]
            break
    return name.replace("_", ".")


__all__ = ["register_all"]
