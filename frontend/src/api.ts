export const tg = window.Telegram?.WebApp;
export async function request(path: string, options: RequestInit = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "X-Telegram-Init-Data": tg?.initData || "", ...options.headers },
  });
  if (!response.ok) {
    let message = "Не удалось выполнить запрос. Попробуйте ещё раз.";
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : "Проверьте поля и введите один эмодзи.";
    } catch {}
    if (response.status === 401)
      message = "Сессия истекла. Откройте приложение заново из бота.";
    throw Error(message);
  }
  return response;
}
export async function json<T>(
  path: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  return (
    await request(
      path,
      body === undefined
        ? {}
        : {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
    )
  ).json();
}
interface Cached {
  created: number;
  size: number;
  url?: string;
  promise: Promise<string>;
}
const cache = new Map<string, Cached>();
const lanes = {
  foreground: { active: 0, waiting: [] as Array<() => void> },
  background: { active: 0, waiting: [] as Array<() => void> },
};
async function download(path: string) {
  const lane = /thumbnail|\/cover/.test(path)
    ? lanes.background
    : lanes.foreground;
  if (lane.active >= 2)
    await new Promise<void>((resolve) => lane.waiting.push(resolve));
  else lane.active++;
  try {
    return await (await request(path)).blob();
  } finally {
    const next = lane.waiting.shift();
    if (next) next();
    else lane.active--;
  }
}
export async function mediaURL(path: string) {
  let item = cache.get(path);
  if (item && Date.now() - item.created < 300000) return item.promise;
  if (item?.url) URL.revokeObjectURL(item.url);
  cache.delete(path);
  item = { created: Date.now(), size: 0, promise: Promise.resolve("") };
  const entry = item;
  entry.promise = (async () => {
    const blob = await download(path);
    entry.size = blob.size;
    entry.url = URL.createObjectURL(blob);
    let bytes = [...cache.values()].reduce((n, c) => n + c.size, 0);
    for (const [key, c] of cache) {
      if (cache.size <= 128 && bytes <= 100 * 1024 * 1024) break;
      if (key === path || !c.url) continue;
      bytes -= c.size;
      URL.revokeObjectURL(c.url);
      cache.delete(key);
    }
    return entry.url;
  })();
  cache.set(path, entry);
  try {
    return await entry.promise;
  } catch (e) {
    if (cache.get(path) === entry) cache.delete(path);
    throw e;
  }
}
export function invalidateCover(id: string) {
  const key = "/api/packs/" + id + "/cover",
    item = cache.get(key);
  cache.delete(key);
  if (item) void item.promise.then(URL.revokeObjectURL, () => {});
}
export function clearMedia() {
  for (const entry of cache.values())
    void entry.promise.then(URL.revokeObjectURL, () => {});
  cache.clear();
}
window.addEventListener("beforeunload", clearMedia);
