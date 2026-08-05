import { registerEventListeners, unregisterAllEventListeners, websocket } from "@/events/event/websocket";
import http from "@/utils/http";

export async function getLLMProviderList() {
  return await http.get('/llm-provider');
}

export async function getTTSProviderList() {
  return await http.get('/tts-provider');
}

export async function getModelConfig(provider?: string) {
  return await http.get(`/model/config?provider=${provider}`);
}
