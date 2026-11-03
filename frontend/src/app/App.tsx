import { useCallback, useEffect, useRef, useState } from "react";
import { clearMedia, json, tg } from "../api";
import type { Pack, Sticker, ScreenHandle } from "../types";
import { Icon } from "../ui";
import { PackLibrary } from "../packs/PackLibrary";
import { CreatePack } from "../packs/CreatePack";
import { PackScreen, type PackScreenHandle } from "../packs/PackScreen";
import { Studio } from "../studio/Studio";
import { useTelegram } from "../telegram/useTelegram";
import { useTask } from "./useTask";
import icons from "../icons.svg?raw";

export default function App() {
  const [screen, setScreen] = useState<"home" | "new" | "pack" | "studio">(
    "home",
  );
  const [packs, setPacks] = useState<Pack[]>([]);
  const [pack, setPack] = useState<Pack | null>(null);
  const [replacing, setReplacing] = useState<Sticker | null>(null);
  const [workspace, setWorkspace] = useState(false);
  const [viewing, setViewing] = useState(false);
  const packScreen = useRef<PackScreenHandle>(null);
  const studio = useRef<ScreenHandle>(null);
  const { tasks, busy, error } = useTask();
  const home = useCallback(async () => {
    const result = await json<{ packs: Pack[] }>("/api/packs");
    setPacks(result.packs);
    setPack(null);
    setScreen("home");
  }, []);
  const open = (current: Pack) => {
    setPack(current);
    setScreen("pack");
  };
  const back = useCallback(() => {
    if (tasks.isRunning()) return;
    tasks.reportError("");
    if (screen === "pack") packScreen.current?.back();
    else if (screen === "studio") studio.current?.back();
    else void tasks.run("Загрузка…", home);
  }, [screen, tasks, home]);
  const { fullscreen, setFullscreen } = useTelegram(
    back,
    screen !== "home",
    workspace,
  );
  useEffect(() => {
    if (tg?.initData) void tasks.run("Загружаем наборы…", home);
    return clearMedia;
  }, [tasks, home]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [screen]);
  const startStudio = (sticker: Sticker | null) => {
    setReplacing(sticker);
    setScreen("studio");
  };
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
            onClick={(event) => {
              event.preventDefault();
              void tasks.run("Загрузка…", home);
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
          <PackLibrary
            packs={packs}
            onNew={() => setScreen("new")}
            onOpen={(id) => {
              void tasks.run("Открываем набор…", async () =>
                open(await json<Pack>("/api/packs/" + id)),
              );
            }}
          />
        )}
        {screen === "new" && <CreatePack tasks={tasks} onOpen={open} />}
        {/* Keep Pack mounted so Studio round trips preserve unsaved drafts. */}
        {pack && (
          <PackScreen
            key={pack.id}
            pack={pack}
            active={screen === "pack"}
            tasks={tasks}
            navigation={packScreen}
            onUpdate={setPack}
            onExit={home}
            onAdd={() => startStudio(null)}
            onEdit={startStudio}
            onViewing={setViewing}
          />
        )}
        {screen === "studio" && pack && (
          <Studio
            pack={pack}
            replacing={replacing}
            tasks={tasks}
            navigation={studio}
            onExit={() => setScreen("pack")}
            onWorkspace={setWorkspace}
            onComplete={(current) => {
              packScreen.current?.published(current);
              setScreen("pack");
            }}
          />
        )}
      </main>
      {busy && (
        <div id="busy" className="busy" role="status" aria-live="polite">
          <div className="busy-card">
            <span className="spinner" />
            <strong>{busy}</strong>
          </div>
        </div>
      )}
      {fullscreen && !workspace && !viewing && (
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
