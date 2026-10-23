"use strict";
const $ = id => document.getElementById(id);
const tg = window.Telegram?.WebApp;
const state = {screen:"home", pack:null, source:null, render:null, shape:"square", importing:false, busy:false, urls:[], sourceURL:null};
const headers = () => ({"X-Telegram-Init-Data": tg?.initData || ""});
function error(message) { $("error").textContent = message; $("error").classList.toggle("hidden", !message); }
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{...headers(), ...options.headers}});
  if (!response.ok) {
    let message = "Не удалось выполнить запрос. Попробуйте ещё раз.";
    try { const data = await response.json(); if (typeof data.detail === "string") message = data.detail; else if (Array.isArray(data.detail)) message = "Проверьте заполненные поля."; } catch {}
    if (response.status === 401) message = "Сессия истекла. Закройте Mini App и откройте его заново из бота.";
    throw new Error(message);
  }
  return response;
}
async function json(path, body) {
  return (await api(path, body === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();
}
async function task(message, action) {
  if (state.busy) return;
  state.busy = true; error(""); $("busy-text").textContent = message; $("busy").classList.remove("hidden");
  document.body.setAttribute("aria-busy", "true");
  try { await action(); } catch(e) { error(e.message || "Не удалось выполнить операцию"); }
  finally { state.busy=false; $("busy").classList.add("hidden"); document.body.removeAttribute("aria-busy"); }
}
function show(screen) {
  $("source-video").pause(); $("result-video").pause();
  state.screen = screen;
  document.querySelectorAll(".screen").forEach(node => node.classList.toggle("hidden", node.id !== screen));
  $("back").classList.toggle("hidden", screen === "home");
  if (screen === "preview") $("result-video").play().catch(()=>{});
  if (screen === "home") tg?.BackButton?.hide(); else tg?.BackButton?.show();
  window.scrollTo({top:0,behavior:"instant"});
}
function revokeMedia() {
  state.urls.forEach(url => URL.revokeObjectURL(url)); state.urls=[];
  $("source-video").removeAttribute("src"); $("result-video").removeAttribute("src");
  state.source=null; state.render=null; state.sourceURL=null;
}
async function mediaURL(path) {
  const blob = await (await api(path)).blob();
  const url = URL.createObjectURL(blob); state.urls.push(url); return url;
}
function setImport(value) {
  state.importing=value;
  $("mode-new").classList.toggle("selected", !value); $("mode-import").classList.toggle("selected", value);
  $("mode-new").setAttribute("aria-pressed", String(!value)); $("mode-import").setAttribute("aria-pressed", String(value));
  $("import-fields").classList.toggle("hidden", !value);
  $("pack-link").required=value; $("ownership").required=value;
  $("create-pack").textContent=value ? "Создать копию набора →" : "Создать набор →";
}
function newPack() { error(""); $("pack-form").reset(); setImport(false); show("new"); }
async function loadHome() {
  const {packs} = await json("/api/packs");
  $("packs").replaceChildren(); $("pack-count").textContent=packs.length;
  $("empty").classList.toggle("hidden", packs.length !== 0);
  packs.forEach(pack => {
    const button=document.createElement("button"); button.className="pack-card";
    const icon=document.createElement("span"); icon.className="pack-symbol"; icon.textContent="✦";
    const title=document.createElement("strong"); title.textContent=pack.title;
    const meta=document.createElement("small"); meta.textContent=pack.status==="draft" ? "Черновик · добавьте первый стикер" : pack.status==="import_pending" ? "Импорт не завершён" : pack.count+" стикеров ↗";
    button.append(icon,title,meta); button.onclick=()=>task("Открываем набор…",()=>openPack(pack.id));
    $("packs").append(button);
  });
  show("home");
}
async function openPack(id) {
  const pack=await json("/api/packs/"+id); state.pack=pack;
  $("current-title").textContent=pack.title;
  $("current-info").textContent=pack.status==="draft" ? "Черновик. Добавьте первый стикер, чтобы опубликовать набор." : pack.status==="import_pending" ? "Копия ещё не готова. Продолжите импорт — уже перенесённые стикеры не дублируются." : pack.count+" стикеров · можно добавить новые";
  $("telegram-link").classList.toggle("hidden",pack.status!=="ready");
  $("telegram-link").href="https://t.me/addstickers/"+pack.name;
  $("add-sticker").classList.toggle("hidden",pack.status==="import_pending");
  $("add-sticker").disabled=pack.count>=120;
  $("resume-import").classList.toggle("hidden",pack.status!=="import_pending");
  $("pack-empty").classList.toggle("hidden",pack.stickers.length!==0 || pack.status==="import_pending");
  $("stickers").replaceChildren();
  show("pack");
  const tiles=pack.stickers.map(sticker=>{
    const tile=document.createElement("div"); tile.className="sticker-tile"; tile.textContent=sticker.emoji;
    $("stickers").append(tile); return {tile,sticker};
  });
  // Load thumbnails independently so a large pack never blocks the whole UI.
  void loadThumbnails(id, tiles);
}
async function loadThumbnails(id, tiles) {
  // Keep file fetches bounded; never put Telegram credentials in image URLs.
  for (let i=0;i<tiles.length;i+=4) {
    if (state.pack?.id!==id || state.screen!=="pack") break;
    await Promise.all(tiles.slice(i,i+4).map(async ({tile,sticker})=>{
      try {
        const url=await mediaURL("/api/packs/"+id+"/thumbnail/"+encodeURIComponent(sticker.preview_id));
        const img=document.createElement("img"); img.alt=sticker.emoji; img.src=url; tile.replaceChildren(img);
      } catch {}
    }));
  }
}
async function resumeImport() {
  await json("/api/packs/"+state.pack.id+"/import",{});
  await openPack(state.pack.id);
}
async function setSource(source) {
  revokeMedia(); state.source=source;
  state.sourceURL=await mediaURL("/api/studio/media/"+source.id);
  const video=$("source-video");
  await new Promise((resolve,reject)=>{
    video.onloadedmetadata=resolve;
    video.onerror=()=>reject(new Error("Браузер не смог открыть видео. Попробуйте другой файл."));
    video.src=state.sourceURL; video.load();
  });
  $("start").value=0; $("end").value=Math.min(3,source.duration).toFixed(2);
  $("start").max=source.duration; $("end").max=source.duration;
  $("timeline").max=Math.max(0,source.duration-.05); $("timeline").value=0;
  $("zoom").value=1; $("position-x").value=.5; $("position-y").value=.5;
  setShape("square"); show("editor"); updateCrop(); updateTiming();
}
function setShape(shape) {
  state.shape=shape; $("crop-stage").className="crop-stage "+shape;
  document.querySelectorAll("[data-shape]").forEach(b=>{
    b.classList.toggle("selected",b.dataset.shape===shape);
    b.setAttribute("aria-pressed",String(b.dataset.shape===shape));
  });
}
function updateCrop() {
  const video=$("source-video"), size=$("crop-stage").clientWidth;
  if (!video.videoWidth || !size) return;
  const scale=Math.max(size/video.videoWidth,size/video.videoHeight)*Number($("zoom").value);
  const width=video.videoWidth*scale,height=video.videoHeight*scale;
  video.style.width=width+"px"; video.style.height=height+"px";
  video.style.left=-(width-size)*Number($("position-x").value)+"px";
  video.style.top=-(height-size)*Number($("position-y").value)+"px";
}
function updateTiming() {
  const start=Number($("start").value),end=Number($("end").value),duration=end-start;
  $("clip-duration").textContent=duration.toFixed(2)+" / 3 сек";
  $("render").disabled=!(duration>=.05 && duration<=3.001 && start>=0 && end<=state.source.duration+.01);
  $("timeline").value=start;
  $("source-video").currentTime=Math.max(0,start);
}
function editPayload() {
  return {source_id:state.source.id,start:Number($("start").value),end:Number($("end").value),
    shape:state.shape,zoom:Number($("zoom").value),x:Number($("position-x").value),y:Number($("position-y").value)};
}
function back() {
  if(state.busy) return;
  error("");
  if(state.screen==="preview"){ show("editor"); updateCrop(); return; }
  if(state.screen==="editor"){ show("source"); return; }
  if(state.screen==="source"){ task("Открываем набор…",()=>openPack(state.pack.id)); return; }
  task("Загружаем наборы…", async()=>{revokeMedia(); await loadHome();});
}
$("back").onclick=back; tg?.BackButton?.onClick(back);
document.querySelector(".brand").onclick=e=>{e.preventDefault();if(!state.busy) task("Загружаем наборы…",async()=>{revokeMedia();await loadHome();});};
$("create").onclick=newPack; $("create-empty").onclick=newPack;
$("mode-new").onclick=()=>setImport(false); $("mode-import").onclick=()=>setImport(true);
$("pack-form").onsubmit=e=>{
  e.preventDefault();
  task(state.importing ? "Готовим копию набора…" : "Создаём набор…",async()=>{
    state.pack=await json("/api/packs",{title:$("pack-title").value.trim(),source:state.importing ? $("pack-link").value.trim() : null});
    if(state.importing) {
      show("pack"); $("current-title").textContent=state.pack.title;
      try { await json("/api/packs/"+state.pack.id+"/import",{}); }
      catch(e) { await openPack(state.pack.id); throw e; }
    }
    await openPack(state.pack.id);
  });
};
$("resume-import").onclick=()=>task("Переносим стикеры…",resumeImport);
$("add-sticker").onclick=()=>{error("");revokeMedia();$("video-file").value="";show("source");};
$("link-form").onsubmit=e=>{e.preventDefault();task("Загружаем и подготавливаем видео…",async()=>setSource(await json("/api/studio/link",{url:$("video-link").value.trim()})));};
$("video-file").onchange=()=>{
  const file=$("video-file").files[0]; if(!file)return;
  if(file.size>50*1024*1024){error("Видео должно быть не больше 50 МБ");return;}
  task("Подготавливаем видео…",async()=>{
    const form=new FormData(); form.append("video",file);
    await setSource(await (await api("/api/studio/upload",{method:"POST",body:form})).json());
  });
};
document.querySelectorAll("[data-shape]").forEach(b=>b.onclick=()=>setShape(b.dataset.shape));
["zoom","position-x","position-y"].forEach(id=>$(id).oninput=updateCrop);
["start","end"].forEach(id=>$(id).oninput=updateTiming);
$("timeline").oninput=()=>{
  const length=Math.min(3,Number($("end").value)-Number($("start").value));
  const start=Number($("timeline").value);
  $("start").value=start.toFixed(2); $("end").value=Math.min(state.source.duration,start+Math.max(.05,length)).toFixed(2); updateTiming();
};
$("play").onclick=()=>{
  const video=$("source-video"); if(!video.paused){video.pause();return;}
  video.currentTime=Number($("start").value); video.play().catch(()=>error("Не удалось запустить видео"));
};
$("source-video").ontimeupdate=()=>{if($("source-video").currentTime>=Number($("end").value)) $("source-video").pause();};
$("render").onclick=()=>task("Создаём стикер…",async()=>{
  state.render=await json("/api/studio/render",editPayload());
  $("result-video").src=await mediaURL("/api/studio/media/"+state.render.id); show("preview");
});
$("edit-again").onclick=()=>{show("editor");updateCrop();};
$("publish").onclick=()=>task("Добавляем стикер в набор…",async()=>{
  await json("/api/studio/packs/"+state.pack.id+"/publish",{render_id:state.render.id,emoji:$("emoji").value});
  tg?.HapticFeedback?.notificationOccurred("success"); revokeMedia(); await openPack(state.pack.id);
});
window.addEventListener("resize",updateCrop);
window.addEventListener("beforeunload",()=>state.urls.forEach(url=>URL.revokeObjectURL(url)));
tg?.ready(); tg?.expand();
if(!tg?.initData) {
  $("auth-notice").classList.remove("hidden"); $("empty").classList.remove("hidden");
  $("create").disabled=true; $("create-empty").disabled=true;
} else {task("Загружаем ваши наборы…",loadHome);}
