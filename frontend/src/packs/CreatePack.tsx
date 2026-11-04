import { useEffect, useState } from "react";
import { json } from "../api";
import type { Pack, TaskRunner } from "../types";

export function CreatePack({
  tasks,
  onOpen,
}: {
  tasks: TaskRunner;
  onOpen: (pack: Pack) => void;
}) {
  const [importing, setImporting] = useState(false);
  const [shortName, setShortName] = useState("");
  const [nameCheck, setNameCheck] = useState<{
    value: string;
    available: boolean | null;
    name?: string | null;
    suffix?: string;
    max_length?: number;
    error?: string;
  } | null>(null);
  useEffect(() => {
    let current = true;
    const timer = window.setTimeout(() => {
      void json<{
        name: string | null;
        suffix: string;
        max_length: number;
        available: boolean | null;
      }>("/api/packs/name-availability?short_name=" + encodeURIComponent(shortName.trim()))
        .then((result) => {
          if (current) setNameCheck({ ...result, value: shortName });
        })
        .catch((error: unknown) => {
          if (current) setNameCheck({
            value: shortName,
            available: false,
            error: error instanceof Error ? error.message : "Не удалось проверить ссылку",
          });
        });
    }, shortName.trim() ? 350 : 0);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [shortName]);
  const nameReady = !shortName.trim() || (
    nameCheck?.value === shortName && nameCheck.available === true
  );
  const open = async (id: string) =>
    onOpen(await json<Pack>("/api/packs/" + id));
  return (
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
          if (!nameReady) return;
          const data = new FormData(e.currentTarget);
          void tasks.run("Создаём набор…", async () => {
            const p = await json<Pack>("/api/packs", {
              title: String(data.get("title")).trim(),
              source: importing ? String(data.get("link")).trim() : null,
              short_name: shortName.trim(),
            });
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
        <label>
          Своя ссылка на новый набор (необязательно)
          <input
            id="pack-short-name"
            value={shortName}
            onChange={(e) => setShortName(e.target.value)}
            maxLength={nameCheck?.max_length || 64}
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            aria-describedby="pack-name-status"
          />
        </label>
        <p id="pack-name-status" className="hint" role="status" aria-live="polite">
          {!shortName.trim()
            ? "Оставьте пустым — ссылка создастся автоматически."
            : nameCheck?.value !== shortName
              ? "Проверяем ссылку…"
              : nameCheck.error || (nameCheck.available
                ? "Ссылка свободна: https://t.me/addstickers/" + nameCheck.name
                : "Эта ссылка уже занята. Выберите другую.")}
          {nameCheck?.suffix && " Обязательное окончание добавится автоматически: " + nameCheck.suffix}
        </p>
        <button className="button wide" type="submit" disabled={!nameReady}>
          Создать {importing ? "копию" : "набор"}
        </button>
      </form>
    </section>
  );
}
