# 📚 src_py 项目文档
> 生成时间：2026-08-04 18:53:09
> 项目路径：`D:\Project\ChatBot\src_py`
---
## 📋 项目概览

## 📊 项目统计
| 指标|数值 |
| ------|------ |
总文件数|398
Python文件|123
类数量|0
函数数量|0
代码行数|0

---

## 🌳 项目目录结构

```text
📁 src_py/
├── cli/
│   ├── generates/
│   │   ├── config.py
│   │   └── pipline.py
│   └── main.py
├── modules/
│   ├── api/
│   │   ├── controllers/
│   │   │   ├── logger.py
│   │   │   ├── models.py
│   │   │   ├── pipline.py
│   │   │   ├── request.py
│   │   │   ├── service.py
│   │   │   └── websocket.py
│   │   └── server.py
│   ├── characters/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── orchestrator.py
│   │   └── presets.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   ├── manager.py
│   │   └── models.py
│   ├── context/
│   │   ├── audio.py
│   │   └── user.py
│   ├── devices/
│   │   ├── base.py
│   │   ├── config.py
│   │   └── keyboard.py
│   ├── events/
│   │   ├── __init__.py
│   │   ├── bus.py
│   │   ├── data.py
│   │   └── types.py
│   ├── logger/
│   │   ├── __init__.py
│   │   ├── animation.json
│   │   ├── log.py
│   │   └── types.py
│   ├── manager/
│   │   ├── service/
│   │   │   ├── decorator.py
│   │   │   └── manager.py
│   │   ├── task/
│   │   │   ├── decorator.py
│   │   │   ├── reference.py
│   │   │   └── schedular.py
│   │   ├── websocket/
│   │   │   ├── manager.py
│   │   │   └── models.py
│   │   ├── base.py
│   │   ├── character.py
│   │   ├── dispatcher.py
│   │   └── pipeline.py
│   ├── memory/
│   │   ├── docs/
│   │   │   └── 相关记忆算法.md
│   │   ├── emdedding/
│   │   │   ├── __init__.py
│   │   │   ├── adapters.py
│   │   │   └── base.py
│   │   ├── storage/
│   │   │   ├── base.py
│   │   │   ├── database.py
│   │   │   ├── markdown.py
│   │   │   └── sqlite.py
│   │   ├── compression.py
│   │   ├── main.py
│   │   ├── managers.py
│   │   ├── models.py
│   │   ├── token.py
│   │   └── utils.py
│   ├── pipeline/
│   │   ├── adapters/
│   │   │   ├── asr/
│   │   │   │   └── adapter.py
│   │   │   ├── landmarker/
│   │   │   │   ├── face.py
│   │   │   │   └── models.py
│   │   │   ├── llm/
│   │   │   │   ├── adapter.py
│   │   │   │   ├── client.py
│   │   │   │   └── types.py
│   │   │   ├── ocr/
│   │   │   │   └── adapter.py
│   │   │   └── tts/
│   │   │       ├── adapter.py
│   │   │       ├── client.py
│   │   │       └── models.py
│   │   ├── downloads/
│   │   │   ├── asr.py
│   │   │   ├── landmarker.py
│   │   │   └── ocr.py
│   │   ├── emotion/
│   │   │   └── predictor.py
│   │   ├── balance.py
│   │   ├── chat.py
│   │   ├── enum.py
│   │   └── manager.py
│   ├── routes/
│   │   ├── intent.py
│   │   ├── keywords.json
│   │   ├── models.py
│   │   └── words.py
│   ├── services/
│   │   ├── browser/
│   │   │   ├── scripts/
│   │   │   │   ├── distiller.js
│   │   │   │   └── stealth.js
│   │   │   ├── browser.py
│   │   │   ├── distiller.py
│   │   │   ├── driver.py
│   │   │   └── models.py
│   │   ├── game/
│   │   │   └── minecraft.py
│   │   ├── knowledge/
│   │   │   └── query/
│   │   │       ├── adapter.py
│   │   │       ├── models.py
│   │   │       └── serach.py
│   │   ├── live2d/
│   │   │   ├── audio.py
│   │   │   ├── canvas.py
│   │   │   ├── components.py
│   │   │   └── views.py
│   │   ├── obs/
│   │   │   ├── client.py
│   │   │   ├── done_table.md
│   │   │   └── models.py
│   │   ├── qqbot/
│   │   │   ├── client.py
│   │   │   └── models.py
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── config.py
│   ├── tools/
│   │   ├── sanbox/
│   │   │   ├── executor.py
│   │   │   └── restricted.py
│   │   ├── services/
│   │   │   ├── exceute.py
│   │   │   ├── formatter.py
│   │   │   └── models.py
│   │   ├── skills/
│   │   │   ├── manager.py
│   │   │   ├── models.py
│   │   │   └── sandbox.py
│   │   ├── ctl.py
│   │   └── models.py
│   ├── types/
│   │   ├── memory/
│   │   │   ├── context.py
│   │   │   └── database.py
│   │   ├── api.py
│   │   └── common.py
│   ├── ui/
│   │   ├── app.py
│   │   └── channel.py
│   ├── utils/
│   │   ├── audio.py
│   │   ├── audio_stream.py
│   │   ├── class.py
│   │   ├── decorators.py
│   │   ├── file.py
│   │   ├── http.py
│   │   ├── response.py
│   │   └── util.py
│   ├── __init__.py
│   ├── app.py
│   └── runtime.py
├── main.py
├── test.py
└── test.wav
```

---

## 📄 Python文件详细分析

### 📄 cli\generates\config.py

- **文件大小**: 0.6 KB
- **代码行数**: 17

#### 导入依赖

```python
from modules.runtime import RuntimePath
from modules.services.config import BrowserConfig
from modules.services.config import Live2DConfig
from modules.services.config import ObsConfig
from modules.services.config import QQBotConfig
from modules.services import ServiceId
from modules.utils.file import write_yaml
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `generate_default_config_file` | 同步 |  |

---

### 📄 cli\generates\pipline.py

- **文件大小**: 17.3 KB
- **代码行数**: 489

#### 模块说明

> pipeline.json 配置自动生成器
=================================
功能：
    扫描 modules/pipeline/adapters/ 下所有 adapter 类，
    通过 inspect 反射提取 __init__ 参数签名，
    自动生成符合 PipelineManager 加载格式的 pipeline.json。

输出结构（与 pipeline.py 对齐）：
    {
        "asr": {
            "whisper": {
                "name": "whisper",
                "description": "",          ← 留空，手动填写
                "tags": [],
                "config": {
                    "model_size": {
                        "type": "str",
                        "default": "base",
                        "required": false,
                        "description": ""
                    }
                }
            }
        },
        "tts": { ... },
        "llm": { ... },
        "ocr": { ... }
    }

用法：
    # 在项目根目录执行
    cd D:\Project\ChatBot
    python cli/generates/config.py

    # 指定输出路径
    python cli/generates/config.py --output ./modules/config/pipeline.json

    # 指定 modules 目录路径
    python cli/generates/config.py --modules ./modules

    # 生成后交互式填写 description
    python cli/generates/config.py --interactive

#### 导入依赖

```python
import argparse
import inspect
import json
import os
import re
import sys
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `camel_to_snake` | 同步 | CamelCase → snake_case |
| `strip_adapter_suffix` | 同步 | WhisperASRAdapter → whisper_asr / ASRAdapter → asr |
| `get_provider_name` | 同步 | WhisperASRAdapter → whisper |
| `python_type_to_json_type` | 同步 | 把 Python 类型注解转为 JSON Schema 风格的字符串 |
| `default_to_jsonable` | 同步 |  |
| `extract_adapter_info` | 同步 | 从 adapter 类提取信息，返回 provider 条目。 |
| `discover_adapters` | 同步 | 自动发现并提取所有 adapter。 |
| `build_final_config` | 同步 | 将发现结果转为 pipeline.json 最终格式。 |
| `merge_with_existing` | 同步 | 如果已有 pipeline.json，合并保留手动填写的 description / tags。 |
| `interactive_fill` | 同步 | 交互式让用户输入每个 provider 的 description |
| `build_frontend_manifest` | 同步 | 生成给前端用的精简清单（不含敏感默认值以外的冗余信息）。 |
| `main` | 同步 |  |

---

### 📄 cli\main.py

- **文件大小**: 2.2 KB
- **代码行数**: 69

#### 导入依赖

```python
import argparse
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `build_pipline_json_args` | 同步 |  |
| `build_service_config_args` | 同步 |  |
| `main` | 同步 |  |

---

### 📄 main.py

- **文件大小**: 0.5 KB
- **代码行数**: 21

#### 导入依赖

```python
import asyncio
import os
import sys
import os
from modules.app import create_app
import os
import signal
import traceback
```

---

### 📄 modules\__init__.py

- **文件大小**: 0.9 KB
- **代码行数**: 38

#### 导入依赖

```python
from functools import wraps
from threading import Lock
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `singleton` | 同步 |  |
| `wrapper` | 同步 |  |
| `__init__` | 同步 |  |
| `__new__` | 同步 |  |

---

### 📄 modules\api\controllers\logger.py

- **文件大小**: 1.2 KB
- **代码行数**: 46

⚠️ **语法错误**:
```
invalid non-printable character U+FEFF (<unknown>, line 1)
```

---

### 📄 modules\api\controllers\models.py

- **文件大小**: 0.2 KB
- **代码行数**: 7

#### 导入依赖

```python
from typing import Any
from typing import Dict
from typing import Optional
from pydantic import BaseModel
```

#### 类定义

##### CLASS: WebSocketRequest(BaseModel)

---

### 📄 modules\api\controllers\pipline.py

- **文件大小**: 0.7 KB
- **代码行数**: 20

#### 导入依赖

```python
from typing import Optional
from fastapi import APIRouter
from fastapi import Query
from pipeline.enum import AdapterType
from utils import response
from manager.pipeline import pipeline_manager
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_supported_models` | 异步 |  |

---

### 📄 modules\api\controllers\request.py

- **文件大小**: 2.0 KB
- **代码行数**: 65

#### 导入依赖

```python
from __future__ import annotations
import platform
from typing import Any
from typing import Dict
import os
from fastapi import APIRouter
from runtime import RuntimePath
from utils import response
from config import get_config
import subprocess
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `open_folder` | 同步 |  |
| `llm_config` | 同步 |  |
| `get_system_config` | 同步 |  |

---

### 📄 modules\api\controllers\service.py

- **文件大小**: 4.4 KB
- **代码行数**: 105

#### 导入依赖

```python
from typing import Optional
from fastapi import APIRouter
from fastapi import Query
from services import ServiceId
from services import ServiceState
from utils import response
from events import emit
from events import BaseEvent
from events import types
from manager.service.manager import service_manager
from services.live2d.views import Live2DView
from services.obs.client import OBSClient
from services.qqbot.client import QQBotClient
from services.browser.browser import Browser
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_service_config_info` | 同步 |  |
| `start_service` | 同步 |  |
| `enable_service` | 同步 |  |
| `stop_service` | 同步 |  |
| `get_qqbot_info` | 同步 |  |

---

### 📄 modules\api\controllers\websocket.py

- **文件大小**: 9.3 KB
- **代码行数**: 272

#### 导入依赖

```python
from __future__ import annotations
import base64
from datetime import datetime
import time
from typing import Optional
from typing import TypeVar
import uuid
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from pipeline import chat
from server import get_web_app
from models import WebSocketRequest
from  import events
from logger import logger
from manager.websocket.manager import get_websocket_manager
from pipeline.downloads.landmarker import download_google_facelandmarker
from pipeline.downloads.ocr import download_paddle_ocr
from pipeline.downloads.ocr import download_umi_ocr
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `handle_download_model` | 异步 |  |
| `chat_complete` | 异步 |  |
| `handle_chat` | 异步 |  |
| `_register_event` | 同步 |  |
| `_unregister_event` | 同步 |  |
| `handle_event` | 异步 |  |
| `gerenate_client_id` | 同步 |  |
| `websocket_connect` | 异步 |  |
| `success_callback` | 异步 |  |
| `error_callback` | 异步 |  |
| `running_callback` | 异步 |  |
| `send_log_to_client` | 异步 |  |
| `handle_qqbot_event` | 异步 |  |

---

### 📄 modules\api\server.py

- **文件大小**: 6.2 KB
- **代码行数**: 205

#### 导入依赖

```python
import asyncio
import logging
import os
import threading
from typing import Any
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import time
from runtime import StandardPaths
from events.data import BaseEvent
from events import emit
from events import types
from logger import logger
import socket
import uvicorn
from controllers.websocket import websocket_connect
from runtime import RuntimePath
from config import get_config
from fastapi.middleware.cors import CORSMiddleware
# ... 还有 5 个导入
```

#### 类定义

##### CLASS: _Web

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_app` | 同步 |  |
| `register_router` | 同步 |  |
| `mount_static` | 同步 |  |

##### CLASS: UvicornLoggerHandler(logging.Handler)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `emit` | 同步 |  |
| `format` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__app_server` | 同步 |  |
| `start_web_server` | 同步 |  |
| `_shutdown` | 异步 |  |
| `stop_web_server` | 同步 |  |
| `get_web_app` | 同步 |  |
| `__init__` | 同步 |  |
| `get_app` | 同步 |  |
| `register_router` | 同步 |  |
| `mount_static` | 同步 |  |
| `__init__` | 同步 |  |
| `emit` | 同步 |  |
| `format` | 同步 |  |
| `fallback` | 异步 |  |

---

### 📄 modules\app.py

- **文件大小**: 5.9 KB
- **代码行数**: 176

#### 导入依赖

```python
import asyncio
from re import S
import sys
import threading
from events import emit
from events import types
from events import BaseEvent
from typing import Literal
from logger import logger
from manager import pipeline
from manager.task import schedular
from manager.service import manager
from manager.dispatcher import get_main_thread_dispatcher
from config import load_config
from api.server import stop_web_server
from api.server import start_web_server
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QSystemTrayIcon
from PyQt5.QtWidgets import QMenu
# ... 还有 7 个导入
```

#### 类定义

##### CLASS: Application

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__new__` | 同步 |  |
| `init` | 同步 |  |
| `close` | 异步 |  |
| `run_web` | 同步 |  |
| `run` | 异步 | 主入口 - 主线程运行 Qt，后台线程运行 asyncio |
| `close_app` | 同步 |  |
| `ui` | 异步 |  |
| `__create_system_tray` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `create_app` | 同步 |  |
| `get_app` | 同步 |  |
| `__init__` | 同步 |  |
| `__new__` | 同步 |  |
| `init` | 同步 |  |
| `close` | 异步 |  |
| `run_web` | 同步 |  |
| `run` | 异步 | 主入口 - 主线程运行 Qt，后台线程运行 asyncio |
| `close_app` | 同步 |  |
| `ui` | 异步 |  |
| `__create_system_tray` | 同步 |  |

---

### 📄 modules\characters\__init__.py

- **文件大小**: 0.6 KB
- **代码行数**: 34

#### 模块说明

> character_system/__init__.py

#### 导入依赖

```python
from models import Character
from models import CharacterAttributes
from models import CharacterState
from models import CharacterStatus
from models import ContextType
from models import BuiltPrompt
from orchestrator import CharacterOrchestrator
from presets import create_ku_zixunshi
from presets import create_youling_loli
from presets import create_custom
from presets import list_presets
from presets import create_from_preset
```

---

### 📄 modules\characters\models.py

- **文件大小**: 5.6 KB
- **代码行数**: 151

#### 模块说明

> character_system/models.py — 角色系统数据模型

定义角色、角色状态、上下文分离结构。

#### 导入依赖

```python
from __future__ import annotations
import uuid
import time
from dataclasses import dataclass
from dataclasses import field
from dataclasses import asdict
from typing import Any
from typing import Dict
from typing import List
from typing import TypedDict
from enum import Enum
from routes.models import RouteType
```

#### 类定义

##### CLASS: CharacterStatus(str, Enum)

##### CLASS: ContextType(str, Enum)

> 上下文类型标识

##### CLASS: CharacterAttributes

> 角色属性（用于动态构建 prompt）

##### CLASS: CharacterState

> 角色运行时状态（切换时保存/恢复）

| 方法 | 类型 | 说明 |
|------|------|------|
| `touch` | 同步 |  |
| `add_message` | 同步 |  |
| `get_recent` | 同步 | 取最近 n 条，转成 {role, content} 格式 |

##### CLASS: Character

> 完整角色定义

| 方法 | 类型 | 说明 |
|------|------|------|
| `__post_init__` | 同步 |  |

##### CLASS: PromptSegment(TypedDict)

##### CLASS: BuiltPrompt

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `touch` | 同步 |  |
| `add_message` | 同步 |  |
| `get_recent` | 同步 | 取最近 n 条，转成 {role, content} 格式 |
| `__post_init__` | 同步 |  |
| `to_dict` | 同步 |  |

---

### 📄 modules\characters\orchestrator.py

- **文件大小**: 13.4 KB
- **代码行数**: 339

#### 导入依赖

```python
from __future__ import annotations
import json
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import AsyncGenerator
from typing import Awaitable
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from src_py.modules.pipeline.manager import LLM
from routes.intent import IntentRouter
from routes.models import RouteType
from tools.ctl import ServiceOrchestrator
from config.builder import PromptBuilder
from manager.character import character_manager
from models import Character
from context.user import UserContext
```

#### 类定义

##### CLASS: OrchestrationResult

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

##### CLASS: CharacterOrchestrator

> Route user input between clean role chat and a lean background task agent.

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `process` | 异步 |  |
| `process_stream` | 异步 |  |
| `_handle_chat` | 异步 |  |
| `_handle_task` | 异步 |  |
| `_handle_task_stream` | 异步 |  |
| `_handle_chat_stream` | 异步 |  |
| `_lightweight_route_judge` | 异步 |  |
| `_recent_dialogue` | 同步 |  |
| `_record_character_state` | 同步 |  |
| `_update_affection_from_interaction` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |
| `__init__` | 同步 |  |
| `process` | 异步 |  |
| `process_stream` | 异步 |  |
| `_handle_chat` | 异步 |  |
| `_handle_task` | 异步 |  |
| `_handle_task_stream` | 异步 |  |
| `_handle_chat_stream` | 异步 |  |
| `_lightweight_route_judge` | 异步 |  |
| `_recent_dialogue` | 同步 |  |
| `_record_character_state` | 同步 |  |
| `_update_affection_from_interaction` | 同步 |  |

---

### 📄 modules\characters\presets.py

- **文件大小**: 8.1 KB
- **代码行数**: 204

#### 模块说明

> character_system/presets.py — 角色预设模板

提供几个开箱即用的角色模板，用户也可以自定义。

#### 导入依赖

```python
from __future__ import annotations
from typing import Optional
from models import Character
from models import CharacterAttributes
from models import CharacterState
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `create_qingmei_zhusma` | 同步 | 青梅竹马型 — 开朗黏人 |
| `create_ku_zixunshi` | 同步 | 高冷咨询师型 — 专业克制 |
| `create_youling_loli` | 同步 | 幽灵萝莉型 — 可爱搞怪 |
| `create_custom` | 同步 | 创建自定义角色 |
| `list_presets` | 同步 | 列出所有预设角色 |
| `create_from_preset` | 同步 | 从预设创建角色 |

---

### 📄 modules\config\__init__.py

- **文件大小**: 0.5 KB
- **代码行数**: 19

#### 导入依赖

```python
from typing import Optional
from manager import ConfigManager
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_config` | 同步 |  |
| `load_config` | 同步 |  |
| `reload_config` | 同步 |  |
| `save_config` | 同步 |  |

---

### 📄 modules\config\builder.py

- **文件大小**: 13.5 KB
- **代码行数**: 343

#### 导入依赖

```python
from __future__ import annotations
import random
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from manager.task.decorator import sync_task_scheduler
from routes.models import RouteType
from characters.models import BuiltPrompt
from characters.models import Character
from characters.models import ContextType
from characters.models import PromptSegment
from runtime import RuntimePath
```

#### 类定义

##### CLASS: PromptBuilder

> Build separated prompts for role chat, background task commands and final replies.

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `read_prompts` | 同步 | Read prompts from file. |
| `load_prompts` | 同步 | Load prompts from file. |
| `format_memory_context` | 同步 | Format memory context into a string. |
| `build` | 同步 |  |
| `_build_chat_segments` | 同步 |  |
| `_build_task_segments` | 同步 |  |
| `_build_mixed_segments` | 同步 |  |
| `_build_randomness_segment` | 同步 |  |
| `_describe_mood` | 同步 |  |
| `_describe_affection` | 同步 |  |
| `build_commands_prompt` | 同步 |  |
| `build_skill_prompt` | 同步 |  |
| `to_messages` | 同步 |  |
| `to_messages_with_history` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `read_prompts` | 同步 | Read prompts from file. |
| `load_prompts` | 同步 | Load prompts from file. |
| `format_memory_context` | 同步 | Format memory context into a string. |
| `build` | 同步 |  |
| `_build_chat_segments` | 同步 |  |
| `_build_task_segments` | 同步 |  |
| `_build_mixed_segments` | 同步 |  |
| `_build_randomness_segment` | 同步 |  |
| `_describe_mood` | 同步 |  |
| `_describe_affection` | 同步 |  |
| `build_commands_prompt` | 同步 |  |
| `build_skill_prompt` | 同步 |  |
| `to_messages` | 同步 |  |
| `to_messages_with_history` | 同步 |  |

---

### 📄 modules\config\manager.py

- **文件大小**: 4.9 KB
- **代码行数**: 132

#### 导入依赖

```python
from typing import Any
from typing import Dict
from typing import Optional
from typing import Union
from pydantic import BaseModel
from pydantic import Field
from typing import List
from typing import Tuple
from  import models
from services import config
from utils.file import read_env
from utils.file import write_env
```

#### 类定义

##### CLASS: AppConfig(BaseModel)

##### CLASS: ConfigLoader

> 配置加载器 - 负责从文件加载配置

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `load` | 同步 | 加载配置 |
| `__apply_config` | 同步 | 将字典配置应用到AppConfig对象 |
| `__get_binding_attrs` | 同步 | 获取section绑定的属性列表 |

##### CLASS: ConfigManager

| 方法 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `initialize` | 同步 |  |
| `get_config` | 同步 |  |
| `reload` | 同步 |  |
| `save_config` | 同步 |  |
| `__serialize_config` | 同步 | 序列化配置为字典 |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `load` | 同步 | 加载配置 |
| `__apply_config` | 同步 | 将字典配置应用到AppConfig对象 |
| `__get_binding_attrs` | 同步 | 获取section绑定的属性列表 |
| `__new__` | 同步 |  |
| `initialize` | 同步 |  |
| `get_config` | 同步 |  |
| `reload` | 同步 |  |
| `save_config` | 同步 |  |
| `__serialize_config` | 同步 | 序列化配置为字典 |

---

### 📄 modules\config\models.py

- **文件大小**: 4.5 KB
- **代码行数**: 115

#### 导入依赖

```python
from __future__ import annotations
from typing import Any
from typing import Dict
from typing import List
from pydantic import BaseModel
from pydantic import Field
from runtime import RuntimePath
from pipeline.enum import ASRProviderType
from pipeline.enum import LLMProviderType
from pipeline.enum import TTSProviderType
```

#### 类定义

##### CLASS: _BaseConfig(BaseModel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |
| `get_config_items` | 同步 |  |
| `update_from_dict` | 同步 |  |

##### CLASS: SkillsConfig(_BaseConfig)

##### CLASS: SqliteConfig(_BaseConfig)

##### CLASS: LogConfig(_BaseConfig)

##### CLASS: NetworkConfig(_BaseConfig)

##### CLASS: WebConfig(_BaseConfig)

| 方法 | 类型 | 说明 |
|------|------|------|
| `update_web_config` | 同步 |  |

##### CLASS: TTSConfig(_BaseConfig)

| 方法 | 类型 | 说明 |
|------|------|------|
| `update_tts_config` | 同步 |  |

##### CLASS: LLMConfig(_BaseConfig)

| 方法 | 类型 | 说明 |
|------|------|------|
| `update_llm_config` | 同步 |  |

##### CLASS: ASRConfig(_BaseConfig)

| 方法 | 类型 | 说明 |
|------|------|------|
| `update_asr_config` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |
| `get_config_items` | 同步 |  |
| `update_from_dict` | 同步 |  |
| `update_web_config` | 同步 |  |
| `update_tts_config` | 同步 |  |
| `update_llm_config` | 同步 |  |
| `update_asr_config` | 同步 |  |

---

### 📄 modules\context\audio.py

- **文件大小**: 2.3 KB
- **代码行数**: 63

#### 导入依赖

```python
from pathlib import Path
from threading import Lock
from typing import Dict
import uuid
from runtime import RuntimePath
from manager.task.decorator import sync_task_scheduler
from utils.audio import write_audio_chunks
```

#### 类定义

##### CLASS: AudioContext

| 方法 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `get_all_audio_paths` | 同步 |  |
| `add_audio_chunk` | 同步 |  |
| `get_current_audio` | 同步 |  |
| `get_current_audio_bytes` | 同步 |  |
| `reset_current_audio` | 同步 |  |
| `save_audio_chunks` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `get_all_audio_paths` | 同步 |  |
| `add_audio_chunk` | 同步 |  |
| `get_current_audio` | 同步 |  |
| `get_current_audio_bytes` | 同步 |  |
| `reset_current_audio` | 同步 |  |
| `save_audio_chunks` | 同步 |  |

---

### 📄 modules\context\user.py

- **文件大小**: 8.3 KB
- **代码行数**: 228

#### 导入依赖

```python
from __future__ import annotations
import asyncio
import json
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any
from typing import Callable
from typing import Deque
from typing import Dict
from typing import List
from typing import Optional
from uuid import uuid4
from types.common import Role
from types.memory.context import Message
from manager.task import decorator
from memory.main import HybridMemorySystem
```

#### 类定义

##### CLASS: SafeSessionContext

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `add_interaction` | 异步 |  |
| `_estimate_tokens` | 同步 |  |
| `get_recent_history` | 同步 |  |
| `cleanup` | 异步 |  |

##### CLASS: UserContext

| 方法 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `init_memory` | 异步 |  |
| `get_current_messages` | 同步 |  |
| `clear_messages` | 同步 |  |
| `find_cached_reply` | 同步 |  |
| `build_memory_messages` | 异步 |  |
| `add_message` | 异步 |  |
| `add_user_message` | 异步 |  |
| `add_assistant_message` | 异步 |  |
| `add_tool_calls_message` | 异步 |  |
| `add_tool_call_message` | 异步 |  |
| `__next_id` | 同步 |  |
| `__remove_duplicates` | 同步 |  |
| `close` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `add_interaction` | 异步 |  |
| `_estimate_tokens` | 同步 |  |
| `get_recent_history` | 同步 |  |
| `cleanup` | 异步 |  |
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `init_memory` | 异步 |  |
| `get_current_messages` | 同步 |  |
| `clear_messages` | 同步 |  |
| `find_cached_reply` | 同步 |  |
| `build_memory_messages` | 异步 |  |
| `add_message` | 异步 |  |
| `add_user_message` | 异步 |  |
| `add_assistant_message` | 异步 |  |
| `add_tool_calls_message` | 异步 |  |
| `add_tool_call_message` | 异步 |  |
| `__next_id` | 同步 |  |
| `__remove_duplicates` | 同步 |  |
| `close` | 异步 |  |

---

### 📄 modules\devices\base.py

- **文件大小**: 0.1 KB
- **代码行数**: 4

#### 类定义

##### CLASS: BaseDevice

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |

---

### 📄 modules\devices\config.py

- **文件大小**: 0.0 KB
- **代码行数**: 2

#### 类定义

##### CLASS: KeyboardConfig

---

### 📄 modules\devices\keyboard.py

- **文件大小**: 5.4 KB
- **代码行数**: 151

#### 导入依赖

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
from typing import Callable
from typing import Optional
import wave
from  import events
from base import BaseDevice
from pynput import keyboard
from pyaudio import PyAudio
from pyaudio import paInt16
```

#### 类定义

##### CLASS: StreamingAudioRecorder

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `set_on_audio_segment` | 同步 |  |
| `start_recording` | 同步 | 开始录音，并在循环中实时推送音频片段 |
| `stop_recording` | 同步 |  |
| `_to_wav_bytes` | 同步 | 将原始音频数据转为WAV格式 |

##### CLASS: KeyboardDevice(BaseDevice)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_key` | 同步 |  |
| `on_press` | 同步 |  |
| `on_release` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `set_on_audio_segment` | 同步 |  |
| `start_recording` | 同步 | 开始录音，并在循环中实时推送音频片段 |
| `stop_recording` | 同步 |  |
| `_to_wav_bytes` | 同步 | 将原始音频数据转为WAV格式 |
| `__init__` | 同步 |  |
| `get_key` | 同步 |  |
| `on_press` | 同步 |  |
| `on_release` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |

---

### 📄 modules\events\__init__.py

- **文件大小**: 2.6 KB
- **代码行数**: 75

#### 导入依赖

```python
from functools import wraps
from typing import Any
from typing import Callable
from typing import Optional
from typing import TypeVar
from bus import event_bus
from data import BaseEvent
from  import types
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `on` | 同步 |  |
| `off` | 同步 |  |
| `emit` | 同步 |  |
| `on_event` | 同步 |  |
| `on_event_class` | 同步 | 事件类装饰器，用于注册事件处理方法 |
| `wrapper` | 同步 |  |
| `decorator` | 同步 |  |
| `offEvent` | 同步 |  |
| `new_init` | 同步 |  |
| `new_del` | 同步 |  |
| `new_del` | 同步 |  |

---

### 📄 modules\events\bus.py

- **文件大小**: 2.9 KB
- **代码行数**: 81

#### 导入依赖

```python
import asyncio
import inspect
from typing import Callable
from typing import Any
from typing import Optional
from typing import TypeVar
from typing import TypedDict
from typing import Dict
from typing import Generic
from typing import List
from collections import defaultdict
from threading import RLock
from inspect import iscoroutinefunction
import weakref
```

#### 类定义

##### CLASS: LeakProofEventBus(<ast.Subscript object at 0x00000246582F1C90>)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `on` | 同步 |  |
| `off` | 同步 | 取消注册 |
| `emit` | 同步 |  |
| `clear` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `on` | 同步 |  |
| `off` | 同步 | 取消注册 |
| `emit` | 同步 |  |
| `clear` | 同步 |  |

---

### 📄 modules\events\data.py

- **文件大小**: 1.3 KB
- **代码行数**: 50

#### 导入依赖

```python
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Optional
from typing import TypedDict
from pydantic import BaseModel
from  import types
```

#### 类定义

##### CLASS: BaseEvent(BaseModel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

##### CLASS: LogEventData(BaseEvent)

##### CLASS: ChatEventData(BaseEvent)

##### CLASS: QQBotEventData

##### CLASS: Data

##### CLASS: Data

##### CLASS: Chat

##### CLASS: C2C_MSG_CREATE

##### CLASS: ON_FRIEND_ADDED

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

---

### 📄 modules\events\types.py

- **文件大小**: 3.1 KB
- **代码行数**: 92

#### 类定义

##### CLASS: AppEventType

##### CLASS: Live2DEventType

##### CLASS: Live2DFaceEventType

##### CLASS: LiveStreamEventType

##### CLASS: ObsEventType

##### CLASS: QQBotEventType

##### CLASS: PipelineEventType

##### CLASS: BrowserEventType

##### CLASS: WebSocketEventType

##### CLASS: DownloadEventType

##### CLASS: TaskSchedularEventType

##### CLASS: ManagerEventType

##### CLASS: MainThreadDispatcherEventType

##### CLASS: KeyboardEventType

---

### 📄 modules\logger\__init__.py

- **文件大小**: 0.4 KB
- **代码行数**: 17

#### 导入依赖

```python
from log import Logger
from types import LogLevel
from types import LogSource
from types import LoggerRecord
from config import get_config
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `create_logger` | 同步 |  |

---

### 📄 modules\logger\log.py

- **文件大小**: 15.4 KB
- **代码行数**: 413

#### 导入依赖

```python
from contextlib import suppress
import os
from pathlib import Path
import logging
import sys
import threading
import time
from typing import Dict
from typing import List
from typing import Optional
import queue
from manager.task.decorator import sync_task_scheduler
from events.types import WebSocketEventType
from  import types
from types.common import TermColors
from events import emit
from events.data import BaseEvent
```

#### 类定义

##### CLASS: ColorFormatter(logging.Formatter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `format` | 同步 |  |

##### CLASS: OptimizedBatchLogHandler(logging.Handler)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `emit` | 同步 |  |
| `start` | 同步 |  |
| `__wait_for_logs` | 同步 |  |
| `__process_logs` | 同步 |  |
| `__print_log_color` | 同步 |  |
| `__flush_current_batch` | 同步 |  |
| `flush` | 同步 | 刷新当前批次到文件 |
| `__write_batch_to_file` | 同步 | 优化的文件写入 |
| `stop` | 同步 |  |

##### CLASS: Logger

| 方法 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `get_logging_levels` | 同步 |  |
| `get_logging_level` | 同步 | 转换日志级别字符串为logging级别 |
| `init` | 同步 |  |
| `__create_handler` | 同步 |  |
| `info` | 同步 |  |
| `exception` | 同步 |  |
| `critical` | 同步 |  |
| `error` | 同步 |  |
| `warning` | 同步 |  |
| `debug` | 同步 |  |
| `log` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `__enter__` | 同步 | 上下文管理器支持 |
| `__exit__` | 同步 | 上下文管理器退出 |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `format` | 同步 |  |
| `__init__` | 同步 |  |
| `emit` | 同步 |  |
| `start` | 同步 |  |
| `__wait_for_logs` | 同步 |  |
| `__process_logs` | 同步 |  |
| `__print_log_color` | 同步 |  |
| `__flush_current_batch` | 同步 |  |
| `flush` | 同步 | 刷新当前批次到文件 |
| `__write_batch_to_file` | 同步 | 优化的文件写入 |
| `stop` | 同步 |  |
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `get_logging_levels` | 同步 |  |
| `get_logging_level` | 同步 | 转换日志级别字符串为logging级别 |
| `init` | 同步 |  |
| `__create_handler` | 同步 |  |
| `info` | 同步 |  |
| `exception` | 同步 |  |
| `critical` | 同步 |  |
| `error` | 同步 |  |
| `warning` | 同步 |  |
| `debug` | 同步 |  |
| `log` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `__enter__` | 同步 | 上下文管理器支持 |
| `__exit__` | 同步 | 上下文管理器退出 |

---

### 📄 modules\logger\types.py

- **文件大小**: 2.1 KB
- **代码行数**: 82

#### 导入依赖

```python
from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any
from typing import Dict
from typing import Optional
from typing import TypedDict
from datetime import datetime
import traceback
```

#### 类定义

##### CLASS: LogSource(str, Enum)

##### CLASS: LogLevel

| 方法 | 类型 | 说明 |
|------|------|------|
| `from_logging_level` | 同步 |  |

##### CLASS: AnimationStyle(TypedDict)

##### CLASS: LoggerRecord

| 方法 | 类型 | 说明 |
|------|------|------|
| `from_logging_record` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `from_logging_level` | 同步 |  |
| `from_logging_record` | 同步 |  |

---

### 📄 modules\manager\base.py

- **文件大小**: 0.4 KB
- **代码行数**: 17

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
from threading import Lock
```

#### 类定义

##### CLASS: _BaseManager(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `stop` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `stop` | 同步 |  |

---

### 📄 modules\manager\character.py

- **文件大小**: 11.5 KB
- **代码行数**: 307

#### 模块说明

> character_system/manager.py — 角色管理器（全局单例）

核心职责:
    1. 角色的注册/注销/切换
    2. 每个角色独立的状态保存与恢复
    3. 全局共享一个"角色上下文"，切换 = 切回之前的状态

#### 导入依赖

```python
from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from src_py.modules.runtime import RuntimePath
from task.decorator import sync_task_scheduler
from events import on_event_class
from events import types
from utils.file import read_json
from utils.file import read_yaml
from utils.file import write_json
from logger import logger
from characters.models import Character
from characters.models import CharacterState
from characters.models import CharacterAttributes
from characters.models import CharacterStatus
# ... 还有 1 个导入
```

#### 类定义

##### CLASS: CharacterManager(_BaseManager)

> 全局角色管理器（单例）。

设计要点:
    - 所有角色存储在 _characters 字典中
    - 当前活跃角色 _current_id，切换时自动保存旧角色状态
    - 持久化到 JSON 文件（可选）
    - 线程安全（使用锁）

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `register` | 同步 | 注册新角色，返回角色 ID |
| `unregister` | 同步 | 注销角色 |
| `get` | 同步 |  |
| `get_all` | 同步 |  |
| `get_list` | 同步 | 返回角色摘要列表（不含完整消息历史） |
| `switch_to` | 同步 | 切换到指定角色，自动保存当前角色状态 |
| `get_current` | 同步 | 获取当前活跃角色 |
| `current_id` | 同步 |  |
| `update_mood` | 同步 | 更新角色心情 |
| `update_affection` | 同步 | 增减好感度 |
| `add_message` | 同步 | 为指定角色添加一条消息 |
| `get_messages` | 同步 | 获取角色最近 N 条消息 |
| `clear_messages` | 同步 | 清空角色消息历史 |
| `add_task` | 同步 | 为角色添加后台任务 |
| `get_pending_tasks` | 同步 |  |
| `complete_task` | 同步 | 完成任务，移入历史 |
| `save` | 同步 | 保存到 JSON 文件 |
| `load` | 同步 | 从 JSON 文件加载 |
| `set_storage_path` | 同步 |  |
| `set_auto_save` | 同步 |  |
| `stop` | 同步 |  |
| `load_default_characters` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `register` | 同步 | 注册新角色，返回角色 ID |
| `unregister` | 同步 | 注销角色 |
| `get` | 同步 |  |
| `get_all` | 同步 |  |
| `get_list` | 同步 | 返回角色摘要列表（不含完整消息历史） |
| `switch_to` | 同步 | 切换到指定角色，自动保存当前角色状态 |
| `get_current` | 同步 | 获取当前活跃角色 |
| `current_id` | 同步 |  |
| `update_mood` | 同步 | 更新角色心情 |
| `update_affection` | 同步 | 增减好感度 |
| `add_message` | 同步 | 为指定角色添加一条消息 |
| `get_messages` | 同步 | 获取角色最近 N 条消息 |
| `clear_messages` | 同步 | 清空角色消息历史 |
| `add_task` | 同步 | 为角色添加后台任务 |
| `get_pending_tasks` | 同步 |  |
| `complete_task` | 同步 | 完成任务，移入历史 |
| `save` | 同步 | 保存到 JSON 文件 |
| `load` | 同步 | 从 JSON 文件加载 |
| `set_storage_path` | 同步 |  |
| `set_auto_save` | 同步 |  |
| `stop` | 同步 |  |
| `load_default_characters` | 同步 |  |

---

### 📄 modules\manager\dispatcher.py

- **文件大小**: 6.6 KB
- **代码行数**: 179

#### 导入依赖

```python
import asyncio
import threading
from concurrent import futures
from logger import logger
from events import on_event_class
from events import types
from base import _BaseManager
```

#### 类定义

##### CLASS: MainThreadDispatcher(_BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `setup` | 异步 |  |
| `start_processing` | 异步 |  |
| `_process_pending_qt_tasks` | 同步 |  |
| `run_on_main_thread` | 同步 | 在主线程执行函数 - 从任何线程调用 |
| `run_async_on_main_thread` | 异步 | 在主线程执行异步函数 - 从 asyncio 线程调用 |
| `stop` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_main_thread_dispatcher` | 同步 |  |
| `__init__` | 同步 |  |
| `setup` | 异步 |  |
| `start_processing` | 异步 |  |
| `_process_pending_qt_tasks` | 同步 |  |
| `run_on_main_thread` | 同步 | 在主线程执行函数 - 从任何线程调用 |
| `run_async_on_main_thread` | 异步 | 在主线程执行异步函数 - 从 asyncio 线程调用 |
| `stop` | 同步 |  |
| `sync_wrapper` | 同步 |  |
| `sync_wrapper` | 同步 |  |

---

### 📄 modules\manager\pipeline.py

- **文件大小**: 7.0 KB
- **代码行数**: 186

#### 导入依赖

```python
from functools import wraps
from inspect import iscoroutinefunction
from typing import Dict
from typing import Optional
from typing import List
from typing import Any
from typing import Type
from typing import TypeVar
import asyncio
from runtime import RuntimePath
from utils.file import read_json
from base import _BaseManager
from events import types
from events import on_event_class
from logger import logger
from pipeline.enum import AdapterType
from manager.task.decorator import sync_task_scheduler
```

#### 类定义

##### CLASS: PipelineManager(_BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__get_adapter_manager` | 同步 |  |
| `start` | 同步 |  |
| `get_valid_providers` | 同步 |  |
| `validate_provider` | 同步 |  |
| `get_provider_names` | 同步 |  |
| `get_adapter_type_config` | 同步 |  |
| `get_pipeline_all_configs` | 同步 |  |
| `get_provider_config` | 同步 | 获取某个 provider 的完整配置 |
| `load_config` | 同步 |  |
| `stop` | 同步 |  |
| `switch_adapter` | 同步 |  |
| `register` | 同步 |  |
| `unregister` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `Pipeline` | 同步 |  |
| `__init__` | 同步 |  |
| `__get_adapter_manager` | 同步 |  |
| `start` | 同步 |  |
| `get_valid_providers` | 同步 |  |
| `validate_provider` | 同步 |  |
| `get_provider_names` | 同步 |  |
| `get_adapter_type_config` | 同步 |  |
| `get_pipeline_all_configs` | 同步 |  |
| `get_provider_config` | 同步 | 获取某个 provider 的完整配置 |
| `load_config` | 同步 |  |
| `stop` | 同步 |  |
| `switch_adapter` | 同步 |  |
| `register` | 同步 |  |
| `unregister` | 同步 |  |
| `decorator` | 同步 |  |
| `__init__` | 同步 |  |
| `new__del__` | 同步 |  |
| `__del__` | 同步 |  |
| `__del__` | 同步 |  |

---

### 📄 modules\manager\service\decorator.py

- **文件大小**: 1.7 KB
- **代码行数**: 45

#### 导入依赖

```python
from functools import wraps
from typing import Generic
from typing import Optional
from typing import Type
from manager import service_manager
from manager import T
```

#### 类定义

##### CLASS: ServiceDecorator(<ast.Subscript object at 0x0000024658430FA0>)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__call__` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `Service` | 同步 |  |
| `__init__` | 同步 |  |
| `__call__` | 同步 |  |
| `__init__` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `close` | 同步 |  |

---

### 📄 modules\manager\service\manager.py

- **文件大小**: 8.5 KB
- **代码行数**: 232

#### 导入依赖

```python
import asyncio
import threading
from typing import Any
from typing import Dict
from typing import Generic
from typing import Optional
from typing import TypeVar
from utils.file import write_yaml
from runtime import RuntimePath
from base import _BaseManager
from services.base import _BaseService
from services.base import ServiceState
from logger import logger
from utils import util
from events import types
from events import on_event_class
from services import ServiceId
from services import config
```

#### 类定义

##### CLASS: ServiceManager(<ast.Subscript object at 0x000002465845A3E0>, _BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__shutdown_event_loop` | 同步 |  |
| `__run_loop` | 同步 |  |
| `__is_main_thread_service` | 同步 |  |
| `register_service` | 同步 |  |
| `unregister` | 同步 |  |
| `is_registered` | 同步 |  |
| `start_service` | 同步 |  |
| `stop_service` | 同步 |  |
| `close_service` | 同步 |  |
| `get_service_names` | 同步 |  |
| `get_service_info` | 同步 |  |
| `get_all_service_infos` | 同步 |  |
| `get_service` | 同步 |  |
| `stop` | 同步 |  |
| `get_service_tool` | 同步 |  |
| `get_service_config` | 同步 |  |
| `update_service_config` | 同步 |  |
| `get_config` | 同步 |  |
| `get_service_state` | 同步 |  |
| `get_tools` | 同步 |  |
| `get_default_services_description` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__shutdown_event_loop` | 同步 |  |
| `__run_loop` | 同步 |  |
| `__is_main_thread_service` | 同步 |  |
| `register_service` | 同步 |  |
| `unregister` | 同步 |  |
| `is_registered` | 同步 |  |
| `start_service` | 同步 |  |
| `stop_service` | 同步 |  |
| `close_service` | 同步 |  |
| `get_service_names` | 同步 |  |
| `get_service_info` | 同步 |  |
| `get_all_service_infos` | 同步 |  |
| `get_service` | 同步 |  |
| `stop` | 同步 |  |
| `get_service_tool` | 同步 |  |
| `get_service_config` | 同步 |  |
| `update_service_config` | 同步 |  |
| `get_config` | 同步 |  |
| `get_service_state` | 同步 |  |
| `get_tools` | 同步 |  |
| `get_default_services_description` | 同步 |  |

---

### 📄 modules\manager\task\decorator.py

- **文件大小**: 3.5 KB
- **代码行数**: 110

#### 导入依赖

```python
from  import reference
from typing import AsyncGenerator
from typing import Awaitable
from typing import Callable
from typing import Optional
from typing import Union
from typing import overload
from functools import wraps
from types.common import P
from types.common import R
from schedular import schedular
from schedular import schedular
from schedular import schedular
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `sync_task_scheduler` | 同步 |  |
| `sync_task_scheduler` | 同步 |  |
| `sync_task_scheduler` | 同步 | 包装同步方法 |
| `async_task_scheduler` | 同步 |  |
| `async_task_scheduler` | 同步 |  |
| `async_task_scheduler` | 同步 | 包装异步方法 |
| `stream_task_scheduler` | 同步 |  |
| `stream_task_scheduler` | 同步 |  |
| `stream_task_scheduler` | 同步 |  |
| `decorator` | 同步 |  |
| `decorator` | 同步 |  |
| `decorator` | 同步 |  |
| `wrapper` | 同步 |  |
| `wrapper` | 同步 |  |
| `wrapper` | 异步 |  |

---

### 📄 modules\manager\task\reference.py

- **文件大小**: 9.8 KB
- **代码行数**: 285

#### 导入依赖

```python
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from dataclasses import field
import time
from typing import Any
from typing import AsyncGenerator
from typing import Callable
from typing import Generic
from typing import Literal
from typing import Optional
from typing import TypeVar
from typing import TypedDict
from utils import util
from inspect import iscoroutinefunction
```

#### 类定义

##### CLASS: TaskStreamingReference(<ast.Subscript object at 0x00000246584962C0>)

> 任务流式结果容器
- 支持异步迭代获取结果
- 支持超时

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `task_id` | 同步 |  |
| `streaming_status` | 同步 |  |
| `produce` | 异步 | 从异步生成器生产数据 |
| `data` | 异步 | 消费者获取生产者生产的所有数据 |
| `send_control` | 同步 | 发送控制信号 |
| `close` | 异步 | 关闭流 |
| `get_stats` | 同步 | 获取统计信息 |

##### CLASS: TaskReference(<ast.Subscript object at 0x0000024658445F30>)

> 任务引用
- 表示一个已提交但尚未完成的任务
- 提供多种方式获取结果

| 方法 | 类型 | 说明 |
|------|------|------|
| `id` | 同步 | 获取任务ID |
| `status` | 同步 | 获取任务状态 |
| `is_done` | 同步 | 检查任务是否完成 |
| `is_success` | 同步 |  |
| `wait_async` | 异步 |  |
| `wait_sync` | 异步 |  |
| `result` | 同步 |  |
| `then` | 同步 | 添加回调（当任务完成时调用） |
| `__repr__` | 同步 |  |

##### CLASS: StreamingTask

##### CLASS: StreamingTaskStatus(TypedDict)

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `task_id` | 同步 |  |
| `streaming_status` | 同步 |  |
| `produce` | 异步 | 从异步生成器生产数据 |
| `data` | 异步 | 消费者获取生产者生产的所有数据 |
| `send_control` | 同步 | 发送控制信号 |
| `close` | 异步 | 关闭流 |
| `get_stats` | 同步 | 获取统计信息 |
| `id` | 同步 | 获取任务ID |
| `status` | 同步 | 获取任务状态 |
| `is_done` | 同步 | 检查任务是否完成 |
| `is_success` | 同步 |  |
| `wait_async` | 异步 |  |
| `wait_sync` | 异步 |  |
| `result` | 同步 |  |
| `then` | 同步 | 添加回调（当任务完成时调用） |
| `__repr__` | 同步 |  |
| `__callback` | 异步 |  |

---

### 📄 modules\manager\task\schedular.py

- **文件大小**: 24.2 KB
- **代码行数**: 651

#### 导入依赖

```python
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import Future
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
import heapq
import time
from typing import Any
from typing import AsyncGenerator
from typing import Callable
from typing import Dict
from typing import Generic
from typing import Literal
from typing import Optional
from typing import TypeVar
from typing import TypedDict
from typing import Union
from threading import Lock
# ... 还有 10 个导入
```

#### 类定义

##### CLASS: TaskPriority

##### CLASS: TaskStatus

##### CLASS: Task(<ast.Subscript object at 0x00000246584830A0>)

##### CLASS: TaskSchedular(<ast.Subscript object at 0x0000024658481CF0>, _BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__init_async_loop` | 同步 | 初始化后台 asyncio 事件循环 |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `submit_stream` | 异步 |  |
| `submit` | 同步 | 提交任务 — 修复版 |
| `get_stats` | 同步 |  |
| `get_task_status` | 同步 |  |
| `wait_for_task_sync` | 异步 |  |
| `submit_and_wait_async` | 异步 |  |
| `get_task_result_async` | 异步 |  |
| `cancel_task` | 同步 |  |
| `__detect_task_type` | 同步 |  |
| `__run_sync_dispatcher` | 同步 |  |
| `__run_async_dispatcher` | 同步 |  |
| `__execute_sync_task` | 同步 | 执行同步任务 |
| `__wrap_sync_task` | 同步 |  |
| `__execute_async_task` | 异步 | 执行异步任务 |
| `__mark_task_failed` | 同步 |  |
| `__handle_sync_task_result` | 同步 |  |
| `__clear_completed_tasks` | 同步 |  |
| `set_older_than_hours` | 同步 |  |

##### CLASS: TaskSchedularInfo(TypedDict)

##### CLASS: TaskStatusInfo(TypedDict)

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__init_async_loop` | 同步 | 初始化后台 asyncio 事件循环 |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `submit_stream` | 异步 |  |
| `submit` | 同步 | 提交任务 — 修复版 |
| `get_stats` | 同步 |  |
| `get_task_status` | 同步 |  |
| `wait_for_task_sync` | 异步 |  |
| `submit_and_wait_async` | 异步 |  |
| `get_task_result_async` | 异步 |  |
| `cancel_task` | 同步 |  |
| `__detect_task_type` | 同步 |  |
| `__run_sync_dispatcher` | 同步 |  |
| `__run_async_dispatcher` | 同步 |  |
| `__execute_sync_task` | 同步 | 执行同步任务 |
| `__wrap_sync_task` | 同步 |  |
| `__execute_async_task` | 异步 | 执行异步任务 |
| `__mark_task_failed` | 同步 |  |
| `__handle_sync_task_result` | 同步 |  |
| `__clear_completed_tasks` | 同步 |  |
| `set_older_than_hours` | 同步 |  |
| `run_async_loop` | 同步 |  |
| `producer_task` | 异步 |  |
| `on_producer_done` | 同步 |  |

---

### 📄 modules\manager\websocket\manager.py

- **文件大小**: 6.4 KB
- **代码行数**: 176

#### 导入依赖

```python
import asyncio
from datetime import datetime
from typing import Any
from typing import Optional
from fastapi import WebSocket
from typing import Dict
from  import base
from events.types import WebSocketEventType
from logger import logger
from events import types
from events import on_event_class
from models import ConnectionInfo
from models import WebSocketResponse
from starlette.websockets import WebSocketState
from starlette.websockets import WebSocketState
```

#### 类定义

##### CLASS: WebSocketClinetManager(base._BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `start` | 同步 |  |
| `connect` | 异步 |  |
| `disconnect` | 同步 |  |
| `__safe_close` | 异步 |  |
| `send_json` | 异步 |  |
| `send_bytes` | 异步 |  |
| `broadcast` | 异步 |  |
| `update_heartbeat` | 同步 |  |
| `is_alive` | 同步 |  |
| `__cleanup_stale_connections` | 异步 |  |
| `stop` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_websocket_manager` | 同步 |  |
| `__init__` | 同步 |  |
| `start` | 同步 |  |
| `connect` | 异步 |  |
| `disconnect` | 同步 |  |
| `__safe_close` | 异步 |  |
| `send_json` | 异步 |  |
| `send_bytes` | 异步 |  |
| `broadcast` | 异步 |  |
| `update_heartbeat` | 同步 |  |
| `is_alive` | 同步 |  |
| `__cleanup_stale_connections` | 异步 |  |
| `stop` | 异步 |  |

---

### 📄 modules\manager\websocket\models.py

- **文件大小**: 0.8 KB
- **代码行数**: 29

#### 导入依赖

```python
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any
from typing import Optional
from pydantic import BaseModel
```

#### 类定义

##### CLASS: ConnectionInfo

| 方法 | 类型 | 说明 |
|------|------|------|
| `update_heartbeat` | 同步 |  |
| `is_alive` | 同步 |  |

##### CLASS: WebSocketResponse(BaseModel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `update_heartbeat` | 同步 |  |
| `is_alive` | 同步 |  |
| `to_dict` | 同步 |  |

---

### 📄 modules\memory\compression.py

- **文件大小**: 9.2 KB
- **代码行数**: 214

#### 导入依赖

```python
from __future__ import annotations
import asyncio
from datetime import datetime
import hashlib
from typing import List
from typing import Optional
from types.memory.context import CompressedContext
from types.memory.context import Message
from types.memory.context import TimeRange
from types.common import Role
from utils.file import read_markdown
from config.builder import prompt_builder
import json
```

#### 类定义

##### CLASS: ContextCompressor

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__generate_compressed_id` | 同步 | 生成压缩记录的唯一ID |
| `compress_context` | 异步 | 压缩对话上下文 |
| `format_messages` | 同步 | 格式化消息为文本 |
| `__compress_with_fallback` | 异步 | 带降级策略的压缩 |
| `__llm_compress` | 异步 |  |
| `__rule_based_compress` | 同步 | 基于规则的压缩（降级方案） |
| `__summarize_short_conversation` | 同步 | 短对话压缩 |
| `__summarize_long_conversation` | 同步 | 长对话压缩 |
| `__format_structured_result` | 同步 | 将结构化结果格式化为文本 |
| `_extract_summary` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__generate_compressed_id` | 同步 | 生成压缩记录的唯一ID |
| `compress_context` | 异步 | 压缩对话上下文 |
| `format_messages` | 同步 | 格式化消息为文本 |
| `__compress_with_fallback` | 异步 | 带降级策略的压缩 |
| `__llm_compress` | 异步 |  |
| `__rule_based_compress` | 同步 | 基于规则的压缩（降级方案） |
| `__summarize_short_conversation` | 同步 | 短对话压缩 |
| `__summarize_long_conversation` | 同步 | 长对话压缩 |
| `__format_structured_result` | 同步 | 将结构化结果格式化为文本 |
| `_extract_summary` | 同步 |  |

---

### 📄 modules\memory\emdedding\__init__.py

- **文件大小**: 0.9 KB
- **代码行数**: 32

#### 导入依赖

```python
from math import e
from typing import Literal
from typing import Optional
from typing import Union
from adapters import SentenceEmbeddingAdapter
from adapters import OpenAIEmbeddingAdapter
from adapters import OllamaEmbeddingAdapter
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `create_adapter` | 同步 |  |

---

### 📄 modules\memory\emdedding\adapters.py

- **文件大小**: 11.4 KB
- **代码行数**: 348

#### 导入依赖

```python
import asyncio
import os
from typing import Optional
from typing import Union
from typing import List
from numpy import array
from numpy import float32
from numpy import ndarray
from numpy import linalg
from src_py.modules.utils import decorators
from logger import logger
from base import _AsyncEmbeddingAdapter
import httpx
import httpx
from concurrent.futures import ThreadPoolExecutor
from sentence_transformers import SentenceTransformer
from openai import AsyncOpenAI
from utils import http
import torch
```

#### 类定义

##### CLASS: EmbeddingError(Exception)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |

##### CLASS: SentenceEmbeddingAdapter(_AsyncEmbeddingAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__get_executor` | 同步 | 获取或创建线程池 |
| `init_model` | 同步 |  |
| `embed` | 异步 | 异步嵌入文本（使用线程池） |
| `__embed` | 同步 | 对文本进行嵌入 |
| `close` | 异步 |  |
| `get_params` | 同步 |  |

##### CLASS: OpenAIEmbeddingAdapter(_AsyncEmbeddingAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_model` | 异步 | 初始化OpenAI客户端（异步） |
| `embed` | 异步 | 嵌入文本（OpenAI API，异步） |

##### CLASS: OllamaEmbeddingAdapter(_AsyncEmbeddingAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_model` | 异步 |  |
| `_check_model_available` | 异步 | 检查模型是否可用 |
| `embed` | 异步 | 嵌入文本（Ollama API，异步） |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__init__` | 同步 |  |
| `__get_executor` | 同步 | 获取或创建线程池 |
| `init_model` | 同步 |  |
| `embed` | 异步 | 异步嵌入文本（使用线程池） |
| `__embed` | 同步 | 对文本进行嵌入 |
| `close` | 异步 |  |
| `get_params` | 同步 |  |
| `__init__` | 同步 |  |
| `init_model` | 异步 | 初始化OpenAI客户端（异步） |
| `embed` | 异步 | 嵌入文本（OpenAI API，异步） |
| `__init__` | 同步 |  |
| `init_model` | 异步 |  |
| `_check_model_available` | 异步 | 检查模型是否可用 |
| `embed` | 异步 | 嵌入文本（Ollama API，异步） |

---

### 📄 modules\memory\emdedding\base.py

- **文件大小**: 4.5 KB
- **代码行数**: 139

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
import asyncio
from types import CoroutineType
from typing import Optional
from typing import Union
from numpy import ndarray
from abc import ABC
from abc import abstractmethod
import asyncio
from typing import Any
from typing import Dict
from typing import Optional
from typing import Union
from typing import List
from numpy import ndarray
from numpy import vstack
from numpy import vstack
from logger import logger
```

#### 类定义

##### CLASS: _BaseEmbeddingAdapter(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_model` | 同步 |  |
| `embed` | 同步 |  |
| `embed_batch` | 同步 | 批量嵌入文本（同步） |
| `get_params` | 同步 |  |
| `close` | 同步 |  |
| `__str__` | 同步 |  |

##### CLASS: _AsyncEmbeddingAdapter(_BaseEmbeddingAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `embed` | 同步 |  |
| `close` | 异步 |  |
| `embed_batch` | 异步 | 异步批量嵌入文本 |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_model` | 同步 |  |
| `embed` | 同步 |  |
| `embed_batch` | 同步 | 批量嵌入文本（同步） |
| `get_params` | 同步 |  |
| `close` | 同步 |  |
| `__str__` | 同步 |  |
| `__init__` | 同步 |  |
| `embed` | 同步 |  |
| `close` | 异步 |  |
| `embed_batch` | 异步 | 异步批量嵌入文本 |

---

### 📄 modules\memory\main.py

- **文件大小**: 12.2 KB
- **代码行数**: 295

#### 导入依赖

```python
from __future__ import annotations
import asyncio
from collections import deque
from datetime import datetime
from datetime import timedelta
from threading import Lock
from typing import Any
from typing import Callable
from typing import Optional
from typing import TypedDict
from typing import Union
from events import on_event_class
from events import types
from types.memory.context import MemoryContext
from types.memory.context import Message
from types.memory.database import CompressedMemory
from types.memory.database import Memory
from types.common import Role
from  import utils
from compression import ContextCompressor
# ... 还有 3 个导入
```

#### 类定义

##### CLASS: SystemInfo(TypedDict)

##### CLASS: HybridMemorySystem

| 方法 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 | HybridMemorySystem is a memory system that combines long-term memory storage with short-term memory storage. |
| `init_embedding_provider` | 同步 |  |
| `calculate_tokens` | 同步 |  |
| `__compress_context_and_update` | 异步 |  |
| `maybe_compress_context` | 异步 |  |
| `add_memories` | 异步 |  |
| `__list_session_memories` | 异步 |  |
| `__format_rows` | 同步 |  |
| `get_short_term_summary` | 异步 |  |
| `get_long_term_summary` | 异步 |  |
| `retrieve_memory` | 异步 |  |
| `get_memory_layers` | 异步 |  |
| `persist_context_detail` | 异步 |  |
| `close_with_context` | 异步 |  |
| `decay_now` | 异步 |  |
| `shutdown` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_instance` | 同步 |  |
| `__new__` | 同步 |  |
| `__init__` | 同步 | HybridMemorySystem is a memory system that combines long-term memory storage with short-term memory storage. |
| `init_embedding_provider` | 同步 |  |
| `calculate_tokens` | 同步 |  |
| `__compress_context_and_update` | 异步 |  |
| `maybe_compress_context` | 异步 |  |
| `add_memories` | 异步 |  |
| `__list_session_memories` | 异步 |  |
| `__format_rows` | 同步 |  |
| `get_short_term_summary` | 异步 |  |
| `get_long_term_summary` | 异步 |  |
| `retrieve_memory` | 异步 |  |
| `get_memory_layers` | 异步 |  |
| `persist_context_detail` | 异步 |  |
| `close_with_context` | 异步 |  |
| `decay_now` | 异步 |  |
| `shutdown` | 异步 |  |

---

### 📄 modules\memory\managers.py

- **文件大小**: 4.3 KB
- **代码行数**: 121

#### 导入依赖

```python
import asyncio
import hashlib
from types import CoroutineType
from typing import Generic
from typing import Literal
from typing import TypeVar
from typing import Union
import os
from numpy import float32
from numpy import ndarray
from numpy import zeros
from numpy import concatenate
from numpy import linalg
from typing import Optional
from typing import Callable
from utils import embed_text
from storage.markdown import MarkDownStorage
from storage.sqlite import SQLiteFAISSStorage
from emdedding import create_adapter
from storage.markdown import MarkDownStorage
```

#### 类定义

##### CLASS: EmbeddingManager

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_adapter` | 同步 |  |
| `embed` | 异步 |  |

##### CLASS: MemoryBackendManager

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `_embed_text` | 异步 |  |
| `__select_storage` | 同步 |  |
| `close` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `embed_text` | 异步 | Simple, deterministic hash embedding (fallback when no embedding model is configured). |
| `__init__` | 同步 |  |
| `init_adapter` | 同步 |  |
| `embed` | 异步 |  |
| `__init__` | 同步 |  |
| `_embed_text` | 异步 |  |
| `__select_storage` | 同步 |  |
| `close` | 异步 |  |

---

### 📄 modules\memory\models.py

- **文件大小**: 1.7 KB
- **代码行数**: 70

#### 导入依赖

```python
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from enum import Enum
from typing import Any
from typing import Optional
from typing import TypedDict
from pydantic import BaseModel
from numpy import ndarray
```

#### 类定义

##### CLASS: TimeRange(TypedDict)

##### CLASS: Role(str, Enum)

| 方法 | 类型 | 说明 |
|------|------|------|
| `get_zh_name` | 同步 |  |

##### CLASS: Message(BaseModel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

##### CLASS: Memory(BaseModel)

##### CLASS: CompressedMemory(BaseModel)

##### CLASS: MemoryStorgeData(Memory)

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_zh_name` | 同步 |  |
| `to_dict` | 同步 |  |

---

### 📄 modules\memory\storage\base.py

- **文件大小**: 1.6 KB
- **代码行数**: 46

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
from types import CoroutineType
from typing import Any
import numpy as np
from types.memory.database import CompressedMemory
from types.memory.database import Memory
```

#### 类定义

##### CLASS: _MemoryStorageBase(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `add_memory` | 同步 |  |
| `retrieve_memory` | 同步 |  |
| `delete_memory` | 同步 |  |
| `get_short_term` | 同步 |  |
| `get_long_term` | 同步 |  |
| `get_detailed` | 同步 |  |
| `close` | 同步 |  |
| `get_compressed` | 同步 |  |
| `add_memories` | 同步 |  |
| `start` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `add_memory` | 同步 |  |
| `retrieve_memory` | 同步 |  |
| `delete_memory` | 同步 |  |
| `get_short_term` | 同步 |  |
| `get_long_term` | 同步 |  |
| `get_detailed` | 同步 |  |
| `close` | 同步 |  |
| `get_compressed` | 同步 |  |
| `add_memories` | 同步 |  |
| `start` | 同步 |  |

---

### 📄 modules\memory\storage\database.py

- **文件大小**: 11.4 KB
- **代码行数**: 312

#### 导入依赖

```python
from __future__ import annotations
from datetime import datetime
import json
import os
import pickle
from typing import Any
from typing import Iterable
from typing import Sequence
import faiss
from numpy import ndarray
from numpy import float32
from numpy import array
from numpy import int64
from numpy import arange
from numpy import empty
import orjson
from database.sqlite import AsyncSqlite
from types.memory.database import CompressedMemory
from types.memory.database import Memory
from types.memory.database import TimeRange
# ... 还有 1 个导入
```

#### 类定义

##### CLASS: SQLiteMemory(AsyncSqlite)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `_init_db` | 异步 |  |
| `add_memories` | 异步 |  |
| `add_compressed_memory` | 异步 |  |
| `get_compressed` | 异步 |  |
| `map_faiss_ids` | 异步 |  |
| `get_memory_ids_by_faiss` | 异步 |  |
| `get_records` | 异步 |  |
| `get_recent` | 异步 |  |
| `reinforce` | 异步 |  |
| `decay_importance` | 异步 |  |
| `count_rows` | 异步 |  |
| `lowest_ranked` | 异步 |  |
| `delete_memories` | 异步 |  |
| `max_faiss_id` | 异步 |  |
| `get_faiss_ids_by_memory` | 异步 |  |

##### CLASS: FAISSMemory

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `next_faiss_id` | 同步 |  |
| `set_next_faiss_id` | 同步 |  |
| `add_vectors` | 同步 |  |
| `search` | 同步 |  |
| `remove_ids` | 同步 |  |
| `save` | 同步 |  |
| `load_meta` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `_init_db` | 异步 |  |
| `add_memories` | 异步 |  |
| `add_compressed_memory` | 异步 |  |
| `get_compressed` | 异步 |  |
| `map_faiss_ids` | 异步 |  |
| `get_memory_ids_by_faiss` | 异步 |  |
| `get_records` | 异步 |  |
| `get_recent` | 异步 |  |
| `reinforce` | 异步 |  |
| `decay_importance` | 异步 |  |
| `count_rows` | 异步 |  |
| `lowest_ranked` | 异步 |  |
| `delete_memories` | 异步 |  |
| `max_faiss_id` | 异步 |  |
| `get_faiss_ids_by_memory` | 异步 |  |
| `__init__` | 同步 |  |
| `next_faiss_id` | 同步 |  |
| `set_next_faiss_id` | 同步 |  |
| `add_vectors` | 同步 |  |
| `search` | 同步 |  |
| `remove_ids` | 同步 |  |
| `save` | 同步 |  |
| `load_meta` | 同步 |  |

---

### 📄 modules\memory\storage\markdown.py

- **文件大小**: 18.2 KB
- **代码行数**: 410

#### 导入依赖

```python
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from datetime import timedelta
from pathlib import Path
import asyncio
from typing import Any
from typing import Callable
from numpy import ndarray
from numpy import ndarray
from numpy import float32
from numpy import allclose
from numpy import linalg
from numpy import array
from base import _MemoryStorageBase
from types.memory.database import CompressedMemory
from types.memory.database import Memory
from types.memory.database import MemoryStorgeData
# ... 还有 2 个导入
```

#### 类定义

##### CLASS: MarkDownStorage(_MemoryStorageBase)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__session_file` | 同步 |  |
| `_detail_file` | 同步 |  |
| `_compressed_file` | 同步 |  |
| `_short_file` | 同步 |  |
| `_long_file` | 同步 |  |
| `_embed_text` | 同步 |  |
| `start` | 异步 |  |
| `__load_from_markdown` | 异步 |  |
| `__append_to_markdown` | 异步 | 追加新行到 markdown 文件末尾 |
| `__persist_session_files` | 异步 |  |
| `__rewrite_summary_files` | 异步 | 重写压缩记忆摘要文件 |
| `add_memory` | 异步 |  |
| `add_memories` | 异步 |  |
| `add_compressed_memory` | 异步 |  |
| `retrieve_memory` | 异步 |  |
| `get_short_term` | 异步 |  |
| `get_long_term` | 异步 |  |
| `get_detailed` | 异步 |  |
| `get_compressed` | 异步 |  |
| `decay_now` | 异步 |  |
| `delete_memory` | 异步 |  |
| `close` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__session_file` | 同步 |  |
| `_detail_file` | 同步 |  |
| `_compressed_file` | 同步 |  |
| `_short_file` | 同步 |  |
| `_long_file` | 同步 |  |
| `_embed_text` | 同步 |  |
| `start` | 异步 |  |
| `__load_from_markdown` | 异步 |  |
| `__append_to_markdown` | 异步 | 追加新行到 markdown 文件末尾 |
| `__persist_session_files` | 异步 |  |
| `__rewrite_summary_files` | 异步 | 重写压缩记忆摘要文件 |
| `add_memory` | 异步 |  |
| `add_memories` | 异步 |  |
| `add_compressed_memory` | 异步 |  |
| `retrieve_memory` | 异步 |  |
| `get_short_term` | 异步 |  |
| `get_long_term` | 异步 |  |
| `get_detailed` | 异步 |  |
| `get_compressed` | 异步 |  |
| `decay_now` | 异步 |  |
| `delete_memory` | 异步 |  |
| `close` | 异步 |  |
| `read_file` | 异步 | 读取单个文件 |
| `_write` | 同步 |  |
| `_write_summary` | 异步 |  |
| `_compute_similarity` | 同步 |  |
| `decay` | 异步 |  |

---

### 📄 modules\memory\storage\sqlite.py

- **文件大小**: 12.1 KB
- **代码行数**: 287

#### 导入依赖

```python
from __future__ import annotations
import asyncio
from datetime import datetime
from datetime import timedelta
from types import CoroutineType
from typing import Any
from typing import Callable
from typing import Optional
import numpy as np
from base import _MemoryStorageBase
from types.memory.database import CompressedMemory
from types.memory.database import Memory
from  import utils
from database import FAISSMemory
from database import SQLiteMemory
import logging
```

#### 类定义

##### CLASS: _MemoryTask

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |

##### CLASS: SQLiteFAISSStorage(_MemoryStorageBase)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `_embed_text` | 异步 |  |
| `__initialize` | 异步 |  |
| `__worker_loop` | 异步 |  |
| `_run_on_worker` | 异步 |  |
| `start` | 异步 |  |
| `close` | 异步 |  |
| `__prune_if_needed` | 异步 | 如果需要，删除最低排名的记录 |
| `add_memory` | 异步 |  |
| `__add_memories_write` | 异步 |  |
| `add_memories` | 异步 |  |
| `add_compressed_memory` | 异步 |  |
| `get_compressed` | 异步 |  |
| `get_detailed` | 异步 |  |
| `retrieve_memory` | 异步 |  |
| `get_short_term` | 异步 |  |
| `get_long_term` | 异步 |  |
| `decay_now` | 异步 |  |
| `__delete_memory` | 异步 |  |
| `delete_memory` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__init__` | 同步 |  |
| `_embed_text` | 异步 |  |
| `__initialize` | 异步 |  |
| `__worker_loop` | 异步 |  |
| `_run_on_worker` | 异步 |  |
| `start` | 异步 |  |
| `close` | 异步 |  |
| `__prune_if_needed` | 异步 | 如果需要，删除最低排名的记录 |
| `add_memory` | 异步 |  |
| `__add_memories_write` | 异步 |  |
| `add_memories` | 异步 |  |
| `add_compressed_memory` | 异步 |  |
| `get_compressed` | 异步 |  |
| `get_detailed` | 异步 |  |
| `retrieve_memory` | 异步 |  |
| `get_short_term` | 异步 |  |
| `get_long_term` | 异步 |  |
| `decay_now` | 异步 |  |
| `__delete_memory` | 异步 |  |
| `delete_memory` | 异步 |  |
| `_write` | 异步 |  |
| `_query` | 异步 |  |
| `_query` | 异步 |  |
| `_search` | 异步 |  |
| `_query` | 异步 |  |
| `_decay` | 异步 |  |

---

### 📄 modules\memory\token.py

- **文件大小**: 0.4 KB
- **代码行数**: 12

#### 类定义

##### CLASS: TokenCalculator

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `extract_tokens` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `extract_tokens` | 同步 |  |

---

### 📄 modules\memory\utils.py

- **文件大小**: 2.3 KB
- **代码行数**: 78

#### 导入依赖

```python
import math
from datetime import datetime
from typing import List
from typing import Union
from numpy import float32
from numpy import ndarray
from numpy import zeros
from numpy import dot
from numpy.linalg import norm
import hashlib
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `now_str` | 同步 |  |
| `now` | 同步 |  |
| `parse_time` | 同步 |  |
| `time_since` | 同步 |  |
| `cosine_similarity` | 同步 |  |
| `embed_text` | 异步 | Simple, deterministic hash embedding (fallback when no embedding model is configured). |
| `compute_memory_score` | 同步 | 计算记忆的分数 |
| `text_to_list` | 同步 |  |

---

### 📄 modules\pipeline\adapters\asr\adapter.py

- **文件大小**: 17.5 KB
- **代码行数**: 492

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
import asyncio
import base64
from dataclasses import dataclass
from enum import Enum
import json
from types import CoroutineType
from typing import Any
from typing import AsyncGenerator
from typing import Optional
import uuid
import httpx
import numpy as np
from modules.utils.util import get_device
from numpy import frombuffer
from numpy import float32
from numpy import int16
from faster_whisper import WhisperModel
```

#### 类定义

##### CLASS: ASRConfig

> ASR 配置

##### CLASS: _ASRBaseAdapter(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize` | 同步 |  |
| `transcribe` | 同步 |  |
| `transcribe_stream` | 同步 |  |
| `close` | 同步 |  |

##### CLASS: WhisperASRAdapter(_ASRBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__transcribe_whisper` | 异步 |  |
| `initialize` | 异步 |  |
| `transcribe` | 异步 |  |
| `transcribe_stream` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize` | 同步 |  |
| `transcribe` | 同步 |  |
| `transcribe_stream` | 同步 |  |
| `close` | 同步 |  |
| `__init__` | 同步 |  |
| `__transcribe_whisper` | 异步 |  |
| `initialize` | 异步 |  |
| `transcribe` | 异步 |  |
| `transcribe_stream` | 异步 |  |

---

### 📄 modules\pipeline\adapters\landmarker\face.py

- **文件大小**: 6.5 KB
- **代码行数**: 207

#### 导入依赖

```python
import os
from pathlib import Path
import time
from threading import Lock
from typing import Optional
from typing import Union
from models import ResultFaceData
import cv2
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision.core.image import Image
from mediapipe.tasks.python.vision.core.image import ImageFormat
from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode
from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarker
from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarkerOptions
from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarkerResult
from numpy import array
from numpy import degrees
from numpy import atan2
from numpy import asin
```

#### 类定义

##### CLASS: FaceTracker

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `check_model` | 同步 |  |
| `__del__` | 同步 |  |
| `__on_result` | 同步 |  |
| `init` | 同步 |  |
| `__submit_frame` | 同步 |  |
| `poll_result` | 同步 |  |
| `close` | 同步 |  |
| `stop` | 同步 |  |
| `start` | 同步 |  |
| `set_source` | 同步 |  |
| `set_fps` | 同步 |  |
| `set_mirror` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `calculate_euler_angles` | 同步 |  |
| `build_face_data` | 同步 |  |
| `create_options` | 同步 |  |
| `__init__` | 同步 |  |
| `check_model` | 同步 |  |
| `__del__` | 同步 |  |
| `__on_result` | 同步 |  |
| `init` | 同步 |  |
| `__submit_frame` | 同步 |  |
| `poll_result` | 同步 |  |
| `close` | 同步 |  |
| `stop` | 同步 |  |
| `start` | 同步 |  |
| `set_source` | 同步 |  |
| `set_fps` | 同步 |  |
| `set_mirror` | 同步 |  |

---

### 📄 modules\pipeline\adapters\landmarker\models.py

- **文件大小**: 0.3 KB
- **代码行数**: 10

#### 导入依赖

```python
from dataclasses import dataclass
```

#### 类定义

##### CLASS: ResultFaceData

---

### 📄 modules\pipeline\adapters\llm\adapter.py

- **文件大小**: 9.6 KB
- **代码行数**: 325

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
from enum import Enum
from types import CoroutineType
from typing import Optional
from typing import List
from typing import Dict
from typing import Any
from typing import AsyncGenerator
from regex import T
from  import client
from  import types
from tools.models import AITool
import asyncio
```

#### 类定义

##### CLASS: _LLMBaseAdapter(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize_client` | 同步 |  |
| `generate_text_stream` | 同步 |  |
| `generate_text` | 同步 |  |
| `_build_request_data` | 同步 | 构建请求数据 |
| `get_params` | 同步 |  |
| `close` | 同步 |  |

##### CLASS: ChatGPTLLMAdapter(_LLMBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize_client` | 异步 |  |
| `generate_text_stream` | 异步 | 生成流式文本 |
| `generate_text` | 异步 |  |

##### CLASS: OllamaLLMAdapter(_LLMBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize_client` | 异步 |  |
| `generate_text_stream` | 异步 | 生成流式文本 |
| `generate_text` | 异步 |  |

##### CLASS: DeepseekLLMAdapter(_LLMBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize_client` | 异步 |  |
| `generate_text_stream` | 异步 |  |
| `generate_text` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize_client` | 同步 |  |
| `generate_text_stream` | 同步 |  |
| `generate_text` | 同步 |  |
| `_build_request_data` | 同步 | 构建请求数据 |
| `get_params` | 同步 |  |
| `close` | 同步 |  |
| `__init__` | 同步 |  |
| `initialize_client` | 异步 |  |
| `generate_text_stream` | 异步 | 生成流式文本 |
| `generate_text` | 异步 |  |
| `__init__` | 同步 |  |
| `initialize_client` | 异步 |  |
| `generate_text_stream` | 异步 | 生成流式文本 |
| `generate_text` | 异步 |  |
| `__init__` | 同步 |  |
| `initialize_client` | 异步 |  |
| `generate_text_stream` | 异步 |  |
| `generate_text` | 异步 |  |

---

### 📄 modules\pipeline\adapters\llm\client.py

- **文件大小**: 9.6 KB
- **代码行数**: 277

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
import json
from typing import AsyncGenerator
from typing import Dict
from typing import Generic
from typing import Literal
from typing import Optional
from typing import TypeVar
from typing import Union
import httpx
from openai import AsyncOpenAI
```

#### 类定义

##### CLASS: _BaseLLMClient(ABC)

> LLM客户端基类

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__aenter__` | 异步 |  |
| `__aexit__` | 异步 |  |
| `__ensure_client` | 异步 | 确保HTTP客户端已初始化 |
| `stream_request` | 异步 | 流式请求 |
| `request` | 异步 | 普通请求 |
| `close` | 异步 | 关闭客户端连接 |

##### CLASS: OpenAIClient(_BaseLLMClient)

> OpenAI兼容客户端（使用httpx）

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `stream_request` | 异步 | OpenAI流式请求 |
| `request` | 异步 |  |
| `__ensure_client` | 异步 |  |
| `close` | 异步 |  |

##### CLASS: AsyncGenerateLLMClient(_BaseLLMClient, <ast.Subscript object at 0x00000246583E6620>)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__get_chunk_parser` | 同步 | 获取流式响应解析器 |
| `__parse_openai_chunk` | 同步 | 解析OpenAI格式的流式响应 |
| `__parse_ollama_chunk` | 同步 | 解析Ollama格式的流式响应 |
| `__parse_generic_chunk` | 同步 | 解析通用格式的流式响应 |
| `__get_default_api_url` | 同步 |  |
| `stream_request` | 异步 |  |
| `request` | 异步 | HTTP普通请求 |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__aenter__` | 异步 |  |
| `__aexit__` | 异步 |  |
| `__ensure_client` | 异步 | 确保HTTP客户端已初始化 |
| `stream_request` | 异步 | 流式请求 |
| `request` | 异步 | 普通请求 |
| `close` | 异步 | 关闭客户端连接 |
| `__init__` | 同步 |  |
| `stream_request` | 异步 | OpenAI流式请求 |
| `request` | 异步 |  |
| `__ensure_client` | 异步 |  |
| `close` | 异步 |  |
| `__init__` | 同步 |  |
| `__get_chunk_parser` | 同步 | 获取流式响应解析器 |
| `__parse_openai_chunk` | 同步 | 解析OpenAI格式的流式响应 |
| `__parse_ollama_chunk` | 同步 | 解析Ollama格式的流式响应 |
| `__parse_generic_chunk` | 同步 | 解析通用格式的流式响应 |
| `__get_default_api_url` | 同步 |  |
| `stream_request` | 异步 |  |
| `request` | 异步 | HTTP普通请求 |

---

### 📄 modules\pipeline\adapters\llm\types.py

- **文件大小**: 0.5 KB
- **代码行数**: 26

#### 导入依赖

```python
from typing import Dict
from typing import Optional
from typing import TypedDict
from pydantic import BaseModel
```

#### 类定义

##### CLASS: OllamaParams(TypedDict)

##### CLASS: _OpenAIBaseParams(OllamaParams, TypedDict)

##### CLASS: ChatGPTParams(_OpenAIBaseParams, TypedDict)

##### CLASS: DeepSeekParams(_OpenAIBaseParams, TypedDict)

##### CLASS: LLMResponse(BaseModel)

---

### 📄 modules\pipeline\adapters\ocr\adapter.py

- **文件大小**: 5.5 KB
- **代码行数**: 177

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
import asyncio
from dataclasses import dataclass
import os
from types import CoroutineType
from typing import Any
from inspect import iscoroutinefunction
from utils.util import get_device
from paddleocr import PaddleOCR
from pytesseract import image_to_string
from umiocr import UmiOCR
from easyocr import Reader
```

#### 类定义

##### CLASS: _OCRBaseAdapter(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_ocr` | 同步 |  |
| `recognize` | 同步 | 识别图片中的文本 |
| `ensure_initialized` | 异步 |  |
| `get_params` | 同步 |  |
| `close` | 同步 |  |

##### CLASS: OCRResult

##### CLASS: PaddleOCRAdapter(_OCRBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_ocr` | 异步 |  |
| `recognize` | 异步 |  |
| `close` | 同步 |  |

##### CLASS: TesseractOCRAdapter(_OCRBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_ocr` | 同步 |  |
| `recognize` | 异步 | 异步执行Tesseract OCR识别 |
| `close` | 同步 |  |

##### CLASS: UmiOCRAdapter(_OCRBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_ocr` | 异步 |  |
| `recognize` | 异步 |  |
| `close` | 同步 |  |

##### CLASS: EasyOCRAdapter(_OCRBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_ocr` | 异步 |  |
| `recognize` | 异步 | 异步执行EasyOCR识别 |
| `close` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init_ocr` | 同步 |  |
| `recognize` | 同步 | 识别图片中的文本 |
| `ensure_initialized` | 异步 |  |
| `get_params` | 同步 |  |
| `close` | 同步 |  |
| `__init__` | 同步 |  |
| `init_ocr` | 异步 |  |
| `recognize` | 异步 |  |
| `close` | 同步 |  |
| `__init__` | 同步 |  |
| `init_ocr` | 同步 |  |
| `recognize` | 异步 | 异步执行Tesseract OCR识别 |
| `close` | 同步 |  |
| `__init__` | 同步 |  |
| `init_ocr` | 异步 |  |
| `recognize` | 异步 |  |
| `close` | 同步 |  |
| `__init__` | 同步 |  |
| `init_ocr` | 异步 |  |
| `recognize` | 异步 | 异步执行EasyOCR识别 |
| `close` | 同步 |  |

---

### 📄 modules\pipeline\adapters\tts\adapter.py

- **文件大小**: 13.4 KB
- **代码行数**: 368

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
import asyncio
import os
from types import CoroutineType
from typing import Any
from typing import AsyncGenerator
from typing import List
from typing import Optional
from typing import Union
from client import AsyncGenerateTTSClient
from  import models
```

#### 类定义

##### CLASS: _TTSBaseAdapter(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize_client` | 同步 |  |
| `generate_voice_stream` | 同步 |  |
| `generate_voice` | 同步 | 生成语音 |
| `get_audio_format` | 同步 |  |
| `get_audio_sample_rate` | 同步 |  |
| `get_audio_channels` | 同步 |  |
| `get_audio_sample_width` | 同步 |  |
| `get_params` | 同步 |  |
| `close` | 异步 |  |

##### CLASS: AIVISAdapter(_TTSBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 | 初始化AIVIS适配器 |
| `__generate_headers` | 同步 | 生成前调用函数，设置text参数 |
| `generate_voice_stream` | 异步 |  |
| `generate_voice` | 异步 |  |
| `close` | 异步 |  |
| `get_params` | 同步 | 获取当前适配器的参数 |

##### CLASS: BV2Adapter(_TTSBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `generate_voice_stream` | 异步 |  |
| `generate_voice` | 异步 |  |

##### CLASS: GPTSoVITSAdapter(_TTSBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize_client` | 同步 |  |
| `generate_voice_stream` | 异步 |  |
| `generate_voice` | 异步 |  |

##### CLASS: VitsAdapter(_TTSBaseAdapter)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `generate_voice_stream` | 异步 |  |
| `generate_voice` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize_client` | 同步 |  |
| `generate_voice_stream` | 同步 |  |
| `generate_voice` | 同步 | 生成语音 |
| `get_audio_format` | 同步 |  |
| `get_audio_sample_rate` | 同步 |  |
| `get_audio_channels` | 同步 |  |
| `get_audio_sample_width` | 同步 |  |
| `get_params` | 同步 |  |
| `close` | 异步 |  |
| `__init__` | 同步 | 初始化AIVIS适配器 |
| `__generate_headers` | 同步 | 生成前调用函数，设置text参数 |
| `generate_voice_stream` | 异步 |  |
| `generate_voice` | 异步 |  |
| `close` | 异步 |  |
| `get_params` | 同步 | 获取当前适配器的参数 |
| `__init__` | 同步 |  |
| `generate_voice_stream` | 异步 |  |
| `generate_voice` | 异步 |  |
| `__init__` | 同步 |  |
| `initialize_client` | 同步 |  |
| `generate_voice_stream` | 异步 |  |
| `generate_voice` | 异步 |  |
| `__init__` | 同步 |  |
| `generate_voice_stream` | 异步 |  |
| `generate_voice` | 异步 |  |

---

### 📄 modules\pipeline\adapters\tts\client.py

- **文件大小**: 2.8 KB
- **代码行数**: 86

#### 导入依赖

```python
import asyncio
from typing import AsyncGenerator
from typing import List
import httpx
```

#### 类定义

##### CLASS: TextSplitter

> 智能文本分割器，用于流式TTS

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `feed` | 同步 | 输入文本，返回可发送的句子列表 |
| `flush` | 同步 |  |

##### CLASS: AsyncGenerateTTSClient

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 | 初始化TTS客户端 |
| `close` | 异步 |  |
| `__aenter__` | 异步 |  |
| `__aexit__` | 异步 |  |
| `stream` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `feed` | 同步 | 输入文本，返回可发送的句子列表 |
| `flush` | 同步 |  |
| `__init__` | 同步 | 初始化TTS客户端 |
| `close` | 异步 |  |
| `__aenter__` | 异步 |  |
| `__aexit__` | 异步 |  |
| `stream` | 异步 |  |

---

### 📄 modules\pipeline\adapters\tts\models.py

- **文件大小**: 1.4 KB
- **代码行数**: 60

#### 导入依赖

```python
from dataclasses import dataclass
from typing import Optional
from typing import TypedDict
```

#### 类定义

##### CLASS: _TTSParamsBase(TypedDict)

##### CLASS: AIVISParams(_TTSParamsBase, TypedDict)

##### CLASS: BV2Params(_TTSParamsBase, TypedDict)

##### CLASS: VitsParams(_TTSParamsBase, TypedDict)

##### CLASS: GPTSoVITSParams(_TTSParamsBase, TypedDict)

##### CLASS: TTSResult

---

### 📄 modules\pipeline\balance.py

- **文件大小**: 0.4 KB
- **代码行数**: 16

#### 导入依赖

```python
from utils import http
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_deepseek_balance` | 异步 |  |

---

### 📄 modules\pipeline\chat.py

- **文件大小**: 6.4 KB
- **代码行数**: 200

#### 导入依赖

```python
from __future__ import annotations
import asyncio
from typing import AsyncGenerator
from typing import Literal
from typing import Optional
from src_py.modules.manager.task.decorator import async_task_scheduler
from src_py.modules.routes.models import RouteType
from  import events
from characters.orchestrator import CharacterOrchestrator
from config import get_config
from logger import logger
from memory.main import HybridMemorySystem
from  import enum
from  import manager
```

#### 类定义

##### CLASS: CharacterChatRouter

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `route` | 异步 |  |
| `route_stream` | 异步 |  |
| `_emit_events` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `_provider_kwargs` | 同步 |  |
| `ensure_initialized` | 异步 |  |
| `router` | 异步 |  |
| `router_stream` | 异步 |  |
| `text_to_speech` | 异步 |  |
| `text_to_speech_stream` | 异步 |  |
| `speech_to_text` | 异步 |  |
| `speech_to_text_stream` | 异步 |  |
| `__init__` | 同步 |  |
| `route` | 异步 |  |
| `route_stream` | 异步 |  |
| `_emit_events` | 同步 |  |

---

### 📄 modules\pipeline\downloads\asr.py

- **文件大小**: 0.0 KB
- **代码行数**: 0

---

### 📄 modules\pipeline\downloads\landmarker.py

- **文件大小**: 0.7 KB
- **代码行数**: 17

#### 导入依赖

```python
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional
from utils.http import download_file
from logger import logger
from manager.task.decorator import async_task_scheduler
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `download_google_facelandmarker` | 异步 |  |

---

### 📄 modules\pipeline\downloads\ocr.py

- **文件大小**: 2.1 KB
- **代码行数**: 52

#### 导入依赖

```python
import asyncio
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional
from utils.http import create_httpx_async_client
from utils.http import download_file
from logger import logger
from manager.task.decorator import async_task_scheduler
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `download_paddle_ocr` | 异步 |  |
| `download_umi_ocr` | 异步 |  |
| `update_progress` | 异步 |  |

---

### 📄 modules\pipeline\emotion\predictor.py

- **文件大小**: 0.5 KB
- **代码行数**: 15

#### 导入依赖

```python
from runtime import RuntimePath
from emotion_classifier import EmotionClassifier
```

#### 类定义

##### CLASS: LLMEmotionClassifier

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize` | 同步 |  |
| `classify` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize` | 同步 |  |
| `classify` | 同步 |  |

---

### 📄 modules\pipeline\enum.py

- **文件大小**: 0.5 KB
- **代码行数**: 26

#### 导入依赖

```python
from enum import Enum
```

#### 类定义

##### CLASS: AdapterType(str, Enum)

##### CLASS: TTSProviderType(str, Enum)

##### CLASS: LLMProviderType(str, Enum)

##### CLASS: ASRProviderType(str, Enum)

##### CLASS: OCRProviderType(str, Enum)

---

### 📄 modules\pipeline\manager.py

- **文件大小**: 13.3 KB
- **代码行数**: 400

#### 导入依赖

```python
from __future__ import annotations
from abc import ABC
from abc import abstractmethod
import asyncio
import json
import threading
from typing import Any
from typing import AsyncGenerator
from typing import Optional
from inspect import iscoroutinefunction
from logger import logger
from manager.task import decorator
from manager.pipeline import Pipeline
from types import common
from tools.models import AITool
from  import enum
from adapters.tts.adapter import _TTSBaseAdapter
from adapters.llm.adapter import _LLMBaseAdapter
from adapters.asr.adapter import _ASRBaseAdapter
from adapters.ocr.adapter import _OCRBaseAdapter
# ... 还有 11 个导入
```

#### 类定义

##### CLASS: _BaseManager(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__new__` | 同步 |  |
| `is_initialized` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `intialize_provider` | 同步 |  |
| `init_provider_client` | 同步 |  |
| `stop` | 同步 |  |

##### CLASS: TTS(_BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `is_initialized` | 同步 |  |
| `get_params` | 同步 |  |
| `stop` | 异步 |  |
| `process_text` | 异步 |  |
| `process_text_stream` | 异步 |  |
| `intialize_provider` | 同步 |  |
| `init_provider_client` | 同步 |  |
| `close` | 异步 |  |

##### CLASS: LLM(_BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `init_provider_client` | 同步 |  |
| `is_initialized` | 同步 |  |
| `get_params` | 同步 |  |
| `stop` | 同步 |  |
| `intialize_provider` | 同步 |  |
| `prompt_message` | 异步 |  |
| `process_message` | 异步 |  |
| `process_message_stream` | 异步 |  |
| `compress` | 异步 |  |
| `close` | 同步 |  |

##### CLASS: ASR(_BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `stop` | 同步 |  |
| `is_initialized` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `intialize_provider` | 同步 |  |
| `init_asr` | 异步 |  |
| `process_audio` | 异步 |  |
| `process_audio_stream` | 异步 |  |
| `close` | 异步 |  |
| `init_provider_client` | 异步 |  |

##### CLASS: OCR(_BaseManager)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `is_initialized` | 同步 |  |
| `intialize_provider` | 同步 |  |
| `init_provider_client` | 异步 |  |
| `stop` | 同步 |  |
| `recognize` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `_message_to_dict` | 同步 |  |
| `__init__` | 同步 |  |
| `__new__` | 同步 |  |
| `is_initialized` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `intialize_provider` | 同步 |  |
| `init_provider_client` | 同步 |  |
| `stop` | 同步 |  |
| `__init__` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `is_initialized` | 同步 |  |
| `get_params` | 同步 |  |
| `stop` | 异步 |  |
| `process_text` | 异步 |  |
| `process_text_stream` | 异步 |  |
| `intialize_provider` | 同步 |  |
| `init_provider_client` | 同步 |  |
| `close` | 异步 |  |
| `__init__` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `init_provider_client` | 同步 |  |
| `is_initialized` | 同步 |  |
| `get_params` | 同步 |  |
| `stop` | 同步 |  |
| `intialize_provider` | 同步 |  |
| `prompt_message` | 异步 |  |
| `process_message` | 异步 |  |
| `process_message_stream` | 异步 |  |
| `compress` | 异步 |  |
| `close` | 同步 |  |
| `__init__` | 同步 |  |
| `stop` | 同步 |  |
| `is_initialized` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `intialize_provider` | 同步 |  |
| `init_asr` | 异步 |  |
| `process_audio` | 异步 |  |
| `process_audio_stream` | 异步 |  |
| `close` | 异步 |  |
| `init_provider_client` | 异步 |  |
| `__init__` | 同步 |  |
| `get_available_providers` | 同步 |  |
| `is_initialized` | 同步 |  |
| `intialize_provider` | 同步 |  |
| `init_provider_client` | 异步 |  |
| `stop` | 同步 |  |
| `recognize` | 异步 |  |

---

### 📄 modules\routes\intent.py

- **文件大小**: 10.4 KB
- **代码行数**: 265

#### 导入依赖

```python
from __future__ import annotations
import asyncio
import hashlib
import json
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Awaitable
from typing import Callable
from typing import Dict
from typing import Generic
from typing import Optional
from typing import TypeVar
from utils.file import read_json
from logger import logger
from models import KeyWords
from models import RouteDecision
from models import RouteDecisionCache
# ... 还有 2 个导入
```

#### 类定义

##### CLASS: LRUCache(<ast.Subscript object at 0x000002465850CD90>)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get` | 同步 |  |
| `put` | 同步 |  |
| `_periodic_cleanup` | 同步 |  |
| `get_stats` | 同步 |  |

##### CLASS: IntentRouter

> Fast rule router; ambiguous requests can be judged by a lightweight LLM call.

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `_default_config` | 同步 |  |
| `read_keywords` | 同步 |  |
| `_init_matchers` | 同步 |  |
| `route` | 异步 |  |
| `_merge_results` | 同步 |  |
| `_quick_rule_match` | 同步 |  |
| `_check_special_patterns` | 同步 |  |
| `_llm_predict` | 异步 |  |
| `_get_cache_key` | 同步 |  |
| `_update_response_time` | 同步 |  |
| `get_stats` | 同步 |  |
| `clear_cache` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get` | 同步 |  |
| `put` | 同步 |  |
| `_periodic_cleanup` | 同步 |  |
| `get_stats` | 同步 |  |
| `__init__` | 同步 |  |
| `_default_config` | 同步 |  |
| `read_keywords` | 同步 |  |
| `_init_matchers` | 同步 |  |
| `route` | 异步 |  |
| `_merge_results` | 同步 |  |
| `_quick_rule_match` | 同步 |  |
| `_check_special_patterns` | 同步 |  |
| `_llm_predict` | 异步 |  |
| `_get_cache_key` | 同步 |  |
| `_update_response_time` | 同步 |  |
| `get_stats` | 同步 |  |
| `clear_cache` | 同步 |  |

---

### 📄 modules\routes\models.py

- **文件大小**: 1.1 KB
- **代码行数**: 36

#### 导入依赖

```python
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from enum import Enum
from typing import List
from typing import TypedDict
```

#### 类定义

##### CLASS: RouteType(Enum)

##### CLASS: RouteDecision

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

##### CLASS: RouteDecisionCache

##### CLASS: KeyWords(TypedDict)

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

---

### 📄 modules\routes\words.py

- **文件大小**: 2.5 KB
- **代码行数**: 71

#### 导入依赖

```python
import re
from typing import Dict
from typing import List
from typing import Tuple
```

#### 类定义

##### CLASS: KeywordMatcher

> 高效的关键词匹配器，使用Trie树结构

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `build_from_keywords` | 同步 | 从 {service: [keywords]} 构建索引 |
| `_add_keyword` | 同步 |  |
| `search` | 同步 | 返回 [(service, weight), ...] |
| `_search_exact` | 同步 |  |
| `_search_regex` | 同步 |  |

##### CLASS: _TrieNode

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `build_from_keywords` | 同步 | 从 {service: [keywords]} 构建索引 |
| `_add_keyword` | 同步 |  |
| `search` | 同步 | 返回 [(service, weight), ...] |
| `_search_exact` | 同步 |  |
| `_search_regex` | 同步 |  |
| `__init__` | 同步 |  |

---

### 📄 modules\runtime.py

- **文件大小**: 2.7 KB
- **代码行数**: 91

#### 导入依赖

```python
from __future__ import annotations
import os
from pathlib import Path
import sys
```

#### 类定义

##### CLASS: StandardPaths

| 方法 | 类型 | 说明 |
|------|------|------|
| `get_app_root` | 同步 |  |
| `get_resources_dir` | 同步 |  |
| `get_models_dir` | 同步 |  |
| `get_scripts_dir` | 同步 |  |
| `get_defaults_dir` | 同步 |  |
| `get_roles_dir` | 同步 |  |

##### CLASS: RuntimePath

| 方法 | 类型 | 说明 |
|------|------|------|
| `get_models_path` | 同步 |  |
| `get_service_config_file_path` | 同步 |  |
| `get_pipeline_config_file_path` | 同步 |  |
| `get_icon_file_path` | 同步 |  |
| `get_memory_db_path` | 同步 |  |
| `get_static_path` | 同步 |  |
| `get_prompts_file_path` | 同步 |  |
| `get_roles_file_path` | 同步 |  |
| `get_scripts_path` | 同步 |  |
| `get_log_dir` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_app_root` | 同步 |  |
| `get_resources_dir` | 同步 |  |
| `get_models_dir` | 同步 |  |
| `get_scripts_dir` | 同步 |  |
| `get_defaults_dir` | 同步 |  |
| `get_roles_dir` | 同步 |  |
| `get_models_path` | 同步 |  |
| `get_service_config_file_path` | 同步 |  |
| `get_pipeline_config_file_path` | 同步 |  |
| `get_icon_file_path` | 同步 |  |
| `get_memory_db_path` | 同步 |  |
| `get_static_path` | 同步 |  |
| `get_prompts_file_path` | 同步 |  |
| `get_roles_file_path` | 同步 |  |
| `get_scripts_path` | 同步 |  |
| `get_log_dir` | 同步 |  |

---

### 📄 modules\services\__init__.py

- **文件大小**: 0.2 KB
- **代码行数**: 11

#### 导入依赖

```python
from base import ServiceState
```

#### 类定义

##### CLASS: ServiceId

---

### 📄 modules\services\base.py

- **文件大小**: 1.6 KB
- **代码行数**: 63

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
from threading import Lock
import threading
from typing import Callable
from typing import Optional
from typing import Dict
from tools.models import ServiceTool
```

#### 类定义

##### CLASS: ServiceState

##### CLASS: ServiceLifecycleHook

| 方法 | 类型 | 说明 |
|------|------|------|
| `on_config_change` | 同步 |  |
| `on_health_check_failed` | 同步 |  |

##### CLASS: _BaseService(ABC, ServiceLifecycleHook)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__new__` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `get_status` | 同步 |  |
| `get_tools` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `on_config_change` | 同步 |  |
| `on_health_check_failed` | 同步 |  |
| `__init__` | 同步 |  |
| `__new__` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `get_status` | 同步 |  |
| `get_tools` | 同步 |  |

---

### 📄 modules\services\browser\browser.py

- **文件大小**: 8.3 KB
- **代码行数**: 261

#### 导入依赖

```python
from dataclasses import asdict
from typing import Dict
from typing import List
from typing import Optional
from typing import Literal
from driver import BrowserDriver
from base import _BaseService
from base import ServiceState
from logger import logger
from events import on_event_class
from events import types
from manager.service.decorator import Service
from  import ServiceId
from distiller import DOMDistiller
from models import DistilledDOM
```

#### 类定义

##### CLASS: Browser(_BaseService)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `start` | 异步 |  |
| `stop` | 异步 |  |
| `set_status` | 同步 |  |
| `open_page` | 异步 |  |
| `go_back` | 异步 |  |
| `go_forward` | 异步 |  |
| `reload` | 异步 |  |
| `distill_dom` | 异步 | 执行完整 7 级蒸馏，返回结构化结果 |
| `get_llm_context` | 异步 | 直接返回喂给 LLM 的字符串。 |
| `get_all_chunks` | 异步 |  |
| `click` | 异步 |  |
| `type_text` | 异步 |  |
| `get_text` | 异步 |  |
| `hover` | 异步 |  |
| `scroll` | 异步 |  |
| `screenshot` | 异步 |  |
| `_uid_to_selector` | 异步 |  |
| `page` | 同步 |  |
| `current_url` | 同步 |  |
| `title` | 异步 |  |
| `get_page_source` | 异步 |  |
| `get_tools` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `start` | 异步 |  |
| `stop` | 异步 |  |
| `set_status` | 同步 |  |
| `open_page` | 异步 |  |
| `go_back` | 异步 |  |
| `go_forward` | 异步 |  |
| `reload` | 异步 |  |
| `distill_dom` | 异步 | 执行完整 7 级蒸馏，返回结构化结果 |
| `get_llm_context` | 异步 | 直接返回喂给 LLM 的字符串。 |
| `get_all_chunks` | 异步 |  |
| `click` | 异步 |  |
| `type_text` | 异步 |  |
| `get_text` | 异步 |  |
| `hover` | 异步 |  |
| `scroll` | 异步 |  |
| `screenshot` | 异步 |  |
| `_uid_to_selector` | 异步 |  |
| `page` | 同步 |  |
| `current_url` | 同步 |  |
| `title` | 异步 |  |
| `get_page_source` | 异步 |  |
| `get_tools` | 同步 |  |

---

### 📄 modules\services\browser\distiller.py

- **文件大小**: 16.6 KB
- **代码行数**: 466

#### 导入依赖

```python
from dataclasses import asdict
from difflib import SequenceMatcher
import hashlib
import json
import re
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from lxml import html as lxml_html
from utils.file import read_text
from runtime import RuntimePath
from models import DistilledDOM
from models import DomElement
from models import DomChunk
```

#### 类定义

##### CLASS: DOMDistiller

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `distill_html` | 同步 |  |
| `__is_style_hidden` | 同步 | 解析 style 属性，检测 display:none / visibility:hidden / opacity:0 |
| `distill_page` | 异步 |  |
| `__distill_from_js_result` | 同步 |  |
| `distill` | 同步 |  |
| `__filter_obscured` | 同步 | ② 遮挡检测：有 aria-modal=true 的弹窗出现时，屏蔽其后的同级元素 |
| `__filter_interactive` | 同步 | 只保留可交互元素或有语义信息的元素 |
| `__post_process` | 同步 |  |
| `__collapse_redundant` | 同步 | 移除无语义的纯包装 div/span/section/article |
| `__deduplicate` | 同步 |  |
| `__assign_stable_ids` | 同步 |  |
| `_chunk_elements` | 同步 |  |
| `__element_to_dom` | 同步 |  |
| `__dict_to_dom` | 同步 |  |
| `__build_xpath` | 同步 |  |
| `__calc_depth` | 同步 |  |
| `format_for_llm` | 同步 |  |
| `to_json` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `distill_html` | 同步 |  |
| `__is_style_hidden` | 同步 | 解析 style 属性，检测 display:none / visibility:hidden / opacity:0 |
| `distill_page` | 异步 |  |
| `__distill_from_js_result` | 同步 |  |
| `distill` | 同步 |  |
| `__filter_obscured` | 同步 | ② 遮挡检测：有 aria-modal=true 的弹窗出现时，屏蔽其后的同级元素 |
| `__filter_interactive` | 同步 | 只保留可交互元素或有语义信息的元素 |
| `__post_process` | 同步 |  |
| `__collapse_redundant` | 同步 | 移除无语义的纯包装 div/span/section/article |
| `__deduplicate` | 同步 |  |
| `__assign_stable_ids` | 同步 |  |
| `_chunk_elements` | 同步 |  |
| `__element_to_dom` | 同步 |  |
| `__dict_to_dom` | 同步 |  |
| `__build_xpath` | 同步 |  |
| `__calc_depth` | 同步 |  |
| `format_for_llm` | 同步 |  |
| `to_json` | 同步 |  |

---

### 📄 modules\services\browser\driver.py

- **文件大小**: 5.6 KB
- **代码行数**: 159

#### 导入依赖

```python
from typing import Dict
from typing import Optional
from typing import Literal
from playwright.async_api import async_playwright
from playwright.async_api import Playwright
from playwright.async_api import Browser
from playwright.async_api import BrowserContext
from playwright.async_api import Page
from src_py.modules.runtime import RuntimePath
from src_py.modules.utils.file import read_text
from logger import logger
from config import BrowserConfig
```

#### 类定义

##### CLASS: BrowserDriver

> 统一管理 Playwright 浏览器实例的生命周期

三种模式：
  1. launch()         —— 启动全新浏览器（自动下载）
  2. launch_persistent() —— 用用户 profile 启动
  3. connect_cdp()    —— 连接已运行的浏览器

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `build_args` | 同步 |  |
| `start_browser` | 异步 |  |
| `stop_browser` | 异步 |  |
| `new_page` | 异步 |  |
| `inject_stealth` | 异步 |  |
| `page` | 同步 |  |
| `context` | 同步 |  |
| `browser` | 同步 |  |
| `playwright` | 同步 |  |
| `__get_launcher` | 同步 |  |
| `__get_channel` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `build_args` | 同步 |  |
| `start_browser` | 异步 |  |
| `stop_browser` | 异步 |  |
| `new_page` | 异步 |  |
| `inject_stealth` | 异步 |  |
| `page` | 同步 |  |
| `context` | 同步 |  |
| `browser` | 同步 |  |
| `playwright` | 同步 |  |
| `__get_launcher` | 同步 |  |
| `__get_channel` | 同步 |  |

---

### 📄 modules\services\browser\models.py

- **文件大小**: 0.9 KB
- **代码行数**: 41

#### 导入依赖

```python
from dataclasses import dataclass
from dataclasses import field
from typing import Dict
from typing import List
```

#### 类定义

##### CLASS: DomElement

##### CLASS: DomChunk

##### CLASS: DistilledDOM

---

### 📄 modules\services\config.py

- **文件大小**: 2.6 KB
- **代码行数**: 49

#### 导入依赖

```python
from typing import Dict
from typing import List
from typing import Optional
from runtime import RuntimePath
from config.models import _BaseConfig
from config.models import Field
```

#### 类定义

##### CLASS: Live2DConfig(_BaseConfig)

##### CLASS: BrowserConfig(_BaseConfig)

##### CLASS: ObsConfig(_BaseConfig)

##### CLASS: BilibiliConfig(_BaseConfig)

> B站配置

##### CLASS: QQBotConfig(_BaseConfig)

---

### 📄 modules\services\game\minecraft.py

- **文件大小**: 0.0 KB
- **代码行数**: 0

---

### 📄 modules\services\knowledge\query\adapter.py

- **文件大小**: 4.2 KB
- **代码行数**: 132

#### 导入依赖

```python
from abc import ABC
from abc import abstractmethod
from typing import Coroutine
import re
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from utils.http import async_get
from  import models
```

#### 类定义

##### CLASS: _EngineSearch(ABC)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_search_params` | 同步 |  |
| `query` | 同步 |  |
| `get_result_header` | 同步 |  |
| `get_search_url` | 同步 |  |

##### CLASS: BingSearch(_EngineSearch)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_search_url` | 同步 |  |
| `query` | 异步 |  |
| `get_result_header` | 同步 |  |
| `get_search_results` | 同步 |  |
| `__parse_single_result` | 同步 | 解析单个搜索结果 |
| `__extract_source` | 同步 | 提取来源网站 |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_search_params` | 同步 |  |
| `query` | 同步 |  |
| `get_result_header` | 同步 |  |
| `get_search_url` | 同步 |  |
| `__init__` | 同步 |  |
| `get_search_url` | 同步 |  |
| `query` | 异步 |  |
| `get_result_header` | 同步 |  |
| `get_search_results` | 同步 |  |
| `__parse_single_result` | 同步 | 解析单个搜索结果 |
| `__extract_source` | 同步 | 提取来源网站 |

---

### 📄 modules\services\knowledge\query\models.py

- **文件大小**: 0.4 KB
- **代码行数**: 18

#### 导入依赖

```python
from typing import TypedDict
```

#### 类定义

##### CLASS: BingSearchParamsParamters

##### CLASS: Form

##### CLASS: SafeSearch

##### CLASS: RequestParams(TypedDict)

---

### 📄 modules\services\knowledge\query\serach.py

- **文件大小**: 3.6 KB
- **代码行数**: 100

#### 导入依赖

```python
import asyncio
from csv import QUOTE_MINIMAL
from csv import writer
import os
from threading import Lock
import time
from typing import Any
from typing import Dict
from typing import List
from typing import Literal
from typing import Union
from logger import logger
from utils.file import write_json
from adapter import BingSearch
```

#### 类定义

##### CLASS: SreachEngine

| 方法 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `get_tools` | 同步 |  |
| `__create_engine_search` | 同步 |  |
| `query` | 异步 |  |
| `save` | 同步 |  |
| `save_json` | 同步 |  |
| `save_csv` | 同步 |  |
| `clear_cache` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `get_tools` | 同步 |  |
| `__create_engine_search` | 同步 |  |
| `query` | 异步 |  |
| `save` | 同步 |  |
| `save_json` | 同步 |  |
| `save_csv` | 同步 |  |
| `clear_cache` | 同步 |  |

---

### 📄 modules\services\live2d\audio.py

- **文件大小**: 9.2 KB
- **代码行数**: 267

#### 导入依赖

```python
from threading import Thread
import asyncio
from typing import Optional
import wave
from queue import Queue
from queue import Empty
import numpy as np
import time
from typing import Callable
from live2d.utils.lipsync import WavHandler as Live2DWavHandler
from pydub import AudioSegment
from pygame import mixer
```

#### 类定义

##### CLASS: AsyncRmsMeter

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `update` | 同步 |  |
| `__event_pool` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `push_chunk` | 同步 |  |
| `get_rms` | 同步 |  |
| `set_audio_format` | 同步 |  |
| `__async_worker` | 异步 |  |
| `__worker` | 同步 |  |

##### CLASS: AsyncChunkPlayer

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__event_pool` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `push_chunk` | 同步 |  |
| `set_before_play_callback` | 同步 |  |
| `__worker` | 同步 |  |
| `__async_worker` | 异步 |  |

##### CLASS: WavHandler(Live2DWavHandler)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `Start` | 同步 |  |
| `Start_Pcm` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `update` | 同步 |  |
| `__event_pool` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `push_chunk` | 同步 |  |
| `get_rms` | 同步 |  |
| `set_audio_format` | 同步 |  |
| `__async_worker` | 异步 |  |
| `__worker` | 同步 |  |
| `__init__` | 同步 |  |
| `__event_pool` | 同步 |  |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `push_chunk` | 同步 |  |
| `set_before_play_callback` | 同步 |  |
| `__worker` | 同步 |  |
| `__async_worker` | 异步 |  |
| `__init__` | 同步 |  |
| `Start` | 同步 |  |
| `Start_Pcm` | 同步 |  |

---

### 📄 modules\services\live2d\canvas.py

- **文件大小**: 28.2 KB
- **代码行数**: 715

#### 导入依赖

```python
from __future__ import annotations
from queue import Queue
import live2d.v3 as live2d
from typing import Optional
import time
import math
import pygame
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QMutex
from PyQt5.QtCore import QWaitCondition
from PyQt5.QtCore import QSize
from PyQt5.QtCore import QThread
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtGui import QOpenGLContext
# ... 还有 18 个导入
```

#### 类定义

##### CLASS: OffscreenRenderer(QObject)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `set_rotation_angle` | 同步 |  |
| `__init_rotate_resources` | 同步 | 创建用于旋转+透明度的着色器程序和全屏四边形 VAO |
| `__rotate_fbo` | 同步 | 将源 FBO 的内容旋转后输出到临时 FBO，并读取为 QImage |
| `start` | 同步 | 启动渲染线程 |
| `stop` | 同步 | 停止渲染线程 |
| `set_render_callback` | 同步 |  |
| `request_render` | 同步 | 请求渲染一帧 (非阻塞) |
| `set_fps` | 同步 |  |
| `__resize_fbo` | 同步 | 调整 FBO 大小 (重新创建) |
| `prepare` | 同步 |  |
| `__create_context` | 同步 | 创建 OpenGL 上下文 |
| `__create_fbo` | 同步 | 创建 FBO |
| `__render_loop` | 同步 | 工作线程主循环 |

##### CLASS: Live2DCanvas(QLabel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__on_image_ready` | 同步 | 接收到渲染图像，显示在界面上 |
| `stop` | 同步 | 停止渲染线程 |
| `closeEvent` | 同步 | 关闭窗口时停止渲染线程 |
| `apply_face_data` | 同步 |  |
| `sync_play` | 同步 |  |
| `mousePressEvent` | 同步 |  |
| `__sync_lip_sync` | 同步 |  |
| `mouseMoveEvent` | 同步 |  |
| `mouseReleaseEvent` | 同步 |  |
| `keyPressEvent` | 同步 |  |
| `getHitFeedback` | 同步 |  |
| `resizeEvent` | 同步 |  |
| `__ensure_model_loaded` | 同步 | 确保模型已加载 (在 OpenGL 上下文中调用) |
| `load_model` | 同步 |  |
| `start` | 同步 |  |
| `init` | 同步 |  |
| `__update_wavehand` | 同步 |  |
| `__draw_live2d` | 同步 | 绘制 Live2D 模型 |
| `pull_audio` | 同步 |  |
| `push_audio_chunk` | 同步 |  |
| `configure_audio_format` | 同步 |  |
| `set_rotation_angle` | 同步 |  |
| `set_opacity` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `compile_shader` | 同步 |  |
| `create_program` | 同步 |  |
| `create_vao` | 同步 |  |
| `create_canvas_framebuffer` | 同步 |  |
| `__init__` | 同步 |  |
| `set_rotation_angle` | 同步 |  |
| `__init_rotate_resources` | 同步 | 创建用于旋转+透明度的着色器程序和全屏四边形 VAO |
| `__rotate_fbo` | 同步 | 将源 FBO 的内容旋转后输出到临时 FBO，并读取为 QImage |
| `start` | 同步 | 启动渲染线程 |
| `stop` | 同步 | 停止渲染线程 |
| `set_render_callback` | 同步 |  |
| `request_render` | 同步 | 请求渲染一帧 (非阻塞) |
| `set_fps` | 同步 |  |
| `__resize_fbo` | 同步 | 调整 FBO 大小 (重新创建) |
| `prepare` | 同步 |  |
| `__create_context` | 同步 | 创建 OpenGL 上下文 |
| `__create_fbo` | 同步 | 创建 FBO |
| `__render_loop` | 同步 | 工作线程主循环 |
| `__init__` | 同步 |  |
| `__on_image_ready` | 同步 | 接收到渲染图像，显示在界面上 |
| `stop` | 同步 | 停止渲染线程 |
| `closeEvent` | 同步 | 关闭窗口时停止渲染线程 |
| `apply_face_data` | 同步 |  |
| `sync_play` | 同步 |  |
| `mousePressEvent` | 同步 |  |
| `__sync_lip_sync` | 同步 |  |
| `mouseMoveEvent` | 同步 |  |
| `mouseReleaseEvent` | 同步 |  |
| `keyPressEvent` | 同步 |  |
| `getHitFeedback` | 同步 |  |
| `resizeEvent` | 同步 |  |
| `__ensure_model_loaded` | 同步 | 确保模型已加载 (在 OpenGL 上下文中调用) |
| `load_model` | 同步 |  |
| `start` | 同步 |  |
| `init` | 同步 |  |
| `__update_wavehand` | 同步 |  |
| `__draw_live2d` | 同步 | 绘制 Live2D 模型 |
| `pull_audio` | 同步 |  |
| `push_audio_chunk` | 同步 |  |
| `configure_audio_format` | 同步 |  |
| `set_rotation_angle` | 同步 |  |
| `set_opacity` | 同步 |  |

---

### 📄 modules\services\live2d\components.py

- **文件大小**: 17.4 KB
- **代码行数**: 471

#### 导入依赖

```python
from pathlib import Path
from typing import Callable
from typing import Optional
from typing import Union
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import Qt
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QWidget
from utils.util import create_daemon_thread
from pipeline.adapters.landmarker.face import ResultFaceData
from pipeline.adapters.landmarker.face import FaceTracker
```

#### 类定义

##### CLASS: FaceTrackerComponent

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init` | 同步 |  |
| `__poll_face_data` | 同步 |  |
| `set_fps` | 同步 |  |
| `start` | 同步 |  |
| `set_model_path` | 同步 |  |
| `set_source` | 同步 |  |
| `set_enabled` | 同步 |  |
| `set_mirror` | 同步 |  |
| `stop` | 同步 |  |
| `close` | 同步 |  |
| `set_process_callback` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `init` | 同步 |  |
| `__poll_face_data` | 同步 |  |
| `set_fps` | 同步 |  |
| `start` | 同步 |  |
| `set_model_path` | 同步 |  |
| `set_source` | 同步 |  |
| `set_enabled` | 同步 |  |
| `set_mirror` | 同步 |  |
| `stop` | 同步 |  |
| `close` | 同步 |  |
| `set_process_callback` | 同步 |  |

---

### 📄 modules\services\live2d\views.py

- **文件大小**: 11.6 KB
- **代码行数**: 319

#### 导入依赖

```python
import os
import sys
from typing import Literal
from typing import Optional
from typing import Union
from events.data import BaseEvent
from runtime import get_models_path
from  import base
from logger import logger
from events import emit
from events import off
from events import on_event_class
from events import types as eventType
from events import on
from manager.service.decorator import Service
from PyQt5.QtCore import QObject
from  import ServiceId
from PyQt5.QtWidgets import QApplication
from canvas import Live2DCanvas
from PyQt5.QtCore import Qt
# ... 还有 3 个导入
```

#### 类定义

##### CLASS: Live2DController(QObject)

> Live2D控制器 - 始终运行在主线程

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize` | 同步 | 初始化（必须在主线程调用） |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `close` | 同步 |  |
| `show` | 同步 |  |
| `hide` | 同步 |  |
| `_do_position` | 同步 |  |
| `set_rotation_angle` | 同步 |  |
| `set_opacity` | 同步 |  |
| `put_audio` | 同步 |  |
| `put_audio_chunk` | 同步 |  |
| `set_model_path` | 同步 |  |
| `set_face_enabled` | 同步 |  |
| `set_face_source` | 同步 |  |
| `set_face_fps` | 同步 |  |

##### CLASS: Live2DView(base._BaseService)

> Parameters:
    model_path: Live2D模型路径
    window_size: 窗口大小
    window_icon_path: 窗口图标路径
    window_title: 窗口标题
    fps: 帧率
    canvas_size: 画布大小
    enable_audio_sync: 是否启用音频同步
    enable_chunk_playback: 是否启用分块播放
    is_face_detected: 是否启用人脸检测
    mediaPipeFace_model_path: 人脸检测模型路径
    face_source: 人脸检测源
    face_fps: 人脸检测帧率

| 方法 | 类型 | 说明 |
|------|------|------|
| `get_tools` | 同步 |  |
| `__init__` | 同步 |  |
| `__ensure_controller` | 同步 |  |
| `__create_controller` | 同步 |  |
| `set_rotation_angle` | 同步 |  |
| `set_opacity` | 同步 |  |
| `put_audio` | 同步 |  |
| `put_audio_chunk` | 同步 |  |
| `set_model_path` | 同步 |  |
| `set_face_enabled` | 同步 |  |
| `set_face_source` | 同步 |  |
| `set_face_fps` | 同步 |  |
| `init` | 同步 | 初始化 - 确保在主线程完成 |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `close` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `initialize` | 同步 | 初始化（必须在主线程调用） |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `close` | 同步 |  |
| `show` | 同步 |  |
| `hide` | 同步 |  |
| `_do_position` | 同步 |  |
| `set_rotation_angle` | 同步 |  |
| `set_opacity` | 同步 |  |
| `put_audio` | 同步 |  |
| `put_audio_chunk` | 同步 |  |
| `set_model_path` | 同步 |  |
| `set_face_enabled` | 同步 |  |
| `set_face_source` | 同步 |  |
| `set_face_fps` | 同步 |  |
| `get_tools` | 同步 |  |
| `__init__` | 同步 |  |
| `__ensure_controller` | 同步 |  |
| `__create_controller` | 同步 |  |
| `set_rotation_angle` | 同步 |  |
| `set_opacity` | 同步 |  |
| `put_audio` | 同步 |  |
| `put_audio_chunk` | 同步 |  |
| `set_model_path` | 同步 |  |
| `set_face_enabled` | 同步 |  |
| `set_face_source` | 同步 |  |
| `set_face_fps` | 同步 |  |
| `init` | 同步 | 初始化 - 确保在主线程完成 |
| `start` | 同步 |  |
| `stop` | 同步 |  |
| `close` | 同步 |  |

---

### 📄 modules\services\obs\client.py

- **文件大小**: 38.5 KB
- **代码行数**: 1022

#### 导入依赖

```python
import asyncio
import asyncio
import base64
from json import loads
from json import dumps
from json import JSONDecodeError
from typing import Any
from typing import Dict
from typing import Optional
from typing import Union
import hashlib
from typing import Dict
from typing import Optional
from manager.service.decorator import Service
from config import ObsConfig
from  import base
from logger import logger
from utils import util
from  import models
from events import on_event_class
# ... 还有 6 个导入
```

#### 类定义

##### CLASS: OBSClient(base._BaseService)

> References:
    <a href="https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md">OBS WebSocket Protocol</a>

Parameters:
    ip: OBS服务器IP地址
    obs_password: OBS服务器密码
    port: OBS服务器端口号
    subprotocol: OBS服务器子协议
    timeout: 连接超时时间

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `set_status` | 同步 |  |
| `_send` | 异步 | 发送请求到OBS服务器 |
| `__build_identify` | 同步 |  |
| `start` | 异步 |  |
| `get_tools` | 同步 |  |
| `connect` | 异步 |  |
| `stop` | 异步 |  |
| `__handle_event` | 异步 |  |
| `is_connected` | 同步 |  |
| `request` | 异步 | 发送请求并等待响应，返回 responseData；失败时抛出 OBSRequestError。 |
| `__auth` | 异步 |  |
| `__generate_base64_secret` | 同步 |  |
| `get_version` | 异步 |  |
| `get_stats` | 异步 |  |
| `get_hotkey_list` | 异步 |  |
| `get_scene_collection_list` | 异步 |  |
| `set_current_scene_collection` | 异步 |  |
| `get_profile_list` | 异步 |  |
| `set_current_profile` | 异步 |  |
| `get_video_settings` | 异步 |  |
| `set_video_settings` | 异步 |  |
| `get_stream_service_settings` | 异步 |  |
| `get_record_directory` | 异步 |  |
| `set_record_directory` | 异步 |  |
| `get_scene_list` | 异步 |  |
| `get_group_list` | 异步 |  |
| `get_current_program_scene` | 异步 |  |
| `set_current_program_scene` | 异步 |  |
| `get_current_preview_scene` | 异步 |  |
| `set_current_preview_scene` | 异步 |  |
| `create_scene` | 异步 |  |
| `remove_scene` | 异步 |  |
| `set_scene_name` | 异步 |  |
| `get_scene_scene_transition_override` | 异步 |  |
| `set_scene_scene_transition_override` | 异步 |  |
| `get_input_list` | 异步 |  |
| `get_input_kind_list` | 异步 |  |
| `get_special_inputs` | 异步 |  |
| `create_input` | 异步 |  |
| `remove_input` | 异步 |  |
| `set_input_name` | 异步 |  |
| `get_input_default_settings` | 异步 |  |
| `get_input_settings` | 异步 |  |
| `set_input_settings` | 异步 |  |
| `get_input_mute` | 异步 |  |
| `set_input_mute` | 异步 |  |
| `toggle_input_mute` | 异步 |  |
| `get_input_volume` | 异步 |  |
| `set_input_volume` | 异步 |  |
| `get_input_audio_balance` | 异步 |  |
| `set_input_audio_balance` | 异步 |  |
| `get_transition_kind_list` | 异步 |  |
| `get_scene_transition_list` | 异步 |  |
| `get_current_scene_transition` | 异步 |  |
| `set_current_scene_transition` | 异步 |  |
| `set_current_scene_transition_duration` | 异步 |  |
| `set_current_scene_transition_settings` | 异步 |  |
| `trigger_studio_mode_transition` | 异步 |  |
| `set_tbar_position` | 异步 |  |
| `get_source_filter_kind_list` | 异步 |  |
| `get_source_filter_list` | 异步 |  |
| `create_source_filter` | 异步 |  |
| `remove_source_filter` | 异步 |  |
| `set_source_filter_name` | 异步 |  |
| `get_source_filter` | 异步 |  |
| `set_source_filter_index` | 异步 |  |
| `set_source_filter_settings` | 异步 |  |
| `set_source_filter_enabled` | 异步 |  |
| `get_scene_item_list` | 异步 |  |
| `get_group_scene_item_list` | 异步 |  |
| `get_scene_item_id` | 异步 |  |
| `create_scene_item` | 异步 |  |
| `remove_scene_item` | 异步 |  |
| `get_scene_item_transform` | 异步 |  |
| `set_scene_item_transform` | 异步 |  |
| `get_scene_item_enabled` | 异步 |  |
| `set_scene_item_enabled` | 异步 |  |
| `get_scene_item_locked` | 异步 |  |
| `set_scene_item_locked` | 异步 |  |
| `get_scene_item_index` | 异步 |  |
| `set_scene_item_index` | 异步 |  |
| `get_virtual_cam_status` | 异步 |  |
| `toggle_virtual_cam` | 异步 |  |
| `start_virtual_cam` | 异步 |  |
| `stop_virtual_cam` | 异步 |  |
| `get_replay_buffer_status` | 异步 |  |
| `toggle_replay_buffer` | 异步 |  |
| `start_replay_buffer` | 异步 |  |
| `stop_replay_buffer` | 异步 |  |
| `save_replay_buffer` | 异步 |  |
| `get_last_replay_buffer_replay` | 异步 |  |
| `get_output_list` | 异步 |  |
| `get_output_status` | 异步 |  |
| `toggle_output` | 异步 |  |
| `start_output` | 异步 |  |
| `stop_output` | 异步 |  |
| `get_output_settings` | 异步 |  |
| `set_output_settings` | 异步 |  |
| `get_stream_status` | 异步 |  |
| `toggle_stream` | 异步 |  |
| `start_stream` | 异步 |  |
| `stop_stream` | 异步 |  |
| `send_stream_caption` | 异步 |  |
| `get_record_status` | 异步 |  |
| `toggle_record` | 异步 |  |
| `start_record` | 异步 |  |
| `stop_record` | 异步 |  |
| `toggle_record_pause` | 异步 |  |
| `pause_record` | 异步 |  |
| `resume_record` | 异步 |  |
| `create_record_chapter` | 异步 |  |
| `get_media_input_status` | 异步 |  |
| `set_media_input_cursor` | 异步 |  |
| `offset_media_input_cursor` | 异步 |  |
| `trigger_media_input_action` | 异步 |  |
| `get_studio_mode_enabled` | 异步 |  |
| `set_studio_mode_enabled` | 异步 |  |
| `open_input_properties_dialog` | 异步 |  |
| `open_input_filters_dialog` | 异步 |  |
| `get_monitor_list` | 异步 |  |
| `get_source_active` | 异步 |  |
| `get_source_screenshot` | 异步 |  |
| `_request_event` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `set_status` | 同步 |  |
| `_send` | 异步 | 发送请求到OBS服务器 |
| `__build_identify` | 同步 |  |
| `start` | 异步 |  |
| `get_tools` | 同步 |  |
| `connect` | 异步 |  |
| `stop` | 异步 |  |
| `__handle_event` | 异步 |  |
| `is_connected` | 同步 |  |
| `request` | 异步 | 发送请求并等待响应，返回 responseData；失败时抛出 OBSRequestError。 |
| `__auth` | 异步 |  |
| `__generate_base64_secret` | 同步 |  |
| `get_version` | 异步 |  |
| `get_stats` | 异步 |  |
| `get_hotkey_list` | 异步 |  |
| `get_scene_collection_list` | 异步 |  |
| `set_current_scene_collection` | 异步 |  |
| `get_profile_list` | 异步 |  |
| `set_current_profile` | 异步 |  |
| `get_video_settings` | 异步 |  |
| `set_video_settings` | 异步 |  |
| `get_stream_service_settings` | 异步 |  |
| `get_record_directory` | 异步 |  |
| `set_record_directory` | 异步 |  |
| `get_scene_list` | 异步 |  |
| `get_group_list` | 异步 |  |
| `get_current_program_scene` | 异步 |  |
| `set_current_program_scene` | 异步 |  |
| `get_current_preview_scene` | 异步 |  |
| `set_current_preview_scene` | 异步 |  |
| `create_scene` | 异步 |  |
| `remove_scene` | 异步 |  |
| `set_scene_name` | 异步 |  |
| `get_scene_scene_transition_override` | 异步 |  |
| `set_scene_scene_transition_override` | 异步 |  |
| `get_input_list` | 异步 |  |
| `get_input_kind_list` | 异步 |  |
| `get_special_inputs` | 异步 |  |
| `create_input` | 异步 |  |
| `remove_input` | 异步 |  |
| `set_input_name` | 异步 |  |
| `get_input_default_settings` | 异步 |  |
| `get_input_settings` | 异步 |  |
| `set_input_settings` | 异步 |  |
| `get_input_mute` | 异步 |  |
| `set_input_mute` | 异步 |  |
| `toggle_input_mute` | 异步 |  |
| `get_input_volume` | 异步 |  |
| `set_input_volume` | 异步 |  |
| `get_input_audio_balance` | 异步 |  |
| `set_input_audio_balance` | 异步 |  |
| `get_transition_kind_list` | 异步 |  |
| `get_scene_transition_list` | 异步 |  |
| `get_current_scene_transition` | 异步 |  |
| `set_current_scene_transition` | 异步 |  |
| `set_current_scene_transition_duration` | 异步 |  |
| `set_current_scene_transition_settings` | 异步 |  |
| `trigger_studio_mode_transition` | 异步 |  |
| `set_tbar_position` | 异步 |  |
| `get_source_filter_kind_list` | 异步 |  |
| `get_source_filter_list` | 异步 |  |
| `create_source_filter` | 异步 |  |
| `remove_source_filter` | 异步 |  |
| `set_source_filter_name` | 异步 |  |
| `get_source_filter` | 异步 |  |
| `set_source_filter_index` | 异步 |  |
| `set_source_filter_settings` | 异步 |  |
| `set_source_filter_enabled` | 异步 |  |
| `get_scene_item_list` | 异步 |  |
| `get_group_scene_item_list` | 异步 |  |
| `get_scene_item_id` | 异步 |  |
| `create_scene_item` | 异步 |  |
| `remove_scene_item` | 异步 |  |
| `get_scene_item_transform` | 异步 |  |
| `set_scene_item_transform` | 异步 |  |
| `get_scene_item_enabled` | 异步 |  |
| `set_scene_item_enabled` | 异步 |  |
| `get_scene_item_locked` | 异步 |  |
| `set_scene_item_locked` | 异步 |  |
| `get_scene_item_index` | 异步 |  |
| `set_scene_item_index` | 异步 |  |
| `get_virtual_cam_status` | 异步 |  |
| `toggle_virtual_cam` | 异步 |  |
| `start_virtual_cam` | 异步 |  |
| `stop_virtual_cam` | 异步 |  |
| `get_replay_buffer_status` | 异步 |  |
| `toggle_replay_buffer` | 异步 |  |
| `start_replay_buffer` | 异步 |  |
| `stop_replay_buffer` | 异步 |  |
| `save_replay_buffer` | 异步 |  |
| `get_last_replay_buffer_replay` | 异步 |  |
| `get_output_list` | 异步 |  |
| `get_output_status` | 异步 |  |
| `toggle_output` | 异步 |  |
| `start_output` | 异步 |  |
| `stop_output` | 异步 |  |
| `get_output_settings` | 异步 |  |
| `set_output_settings` | 异步 |  |
| `get_stream_status` | 异步 |  |
| `toggle_stream` | 异步 |  |
| `start_stream` | 异步 |  |
| `stop_stream` | 异步 |  |
| `send_stream_caption` | 异步 |  |
| `get_record_status` | 异步 |  |
| `toggle_record` | 异步 |  |
| `start_record` | 异步 |  |
| `stop_record` | 异步 |  |
| `toggle_record_pause` | 异步 |  |
| `pause_record` | 异步 |  |
| `resume_record` | 异步 |  |
| `create_record_chapter` | 异步 |  |
| `get_media_input_status` | 异步 |  |
| `set_media_input_cursor` | 异步 |  |
| `offset_media_input_cursor` | 异步 |  |
| `trigger_media_input_action` | 异步 |  |
| `get_studio_mode_enabled` | 异步 |  |
| `set_studio_mode_enabled` | 异步 |  |
| `open_input_properties_dialog` | 异步 |  |
| `open_input_filters_dialog` | 异步 |  |
| `get_monitor_list` | 异步 |  |
| `get_source_active` | 异步 |  |
| `get_source_screenshot` | 异步 |  |
| `_request_event` | 异步 |  |

---

### 📄 modules\services\obs\models.py

- **文件大小**: 3.8 KB
- **代码行数**: 105

#### 导入依赖

```python
from typing import TypedDict
from typing import Optional
from typing import TypedDict
from dataclasses import dataclass
from pydantic import BaseModel
```

#### 类定义

##### CLASS: OBSEventType

##### CLASS: OBSError

##### CLASS: OBSRequestParams(TypedDict)

##### CLASS: OBSResponseData(BaseModel)

##### CLASS: ObsWebsocketSERIVE

##### CLASS: ObsWebsocketCLINETEvent

##### CLASS: EventSubscription

##### CLASS: ObsMediaInputAction

##### CLASS: GeneralEventType

##### CLASS: TransitionsEventType

##### CLASS: SourceEventType

##### CLASS: ConfigEventType

##### CLASS: RequestError(Exception)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |

##### CLASS: ConnectionError(Exception)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `__init__` | 同步 |  |

---

### 📄 modules\services\qqbot\client.py

- **文件大小**: 24.8 KB
- **代码行数**: 655

#### 导入依赖

```python
import asyncio
import json
import time
from typing import Any
from typing import Dict
from typing import Optional
import httpx
from websockets import connect
from websockets import ClientConnection
from websockets.exceptions import ConnectionClosed
from tools.models import ToolFunction
from tools.models import ToolFunctionParameters
from events.data import BaseEvent
from logger import logger
from config import QQBotConfig
from  import base
from  import models
from events import emit
from events import types as eventType
from events import on_event_class
# ... 还有 3 个导入
```

#### 类定义

##### CLASS: QQBotClient(base._BaseService)

> Reference:
    <a href="https://bot.q.qq.com/wiki/develop/api-v2/#">QQ Bot API V2</a>
Parameters:
    appid: QQ Bot应用ID
    secret: QQ Bot应用密钥

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_tools` | 同步 |  |
| `set_status` | 同步 |  |
| `start` | 异步 |  |
| `stop` | 异步 |  |
| `__ensure_token` | 异步 | 获取或刷新 AccessToken `POST app/getAppAccessToken` |
| `__headers` | 同步 | 构造API请求头 |
| `__get_websocket_url` | 异步 | 从gateway接口获取WebSocket地址 `GET /gateway` |
| `__connect_gateway` | 异步 | 连接WebSocket Gateway `WS` |
| `__handle_payload` | 异步 |  |
| `__send_identify` | 异步 |  |
| `__dispatch_event` | 异步 | 可用事件名： |
| `__on_c2c_msg_created` | 同步 | 2C消息创建 |
| `__heartbeat` | 异步 |  |
| `send_group_message` | 异步 | 发送群消息 `POST /v2/groups/{group_openid}/messages` |
| `send_user_message` | 异步 | 发送单聊(C2C)消息 `POST /v2/users/{user_openid}/messages` |
| `get_bot_info` | 异步 | 获取机器人自身信息 `GET /v2/users/@me` |
| `get_info` | 同步 | 重写基类方法，返回服务状态 |
| `__on_guild_created` | 同步 | 机器人加入新频道 |
| `__on_guild_deleted` | 同步 | 机器人被移出频道（被踢/解散） |
| `__on_guild_updated` | 异步 | 频道信息更新 |
| `__on_channel_created` | 异步 | 子频道创建 |
| `__on_channel_deleted` | 同步 | 子频道删除 |
| `__on_channel_updated` | 同步 | 子频道更新 |
| `__on_group_added` | 同步 | 机器人被添加到群聊 |
| `__on_group_removed` | 同步 | 机器人被踢出群聊或被群管理员删除 |
| `__on_group_msg_rejected` | 同步 | 机器人被群禁言 |
| `__on_friend_added` | 同步 | 机器人被添加好友 |
| `__on_friend_deleted` | 同步 | 机器人被删除好友 |
| `__on_c2c_msg_rejected` | 同步 | 用户拒绝接收机器人消息 |
| `__on_direct_message` | 同步 | 收到私信消息 |
| `__on_interaction_create` | 同步 | 交互事件（按钮点击等） |
| `__log_bot_event` | 同步 | 记录机器人生命周期事件到持久化日志 |
| `__trigger_lifecycle` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_tools` | 同步 |  |
| `set_status` | 同步 |  |
| `start` | 异步 |  |
| `stop` | 异步 |  |
| `__ensure_token` | 异步 | 获取或刷新 AccessToken `POST app/getAppAccessToken` |
| `__headers` | 同步 | 构造API请求头 |
| `__get_websocket_url` | 异步 | 从gateway接口获取WebSocket地址 `GET /gateway` |
| `__connect_gateway` | 异步 | 连接WebSocket Gateway `WS` |
| `__handle_payload` | 异步 |  |
| `__send_identify` | 异步 |  |
| `__dispatch_event` | 异步 | 可用事件名： |
| `__on_c2c_msg_created` | 同步 | 2C消息创建 |
| `__heartbeat` | 异步 |  |
| `send_group_message` | 异步 | 发送群消息 `POST /v2/groups/{group_openid}/messages` |
| `send_user_message` | 异步 | 发送单聊(C2C)消息 `POST /v2/users/{user_openid}/messages` |
| `get_bot_info` | 异步 | 获取机器人自身信息 `GET /v2/users/@me` |
| `get_info` | 同步 | 重写基类方法，返回服务状态 |
| `__on_guild_created` | 同步 | 机器人加入新频道 |
| `__on_guild_deleted` | 同步 | 机器人被移出频道（被踢/解散） |
| `__on_guild_updated` | 异步 | 频道信息更新 |
| `__on_channel_created` | 异步 | 子频道创建 |
| `__on_channel_deleted` | 同步 | 子频道删除 |
| `__on_channel_updated` | 同步 | 子频道更新 |
| `__on_group_added` | 同步 | 机器人被添加到群聊 |
| `__on_group_removed` | 同步 | 机器人被踢出群聊或被群管理员删除 |
| `__on_group_msg_rejected` | 同步 | 机器人被群禁言 |
| `__on_friend_added` | 同步 | 机器人被添加好友 |
| `__on_friend_deleted` | 同步 | 机器人被删除好友 |
| `__on_c2c_msg_rejected` | 同步 | 用户拒绝接收机器人消息 |
| `__on_direct_message` | 同步 | 收到私信消息 |
| `__on_interaction_create` | 同步 | 交互事件（按钮点击等） |
| `__log_bot_event` | 同步 | 记录机器人生命周期事件到持久化日志 |
| `__trigger_lifecycle` | 同步 |  |

---

### 📄 modules\services\qqbot\models.py

- **文件大小**: 1.5 KB
- **代码行数**: 48

#### 导入依赖

```python
from dataclasses import dataclass
from dataclasses import field
from typing import Dict
from typing import Optional
from typing import TypedDict
```

#### 类定义

##### CLASS: QQBotEvent

##### CLASS: QQBotData

##### CLASS: WebSocketEvent

##### CLASS: MessageType

##### CLASS: LifecycleEvent

##### CLASS: QQBotResponse

##### CLASS: QQBotInfo(TypedDict)

---

### 📄 modules\tools\ctl.py

- **文件大小**: 6.0 KB
- **代码行数**: 151

#### 导入依赖

```python
from __future__ import annotations
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from manager.task.decorator import async_task_scheduler
from routes.models import RouteType
from logger import logger
from manager.service.manager import service_manager
from services.exceute import CommandExecutor
from services.exceute import ResultFormatter
from services.formatter import CommandParser
from services.formatter import CommandValidator
from services.models import CommandData
from services.models import CommandResult
from services.models import CommandStatus
from services.models import OrchestrationConfig
from services.models import OrchestrationState
from skills.manager import ExternalSkillManager
from config.builder import PromptBuilder
# ... 还有 1 个导入
```

#### 类定义

##### CLASS: ServiceOrchestrator

> Prompt-command orchestrator for service calls and skills.

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `run_raw_commands` | 异步 |  |
| `_build_system_prompt` | 同步 |  |
| `_extract_commands` | 同步 |  |
| `_execute_commands` | 异步 |  |
| `_execute_skill_command` | 异步 |  |
| `get_audit_result` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `run_raw_commands` | 异步 |  |
| `_build_system_prompt` | 同步 |  |
| `_extract_commands` | 同步 |  |
| `_execute_commands` | 异步 |  |
| `_execute_skill_command` | 异步 |  |
| `get_audit_result` | 同步 |  |

---

### 📄 modules\tools\models.py

- **文件大小**: 1.5 KB
- **代码行数**: 63

#### 导入依赖

```python
from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import Literal
from typing import Optional
from typing import TypedDict
from typing import List
from typing import Union
from pydantic import BaseModel
```

#### 类定义

##### CLASS: ToolFunctionParameters(BaseModel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

##### CLASS: ToolFunction(BaseModel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

##### CLASS: OpenAITool(BaseModel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

##### CLASS: AnthropicTool(BaseModel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |
| `to_dict` | 同步 |  |
| `to_dict` | 同步 |  |
| `to_dict` | 同步 |  |

---

### 📄 modules\tools\sanbox\executor.py

- **文件大小**: 4.6 KB
- **代码行数**: 187

#### 导入依赖

```python
import ast
from dataclasses import field
import re
from typing import List
from typing import Set
from typing import Tuple
from restricted import SandboxConfig
```

#### 类定义

##### CLASS: CodeValidator

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `_compile_blocked_patterns` | 同步 |  |
| `validate_code` | 同步 | 验证代码安全性 |
| `_is_module_allowed` | 同步 | 检查模块是否在白名单中 |
| `_get_call_name` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `_compile_blocked_patterns` | 同步 |  |
| `validate_code` | 同步 | 验证代码安全性 |
| `_is_module_allowed` | 同步 | 检查模块是否在白名单中 |
| `_get_call_name` | 同步 |  |

---

### 📄 modules\tools\sanbox\restricted.py

- **文件大小**: 7.5 KB
- **代码行数**: 228

#### 导入依赖

```python
from dataclasses import dataclass
import gc
import os
import sys
import threading
import time
from typing import Any
from typing import Dict
from typing import Optional
import psutil
```

#### 类定义

##### CLASS: SandboxConfig

##### CLASS: ResourceLimiter

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `start_monitoring` | 同步 |  |
| `check_timeout` | 同步 | 检查是否超时 |
| `check_memory` | 同步 |  |

##### CLASS: RestrictedCodeExecutor

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `_create_safe_builtins` | 同步 | 创建安全的builtins字典 |
| `_safe_print` | 同步 |  |
| `execute_code` | 同步 | 在沙盒中执行代码 |
| `_filter_output` | 同步 | 过滤输出，移除敏感信息 |
| `get_stats` | 同步 | 获取执行统计 |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `start_monitoring` | 同步 |  |
| `check_timeout` | 同步 | 检查是否超时 |
| `check_memory` | 同步 |  |
| `__init__` | 同步 |  |
| `_create_safe_builtins` | 同步 | 创建安全的builtins字典 |
| `_safe_print` | 同步 |  |
| `execute_code` | 同步 | 在沙盒中执行代码 |
| `_filter_output` | 同步 | 过滤输出，移除敏感信息 |
| `get_stats` | 同步 | 获取执行统计 |
| `execute_target` | 同步 |  |

---

### 📄 modules\tools\services\exceute.py

- **文件大小**: 3.5 KB
- **代码行数**: 100

#### 导入依赖

```python
from __future__ import annotations
import asyncio
import inspect
import json
import time
from typing import Any
from typing import List
from models import CommandData
from models import CommandResult
from models import CommandStatus
```

#### 类定义

##### CLASS: CommandExecutor

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `execute` | 异步 |  |
| `_invoke` | 异步 |  |

##### CLASS: ResultFormatter

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_prompt` | 同步 |  |
| `to_json` | 同步 |  |
| `to_summary` | 同步 |  |
| `_truncate` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `execute` | 异步 |  |
| `_invoke` | 异步 |  |
| `to_prompt` | 同步 |  |
| `to_json` | 同步 |  |
| `to_summary` | 同步 |  |
| `_truncate` | 同步 |  |

---

### 📄 modules\tools\services\formatter.py

- **文件大小**: 8.6 KB
- **代码行数**: 246

#### 导入依赖

```python
from json import loads
import re
import shlex
from typing import Any
from typing import List
from typing import Optional
from tools.services.models import CommandData
from tools.services.models import CommandResult
from tools.services.models import CommandStatus
```

#### 类定义

##### CLASS: CommandParser

> 将 LLM 输出的多行文本解析为结构化命令列表。

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

| 方法 | 类型 | 说明 |
|------|------|------|
| `parse` | 同步 | 解析多行命令文本 → 命令字典列表 |
| `_looks_like_command` | 同步 | 快速判断一行是否像命令 |
| `_parse_line` | 同步 |  |
| `_parse_params` | 同步 |  |
| `_cast` | 同步 | 智能类型转换: str → int/float/bool/list/dict |

##### CLASS: CommandValidator

> 校验命令合法性:
    1. 服务是否注册
    2. 方法是否存在
    3. 必填参数是否齐全
    4. 参数类型是否匹配 (可选, 按 schema)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `validate` | 同步 | 返回与 commands 等长的检查结果列表。 |
| `_validate_one` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `parse` | 同步 | 解析多行命令文本 → 命令字典列表 |
| `_looks_like_command` | 同步 | 快速判断一行是否像命令 |
| `_parse_line` | 同步 |  |
| `_parse_params` | 同步 |  |
| `_cast` | 同步 | 智能类型转换: str → int/float/bool/list/dict |
| `__init__` | 同步 |  |
| `validate` | 同步 | 返回与 commands 等长的检查结果列表。 |
| `_validate_one` | 同步 |  |

---

### 📄 modules\tools\services\models.py

- **文件大小**: 1.0 KB
- **代码行数**: 38

#### 导入依赖

```python
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import TypedDict
```

#### 类定义

##### CLASS: CommandStatus(str, Enum)

##### CLASS: CommandData(TypedDict)

##### CLASS: CommandResult(TypedDict)

##### CLASS: OrchestrationState

##### CLASS: OrchestrationConfig(TypedDict)

---

### 📄 modules\tools\skills\manager.py

- **文件大小**: 5.2 KB
- **代码行数**: 149

#### 导入依赖

```python
from __future__ import annotations
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional
from typing import Set
import yaml
from manager.task.decorator import sync_task_scheduler
from logger import logger
from sandbox import RestrictedCodeExecutor
from models import ExternalSkill
from models import ExternalSkillMetadata
from models import SkillsManagerConfig
```

#### 类定义

##### CLASS: ExternalSkillManager

| 方法 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `load_from_directory` | 同步 |  |
| `_load_single_file` | 同步 |  |
| `activate_skill` | 同步 |  |
| `deactivate_skill` | 同步 |  |
| `reject_skill` | 同步 |  |
| `get_active_skills` | 同步 |  |
| `get_pending_skills` | 同步 |  |
| `get_skill` | 同步 |  |
| `list_skills` | 同步 |  |
| `build_prompt` | 同步 |  |
| `execute_skill` | 异步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__new__` | 同步 |  |
| `__init__` | 同步 |  |
| `load_from_directory` | 同步 |  |
| `_load_single_file` | 同步 |  |
| `activate_skill` | 同步 |  |
| `deactivate_skill` | 同步 |  |
| `reject_skill` | 同步 |  |
| `get_active_skills` | 同步 |  |
| `get_pending_skills` | 同步 |  |
| `get_skill` | 同步 |  |
| `list_skills` | 同步 |  |
| `build_prompt` | 同步 |  |
| `execute_skill` | 异步 |  |

---

### 📄 modules\tools\skills\models.py

- **文件大小**: 1.2 KB
- **代码行数**: 40

#### 导入依赖

```python
from dataclasses import dataclass
import re
from typing import List
from typing import Literal
from typing import Tuple
```

#### 类定义

##### CLASS: ExternalSkillMetadata

| 方法 | 类型 | 说明 |
|------|------|------|
| `validate` | 同步 |  |

##### CLASS: ExternalSkill

| 方法 | 类型 | 说明 |
|------|------|------|
| `get_description` | 同步 |  |

##### CLASS: SkillsManagerConfig

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `validate` | 同步 |  |
| `get_description` | 同步 |  |

---

### 📄 modules\tools\skills\sandbox.py

- **文件大小**: 5.2 KB
- **代码行数**: 138

#### 导入依赖

```python
from __future__ import annotations
import ast
import asyncio
import builtins
import contextlib
import io
import math
import random
import re
import time
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import Set
```

#### 类定义

##### CLASS: SandboxConfig

##### CLASS: CodeValidator

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `validate` | 同步 |  |
| `_validate_module` | 同步 |  |
| `_call_name` | 同步 |  |

##### CLASS: RestrictedCodeExecutor

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `execute` | 异步 |  |
| `execute_sync` | 同步 |  |
| `_safe_builtins` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `validate` | 同步 |  |
| `_validate_module` | 同步 |  |
| `_call_name` | 同步 |  |
| `__init__` | 同步 |  |
| `execute` | 异步 |  |
| `execute_sync` | 同步 |  |
| `_safe_builtins` | 同步 |  |

---

### 📄 modules\types\api.py

- **文件大小**: 0.3 KB
- **代码行数**: 15

#### 导入依赖

```python
from typing import Any
from typing import Optional
from pydantic import BaseModel
```

#### 类定义

##### CLASS: ConfigDescriptionItem(BaseModel)

##### CLASS: ServiceConfigDescription(BaseModel)

---

### 📄 modules\types\common.py

- **文件大小**: 1.2 KB
- **代码行数**: 59

#### 导入依赖

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any
from typing import Generic
from typing import Optional
from pydantic import BaseModel
from typing_extensions import ParamSpec
from typing_extensions import TypeVar
```

#### 类定义

##### CLASS: LLMProvider(str, Enum)

##### CLASS: BowserType(str, Enum)

##### CLASS: Role

| 方法 | 类型 | 说明 |
|------|------|------|
| `get_zh_name` | 同步 |  |

##### CLASS: Message

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_dict` | 同步 |  |

##### CLASS: TermColors

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_zh_name` | 同步 |  |
| `to_dict` | 同步 |  |

---

### 📄 modules\types\memory\context.py

- **文件大小**: 0.9 KB
- **代码行数**: 38

#### 导入依赖

```python
from __future__ import annotations
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any
from typing import Optional
from typing import TypedDict
from types.common import Role
```

#### 类定义

##### CLASS: Message

##### CLASS: TimeRange(TypedDict)

##### CLASS: CompressedContext

##### CLASS: MemoryContext(TypedDict)

---

### 📄 modules\types\memory\database.py

- **文件大小**: 1.1 KB
- **代码行数**: 45

#### 导入依赖

```python
from __future__ import annotations
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from enum import Enum
from typing import Any
from typing import Optional
import numpy as np
from context import TimeRange
from common import Role
```

#### 类定义

##### CLASS: Memory

##### CLASS: CompressedMemory

##### CLASS: MemoryStorgeData(Memory)

---

### 📄 modules\ui\app.py

- **文件大小**: 1.1 KB
- **代码行数**: 37

⚠️ **语法错误**:
```
invalid non-printable character U+FEFF (<unknown>, line 1)
```

---

### 📄 modules\ui\channel.py

- **文件大小**: 0.6 KB
- **代码行数**: 24

#### 导入依赖

```python
import platform
from PyQt5.QtWebChannel import QWebChannel
from api import common
from PyQt5.QtCore import pyqtSlot
```

#### 类定义

##### CLASS: API(QWebChannel)

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `open_folder` | 同步 |  |
| `get_service_config_list` | 同步 |  |
| `get_service_info_list` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `open_folder` | 同步 |  |
| `get_service_config_list` | 同步 |  |
| `get_service_info_list` | 同步 |  |

---

### 📄 modules\utils\audio.py

- **文件大小**: 0.5 KB
- **代码行数**: 16

#### 导入依赖

```python
from pathlib import Path
from typing import Union
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `read_audio` | 同步 |  |
| `write_audio` | 同步 |  |
| `write_audio_chunks` | 同步 |  |

---

### 📄 modules\utils\audio_stream.py

- **文件大小**: 3.4 KB
- **代码行数**: 111

#### 导入依赖

```python
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from typing import List
from typing import Optional
from typing import Tuple
from pydub import AudioSegment
```

#### 类定义

##### CLASS: AudioFormat

##### CLASS: AudioStreamDecoder

> 简易流式解码器：
- WAV: 解析 header 后直接输出 PCM
- MP3: 缓冲到一定大小后整体解码为 PCM

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_format` | 同步 |  |
| `feed` | 同步 |  |
| `_feed_wav` | 同步 |  |
| `_try_parse_wav_header` | 同步 |  |
| `_feed_mp3` | 同步 |  |
| `flush` | 同步 |  |
| `_decode_mp3_buffer` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get_format` | 同步 |  |
| `feed` | 同步 |  |
| `_feed_wav` | 同步 |  |
| `_try_parse_wav_header` | 同步 |  |
| `_feed_mp3` | 同步 |  |
| `flush` | 同步 |  |
| `_decode_mp3_buffer` | 同步 |  |

---

### 📄 modules\utils\class.py

- **文件大小**: 0.2 KB
- **代码行数**: 4

#### 导入依赖

```python
from typing import Any
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_all_methods` | 同步 |  |

---

### 📄 modules\utils\decorators.py

- **文件大小**: 4.1 KB
- **代码行数**: 125

⚠️ **语法错误**:
```
invalid non-printable character U+FEFF (<unknown>, line 1)
```

---

### 📄 modules\utils\file.py

- **文件大小**: 5.3 KB
- **代码行数**: 139

#### 导入依赖

```python
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
import os
from json import load
from json import dump
from json import JSONDecodeError
import yaml
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `check_file_exists` | 同步 |  |
| `ensure_file_exists` | 同步 |  |
| `read_json` | 同步 |  |
| `write_json` | 同步 |  |
| `read_markdown` | 同步 |  |
| `read_env` | 同步 |  |
| `write_env` | 同步 |  |
| `write_yaml` | 同步 |  |
| `read_yaml` | 同步 |  |
| `read_text` | 同步 |  |

---

### 📄 modules\utils\http.py

- **文件大小**: 7.2 KB
- **代码行数**: 207

#### 导入依赖

```python
from functools import wraps
import os
from pathlib import Path
from typing import Callable
from typing import Literal
from typing import Union
from typing import Optional
from typing import Union
from typing import Any
import httpx
from tqdm import tqdm
from inspect import iscoroutinefunction
from lxml import html
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `create_httpx_async_client` | 同步 |  |
| `create_httpx_sync_client` | 同步 |  |
| `http_exceptions` | 同步 |  |
| `download_file` | 异步 |  |
| `__parse_response` | 同步 |  |
| `get` | 同步 |  |
| `post` | 同步 |  |
| `async_post` | 异步 |  |
| `async_get` | 异步 |  |
| `decorator` | 同步 |  |
| `sync_wrapper` | 同步 |  |
| `async_wrapper` | 异步 |  |

---

### 📄 modules\utils\response.py

- **文件大小**: 1.8 KB
- **代码行数**: 68

#### 导入依赖

```python
from typing import Optional
from typing import TypeVar
from typing import Generic
from typing import Any
from dataclasses import dataclass
```

#### 类定义

##### CLASS: ResponseData(<ast.Subscript object at 0x0000024658504580>)

| 方法 | 类型 | 说明 |
|------|------|------|
| `to_json` | 同步 |  |

##### CLASS: CodeDefinition

##### CLASS: ResponseCode

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `success` | 同步 |  |
| `error` | 同步 |  |
| `not_found` | 同步 |  |
| `unknown_error` | 同步 |  |
| `to_json` | 同步 |  |

---

### 📄 modules\utils\util.py

- **文件大小**: 1.3 KB
- **代码行数**: 37

#### 导入依赖

```python
import time
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Mapping
from typing import Optional
from threading import Thread
from uuid import uuid4
from torch import cuda
```

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `get_device` | 同步 |  |
| `create_daemon_thread` | 同步 |  |
| `id_generator` | 同步 |  |
| `format_time` | 同步 |  |
| `any_to_str` | 同步 |  |

---

### 📄 test.py

- **文件大小**: 45.4 KB
- **代码行数**: 1248

#### 导入依赖

```python
import asyncio
import sys
import os
import time
import httpx
import os
import sys
from modules.context.audio import AudioContext
from datetime import datetime
from datetime import timedelta
import hashlib
import json
import re
from typing import Any
from typing import Dict
from typing import Generic
from typing import List
from typing import Optional
from typing import Callable
from typing import OrderedDict
# ... 还有 27 个导入
```

#### 类定义

##### CLASS: EnhancedLRUCache(<ast.Subscript object at 0x0000024658504A90>)

> 增强版LRU缓存，支持异步清理和批量操作

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `get` | 同步 |  |
| `put` | 同步 |  |
| `_periodic_cleanup` | 同步 | 定期清理过期条目 |
| `cleanup` | 同步 | 清理所有过期条目 |
| `get_stats` | 同步 |  |

##### CLASS: KeywordMatcher

> 高效的关键词匹配器，使用Trie树结构

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `build_from_keywords` | 同步 | 从关键词字典构建匹配器 |
| `_add_keyword` | 同步 | 向Trie树添加关键词 |
| `search_exact` | 同步 | 精确匹配搜索 |
| `search_regex` | 同步 | 正则表达式匹配搜索 |
| `search` | 同步 | 综合搜索，优先精确匹配 |

##### CLASS: ModernTypingDisplay(QWidget)

> 极简流式打字机显示组件 - 可拖动

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |
| `center_on_screen` | 同步 | 居中显示在屏幕上 |
| `_setup_ui` | 同步 | 设置UI布局 |
| `_apply_styles` | 同步 | 应用样式 |
| `resizeEvent` | 同步 | 调整大小事件 |
| `_format_text_with_gradient` | 同步 | 格式化文本为花字效果 |
| `display_text` | 同步 | 显示文字 - 流式输出 |
| `_type_next_chunk` | 同步 | 打字下一批字符 |
| `_finish_typing` | 同步 | 完成打字 |
| `_fade_and_hide` | 同步 | 淡出并隐藏 |
| `_on_fade_finished` | 同步 | 淡出完成 |
| `clear` | 同步 | 清除显示 |
| `skip_typing` | 同步 | 跳过打字动画 |
| `set_typing_speed` | 同步 | 设置打字速度 |
| `set_auto_clear_delay` | 同步 | 设置自动清除延迟 |
| `show_at_position` | 同步 | 在指定位置显示 |
| `mousePressEvent` | 同步 | 鼠标按下事件 - 开始拖动 |
| `mouseMoveEvent` | 同步 | 鼠标移动事件 - 拖动中 |
| `mouseReleaseEvent` | 同步 | 鼠标释放事件 - 结束拖动 |

##### CLASS: TrieNode

| 方法 | 类型 | 说明 |
|------|------|------|
| `__init__` | 同步 |  |

#### 函数定义

| 函数 | 类型 | 说明 |
|------|------|------|
| `test_connection` | 异步 | 测试QQ机器人连接 |
| `test_network` | 异步 | 测试网络连通性 |
| `test_webservice` | 同步 |  |
| `test_ui` | 同步 |  |
| `test_router` | 同步 |  |
| `test_html` | 异步 |  |
| `test_real_page` | 异步 |  |
| `test_compression_comparison` | 异步 | 对比不同页面的压缩效果 |
| `main` | 异步 |  |
| `simulate_stream` | 同步 |  |
| `__init__` | 同步 |  |
| `get` | 同步 |  |
| `put` | 同步 |  |
| `_periodic_cleanup` | 同步 | 定期清理过期条目 |
| `cleanup` | 同步 | 清理所有过期条目 |
| `get_stats` | 同步 |  |
| `__init__` | 同步 |  |
| `build_from_keywords` | 同步 | 从关键词字典构建匹配器 |
| `_add_keyword` | 同步 | 向Trie树添加关键词 |
| `search_exact` | 同步 | 精确匹配搜索 |
| `search_regex` | 同步 | 正则表达式匹配搜索 |
| `search` | 同步 | 综合搜索，优先精确匹配 |
| `__init__` | 同步 |  |
| `center_on_screen` | 同步 | 居中显示在屏幕上 |
| `_setup_ui` | 同步 | 设置UI布局 |
| `_apply_styles` | 同步 | 应用样式 |
| `resizeEvent` | 同步 | 调整大小事件 |
| `_format_text_with_gradient` | 同步 | 格式化文本为花字效果 |
| `display_text` | 同步 | 显示文字 - 流式输出 |
| `_type_next_chunk` | 同步 | 打字下一批字符 |
| `_finish_typing` | 同步 | 完成打字 |
| `_fade_and_hide` | 同步 | 淡出并隐藏 |
| `_on_fade_finished` | 同步 | 淡出完成 |
| `clear` | 同步 | 清除显示 |
| `skip_typing` | 同步 | 跳过打字动画 |
| `set_typing_speed` | 同步 | 设置打字速度 |
| `set_auto_clear_delay` | 同步 | 设置自动清除延迟 |
| `show_at_position` | 同步 | 在指定位置显示 |
| `mousePressEvent` | 同步 | 鼠标按下事件 - 开始拖动 |
| `mouseMoveEvent` | 同步 | 鼠标移动事件 - 拖动中 |
| `mouseReleaseEvent` | 同步 | 鼠标释放事件 - 结束拖动 |
| `__init__` | 同步 |  |

---

## 🔗 相关链接

- [项目主页](#)
- [API文档](#)
- [开发指南](#)

---

*此文档由 ProjectDocGenerator 自动生成*
