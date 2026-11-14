import { computed, onScopeDispose, ref, shallowRef } from "vue";
import { pipelineService } from "@/api/services/pipeline";
import { registerEventListeners, unregisterAllEventListeners } from "@/api/websocket";
import notification from "@/utils/notification";
import {
  CAPABILITY_PRESETS,
  OFFLINE_DESCRIPTIONS,
  READONLY_ENDPOINT_KEYS,
  fieldLabel,
  isMaskedValue,
  isSecretKey,
} from "../../composables/modelPresets";

/** 详情缓存有效期：切回已读过的页签不重复打接口 */
const DETAIL_TTL = 60_000;
/** 单页最多展示的告警条数，避免后端长列表撑爆设置页 */
const MAX_WARNINGS = 5;

function safeMessage(error: unknown): string {
  const raw = (error as { message?: unknown } | null)?.message;
  if (typeof raw === "string" && raw.trim()) return raw.trim().slice(0, 160);
  return "请求未完成，请稍后重试";
}

function toEnum(raw: unknown): (string | number | Model.EnumOption)[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  return raw.map((item) => {
    if (item && typeof item === "object") {
      const o = item as Record<string, any>;
      return { value: o.value ?? o.id ?? "", label: String(o.label ?? o.value ?? o.id ?? "") };
    }
    return item as string | number;
  });
}

function typeDefault(type: Model.ParamType): Model.Value {
  switch (type) {
    case "boolean": return false;
    case "number":
    case "integer": return 0;
    case "array": return [];
    case "object": return {};
    default: return "";
  }
}

/**
 * 把 provider 描述（params / ui schema / model.params / config）压平成控件描述。
 * 只读端点字段与 hidden 字段不进入表单，也不参与提交。
 */
function buildFields(
  detail: Model.ProviderDetail | null,
  status: Model.ProviderStatus | null,
  modelId: string,
  offlineKeys: string[],
): Model.ParamSpec[] {
  const uiParams = status?.ui?.params;
  const rawParams =
    (status?.params && Object.keys(status.params).length ? status.params : null) ??
    (uiParams && typeof uiParams === "object" && Object.keys(uiParams).length ? uiParams : null) ??
    (status?.ui && Object.keys(status.ui).length ? status.ui : null) ??
    detail?.meta?.params ??
    null;

  const hintSource =
    (uiParams && typeof uiParams === "object" ? uiParams : null) ??
    (status?.ui && !status.ui.params ? status.ui : null) ??
    null;

  const source: Record<string, any> = rawParams && typeof rawParams === "object"
    ? { ...rawParams }
    : Object.fromEntries(offlineKeys.map((key) => [key, { type: "string" }]));

  if (!Object.keys(source).length) return [];

  const modelParams = (detail?.models ?? []).find((m) => m.id === modelId)?.params ?? {};
  const config = detail?.config ?? {};

  const out: Model.ParamSpec[] = [];
  for (const [key, value] of Object.entries(source)) {
    if (READONLY_ENDPOINT_KEYS.includes(key)) continue;

    const spec: Record<string, any> =
      value && typeof value === "object" && !Array.isArray(value) ? { ...value } : { type: "string" };
    const hint: Record<string, any> =
      hintSource && typeof hintSource[key] === "object" ? { ...hintSource[key] } : {};

    if (spec.hidden === true || hint.hidden === true) continue;

    const type: Model.ParamType = (spec.type ?? hint.type ?? "string") as Model.ParamType;
    const secret = isSecretKey(key) || spec.secret === true;
    const en = toEnum(spec.enum ?? hint.enum);
    const hasRange =
      typeof (spec.min ?? hint.min) === "number" &&
      typeof (spec.max ?? hint.max) === "number" &&
      typeof (spec.step ?? hint.step) === "number";

    let ui: Model.ParamSpec["ui"] = "text";
    if (secret) ui = "secret";
    else if (en?.length) ui = "select";
    else if (type === "boolean") ui = "boolean";
    else if (type === "object" || type === "array") ui = "json";
    else if ((type === "number" || type === "integer") && hasRange) ui = "slider";
    else if (type === "number" || type === "integer") ui = "number";
    if (spec.ui === "slider" || hint.ui === "slider") ui = "slider";
    if (spec.ui === "number" || hint.ui === "number") ui = "number";

    const fallbackDefault = modelParams[key]?.default;
    const configValue = config[key];
    const usableConfig =
      !secret && !isMaskedValue(configValue) && configValue !== undefined && configValue !== null
        ? configValue
        : undefined;
    const defaultValue =
      spec.default ?? hint.default ?? fallbackDefault ?? usableConfig ?? typeDefault(type);

    out.push({
      key,
      type,
      label: String(spec.label ?? hint.label ?? fieldLabel(key)),
      description: spec.description ?? hint.description,
      default: defaultValue,
      enum: en,
      min: spec.min ?? hint.min,
      max: spec.max ?? hint.max,
      step: spec.step ?? hint.step,
      required: spec.required === true || hint.required === true,
      scope: (spec.scope ?? hint.scope ?? "unknown") as Model.Scope,
      ui,
      secret,
      readonly: false,
    });
  }

  // 稳定顺序：required → init → request → 其它，减少切换 provider 时的视觉跳动
  const weight = (f: Model.ParamSpec) => (f.required ? 0 : f.scope === "init" ? 1 : f.scope === "request" ? 2 : 3);
  return out.sort((a, b) => weight(a) - weight(b) || a.key.localeCompare(b.key));
}

function offlineProvider(
  capability: Model.Capability,
  name: string,
): Model.OfflineProvider | undefined {
  return OFFLINE_DESCRIPTIONS[capability].providers.find((p) => p.name === name);
}

function normalizeProviders(
  capability: Model.Capability,
  list: Record<string, any> | null,
  adapters: Record<string, any> | null,
): Model.ProviderItem[] {
  const raw = Array.isArray(list?.providers) ? (list?.providers as any[]) : [];
  if (!raw.length) return [];

  const out: Model.ProviderItem[] = [];
  for (const item of raw) {
    const name = String(item?.name ?? "");
    if (!name) continue;
    const fb = offlineProvider(capability, name);
    const ids: string[] = Array.isArray(item.models)
      ? item.models.map((m: any) => (typeof m === "string" ? m : String(m?.id ?? ""))).filter(Boolean)
      : [];
    const models: Model.ModelItem[] = ids.length
      ? ids.map((id) => {
          const hit = fb?.models.find((m) => m.id === id);
          return { id, label: hit?.label ?? id, tags: hit?.tags };
        })
      : (fb?.models ?? []).map((m) => ({ ...m }));

    out.push({
      name,
      label: String(item?.label ?? fb?.label ?? name),
      deployment: item?.deployment ?? fb?.deployment,
      tags: fb?.tags ?? [],
      available: item?.available !== false,
      models,
      meta: fb
        ? { label: fb.label, tags: fb.tags, deployment: fb.deployment }
        : undefined,
      params: Object.fromEntries((fb?.params ?? []).map((key) => [key, { type: "string" }])),
    });
  }
  return out;
}

export function useModelProvider(capability: Model.Capability) {
  const preset = CAPABILITY_PRESETS[capability];
  /** 请求用的能力名；models/images.json 在部分版本里注册为 images */
  const adapterName = ref<string>(capability);

  const state = ref<Model.PageState>("loading");
  const pending = ref<Model.PendingAction>(null);
  const notice = ref<Model.Notice | null>(null);
  const offline = ref(false);

  const providers = shallowRef<Model.ProviderItem[]>([]);
  const activeProvider = ref("");
  const activeModel = ref("");
  const detail = shallowRef<Model.ProviderDetail | null>(null);
  const status = shallowRef<Model.ProviderStatus | null>(null);
  const usage = shallowRef<Model.AdapterUsage | null>(null);

  // 表单草稿：只存内存，不进 localStorage / Pinia persistence
  const values = ref<Record<string, Model.Value>>({});
  const secrets = ref<Record<string, string>>({});
  const changed = ref<Set<string>>(new Set());
  const dirty = ref(false);

  const downloadProgress = ref(0);
  const downloadPhase = ref("");

  let disposed = false;
  let revision = 0;
  let lastLoadedAt = 0;
  let rafId: number | null = null;
  let queuedProgress = 0;
  let queuedPhase = "";
  const inflight = new Map<string, Promise<void>>();
  const detailCache = new Map<string, { detail: Model.ProviderDetail | null; status: Model.ProviderStatus | null; at: number }>();

  const guard = (at: number) => !disposed && at === revision;

  const setNotice = (type: Model.Notice["type"], text: string) => {
    notice.value = { type, text };
  };

  const currentProvider = computed(() =>
    providers.value.find((p) => p.name === activeProvider.value) ?? null,
  );

  const models = computed<Model.ModelItem[]>(() => {
    const fromDetail = detail.value?.models;
    if (Array.isArray(fromDetail) && fromDetail.length) {
      return fromDetail.map((m: any) =>
        typeof m === "string" ? { id: m, label: m } : { ...m },
      ) as Model.ModelItem[];
    }
    return currentProvider.value?.models ?? [];
  });

  const offlineKeys = computed(() => {
    const fb = offlineProvider(capability, activeProvider.value);
    return fb?.params ?? [];
  });

  const fields = computed<Model.ParamSpec[]>(() =>
    buildFields(detail.value, status.value, activeModel.value, offlineKeys.value),
  );

  const maskedKeys = computed<string[]>(() => {
    const config = detail.value?.config ?? {};
    return Object.keys(config).filter((key) => isSecretKey(key) && isMaskedValue(config[key]));
  });

  const invalidFields = computed(() =>
    fields.value.filter((f) => {
      if (!f.required || f.secret) return false;
      const v = values.value[f.key];
      return v === "" || v === null || v === undefined;
    }),
  );

  const warnings = computed(() => {
    const list = [...(status.value?.warnings ?? []), ...(detail.value?.warnings ?? [])];
    return list.slice(0, MAX_WARNINGS).map(String);
  });

  const missingEnv = computed(() => (status.value?.missing_env ?? []).slice(0, MAX_WARNINGS).map(String));

  const isLocal = computed(() =>
    (status.value?.deployment ?? currentProvider.value?.deployment) === "local" ||
    !!status.value?.download,
  );

  const installed = computed(() => !!status.value?.download_status?.installed);

  const canApply = computed(() =>
    !offline.value &&
    (!!detail.value || !!status.value) &&
    !!activeProvider.value &&
    pending.value === null &&
    invalidFields.value.length === 0,
  );

  /** 只取一次默认值，之后完全由用户编辑驱动，不做 deep watch */
  const resetDraft = (list: Model.ParamSpec[]) => {
    const next: Record<string, Model.Value> = {};
    for (const f of list) next[f.key] = f.default;
    values.value = next;
    secrets.value = {};
    changed.value = new Set();
    dirty.value = false;
  };

  const setParam = (key: string, value: Model.Value) => {
    values.value = { ...values.value, [key]: value };
    const next = new Set(changed.value);
    next.add(key);
    changed.value = next;
    dirty.value = true;
  };

  const setSecret = (key: string, value: string) => {
    secrets.value = { ...secrets.value, [key]: value };
    dirty.value = true;
  };

  const loadDetail = (name: string, modelId?: string, force = false): Promise<void> => {
    const key = `${name}:${modelId ?? ""}`;
    const existing = inflight.get(key);
    if (existing) return existing;

    const cached = detailCache.get(key);
    if (!force && cached && Date.now() - cached.at < DETAIL_TTL) {
      detail.value = cached.detail;
      status.value = cached.status;
      return Promise.resolve();
    }

    const at = revision;
    const task = (async () => {
      const query = modelId ? { model_id: modelId } : undefined;
      const [detailResult, statusResult] = await Promise.allSettled([
        pipelineService.getProvider(adapterName.value, name, query),
        pipelineService.status(adapterName.value, name, query),
      ]);
      if (!guard(at)) return;

      const d = (detailResult.status === "fulfilled" ? detailResult.value : null) as Model.ProviderDetail | null;
      const s = (statusResult.status === "fulfilled" ? statusResult.value : null) as unknown as Model.ProviderStatus | null;
      detail.value = d;
      status.value = s;
      detailCache.set(key, { detail: d, status: s, at: Date.now() });

      if (!d && !s) {
        setNotice("warning", "模型描述读取失败，显示离线描述；请刷新重试");
      } else if (notice.value?.type === "warning" && notice.value.text.includes("读取失败")) {
        notice.value = null;
      }

      const chosen =
        modelId ||
        d?.selected_model ||
        s?.selected_model ||
        (d?.models?.[0] as any)?.id ||
        (currentProvider.value?.models?.[0]?.id ?? "");
      activeModel.value = typeof chosen === "string" ? chosen : "";
      resetDraft(buildFields(d, s, activeModel.value, offlineKeys.value));
    })();

    inflight.set(key, task);
    task.finally(() => inflight.delete(key));
    return task;
  };

  const load = async (force = false): Promise<void> => {
    if (!force && pending.value === "load" && providers.value.length) return;
    const at = ++revision;
    pending.value = "load";
    state.value = providers.value.length ? "ready" : "loading";
    notice.value = null;

    const [listResult, adapterResult] = await Promise.allSettled([
      pipelineService.listProviders(adapterName.value),
      pipelineService.listAdapters(),
    ]);
    if (!guard(at)) return;

    let list = listResult.status === "fulfilled" ? (listResult.value as Record<string, any>) : null;
    // 模型描述文件名（images.json）与能力名（image）不完全一致时，探测一次别名
    if (
      (!Array.isArray(list?.providers) || !list.providers.length) &&
      capability === "image" &&
      adapterName.value === "image"
    ) {
      try {
        const alt = await pipelineService.listProviders("images");
        if (Array.isArray(alt?.providers) && alt.providers.length) {
          adapterName.value = "images";
          list = alt as Record<string, any>;
        }
      } catch {
        // 保持原能力名，走离线描述骨架
      }
    }
    if (!guard(at)) return;

    const adapters = adapterResult.status === "fulfilled" ? (adapterResult.value as Record<string, any>) : null;
    const items = normalizeProviders(capability, list, adapters);
    const adapter = (adapters?.adapters?.[adapterName.value] ?? adapters?.adapters?.[capability]) as Record<string, any> | undefined;
    usage.value = adapter
      ? { current: adapter.current, model: adapter.model, initialized: adapter.initialized, usage: adapter.usage ?? {} }
      : null;

    if (!items.length) {
      // 接口未就绪：按 models/*.json 的离线描述铺出骨架，但不开放任何写操作
      const fb = OFFLINE_DESCRIPTIONS[capability].providers;
      providers.value = fb.map((p) => ({
        name: p.name,
        label: p.label,
        tags: p.tags,
        deployment: p.deployment,
        available: false,
        models: p.models.map((m) => ({ ...m })),
        offline: true,
        params: Object.fromEntries(p.params.map((key) => [key, { type: "string" }])),
      }));
      offline.value = true;
      detail.value = null;
      status.value = null;
      const preferred = activeProvider.value || fb[0]?.name || "";
      activeProvider.value = preferred;
      activeModel.value = providers.value.find((p) => p.name === preferred)?.models[0]?.id ?? "";
      resetDraft(buildFields(null, null, activeModel.value, offlineProvider(capability, preferred)?.params ?? []));
      state.value = "empty";
      setNotice("warning", "当前展示离线模型描述；连接后端后可切换与下载");
    } else {
      offline.value = false;
      providers.value = items;
      const preferred =
        items.find((p) => p.name === activeProvider.value)?.name ||
        (typeof adapter?.current === "string" ? items.find((p) => p.name === adapter.current)?.name : "") ||
        items[0].name;
      activeProvider.value = preferred;
      await loadDetail(preferred, undefined, force);
      if (!guard(at)) return;
      state.value = "ready";
    }

    lastLoadedAt = Date.now();
    if (!disposed && guard(at)) pending.value = null;
  };

  const refresh = async (): Promise<void> => {
    if (!activeProvider.value) return;
    for (const key of detailCache.keys()) {
      if (key.startsWith(`${activeProvider.value}:`)) detailCache.delete(key);
    }
    const at = ++revision;
    pending.value = "refresh";
    await loadDetail(activeProvider.value, activeModel.value || undefined, true);
    if (!guard(at)) return;
    lastLoadedAt = Date.now();
    pending.value = null;
  };

  /** KeepAlive 页签切回时的按需刷新，避免每次 activated 都打接口 */
  const refreshIfStale = () => {
    if (!lastLoadedAt || Date.now() - lastLoadedAt > DETAIL_TTL) void refresh();
  };

  const selectProvider = (name: string) => {
    if (name === activeProvider.value || pending.value) return;
    revision += 1;
    activeProvider.value = name;
    activeModel.value = "";
    void loadDetail(name);
  };

  const selectModel = (id: string) => {
    if (id === activeModel.value || pending.value) return;
    revision += 1;
    activeModel.value = id;
    void loadDetail(activeProvider.value, id, true);
  };

  const buildConfig = (): Record<string, any> => {
    const config: Record<string, any> = {};
    const specByKey = new Map(fields.value.map((f) => [f.key, f]));
    for (const key of changed.value) {
      const spec = specByKey.get(key);
      if (!spec || spec.secret || spec.readonly || READONLY_ENDPOINT_KEYS.includes(key)) continue;
      const value = values.value[key];
      if (value === undefined || value === null || value === "") continue;
      config[key] = value;
    }
    for (const [key, value] of Object.entries(secrets.value)) {
      if (value) config[key] = value;
    }
    return config;
  };

  const apply = async (): Promise<void> => {
    if (!canApply.value || !activeProvider.value) return;
    if (invalidFields.value.length) {
      setNotice("warning", `请先填写：${invalidFields.value.map((f) => f.label).join("、")}`);
      return;
    }
    pending.value = "apply";
    notice.value = null;
    try {
      await pipelineService.switch(adapterName.value, {
        provider: activeProvider.value,
        model_id: activeModel.value || undefined,
        config: buildConfig(),
      });
      detailCache.clear();
      secrets.value = {};
      changed.value = new Set();
      dirty.value = false;
      setNotice("success", `已切换到 ${currentProvider.value?.label ?? activeProvider.value}`);
      notification.showSuccess({ title: "模型配置", message: "切换已生效" });
      await refresh();
    } catch (error) {
      setNotice("error", safeMessage(error));
    } finally {
      if (!disposed) pending.value = null;
    }
  };

  const stop = async (): Promise<void> => {
    if (!activeProvider.value || pending.value) return;
    pending.value = "stop";
    notice.value = null;
    try {
      await pipelineService.stopAdapter(adapterName.value);
      detailCache.clear();
      setNotice("success", "已释放当前模型，能力门面保留");
      await refresh();
    } catch (error) {
      setNotice("error", safeMessage(error));
    } finally {
      if (!disposed) pending.value = null;
    }
  };

  const download = async (force = false): Promise<void> => {
    if (offline.value || !activeProvider.value || pending.value) return;
    pending.value = "download";
    notice.value = null;
    downloadPhase.value = "准备中";
    downloadProgress.value = 0;
    try {
      const result = await pipelineService.downloadModel(adapterName.value, activeProvider.value, {
        model_id: activeModel.value || undefined,
        force,
      });
      downloadPhase.value = result?.status === "running" ? "已有下载任务进行中" : "下载已开始";
      setNotice("info", "本地模型下载已开始，进度由后台事件推送");
    } catch (error) {
      downloadPhase.value = "";
      setNotice("error", safeMessage(error));
    } finally {
      if (!disposed) pending.value = null;
    }
  };

  // ---- 下载进度：事件归属过滤 + 一帧最多一次写入 ----
  const matchesDownload = (data: any): boolean => {
    if (!data || typeof data !== "object") return false;
    const capOk = (value: string) => value === capability || value === adapterName.value;
    if (data.capability && !capOk(String(data.capability))) return false;
    if (data.provider && data.provider !== activeProvider.value) return false;
    if (typeof data.model === "string" && data.model.includes(":")) {
      const [cap, provider] = data.model.split(":");
      if (!capOk(cap) || provider !== activeProvider.value) return false;
    }
    return true;
  };

  const queueProgress = (value: number, phase: string) => {
    queuedProgress = Math.max(0, Math.min(100, value));
    queuedPhase = phase;
    if (rafId !== null) return;
    rafId = requestAnimationFrame(() => {
      rafId = null;
      if (disposed) return;
      downloadProgress.value = queuedProgress;
      downloadPhase.value = queuedPhase;
    });
  };

  const onDownloadEvent = (kind: string, data: any) => {
    if (disposed || !matchesDownload(data)) return;
    const raw = Number(data?.progress ?? 0);
    const percent = raw > 0 && raw <= 1 ? raw * 100 : raw;
    switch (kind) {
      case "started":
        queueProgress(0, "开始下载");
        break;
      case "running":
        queueProgress(percent, data?.file ? `下载 ${data.file}` : "下载中");
        break;
      case "completed":
        queueProgress(100, "下载完成");
        setNotice("success", "本地模型下载完成");
        notification.showSuccess({ title: "模型下载", message: "模型文件已就绪" });
        detailCache.clear();
        void refresh();
        break;
      case "failed":
      case "error":
        queueProgress(0, "");
        setNotice("error", String(data?.message ?? "下载失败").slice(0, 160));
        break;
    }
  };

  const downloadListeners: Record<string, (data: any) => void> = {
    download_started: (d) => onDownloadEvent("started", d),
    download_running: (d) => onDownloadEvent("running", d),
    download_completed: (d) => onDownloadEvent("completed", d),
    download_failed: (d) => onDownloadEvent("failed", d),
    download_error: (d) => onDownloadEvent("error", d),
  };
  // KeepAlive 会缓存六个能力页；监听只在当前激活页注册，避免六份回调同时跑
  let listenersOn = false;
  const activate = () => {
    if (disposed || listenersOn) return;
    registerEventListeners(downloadListeners);
    listenersOn = true;
  };
  const deactivate = () => {
    if (!listenersOn) return;
    unregisterAllEventListeners(downloadListeners);
    listenersOn = false;
  };

  onScopeDispose(() => {
    disposed = true;
    revision += 1;
    deactivate();
    if (rafId !== null) cancelAnimationFrame(rafId);
    inflight.clear();
    detailCache.clear();
  });

  return {
    preset,
    state,
    pending,
    notice,
    offline,
    providers,
    activeProvider,
    activeModel,
    currentProvider,
    models,
    detail,
    status,
    usage,
    values,
    secrets,
    fields,
    maskedKeys,
    invalidFields,
    warnings,
    missingEnv,
    isLocal,
    installed,
    canApply,
    dirty,
    downloadProgress,
    downloadPhase,
    load,
    refresh,
    refreshIfStale,
    selectProvider,
    selectModel,
    setParam,
    setSecret,
    apply,
    stop,
    download,
    activate,
    deactivate,
  };
}
