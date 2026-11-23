/**
 * 电脑端设备帧接线：把 device.* 事件喂给 stage store（蓝色 galgame 立绘层消费）。
 * 只注册一次，重连后回调仍有效；回灌自己的帧在此统一丢弃。
 */
import websocket from "@/api/websocket/index";
import { WebSocketEvent } from "@/typings/enums";
// import { useStageStore } from "@/stores/stage";

// type FrameHandler = (data: any, frame: WebSocketAPI.WebSocketResponse) => void;

// const handlers: Record<string, FrameHandler> = {
//   [WebSocketEvent.DEVICE_STAGE_EVENT]: (data, frame) => {
//     if (frame?.from_id && frame.from_id === websocket.clientId) return;
//     useStageStore().applyDeviceFrame(data);
//   },
//   [WebSocketEvent.DEVICE_PLAY_ANIMATION]: (data, frame) => {
//     if (frame?.from_id && frame.from_id === websocket.clientId) return;
//     useStageStore().applyDeviceFrame({ ...data, action: "play_animation" });
//   },
//   [WebSocketEvent.DEVICE_MODEL_SET]: (data, frame) => {
//     if (frame?.from_id && frame.from_id === websocket.clientId) return;
//     useStageStore().applyDeviceFrame({ ...data, action: "model_set" });
//   },
//   [WebSocketEvent.DEVICE_POSE]: (data, frame) => {
//     if (frame?.from_id && frame.from_id === websocket.clientId) return;
//     useStageStore().applyPose(data);
//   },
//   [WebSocketEvent.DEVICE_TEXT_INPUT]: (data, frame) => {
//     if (frame?.from_id && frame.from_id === websocket.clientId) return;
//     useStageStore().applyTextInput(data);
//   },
//   [WebSocketEvent.DEVICE_ASR_TEXT]: (data, frame) => {
//     if (frame?.from_id && frame.from_id === websocket.clientId) return;
//     useStageStore().applyTextInput({ ...data, source: "asr" });
//   },
// };

// let installed = false;

export function registerDeviceHandlers(): void {
  // if (installed) return;
  // installed = true;
  // Object.entries(handlers).forEach(([type, callback]) => {
  //   websocket.registerEventListener(type, callback);
  // });
}

export function unregisterDeviceHandlers(): void {
  // if (!installed) return;
  // Object.entries(handlers).forEach(([type, callback]) => {
  //   websocket.removeEventListener(type, callback);
  // });
  // installed = false;
}
