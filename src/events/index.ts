class EventBus {
  private events: Record<string, (...args: any[]) => void> = {};

  on(type: string, callback: (...args: any[]) => void) {
    this.events[type] = callback;
  }
  emit(type: string, ...args: any[]) {
    this.events[type]?.(...args);
  }
  off(type: string) {
    delete this.events[type];
  }
}
const events = new EventBus();
export default events;
