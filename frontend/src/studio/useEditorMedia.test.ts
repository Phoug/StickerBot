import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { mediaURL, sourceVideoURL } from "../api";
import { useEditorMedia } from "./useEditorMedia";

vi.mock("../api", () => ({ mediaURL: vi.fn(), sourceVideoURL: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.mocked(mediaURL).mockReset();
  vi.mocked(sourceVideoURL).mockReset();
});

it("keeps the Source loading until the first image or video frame is ready", async () => {
  vi.mocked(mediaURL).mockResolvedValue("blob:source");
  const { result } = renderHook(() => useEditorMedia({ id: "photo", kind: "photo", duration: 0 }));
  await waitFor(() => expect(result.current.url).toBe("blob:source"));
  expect(result.current.ready).toBe(false);
  act(() => result.current.onReady());
  expect(result.current.ready).toBe(true);
});

it("retries a failed Source request and clears its error", async () => {
  vi.mocked(mediaURL).mockRejectedValueOnce(Error("Connection lost")).mockResolvedValue("blob:retry");
  const { result } = renderHook(() => useEditorMedia({ id: "photo", kind: "photo", duration: 0 }));
  await waitFor(() => expect(result.current.failure).toBe("Connection lost"));
  act(() => result.current.retry());
  await waitFor(() => expect(result.current.url).toBe("blob:retry"));
  expect(result.current.failure).toBe("");
  expect(result.current.ready).toBe(false);
});

it("ignores a stale Source that finishes after another Source was selected", async () => {
  let resolve!: (url: string) => void;
  vi.mocked(mediaURL).mockImplementation((path) => path.includes("/first")
    ? new Promise<string>((done) => { resolve = done; })
    : Promise.resolve("blob:second"));
  const { result, rerender } = renderHook(({ id }) => useEditorMedia({ id, kind: "photo", duration: 0 }), {
    initialProps: { id: "first" },
  });
  rerender({ id: "second" });
  await waitFor(() => expect(result.current.url).toBe("blob:second"));
  await act(async () => resolve("blob:first"));
  expect(result.current.url).toBe("blob:second");
});

it("defers filmstrip decoding until the first frame and releases the decoder on exit", async () => {
  vi.mocked(sourceVideoURL).mockResolvedValue("/private/range-stream");
  const create = vi.spyOn(document, "createElement");
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const load = vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  const { result, unmount } = renderHook(() => useEditorMedia({ id: "video", kind: "video", duration: 3 }));
  await waitFor(() => expect(result.current.url).toBe("/private/range-stream"));
  expect(create.mock.calls.filter(([tag]) => tag === "video")).toHaveLength(0);
  expect(mediaURL).not.toHaveBeenCalled();
  expect(sourceVideoURL).toHaveBeenCalledWith("video");
  act(() => result.current.onReady());
  expect(create.mock.calls.filter(([tag]) => tag === "video")).toHaveLength(1);
  unmount();
  expect(pause).toHaveBeenCalledOnce();
  expect(load).toHaveBeenCalledOnce();
});


it("reuses a completed filmstrip when returning from Render Preview", async () => {
  vi.mocked(sourceVideoURL).mockResolvedValue("/private/filmstrip-stream");
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    drawImage: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/jpeg;base64,frame");
  const create = vi.spyOn(document, "createElement");
  const source = { id: "cached-filmstrip", kind: "video" as const, duration: 3 };
  const first = renderHook(() => useEditorMedia(source));
  await waitFor(() => expect(first.result.current.url).toBe("/private/filmstrip-stream"));
  act(() => first.result.current.onReady());
  const decoder = create.mock.results.find((_, i) => create.mock.calls[i][0] === "video")!.value as HTMLVideoElement;
  Object.defineProperty(decoder, "duration", { value: 3 });
  Object.defineProperty(decoder, "currentTime", {
    set() { queueMicrotask(() => decoder.dispatchEvent(new Event("seeked"))); },
  });
  await act(async () => decoder.dispatchEvent(new Event("loadedmetadata")));
  await waitFor(() => expect(first.result.current.frames).toHaveLength(16));
  first.unmount();
  const second = renderHook(() => useEditorMedia(source));
  await waitFor(() => expect(second.result.current.url).toBe("/private/filmstrip-stream"));
  act(() => second.result.current.onReady());
  await waitFor(() => expect(second.result.current.frames).toHaveLength(16));
  expect(create.mock.calls.filter(([tag]) => tag === "video")).toHaveLength(1);
});

it("ends a stalled first-frame wait and recovers when the user starts playback", async () => {
  vi.mocked(sourceVideoURL).mockResolvedValue("/private/stalled-stream");
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  const { result } = renderHook(() => useEditorMedia({ id: "stalled", kind: "video", duration: 3 }));
  await waitFor(() => expect(result.current.url).toBe("/private/stalled-stream"));
  vi.useFakeTimers();
  // Retry starts a new loading deadline.
  act(() => result.current.retry());
  await act(async () => {});
  act(() => vi.advanceTimersByTime(30000));
  expect(result.current.failure).toContain("Нажмите ▶");
  expect(result.current.ready).toBe(false);
  act(() => result.current.onReady());
  expect(result.current.ready).toBe(true);
  expect(result.current.failure).toBe("");
  vi.useRealTimers();
});
