import events from "..";

enum BackgroundEvent {
  Change = "background:change",
}

export function emitBackgroundChange(url: string, duration?: number) {
  events.emit(BackgroundEvent.Change, url, duration);
}

export function onBackgroundChange(
  callback: (url: string, duration?: number) => void
) {
  events.on(BackgroundEvent.Change, callback);
}

export function offBackgroundChange() {
  events.off(BackgroundEvent.Change);
}
