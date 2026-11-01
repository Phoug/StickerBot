import { Playback } from "./Playback";
import { useSwipeLock } from "./useSwipeLock";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  json,
  request,
  mediaURL,
  tg,
  invalidateCover,
  clearMedia,
} from "./api";
import type { Album, Edit, Media, Pack, Sticker } from "./types";
import { ImageAsset, Icon, Modal } from "./ui";
import { Editor } from "./Editor";
import icons from "./icons.svg?raw";
type Screen =
  "home" | "new" | "pack" | "source" | "album" | "editor" | "preview";
export default function App() {
  const [screen, setScreen] = useState<Screen>("home"),
    [packs, setPacks] = useState<Pack[]>([]),
    [pack, setPack] = useState<Pack | null>(null),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [importing, setImporting] = useState(false),
    [source, setSource] = useState<Media | null>(null),
    [album, setAlbum] = useState<Album | null>(null),
    [edit, setEdit] = useState<Edit | null>(null),
    [render, setRender] = useState<Media | null>(null),
    [replacing, setReplacing] = useState<Sticker | null>(null),
    [order, setOrder] = useState<string[] | null>(null),
    [emojis, setEmojis] = useState<Record<string, string>>({}),
    [viewer, setViewer] = useState<number | null>(null),
    [deleting, setDeleting] = useState<Sticker | "pack" | null>(null),
    [fullscreen, setFullscreen] = useState(
      !!tg?.requestFullscreen &&
        !tg.isFullscreen &&
        (!tg.isVersionAtLeast || tg.isVersionAtLeast("8.0")),
    );
  const lock = useRef(false),
    renderCache = useRef<{ key: string; media: Media } | null>(null),
    drag = useRef<{
      id: string;
      pointer: number;
      y: number;
      grab: number;
    } | null>(null),
    list = useRef<HTMLDivElement>(null),
    orderRef = useRef(order);
  orderRef.current = order;
  useSwipeLock(order !== null || viewer !== null);
  const rowPositions = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    if (!order) {
      rowPositions.current.clear();
      return;
    }
    const rows = [...(list.current?.children || [])] as HTMLElement[];
    for (const row of rows) {
      const id = row.dataset.stickerId!,
        before = rowPositions.current.get(id),
        delta = before === undefined ? 0 : before - row.offsetTop;
      if (
        delta &&
        drag.current?.id !== id &&
        !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
      ) {
        row.getAnimations?.().forEach((a) => a.cancel());
        row.animate?.(
          [
            { transform: `translateY(${delta}px)` },
            { transform: "translateY(0)" },
          ],
          { duration: 200, easing: "cubic-bezier(.2,.8,.2,1)" },
        );
      }
      rowPositions.current.set(id, row.offsetTop);
    }
  }, [order]);
  const task = async (label: string, fn: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Не удалось выполнить операцию",
      );
    } finally {
      lock.current = false;
      setBusy("");
    }
  };
  const home = async () => {
    const result = await json<{ packs: Pack[] }>("/api/packs");
    setPacks(result.packs);
    setOrder(null);
    setAlbum(null);
    setSource(null);
    setScreen("home");
  };
  const open = async (id: string) => {
    const p = await json<Pack>("/api/packs/" + id);
    setPack(p);
    setOrder(null);
    setEmojis({});
    setScreen("pack");
    return p;
  };
  const select = (s: Media) => {
    setSource(s);
    setEdit({
      source_id: s.id,
      start: 0,
      end: s.kind === "photo" ? 1 : Math.min(3, s.duration),
      shape: "original",
      zoom: 1,
      x: 0.5,
      y: 0.5,
    });
    setRender(null);
    renderCache.current = null;
    setScreen("editor");
  };
  const back = useCallback(() => {
    if (lock.current) return;
    if (deleting) {
      setDeleting(null);
      return;
    }
    if (viewer !== null) {
      setViewer(null);
      return;
    }
    if (order) {
      setOrder(null);
      return;
    }
    setError("");
    if (screen === "preview") setScreen("editor");
    else if (screen === "editor")
      setScreen(replacing ? "pack" : album ? "album" : "source");
    else if (screen === "album") setScreen("source");
    else if (screen === "source") setScreen("pack");
    else void task("Загрузка…", home);
  }, [screen, deleting, viewer, order, replacing, album]);
  useEffect(() => {
    tg?.ready();
    tg?.expand();
    try {
      tg?.setHeaderColor?.("#1f1f1f");
      tg?.setBackgroundColor?.("#1f1f1f");
    } catch {}
    if (tg?.initData) void task("Загружаем наборы…", home);
    return clearMedia;
  }, []);
  useEffect(() => {
    tg?.BackButton?.onClick(back);
    if (screen === "home" && viewer === null && !deleting)
      tg?.BackButton?.hide();
    else tg?.BackButton?.show();
    return () => tg?.BackButton?.offClick?.(back);
  }, [back, screen, viewer, deleting]);
  useEffect(() => {
    const update = () => {
      const root = document.documentElement;
      root.style.setProperty(
        "--app-height",
        (tg?.viewportStableHeight ||
          window.visualViewport?.height ||
          innerHeight) + "px",
      );
      for (const edge of ["top", "bottom", "left", "right"] as const) {
        if (tg?.safeAreaInset)
          root.style.setProperty(
            "--device-" + edge,
            tg.safeAreaInset[edge] + "px",
          );
        if (tg?.contentSafeAreaInset)
          root.style.setProperty(
            "--content-" + edge,
            tg.contentSafeAreaInset[edge] + "px",
          );
      }
    };
    update();
    const events = [
      "viewportChanged",
      "safeAreaChanged",
      "contentSafeAreaChanged",
      "fullscreenChanged",
    ];
    events.forEach((e) => tg?.onEvent?.(e, update));
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    return () => {
      events.forEach((e) => tg?.offEvent?.(e, update));
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
    };
  }, []);
  useEffect(() => {
    const editing = screen === "editor" || screen === "preview";
    document.body.classList.toggle("editing", editing);
    document.body.classList.toggle("in-telegram", !!tg?.initData);
    document.body.classList.toggle("viewing", viewer !== null);
    return () => {
      document.body.classList.remove("editing", "viewing");
    };
  }, [screen, viewer]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [screen]);
  const [dragging, setDragging] = useState("");
  useEffect(() => {
    if (!drag.current) return;
    let frame = 0;
    const move = (y: number) => {
      const d = drag.current,
        current = orderRef.current;
      if (!d || !current || !list.current) return;
      d.y = y;
      const floating = list.current.querySelector<HTMLElement>(
        `[data-sticker-id="${d.id}"]`,
      );
      if (floating)
        floating.style.transform = `translateY(${y - d.grab - list.current.getBoundingClientRect().top - floating.offsetTop}px)`;
      const rows = [...list.current.children] as HTMLElement[],
        from = current.indexOf(d.id);
      let to = from;
      const top = list.current.getBoundingClientRect().top;
      rows.forEach((row, i) => {
        const mid = top + row.offsetTop + row.offsetHeight / 2;
        if (i > from && y > mid + 8) to = i;
        if (i < from && y < mid - 8 && to === from) to = i;
      });
      if (to !== from) {
        const next = [...current];
        next.splice(to, 0, next.splice(from, 1)[0]);
        orderRef.current = next;
        setOrder(next);
        tg?.HapticFeedback?.selectionChanged?.();
      }
    };
    const pointer = (e: PointerEvent) => {
      if (e.pointerId !== drag.current?.pointer) return;
      e.preventDefault();
      move(e.clientY);
    };
    const end = (event?: PointerEvent | Event) => {
      if (
        event &&
        "pointerId" in event &&
        event.pointerId !== drag.current?.pointer
      )
        return;
      const row = list.current?.querySelector<HTMLElement>(".is-dragging");
      if (row) {
        const transform = row.style.transform;
        row.style.transform = "";
        if (
          transform &&
          !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
        )
          row.animate?.([{ transform }, { transform: "translateY(0)" }], {
            duration: 160,
            easing: "ease-out",
          });
      }
      drag.current = null;
      setDragging("");
      cancelAnimationFrame(frame);
    };
    const scroll = () => {
      if (!drag.current) return;
      const y = drag.current.y,
        bottom =
          document.getElementById("order-actions")?.getBoundingClientRect()
            .top || innerHeight;
      if (y < 120) window.scrollBy(0, -Math.min(12, (120 - y) / 4));
      else if (y > bottom - 24)
        window.scrollBy(0, Math.min(12, (y - bottom + 24) / 4));
      move(y);
      frame = requestAnimationFrame(scroll);
    };
    frame = requestAnimationFrame(scroll);
    window.addEventListener("pointermove", pointer, { passive: false });
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    window.addEventListener("blur", end);
    return () => {
      end();
      window.removeEventListener("pointermove", pointer);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      window.removeEventListener("blur", end);
    };
  }, [dragging]);
  const saveOrder = () =>
    void task("Сохраняем изменения…", async () => {
      if (!pack || !order) return;
      try {
        for (const [id, emoji] of Object.entries(emojis)) {
          if (!emoji.trim()) throw Error("Введите один эмодзи.");
          await json(
            "/api/packs/" +
              pack.id +
              "/stickers/" +
              encodeURIComponent(id) +
              "/emoji",
            { emoji: emoji.trim() },
            "PUT",
          );
        }
        await json(
          "/api/packs/" + pack.id + "/order",
          { sticker_ids: order },
          "PUT",
        );
      } catch (e) {
        await open(pack.id);
        throw e;
      }
      invalidateCover(pack.id);
      await open(pack.id);
    });
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Tab")
        document.body.classList.add("keyboard-navigation");
    };
    const pointer = () => document.body.classList.remove("keyboard-navigation");
    document.addEventListener("keydown", keyboard);
    document.addEventListener("pointerdown", pointer);
    return () => {
      document.removeEventListener("keydown", keyboard);
      document.removeEventListener("pointerdown", pointer);
    };
  }, []);
  const swipe = useRef({ x: 0, y: 0, moved: false });
  const [viewerDirection, setViewerDirection] = useState(1);
  const navigateViewer = (index: number) => {
    if (!pack || viewer === null) return;
    const next = Math.max(0, Math.min(pack.stickers.length - 1, index));
    if (next === viewer) return;
    setViewerDirection(next > viewer ? 1 : -1);
    setViewer(next);
  };
  const active = pack && viewer !== null ? pack.stickers[viewer] : null;
  const workspace = screen === "editor" || screen === "preview";
  return (
    <>
      <div dangerouslySetInnerHTML={{ __html: icons }} />
      <main
        id="app-shell"
        className={"shell " + (workspace ? "is-editor" : "")}
      >
        <header className="topbar">
          <button
            id="back"
            className={"icon-button " + (screen === "home" ? "hidden" : "")}
            onClick={back}
            aria-label="Назад"
          >
            <Icon name="back" />
          </button>
          <a
            className="brand"
            href="#home"
            onClick={(e) => {
              e.preventDefault();
              void task("Загрузка…", home);
            }}
          >
            <Icon name="sticker" />
            Sticker Studio
          </a>
        </header>
        {error && (
          <div id="error" className="notice" role="alert">
            {error}
          </div>
        )}
        {!tg?.initData && (
          <div id="auth-notice" className="notice">
            Откройте приложение из Telegram-бота.
          </div>
        )}
        {screen === "home" && (
          <section id="home" className="screen">
            <div className="collection-hero">
              <span className="studio-mark">
                <Icon name="sticker" />
              </span>
              <h1>Мои стикеры</h1>
              <p>
                Создавайте стикеры из фото и видео
                <br />и собирайте свои наборы.
              </p>
            </div>
            {packs.length > 0 && (
              <>
                <div className="section-heading">
                  <h2>
                    Наборы <span className="counter">{packs.length}</span>
                  </h2>
                </div>
                <button
                  id="create"
                  className="action-row"
                  onClick={() => {
                    setImporting(false);
                    setScreen("new");
                  }}
                >
                  <Icon name="plus" />
                  Создать набор стикеров
                </button>
              </>
            )}
            <div id="packs" className="pack-grid">
              {packs.map((p) => (
                <button
                  key={p.id}
                  className="pack-card"
                  onClick={() =>
                    void task("Открываем набор…", async () => {
                      await open(p.id);
                    })
                  }
                >
                  <span className="pack-symbol">
                    {p.status === "ready" ? (
                      <ImageAsset path={"/api/packs/" + p.id + "/cover"} />
                    ) : (
                      <Icon name="sticker" />
                    )}
                  </span>
                  <strong>{p.title}</strong>
                  <small>
                    {p.status === "draft"
                      ? "Черновик"
                      : p.status === "import_pending"
                        ? "Импорт не завершён"
                        : p.count + " стикеров"}
                  </small>
                </button>
              ))}
            </div>
            {!packs.length && (
              <div id="empty" className="empty">
                <h2>Начните с первого набора</h2>
                <p>Соберите фото и видео или перенесите готовый набор.</p>
                <button
                  id="create-empty"
                  className="button"
                  disabled={!tg?.initData}
                  onClick={() => {
                    setImporting(false);
                    setScreen("new");
                  }}
                >
                  Создать стикерпак
                </button>
              </div>
            )}
          </section>
        )}
        {screen === "new" && (
          <section id="new" className="screen">
            <h1>Новый набор</h1>
            <div className="segmented">
              <button
                className={!importing ? "selected" : ""}
                onClick={() => setImporting(false)}
              >
                С нуля
              </button>
              <button
                className={importing ? "selected" : ""}
                onClick={() => setImporting(true)}
              >
                По ссылке
              </button>
            </div>
            <form
              id="pack-form"
              onSubmit={(e) => {
                e.preventDefault();
                const data = new FormData(e.currentTarget);
                void task("Создаём набор…", async () => {
                  const p = await json<Pack>("/api/packs", {
                    title: String(data.get("title")).trim(),
                    source: importing ? String(data.get("link")).trim() : null,
                  });
                  setPack({ ...p, stickers: [] });
                  if (importing) {
                    try {
                      await json("/api/packs/" + p.id + "/import", {});
                    } catch (e) {
                      await open(p.id);
                      throw e;
                    }
                  }
                  await open(p.id);
                });
              }}
            >
              <label>
                Название набора
                <input id="pack-title" name="title" required maxLength={64} />
              </label>
              {importing && (
                <>
                  <label>
                    Ссылка на набор
                    <input id="pack-link" name="link" type="url" required />
                  </label>
                  <p className="hint">
                    Создадим редактируемую копию с новой ссылкой.
                  </p>
                  <label className="check">
                    <input type="checkbox" required />
                    Это мой набор или у меня есть разрешение на копирование.
                  </label>
                </>
              )}
              <button className="button wide" type="submit">
                Создать {importing ? "копию" : "набор"}
              </button>
            </form>
          </section>
        )}
        {screen === "pack" && pack && (
          <section id="pack" className="screen">
            <div className="pack-hero">
              <div className="pack-cover">
                {pack.status === "ready" && (
                  <ImageAsset path={"/api/packs/" + pack.id + "/cover"} />
                )}
              </div>
              <h1>{pack.title}</h1>
            </div>
            <p id="current-info" className="intro">
              {pack.status === "draft"
                ? "Черновик. Добавьте первый стикер."
                : pack.status === "import_pending"
                  ? "Копия ещё не готова. Продолжите импорт."
                  : pack.count + " стикеров · фото и видео"}
            </p>
            {pack.status === "ready" && (
              <a
                className="action-row"
                id="telegram-link"
                target="_blank"
                rel="noopener"
                href={"https://t.me/addstickers/" + pack.name}
              >
                <Icon name="external" />
                Открыть в Telegram
              </a>
            )}
            <div className="pack-actions">
              {pack.status === "import_pending" ? (
                <button
                  id="resume-import"
                  className="button"
                  onClick={() =>
                    void task("Продолжаем импорт…", async () => {
                      await json("/api/packs/" + pack.id + "/import", {});
                      await open(pack.id);
                    })
                  }
                >
                  Продолжить импорт
                </button>
              ) : (
                <button
                  id="add-sticker"
                  className="action-row"
                  disabled={pack.count >= 120}
                  onClick={() => {
                    setReplacing(null);
                    setAlbum(null);
                    setScreen("source");
                  }}
                >
                  <Icon name="plus" />
                  Добавить стикер
                </button>
              )}
            </div>
            <div className="section-heading">
              <h2>Стикеры</h2>
              {!order && pack.stickers.length > 0 && (
                <button
                  id="edit-stickers"
                  className="button secondary compact-button"
                  onClick={() => {
                    setEmojis({});
                    setOrder(pack.stickers.map((s) => s.id));
                  }}
                >
                  Редактировать
                </button>
              )}
            </div>
            {order && (
              <p className="hint">Перетаскивайте стикеры и меняйте эмодзи.</p>
            )}
            <div
              id="stickers"
              ref={list}
              className={"sticker-grid " + (order ? "sticker-list" : "")}
            >
              {(order || pack.stickers.map((s) => s.id)).map((id, index) => {
                const s = pack.stickers.find((s) => s.id === id)!;
                return (
                  <div
                    key={id}
                    data-sticker-id={id}
                    className={
                      order
                        ? "sticker-row " +
                          (dragging === id ? "is-dragging" : "")
                        : "sticker-cell"
                    }
                  >
                    {order && (
                      <button
                        className="drag-handle"
                        aria-label={"Перетащить стикер " + (index + 1)}
                        onPointerDown={(e) => {
                          if (e.button !== 0 || drag.current || lock.current)
                            return;
                          e.preventDefault();
                          e.currentTarget.setPointerCapture(e.pointerId);
                          drag.current = {
                            id,
                            pointer: e.pointerId,
                            y: e.clientY,
                            grab:
                              e.clientY -
                              e.currentTarget
                                .closest<HTMLElement>(".sticker-row")!
                                .getBoundingClientRect().top,
                          };
                          setDragging(id);
                        }}
                        onKeyDown={(e) => {
                          if (!["ArrowUp", "ArrowDown"].includes(e.key)) return;
                          e.preventDefault();
                          const next = [...order],
                            to = index + (e.key === "ArrowUp" ? -1 : 1);
                          if (to < 0 || to >= next.length) return;
                          next.splice(to, 0, next.splice(index, 1)[0]);
                          setOrder(next);
                        }}
                      >
                        ☰
                      </button>
                    )}
                    <button
                      className="sticker-tile"
                      onClick={() =>
                        setViewer(pack.stickers.findIndex((x) => x.id === id))
                      }
                      aria-label={"Посмотреть стикер " + (index + 1)}
                    >
                      <ImageAsset
                        path={
                          "/api/packs/" +
                          pack.id +
                          "/thumbnail/" +
                          encodeURIComponent(s.preview_id)
                        }
                        alt={s.emoji}
                      />
                    </button>
                    {order ? (
                      <>
                        <label className="row-emoji">
                          <input
                            aria-label={"Эмодзи стикера " + (index + 1)}
                            value={emojis[id] ?? s.emoji}
                            maxLength={32}
                            onChange={(e) =>
                              setEmojis({ ...emojis, [id]: e.target.value })
                            }
                          />
                        </label>
                        <button
                          className="icon-button remove-sticker"
                          aria-label="Удалить стикер"
                          onClick={() => setDeleting(s)}
                        >
                          ✕
                        </button>
                      </>
                    ) : s.is_video || s.is_animated ? (
                      <span className="sticker-kind" aria-hidden="true">
                        <svg viewBox="0 0 16 16">
                          <path d="M6 4 12 8 6 12Z" />
                        </svg>
                      </span>
                    ) : null}
                  </div>
                );
              })}
            </div>
            {!pack.stickers.length && (
              <p className="empty">
                Пока ни одного стикера. Добавьте фото или видео.
              </p>
            )}
            {order ? (
              <div id="order-actions" className="order-actions">
                <button
                  id="cancel-order"
                  className="button secondary"
                  onClick={() => setOrder(null)}
                >
                  Отмена
                </button>
                <button id="save-order" className="button" onClick={saveOrder}>
                  Сохранить
                </button>
              </div>
            ) : (
              <button
                id="delete-pack"
                className="action-row delete-row"
                onClick={() => setDeleting("pack")}
              >
                <Icon name="trash" />
                Удалить набор
              </button>
            )}
          </section>
        )}
        {screen === "source" && (
          <section id="source" className="screen">
            <h1>Добавить стикер</h1>
            <p className="intro">
              Выберите фото или видео либо вставьте ссылку.
            </p>
            <form
              id="link-form"
              onSubmit={(e) => {
                e.preventDefault();
                const url = String(new FormData(e.currentTarget).get("url"));
                void task("Загружаем публикацию…", async () => {
                  const result = await json<Media | Album>("/api/studio/link", {
                    url,
                  });
                  setAlbum(null);
                  if (result.kind === "album") {
                    setAlbum(result);
                    setScreen("album");
                  } else select(result as Media);
                });
              }}
            >
              <label>
                Ссылка на фото или видео
                <input
                  id="video-link"
                  name="url"
                  type="url"
                  required
                  maxLength={2048}
                />
              </label>
              <button className="button wide">Загрузить</button>
            </form>
            <p className="hint">
              Видео из соцсетей, фотопубликации TikTok или прямая ссылка на
              JPEG, PNG, WebP.
            </p>
            <div className="divider">или с устройства</div>
            <label className="upload-box">
              <Icon name="gallery" />
              <strong>Выбрать из галереи</strong>
              <span>Фото или видео · до 50 МБ</span>
              <input
                id="video-file"
                type="file"
                accept="video/*,image/jpeg,image/png,image/webp"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (!f) return;
                  if (f.size > 50 * 1024 * 1024) {
                    setError("Файл должен быть не больше 50 МБ");
                    return;
                  }
                  void task("Подготавливаем файл…", async () => {
                    const form = new FormData();
                    form.append("video", f);
                    const s = await (
                      await request("/api/studio/upload", {
                        method: "POST",
                        body: form,
                      })
                    ).json();
                    setAlbum(null);
                    select(s);
                  });
                }}
              />
            </label>
          </section>
        )}
        {screen === "album" && album && (
          <section id="album" className="screen">
            <h1>Выберите фото</h1>
            <p className="intro">Нажмите на снимок для редактирования.</p>
            <div className="album-photos">
              {album.photos.map((photo, i) => (
                <button
                  key={photo.id}
                  className="album-photo"
                  onClick={() => select(photo)}
                >
                  <ImageAsset
                    path={"/api/studio/media/" + photo.id + "?thumbnail=true"}
                    alt={"Фото " + (i + 1)}
                  />
                </button>
              ))}
            </div>
          </section>
        )}
        {screen === "editor" && source && edit && (
          <Editor
            key={source.id}
            source={source}
            edit={edit}
            onChange={setEdit}
            busy={!!busy}
            onRender={() =>
              void task("Создаём стикер…", async () => {
                const key = JSON.stringify(edit);
                const result =
                  renderCache.current?.key === key
                    ? renderCache.current.media
                    : await json<Media>("/api/studio/render", edit);
                renderCache.current = { key, media: result };
                await mediaURL(
                  "/api/studio/media/" +
                    result.id +
                    (source.kind === "photo" ? "" : "?preview=true"),
                );
                setRender(result);
                setScreen("preview");
              })
            }
          />
        )}
        {screen === "preview" && render && source && (
          <section id="preview" className="screen">
            <p className="eyebrow">ПРЕДПРОСМОТР</p>
            <h1>Можно отправлять</h1>
            <p className="intro">Эмодзи можно задать в редакторе набора.</p>
            <div className="preview-stage">
              <Playback
                path={
                  "/api/studio/media/" +
                  render.id +
                  (source.kind === "photo" ? "" : "?preview=true")
                }
                video={source.kind !== "photo"}
                alt="Готовый стикер"
              />
            </div>
            <button
              id="publish"
              className="button wide"
              onClick={() =>
                void task("Сохраняем стикер…", async () => {
                  if (!pack) return;
                  await json("/api/studio/packs/" + pack.id + "/publish", {
                    render_id: render.id,
                    emoji: replacing?.emoji || "🙂",
                    replace_id: replacing?.id || null,
                  });
                  invalidateCover(pack.id);
                  const p = await open(pack.id);
                  setOrder(p.stickers.map((s) => s.id));
                  setSource(null);
                  setReplacing(null);
                  setAlbum(null);
                  tg?.HapticFeedback?.notificationOccurred("success");
                })
              }
            >
              {replacing ? "Сохранить стикер" : "Добавить в набор"}
            </button>
            <button
              id="edit-again"
              className="button secondary wide"
              onClick={() => setScreen("editor")}
            >
              Вернуться к редактированию
            </button>
          </section>
        )}
      </main>
      {active && pack && viewer !== null && (
        <Modal
          label="Просмотр стикера"
          className="sticker-viewer"
          onNavigate={(delta) => navigateViewer(viewer + delta)}
          onClose={() => setViewer(null)}
        >
          <div className="viewer-heading">
            <span>
              {viewer + 1} из {pack.stickers.length}
            </span>
            <button
              id="close-viewer"
              className="icon-button"
              aria-label="Закрыть просмотр"
              onClick={() => setViewer(null)}
            >
              ✕
            </button>
          </div>
          <div
            className="viewer-media"
            key={active.id}
            style={
              { "--slide-direction": viewerDirection } as React.CSSProperties
            }
            onPointerDown={(e) => {
              swipe.current = { x: e.clientX, y: e.clientY, moved: false };
            }}
            onPointerMove={(e) => {
              if (Math.abs(e.clientX - swipe.current.x) > 16)
                swipe.current.moved = true;
            }}
            onPointerUp={(e) => {
              const dx = e.clientX - swipe.current.x,
                dy = e.clientY - swipe.current.y;
              if (Math.abs(dx) > 50 && Math.abs(dy) < 60)
                navigateViewer(viewer + (dx < 0 ? 1 : -1));
            }}
            onPointerCancel={() => {
              swipe.current.moved = true;
            }}
            onClickCapture={(e) => {
              if (swipe.current.moved) {
                e.preventDefault();
                e.stopPropagation();
                swipe.current.moved = false;
              }
            }}
          >
            <Playback
              path={
                "/api/packs/" +
                pack.id +
                "/stickers/" +
                encodeURIComponent(active.id) +
                "/file"
              }
              video={!!active.is_video}
              alt={active.emoji}
              onReady={() => {
                const neighbor =
                  pack.stickers[viewer + 1] || pack.stickers[viewer - 1];
                if (neighbor)
                  void mediaURL(
                    "/api/packs/" +
                      pack.id +
                      "/stickers/" +
                      encodeURIComponent(neighbor.id) +
                      "/file",
                  ).catch(() => {});
              }}
              poster={
                "/api/packs/" +
                pack.id +
                "/thumbnail/" +
                encodeURIComponent(active.preview_id)
              }
            />
          </div>
          {active.is_animated && (
            <p className="hint">
              Показана обложка. Анимация доступна в Telegram.
            </p>
          )}
          <div className="viewer-caption">
            <span id="viewer-emoji">{active.emoji}</span>
            <span>Листайте смахиванием</span>
          </div>
          <nav className="viewer-strip" aria-label="Стикеры набора">
            {pack.stickers
              .slice(
                Math.max(0, Math.min(viewer - 2, pack.stickers.length - 5)),
                Math.max(0, Math.min(viewer - 2, pack.stickers.length - 5)) + 5,
              )
              .map((sticker) => {
                const index = pack.stickers.indexOf(sticker);
                return (
                  <button
                    key={sticker.id}
                    aria-label={"Стикер " + (index + 1)}
                    aria-current={index === viewer ? "true" : undefined}
                    onClick={() => navigateViewer(index)}
                  >
                    <ImageAsset
                      path={
                        "/api/packs/" +
                        pack.id +
                        "/thumbnail/" +
                        encodeURIComponent(sticker.preview_id)
                      }
                      alt=""
                    />
                  </button>
                );
              })}
          </nav>
          <div className="viewer-actions">
            <button
              id="viewer-edit"
              className="button secondary"
              disabled={active.is_animated}
              onClick={() => {
                setViewer(null);
                void task("Открываем редактор…", async () => {
                  const s = await json<Media>(
                    "/api/studio/packs/" +
                      pack.id +
                      "/stickers/" +
                      encodeURIComponent(active.id) +
                      "/edit",
                    {},
                  );
                  setReplacing(active);
                  setAlbum(null);
                  select(s);
                });
              }}
            >
              Редактировать
            </button>
            <button
              id="delete-sticker"
              className="action-row delete-row"
              onClick={() => {
                setViewer(null);
                setDeleting(active);
              }}
            >
              Удалить
            </button>
          </div>
        </Modal>
      )}
      {deleting && pack && (
        <Modal
          label="Подтверждение удаления"
          className="confirm-dialog"
          onClose={() => setDeleting(null)}
        >
          <h2>
            {deleting === "pack" ? "Удалить стикерпак?" : "Удалить стикер?"}
          </h2>
          <p>
            {deleting === "pack"
              ? "Набор «" +
                pack.title +
                "» будет удалён из Telegram и приложения навсегда."
              : "Остальные стикеры останутся в наборе."}
            {pack.source_name && deleting === "pack"
              ? " Исходный набор по ссылке останется без изменений."
              : ""}
          </p>
          <div className="dialog-actions">
            <button
              id="cancel-delete"
              className="button secondary"
              onClick={() => setDeleting(null)}
            >
              Оставить {deleting === "pack" ? "набор" : "стикер"}
            </button>
            <button
              id="confirm-delete"
              className="button danger"
              onClick={() => {
                const target = deleting;
                setDeleting(null);
                void task("Удаляем…", async () => {
                  await request(
                    "/api/packs/" +
                      pack.id +
                      (target === "pack"
                        ? ""
                        : "/stickers/" + encodeURIComponent(target.id)),
                    { method: "DELETE" },
                  );
                  invalidateCover(pack.id);
                  if (target === "pack") await home();
                  else await open(pack.id);
                });
              }}
            >
              Удалить
            </button>
          </div>
        </Modal>
      )}
      {busy && (
        <div id="busy" className="busy" role="status" aria-live="polite">
          <div className="busy-card">
            <span className="spinner" />
            <strong>{busy}</strong>
          </div>
        </div>
      )}
      {fullscreen && !workspace && viewer === null && (
        <div className="fullscreen-prompt">
          <span>Больше места для творчества</span>
          <button
            className="text-button"
            onClick={() => {
              try {
                tg?.requestFullscreen?.();
              } catch {}
              setFullscreen(false);
            }}
          >
            На весь экран
          </button>
          <button
            className="icon-button"
            aria-label="Скрыть предложение"
            onClick={() => setFullscreen(false)}
          >
            ✕
          </button>
        </div>
      )}
    </>
  );
}
