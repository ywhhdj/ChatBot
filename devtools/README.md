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

服务配置三态面板是 `docs/api.md §3.20` 的验收入口：
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
