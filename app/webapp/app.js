"use strict";
const $ = id => document.getElementById(id);
const tg = window.Telegram?.WebApp;
const state = {screen:"home", pack:null, source:null, render:null, shape:"original", tool:"trim", importing:false, busy:false, urls:[], sourceURL:null, deleteTarget:null};
state.emojiEdits={}; state.replacing=null; state.publishEmoji="🙂"; state.renderKey=null;
state.order=null; state.viewerIndex=0; state.viewerGeneration=0;
const mediaCache=new Map();
let mediaGeneration=0;
let orderDrag=null;
const headers = () => ({"X-Telegram-Init-Data": tg?.initData || ""});
function error(message) { $("error").textContent = message; $("error").classList.toggle("hidden", !message); }
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{...headers(), ...options.headers}});
  if (!response.ok) {
    let message = "Не удалось выполнить запрос. Попробуйте ещё раз.";
    try { const data = await response.json(); if (typeof data.detail === "string") message = data.detail; else if (Array.isArray(data.detail)) message = data.detail.some(item=>item.loc?.includes("emoji")) ? "Введите один эмодзи с клавиатуры, например 🥹." : "Проверьте заполненные поля."; } catch {}
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
  finishOrderDrag();
  $("source-video").pause(); $("result-video").pause();
  state.screen = screen;
  const workspace=screen === "editor" || screen === "preview";
  document.body.classList.toggle("editing", workspace);
  $("app-shell").classList.toggle("is-editor", workspace);
  document.querySelectorAll(".screen").forEach(node => node.classList.toggle("hidden", node.id !== screen));
  $("back").classList.toggle("hidden", screen === "home");
  if (screen === "preview" && !isPhoto()) $("result-video").play().catch(()=>{});
  if (screen === "home") tg?.BackButton?.hide(); else tg?.BackButton?.show();
  window.scrollTo({top:0,behavior:"instant"});
  updateViewport();
}
function revokeMedia() {
  mediaGeneration++;
  for(const [path,item] of mediaCache) if(path.startsWith("/api/studio/")) {
    mediaCache.delete(path); if(item.url) URL.revokeObjectURL(item.url);
  }
  $("source-video").removeAttribute("src"); $("result-video").removeAttribute("src");
  $("source-photo").removeAttribute("src"); $("result-photo").removeAttribute("src");
  state.source=null; state.render=null; state.renderKey=null; state.sourceURL=null;
}
async function mediaURL(path) {
  const previous=mediaCache.get(path);
  if(previous && Date.now()-previous.created<300000) return previous.promise;
  if(previous?.url)URL.revokeObjectURL(previous.url);
  mediaCache.delete(path);
  const generation=mediaGeneration;
  const item={created:Date.now(),size:0,url:null};
  item.promise=(async()=>{
    const blob=await (await api(path)).blob();
    if(item.cancelled || path.startsWith("/api/studio/") && generation!==mediaGeneration) throw new Error("Предпросмотр закрыт");
    item.url=URL.createObjectURL(blob); item.size=blob.size;
    // Keep a bounded session cache across navigation; no credentials in URLs.
    let bytes=[...mediaCache.values()].reduce((total,entry)=>total+entry.size,0);
    for(const [key,entry] of mediaCache) {
      if(mediaCache.size<=128 && bytes<=100*1024*1024)break;
      if(key===path || !entry.url)continue;
      bytes-=entry.size;URL.revokeObjectURL(entry.url);mediaCache.delete(key);
    }
    return item.url;
  })();
  mediaCache.set(path,item);
  try {return await item.promise;}
  catch(e){if(mediaCache.get(path)===item)mediaCache.delete(path);throw e;}
}
function invalidateCover(id) {
  const path="/api/packs/"+id+"/cover",item=mediaCache.get(path);
  if(item){item.cancelled=true;if(item.url)URL.revokeObjectURL(item.url);mediaCache.delete(path);}
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
function stickerCount(count) {
  const last=count%10, tail=count%100;
  const word=last===1 && tail!==11?"стикер":last>=2 && last<=4 && (tail<12 || tail>14)?"стикера":"стикеров";
  return count+" "+word;
}
async function loadHome() {
  finishOrderDrag(); revokeMedia();state.order=null;
  const {packs} = await json("/api/packs");
  $("packs").replaceChildren(); $("pack-count").textContent=packs.length;
  $("empty").classList.toggle("hidden", packs.length !== 0);
  $("create").classList.toggle("hidden", packs.length===0);
  $("collection-heading").classList.toggle("hidden", packs.length===0);
  packs.forEach(pack => {
    const button=document.createElement("button"); button.className="pack-card";
    const icon=document.createElement("span"); icon.className="pack-symbol";
    icon.innerHTML='<svg class="icon" aria-hidden="true"><use href="#i-sticker"/></svg>';
    const title=document.createElement("strong"); title.textContent=pack.title;
    const meta=document.createElement("small"); meta.textContent=pack.status==="draft" ? "Черновик · добавьте первый стикер" : pack.status==="import_pending" ? "Импорт не завершён" : stickerCount(pack.count);
    button.append(icon,title,meta); button.onclick=()=>task("Открываем набор…",()=>openPack(pack.id));
    $("packs").append(button);
    if(pack.status==="ready") void loadCover(pack.id,icon);
  });
  show("home");
}
async function openPack(id) {
  const pack=await json("/api/packs/"+id); state.pack=pack;
  state.order=null; state.emojiEdits={};
  $("current-title").textContent=pack.title;
  $("current-info").textContent=pack.status==="draft" ? "Черновик. Добавьте первый стикер, чтобы опубликовать набор." : pack.status==="import_pending" ? "Копия ещё не готова. Продолжите импорт — уже перенесённые стикеры не дублируются." : stickerCount(pack.count)+(pack.source_name?" · редактируемая копия набора":" · фото и видео");
  $("telegram-link").classList.toggle("hidden",pack.status!=="ready");
  $("telegram-link").href="https://t.me/addstickers/"+pack.name;
  $("add-sticker").classList.toggle("hidden",pack.status==="import_pending");
  $("add-sticker").disabled=pack.count>=120;
  $("resume-import").classList.toggle("hidden",pack.status!=="import_pending");
  $("pack-empty").classList.toggle("hidden",pack.stickers.length!==0 || pack.status==="import_pending");
  show("pack");
  $("pack-cover").innerHTML='<svg class="icon"><use href="#i-sticker"/></svg>';
  if(pack.status==="ready") void loadCover(id,$("pack-cover"));
  renderStickers();
}
async function loadCover(id,node) {
  try { const url=await mediaURL("/api/packs/"+id+"/cover"); const img=document.createElement("img");img.src=url;img.alt="";node.replaceChildren(img); } catch {}
}
function renderStickers() {
  finishOrderDrag();
  const editing=!!state.order, id=state.pack.id;
  $("stickers").replaceChildren();
  $("stickers").classList.toggle("sticker-list",editing);
  $("order-actions").classList.toggle("hidden",!editing);
  $("order-hint").classList.toggle("hidden",!editing);
  $("edit-stickers").classList.toggle("hidden",editing || !state.pack.stickers.length);
  $("delete-pack").classList.toggle("hidden",editing);
  const stickers=editing?state.order.map(key=>state.pack.stickers.find(s=>s.id===key)):state.pack.stickers;
  const tiles=stickers.map((sticker,index)=>{
    const tile=document.createElement("div");tile.className=editing?"sticker-row":"sticker-cell";
    const thumb=document.createElement("button");thumb.className="sticker-tile";thumb.textContent=sticker.emoji;
    thumb.setAttribute("aria-label","Посмотреть стикер "+(index+1)+" "+sticker.emoji);
    thumb.onclick=()=>openViewer(state.pack.stickers.findIndex(s=>s.id===sticker.id));
    if(editing) {
      const handle=document.createElement("button");handle.className="drag-handle";handle.textContent="☰";handle.setAttribute("aria-label","Перетащить стикер "+(index+1));
      handle.onpointerdown=e=>startOrderDrag(e,sticker.id,handle);
      handle.onkeydown=e=>{
        if(!["ArrowUp","ArrowDown"].includes(e.key))return;
        e.preventDefault();moveSticker(sticker.id,state.order.indexOf(sticker.id)+(e.key==="ArrowUp"?-1:1));
      };
      const field=document.createElement("label");field.className="row-emoji";field.textContent="Эмодзи";
      const emoji=document.createElement("input");emoji.type="text";emoji.value=state.emojiEdits[sticker.id]??sticker.emoji;emoji.maxLength=32;
      emoji.autocomplete="off";emoji.spellcheck=false;emoji.setAttribute("aria-label","Эмодзи стикера "+(index+1));
      emoji.oninput=()=>{state.emojiEdits[sticker.id]=emoji.value;};field.append(emoji);
      tile.append(handle,thumb,field);
      const remove=document.createElement("button");remove.className="icon-button remove-sticker";remove.textContent="✕";remove.setAttribute("aria-label","Удалить стикер "+(index+1));remove.onclick=()=>requestStickerDelete(sticker);tile.append(remove);
    } else {
      const kind=document.createElement("span");kind.className="sticker-kind";
      kind.textContent=sticker.is_video?"Видео":sticker.is_animated?"Анимация":"Фото";
      tile.append(thumb,kind);
    }
    tile.dataset.stickerId=sticker.id;$("stickers").append(tile); return {tile:thumb,sticker};
  });
  // Load thumbnails independently so a large pack never blocks the whole UI.
  void loadThumbnails(id, tiles);
}
function moveSticker(id,position) {
  if(!state.order || state.busy)return;
  const from=state.order.indexOf(id);if(from<0 || position<0 || position>=state.order.length || from===position)return;
  const focused=document.activeElement;
  const rows=[...$("stickers").children];
  const before=new Map(rows.map(row=>[row.dataset.stickerId,row.getBoundingClientRect?.().top]));
  state.order.splice(position,0,state.order.splice(from,1)[0]);
  const byId=new Map(rows.map(row=>[row.dataset.stickerId,row]));
  state.order.forEach((key,index)=>{
    const row=byId.get(key);$("stickers").append(row);
  });
  if(focused?.isConnected)focused.focus({preventScroll:true});
  if(!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) rows.forEach(row=>{
    const delta=before.get(row.dataset.stickerId)-row.getBoundingClientRect?.().top;
    row.getAnimations?.().forEach(animation=>animation.cancel());
    if(delta && row!==orderDrag?.row)row.animate?.([{transform:`translateY(${delta}px)`},{transform:"translateY(0)"}],{duration:220,easing:"cubic-bezier(.2,.8,.2,1)"});
  });
  tg?.HapticFeedback?.selectionChanged?.();
}
function finishOrderDrag() {
  if(!orderDrag)return;
  cancelAnimationFrame(orderDrag.frame);
  window.removeEventListener("pointermove",orderDrag.move);
  window.removeEventListener("pointerup",orderDrag.end);
  window.removeEventListener("pointercancel",orderDrag.end);
  window.removeEventListener("blur",orderDrag.end);
  orderDrag.row?.classList.remove("is-dragging");
  orderDrag.handle.classList.remove("dragging");orderDrag=null;
}
function startOrderDrag(e,id,handle) {
  if(state.busy || !state.order || (e.button!==undefined && e.button!==0))return;
  finishOrderDrag();e.preventDefault();
  const row=handle.closest("[data-sticker-id]");
  handle.classList.add("dragging");row.classList.add("is-dragging");
  const drag={handle,row,x:e.clientX,y:e.clientY,frame:0};orderDrag=drag;
  // Compare layout midpoints, never animated hit-test boxes. The dragged row
  // must cross a neighbour's centre before another reorder is possible.
  const update=()=>{
    const rows=[...$("stickers").children], from=state.order.indexOf(id);
    const listTop=$("stickers").getBoundingClientRect().top;
    let target=from;
    for(let index=from+1;index<rows.length;index++) {
      const mid=listTop+rows[index].offsetTop+rows[index].offsetHeight/2;
      if(drag.y>mid+8)target=index;
    }
    for(let index=from-1;index>=0;index--) {
      const mid=listTop+rows[index].offsetTop+rows[index].offsetHeight/2;
      if(drag.y<mid-8)target=index;
    }
    if(target!==from)moveSticker(id,target);
  };
  drag.move=event=>{
    if(event.pointerId!==e.pointerId)return;
    event.preventDefault();drag.x=event.clientX;drag.y=event.clientY;update();
  };
  drag.end=event=>{if(event.type==="blur" || event.pointerId===e.pointerId)finishOrderDrag();};
  const scroll=()=>{
    if(orderDrag!==drag)return;
    const bottom=$("order-actions").getBoundingClientRect().top-24;
    const speed=drag.y>bottom?Math.min(16,(drag.y-bottom)/4):drag.y<120?-Math.min(16,(120-drag.y)/4):0;
    if(speed){window.scrollBy(0,speed);update();}
    drag.frame=requestAnimationFrame(scroll);
  };
  window.addEventListener("pointermove",drag.move,{passive:false});
  window.addEventListener("pointerup",drag.end);window.addEventListener("pointercancel",drag.end);window.addEventListener("blur",drag.end);
  drag.frame=requestAnimationFrame(scroll);
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
const isPhoto=()=>state.source?.kind==="photo";
const sourceElement=()=>$(isPhoto()?"source-photo":"source-video");
function sourceSize(){const media=sourceElement();return {width:media.naturalWidth||media.videoWidth||state.source?.width,height:media.naturalHeight||media.videoHeight||state.source?.height};}
async function setSource(source) {
  revokeMedia(); state.source=source;
  state.sourceURL=await mediaURL("/api/studio/media/"+source.id);
  const photo=isPhoto(), media=sourceElement();
  $("source-video").classList.toggle("hidden",photo);$("source-photo").classList.toggle("hidden",!photo);
  $("playbar").classList.toggle("hidden",photo);$("tab-trim").classList.toggle("hidden",photo);
  $("editor-title").textContent=photo?"Редактор фото":"Редактор видео";$("editor-kind").textContent=photo?"Фото":"Видео";
  await new Promise((resolve,reject)=>{
    media[photo?"onload":"onloadedmetadata"]=resolve;
    media.onerror=()=>reject(new Error("Не удалось открыть файл. Попробуйте JPEG, PNG, WebP или другое видео."));
    media.src=state.sourceURL;if(!photo)media.load();
  });
  $("start").value=0; $("end").value=photo?1:Math.min(3,source.duration).toFixed(3);
  $("zoom").value=1; $("position-x").value=.5; $("position-y").value=.5;
  state.timelineStart=0;state.timelineSpan=Math.min(12,source.duration||1);$("timeline-overview").textContent="Всё видео";
  setShape("original");setTool(photo?"crop":"trim");show("editor");updateCrop();updateTiming();
  if(!photo)void drawFilmstrip();
}
function setShape(shape) {
  state.shape=shape; $("crop-stage").className="crop-stage "+shape;
  document.querySelectorAll("[data-shape]").forEach(b=>{
    b.classList.toggle("selected",b.dataset.shape===shape);
    b.setAttribute("aria-pressed",String(b.dataset.shape===shape));
  });
  updateCrop();
}
function updateCrop() {
  if(!state.source)return;
  const media=sourceElement(), {width:sw,height:sh}=sourceSize(), stage=$("crop-stage");
  if(!sw || !sh || !stage.clientWidth)return;
  const ratio=state.shape==="original"?sw/sh:1;
  stage.style.aspectRatio=String(ratio);
  // Limit the longest side so portrait and landscape both fit the workspace.
  stage.style.height=ratio<1?stage.clientWidth+"px":"auto";
  if(ratio<1)stage.style.width="min(calc(var(--content-height) * .29 * "+ratio+"), 260px)";
  else stage.style.width="";
  const width=stage.clientWidth, height=width/ratio;
  stage.style.height=height+"px";
  const scale=Math.max(width/sw,height/sh)*Number($("zoom").value);
  media.style.width=sw*scale+"px"; media.style.height=sh*scale+"px";
  media.style.left=-(sw*scale-width)*Number($("position-x").value)+"px";
  media.style.top=-(sh*scale-height)*Number($("position-y").value)+"px";
  $("zoom-value").textContent=Math.round(Number($("zoom").value)*100)+"%";
}
function updateTiming() {
  const start=Number($("start").value),end=Number($("end").value),duration=end-start;
  const valid=isPhoto() || Number.isFinite(duration) && duration>=.05 && duration<=3.001 && start>=0 && end<=state.source.duration+.01;
  $("clip-duration").textContent=(Number.isFinite(duration)?duration.toFixed(2):"—")+" / 3 сек";
  $("clip-duration").classList.toggle("invalid", !valid);
  $("render").disabled=!valid;
  $("timing-hint").textContent=valid ? "Двигайте ленту для поиска. Тяните края рамки для обрезки." : "Выберите фрагмент от 0,05 до 3 секунд в пределах видео.";
  $("timeline").max=Math.max(0,state.source.duration-Math.max(.05,Math.min(3,duration||3)));
  $("timeline").value=start;
  updateFilmstrip();
  if(isPhoto())return;
  $("source-video").pause();
  $("source-video").currentTime=Math.min(state.source.duration,Math.max(0,start||0));
  updatePlayState();
}

function setTool(tool, focus=false) {
  state.tool=tool;
  for(const name of ["trim","crop","shape"]) {
    const selected=name===tool;
    $("tab-"+name).classList.toggle("selected",selected);
    $("tab-"+name).setAttribute("aria-selected",String(selected));
    $("tab-"+name).setAttribute("tabindex",selected?"0":"-1");
    $("tools-"+name).classList.toggle("hidden",!selected);
  }
  $("tools-scroll").scrollTop=0;
  if(focus) $("tab-"+tool).focus();
}
function updateViewport() {
  const height=tg?.viewportStableHeight || window.visualViewport?.height || window.innerHeight;
  const root=document.documentElement;
  if(height) root.style.setProperty("--app-height",height+"px");
  for(const edge of ["top","bottom","left","right"]) {
    if(tg?.safeAreaInset?.[edge]!==undefined)root.style.setProperty("--device-"+edge,tg.safeAreaInset[edge]+"px");
    if(tg?.contentSafeAreaInset?.[edge]!==undefined)root.style.setProperty("--content-"+edge,tg.contentSafeAreaInset[edge]+"px");
  }
  if(state.screen==="editor") updateCrop();
}
function updatePlayState() {
  const video=$("source-video"), time=video.currentTime||0;
  $("play-time").textContent=Math.floor(time/60)+":"+(time%60).toFixed(2).padStart(5,"0");
  $("play").setAttribute("aria-label",video.paused?"Воспроизвести фрагмент":"Приостановить фрагмент");
  $("play").innerHTML='<svg class="icon" aria-hidden="true"><use href="#i-'+(video.paused?"play":"pause")+'"/></svg>';
}
function requestDelete() {
  if(state.busy || !state.pack) return;
  state.deleteTarget=state.pack;
  $("delete-title").textContent="Удалить стикерпак?";$("delete-warning").textContent="Восстановить набор и его ссылку не получится.";
  $("cancel-delete").textContent="Оставить набор";
  const pack=state.pack;
  $("delete-description").textContent=pack.status==="draft"
    ? 'Черновик «'+pack.title+'» будет удалён из приложения.'
    : 'Набор «'+pack.title+'» будет навсегда удалён из Telegram и приложения.'+(pack.source_name?" Исходный набор по ссылке останется без изменений.":"");
  $("delete-dialog").showModal();$("delete-dialog").focus();
}
function requestStickerDelete(sticker) {
  if(state.busy)return;
  closeViewer();state.deleteTarget={...state.pack,stickerId:sticker.id};
  $("delete-title").textContent="Удалить стикер?";$("delete-description").textContent="Стикер "+sticker.emoji+" будет удалён из этого набора в Telegram.";
  $("delete-warning").textContent="Остальные стикеры останутся в наборе.";$("cancel-delete").textContent="Оставить стикер";
  $("delete-dialog").showModal();$("delete-dialog").focus();
}
function closeViewer(){const video=$("viewer-media").querySelector?.("video");video?.pause();state.viewerGeneration++;$("sticker-viewer").close();document.body.classList.remove("viewing");$("viewer-media").replaceChildren();}
async function openViewer(index) {
  if(state.busy)return;
  const sticker=state.pack.stickers[index];if(!sticker)return;
  const generation=++state.viewerGeneration;state.viewerIndex=index;
  $("viewer-position").textContent=(index+1)+" из "+state.pack.stickers.length;$("viewer-emoji").textContent=sticker.emoji;
  $("viewer-status").textContent="Загрузка…";$("viewer-media").replaceChildren();
  $("previous-sticker").disabled=index===0;$("next-sticker").disabled=index===state.pack.stickers.length-1;
  if(!$("sticker-viewer").open){$("sticker-viewer").showModal();$("sticker-viewer").focus();}
  $("viewer-kind").textContent=sticker.is_video?"Видео":sticker.is_animated?"Анимация":"Фото";
  $("viewer-edit").disabled=!!sticker.is_animated;
  document.body.classList.add("viewing");
  try {
    const url=await mediaURL("/api/packs/"+state.pack.id+"/stickers/"+encodeURIComponent(sticker.id)+"/file");
    if(generation!==state.viewerGeneration)return;
    const media=document.createElement(sticker.is_video?"video":"img");media.src=url;media.alt=sticker.emoji;
    if(sticker.is_video){media.muted=true;media.loop=true;media.playsInline=true;media.controls=false;media.autoplay=true;media.disablePictureInPicture=true;media.setAttribute("webkit-playsinline","");}
    media.onerror=()=>{$("viewer-status").textContent="Не удалось показать стикер. Откройте набор в Telegram.";};
    $("viewer-media").replaceChildren(media);if(sticker.is_video)media.play().catch(()=>{$("viewer-status").textContent="Нажмите на стикер, чтобы запустить видео.";});
    media.onclick=()=>{if(sticker.is_video){if(media.paused)media.play().catch(()=>{});else media.pause();}};$("viewer-status").textContent=sticker.is_animated?"Для анимированного стикера показана обложка. Анимация доступна в Telegram.":"";
  } catch(e){if(generation===state.viewerGeneration)$("viewer-status").textContent=e.message;}
}
function cancelDelete() {
  $("delete-dialog").close(); state.deleteTarget=null;
}
function editPayload() {
  return {source_id:state.source.id,start:Number($("start").value),end:Number($("end").value),
    shape:state.shape,zoom:Number($("zoom").value),x:Number($("position-x").value),y:Number($("position-y").value)};
}
function back() {
  if(state.busy) return;
  if($("delete-dialog").open){ cancelDelete(); return; }
  if($("sticker-viewer").open){closeViewer();return;}
  if(state.order){state.order=null;renderStickers();return;}
  error("");
  if(state.screen==="preview"){ show("editor"); updateCrop(); return; }
  if(state.screen==="editor"){if(state.replacing){state.replacing=null;task("Открываем набор…",()=>openPack(state.pack.id));}else show("source");return;}
  if(state.screen==="source"){ task("Открываем набор…",()=>openPack(state.pack.id)); return; }
  task("Загружаем наборы…", loadHome);
}
$("back").onclick=back; tg?.BackButton?.onClick(back);
document.querySelector(".brand").onclick=e=>{e.preventDefault();if(!state.busy) task("Загружаем наборы…",loadHome);};
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
$("delete-pack").onclick=requestDelete;
$("edit-stickers").onclick=()=>{state.emojiEdits={};state.order=state.pack.stickers.map(s=>s.id);renderStickers();};
$("cancel-order").onclick=()=>{state.order=null;renderStickers();};
$("save-order").onclick=()=>task("Сохраняем порядок…",async()=>{
  const id=state.pack.id;
  try {
    const changes=Object.entries(state.emojiEdits).filter(([key,value])=>value.trim()!==state.pack.stickers.find(s=>s.id===key)?.emoji);
    if(changes.some(([,value])=>!value.trim()))throw new Error("Введите эмодзи для каждого стикера.");
    for(const [key,value] of changes) await api("/api/packs/"+id+"/stickers/"+encodeURIComponent(key)+"/emoji",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({emoji:value.trim()})});
    await api("/api/packs/"+id+"/order",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({sticker_ids:state.order})});
  } catch(e){
    // Keep typed values on validation errors; refresh after partial Telegram writes.
    if(!/эмодзи|поля/i.test(e.message))await openPack(id);
    throw e;
  }
  invalidateCover(id);await openPack(id);
});
$("close-viewer").onclick=closeViewer;
$("sticker-viewer").oncancel=closeViewer;
$("previous-sticker").onclick=()=>openViewer(state.viewerIndex-1);
$("next-sticker").onclick=()=>openViewer(state.viewerIndex+1);
$("delete-sticker").onclick=()=>requestStickerDelete(state.pack.stickers[state.viewerIndex]);
$("cancel-delete").onclick=cancelDelete;
$("delete-dialog").oncancel=()=>{state.deleteTarget=null;};
$("confirm-delete").onclick=()=>{
  const target=state.deleteTarget;
  if(!target || state.busy) return;
  cancelDelete();
  task(target.stickerId?"Удаляем стикер…":"Удаляем стикерпак…",async()=>{
    if(target.stickerId){await api("/api/packs/"+target.id+"/stickers/"+encodeURIComponent(target.stickerId),{method:"DELETE"});invalidateCover(target.id);await openPack(target.id);return;}
    await api("/api/packs/"+target.id,{method:"DELETE"});
    state.pack=null;
    await loadHome(); tg?.HapticFeedback?.notificationOccurred("success");
  });
};
$("add-sticker").onclick=()=>{state.replacing=null;state.publishEmoji="🙂";error("");revokeMedia();$("video-file").value="";show("source");};
$("link-form").onsubmit=e=>{e.preventDefault();task("Загружаем и подготавливаем видео…",async()=>setSource(await json("/api/studio/link",{url:$("video-link").value.trim()})));};
$("video-file").onchange=()=>{
  const file=$("video-file").files[0]; if(!file)return;
  if(file.size>50*1024*1024){error("Файл должен быть не больше 50 МБ");return;}
  task("Подготавливаем файл…",async()=>{
    const form=new FormData(); form.append("video",file);
    await setSource(await (await api("/api/studio/upload",{method:"POST",body:form})).json());
  });
};
document.querySelectorAll("[data-shape]").forEach(b=>b.onclick=()=>setShape(b.dataset.shape));
for(const name of ["trim","crop","shape"]) {
  $("tab-"+name).onclick=()=>setTool(name);
  $("tab-"+name).onkeydown=e=>{
    const names=isPhoto()?["crop","shape"]:["trim","crop","shape"], index=names.indexOf(name);
    if(!["ArrowLeft","ArrowRight","Home","End"].includes(e.key)) return;
    e.preventDefault();
    const next=e.key==="Home"?0:e.key==="End"?names.length-1:(index+(e.key==="ArrowRight"?1:names.length-1))%names.length;
    setTool(names[next],true);
  };
}
$("reset-crop").onclick=()=>{
  $("zoom").value=1; $("position-x").value=.5; $("position-y").value=.5; updateCrop();
};
["zoom","position-x","position-y"].forEach(id=>$(id).oninput=updateCrop);
["start","end"].forEach(id=>$(id).oninput=updateTiming);
$("timeline").oninput=()=>{
  const length=Math.min(3,Number($("end").value)-Number($("start").value));
  const start=Number($("timeline").value);
  $("start").value=start.toFixed(2); $("end").value=Math.min(state.source.duration,start+Math.max(.05,length)).toFixed(2); updateTiming();
};
$("play").onclick=()=>{
  if($("render").disabled) return;
  const video=$("source-video"); if(!video.paused){video.pause();return;}
  video.currentTime=Number($("start").value); video.play().catch(()=>error("Не удалось запустить видео"));
};
$("source-video").ontimeupdate=()=>{if($("source-video").currentTime>=Number($("end").value)) $("source-video").pause();updatePlayState();};
$("source-video").onplay=updatePlayState;
$("source-video").onpause=updatePlayState;
$("render").onclick=()=>task("Создаём стикер…",async()=>{
  const payload=editPayload(),key=JSON.stringify(payload);
  if(state.renderKey!==key){state.render=await json("/api/studio/render",payload);state.renderKey=key;}
  const photo=isPhoto();
  $("result-video").classList.toggle("hidden",photo);$("result-photo").classList.toggle("hidden",!photo);$("result-play").classList.toggle("hidden",photo);
  $(photo?"result-photo":"result-video").src=await mediaURL("/api/studio/media/"+state.render.id+(photo?"":"?preview=true"));
  $("publish").textContent=state.replacing?"Сохранить стикер":"Добавить в набор";show("preview");
});
function updateResultPlayState() {
  const paused=$("result-video").paused;
  $("result-play").setAttribute("aria-label",paused?"Воспроизвести предпросмотр":"Приостановить предпросмотр");
  $("result-play").innerHTML='<svg class="icon" aria-hidden="true"><use href="#i-'+(paused?"play":"pause")+'"/></svg>';
}
$("result-play").onclick=()=>{
  const video=$("result-video");
  if(video.paused)video.play().catch(()=>error("Не удалось запустить предпросмотр"));else video.pause();
};
$("result-video").onplay=updateResultPlayState;
$("result-video").onpause=updateResultPlayState;
$("edit-again").onclick=()=>{show("editor");updateCrop();};
$("publish").onclick=()=>task("Сохраняем стикер…",async()=>{
  await json("/api/studio/packs/"+state.pack.id+"/publish",{render_id:state.render.id,emoji:state.publishEmoji,replace_id:state.replacing});
  tg?.HapticFeedback?.notificationOccurred("success");invalidateCover(state.pack.id);revokeMedia();await openPack(state.pack.id);
  state.replacing=null;state.emojiEdits={};state.order=state.pack.stickers.map(s=>s.id);renderStickers();
});
$("viewer-edit").onclick=()=>{
  const sticker=state.pack.stickers[state.viewerIndex];closeViewer();
  task("Открываем редактор…",async()=>{
    const source=await json("/api/studio/packs/"+state.pack.id+"/stickers/"+encodeURIComponent(sticker.id)+"/edit",{});
    state.replacing=sticker.id;state.publishEmoji=sticker.emoji;await setSource(source);
  });
};
const pointers=new Map();
let gesture=null;
function rebaseGesture() {
  const points=[...pointers.values()];
  if(!points.length){gesture=null;return;}
  const rect=$("crop-stage").getBoundingClientRect?.()||{left:0,top:0};
  const centre={x:points.reduce((sum,p)=>sum+p.x,0)/points.length-rect.left,y:points.reduce((sum,p)=>sum+p.y,0)/points.length-rect.top};
  gesture={centre,rect,zoom:Number($("zoom").value),x:Number($("position-x").value),y:Number($("position-y").value),
    distance:points.length>1?Math.hypot(points[1].x-points[0].x,points[1].y-points[0].y):0};
}
const clamp=(value,min=0,max=1)=>Math.max(min,Math.min(max,value));
$("crop-stage").onpointerdown=e=>{
  if(!state.source || state.busy) return;
  e.preventDefault(); $("source-video").pause(); setTool("crop");
  $("crop-stage").setPointerCapture(e.pointerId);
  $("crop-stage").classList.add("dragging");
  pointers.set(e.pointerId,{x:e.clientX,y:e.clientY}); rebaseGesture();
};
$("crop-stage").onpointermove=e=>{
  if(!pointers.has(e.pointerId) || !gesture) return;
  e.preventDefault(); pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  const points=[...pointers.values()];
  const distance=points.length>1?Math.hypot(points[1].x-points[0].x,points[1].y-points[0].y):0;
  const zoom=gesture.distance>0 && distance>0?clamp(gesture.zoom*distance/gesture.distance,1,3):gesture.zoom;
  const centre={x:points.reduce((sum,p)=>sum+p.x,0)/points.length-gesture.rect.left,y:points.reduce((sum,p)=>sum+p.y,0)/points.length-gesture.rect.top};
  const {width,height}=sourceSize(),stageWidth=$("crop-stage").clientWidth,stageHeight=Number.parseFloat($("crop-stage").style.height)||stageWidth;
  const base=Math.max(stageWidth/width,stageHeight/height);
  const ratio=zoom/gesture.zoom;
  const overflowX=width*base*zoom-stageWidth,overflowY=height*base*zoom-stageHeight;
  // Keep the image under the fingers in place while zooming and panning.
  if(overflowX>.5)$("position-x").value=clamp(((gesture.centre.x+(width*base*gesture.zoom-stageWidth)*gesture.x)*ratio-centre.x)/overflowX);
  if(overflowY>.5)$("position-y").value=clamp(((gesture.centre.y+(height*base*gesture.zoom-stageHeight)*gesture.y)*ratio-centre.y)/overflowY);
  $("zoom").value=zoom;
  updateCrop();
};
function releasePointer(e) {
  pointers.delete(e.pointerId); rebaseGesture();
  if(!pointers.size) $("crop-stage").classList.remove("dragging");
}
$("crop-stage").onpointerup=releasePointer;
$("crop-stage").onpointercancel=releasePointer;
$("crop-stage").onlostpointercapture=releasePointer;

function timeLabel(time){return Math.floor(time/60)+":"+(time%60).toFixed(2).padStart(5,"0");}
function updateFilmstrip() {
  if(!state.source || isPhoto())return;
  const span=state.timelineSpan||Math.min(12,state.source.duration),start=Number($("start").value),end=Number($("end").value);
  state.timelineStart=clamp(state.timelineStart||0,0,Math.max(0,state.source.duration-span));
  if(start<state.timelineStart)state.timelineStart=start;
  if(end>state.timelineStart+span)state.timelineStart=end-span;
  $("trim-selection").style.left=((start-state.timelineStart)/span*100)+"%";
  $("trim-selection").style.width=((end-start)/span*100)+"%";
  $("trim-start-label").textContent=timeLabel(start);$("trim-end-label").textContent=timeLabel(end);
  for(const [id,value] of [["trim-left",start],["trim-right",end]]) {
    $(id).setAttribute("aria-valuemax",state.source.duration);$(id).setAttribute("aria-valuenow",value.toFixed(2));
    $(id).setAttribute("aria-valuetext",timeLabel(value));
  }
  // The film image spans the complete source and moves behind the trim window.
  $("film-frames").style.width=(state.source.duration/span*100)+"%";
  $("film-frames").style.left=(-state.timelineStart/span*100)+"%";
}
async function drawFilmstrip() {
  const source=state.source,url=state.sourceURL,frames=$("film-frames");frames.replaceChildren();
  const video=document.createElement("video");video.muted=true;video.playsInline=true;video.preload="auto";
  try {
    await new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=reject;video.src=url;video.load();});
    if(typeof document.createElement("canvas").getContext!=="function")return;
    for(let index=0;index<16;index++) {
      if(state.source!==source)return;
      const time=Math.min(source.duration-.01,(index+.5)*source.duration/16);
      await new Promise((resolve,reject)=>{video.onseeked=resolve;video.onerror=reject;video.currentTime=time;});
      if(state.source!==source)return;
      const canvas=document.createElement("canvas");canvas.width=96;canvas.height=64;
      const ctx=canvas.getContext("2d");ctx.drawImage(video,0,0,96,64);frames.append(canvas);
    }
  } catch {} finally {video.pause();video.removeAttribute("src");video.load();}
}
function changeTrim(part,delta,baseStart=Number($("start").value),baseEnd=Number($("end").value)) {
  const total=state.source.duration;
  if(part==="left")$("start").value=clamp(baseStart+delta,Math.max(0,baseEnd-3),baseEnd-.05);
  else if(part==="right")$("end").value=clamp(baseEnd+delta,baseStart+.05,Math.min(total,baseStart+3));
  else {const start=clamp(baseStart+delta,0,total-(baseEnd-baseStart));$("start").value=start;$("end").value=start+baseEnd-baseStart;}
  updateTiming();
}
$("timeline-overview").onclick=()=>{
  if(!state.source || isPhoto())return;
  const detailed=state.timelineSpan>=state.source.duration;
  state.timelineSpan=detailed?Math.min(12,state.source.duration):state.source.duration;
  state.timelineStart=Math.max(0,Number($("start").value)-state.timelineSpan/3);
  $("timeline-overview").textContent=detailed?"Всё видео":"Точнее";updateFilmstrip();
};
let trimDrag=null;
$("filmstrip").onpointerdown=e=>{
  if(!state.source || isPhoto() || state.busy || (e.button!==undefined && e.button!==0))return;
  e.preventDefault();$("filmstrip").setPointerCapture(e.pointerId);
  const part=e.target.id==="trim-left"?"left":e.target.id==="trim-right"?"right":e.target.id==="trim-move"?"move":"pan";
  trimDrag={id:e.pointerId,x:e.clientX,part,start:Number($("start").value),end:Number($("end").value),span:state.timelineSpan};
};
$("filmstrip").onpointermove=e=>{
  if(!trimDrag || trimDrag.id!==e.pointerId)return;
  e.preventDefault();const drag=trimDrag;
  const delta=(e.clientX-drag.x)/$("filmstrip").clientWidth*drag.span*(drag.part==="pan"?-1:1);
  changeTrim(drag.part,delta,drag.start,drag.end);
};
for(const event of ["onpointerup","onpointercancel","onlostpointercapture"])$("filmstrip")[event]=()=>{trimDrag=null;};
for(const [id,part] of [["trim-left","left"],["trim-right","right"],["trim-move","move"]])$(id).onkeydown=e=>{
  if(!["ArrowLeft","ArrowRight"].includes(e.key) || !state.source)return;
  e.preventDefault();changeTrim(part,(e.key==="ArrowRight"?1:-1)*(e.shiftKey?.5:.05));
};
function zoomBy(factor){if(!state.source)return;$("zoom").value=clamp(Number($("zoom").value)*factor,1,3);updateCrop();}
$("zoom-in").onclick=()=>zoomBy(1.15);$("zoom-out").onclick=()=>zoomBy(1/1.15);
$("crop-stage").onwheel=e=>{if(state.screen!=="editor")return;e.preventDefault();zoomBy(e.deltaY<0?1.08:1/1.08);};
$("crop-stage").setAttribute("tabindex","0");
$("crop-stage").onkeydown=e=>{
  if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","+","-"].includes(e.key))return;
  e.preventDefault();if(e.key==="+"||e.key==="-"){zoomBy(e.key==="+"?1.1:1/1.1);return;}
  const horizontal=e.key==="ArrowLeft"||e.key==="ArrowRight",input=$(horizontal?"position-x":"position-y");
  input.value=clamp(Number(input.value)+(["ArrowRight","ArrowDown"].includes(e.key)?.05:-.05));updateCrop();
};
// Pointer focus stays quiet. Keyboard navigation still gets a visible focus ring.
document.addEventListener?.("keydown",e=>{if(e.key==="Tab")document.body.classList.add("keyboard-navigation");});
document.addEventListener?.("pointerdown",()=>document.body.classList.remove("keyboard-navigation"));
$("sticker-viewer").onkeydown=e=>{if(e.key==="ArrowLeft")void openViewer(state.viewerIndex-1);if(e.key==="ArrowRight")void openViewer(state.viewerIndex+1);};
let swipeStart=null;
$("viewer-media").onpointerdown=e=>{swipeStart={x:e.clientX,y:e.clientY};};
$("viewer-media").onpointerup=e=>{
  if(swipeStart && Math.abs(e.clientX-swipeStart.x)>50 && Math.abs(e.clientY-swipeStart.y)<60)void openViewer(state.viewerIndex+(e.clientX<swipeStart.x?1:-1));
  swipeStart=null;
};
$("dismiss-fullscreen").onclick=()=>$("fullscreen-prompt").classList.add("hidden");
$("enter-fullscreen").onclick=()=>{try{tg?.requestFullscreen?.();}catch{}$("fullscreen-prompt").classList.add("hidden");};
if(tg?.initData && typeof tg.requestFullscreen==="function" && (!tg.isVersionAtLeast || tg.isVersionAtLeast("8.0")) && !tg.isFullscreen)$("fullscreen-prompt").classList.remove("hidden");
tg?.onEvent?.("fullscreenChanged",()=>{updateViewport();if(tg.isFullscreen)$("fullscreen-prompt").classList.add("hidden");});
window.addEventListener("resize",updateViewport);
window.visualViewport?.addEventListener("resize",updateViewport);
tg?.onEvent?.("viewportChanged",updateViewport);
tg?.onEvent?.("contentSafeAreaChanged",updateViewport);
tg?.onEvent?.("safeAreaChanged",updateViewport);
tg?.onEvent?.("fullscreenChanged",updateViewport);
window.addEventListener("beforeunload",()=>{for(const item of mediaCache.values())if(item.url)URL.revokeObjectURL(item.url);});
tg?.ready(); tg?.expand();
document.body.classList.toggle("in-telegram",!!tg?.initData);
try { tg?.setHeaderColor?.("#1f1f1f"); tg?.setBackgroundColor?.("#1f1f1f"); } catch {}
updateViewport();
if(!tg?.initData) {
  $("auth-notice").classList.remove("hidden"); $("empty").classList.remove("hidden");
  $("create").classList.add("hidden");$("collection-heading").classList.add("hidden");
  $("create").disabled=true; $("create-empty").disabled=true;
} else {task("Загружаем ваши наборы…",loadHome);}
