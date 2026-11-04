import { useCallback, useEffect, useState } from "react";
import { mediaURL, sourceVideoURL } from "../api";
import type { Media } from "../types";

/** Own Source loading and the visible timeline Preview. */
export function useEditorMedia(source: Media, start = 0, span = Math.min(12, source.duration)) {
  const [url, setURL] = useState("");
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [filmstrip, setFilmstrip] = useState("");
  const [filmstripFailure, setFilmstripFailure] = useState(false);
  const [filmstripAttempt, setFilmstripAttempt] = useState(0);
  const retryFilmstrip = useCallback(() => setFilmstripAttempt((n) => n + 1), []);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let live = true;
    setURL("");
    setReady(false);
    setFailure("");
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
    setFilmstrip("");
    setFilmstripFailure(false);
    if (source.kind === "photo" || !ready || failure) return;
    let live = true;
    // Avoid decoding a new timeline for every pointer move while trimming.
    const timer = setTimeout(() => {
      const path = "/api/studio/media/" + encodeURIComponent(source.id)
        + "/filmstrip?start=" + start + "&span=" + span;
      void mediaURL(path).then(
        (value) => { if (live) setFilmstrip(value); },
        () => { if (live) setFilmstripFailure(true); },
      );
    }, 200);
    return () => { live = false; clearTimeout(timer); };
  }, [source.id, source.kind, ready, failure, start, span, filmstripAttempt]);

  return {
    url, ready, failure, filmstrip, filmstripFailure, retryFilmstrip, retry, attempt,
    onFilmstripError: () => { setFilmstrip(""); setFilmstripFailure(true); },
    onReady: () => { setReady(true); setFailure(""); },
    onError: () => setFailure("Не удалось открыть файл. Повторите загрузку или выберите другой файл."),
  };
}
