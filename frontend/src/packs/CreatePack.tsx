import { useState } from "react";
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
          const data = new FormData(e.currentTarget);
          void tasks.run("Создаём набор…", async () => {
            const p = await json<Pack>("/api/packs", {
              title: String(data.get("title")).trim(),
              source: importing ? String(data.get("link")).trim() : null,
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
        <button className="button wide" type="submit">
          Создать {importing ? "копию" : "набор"}
        </button>
      </form>
    </section>
  );
}
