# AI Companion API 文档

## 概述

本文档描述了 AI Companion 项目的所有 API 接口。基础 URL 为 `http://localhost:8000/api`。

## 通用响应格式

所有 API 响应遵循统一格式：
```json
{
"code": 200,
"message": "success",
"data": {},
"timestamp": 1623456789
}
```
### 错误码说明

| 错误码 | 描述 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 404 | 资源未找到 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## 1. 系统管理 API

### 1.1 获取系统状态

获取系统各组件运行状态。

**Endpoint:** `GET /api/system/status`

**请求示例：**
bash
curl http://localhost:8000/api/system/status
**响应示例：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "server": "running",
    "memory_usage": 45.2,
    "cpu_usage": 23.1,
    "active_connections": 3,
    "services": {
      "live2d": "running",
      "voice": "stopped"
    },
    "uptime": 3600
  }
}
```
---

## 2. LLM 配置 API

### 2.1 设置 LLM 配置

配置大语言模型的连接参数。

**Endpoint:** `PUT /api/llm/setConfig`

**请求体：**
```json
{
  "model": "gpt-4",
  "apiKey": "sk-xxxxxxxxxxxx",
  "apiBaseURL": "https://api.openai.com/v1"
}
```
**字段说明：**

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| model | string | 否 | 模型名称 |
| apiKey | string | 否 | API密钥 |
| apiBaseURL | string | 否 | API基础URL |

**响应示例：**
json
{
"code": 200,
"message": "LLM configuration updated successfully",
"data": true
}
纯文本
### 2.2 获取 LLM 配置

**Endpoint:** `GET /api/llm/getConfig`

**响应示例：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "model": "gpt-4",
    "apiKey": "sk-****",
    "apiBaseURL": "https://api.openai.com/v1"
  }
}
```
---

## 3. 文件操作 API

### 3.1 打开文件夹

在文件管理器中打开指定文件夹。

**Endpoint:** `GET /api/open-folder/{folder_path}`

**路径参数：**

| 参数 | 类型 | 描述 |
|------|------|------|
| folder_path | string | 文件夹路径（URL编码） |

**请求示例：**
bash
curl "http://localhost:8000/api/open-folder/C%3A%5CUsers%5Cuser%5CDocuments"
纯文本
**响应示例：**
```json
{
  "code": 200,
  "message": "Folder opened successfully",
  "data": true
}
```
---

## 4. 聊天 API

### 4.1 发送聊天消息

向 AI 发送一条消息并获取回复。

**Endpoint:** `POST /api/chat/message`

**请求体：**
```json
{
  "message": "你好，今天天气怎么样？",
  "session_id": "session_123456",
  "context": {
    "mode": "conversation",
    "personality": "friendly"
  }
}
```
**字段说明：**

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| message | string | 是 | 用户消息内容 |
| session_id | string | 否 | 会话ID，不传则创建新会话 |
| context | object | 否 | 上下文配置 |

**响应示例：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "reply": "你好！很高兴见到你。关于今天的天气，我建议你查看天气预报应用获取实时信息哦！",
    "session_id": "session_123456",
    "emotion": "happy",
    "timestamp": 1623456789
  }
}
```
### 4.2 获取聊天历史

获取指定会话的聊天记录。

**Endpoint:** `GET /api/chat/history?session_id={session_id}&limit={limit}&offset={offset}`

**查询参数：**

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| session_id | string | 是 | 会话ID |
| limit | integer | 否 | 返回条数，默认50 |
| offset | integer | 否 | 偏移量，默认0 |

**响应示例：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
  "messages": [
      {
        "role": "user",
        "content": "你好",
        "timestamp": 1623456700
      },
      {
        "role": "assistant",
        "content": "你好！有什么可以帮助你的吗？",
        "timestamp": 1623456701,
        "emotion": "happy"
      }
    ],
    "total": 100,
    "has_more": true
  }
}
```
---

## 5. 情感分析 API

### 5.1 分析情感

分析文本的情感倾向。

**Endpoint:** `POST /api/emotion/analyze`

**请求体：**
json
{
"text": "今天真是太开心了！",
"detail": false
}
纯文本
**字段说明：**

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| text | string | 是 | 要分析的文本 |
| detail | boolean | 否 | 是否返回详细分析 |

**响应示例（简单模式）：**
json
{
"code": 200,
"message": "success",
"data": {
"emotion": "happy",
"confidence": 0.95
}
}
纯文本
**响应示例（详细模式）：**
json
{
"code": 200,
"message": "success",
"data": {
"emotion": "happy",
"confidence": 0.92,
"details": {
"happy": 0.85,
"neutral": 0.08,
"sad": 0.03,
"angry": 0.02,
"surprised": 0.05
},
"keywords": ["开心", "太"]
}
}
纯文本
---

## 6. 语音 API

### 6.1 文本转语音

将文本转换为语音音频。

**Endpoint:** `POST /api/voice/text-to-speech`

**请求体：**
json
{
"text": "你好，欢迎使用AI助手",
"voice": "female",
"speed": 1.0,
"format": "wav"
}
纯文本
**字段说明：**

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| text | string | 是 | 要转换的文本 |
| voice | string | 否 | 音色，可选：female/male，默认female |
| speed | float | 否 | 语速，范围0.5-2.0，默认1.0 |
| format | string | 否 | 音频格式，可选：wav/mp3/ogg，默认wav |

**响应：**
- Content-Type: audio/wav
- Body: 二进制音频数据

### 6.2 语音转文本

将语音音频转换为文本。

**Endpoint:** `POST /api/voice/speech-to-text`

**请求体：**
- Content-Type: multipart/form-data
- 字段: audio (文件)

**响应示例：**
json
{
"code": 200,
"message": "success",
"data": {
"text": "你好，欢迎使用AI助手",
"confidence": 0.98,
"duration": 2.5
}
}
纯文本
---

## 7. 服务管理 API

### 7.1 启动 Live2D 服务

**Endpoint:** `POST /api/services/live2d/start`

**请求体：**
json
{
"model_path": "/path/to/model.model3.json",
"window_size": [1200, 800]
}
纯文本
**响应示例：**
json
{
"code": 200,
"message": "Live2D service started successfully",
"data": {
"service_id": "live2d",
"status": "running"
}
}
纯文本
### 7.2 停止 Live2D 服务

**Endpoint:** `POST /api/services/live2d/stop`

**响应示例：**
```json
{
  "code": 200,
  "message": "Live2D service stopped successfully",
  "data": {
  "service_id": "live2d",
  "status": "stopped"
  }
}
```
### 7.3 关闭 Live2D 服务

**Endpoint:** `POST /api/services/live2d/close`

**响应示例：**
```json
{
"code": 200,
"message": "Live2D service closed successfully",
"data": {
"service_id": "live2d",
"status": "closed"
}
}
```
---

## 8. WebSocket API

### 8.1 WebSocket 连接

建立实时双向通信连接。

**Endpoint:** `WS /api/ws`

**客户端发送消息格式：**
```json
{
"type": "message",
"message": "你好",
"to": "client_id" // 可选，私信目标
}
```
**消息类型：**

| 类型 | 描述 |
|------|------|
| message | 普通消息 |
| private | 私信 |
| heartbeat | 心跳检测 |
| emotion_update | 情感状态更新 |
| live2d_action | Live2D动作控制 |

**服务器推送消息格式：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "type": "message",
    "from": "client_id",
    "data": "回复内容",
    "timestamp": 1623456789
  }
}
```
**心跳机制：**
- 客户端每30秒发送一次心跳
- 服务端响应 `{"type": "pong"}`
- 超过60秒无心跳视为断开连接

---

## 错误响应示例

### 400 Bad Request
```json
{
"code": 400,
"message": "Invalid parameter: message field is required",
"data": null
}
```
### 500 Internal Server Error
```json
{
"code": 500,
"message": "Internal server error occurred",
"data": null
}
```