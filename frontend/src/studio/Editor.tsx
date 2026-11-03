import { useSwipeLock } from "../telegram/useSwipeLock";
import { useEffect, useRef, useState, type PointerEvent as PE } from "react";
import type { Edit, Media } from "../types";
import { mediaURL } from "../api";
import { Icon } from "../ui";
export const clamp = (n: number, min = 0, max = 1) =>
  Math.max(min, Math.min(max, n));
export function trim(
  start: number,
  end: number,
  total: number,
  part: string,
  delta: number,
) {
  if (part === "left")
    return [clamp(start + delta, Math.max(0, end - 3), end - 0.05), end];
  if (part === "right")
    return [
      start,
      clamp(end + delta, start + 0.05, Math.min(total, start + 3)),
    ];
  const next = clamp(start + delta, 0, total - (end - start));
  return [next, next + end - start];
}
const time = (n: number) =>
  Math.floor(n / 60) + ":" + (n % 60).toFixed(2).padStart(5, "0");
export function cropOverflow(
  width: number,
  height: number,
  ratio: number,
  zoom: number,
) {
  return {
    x: Math.max(0, Math.max(1, width / (ratio * height)) * zoom - 1),
    y: Math.max(0, Math.max(1, (ratio * height) / width) * zoom - 1),
  };
}
export function Editor({
  source,
  edit,
  onChange,
  onRender,
  busy,
}: {
  source: Media;
  edit: Edit;
  onChange: (edit: Edit) => void;
  onRender: () => void;
  busy: boolean;
}) {
  const photo = source.kind === "photo";
  const [url, setURL] = useState(""),
    [tool, setTool] = useState(photo ? "crop" : "trim"),
    [size, setSize] = useState({
      w: source.width || 640,
      h: source.height || 360,
    }),
    [playing, setPlaying] = useState(false),
    [clock, setClock] = useState(0),
    [span, setSpan] = useState(Math.min(12, source.duration || 1)),
    [frames, setFrames] = useState<string[]>([]),
    [failure, setFailure] = useState("");
  const video = useRef<HTMLVideoElement>(null),
    stage = useRef<HTMLDivElement>(null),
    points = useRef(new Map<number, { x: number; y: number }>()),
    gesture = useRef<{
      cx: number;
      cy: number;
      distance: number;
      edit: Edit;
    } | null>(null),
    drag = useRef<{
      id: number;
      x: number;
      part: string;
      start: number;
      end: number;
    } | null>(null);
  useEffect(() => {
    let live = true;
    void mediaURL("/api/studio/media/" + source.id).then(
      (u) => {
        if (live) setURL(u);
      },
      (e) => {
        if (live) setFailure(e.message);
      },
    );
    return () => {
      live = false;
    };
  }, [source.id]);
  useSwipeLock(true);
  useEffect(() => {
    if (photo || !url) return;
    let live = true;
    const v = document.createElement("video");
    v.muted = true;
    v.playsInline = true;
    const urls: string[] = [];
    v.onloadedmetadata = async () => {
      try {
        for (let i = 0; i < 16 && live; i++) {
          await new Promise<void>((resolve, reject) => {
            v.onseeked = () => resolve();
            v.onerror = reject;
            v.currentTime = Math.min(
              source.duration - 0.01,
              ((i + 0.5) * source.duration) / 16,
            );
          });
          if (!live) break;
          const c = document.createElement("canvas");
          c.width = 96;
          c.height = 64;
          c.getContext("2d")!.drawImage(v, 0, 0, 96, 64);
          urls.push(c.toDataURL("image/jpeg", 0.6));
          setFrames([...urls]);
        }
      } catch {}
    };
    v.src = url;
    return () => {
      live = false;
      v.pause();
      v.removeAttribute("src");
      v.load();
    };
  }, [url, photo, source.duration]);
  const change = (patch: Partial<Edit>) => onChange({ ...edit, ...patch });
  const ratio = edit.shape === "original" ? size.w / size.h : 1;
  const { x: overflowX, y: overflowY } = cropOverflow(
    size.w,
    size.h,
    ratio,
    edit.zoom,
  );
  const mediaStyle = {
    position: "absolute" as const,
    width: (1 + overflowX) * 100 + "%",
    height: (1 + overflowY) * 100 + "%",
    left: -overflowX * edit.x * 100 + "%",
    top: -overflowY * edit.y * 100 + "%",
  };
  const rebase = () => {
    const p = [...points.current.values()];
    gesture.current = p.length
      ? {
          cx: p.reduce((n, p) => n + p.x, 0) / p.length,
          cy: p.reduce((n, p) => n + p.y, 0) / p.length,
          distance:
            p.length > 1 ? Math.hypot(p[1].x - p[0].x, p[1].y - p[0].y) : 0,
          edit: { ...edit },
        }
      : null;
  };
  const move = (e: PE<HTMLDivElement>) => {
    if (!points.current.has(e.pointerId) || !gesture.current) return;
    e.preventDefault();
    points.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const p = [...points.current.values()],
      g = gesture.current,
      r = stage.current!.getBoundingClientRect(),
      cx = p.reduce((n, p) => n + p.x, 0) / p.length - r.left,
      cy = p.reduce((n, p) => n + p.y, 0) / p.length - r.top,
      d = p.length > 1 ? Math.hypot(p[1].x - p[0].x, p[1].y - p[0].y) : 0,
      z =
        g.distance && d
          ? clamp((g.edit.zoom * d) / g.distance, 1, 3)
          : g.edit.zoom,
      b = Math.max(r.width / size.w, r.height / size.h),
      x = size.w * b * z - r.width,
      y = size.h * b * z - r.height;
    change({
      zoom: z,
      x:
        x > 0.5
          ? clamp(
              (((g.cx -
                r.left +
                (size.w * b * g.edit.zoom - r.width) * g.edit.x) *
                z) /
                g.edit.zoom -
                cx) /
                x,
            )
          : 0.5,
      y:
        y > 0.5
          ? clamp(
              (((g.cy -
                r.top +
                (size.h * b * g.edit.zoom - r.height) * g.edit.y) *
                z) /
                g.edit.zoom -
                cy) /
                y,
            )
          : 0.5,
    });
  };
  const release = (e: PE) => {
    points.current.delete(e.pointerId);
    rebase();
  };
  const viewStart = clamp(
    edit.start - span / 3,
    0,
    Math.max(0, source.duration - span),
  );
  return (
    <section id="editor" className="screen">
      <div className="editor-heading">
        <h1>Редактор {photo ? "фото" : "видео"}</h1>
        <span className="badge">{photo ? "Фото" : "Видео"}</span>
      </div>
      {failure && (
        <p className="notice" role="alert">
          {failure}
        </p>
      )}
      <div className="editor-layout">
        <div className="editor-view">
          <div className="preview-surface">
            <div
              id="crop-stage"
              ref={stage}
              className={"crop-stage " + edit.shape}
              style={{
                aspectRatio: ratio,
                height: "auto",
                width:
                  ratio < 1
                    ? `min(calc(var(--content-height) * .29 * ${ratio}), 260px)`
                    : undefined,
              }}
              tabIndex={0}
              onKeyDown={(e) => {
                const k = e.key;
                if (
                  ![
                    "ArrowLeft",
                    "ArrowRight",
                    "ArrowUp",
                    "ArrowDown",
                    "+",
                    "-",
                  ].includes(k)
                )
                  return;
                e.preventDefault();
                if (k === "+" || k === "-")
                  change({
                    zoom: clamp(edit.zoom * (k === "+" ? 1.1 : 1 / 1.1), 1, 3),
                  });
                else if (k === "ArrowLeft" || k === "ArrowRight")
                  change({
                    x: clamp(edit.x + (k === "ArrowRight" ? 0.05 : -0.05)),
                  });
                else
                  change({
                    y: clamp(edit.y + (k === "ArrowDown" ? 0.05 : -0.05)),
                  });
              }}
              aria-label="Кадр. Двигайте изображение и увеличивайте двумя пальцами"
              onWheel={(e) =>
                change({
                  zoom: clamp(
                    edit.zoom * (e.deltaY < 0 ? 1.08 : 1 / 1.08),
                    1,
                    3,
                  ),
                })
              }
              onPointerDown={(e) => {
                if (busy) return;
                e.preventDefault();
                video.current?.pause();
                setTool("crop");
                e.currentTarget.setPointerCapture(e.pointerId);
                points.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
                rebase();
              }}
              onPointerMove={move}
              onPointerUp={release}
              onPointerCancel={release}
              onLostPointerCapture={release}
            >
              {photo ? (
                <img
                  id="source-photo"
                  src={url || undefined}
                  style={mediaStyle}
                  alt="Фото для стикера"
                  onLoad={(e) =>
                    setSize({
                      w: e.currentTarget.naturalWidth,
                      h: e.currentTarget.naturalHeight,
                    })
                  }
                />
              ) : (
                <video
                  id="source-video"
                  ref={video}
                  src={url || undefined}
                  style={mediaStyle}
                  muted
                  playsInline
                  onLoadedMetadata={(e) => {
                    setSize({
                      w: e.currentTarget.videoWidth,
                      h: e.currentTarget.videoHeight,
                    });
                    e.currentTarget.currentTime = edit.start;
                  }}
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                  onTimeUpdate={(e) => {
                    setClock(e.currentTarget.currentTime);
                    if (e.currentTarget.currentTime >= edit.end)
                      e.currentTarget.pause();
                  }}
                />
              )}
              <div className="crop-guide" />
            </div>
          </div>
          {!photo && (
            <div className="playbar">
              <button
                id="play"
                className="icon-button"
                aria-label={playing ? "Пауза" : "Воспроизвести"}
                onClick={() => {
                  const v = video.current!;
                  if (!v.paused) v.pause();
                  else {
                    v.currentTime = edit.start;
                    void v.play().catch(() => {});
                  }
                }}
              >
                <Icon name={playing ? "pause" : "play"} />
              </button>
              <span className="play-time">{time(clock)}</span>
              <span className="duration-badge">
                {(edit.end - edit.start).toFixed(2)} / 3 сек
              </span>
            </div>
          )}
        </div>
        <div className="editor-tools">
          <div className="tool-tabs" role="tablist">
            {(photo ? ["crop", "shape"] : ["trim", "crop", "shape"]).map(
              (name) => (
                <button
                  key={name}
                  id={"tab-" + name}
                  role="tab"
                  aria-selected={tool === name}
                  className={tool === name ? "selected" : ""}
                  onClick={() => setTool(name)}
                >
                  {{ trim: "Фрагмент", crop: "Кадр", shape: "Форма" }[name]}
                </button>
              ),
            )}
          </div>
          <div className="tool-content">
            {tool === "trim" && (
              <div className="tool-panel">
                <div className="control-heading">
                  <strong>Выберите момент</strong>
                  <button
                    className="text-button"
                    onClick={() =>
                      setSpan(
                        span >= source.duration
                          ? Math.min(12, source.duration)
                          : source.duration,
                      )
                    }
                  >
                    {span >= source.duration ? "Точнее" : "Всё видео"}
                  </button>
                </div>
                <div
                  id="filmstrip"
                  className="filmstrip"
                  onPointerDown={(e) => {
                    e.preventDefault();
                    e.currentTarget.setPointerCapture(e.pointerId);
                    const id = (e.target as HTMLElement).id;
                    drag.current = {
                      id: e.pointerId,
                      x: e.clientX,
                      part:
                        id === "trim-left"
                          ? "left"
                          : id === "trim-right"
                            ? "right"
                            : id === "trim-move"
                              ? "move"
                              : "pan",
                      start: edit.start,
                      end: edit.end,
                    };
                  }}
                  onPointerMove={(e) => {
                    const d = drag.current;
                    if (!d || d.id !== e.pointerId) return;
                    const delta =
                        ((e.clientX - d.x) / e.currentTarget.clientWidth) *
                        span *
                        (d.part === "pan" ? -1 : 1),
                      [start, end] = trim(
                        d.start,
                        d.end,
                        source.duration,
                        d.part,
                        delta,
                      );
                    change({ start, end });
                    if (video.current) {
                      video.current.pause();
                      video.current.currentTime = start;
                    }
                  }}
                  onPointerUp={() => {
                    drag.current = null;
                  }}
                  onPointerCancel={() => {
                    drag.current = null;
                  }}
                  onLostPointerCapture={() => {
                    drag.current = null;
                  }}
                >
                  <div
                    className="film-frames"
                    style={{
                      width: (source.duration / span) * 100 + "%",
                      left: (-viewStart / span) * 100 + "%",
                    }}
                  >
                    {frames.map((src, i) => (
                      <img
                        key={i}
                        src={src}
                        alt=""
                        style={{ width: "6.25%", objectFit: "cover" }}
                      />
                    ))}
                  </div>
                  <div
                    className="trim-selection"
                    style={{
                      left: ((edit.start - viewStart) / span) * 100 + "%",
                      width: ((edit.end - edit.start) / span) * 100 + "%",
                    }}
                  >
                    {["left", "move", "right"].map((part) =>
                      part === "move" ? (
                        <span key={part} id="trim-move" className="trim-move" />
                      ) : (
                        <button
                          key={part}
                          id={"trim-" + part}
                          className="trim-handle"
                          aria-label={
                            part === "left"
                              ? "Начало фрагмента"
                              : "Конец фрагмента"
                          }
                          onKeyDown={(e) => {
                            if (!["ArrowLeft", "ArrowRight"].includes(e.key))
                              return;
                            e.preventDefault();
                            const [start, end] = trim(
                              edit.start,
                              edit.end,
                              source.duration,
                              part,
                              e.key === "ArrowRight" ? 0.05 : -0.05,
                            );
                            change({ start, end });
                          }}
                        />
                      ),
                    )}
                  </div>
                </div>
                <div className="timeline-times">
                  <span>{time(edit.start)}</span>
                  <span>{time(edit.end)}</span>
                </div>
                <p className="hint">
                  Двигайте ленту. Тяните края рамки для обрезки.
                </p>
              </div>
            )}
            {tool === "crop" && (
              <div className="tool-panel">
                <div className="control-heading">
                  <strong>Настройте кадр</strong>
                  <button
                    id="reset-crop"
                    className="text-button"
                    onClick={() => change({ zoom: 1, x: 0.5, y: 0.5 })}
                  >
                    Сбросить
                  </button>
                </div>
                <p className="hint">
                  Двигайте изображение. Разведите два пальца для увеличения.
                </p>
                <div className="gesture-art">↔ ⤢</div>
                <div className="zoom-actions">
                  <button
                    className="icon-button"
                    aria-label="Уменьшить"
                    onClick={() =>
                      change({ zoom: clamp(edit.zoom / 1.15, 1, 3) })
                    }
                  >
                    −
                  </button>
                  <output>{Math.round(edit.zoom * 100)}%</output>
                  <button
                    className="icon-button"
                    aria-label="Увеличить"
                    onClick={() =>
                      change({ zoom: clamp(edit.zoom * 1.15, 1, 3) })
                    }
                  >
                    +
                  </button>
                </div>
              </div>
            )}
            {tool === "shape" && (
              <div className="tool-panel">
                <strong>Форма стикера</strong>
                <div className="shapes">
                  {(["original", "square", "rounded", "circle"] as const).map(
                    (shape) => (
                      <button
                        key={shape}
                        data-shape={shape}
                        aria-pressed={shape === edit.shape}
                        className={shape === edit.shape ? "selected" : ""}
                        onClick={() => change({ shape })}
                      >
                        <i className={"shape-" + shape} />
                        {
                          {
                            original: "Оригинал",
                            square: "Квадрат",
                            rounded: "Скругление",
                            circle: "Круг",
                          }[shape]
                        }
                      </button>
                    ),
                  )}
                </div>
                <p className="hint">
                  Оригинал сохраняет пропорции. Остальные формы обрезают кадр.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
      <footer className="editor-footer">
        <button
          id="render"
          className="button wide"
          disabled={busy || !url || !!failure}
          onClick={onRender}
        >
          Посмотреть результат
          <Icon name="arrow" />
        </button>
      </footer>
    </section>
  );
}
