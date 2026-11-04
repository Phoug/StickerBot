import { useCallback, useEffect, useState } from "react";
import { mediaURL, sourceVideoURL } from "../api";
import type { Media } from "../types";

const filmstrips = new Map<string, { created: number; frames: string[] }>();

/** Own browser loading, first-frame readiness and the filmstrip decoder. */
export function useEditorMedia(source: Media) {
  const [url, setURL] = useState("");
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [frames, setFrames] = useState<string[]>([]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let live = true;
    setURL("");
    setReady(false);
    setFailure("");
    setFrames([]);
    const path = "/api/studio/media/" + source.id + (source.kind === "photo" ? "?preview=true" : "");
    void (source.kind === "photo" ? mediaURL(path) : sourceVideoURL(source.id)).then(
      (value) => { if (live) setURL(value); },
      (error: unknown) => {
        if (live) setFailure(error instanceof Error ? error.message : "Не удалось загрузить файл.");
      },
    );
    return () => { live = false; };
  }, [source.id, source.kind, attempt]);

  useEffect(() => {
    if (ready || failure) return;
    const timer = setTimeout(() => {
      setFailure(source.kind === "photo"
        ? "Фото не загрузилось. Проверьте соединение и повторите загрузку."
        : "Видео не загрузилось. Нажмите ▶ или повторите загрузку.");
    }, 30000);
    return () => clearTimeout(timer);
  }, [source.id, source.kind, attempt, ready, failure]);

  useEffect(() => {
    // Show the first frame before spending decoder time on the timeline.
    if (source.kind === "photo" || !url || !ready || failure) return;
    const cached = filmstrips.get(source.id);
    if (cached && Date.now() - cached.created < 300000) {
      setFrames(cached.frames);
      return;
    }
    filmstrips.delete(source.id);
    let live = true;
    let cancelSeek = () => {};
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    const thumbnails: string[] = [];
    video.onloadedmetadata = async () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = 96;
        canvas.height = 64;
        const context = canvas.getContext("2d");
        if (!context) return;
        for (let i = 0; i < 16 && live; i++) {
          await new Promise<void>((resolve, reject) => {
            const timer = setTimeout(() => finish(false), 5000);
            const finish = (ok: boolean) => {
              clearTimeout(timer);
              video.onseeked = null;
              video.onerror = null;
              cancelSeek = () => {};
              if (ok) resolve();
              else reject(Error("Filmstrip seek cancelled"));
            };
            cancelSeek = () => finish(false);
            video.onseeked = () => finish(true);
            video.onerror = () => finish(false);
            video.currentTime = Math.max(0, Math.min(
              video.duration - 0.01,
              ((i + 0.5) * video.duration) / 16,
            ));
          });
          if (!live) return;
          context.drawImage(video, 0, 0, 96, 64);
          thumbnails.push(canvas.toDataURL("image/jpeg", 0.6));
          setFrames([...thumbnails]);
        }
        if (live) {
          if (filmstrips.size >= 16) filmstrips.delete(filmstrips.keys().next().value!);
          filmstrips.set(source.id, { created: Date.now(), frames: [...thumbnails] });
        }
      } catch {
        // Timeline editing also works without thumbnails.
      }
    };
    video.src = url;
    return () => {
      live = false;
      cancelSeek();
      video.onloadedmetadata = null;
      video.pause();
      video.removeAttribute("src");
      video.load();
    };
  }, [url, ready, failure, source.kind, source.id]);

  return {
    url, ready, failure, frames, retry, attempt,
    onReady: () => { setReady(true); setFailure(""); },
    onError: () => setFailure("Не удалось открыть файл. Повторите загрузку или выберите другой файл."),
  };
}
