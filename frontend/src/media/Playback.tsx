import { useEffect, useRef, useState } from "react";
import { mediaURL } from "../api";
import { Icon, ImageAsset } from "../ui";
export function Playback({
  path,
  video,
  alt,
  poster,
  onReady,
}: {
  path: string;
  video: boolean;
  alt: string;
  poster?: string;
  onReady?: () => void;
}) {
  const [url, setURL] = useState(""),
    [failure, setFailure] = useState(""),
    [ready, setReady] = useState(false),
    [paused, setPaused] = useState(false),
    [flash, setFlash] = useState<"play" | "pause" | null>(null);
  const ref = useRef<HTMLVideoElement>(null),
    timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    let live = true;
    setURL("");
    setFailure("");
    setReady(false);
    setFlash(null);
    void mediaURL(path).then(
      (u) => {
        if (live) setURL(u);
      },
      (e) => {
        if (live) setFailure(e.message);
      },
    );
    return () => {
      live = false;
      clearTimeout(timer.current);
    };
  }, [path]);
  const toggle = () => {
    const v = ref.current;
    if (!v) return;
    const play = v.paused;
    setFlash(play ? "play" : "pause");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setFlash(null), 650);
    if (play)
      void v
        .play()
        .catch(() => setFailure("Нажмите ещё раз для воспроизведения."));
    else v.pause();
  };
  return (
    <>
      <div className={"playback-poster " + (ready ? "is-ready" : "")}>
        {poster && <ImageAsset path={poster} alt={alt} />}
      </div>
      {!ready && !failure && (
        <span
          className="media-loading"
          role="status"
          aria-label="Загружаем стикер"
        >
          <span className="spinner" />
        </span>
      )}
      {failure && (
        <p className="media-error" role="status">
          {failure}
        </p>
      )}
      {url &&
        (video ? (
          <video
            className={ready ? "media-ready" : ""}
            ref={ref}
            src={url}
            autoPlay
            muted
            loop
            playsInline
            disablePictureInPicture
            onLoadedData={() => {
              setReady(true);
              onReady?.();
            }}
            onPlay={() => setPaused(false)}
            onPause={() => setPaused(true)}
            onError={() => setFailure("Не удалось воспроизвести видео.")}
          />
        ) : (
          <img
            className={ready ? "media-ready" : ""}
            src={url}
            alt={alt}
            onLoad={() => {
              setReady(true);
              onReady?.();
            }}
            onError={() => setFailure("Не удалось показать стикер.")}
          />
        ))}
      {url && video && (
        <button
          className="playback-hit"
          aria-label={paused ? "Воспроизвести" : "Пауза"}
          onClick={toggle}
        />
      )}
      {flash && (
        <span key={flash} className="playback-flash" aria-hidden="true">
          <Icon name={flash} />
        </span>
      )}
    </>
  );
}
