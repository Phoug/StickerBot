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

it("loads the visible filmstrip after the first frame without another video decoder", async () => {
  vi.mocked(sourceVideoURL).mockResolvedValue("/private/range-stream");
  vi.mocked(mediaURL).mockResolvedValue("blob:filmstrip");
  const create = vi.spyOn(document, "createElement");
  const { result } = renderHook(() => useEditorMedia({ id: "video", kind: "video", duration: 120 }, 4, 6));
  await waitFor(() => expect(result.current.url).toBe("/private/range-stream"));
  expect(mediaURL).not.toHaveBeenCalled();
  act(() => result.current.onReady());
  await waitFor(() => expect(result.current.filmstrip).toBe("blob:filmstrip"));
  expect(mediaURL).toHaveBeenCalledWith("/api/studio/media/video/filmstrip?start=4&span=6");
  expect(create.mock.calls.filter(([tag]) => tag === "video")).toHaveLength(0);
});

it("ignores stale filmstrip responses after the visible window changes", async () => {
  let resolve!: (url: string) => void;
  vi.mocked(sourceVideoURL).mockResolvedValue("/private/range-stream");
  vi.mocked(mediaURL).mockImplementation((path) => path.includes("start=0&")
    ? new Promise<string>((done) => { resolve = done; })
    : Promise.resolve("blob:later-window"));
  const { result, rerender } = renderHook(({ start }) =>
    useEditorMedia({ id: "video", kind: "video", duration: 120 }, start, 12), {
      initialProps: { start: 0 },
    });
  await waitFor(() => expect(result.current.url).toBe("/private/range-stream"));
  act(() => result.current.onReady());
  await waitFor(() => expect(mediaURL).toHaveBeenCalledOnce());
  rerender({ start: 12 });
  await waitFor(() => expect(result.current.filmstrip).toBe("blob:later-window"));
  await act(async () => resolve("blob:stale-window"));
  expect(result.current.filmstrip).toBe("blob:later-window");
});

it("retries filmstrip failure without reloading or disabling the editable Source", async () => {
  vi.mocked(sourceVideoURL).mockResolvedValue("/private/range-stream");
  vi.mocked(mediaURL).mockRejectedValueOnce(Error("Busy")).mockResolvedValue("blob:recovered");
  const { result } = renderHook(() => useEditorMedia({ id: "video", kind: "video", duration: 3 }));
  await waitFor(() => expect(result.current.url).toBe("/private/range-stream"));
  act(() => result.current.onReady());
  await waitFor(() => expect(result.current.filmstripFailure).toBe(true));
  expect(result.current.ready).toBe(true);
  expect(result.current.failure).toBe("");
  act(() => result.current.retryFilmstrip());
  await waitFor(() => expect(result.current.filmstrip).toBe("blob:recovered"));
  expect(result.current.filmstripFailure).toBe(false);
  expect(sourceVideoURL).toHaveBeenCalledOnce();
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
