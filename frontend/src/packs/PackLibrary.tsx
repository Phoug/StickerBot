import { tg } from "../api";
import type { Pack } from "../types";
import { ImageAsset, Icon } from "../ui";

export function PackLibrary({
  packs,
  onNew,
  onOpen,
}: {
  packs: Pack[];
  onNew: () => void;
  onOpen: (id: string) => void;
}) {
  return (
    <section id="home" className="screen">
      <div className="collection-hero">
        <span className="studio-mark">
          <Icon name="sticker" />
        </span>
        <h1>Мои стикеры</h1>
        <p>
          Создавайте стикеры из фото и видео
          <br />и собирайте свои наборы.
        </p>
      </div>
      {packs.length > 0 && (
        <>
          <div className="section-heading">
            <h2>
              Наборы <span className="counter">{packs.length}</span>
            </h2>
          </div>
          <button id="create" className="action-row" onClick={onNew}>
            <Icon name="plus" />
            Создать набор стикеров
          </button>
        </>
      )}
      <div id="packs" className="pack-grid">
        {packs.map((p) => (
          <button key={p.id} className="pack-card" onClick={() => onOpen(p.id)}>
            <span className="pack-symbol">
              {p.status === "ready" ? (
                <ImageAsset path={"/api/packs/" + p.id + "/cover"} />
              ) : (
                <Icon name="sticker" />
              )}
            </span>
            <strong>{p.title}</strong>
            <small>
              {p.status === "draft"
                ? "Черновик"
                : p.status === "import_pending"
                  ? "Импорт не завершён"
                  : p.count + " стикеров"}
            </small>
          </button>
        ))}
      </div>
      {!packs.length && (
        <div id="empty" className="empty">
          <h2>Начните с первого набора</h2>
          <p>Соберите фото и видео или перенесите готовый набор.</p>
          <button
            id="create-empty"
            className="button"
            disabled={!tg?.initData}
            onClick={onNew}
          >
            Создать стикерпак
          </button>
        </div>
      )}
    </section>
  );
}
