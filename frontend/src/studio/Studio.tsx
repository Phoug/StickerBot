import {
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
} from "react";
import { json, request, mediaURL, tg, invalidateCover } from "../api";
import { Playback } from "../media/Playback";
import type {
  Album,
  Edit,
  Media,
  Pack,
  Sticker,
  TaskRunner,
  ScreenHandle,
} from "../types";
import { ImageAsset, Icon } from "../ui";
import { Editor } from "./Editor";

export function Studio({
  pack,
  replacing,
  tasks,
  navigation,
  onExit,
  onComplete,
  onWorkspace,
}: {
  pack: Pack;
  replacing: Sticker | null;
  tasks: TaskRunner;
  navigation: Ref<ScreenHandle>;
  onExit: () => void;
  onComplete: (pack: Pack) => void;
  onWorkspace: (workspace: boolean) => void;
}) {
  const [screen, setScreen] = useState<
    "source" | "album" | "editor" | "preview"
  >("source");
  const [source, setSource] = useState<Media | null>(null);
  const [album, setAlbum] = useState<Album | null>(null);
  const [edit, setEdit] = useState<Edit | null>(null);
  const [render, setRender] = useState<Media | null>(null);
  const renderCache = useRef<{ key: string; media: Media } | null>(null);
  const busy = tasks.isRunning();
  const select = (s: Media) => {
    setSource(s);
    setEdit({
      source_id: s.id,
      start: 0,
      end: s.kind === "photo" ? 1 : Math.min(3, s.duration),
      shape: "original",
      zoom: 1,
      x: 0.5,
      y: 0.5,
    });
    setRender(null);
    renderCache.current = null;
    setScreen("editor");
  };
  useImperativeHandle(navigation, () => ({
    back: () => {
      if (tasks.isRunning()) return;
      if (screen === "preview") setScreen("editor");
      else if (screen === "editor") {
        if (replacing) onExit();
        else setScreen(album ? "album" : "source");
      } else if (screen === "album") setScreen("source");
      else onExit();
    },
  }));
  useEffect(() => {
    if (!replacing) return;
    void tasks.run("Открываем редактор…", async () => {
      try {
        select(
          await json<Media>(
            "/api/studio/packs/" +
              pack.id +
              "/stickers/" +
              encodeURIComponent(replacing.id) +
              "/edit",
            {},
          ),
        );
      } catch (error) {
        onExit();
        throw error;
      }
    });
  }, []);
  useEffect(() => {
    onWorkspace(screen === "editor" || screen === "preview");
    window.scrollTo(0, 0);
    return () => onWorkspace(false);
  }, [screen, onWorkspace]);
  return (
    <>
      {screen === "source" && (
        <section id="source" className="screen">
          <h1>Добавить стикер</h1>
          <p className="intro">Выберите фото или видео либо вставьте ссылку.</p>
          <form
            id="link-form"
            onSubmit={(e) => {
              e.preventDefault();
              const url = String(new FormData(e.currentTarget).get("url"));
              void tasks.run("Загружаем публикацию…", async () => {
                const result = await json<Media | Album>("/api/studio/link", {
                  url,
                });
                setAlbum(null);
                if (result.kind === "album") {
                  setAlbum(result);
                  setScreen("album");
                } else select(result);
              });
            }}
          >
            <label>
              Ссылка на фото или видео
              <input
                id="video-link"
                name="url"
                type="url"
                required
                maxLength={2048}
              />
            </label>
            <button className="button wide">Загрузить</button>
          </form>
          <p className="hint">
            Публичное видео, фотопубликация TikTok или прямая ссылка на JPEG,
            PNG, WebP, HEIC/HEIF, AVIF, GIF, BMP или TIFF. Закрытые публикации и трансляции недоступны.
          </p>
          <details className="hint">
            <summary>Поддерживаемые площадки</summary>
            <p>
              YouTube, TikTok, Instagram, X, VK и VK Video, OK, Rutube,
              Reddit, Facebook, Vimeo, Twitch, Dailymotion, Pinterest,
              Bilibili, Bluesky, Streamable, Coub.
            </p>
          </details>
          <div className="divider">или с устройства</div>
          <label className="upload-box">
            <Icon name="gallery" />
            <strong>Выбрать из галереи</strong>
            <span>Фото или видео · до 50 МБ</span>
            <span>HEIC, JPEG, PNG и другие фото; MOV, MP4, WebM и другие видео. GIF — первый кадр.</span>
            <input
              id="video-file"
              type="file"
              accept="video/*,image/jpeg,image/png,image/webp,image/heic,image/heif,image/heic-sequence,image/heif-sequence,image/avif,image/gif,image/bmp,image/tiff,.mov,.mp4,.m4v,.3gp,.3g2,.mkv,.webm,.avi,.mpeg,.mpg,.mts,.m2ts,.ts,.wmv,.asf,.flv,.ogv,.ogg,.vob,.heic,.heif,.avif,.tif,.tiff"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (!f) return;
                if (f.size > 50 * 1024 * 1024) {
                  tasks.reportError("Файл должен быть не больше 50 МБ");
                  return;
                }
                void tasks.run("Подготавливаем файл…", async () => {
                  const form = new FormData();
                  form.append("video", f);
                  const s = await (
                    await request("/api/studio/upload", {
                      method: "POST",
                      body: form,
                    })
                  ).json();
                  setAlbum(null);
                  select(s);
                });
              }}
            />
          </label>
        </section>
      )}
      {screen === "album" && album && (
        <section id="album" className="screen">
          <h1>Выберите фото</h1>
          <p className="intro">Нажмите на снимок для редактирования.</p>
          <div className="album-photos">
            {album.photos.map((photo, i) => (
              <button
                key={photo.id}
                className="album-photo"
                onClick={() => select(photo)}
              >
                <ImageAsset
                  path={"/api/studio/media/" + photo.id + "?thumbnail=true"}
                  alt={"Фото " + (i + 1)}
                />
              </button>
            ))}
          </div>
        </section>
      )}
      {screen === "editor" && source && edit && (
        <Editor
          key={source.id}
          source={source}
          edit={edit}
          onChange={setEdit}
          busy={busy}
          onRender={() =>
            void tasks.run("Создаём стикер…", async () => {
              const key = JSON.stringify(edit);
              const result =
                renderCache.current?.key === key
                  ? renderCache.current.media
                  : await json<Media>("/api/studio/render", edit);
              renderCache.current = { key, media: result };
              await mediaURL(
                "/api/studio/media/" +
                  result.id +
                  (source.kind === "photo" ? "" : "?preview=true"),
              );
              setRender(result);
              setScreen("preview");
            })
          }
        />
      )}
      {screen === "preview" && render && source && (
        <section id="preview" className="screen">
          <p className="eyebrow">ПРЕДПРОСМОТР</p>
          <h1>Можно отправлять</h1>
          <p className="intro">Эмодзи можно задать в редакторе набора.</p>
          <div className="preview-stage">
            <Playback
              path={
                "/api/studio/media/" +
                render.id +
                (source.kind === "photo" ? "" : "?preview=true")
              }
              video={source.kind !== "photo"}
              alt="Готовый стикер"
            />
          </div>
          <button
            id="publish"
            className="button wide"
            onClick={() =>
              void tasks.run("Сохраняем стикер…", async () => {
                if (!pack) return;
                await json("/api/studio/packs/" + pack.id + "/publish", {
                  render_id: render.id,
                  emoji: replacing?.emoji || "🙂",
                  replace_id: replacing?.id || null,
                });
                invalidateCover(pack.id);
                onComplete(await json<Pack>("/api/packs/" + pack.id));
                tg?.HapticFeedback?.notificationOccurred("success");
              })
            }
          >
            {replacing ? "Сохранить стикер" : "Добавить в набор"}
          </button>
          <button
            id="edit-again"
            className="button secondary wide"
            onClick={() => setScreen("editor")}
          >
            Вернуться к редактированию
          </button>
        </section>
      )}
    </>
  );
}
