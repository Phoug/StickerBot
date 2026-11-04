import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { mediaURL } from "../api";
import { useEditorMedia } from "./useEditorMedia";

vi.mock("../api", () => ({ mediaURL: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.mocked(mediaURL).mockReset();
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
  vi.mocked(mediaURL).mockResolvedValue("blob:video");
  const create = vi.spyOn(document, "createElement");
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const load = vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  const { result, unmount } = renderHook(() => useEditorMedia({ id: "video", kind: "video", duration: 3 }));
  await waitFor(() => expect(result.current.url).toBe("blob:video"));
  expect(create.mock.calls.filter(([tag]) => tag === "video")).toHaveLength(0);
  act(() => result.current.onReady());
  expect(create.mock.calls.filter(([tag]) => tag === "video")).toHaveLength(1);
  unmount();
  expect(pause).toHaveBeenCalledOnce();
  expect(load).toHaveBeenCalledOnce();
});
