import { useEffect, useState } from "react";
import { tg } from "../api";

export function useTelegram(
  back: () => void,
  hasBack: boolean,
  editing: boolean,
) {
  const [fullscreen, setFullscreen] = useState(
    !!tg?.requestFullscreen &&
      !tg.isFullscreen &&
      (!tg.isVersionAtLeast || tg.isVersionAtLeast("8.0")),
  );
  useEffect(() => {
    tg?.ready();
    tg?.expand();
    try {
      tg?.setHeaderColor?.("#1f1f1f");
      tg?.setBackgroundColor?.("#1f1f1f");
    } catch {}
  }, []);
  useEffect(() => {
    tg?.BackButton?.onClick(back);
    if (hasBack) tg?.BackButton?.show();
    else tg?.BackButton?.hide();
    return () => tg?.BackButton?.offClick?.(back);
  }, [back, hasBack]);
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
  useEffect(() => {
    document.body.classList.toggle("editing", editing);
    document.body.classList.toggle("in-telegram", !!tg?.initData);
    return () => document.body.classList.remove("editing", "in-telegram");
  }, [editing]);
  return { fullscreen, setFullscreen };
}
