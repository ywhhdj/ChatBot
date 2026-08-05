import HttpUtil from "@/utils/http";

export async function getHistory(params?: string[][] | Record<string, string> | string | URLSearchParams, callback?: (data: HistoryItems) => void) {
  const query: Record<string, string> = {};
  if (params && typeof params === 'object' && !Array.isArray(params) && !(params instanceof URLSearchParams)) {
    Object.assign(query, params);
  }
  const res = await HttpUtil.get<HistoryItems>('/history', query);
  if (res) {
    if (callback) {
      return callback(res);
    }
    return res;
  }
}
