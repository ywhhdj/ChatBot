# ChatBot DevTools

开发态调试页：**纯静态、零依赖、不参与业务、不注册任何后端路由**。

> ⚠️ 本目录**不随包分发**。禁止把这里的文件复制进 `static/`、`web/`，
> 也不要给它加 Vite 构建入口。

## 打开方式

```bash
npm run devtools          # 等价于 vite --open /devtools/index.html
# 或先 npm run dev，再访问：
# http://localhost:5173/devtools/index.html
```

页面默认把 `API Base` 设为 `/api`（同源），由 `vite.config.ts` 的
`server.proxy` 转发到 `127.0.0.1:8000`；如果后端不在 8000，改页面顶部输入框即可。
`WS Base` 默认推导到 `ws://<host>:8000/`（后端 WebSocket 路由是 `/`，不受 CORS 约束）。

生产包里没有这个目录：`RuntimePath.get_web_resources_dir()` 指向 `static/`，
`StaticFiles` 只挂载该目录；Vite build 的唯一入口是 `web/main.ts`，产物写回 `static/`。

## 面板

| 面板 | 做什么 |
|---|---|
| 概览 | `/api/catalog` 端点总数、能力域、方法分布、最近 12 次请求（含 `X-Request-ID` 与耗时） |
| 端点浏览器 | 124 个端点按 op / 路径 / 分组 / 方法过滤，点击填入请求编辑器 |
| 请求调试 | 自定义 method / path / query / body，展示状态码、耗时、关联 ID 与原始响应 |
| 性能压测 | 指定端点、并发、总数，统计成功率、RPS、p50/p75/p90/p95/p99、错误分布 |
| 功能冒烟 | 批量跑只读 GET 端点出表格；写操作默认不执行，勾选后才跑且仍有黑名单 |
| 服务配置三态 | 可视化 `get_config` → `update_config`（`pending=true`）→ `apply_config`（`pending=false`） |
| SSE / WS | SSE 首帧延迟 / 帧数 / 事件序列；WS 连接、心跳、收发帧 |
| 插件 | 对齐 AIRI DevTools plugin-host 的 Registry View（manifest / 路径 / enabled / loaded / state / missing）与 Capability Matrix；支持目录 / zip 安装、启用、停用、热重载、卸载 |
| Live2D / Galgame | 立绘状态与性能、鼠标视线折线、表情/动作/情绪、EnhancedDialogueComponent 台词与回看、配置三态验收、离线自检与真实服务冒烟 |

插件面板是 `docs/api.md §3.24` 的验收入口：安装后必须看到 `enabled=false` / `state=not_loaded`，显式启用才变 `active`；禁用 `builtin-services` 后依赖它的第三方插件应自动回 `pending`。

## Live2D 面板怎么测（§3.25）

**不需要启动 live2d 服务也能验的部分**：

1. 点「离线自检 18 例」→ 调 `POST /api/live2d/test/suite`，覆盖视线、动捕回落、
   待机演出、口型闭合、性能自适应、打字机与标点停顿、队列、回看、QSS/XSS、
   存档三态；与 `python src/tests/test_live2d.py` 同一套用例。
2. 在轨迹框里改 `[[nx,ny],…]` 点「画视线曲线」→ 调 `POST /api/live2d/test/gaze`，
   蓝线 `ParamAngleX`（头转）、金线 `ParamEyeBallX`（眼球）。这是纯逻辑模拟，
   **不碰 Qt / OpenGL / GPU**。

**需要服务已启动的部分**：

3. 点「启动服务」（等于 `POST /api/service/live2d/start`），模型加载后状态卡片变 `READY`。
4. 表情 / 动作 / 情绪 / 说话 / 眨眼 / 复位按钮逐项点，看立绘反应与右下角动作日志。
5. 推送台词 → 观察打字机、名称框、等待指示器；再点跳过 / 推进 / 清空，看对话框状态与回看表。
6. 配置三态：勾掉「无动捕跟随鼠标」、改打字速度与帧率 → **① 只保存**
   （`pending=true`、运行态不变）→ **② 显式应用**（`on_config_change` 热应用，
   `restart:false`，不重启服务）。
7. 点「真实服务冒烟」→ 自动跑 status → gaze → expression → motion → emotion →
   dialogue → skip → backlog → status，逐步给 ok/detail。

> 表情 / 动作 id 必须来自你自己的 `.model3.json`；不存在的 id 会被引擎静默过滤，
> 这是设计而不是 bug。完整 112 项设置的分组见 `GET /api/live2d/settings`。

服务配置三态面板是 `docs/api.md §3.22` 的验收入口：
② 保存后 `active_config` 必须保持不变；③ 应用后才 `config == active_config`。
面板里的 apply 用 `restart=false`，避免调试时重启真实服务。

## 打包排除（三重保证）

1. **构建入口**：`vite.config.ts` 的 `rollupOptions.input` 只有 `web/main.ts`，
   `build.outDir = static`。`devtools/` 既不是入口也不在 `static/`，不进 bundle。
2. **资源复制**：`scripts/builds/steps/nuitka.py::_data_dirs` 只显式 include
   `skills` / `static` / `resources`；`scripts/builds/config.py` 的
   `EXCLUDED_DIR_NAMES` 含 `devtools`，`copy_tree()` 会跳过同名目录；
   `DEVTOOLS_DIR` / `DEVTOOLS_DIR_NAME` 是唯一常量源。
3. **部署后自检**：`scripts/builds/steps/resources.py::assert_devtools_excluded()`
   扫描安装目录与 `static/`，发现 `devtools` 目录或 `/devtools/` 路由痕迹直接
   `raise RuntimeError`，让构建失败。`scripts/builds/build.py` 在部署完成后调用。

`.gitignore` 里另有 `static/devtools/` 兜底，防止有人误把调试页放进步被打包的目录。

## 安全口径

- 只调用**现有契约端点**，不新增 op、不改 `endpoints.json`。
- 默认只发 `GET`；性能压测与冒烟的写操作需手动开启，且冒烟有 `SMOKE_DENY`
  黑名单（启停服务、切换 provider、删除存档、应用配置等）。
- `compat.*` 是原生 OpenAI 协议端点，不带统一信封；页面同时兼容两种响应形态。
- 调试页不做鉴权、不存 token，仅供本机开发时使用。
