import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";
import { json, request, tg } from "../api";
import { trim, Editor, cropOverflow } from "../studio/Editor";
vi.mock("../api", () => ({
  tg: {
    initData: "test",
    ready: vi.fn(),
    expand: vi.fn(),
    BackButton: {
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn(),
      offClick: vi.fn(),
    },
  },
  json: vi.fn(),
  request: vi.fn(),
  mediaURL: vi.fn(async () => "blob:fixture"),
  invalidateCover: vi.fn(),
  clearMedia: vi.fn(),
}));
const pack = {
  id: "p",
  title: "Реакции",
  name: "test_by_bot",
  status: "ready",
  count: 2,
  stickers: [
    { id: "a", emoji: "🙂", preview_id: "ta" },
    { id: "b", emoji: "🔥", preview_id: "tb", is_video: true },
  ],
};
beforeEach(() => {
  vi.clearAllMocks();
  window.scrollTo = vi.fn();
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  vi.mocked(json).mockImplementation(async (path) =>
    path === "/api/packs"
      ? { packs: [structuredClone(pack)] }
      : structuredClone(pack),
  );
  vi.mocked(request).mockResolvedValue(new Response(null, { status: 204 }));
});
afterEach(cleanup);

function telegramBack() {
  const listener = vi.mocked(tg!.BackButton!.onClick).mock.calls.at(-1)![0];
  act(() => listener());
}

it("publishes a Studio render and opens the updated Pack order", async () => {
  let published = false;
  const current = () =>
    published
      ? {
          ...pack,
          count: 3,
          stickers: [
            ...pack.stickers,
            { id: "new", emoji: "🙂", preview_id: "tn" },
          ],
        }
      : structuredClone(pack);
  vi.mocked(json).mockImplementation(async (path) => {
    if (path === "/api/packs") return { packs: [structuredClone(pack)] };
    if (path === "/api/studio/link")
      return { id: "source", kind: "photo", duration: 0 };
    if (path === "/api/studio/render")
      return { id: "render", kind: "photo", duration: 0 };
    if (path.endsWith("/publish")) published = true;
    return current();
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Добавить стикер" }),
  );
  fireEvent.change(document.getElementById("video-link")!, {
    target: { value: "https://example.com/photo.png" },
  });
  fireEvent.submit(document.getElementById("link-form")!);
  const renderButton = await screen.findByRole("button", {
    name: /Посмотреть результат/,
  });
  await waitFor(() =>
    expect((renderButton as HTMLButtonElement).disabled).toBe(false),
  );
  fireEvent.click(renderButton);
  fireEvent.click(
    await screen.findByRole("button", { name: "Добавить в набор" }),
  );
  await screen.findByLabelText("Эмодзи стикера 3");
  expect(json).toHaveBeenCalledWith("/api/studio/packs/p/publish", {
    render_id: "render",
    emoji: "🙂",
    replace_id: null,
  });
});

it("Telegram back closes viewing before leaving the order draft", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Редактировать" }));
  fireEvent.change(screen.getByLabelText("Эмодзи стикера 1"), {
    target: { value: "🥹" },
  });
  fireEvent.click(screen.getByLabelText("Посмотреть стикер 1"));
  telegramBack();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(
    (screen.getByLabelText("Эмодзи стикера 1") as HTMLInputElement).value,
  ).toBe("🥹");
  telegramBack();
  expect(screen.queryByLabelText("Эмодзи стикера 1")).toBeNull();
  expect(screen.getByRole("heading", { name: "Реакции" })).toBeTruthy();
});

it("keeps the order draft when opening a replacement fails", async () => {
  vi.mocked(json).mockImplementation(async (path) => {
    if (path.endsWith("/edit")) throw Error("Редактор временно недоступен");
    return path === "/api/packs"
      ? { packs: [structuredClone(pack)] }
      : structuredClone(pack);
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Редактировать" }));
  fireEvent.change(screen.getByLabelText("Эмодзи стикера 1"), {
    target: { value: "🥹" },
  });
  fireEvent.click(screen.getByLabelText("Посмотреть стикер 1"));
  fireEvent.click(screen.getByRole("button", { name: "Редактировать" }));
  await screen.findByRole("alert");
  expect(
    (screen.getByLabelText("Эмодзи стикера 1") as HTMLInputElement).value,
  ).toBe("🥹");
});

it("returns from replacement editing to the same order draft", async () => {
  vi.mocked(json).mockImplementation(async (path) => {
    if (path.endsWith("/edit"))
      return { id: "photo", kind: "photo", duration: 0 };
    return path === "/api/packs"
      ? { packs: [structuredClone(pack)] }
      : structuredClone(pack);
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Редактировать" }));
  fireEvent.change(screen.getByLabelText("Эмодзи стикера 1"), {
    target: { value: "🥹" },
  });
  fireEvent.click(screen.getByLabelText("Посмотреть стикер 1"));
  fireEvent.click(screen.getByRole("button", { name: "Редактировать" }));
  await screen.findByRole("heading", { name: "Редактор фото" });
  telegramBack();
  expect(
    (screen.getByLabelText("Эмодзи стикера 1") as HTMLInputElement).value,
  ).toBe("🥹");
});
describe("React page flows", () => {
  it("opens a pack, changes emoji and saves order", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Редактировать" }),
    );
    fireEvent.change(screen.getByLabelText("Эмодзи стикера 1"), {
      target: { value: "🥹" },
    });
    fireEvent.keyDown(screen.getByLabelText("Перетащить стикер 1"), {
      key: "ArrowDown",
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(json).toHaveBeenCalledWith(
        "/api/packs/p/order",
        { sticker_ids: ["b", "a"] },
        "PUT",
      ),
    );
    expect(json).toHaveBeenCalledWith(
      "/api/packs/p/stickers/a/emoji",
      { emoji: "🥹" },
      "PUT",
    );
  });
  it("requires confirmation before deletion", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Удалить набор" }),
    );
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Оставить набор" }));
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Удалить набор" }));
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/api/packs/p", {
        method: "DELETE",
      }),
    );
  });
  it("viewer displays inline video without native controls", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
    fireEvent.click(await screen.findByLabelText("Посмотреть стикер 2"));
    await waitFor(() =>
      expect(document.querySelector("dialog video")).not.toBeNull(),
    );
    const video = document.querySelector("dialog video") as HTMLVideoElement;
    expect(video.controls).toBe(false);
    expect(video.playsInline).toBe(true);
    expect(video.loop).toBe(true);
    fireEvent.click(screen.getByLabelText("Закрыть просмотр"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("unsubscribes Telegram back navigation on unmount", async () => {
    const view = render(<App />);
    await screen.findByRole("button", { name: /Реакции/ });
    view.unmount();
    expect(tg?.BackButton?.offClick).toHaveBeenCalled();
  });
});
it("trimming preserves bounds and a maximum duration of three seconds", () => {
  expect(trim(10, 13, 60, "right", 100)).toEqual([10, 13]);
  expect(trim(10, 13, 60, "move", 100)).toEqual([57, 60]);
  expect(trim(10, 13, 60, "left", -100)).toEqual([10, 13]);
});

it("does not access private API outside Telegram", async () => {
  const sdk = tg!;
  const previous = sdk.initData;
  sdk.initData = "";
  try {
    render(<App />);
    expect(json).not.toHaveBeenCalled();
    expect(
      (
        screen.getByRole("button", {
          name: "Создать стикерпак",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  } finally {
    sdk.initData = previous;
  }
});

it("shows saved import and allows retry after a Telegram error", async () => {
  let attempts = 0;
  vi.mocked(json).mockImplementation(async (path, body) => {
    if (path === "/api/packs")
      return body
        ? { ...pack, status: "import_pending", stickers: [] }
        : { packs: [] };
    if (path.endsWith("/import")) {
      if (++attempts === 1) throw Error("Временная ошибка Telegram");
      return pack;
    }
    return {
      ...pack,
      status: attempts > 1 ? "ready" : "import_pending",
      stickers: [],
    };
  });
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Создать стикерпак" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "По ссылке" }));
  fireEvent.change(document.getElementById("pack-title")!, {
    target: { value: "Копия" },
  });
  fireEvent.change(document.getElementById("pack-link")!, {
    target: { value: "https://t.me/addstickers/Original" },
  });
  fireEvent.submit(document.getElementById("pack-form")!);
  const retry = await screen.findByRole("button", {
    name: "Продолжить импорт",
  });
  await screen.findByRole("alert");
  fireEvent.click(retry);
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Продолжить импорт" }),
    ).toBeNull(),
  );
  expect(attempts).toBe(2);
});

it("opens linked photo carousels without treating audio as a source", async () => {
  vi.mocked(json).mockImplementation(async (path) =>
    path === "/api/packs"
      ? { packs: [pack] }
      : path === "/api/studio/link"
        ? {
            kind: "album",
            photos: [
              {
                id: "photo1",
                kind: "photo",
                duration: 0,
                width: 640,
                height: 400,
              },
              {
                id: "photo2",
                kind: "photo",
                duration: 0,
                width: 640,
                height: 400,
              },
            ],
          }
        : pack,
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Добавить стикер" }),
  );
  fireEvent.change(document.getElementById("video-link")!, {
    target: { value: "https://tiktok.com/@test/photo/123" },
  });
  fireEvent.submit(document.getElementById("link-form")!);
  await screen.findByRole("heading", { name: "Выберите фото" });
  const photo = await screen.findByAltText("Фото 2");
  fireEvent.click(photo);
  await screen.findByRole("heading", { name: "Редактор фото" });
  expect(screen.queryByRole("tab", { name: "Фрагмент" })).toBeNull();
  expect(json).toHaveBeenCalledWith("/api/studio/link", {
    url: "https://tiktok.com/@test/photo/123",
  });
});

it("locks Telegram minimization gestures only while editing", () => {
  const sdk = tg!;
  sdk.disableVerticalSwipes = vi.fn();
  sdk.enableVerticalSwipes = vi.fn();
  const view = render(
    <Editor
      source={{
        id: "photo",
        kind: "photo",
        duration: 0,
        width: 640,
        height: 400,
      }}
      edit={{
        source_id: "photo",
        start: 0,
        end: 1,
        shape: "original",
        zoom: 1,
        x: 0.5,
        y: 0.5,
      }}
      onChange={() => {}}
      onRender={() => {}}
      busy={false}
    />,
  );
  expect(sdk.disableVerticalSwipes).toHaveBeenCalledOnce();
  view.unmount();
  expect(sdk.enableVerticalSwipes).toHaveBeenCalledOnce();
});

it("cropping preserves artwork proportions at every canvas shape and zoom", () => {
  for (const [w, h] of [
    [640, 360],
    [360, 640],
    [512, 512],
  ])
    for (const ratio of [1, w / h])
      for (const zoom of [1, 1.5, 3]) {
        const overflow = cropOverflow(w, h, ratio, zoom);
        expect(((1 + overflow.x) * ratio) / (1 + overflow.y)).toBeCloseTo(
          w / h,
          8,
        );
        expect(overflow.x).toBeGreaterThanOrEqual(0);
        expect(overflow.y).toBeGreaterThanOrEqual(0);
      }
});

it("keeps Telegram swipe protection during ordering and nested viewing", async () => {
  const sdk = tg!;
  sdk.disableVerticalSwipes = vi.fn();
  sdk.enableVerticalSwipes = vi.fn();
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Редактировать" }));
  expect(sdk.disableVerticalSwipes).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByLabelText("Посмотреть стикер 1"));
  fireEvent.click(screen.getByLabelText("Закрыть просмотр"));
  expect(sdk.enableVerticalSwipes).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
  expect(sdk.enableVerticalSwipes).toHaveBeenCalledOnce();
});

it("shows play/pause feedback only after a tap and hides it afterwards", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Реакции/ }));
  fireEvent.click(await screen.findByLabelText("Посмотреть стикер 2"));
  const toggle = await screen.findByRole("button", { name: "Пауза" });
  expect(document.querySelector(".playback-flash")).toBeNull();
  const video = document.querySelector("dialog video") as HTMLVideoElement;
  video.play = vi.fn().mockResolvedValue(undefined);
  video.pause = vi.fn();
  fireEvent.click(toggle);
  expect(document.querySelector(".playback-flash")).not.toBeNull();
  await waitFor(
    () => expect(document.querySelector(".playback-flash")).toBeNull(),
    { timeout: 1500 },
  );
});
