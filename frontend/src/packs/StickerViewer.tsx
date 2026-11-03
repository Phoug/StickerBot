import { useRef, useState } from "react";
import { mediaURL } from "../api";
import { Playback } from "../media/Playback";
import type { Pack, Sticker } from "../types";
import { ImageAsset, Modal } from "../ui";

export function StickerViewer({
  pack,
  initialIndex,
  onClose,
  onEdit,
  onDelete,
}: {
  pack: Pack;
  initialIndex: number;
  onClose: () => void;
  onEdit: (sticker: Sticker) => void;
  onDelete: (sticker: Sticker) => void;
}) {
  const [viewer, setViewer] = useState(initialIndex);
  const swipe = useRef({ x: 0, y: 0, moved: false });
  const [viewerDirection, setViewerDirection] = useState(1);
  const navigateViewer = (index: number) => {
    const next = Math.max(0, Math.min(pack.stickers.length - 1, index));
    if (next === viewer) return;
    setViewerDirection(next > viewer ? 1 : -1);
    setViewer(next);
  };
  const active = pack.stickers[viewer];
  if (!active) return null;
  return (
    <Modal
      label="Просмотр стикера"
      className="sticker-viewer"
      onNavigate={(delta) => navigateViewer(viewer + delta)}
      onClose={onClose}
    >
      <div className="viewer-heading">
        <span>
          {viewer + 1} из {pack.stickers.length}
        </span>
        <button
          id="close-viewer"
          className="icon-button"
          aria-label="Закрыть просмотр"
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      <div
        className="viewer-media"
        key={active.id}
        style={{ "--slide-direction": viewerDirection } as React.CSSProperties}
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
        <p className="hint">Показана обложка. Анимация доступна в Telegram.</p>
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
          onClick={() => onEdit(active)}
        >
          Редактировать
        </button>
        <button
          id="delete-sticker"
          className="action-row delete-row"
          onClick={() => onDelete(active)}
        >
          Удалить
        </button>
      </div>
    </Modal>
  );
}
