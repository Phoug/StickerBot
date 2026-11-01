import { afterEach, expect, it, vi } from "vitest";
import { clearMedia, mediaURL } from "./api";
afterEach(() => {
  clearMedia();
  vi.unstubAllGlobals();
});
it("opens active media while the thumbnail lane is saturated", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  vi.stubGlobal("URL", {
    createObjectURL: vi.fn(() => "blob:fixture"),
    revokeObjectURL: vi.fn(),
  });
  const fetch = vi.fn(async (path: string) => {
    if (path.includes("thumbnail")) await gate;
    return new Response(new Blob(["file"]));
  });
  vi.stubGlobal("fetch", fetch);
  const background = [0, 1, 2, 3, 4].map((i) =>
    mediaURL("/api/packs/p/thumbnail/" + i),
  );
  const foreground = mediaURL("/api/studio/media/source");
  expect(
    fetch.mock.calls.some(([path]) => path === "/api/studio/media/source"),
  ).toBe(true);
  await foreground;
  release();
  await Promise.all(background);
});
it("failed media requests can be retried", async () => {
  vi.stubGlobal("URL", {
    createObjectURL: () => "blob:ok",
    revokeObjectURL: () => {},
  });
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Retry" }), { status: 502 }),
    )
    .mockResolvedValueOnce(new Response(new Blob(["file"])));
  vi.stubGlobal("fetch", fetch);
  await expect(mediaURL("/retry")).rejects.toThrow("Retry");
  await expect(mediaURL("/retry")).resolves.toBe("blob:ok");
  expect(fetch).toHaveBeenCalledTimes(2);
});
