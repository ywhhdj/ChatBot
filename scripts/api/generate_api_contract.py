#!/usr/bin/env python3
"""generate_api_contract.py —— ChatBot API 单一契约源与文档生成器。

用法（仓库根目录）：

    python scripts/api/generate_api_contract.py

产出（均为生成文件，禁止手工编辑）：

    resources/configs/api/endpoints.json   路由权威源（EndpointLoader 读取）
    resources/configs/api/groups.json      能力分组目录（catalog 读取）
    docs/api.md                           官方 API 参考文档

设计依据
────────
* ADR-002「API contract 的唯一权威来源」：文档 / 路由 / 分组由同一份契约生成。
* FrontendBackendContract.md §9「生成文件标头含生成命令与源文件」。
* docs/api.md 第 0 节通用约定 + OpenAPI 3.1 字段口径（path/query/requestBody/
  responses/errors/example），端点表与请求/响应字段从源码 AST 提取，避免漂移。

本脚本只做静态解析与文本生成：不 import 项目模块、不启动服务、不跑测试。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "src" / "modules" / "api"
CONTROLLERS = API_DIR / "controllers"
OUT_ENDPOINTS = ROOT / "resources" / "configs" / "api" / "endpoints.json"
OUT_GROUPS = ROOT / "resources" / "configs" / "api" / "groups.json"
OUT_DOC = ROOT / "docs" / "api.md"

BASELINE = "a6c38fefb98a4d82acb616bc4c9b98f405b83be9"
BASE_URL = "http://127.0.0.1:8000"

# ==========================================================================
# 1. 分组定义
# ==========================================================================

GROUPS: Dict[str, Dict[str, str]] = {
    "request":{"label": "常规请求", "prefix": "/", "description": "常规请求"},
    "generation": {"label": "生成与推理", "prefix": "/generation", "description": "对话、语音、图像、OCR、向量、工具命令及生成任务辅助"},
    "system": {"label": "系统", "prefix": "/system", "description": "健康、版本、统计、GC 与连通性探测"},
    "config": {"label": "配置", "prefix": "/config", "description": "配置读取、局部更新、重载、持久化与 schema"},
    "logger": {"label": "日志", "prefix": "/logger", "description": "日志级别、统计、记录与排空"},
    "device": {"label": "设备", "prefix": "/device", "description": "CPU/GPU/内存与推荐帧率"},
    "providers": {"label": "供应商", "prefix": "/providers", "description": "provider 目录、状态、切换、停止与模型下载"},
    "service": {"label": "服务", "prefix": "/service", "description": "服务注册、启停、配置、工具与 UI 描述"},
    "skill": {"label": "技能", "prefix": "/skill", "description": "技能目录、启停、提示词与受控执行"},
    "workspace": {"label": "工作区", "prefix": "/workspace", "description": "工作区选择、权限档位与敏感确认"},
    "audit": {"label": "能力审计", "prefix": "/audit", "description": "可调用能力树与工具清单（非安全事件日志）"},
    "session": {"label": "会话", "prefix": "/session", "description": "会话生命周期、消息追加与落盘"},
    "save": {"label": "存档", "prefix": "/save", "description": "存档槽、分段更新、同步与恢复"},
    "character": {"label": "角色", "prefix": "/character", "description": "角色 CRUD、预设、切换与状态"},
    "memories": {"label": "记忆", "prefix": "/memories", "description": "分层记忆、检索、压缩、统计、衰减与删除"},
    "task": {"label": "任务", "prefix": "/task", "description": "后台任务查询与取消"},
    "ppt": {"label": "PPT", "prefix": "/ppt", "description": "模板、大纲、渲染任务与产物下载"},
    "hotkeys": {"label": "热键", "prefix": "/hotkeys", "description": "快捷键清单、校验、批量更新与重置"},
    "catalog": {"label": "接口目录", "prefix": "/catalog", "description": "端点清单 + OpenAPI schema，供前端动态表单使用"},
}


def E(
    group: str,
    method: str,
    path: str,
    op: str,
    mod: str,
    fn: str,
    summary: str,
    *,
    status: str = "新增",
    body: Optional[str] = None,
    data: Optional[str] = None,
    desktop: bool = True,
    dispatch: str = "loop",
    timeout: float = 60.0,
    note: str = "",
    example: Optional[Dict[str, Any]] = None,
    sse: bool = False,
) -> Dict[str, Any]:
    return dict(
        group=group, method=method, path=path, op=op, mod=mod, fn=fn,
        summary=summary, status=status, body=body, data=data,
        desktop=desktop, dispatch=dispatch, timeout=timeout,
        note=note, example=example, sse=sse,
    )


# ==========================================================================
# 2. 端点契约（唯一权威源）
#    顺序即注册顺序：静态路径必须排在同层 {param} 动态路径之前。
# ==========================================================================

ENDPOINTS: List[Dict[str, Any]] = [
    # ---------------- 生成与推理（generation.py） ----------------
    E("generation", "GET", "/generation/status", "generation.status", "generation", "status", "查询 LLM/TTS/ASR/图像/OCR/向量能力就绪状态", data="GenerationStatusData", status="新增", note="只读探测，不触发模型加载、索引重建或全盘扫描。"),
    E("generation", "POST", "/generation/chat", "generation.chat", "generation", "chat_once", "非流式对话，一次返回完整回复", body="ChatRequest", data="ChatResultData", timeout=600.0, example={"text": "你好", "session_id": "default", "source": "text"}, note="route 为空时由意图路由自动判定 pure_chat / tool_call / mixed。"),
    E("generation", "POST", "/generation/chat/stream", "generation.chat_stream", "generation", "chat_stream", "SSE 流式对话", body="ChatStreamRequest", timeout=600.0, sse=True, desktop=False, example={"text": "讲个短故事"}, note="每帧 `event:` + `data:`（含 stream_id / request_id / seq / ts）；终态恰为 done / error / cancelled 之一，见 §4.1。"),
    E("generation", "POST", "/generation/tts", "generation.tts", "generation", "tts", "文本转语音，返回 base64 音频", body="TTSRequest", data="TTSResultData", timeout=120.0, example={"text": "你好呀", "format": "mp3"}, note="二进制一律 base64；日志不记录音频内容。"),
    E("generation", "POST", "/asr", "generation.asr", "generation", "asr", "语音转文本，audio 为 base64 音频", body="ASRRequest", data="ASRResultData", timeout=120.0, example={"audio": "<base64-wav>", "format": "wav", "is_final": True}, note="需限制请求体大小、音频时长与解码资源。"),
    E("generation", "POST", "/generation/image", "generation.image", "generation", "image", "图像生成（OpenAI / Stability / ComfyUI 协议）", body="ImageGenerateRequest", data="ImageGenerateData", timeout=600.0, example={"prompt": "一只在窗台晒太阳的猫", "size": "1024x1024", "n": 1, "response_format": "url"}, note="provider/model_id 必须落在 Registry 白名单；extra 展开为供应商原生参数。"),
    E("generation", "POST", "/generation/ocr", "generation.ocr", "generation", "ocr", "图片文字识别", body="OCRRecognizeRequest", data="OCRResultData", timeout=120.0, example={"image": "<base64-png>", "format": "png"}),
    E("generation", "POST", "/generation/embedding", "generation.embedding", "generation", "embedding", "批量文本向量化", body="EmbeddingRequest", data="EmbeddingData", timeout=120.0, example={"texts": ["你好", "世界"]}, note="开发态无模型时走 hash 兜底，fingerprint 明确标记，禁止与真实向量混用。"),
    E("generation", "POST", "/command", "generation.command", "generation", "command", "执行工具命令文本（策略/沙箱/工作区约束）", body="CommandRunRequest", data="CommandResultData", timeout=120.0, example={"text": "skill --id weather --city 深圳", "wait": True}, note="命令文本只认 `--id`；shell 与未隔离语言默认拒绝"),
    E("request", "GET", "/folder/{type}", "request.open_folder", "request", "open_folder", "打开受支持的本地数据目录", dispatch="thread", status="新增", note="type 白名单：images / roles / memory / workspace；禁止任意路径。"),
    E("generation", "POST", "/progress-stream/{task_id}", "generation.progress_stream", "generation", "progress_stream", "SSE 任务进度流", timeout=600.0, sse=True, desktop=False, status="修正", note="生产者调用 generation.set_progress(task_id, data) 写入；0.3s 轮询、终态清理、有 deadline；事件名随 status，帧带 stream_id / request_id / seq / ts。"),

    # ---------------- 系统 ----------------
    E("system", "GET", "/system/health", "system.health", "system", "health", "Web、调度器、主线程、记忆与服务健康状态", data="HealthData", status="现行"),
    E("system", "GET", "/system/info", "system.info", "system", "info", "版本、配置路径与数据目录", data="InfoData", status="现行"),
    E("system", "GET", "/system/stats", "system.stats", "system", "stats", "uptime、日志、任务、连接与记忆统计", data="StatsData", status="现行"),
    E("system", "POST", "/system/gc", "system.gc", "system", "gc", "触发记忆衰减/清理与日志排空", body="GcRequest", data="GcData", status="现行"),
    E("system", "GET", "/system/ping", "system.ping", "system", "ping", "轻量连通性探测", data="str", status="现行"),

    # ---------------- 配置 ----------------
    E("config", "GET", "/config", "config.get", "config", "get_config_api", "读取配置，可按 section 过滤", status="现行", note="涉及密钥时默认遮蔽；raw 明文回显仅限本地受控调试，属待收敛项。"),
    E("config", "GET", "/config/schema", "config.schema", "config", "schema", "配置字段描述", status="现行"),
    E("config", "POST", "/config/reload", "config.reload", "config", "reload", "从配置文件重新加载", status="现行"),
    E("config", "POST", "/config/save", "config.save", "config", "save", "持久化配置到磁盘", body="ConfigSaveRequest", status="现行"),
    E("config", "PATCH", "/config/{section}", "config.patch_section", "config", "patch_section", "局部更新配置段", body="ConfigPatchRequest", status="现行"),

    # ---------------- 日志 ----------------
    E("logger", "GET", "/logger/level", "logger.get_level", "logger", "get_level", "当前日志级别", data="LoggerLevelData", status="新增"),
    E("logger", "PUT", "/logger/level", "logger.set_level", "logger", "set_level", "设置日志级别", body="LoggerLevelRequest", data="LoggerLevelData", status="新增"),
    E("logger", "GET", "/logger/levels", "logger.list_levels", "logger", "list_levels", "可用日志级别列表", status="新增"),
    E("logger", "GET", "/logger/stats", "logger.stats", "logger", "stats", "日志计数与按级别统计", data="LoggerStatsData", status="新增"),
    E("logger", "GET", "/logger/records", "logger.records", "logger", "records", "最近日志记录", status="新增", note="limit / level 为查询参数；正文限长，不回传凭据。"),
    E("logger", "POST", "/logger/flush", "logger.flush", "logger", "flush", "排空日志缓冲", dispatch="thread", status="新增"),
    E("logger", "POST", "/logger/append", "logger.append", "logger", "append_log", "接收前端 LogForwarder 批量日志", body="LogAppendRequest", data="LogAppendData", dispatch="thread", status="新增", example={"records": [{"level": "info", "message": "ui ready", "source": "frontend"}], "no_frontend_push": True}, note="单次上限 100 条、字段白名单、正文 4000 / 堆栈 12000 字符；no_frontend_push=true 不广播 GET_LOG，避免日志回环。"),

    # ---------------- 设备 ----------------
    E("device", "GET", "/device/info", "device.info", "device", "device_info", "设备与平台信息（CPU/GPU/内存/推荐帧率）", data="DeviceInfoData", dispatch="thread", status="新增"),

    # ---------------- 供应商 ----------------
    E("providers", "GET", "/providers/adapters", "providers.list_describe", "providers", "list_describe", "能力、可选 provider、当前选中与用量", status="新增"),
    E("providers", "GET", "/providers/configs", "providers.all_configs", "providers", "all_configs", "各能力供应商配置（敏感字段已掩码）", status="新增"),
    E("providers", "GET", "/providers/{adapter}", "providers.list_providers", "providers", "list_providers", "某能力下的 provider 清单", status="新增"),
    E("providers", "GET", "/providers/{adapter}/{provider}", "providers.get_provider", "providers", "get_provider", "读取 provider 配置（已掩码）", status="新增"),
    E("providers", "GET", "/providers/{adapter}/{provider}/status", "providers.status", "providers", "status", "provider 完整状态与本地模型文件状态", data="ProviderStatusData", status="新增"),
    E("providers", "POST", "/providers/{adapter}/switch", "providers.switch", "providers", "switch", "切换 provider / 模型", body="ProviderSwitchRequest", data="SwitchResultData", dispatch="thread", timeout=120.0, status="新增", note="先初始化新实例并健康检查，成功后才切流量；配置覆盖走白名单。"),
    E("providers", "POST", "/providers/{adapter}/stop", "providers.stop", "providers", "stop_adapter", "停止当前 provider，保留能力门面", dispatch="thread", status="新增"),
    E("providers", "POST", "/providers/{adapter}/{provider}/download", "providers.download", "providers", "download_model", "触发本地模型下载（进度走 WebSocket）", body="ProviderDownloadRequest", data="DownloadStartData", timeout=30.0, status="新增", note="返回 task_id；已安装且未 force 时返回 1001「模型已存在」。"),

    # ---------------- 服务 ----------------
    E("service", "GET", "/service", "service.list", "service", "list_services", "服务列表（支持 running_only）", data="ServiceListData", status="现行"),
    E("service", "GET", "/service/tools", "service.list_tools", "service", "list_tools", "所有服务工具定义", data="ToolData", status="现行"),
    E("service", "GET", "/service/{service_id}", "service.get", "service", "get_service", "服务详情", data="ServiceInfoData", status="现行"),
    E("service", "GET", "/service/{service_id}/tools", "service.tools", "service", "service_tools", "单服务工具定义", data="ToolData", status="现行"),
    E("service", "GET", "/service/{service_id}/ui", "service.ui", "service", "service_ui", "服务 UI 描述", data="ServiceUIDescription", status="现行"),
    E("service", "POST", "/service/{service_id}/register", "service.register", "service", "register_service", "注册服务实例", dispatch="thread", status="新增"),
    E("service", "POST", "/service/{service_id}/start", "service.start", "service", "start_service", "启动服务", body="ServiceStartRequest", data="ServiceActionData", dispatch="thread", timeout=120.0, status="现行"),
    E("service", "POST", "/service/{service_id}/stop", "service.stop", "service", "stop_service", "停止服务", data="ServiceActionData", dispatch="thread", status="现行"),
    E("service", "GET", "/service/{service_id}/config", "service.get_config", "service", "get_config", "读取服务配置", status="现行"),
    E("service", "PUT", "/service/{service_id}/config", "service.update_config", "service", "update_config", "更新服务配置", body="ServiceConfigUpdateRequest", status="现行"),
    E("service", "PUT", "/service/{service_id}/config/apply", "service.apply_config", "service", "apply_config", "应用配置（停 → 启）", dispatch="thread", timeout=120.0, status="现行"),

    # ---------------- 技能 ----------------
    E("skill", "GET", "/skill", "skill.list", "skill", "list_skills", "技能列表（支持 active_only）", data="SkillListData", status="现行"),
    E("skill", "GET", "/skill/prompt", "skill.prompt", "skill", "prompt", "给模型使用的技能提示词", status="现行"),
    E("skill", "POST", "/skill/reload", "skill.reload", "skill", "reload", "重新扫描技能目录", dispatch="thread", status="现行"),
    E("skill", "GET", "/skill/{skill_id}", "skill.get", "skill", "get_skill", "技能详情", data="SkillInfoData", status="现行"),
    E("skill", "POST", "/skill/{skill_id}/activate", "skill.activate", "skill", "activate", "启用技能", data="SkillInfoData", status="现行"),
    E("skill", "POST", "/skill/{skill_id}/deactivate", "skill.deactivate", "skill", "deactivate", "停用技能", data="SkillInfoData", status="现行"),
    E("skill", "POST", "/skill/{skill_id}/execute", "skill.execute", "skill", "execute", "执行技能（超时 30s，AST 白名单沙盒）", body="SkillExecuteRequest", data="SkillExecuteData", timeout=30.0, status="现行", note="shell / javascript 类型可见但不支持执行；输出限制到 <workspace>/skill/<skill_id>/。"),

    # ---------------- 工作区 ----------------
    E("workspace", "GET", "/workspace", "workspace.info", "workspace", "info", "当前工作区、权限档位与输出目录", status="新增"),
    E("workspace", "POST", "/workspace/select", "workspace.select", "workspace", "select", "选择目录与权限档位", dispatch="thread", status="新增"),
    E("workspace", "POST", "/workspace/confirm", "workspace.confirm", "workspace", "confirm", "显式确认敏感原文暴露", status="新增"),
    E("workspace", "DELETE", "/workspace", "workspace.clear", "workspace", "clear", "撤销选择，回到默认工作区", status="新增"),

    # ---------------- 能力审计 ----------------
    E("audit", "GET", "/audit/tree", "audit.tree", "audit", "tree", "服务 → 方法 → 参数 能力树", data="AuditTreeData", status="新增"),
    E("audit", "GET", "/audit/tools", "audit.tools", "audit", "tools", "扁平工具清单", status="新增"),

    # ---------------- 会话 ----------------
    E("session", "GET", "/session", "session.list", "session", "list_sessions", "会话列表", data="SessionListData", status="现行"),
    E("session", "POST", "/session", "session.create", "session", "create_session", "创建会话", body="SessionCreateRequest", data="SessionInfoData", status="现行"),
    E("session", "POST", "/session/flush", "session.flush", "session", "flush", "等待会话后台写入落盘", body="FlushRequest", dispatch="thread", status="现行"),
    E("session", "GET", "/session/{session_id}", "session.get", "session", "get_session", "会话详情", data="SessionInfoData", status="现行"),
    E("session", "DELETE", "/session/{session_id}", "session.delete", "session", "delete_session", "删除会话", status="现行"),
    E("session", "POST", "/session/{session_id}/switch", "session.switch", "session", "switch_session", "切换当前会话", data="SessionInfoData", status="现行", note="切换是状态边界：先取消旧 session 的活动 stream 再加载新数据。"),
    E("session", "GET", "/session/{session_id}/messages", "session.messages", "session", "messages", "会话消息列表", data="MessageListData", status="现行"),
    E("session", "POST", "/session/{session_id}/messages", "session.append", "session", "append_message", "追加一条消息", body="MessageAppendRequest", status="现行"),

    # ---------------- 存档 ----------------
    E("save", "GET", "/save", "save.all", "save", "all_slots", "全量存档槽（含未激活）", data="SlotListData", status="新增"),
    E("save", "GET", "/save/snapshot/status", "save.snapshot_status", "save", "snapshot_status", "恢复事务、自动存档与调度器 gate 状态", data="SnapshotActionData", status="新增", dispatch="thread", note="组合根未由应用层装配时返回 2001，不假造成功。"),
    E("save", "GET", "/save/snapshot/graph", "save.snapshot_graph", "save", "snapshot_graph", "revision DAG（parent_revision / branch_id）", data="SnapshotActionData", status="新增", dispatch="thread", note="slot_id 为 query 参数，缺省取当前槽。"),
    E("save", "POST", "/save/snapshot/preview", "save.snapshot_preview", "save", "snapshot_preview", "恢复预演（只读、无副作用）", data="SnapshotActionData", status="新增", dispatch="thread", note="slot_id / revision 为 query 参数；Preview → Prepare → Commit → Verify 中不改动运行态。"),
    E("save", "POST", "/save/snapshot", "save.snapshot", "save", "snapshot", "创建不可变 Snapshot revision", body="SnapshotRequest", data="SnapshotActionData", timeout=300.0, status="新增", dispatch="thread", example={"slot_id": "slot_001", "label": "章节通关", "trigger": "manual"}, note="stage → validate → publish；parent 默认取最近成功恢复的 revision。"),
    E("save", "POST", "/save/snapshot/restore", "save.snapshot_restore", "save", "snapshot_restore", "执行恢复事务（失败自动回滚）", body="SnapshotRequest", data="SnapshotActionData", timeout=300.0, status="新增", dispatch="thread", example={"slot_id": "slot_001", "revision": "rev_0007"}, note="墓碑优先于旧快照；事务结束后恢复调度并启动 pre-restore 缓冲期计时。"),
    E("save", "GET", "/save/list", "save.list_slots", "save", "list_slots", "存档槽列表", data="SlotListData", status="修正", note="修正旧端点 path 自带 /api 造成的 /api/api/... 重复前缀。"),
    E("save", "POST", "/save/create", "save.create", "save", "create_slot", "创建存档槽", body="SlotCreateRequest", data="SlotInfoData", status="修正"),
    E("save", "POST", "/save/sync", "save.sync", "save", "sync_from_sessions", "从会话同步到存档槽", body="SlotSyncRequest", dispatch="thread", status="修正"),
    E("save", "POST", "/save/restore", "save.restore", "save", "restore_to_sessions", "从存档槽恢复到会话", dispatch="thread", status="修正"),
    E("save", "GET", "/save/{slot_id}", "save.get", "save", "get_slot", "存档槽详情", data="SlotInfoData", status="修正"),
    E("save", "DELETE", "/save/{slot_id}", "save.delete", "save", "delete_slot", "删除存档槽", data="SlotActionData", status="修正"),
    E("save", "POST", "/save/{slot_id}/toggle", "save.toggle", "save", "toggle_slot", "切换激活存档槽", data="SlotActionData", status="修正"),
    E("save", "POST", "/save/{slot_id}/save", "save.save", "save", "save_slot", "写入存档", data="SlotActionData", dispatch="thread", status="修正"),
    E("save", "POST", "/save/{slot_id}/load", "save.load", "save", "load_slot", "加载存档", data="SlotActionData", dispatch="thread", status="修正"),
    E("save", "PUT", "/save/{slot_id}/section", "save.update_section", "save", "update_section", "更新存档分段", body="SlotSectionUpdateRequest", dispatch="thread", status="修正"),

    # ---------------- 角色 ----------------
    E("character", "GET", "/character", "character.list", "character", "list_characters", "角色列表", data="CharacterListData", status="新增"),
    E("character", "GET", "/character/presets", "character.presets", "character", "presets", "角色预设（情绪映射等）", status="新增", note="静态路径必须先于 /character/{character_id} 注册。"),
    E("character", "GET", "/character/current", "character.current", "character", "current", "当前角色", data="CharacterInfoData", status="新增"),
    E("character", "POST", "/character/create", "character.create", "character", "create_character", "创建角色", body="CharacterCreateRequest", data="CharacterInfoData", status="新增"),
    E("character", "GET", "/character/{character_id}", "character.get", "character", "get_character", "角色详情", data="CharacterInfoData", status="新增"),
    E("character", "PUT", "/character/{character_id}", "character.update", "character", "update_character", "更新角色", body="CharacterUpdateRequest", data="CharacterInfoData", status="新增"),
    E("character", "DELETE", "/character/{character_id}", "character.delete", "character", "delete_character", "删除角色", status="现行"),
    E("character", "POST", "/character/{character_id}/switch", "character.switch", "character", "switch_character", "切换当前角色", data="CharacterInfoData", status="现行"),
    E("character", "GET", "/character/{character_id}/state", "character.get_state", "character", "get_state", "角色运行状态", data="CharacterStateData", status="现行"),
    E("character", "PUT", "/character/{character_id}/state", "character.update_state", "character", "update_state", "更新角色状态", body="CharacterStateUpdateRequest", data="CharacterStateData", status="现行"),

    # ---------------- 记忆 ----------------
    E("memories", "GET", "/memories/layers", "memories.layers", "memories", "layers", "分层记忆（short_term / long_term / detailed）", data="MemoryLayersData", status="新增"),
    E("memories", "GET", "/memories/short", "memories.short_term", "memories", "short_term", "短期记忆摘要", data="MemoryShortTermData", status="新增"),
    E("memories", "GET", "/memories/long", "memories.long_term", "memories", "long_term", "长期记忆", data="MemoryLongTermData", status="新增"),
    E("memories", "POST", "/memories/search", "memories.search", "memories", "search", "语义 / 相关记忆检索", body="MemorySearchRequest", data="MemorySearchData", status="新增", note="必须先按 session_id 过滤再查询存储。"),
    E("memories", "GET", "/memories/compressed", "memories.compressed", "memories", "compressed", "压缩记忆列表", data="MemoryCompressedListData", status="新增"),
    E("memories", "GET", "/memories/stats", "memories.stats", "memories", "stats", "记忆容量统计", data="MemoryStatsData", status="新增"),
    E("memories", "POST", "/memories/decay", "memories.decay", "memories", "decay", "手动触发记忆衰减", data="MemoryDecayData", dispatch="thread", status="新增"),
    E("memories", "POST", "/memories/flush", "memories.flush", "memories", "flush", "等待后台写入完成", data="MemoryFlushData", dispatch="thread", status="新增"),
    E("memories", "POST", "/memories/retention", "memories.retention", "memories", "retention", "设置记忆保留期 / 层级（默认预演）", body="MemoryActionRequest", data="MemoryActionData", dispatch="thread", status="新增", example={"memory_id": "42", "session_id": "default", "retention_days": 30, "dry_run": True}, note="静态路径必须先于 /memories/{memory_id} 注册；dry_run 默认 true，code 为稳定拒绝码（bad_scope / not_found / no_change…），不是 HTTP 错误。"),
    E("memories", "POST", "/memories/pin", "memories.pin", "memories", "pin", "固定 / 取消固定一条记忆", body="MemoryActionRequest", data="MemoryActionData", dispatch="thread", status="新增", example={"memory_id": "42", "pinned": True, "dry_run": False}),
    E("memories", "POST", "/memories/revive", "memories.revive", "memories", "revive", "唤醒 faded / archived 记忆", body="MemoryActionRequest", data="MemoryActionData", dispatch="thread", status="新增", example={"memory_id": "42", "dry_run": False}, note="复用 MemoryAPI.retention_service，提升稳定度但不重置时间轴；scope 先按 session_id 校验。"),
    E("memories", "DELETE", "/memories/{memory_id}", "memories.delete_memory", "memories", "delete_memory", "删除单条记忆（墓碑协议）", data="MemoryDeleteData", dispatch="thread", status="新增"),

    # ---------------- 任务 ----------------
    E("task", "GET", "/task/{task_id}", "task.get", "task", "get_task", "查询后台任务状态与结果", data="TaskStatusData", status="新增"),
    E("task", "POST", "/task/{task_id}/cancel", "task.cancel", "task", "cancel_task", "取消任务（尽力而为）", body="TaskCancelRequest", data="TaskStatusData", status="新增", note="同步线程不保证强制终止；超时只标记放弃等待。"),

    # ---------------- PPT ----------------
    E("ppt", "GET", "/ppt/templates", "ppt.templates", "ppt", "templates", "PPT 模板列表", data="PptTemplateListData", status="新增"),
    E("ppt", "POST", "/ppt/outline", "ppt.outline", "ppt", "outline", "生成内容大纲（不渲染）", body="PptOutlineRequest", data="PptOutlineData", timeout=300.0, status="新增"),
    E("ppt", "POST", "/ppt/render", "ppt.render", "ppt", "render", "提交渲染后台任务，返回 task_id", body="PptRenderRequest", data="PptRenderData", timeout=600.0, status="新增"),
    E("ppt", "POST", "/ppt/render/async", "ppt.render_async", "ppt", "render_async", "提交渲染后台任务（render 的显式异步别名）", body="PptRenderRequest", data="PptRenderData", timeout=600.0, status="新增", note="与 /ppt/render 共用同一实现、DTO 与 task_id 语义；保留别名兼容旧前端 renderAsync 调用，不新建第二套队列。"),
    E("ppt", "GET", "/ppt/job/{task_id}", "ppt.status", "ppt", "job_status", "查询渲染任务", data="PptJobData", status="新增"),
    E("ppt", "GET", "/ppt/download/{file_name}", "ppt.download", "ppt", "download", "取回产出文件（base64 + 路径）", data="PptDownloadData", dispatch="thread", status="新增", note="只接受 basename，并再次经工作区边界复验；产出固定落在 <workspace>/ppt/。"),

    # ---------------- 热键 ----------------
    E("hotkeys", "GET", "/hotkeys", "hotkeys.list", "hotkeys", "list_hotkeys", "快捷键清单与 revision", data="HotkeyListData", status="新增"),
    E("hotkeys", "POST", "/hotkeys/validate", "hotkeys.validate", "hotkeys", "validate_hotkey", "录制中实时校验组合键", body="HotkeyValidateRequest", data="HotkeyValidateData", status="新增"),
    E("hotkeys", "POST", "/hotkeys/reset", "hotkeys.reset", "hotkeys", "reset_hotkeys", "恢复默认快捷键", body="HotkeyResetRequest", data="HotkeyListData", status="新增"),
    E("hotkeys", "PUT", "/hotkeys", "hotkeys.batch_update", "hotkeys", "update_hotkeys", "批量更新快捷键", body="HotkeyBatchUpdateRequest", data="HotkeyListData", status="新增", note="带 revision 乐观并发；冲突 / 保留键 / 过期版本均拒绝且状态不变。"),
    E("hotkeys", "PUT", "/hotkeys/{action}", "hotkeys.update", "hotkeys", "update_hotkey", "更新单个快捷键", body="HotkeyUpdateRequest", data="HotkeyListData", status="新增"),

    # ---------------- 接口目录 ----------------
    E("catalog", "GET", "/catalog", "catalog.api", "catelog", "api", "端点清单 + OpenAPI schema（动态表单用）", desktop=False, status="新增", note="返回 {total, groups, endpoints[]}；不计入 desktop bridge op。"),
]

# ==========================================================================
# 3. 源码 AST 解析（模型字段 / handler 签名）
# ==========================================================================


def _lit(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return ast.unparse(node)


def _factory_default(node: ast.AST) -> Any:
    name = ast.unparse(node)
    return {"list": [], "dict": {}, "set": [], "str": "", "int": 0, "float": 0.0, "bool": False}.get(name, [])


def parse_models(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    tree = ast.parse(path.read_text("utf-8"))
    out: Dict[str, List[Dict[str, Any]]] = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        # 继承字段：ChatStreamRequest(ChatRequest)、SseXxxEvent(SseEventBase) 等
        fields: List[Dict[str, Any]] = []
        by_name: Dict[str, Dict[str, Any]] = {}
        for base in (ast.unparse(b) for b in cls.bases):
            for inherited in out.get(base, []):
                by_name[inherited["name"]] = dict(inherited)
        fields = list(by_name.values())
        by_name = {f["name"]: i for i, f in enumerate(fields)}
        for st in cls.body:
            if not isinstance(st, ast.AnnAssign) or not isinstance(st.target, ast.Name):
                continue
            ann = ast.unparse(st.annotation)
            required, default, desc, constraints = True, None, "", []
            value = st.value
            if value is not None:
                if isinstance(value, ast.Call) and getattr(value.func, "id", None) == "Field":
                    if value.args:
                        first = value.args[0]
                        if isinstance(first, ast.Constant) and first.value is Ellipsis:
                            required = True
                        else:
                            required, default = False, _lit(first)
                    else:
                        required = False
                    for kw in value.keywords:
                        if kw.arg == "default":
                            required, default = False, _lit(kw.value)
                        elif kw.arg == "default_factory":
                            required, default = False, _factory_default(kw.value)
                        elif kw.arg == "description" and isinstance(kw.value, ast.Constant):
                            desc = str(kw.value.value)
                        elif kw.arg in ("min_length", "max_length", "ge", "le", "gt", "lt"):
                            constraints.append(f"{kw.arg}={ast.unparse(kw.value)}")
                else:
                    required, default = False, _lit(value)
            item = dict(name=st.target.id, ann=ann, required=required,
                        default=default, desc=desc, constraints=", ".join(constraints))
            if item["name"] in by_name:
                fields[by_name[item["name"]]] = item
            else:
                by_name[item["name"]] = len(fields)
                fields.append(item)
        out[cls.name] = fields
    return out


REQUEST_MODELS = parse_models(API_DIR / "requests.py")
DTO_MODELS = parse_models(API_DIR / "dto.py")
ALL_MODELS = {**REQUEST_MODELS, **DTO_MODELS}


def parse_handlers() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for path in sorted(CONTROLLERS.glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = []
                defaults = list(node.args.defaults)
                offset = len(node.args.args) - len(defaults)
                for i, a in enumerate(node.args.args):
                    default_node = defaults[i - offset] if i >= offset else None
                    args.append(dict(
                        name=a.arg,
                        ann=ast.unparse(a.annotation) if a.annotation else "",
                        default=_lit(default_node) if default_node is not None else None,
                        has_default=default_node is not None,
                        default_node=default_node,
                    ))
                out[f"{path.stem}:{node.name}"] = dict(
                    args=args,
                    ret=ast.unparse(node.returns) if node.returns else "",
                    doc=(ast.get_docstring(node) or "").strip().splitlines()[0] if ast.get_docstring(node) else "",
                )
    return out


HANDLERS = parse_handlers()


def py_type(ann: str) -> str:
    a = (ann or "").strip()
    if not a:
        return "any"
    nullable = a.startswith("Optional[") or "| None" in a
    base = a
    m = re.match(r"Optional\[(.*)\]$", a)
    if m:
        base = m.group(1)
    lit = re.match(r"Literal\[(.*)\]$", base)
    if lit:
        values = lit.group(1).replace("'", '"')
        return "string（枚举：" + values + "）" + ("，可空" if nullable else "")
    if base.startswith(("List[", "list[")):
        inner = py_type(base[base.index("[") + 1:-1])
        return f"array<{inner}>" + ("，可空" if nullable else "")
    if base.startswith(("Dict[", "dict[")):
        return "object" + ("，可空" if nullable else "")
    if base in ("str", "AnyStr"):
        t = "string"
    elif base == "int":
        t = "integer"
    elif base == "float":
        t = "number"
    elif base == "bool":
        t = "boolean"
    elif base == "bytes":
        t = "string（byte）"
    elif base in ("Any", "object", "Dict[str, Any]"):
        t = "any"
    else:
        t = base
    return t + ("，可空" if nullable else "")


def show_default(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def sample_value(name: str, field: Dict[str, Any], prefer_sample: bool = False) -> Any:
    ann = field["ann"]
    samples = {
        "text": "你好", "prompt": "一只在窗台晒太阳的猫", "query": "最近聊了什么",
        "audio": "<base64-wav>", "image": "<base64-png>", "content": "一条消息",
        "name": "示例", "topic": "人工智能简介", "session_id": "sess_001",
        "slot_id": "slot_001", "character_id": "qingmei", "service_id": "browser",
        "task_id": "task_001", "skill_id": "weather", "file_name": "deck.pptx",
        "level": "INFO", "combo": "Ctrl+Shift+A", "action": "record",
    }
    if prefer_sample and name in samples:
        return samples[name]
    d = field["default"]
    if d is not None and d != "—" and not (prefer_sample and d in ("", 0, [], {}, False)):
        return d
    if name in samples:
        return samples[name]
    if "List" in ann or "list" in ann:
        return []
    if "Dict" in ann or "dict" in ann:
        return {}
    if "int" in ann.lower():
        return 8
    if "float" in ann.lower():
        return 0.7
    if "bool" in ann.lower():
        return True
    return ""


def endpoint_args(ep: Dict[str, Any]) -> Dict[str, Any]:
    """从 path 模板 + handler 签名推导 path / query / body 参数。"""
    path_names = re.findall(r"\{(\w+)\}", ep["path"])
    info = HANDLERS.get(f"{ep['mod']}:{ep['fn']}", {})
    path_params, query_params, body_name = [], [], ep["body"]
    for a in info.get("args", []):
        name, ann = a["name"], a["ann"]
        if name in path_names:
            path_params.append(dict(name=name, type=py_type(ann) or "string", desc="路径资源标识"))
            continue
        if name == "request" and "Request" in ann:
            continue
        if name in ("payload", "body") or ann in REQUEST_MODELS:
            if body_name is None and ann in REQUEST_MODELS:
                body_name = ann
            elif body_name is None and name in ("payload", "body"):
                body_name = None
            continue
        if a["default_node"] is not None and isinstance(a["default_node"], ast.Call):
            call = a["default_node"]
            desc = ""
            for kw in call.keywords:
                if kw.arg == "description" and isinstance(kw.value, ast.Constant):
                    desc = str(kw.value.value)
            default = _lit(call.args[0]) if call.args else None
        else:
            desc, default = "", a["default"]
        query_params.append(dict(
            name=name, type=py_type(ann), required=not a["has_default"],
            default=show_default(default), desc=desc,
        ))
    for name in path_names:
        if not any(p["name"] == name for p in path_params):
            path_params.append(dict(name=name, type="string", desc="路径资源标识"))
    return dict(path=path_params, query=query_params, body=body_name)


def response_data(ep: Dict[str, Any]) -> str:
    if ep.get("sse"):
        return "SSE"
    if ep["data"]:
        return ep["data"]
    info = HANDLERS.get(f"{ep['mod']}:{ep['fn']}", {})
    ret = info.get("ret", "")
    m = re.search(r"ApiResponse\[(.+)\]", ret)
    if m:
        return m.group(1)
    return ""


# ==========================================================================
# 4. 生成 endpoints.json / groups.json
# ==========================================================================


def write_endpoints() -> List[Dict[str, Any]]:
    items = []
    for ep in ENDPOINTS:
        items.append({
            "op": ep["op"],
            "handler": f"modules.api.controllers.{ep['mod']}:{ep['fn']}",
            "http": {
                "method": ep["method"],
                "path": ep["path"],
                "status_code": 200,
                "summary": ep["summary"],
                "deprecated": False,
            },
            "tags": [ep["group"]],
            "desktop": ep["desktop"],
            "dispatch": ep["dispatch"],
            "timeout": ep["timeout"],
            "enabled": True,
            "meta": {
                "label": ep["fn"],
                "group": ep["group"],
                "status": ep["status"],
                "note": ep["note"],
            },
        })
    OUT_ENDPOINTS.write_text(json.dumps({"version": 2, "endpoints": items},
                                        ensure_ascii=False, indent=2) + "\n", "utf-8")
    return items


def write_groups() -> None:
    groups = {}
    for key, meta in GROUPS.items():
        groups[key] = {
            "label": meta["label"],
            "prefix": meta["prefix"],
            "description": meta["description"],
            "ops": [e["op"] for e in ENDPOINTS if e["group"] == key],
        }
    OUT_GROUPS.write_text(json.dumps({"version": 2, "groups": groups},
                                     ensure_ascii=False, indent=2) + "\n", "utf-8")


# ==========================================================================
# 5. 生成 docs/api.md
# ==========================================================================


def md_table(headers: List[str], rows: List[List[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in row) + " |")
    return "\n".join(out)


def model_fields_table(model: str) -> str:
    fields = ALL_MODELS.get(model)
    if not fields:
        return ""
    rows = []
    for f in fields:
        rows.append([
            f"`{f['name']}`", py_type(f["ann"]), "是" if f["required"] else "否",
            show_default(f["default"]), (f["desc"] or "—") + (f"；约束：{f['constraints']}" if f["constraints"] else ""),
        ])
    return md_table(["字段", "类型", "必填", "默认", "说明"], rows)


def sample_body(ep: Dict[str, Any], body: Optional[str]) -> Dict[str, Any]:
    if ep.get("example") is not None:
        return ep["example"]
    if not body or body not in ALL_MODELS:
        return {}
    fields = ALL_MODELS[body]
    required = [f for f in fields if f["required"]]
    chosen = required or fields[:6]
    return {f["name"]: sample_value(f["name"], f) for f in chosen}


def sample_data(data: str) -> Any:
    if not data or data in ("SSE", "str", "Dict[str, Any]", "Any"):
        if data == "str":
            return "pong"
        return {}
    fields = ALL_MODELS.get(data)
    if not fields:
        return {}
    out = {f["name"]: sample_value(f["name"], f, prefer_sample=True) for f in fields[:8]}
    # 计数类示例保持自洽（total = accepted + dropped），别出现三个同值
    if {"accepted", "dropped", "total"} <= set(out):
        out["accepted"], out["dropped"], out["total"] = 1, 0, 1
    return out


def endpoint_section(ep: Dict[str, Any], idx: int) -> str:
    args = endpoint_args(ep)
    data = response_data(ep)
    url = f"/api{ep['path']}"
    lines: List[str] = []
    lines.append(f"#### {ep['method']} `{url}`")
    lines.append("")
    lines.append(f"**{ep['summary']}**")
    lines.append("")
    lines.append(md_table(
        ["项", "值"],
        [
            ["op", f"`{ep['op']}`"],
            ["分组 / tag", f"`{ep['group']}`（{GROUPS[ep['group']]['label']}）"],
            ["handler", f"`modules.api.controllers.{ep['mod']}:{ep['fn']}`"],
            ["desktop bridge", "是" if ep["desktop"] else "否（仅 HTTP）"],
            ["dispatch", f"`{ep['dispatch']}`"],
            ["超时", f"{ep['timeout']:g} s"],
            ["状态", ep["status"]],
        ],
    ))
    lines.append("")

    if args["path"]:
        lines.append("**路径参数**")
        lines.append("")
        lines.append(md_table(["参数", "类型", "说明"],
                             [[f"`{p['name']}`", p["type"], p["desc"]] for p in args["path"]]))
        lines.append("")
    if args["query"]:
        lines.append("**查询参数**")
        lines.append("")
        lines.append(md_table(["参数", "类型", "必填", "默认", "说明"],
                             [[f"`{p['name']}`", p["type"], "是" if p["required"] else "否",
                               p["default"], p["desc"] or "—"] for p in args["query"]]))
        lines.append("")
    body = args["body"]
    if body:
        lines.append(f"**请求体** `application/json` · `{body}`")
        lines.append("")
        lines.append(model_fields_table(body))
        lines.append("")
    elif ep["method"] in ("POST", "PUT", "PATCH"):
        lines.append("**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。")
        lines.append("")

    if ep.get("sse"):
        lines.append("**响应** `text/event-stream`（非统一信封；逐帧 `event:` + `data:`，字段见 §4.1）")
        lines.append("")
        lines.append("```text")
        if "chat" in ep["path"]:
            lines.append('event: chunk')
            lines.append('data: {"type":"chunk","text":"你好","stream_id":"s1","request_id":"r1","seq":1,"ts":1760000000.1}')
            lines.append("")
            lines.append('event: done')
            lines.append('data: {"type":"done","session_id":"sess_001","elapsed_ms":1234,"result":{"route":"pure_chat"},"stream_id":"s1","request_id":"r1","seq":2,"ts":1760000001.2}')
        else:
            lines.append('event: progress')
            lines.append('data: {"type":"progress","task_id":"task_001","status":"running","percent":42.5,"stream_id":"s1","request_id":"r1","seq":1,"ts":1760000000.1}')
            lines.append("")
            lines.append('event: done')
            lines.append('data: {"type":"progress","task_id":"task_001","status":"done","percent":100.0,"stream_id":"s1","request_id":"r1","seq":2,"ts":1760000001.2}')
        lines.append("```")
        lines.append("")
    else:
        lines.append("**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）")
        lines.append("")
        if data and data in ALL_MODELS:
            lines.append(f"`data` · `{data}`")
            lines.append("")
            lines.append(model_fields_table(data))
            lines.append("")
        elif data:
            lines.append(f"`data` 类型：`{data}`（动态对象，字段由运行时决定）。")
            lines.append("")
        lines.append("**示例响应**")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps({
            "ok": True, "code": 200, "message": "ok",
            "data": sample_data(data),
            "request_id": "a1b2c3d4e5f6a7b8", "ts": 1760000000.0,
        }, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    lines.append("**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常"
                 + (" / 1002 资源不存在" if (args["path"] or ep["method"] == "DELETE") else "")
                 + (" / 1003 状态冲突" if ep["method"] in ("POST", "PUT", "PATCH") else "")
                 + "（完整映射见 §2.3）。")
    lines.append("")

    lines.append("**请求示例**")
    lines.append("")
    lines.append("```bash")
    example_path = ep["path"]
    for p in args["path"]:
        example_path = example_path.replace("{" + p["name"] + "}", str(sample_value(p["name"], {"ann": "str", "default": None})))
    if ep.get("sse"):
        lines.append(f"curl -N -X {ep['method']} '{BASE_URL}/api{example_path}' \\")
        lines.append("  -H 'Content-Type: application/json' \\")
        lines.append("  -H 'Accept: text/event-stream' \\")
        lines.append("  -d '" + json.dumps(sample_body(ep, body), ensure_ascii=False) + "'")
    elif ep["method"] == "GET" and not body:
        lines.append(f"curl '{BASE_URL}/api{example_path}'")
    else:
        lines.append(f"curl -X {ep['method']} '{BASE_URL}/api{example_path}' \\")
        lines.append("  -H 'Content-Type: application/json' \\")
        lines.append("  -d '" + json.dumps(sample_body(ep, body), ensure_ascii=False) + "'")
    lines.append("```")
    lines.append("")
    if ep["note"]:
        lines.append(f"> **备注**：{ep['note']}")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


DOC_HEAD = """# ChatBot API 参考（dev 分支 · 官方契约基线）

> **生成文件，请勿手工编辑。**
> 生成命令：`python scripts/api/generate_api_contract.py`
> 契约源：`scripts/api/generate_api_contract.py::ENDPOINTS` → `resources/configs/api/endpoints.json`、`resources/configs/api/groups.json`、本文件。
> 源码基线：`ywhhdj/ChatBot` dev 分支 `@@BASELINE@@`；Python 源码目录 `src/modules/`（历史文档记作 `src_py/`）。
> 格式口径：项目契约（ADR-002、`FrontendBackendContract.md`）+ OpenAPI 3.1 字段语义；每个端点给出 path / query / requestBody / responses / errors / example。
> 端点总数：**@@TOTAL@@**（启用 @@ENABLED@@）；分组数：**@@GROUPS@@**；基线 commit 的 `endpoints.json` 仅注册 50 条，本次按控制器与各管理器能力补齐。

---

## 1. 概览

### 1.1 服务地址与传输

| 项 | 值 |
|---|---|
| REST / SSE Base URL | `@@BASE@@/api` |
| WebSocket | `ws://<host>:<port>/`（由 `controllers/websocket` 注册，不是 `/ws`） |
| 桌面 Bridge | 进程内 `ApiGateway.call(op)`，仅 `desktop=true` 端点注册 |
| 默认监听 | `127.0.0.1:8000`（`resources/configs/app.conf` 的 `[Web]` 段为权威） |
| 认证 | 本地回环默认无认证；远程监听必须显式启用认证与严格来源限制 |
| 内容类型 | `application/json`；SSE 为 `text/event-stream`；二进制一律 base64 |

**最终 URL = `/api` + 资源路径**。`endpoints.json` 内 `http.path` 一律为资源相对路径，不得再带 `/api`；`/api` 只在 `register_all_routers(app, prefix="/api")` 添加一次。控制器内声明的 `APIRouter(prefix=...)` 为历史遗留，`all_routers()` 只返回 loader 生成的 router。

### 1.2 状态标记

| 标记 | 含义 |
|---|---|
| 现行 | 基线 `endpoints.json` 已注册且路径正确 |
| 修正 | 基线已注册但存在缺陷（如 save 组 `/api/api/...` 重复前缀），本次更正 |
| 新增 | 控制器中已有 handler 或本次新增 handler，但基线未注册，本次补齐 |

文档只描述**已注册端点**；设计目标、待办与不兼容变更统一放 §7，不混写为「已实现」。

### 1.3 端点与 op 命名

`op` 统一为 `<group>.<action>`（如 `generation.chat`、`session.create`），与 `groups.json` 的 `ops` 一一对应。`desktop=true` 的端点同时注册为 `ApiGateway` 的 op，桌面端 `call(op)` 与 REST 复用同一 handler 与 DTO。相比基线 `<module>.<func>` 形式的 op，本次为**破坏性重命名**；前端 service 已由 `scripts/api/generate_frontend_services.py` 按同一契约重新生成，每个请求显式携带 `opName` 与 `pathParams`，bridge 不再依赖路径推导（见 §4.3 / §6）。

### 1.4 分组总览

@@GROUP_TABLE@@

---

## 2. 通用约定

### 2.1 路由与注册链路

~~~text
ENDPOINTS（契约源）
   ├─→ resources/configs/api/endpoints.json   EndpointLoader._validate() → add_api_route()
   ├─→ resources/configs/api/groups.json     前端能力目录（catalog）
   └─→ docs/api.md                          本文（同一契约生成）
EndpointLoader.register_gateway() → desktop=true 端点注册为 ApiGateway op
register_all_routers(app, prefix="/api") → 最终 URL
~~~

`EndpointSpec` 字段：`op`、`handler`（`modules.api.controllers.<module>:<func>`）、`http{method,path,status_code,summary,deprecated}`、`tags`、`desktop`、`dispatch`、`timeout`、`enabled`、`meta`。启动期 `_validate()` 校验 handler 可 import 且 `METHOD + path` 不冲突；生成脚本同样做静态自检。

`dispatch`：`loop`（默认，网关已在调度器 loop）/ `thread`（`asyncio.to_thread`，用于文件 IO、模型加载、渲染）/ `main`（Qt 主线程派发，当前 dispatcher 接口待对齐，本次未启用）。

### 2.2 统一响应信封

成功与失败共用一套信封，前端只判 `ok` 与业务 `code`：

~~~json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.123
}
~~~

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | boolean | 业务是否成功 |
| `code` | integer | 业务码，成功固定 **200** |
| `message` | string | 可展示文本，失败时不得含内部异常详情 |
| `data` | object / array / string / null | 业务数据，结构见各端点 `T` |
| `request_id` | string | 16 字符请求标识，`X-Request-ID` 由中间件注入并回写响应头 |
| `ts` | number | Unix 秒（float） |

HTTP status 保留语义（2xx / 4xx / 5xx），业务 `code` 表示应用错误种类；`/api` 下的 404 / 405 也返回同构信封。SSE 与 WebSocket 不走该信封，见 §4。

### 2.3 错误码

| code | HTTP | 含义 | 客户端建议 |
|---:|---:|---|---|
| 200 | 200 | 成功 | 读取 `data` |
| 1001 | 400 | 参数校验失败 | 修正输入 |
| 1002 | 404 | 资源不存在 | 刷新资源或确认 ID |
| 1003 | 409 | 状态冲突 | 查询当前状态后决定 |
| 2001 | 503 | 依赖未初始化 | 配置 / 初始化依赖 |
| 2002 | 504 | 处理超时 | 先查任务状态；仅幂等操作可重试 |
| 3001 | 500 | 内部异常 | 用 `request_id` 排障 |
| 3002 | 503 | 主线程忙或不可用 | 稍后重试 |

统一错误对象建议包含 `kind`（validation / not_found / conflict / not_ready / timeout / cancelled / network / internal）、`code`、`status`、`request_id`、`retryable` 与安全处理后的 `message`。非幂等 POST/PUT/DELETE 默认不自动重试；长任务创建重试必须携带幂等键。

> 已闭环（P0）：桌面 bridge 的 `http.ts` 现判 `code === 200`，与 REST 共用同一信封判定；`response.py::_unhandled_handler` 与 `gateway.py::_invoke` 的兜底只回稳定 `message` + `request_id`，异常类型仅写入本地脱敏日志；外部 `X-Request-ID` 经 `normalize_request_id()` 限制为 `[A-Za-z0-9._-]{1,64}`。

### 2.4 请求标识与隔离维度

| 字段 | 生命周期 | 规则 |
|---|---|---|
| `request_id` | 一个入站请求 | 日志与错误定位；外部传入须限制长度与字符集 |
| `trace_id` | 一条完整业务链路 | 串联路由、memory retrieve、LLM、tool、持久化 |
| `stream_id` | 一次流式传输 | 关联 SSE / WS chunk、done / error / cancel |
| `task_id` | 一个后台工作 | 持续到 succeeded / failed / cancelled / timeout 终态 |
| `session_id` | 一段对话会话 | 上下文、检索、写入必须显式传入并按其过滤 |
| `character_id` | 当前角色实体 | 上下文与角色状态隔离维度 |
| `operation_id` | 长事务型操作 | 存档创建 / 恢复 / 索引重建的幂等查询键 |

`request_id` ≠ `task_id`；一次 POST 可能只创建 task，之后用 `task_id` 查询。

### 2.5 长任务、超时与限流

- 模型下载、PPT 渲染、批量生成等长操作返回 `task_id`，通过 `GET /api/task/{task_id}`、`GET /api/ppt/job/{task_id}` 或 `POST /api/progress-stream/{task_id}` 观察。
- 取消对同步线程不保证强制终止；超时只标记放弃等待，终态以服务端为准。
- 每个端点在 `endpoints.json` 声明 `timeout`；chat / image / PPT 为 300–600s，语音 120s，技能执行 30s，其余 60s。
- chat / audio / 文件 / PPT / 工具请求限制 body size、音频时长、并发数与输出大小；单 WebSocket 连接在途请求上限 8。

### 2.6 安全约束

- 默认只绑定 `127.0.0.1`；远程监听必须启用认证与严格来源限制。
- 配置密钥默认掩码；不在 URL、日志、前端持久化明文凭据。`config.raw=true` 仅在 `CHATBOT_ALLOW_RAW_CONFIG=1` 且本地 debug 模式下放行（`_raw_allowed()`），否则返回 1003 状态冲突，不回显任何原值。
- 所有服务产出与 shell / 技能执行受 `security/workspace` 工作区边界约束；文件参数只接受 `basename`，经 `realpath` + `is_within` 复验。
- 工作区档位：`read_only` / `writable` / `unrestricted`；未选择时惰性使用 `<用户数据目录>/workspace`（writable）。
- 日志不保存 key、完整 prompt、音频或私人记忆正文；健康检查不得触发模型加载、全量索引重建或全盘扫描。

### 2.7 版本与兼容策略

- 契约版本记录在 `endpoints.json` / `groups.json` 的 `version` 字段（本次为 2）。
- 新增字段保持向后兼容；删除 / 重命名 op 或路径须给出兼容期、旧路径别名与移除标准，并在同一变更中更新前端 service / types 与契约测试。
- 生成文件标头必须含生成命令与源文件；禁止手工编辑生成结果。

---

## 3. REST 接口参考

> 每小节字段顺序遵循 OpenAPI 口径：路径 → 参数 → requestBody → responses → errors → example。`data` 字段表由 `src/modules/api/requests.py` / `dto.py` 的 Pydantic 模型经 AST 提取，与源码同步。

"""

SSE_WS_BRIDGE = """---

## 4. SSE、WebSocket 与桌面 Bridge

### 4.1 SSE 事件（`text/event-stream`）

`POST /api/chat/stream` 与 `POST /api/progress-stream/{task_id}` 返回 SSE。**目标事件信封已落地**（`response.sse(event, event_name=..., **meta)`）；每帧带 `event:` 行，data 内含 `stream_id`、`request_id`、`seq`、`ts` 与兼容用的 `type`：

~~~text
event: chunk
data: {"type":"chunk","text":"你好","stream_id":"s1","request_id":"r1","seq":1,"ts":1760000000.1}

event: done
data: {"type":"done","session_id":"sess_001","elapsed_ms":1234,"result":{"route":"pure_chat"},"stream_id":"s1","request_id":"r1","seq":3,"ts":1760000001.2}

event: error
data: {"type":"error","code":2002,"error":{"code":2002,"kind":"timeout","message":"处理超时"},"stream_id":"s1","request_id":"r1","seq":4,"ts":1760000001.3}
~~~

| 事件名 | 流 | 语义 |
|---|---|---|
| `chunk` / `progress` / `pending` | chat / progress | 增量帧，`seq` 单调递增 |
| `done` / `finished` | 两者 | 成功终态 |
| `error` | 两者 | 失败终态，data 带 `code` 与结构化 `error` |
| `cancelled` | chat | 客户端断连终态，同时 `ref.cancel()` 向上传播取消 |
| `timeout` | progress | 超过 `STREAM_TIMEOUT` 的终态 |

进度流帧 data 为 `{task_id, status, percent, sent, total, files_done, files_total, error, type, stream_id, request_id, seq, ts}`；`status` 取 `pending` / `running` / `done` / `error` / `cancelled` / `timeout` / `finished`；生产者调用 `generation.set_progress(task_id, data)` 写入，终态到达后 `clear_progress(task_id)`。

约束：每流**恰好一个终态**（done / error / cancelled / timeout）；旧客户端忽略 `event:` 行仍可解析 `data:`；服务端有 max lifetime（600s）；断连传播取消；不伪装支持 replay。

### 4.2 WebSocket

路径 `ws://<host>:<port>/`（`app.websocket("/")` 注册，旧文档的 `/ws` 作废）。

**入站帧** `WebSocketRequest {type, data, client_id, request_id, stream_id}`（由 `model_validate()` 解析 `receive_json()` 返回的 dict）。`type` 必填，取值与 `src/modules/events/types.py::WebSocketEventType` 逐字一致：`websocket.connect` / `websocket.error` / `websocket.heartbeat` / `result` / `chat` / `get_log` 等；前端 `web/typings/enums.ts` 与 `web/typings/types/api.d.ts` 已同步。业务帧的 `data.client_id` 必须与连接分配一致，否则回错误但**不切断连接**；控制帧与心跳不强制该字段。心跳 `websocket.heartbeat` 单独响应，不进入业务派发；空闲 90s 由 `__cleanup_stale_connections()` 清理。

| type | 载荷 | 说明 |
|---|---|---|
| `chat` | `WsChatPayload {text, session_id, source, route}` | 对话 |
| `record.audio_chunk` | `WsAsrPayload {audio(base64), is_final}` | 语音分片 |
| `tts` / `WsTtsPayload` | `{text}` | 语音合成 |
| `download_model` | `WsDownloadModelPayload {model_name, force}` | 本地模型下载 |
| `subscribe` | `{events: string[]}` | 订阅**固定 allowlist**：`get_log` / `get_audit_logs` / `qq_bot.info`；回当前订阅清单 |
| `unsubscribe` | `{events: string[]}` | 退订，回剩余订阅清单 |
| `cancel` | `{request_id}` | 按 request_id 精确取消**本连接**在途任务，回 `{request_id, cancelled}` |

`request_id` 关联单次请求，`stream_id` 关联一条流，两者与 `task_id` 严格区分；帧级字段由 `websocket/context.py` 的 ContextVar 承载，`send_json` / `broadcast` 自动继承，同一连接并发的多条流不会串线。业务帧以独立任务派发并 `track_request()` 绑定，单连接在途上限 8；控制帧即时执行、不占 inflight。

**出站帧** `WebSocketAPIResponse<T> {type, ok, message, data, from_id, request_id, stream_id, ts}`。敏感事件未订阅则直接丢弃（不推送、不报错）。下载事件 DTO：`WsDownloadStartedData`（STARTED）、`WsDownloadProgressData`（RUNNING）、`WsDownloadCompletedData`（COMPLETED）、`WsDownloadFailedData`（FAILED）、`WsDownloadErrorData`（ERROR）；单连接在途下载上限 2。

`model_name` 新格式 `capability:provider[:model_id]`（如 `ocr:paddle`、`image:comfyui-local`），兼容别名 `paddle_ocr → ocr:paddle`、`whisper → asr:whisper`；已安装且未 `force` 直接回 `ERROR "模型已存在"`。

### 4.3 桌面 Bridge

`EndpointLoader.register_gateway()` 把 `desktop=true` 端点注册为 op；`call_sync()` 在无运行中 loop 的线程里复用调度器 loop。Web 与 Qt bridge 已统一：同一信封、同一成功 `code=200`、同一 DTO、同一 decoder（`web/api/http.ts` 判 `ok === true && code === 200`）。

`loader._wrap()` 现在是**契约适配层**：按 `EndpointSpec.http.path` 与 handler 的 `get_type_hints()`，把平铺的 `{pathParams + query + body}` 绑定成具名参数，遇到 Pydantic 请求模型自动 `model_validate()`，校验失败返回 1001（而非过去被兜底成 3001 的 `AttributeError`）。`dispatch=thread/main` 不再把裸 dict 塞给 handler；`dispatch=main` 走 `run_async_on_main_thread()`，本次仍未启用该档位。

`gateway._ok()` 对 `ApiResponse` 直接展开，避免 bridge 出现 `data` 里再套一层信封；未知 op 返回 1002，内部异常只回稳定 message + `request_id`。

### 4.4 shell 与工具命令契约（非独立 HTTP 资源）

- 命令文本由模型直接写原生命令原文，不需要 `shell --command` 包装；只认 `--id`（技能名可重复，id 才唯一）。
- 命中 `shell/commands.py` 白名单且不属于 skill / 已注册服务命令的行，转成 `service="shell", method="run", params={"command":"<整行>"}`；其它行保留为自然语言。
- 平台映射：Windows `cmd.exe /C`，Linux/macOS `/bin/sh -c`；`dir→ls`、`copy→cp`、`del/erase→rm`、`type→cat`、`move→mv`、`cls→clear`。
- 拒绝 `rm` / `rmdir` / `del` / `format` / `mkfs` / `dd` / `shutdown` / `sudo` / `chmod` / `chown` / `kill` / `reg` / `diskpart` 及 `|` `;` `&` 反引号 `>` `>>` 拼接与重定向。
- 执行边界：cwd 锁定工作区、路径经 `realpath` + `is_within` 复验、环境变量净化、超时与输出上限；`shell` / `javascript` 技能暂不支持执行。

---

## 5. 数据模型索引

请求模型位于 `src/modules/api/requests.py`，响应 DTO 位于 `src/modules/api/dto.py`；生成类扩展模型与本次新增 DTO 亦登记于此。字段级定义见 §3 各端点的请求体 / 响应表。

@@MODEL_INDEX@@

---

## 附录 A：端点速查表

@@SPEED_TABLE@@

---

## 附录 B：架构文档索引

- [BackendDesign.md](BackendDesign.md)：模块边界、线程模型、工具链、shell 服务与工作区。
- [SecurityAndAuditDesign.md](SecurityAndAuditDesign.md)：威胁模型、工作区权限、命令准入、审计事件。
- [FrontendBackendContract.md](FrontendBackendContract.md)：REST / SSE / WS / Qt bridge 统一契约。
- [ContextArchitecture.md](ContextArchitecture.md)：session-scoped context 与 prompt 装配。
- [GameSaveArchitecture.md](GameSaveArchitecture.md)：Slot / Snapshot / restore。
- [MemoryDesign.md](MemoryDesign.md)：记忆查询、删改与向量一致性。
- [ArchitectureDecisionRecords.md](ArchitectureDecisionRecords.md)：ADR-002 契约唯一权威源。
"""


def write_doc() -> None:
    total = len(ENDPOINTS)
    group_rows = []
    for key, meta in GROUPS.items():
        eps = [e for e in ENDPOINTS if e["group"] == key]
        group_rows.append([
            f"`{key}`", meta["label"], f"`{meta['prefix']}`", str(len(eps)),
            meta["description"],
        ])
    group_table = md_table(["group / tag", "名称", "路径前缀", "端点数", "说明"], group_rows)

    model_rows = []
    for name in sorted(REQUEST_MODELS):
        if name.startswith("_"):
            continue
        model_rows.append([f"`{name}`", "请求模型", "requests.py", str(len(REQUEST_MODELS[name]))])
    for name in sorted(DTO_MODELS):
        if name.startswith("_"):
            continue
        model_rows.append([f"`{name}`", "响应 DTO", "dto.py", str(len(DTO_MODELS[name]))])
    model_index = md_table(["模型", "类别", "文件", "字段数"], model_rows)

    speed_rows = []
    for e in ENDPOINTS:
        speed_rows.append([f"`{e['group']}`", e["method"], f"`/api{e['path']}`", f"`{e['op']}`", e["status"]])
    speed_table = md_table(["分组", "方法", "最终 URL", "op", "状态"], speed_rows)

    head = DOC_HEAD
    for key, value in {
        "@@BASELINE@@": BASELINE,
        "@@TOTAL@@": str(total),
        "@@ENABLED@@": str(total),
        "@@GROUPS@@": str(len(GROUPS)),
        "@@BASE@@": BASE_URL,
        "@@GROUP_TABLE@@": group_table,
    }.items():
        head = head.replace(key, value)

    parts: List[str] = [head]
    for gi, (key, meta) in enumerate(GROUPS.items(), 1):
        eps = [e for e in ENDPOINTS if e["group"] == key]
        parts.append(f"### 3.{gi} {meta['label']}（tag: `{key}`，{len(eps)} 个端点）\n")
        parts.append(f"{meta['description']}。路径前缀 `{meta['prefix']}`。\n")
        for i, ep in enumerate(eps, 1):
            parts.append(endpoint_section(ep, i))
        parts.append("\n")

    tail = SSE_WS_BRIDGE.replace("@@MODEL_INDEX@@", model_index).replace("@@SPEED_TABLE@@", speed_table)
    parts.append(tail)
    OUT_DOC.write_text("\n".join(parts), "utf-8")


# ==========================================================================
# 6. 自检
# ==========================================================================


def self_check() -> None:
    errors: List[str] = []
    ops, routes = set(), set()
    for e in ENDPOINTS:
        if e["op"] in ops:
            errors.append(f"op 重复: {e['op']}")
        ops.add(e["op"])
        key = f"{e['method']} {e['path']}"
        if key in routes:
            errors.append(f"路由冲突: {key}")
        routes.add(key)
        if f"{e['mod']}:{e['fn']}" not in HANDLERS:
            errors.append(f"handler 不存在: {e['mod']}:{e['fn']} ({e['op']})")
        if e["body"] and e["body"] not in REQUEST_MODELS:
            errors.append(f"请求模型不存在: {e['body']} ({e['op']})")
        if e["data"] and e["data"] not in DTO_MODELS and e["data"] not in ("str",):
            errors.append(f"响应 DTO 不存在: {e['data']} ({e['op']})")
        if e["dispatch"] not in ("loop", "thread", "main"):
            errors.append(f"非法 dispatch: {e['dispatch']} ({e['op']})")
    for key, meta in GROUPS.items():
        if not any(e["group"] == key for e in ENDPOINTS):
            errors.append(f"空分组: {key}")
    if errors:
        raise SystemExit("契约自检失败:\n  - " + "\n  - ".join(errors))
    print(f"[OK] 自检通过：{len(ENDPOINTS)} 端点 / {len(GROUPS)} 分组 / {len(ops)} op")


def main() -> None:
    self_check()
    write_endpoints()
    write_groups()
    write_doc()
    print(f"[OK] {OUT_ENDPOINTS.relative_to(ROOT)}  ({len(ENDPOINTS)} 端点)")
    print(f"[OK] {OUT_GROUPS.relative_to(ROOT)}  ({len(GROUPS)} 分组)")
    print(f"[OK] {OUT_DOC.relative_to(ROOT)}  ({len(OUT_DOC.read_text('utf-8').splitlines())} 行)")


if __name__ == "__main__":
    main()
