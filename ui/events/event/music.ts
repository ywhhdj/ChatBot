import events from "..";

enum MusicEvent {
  Play = "music:play",
  Pause = "music:pause",
  Progress = "music:progress",
  VolumeChange = "music:volumeChange",
}

export function emitMusicPlay(url?: string) {
  events.emit(MusicEvent.Play, url);
}

export function emitMusicPause() {
  events.emit(MusicEvent.Pause);
}

export function emitMusicProgress(progress: number, url?: string) {
  events.emit(MusicEvent.Progress, progress, url);
}

export function emitMusicVolumeChange(volume: number) {
  events.emit(MusicEvent.VolumeChange, volume);
}

export function onMusicPlay(callback: (url?: string) => void) {
  events.on(MusicEvent.Play, callback);
}

export function onMusicPause(callback: () => void) {
  events.on(MusicEvent.Pause, callback);
}

export function onMusicProgress(
  callback: (progress: number, url?: string) => void
) {
  events.on(MusicEvent.Progress, callback);
}

export function onMusicVolumeChange(callback: (volume: number) => void) {
  events.on(MusicEvent.VolumeChange, callback);
}

export function offMusicPlay() {
  events.off(MusicEvent.Play);
}

export function offMusicPause() {
  events.off(MusicEvent.Pause);
}

export function offMusicProgress() {
  events.off(MusicEvent.Progress);
}

export function offMusicVolumeChange() {
  events.off(MusicEvent.VolumeChange);
}
