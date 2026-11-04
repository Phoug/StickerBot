// Real-browser regression checks for intrinsic media sizes and the editor canvas.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";
import { createServer } from "vite";

const server = await createServer({ server: { host: "127.0.0.1", port: 0 } });
await server.listen();
const address = server.httpServer.address();
const base = `http://127.0.0.1:${address.port}`;
const browser = await chromium.launch();
const video = await readFile(new URL("fixtures/portrait.mp4", import.meta.url));
const pack = {
  id: "p", title: "Test pack", name: "test_by_bot", status: "ready", count: 1,
  stickers: [{ id: "a", emoji: "🙂", preview_id: "thumb" }],
};

async function contained(page, selector, frameSelector) {
  const element = page.locator(selector).first();
  await element.waitFor({ state: "visible" });
  if (await element.evaluate((e) => e.tagName === "IMG")) {
    await element.evaluate((e) => e.decode());
  }
  const box = await element.boundingBox();
  const frame = await page.locator(frameSelector).first().boundingBox();
  assert(box && frame, `Missing frame: ${selector}`);
  assert(box.width > 0 && box.height > 0, `Empty media: ${selector}`);
  assert(box.x >= frame.x - 1 && box.y >= frame.y - 1, `Media starts outside ${frameSelector}`);
  assert(box.x + box.width <= frame.x + frame.width + 1, `Media exceeds frame width: ${selector}`);
  assert(box.y + box.height <= frame.y + frame.height + 1, `Media exceeds frame height: ${selector}`);
  return box;
}

try {
  for (const [width, height] of [[390, 844], [360, 560], [1024, 768]]) {
    for (const [mediaWidth, mediaHeight, kind] of [[120, 1200, "photo"], [1200, 120, "photo"], [512, 512, "photo"], [64, 512, "video"]]) {
      const context = await browser.newContext({ viewport: { width, height }, reducedMotion: "reduce" });
      const page = await context.newPage();
      await page.addInitScript(() => {
        window.Telegram = { WebApp: {
          initData: "layout-test", ready() {}, expand() {},
          viewportStableHeight: innerHeight,
          safeAreaInset: { top: 24, bottom: 24, left: 0, right: 0 },
          contentSafeAreaInset: { top: 48, bottom: 0, left: 0, right: 0 },
          setHeaderColor() {}, setBackgroundColor() {}, onEvent() {},
          BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        } };
      });
      const scenarioPack = { ...pack, stickers: [{ ...pack.stickers[0], is_video: kind === "video" }] };
      const image = `<svg xmlns="http://www.w3.org/2000/svg" width="${mediaWidth}" height="${mediaHeight}"><rect width="100%" height="100%" fill="#39719f"/></svg>`;
      await page.route("https://telegram.org/**", (route) => route.fulfill({ body: "" }));
      await page.route("**/api/**", (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path === "/api/packs") return route.fulfill({ json: { packs: [scenarioPack] } });
        if (path === "/api/packs/p") return route.fulfill({ json: scenarioPack });
        if (path === "/api/studio/link" && kind === "photo") {
          return route.fulfill({ json: { kind: "album", photos: [{ id: "source", kind, duration: 0, width: mediaWidth, height: mediaHeight }] } });
        }
        if (path.endsWith("/edit") || path === "/api/studio/link" || path === "/api/studio/upload") {
          return route.fulfill({ json: { id: "source", kind, duration: 0.5, width: mediaWidth, height: mediaHeight } });
        }
        if (path.endsWith("/playback")) return route.fulfill({ json: { url: "/api/studio/media/source/stream" } });
        if (path === "/api/studio/render") return route.fulfill({ json: { id: "render", kind, duration: 0.5 } });
        if (kind === "video" && (path.startsWith("/api/studio/media/") || path.endsWith("/file"))) {
          return route.fulfill({ contentType: "video/mp4", body: video });
        }
        return route.fulfill({ contentType: "image/svg+xml", body: image });
      });
      await page.goto(base + "/app/");
      await contained(page, ".pack-symbol img", ".pack-symbol");
      await page.getByRole("button", { name: /Test pack/ }).click();
      await contained(page, ".pack-cover img", ".pack-cover");
      await contained(page, ".sticker-tile img", ".sticker-tile");
      await page.getByLabel("Посмотреть стикер 1").click();
      await contained(page, ".viewer-media > img, .viewer-media > video", ".viewer-media");
      await contained(page, ".viewer-strip img", ".viewer-strip button");
      await page.getByLabel("Закрыть просмотр").click();
      await page.locator("#edit-stickers").click();
      await contained(page, ".sticker-tile img", ".sticker-tile");
      await page.locator("#add-sticker").click();
      if (mediaWidth === 1200 || (kind === "video" && width === 1024)) {
        await page.locator("#video-link").fill("https://www.tiktok.com/@fixture/photo/123");
        await page.locator("#link-form").evaluate((form) => form.requestSubmit());
        if (kind === "photo") {
          await contained(page, ".album-photo img", ".album-photo");
          await page.locator(".album-photo").click();
        }
      } else {
        await page.locator("#video-file").setInputFiles({ name: "fixture.png", mimeType: "image/png", buffer: Buffer.from(image) });
      }
      await page.locator("#render:enabled").waitFor();
      const stage = await contained(page, "#crop-stage", ".preview-surface");
      const surface = await page.locator(".preview-surface").boundingBox();
      // Portrait media must use the available height, not a 150–260px cap.
      if (mediaHeight > mediaWidth) assert(stage.height >= surface.height - 20, "Portrait editor does not use its available height");
      await page.locator("#tab-shape").click();
      await page.getByRole("button", { name: "Квадрат", exact: true }).click();
      const square = await contained(page, "#crop-stage", ".preview-surface");
      assert(Math.abs(square.width - square.height) < 2, "Square crop is distorted");
      await page.getByRole("button", { name: "Оригинал", exact: true }).click();
      if (process.env.LAYOUT_SCREENSHOTS && width === 390 && kind === "photo" && mediaHeight === 1200) {
        await page.screenshot({ path: process.env.LAYOUT_SCREENSHOTS + "/editor-portrait.png" });
      }
      await page.locator("#render").click();
      await page.locator(".preview-stage .media-ready").waitFor();
      await contained(page, ".preview-stage > img, .preview-stage > video", ".preview-stage");
      console.log(`PASS ${width}×${height}: ${kind} ${mediaWidth}×${mediaHeight}`);
      await context.close();
    }
  }
} finally {
  await browser.close();
  await server.close();
}
