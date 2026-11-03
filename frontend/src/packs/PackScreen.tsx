import {
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type Ref,
} from "react";
import { json, request, tg, invalidateCover } from "../api";
import { useSwipeLock } from "../telegram/useSwipeLock";
import type { Pack, Sticker, TaskRunner } from "../types";
import { Icon, ImageAsset, Modal } from "../ui";
import { StickerViewer } from "./StickerViewer";

export interface PackScreenHandle {
  back: () => void;
  published: (pack: Pack) => void;
}

export function PackScreen({
  pack,
  active,
  tasks,
  navigation,
  onUpdate,
  onExit,
  onAdd,
  onEdit,
  onViewing,
}: {
  pack: Pack;
  active: boolean;
  tasks: TaskRunner;
  navigation: Ref<PackScreenHandle>;
  onUpdate: (pack: Pack) => void;
  onExit: () => Promise<void>;
  onAdd: () => void;
  onEdit: (sticker: Sticker) => void;
  onViewing: (viewing: boolean) => void;
}) {
  const [order, setOrder] = useState<string[] | null>(null);
  const [emojis, setEmojis] = useState<Record<string, string>>({});
  const [viewer, setViewer] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Sticker | "pack" | null>(null);
  const drag = useRef<{
    id: string;
    pointer: number;
    y: number;
    grab: number;
  } | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const orderRef = useRef(order);
  orderRef.current = order;
  useSwipeLock(order !== null || viewer !== null);
  const open = async (id: string) => {
    const current = await json<Pack>("/api/packs/" + id);
    setOrder(null);
    setEmojis({});
    onUpdate(current);
    return current;
  };
  useImperativeHandle(navigation, () => ({
    back: () => {
      if (tasks.isRunning()) return;
      if (deleting) setDeleting(null);
      else if (viewer !== null) setViewer(null);
      else if (order) setOrder(null);
      else void tasks.run("Загрузка…", onExit);
    },
    published: (current) => {
      onUpdate(current);
      setOrder(current.stickers.map((sticker) => sticker.id));
      setEmojis({});
    },
  }));
  useEffect(() => {
    const viewing = active && viewer !== null;
    document.body.classList.toggle("viewing", viewing);
    onViewing(viewing);
    return () => {
      document.body.classList.remove("viewing");
      onViewing(false);
    };
  }, [active, viewer, onViewing]);
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
    void tasks.run("Сохраняем изменения…", async () => {
      if (!order) return;
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
  if (!active) return null;
  return (
    <>
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
                void tasks.run("Продолжаем импорт…", async () => {
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
              onClick={onAdd}
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
                    ? "sticker-row " + (dragging === id ? "is-dragging" : "")
                    : "sticker-cell"
                }
              >
                {order && (
                  <button
                    className="drag-handle"
                    aria-label={"Перетащить стикер " + (index + 1)}
                    onPointerDown={(e) => {
                      if (e.button !== 0 || drag.current || tasks.isRunning())
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
      {viewer !== null && (
        <StickerViewer
          pack={pack}
          initialIndex={viewer}
          onClose={() => setViewer(null)}
          onEdit={(sticker) => {
            setViewer(null);
            onEdit(sticker);
          }}
          onDelete={(sticker) => {
            setViewer(null);
            setDeleting(sticker);
          }}
        />
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
                void tasks.run("Удаляем…", async () => {
                  await request(
                    "/api/packs/" +
                      pack.id +
                      (target === "pack"
                        ? ""
                        : "/stickers/" + encodeURIComponent(target.id)),
                    { method: "DELETE" },
                  );
                  invalidateCover(pack.id);
                  if (target === "pack") await onExit();
                  else await open(pack.id);
                });
              }}
            >
              Удалить
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
