let hideTimer: number | null = null; // 通知的定时器

// const notificationDebounceMap = new Map<string, number>()
const DEBOUNCE_MS_NETWORK = 10000; // "未注明的错误" 10秒
const DEBOUNCE_MS_DEFAULT = 3000;
class Notification {
  public isVisible = ref(false);
  public title = ref("");
  public type = ref<UI.NotificationType>("info");
  public avatarUrl = ref("");
  public message = ref("");
  public duration = ref(3000);

  private hideTimer: number | null = null;
  private lastFingerprint: string | null = null; // 上次显示的消息指纹
  private lastShowTime = 0; // 上次显示的时间戳
  private readonly DEBOUNCE_MS_DEFAULT = 3500; // 默认展示时长
  private readonly DEBOUNCE_MS_NETWORK_ERROR = 8000; // “未知错误”防刷时长
  private readonly MIN_INTERVAL = 500; // 同一指纹最小间隔（防闪烁）

  /**
   * 生成消息指纹，用于去重
   */
  private getFingerprint(opts: UI.NotificationOptions): string {
    return `${opts.type}|${opts.title}|${opts.message}`;
  }

  showNotification(options: UI.NotificationOptions) {
    const now = Date.now();
    const fingerprint = this.getFingerprint(options);
    if (
      fingerprint === this.lastFingerprint &&
      now - this.lastShowTime < this.MIN_INTERVAL
    ) {
      if (this.hideTimer) {
        clearTimeout(this.hideTimer);
        this.hideTimer = null;
      }
      const duration = this.calcDuration(options);
      this.hideTimer = window.setTimeout(
        () => this.hideNotification(),
        duration
      );
      return;
    }
    if (this.hideTimer) {
      clearTimeout(this.hideTimer);
      this.hideTimer = null;
    }

    this.title.value = options.title ?? "";
    this.type.value = options.type ?? "info";
    this.avatarUrl.value = options.avatarUrl ?? "/static/icons/chatbot.ico";
    this.message.value = options.message;
    this.duration.value = options.duration ?? this.DEBOUNCE_MS_DEFAULT;

    this.lastFingerprint = fingerprint;
    this.lastShowTime = now;

    this.isVisible.value = true;

    const duration = this.calcDuration(options);
    if (duration > 0) {
      this.hideTimer = window.setTimeout(
        () => this.hideNotification(),
        duration
      );
    }
  }

  private calcDuration(options: UI.NotificationOptions): number {
    const isNetworkError =
      options.type === "error" && options.message === "未知错误";
    return isNetworkError
      ? this.DEBOUNCE_MS_NETWORK_ERROR
      : options.duration ?? this.DEBOUNCE_MS_DEFAULT;
  }

  hideNotification() {
    this.isVisible.value = false;
    if (this.hideTimer) {
      clearTimeout(this.hideTimer);
      this.hideTimer = null;
    }
  }

  showError(opts: Omit<UI.NotificationOptions, "type">) {
    this.showNotification({ ...opts, type: "error" });
  }
  showSuccess(opts: Omit<UI.NotificationOptions, "type">) {
    this.showNotification({ ...opts, type: "success" });
  }
  showWarning(opts: Omit<UI.NotificationOptions, "type">) {
    this.showNotification({ ...opts, type: "warning" });
  }
  showInfo(opts: Omit<UI.NotificationOptions, "type">) {
    this.showNotification({ ...opts, type: "info" });
  }
}
const notification = new Notification();
export default notification;
