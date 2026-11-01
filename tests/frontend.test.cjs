const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor(id) {
    this.id=id; this.value=""; this.children=[]; this.dataset={}; this.style={setProperty(name,value){this[name]=value;}};
    this.disabled=false; this.paused=true; this.videoWidth=640; this.videoHeight=360; this.clientWidth=320;
    const classes=new Set();
    this.classList={add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),
      toggle(c,force){if(force===undefined)force=!classes.has(c); if(force)classes.add(c);else classes.delete(c);}};
  }
  append(...children){for(const child of children){this.children=this.children.filter(item=>item!==child);this.children.push(child);}}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this[name]=value;}
  removeAttribute(name){delete this[name];}
  pause(){this.paused=true;}
  play(){this.paused=false;return Promise.resolve();}
  load(){queueMicrotask(()=>this.onloadedmetadata?.());}
  reset(){}
  focus(){this.focused=true;}
  showModal(){this.open=true;}
  close(){this.open=false;}
  setPointerCapture(){}
}

function boot(responder, authenticated=true, sdk={}){
  const elements=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
  const screens=["home","new","pack","source","editor","preview"].map(get);
  const shapes=["original","square","rounded","circle"].map(shape=>{const e=new Element(shape);e.dataset.shape=shape;return e;});
  let blobId=0;
  const requests=[];
  const context=vm.createContext({
    console, Blob, FormData, queueMicrotask,
    URL:{createObjectURL:()=> "blob:test-"+(++blobId),revokeObjectURL:()=>{}},
    window:{Telegram:authenticated?{WebApp:{initData:"signed-test",ready(){},expand(){},...sdk}}:undefined,scrollTo(){},addEventListener(){}},
    document:{getElementById:get,querySelector:()=>get("brand"),querySelectorAll:selector=>selector===".screen"?screens:selector==="[data-shape]"?shapes:[],
      createElement:tag=>new Element(tag),body:new Element("body"),documentElement:new Element("html")},
    fetch:async(path,options={})=>{
      requests.push({path,options});
      const response=await responder(path,options);
      return {ok:!response.status || response.status<400,status:response.status||200,
        json:async()=>response.data,blob:async()=>new Blob(["video"])};
    }
  });
  vm.runInContext(fs.readFileSync("app/webapp/app.js","utf8"),context);
  return {get,requests,shapes,context};
}
async function idle(ui){
  for(let attempt=0;attempt<50;attempt++){
    await new Promise(resolve=>setImmediate(resolve));
    if(!vm.runInContext("state.busy",ui.context))return;
  }
  throw Error("UI operation did not finish");
}
const submit={preventDefault(){}};

test("outside Telegram no private API is called",async()=>{
  const ui=boot(()=>{throw Error("Unexpected network");},false);
  await idle(ui);
  assert.equal(ui.requests.length,0);
  assert.equal(ui.get("create").disabled,true);
  assert.equal(ui.get("auth-notice").classList.contains("hidden"),false);
});

test("create draft, load link, crop circle, preview, publish and return to pack",async()=>{
  const pack={id:"p1",name:"reactions_by_test_bot",title:"Реакции",count:0,status:"draft",stickers:[]};
  const ui=boot((path,options)=>{
    if(path==="/api/packs")return {data:options.method?pack:{packs:[]}};
    if(path==="/api/packs/p1")return {data:{...pack}};
    if(path==="/api/studio/link")return {data:{id:"source1",duration:8}};
    if(path.startsWith("/api/studio/media/"))return {data:{}};
    if(path==="/api/studio/render")return {data:{id:"render1",duration:2.3}};
    if(path==="/api/studio/packs/p1/publish"){pack.status="ready";pack.count=1;return {data:{...pack}};}
    throw Error("Unexpected "+path);
  });
  await idle(ui);
  ui.get("create").onclick();
  ui.get("pack-title").value="Реакции";
  ui.get("pack-form").onsubmit(submit);await idle(ui);
  assert.equal(ui.get("pack").classList.contains("hidden"),false);
  ui.get("add-sticker").onclick();
  ui.get("video-link").value="https://youtube.com/watch?v=example";
  ui.get("link-form").onsubmit(submit);await idle(ui);
  assert.equal(ui.get("editor").classList.contains("hidden"),false);
  assert.equal(ui.get("app-shell").classList.contains("is-editor"),true);
  assert.equal(ui.get("tab-trim")["aria-selected"],"true");
  ui.get("tab-trim").onkeydown({key:"ArrowRight",preventDefault(){}});
  assert.equal(ui.get("tab-crop")["aria-selected"],"true");
  assert.equal(ui.get("tab-crop").focused,true);
  assert.equal(ui.get("tools-trim").classList.contains("hidden"),true);
  assert.equal(vm.runInContext("state.shape",ui.context),"original");
  ui.shapes.find(s=>s.dataset.shape==="square").onclick();
  // Drag and pinch update the same crop values sent to the server.
  const stage=ui.get("crop-stage");
  const pointer=(id,x,y)=>({pointerId:id,clientX:x,clientY:y,preventDefault(){}});
  stage.onpointerdown(pointer(1,100,100));
  stage.onpointermove(pointer(1,140,100));
  assert.ok(Number(ui.get("position-x").value)<.5);
  stage.onpointerdown(pointer(2,160,100));
  stage.onpointermove(pointer(2,200,100));
  assert.equal(Number(ui.get("zoom").value),3);
  stage.onpointercancel(pointer(2,200,100));
  stage.onpointerup(pointer(1,140,100));
  assert.equal(stage.classList.contains("dragging"),false);
  ui.get("reset-crop").onclick();
  assert.equal(Number(ui.get("zoom").value),1);
  assert.equal(Number(ui.get("position-x").value),.5);
  assert.equal(ui.get("zoom-value").textContent,"100%");
  ui.get("end").value="6";ui.get("end").oninput();
  assert.equal(ui.get("render").disabled,true);
  assert.match(ui.get("timing-hint").textContent,/0,05 до 3 секунд/);
  ui.shapes.find(s=>s.dataset.shape==="circle").onclick();
  ui.get("start").value="0.2";ui.get("end").value="2.5";ui.get("zoom").value="1.4";
  ui.get("render").onclick();await idle(ui);
  const request=ui.requests.find(r=>r.path==="/api/studio/render");
  const edit=JSON.parse(request.options.body);
  assert.equal(edit.shape,"circle");assert.equal(edit.start,.2);assert.equal(edit.end,2.5);assert.equal(edit.zoom,1.4);
  assert.equal(ui.get("preview").classList.contains("hidden"),false);
  ui.get("publish").onclick();await idle(ui);
  assert.equal(ui.get("pack").classList.contains("hidden"),false);
  assert.equal(ui.get("telegram-link").href,"https://t.me/addstickers/reactions_by_test_bot");
  assert.equal(vm.runInContext("state.source",ui.context),null);
  assert.ok(ui.requests.every(r=>r.options.headers["X-Telegram-Init-Data"]==="signed-test"));
});

test("failed import exposes the saved draft and retry action",async()=>{
  const pack={id:"p1",name:"copy_by_test_bot",title:"Копия",count:0,status:"import_pending",stickers:[]};
  let attempts=0;
  const ui=boot((path,options)=>{
    if(path==="/api/packs")return {data:options.method?pack:{packs:[]}};
    if(path==="/api/packs/p1")return {data:{...pack}};
    if(path==="/api/packs/p1/import"){
      if(++attempts===1)return {status:502,data:{detail:"Временная ошибка Telegram"}};
      pack.status="ready";pack.count=55;return {data:{...pack}};
    }
    throw Error("Unexpected "+path);
  });
  await idle(ui);
  ui.get("create").onclick();ui.get("mode-import").onclick();
  ui.get("pack-title").value="Копия";ui.get("pack-link").value="https://t.me/addstickers/Original";
  ui.get("pack-form").onsubmit(submit);await idle(ui);
  assert.equal(ui.get("pack").classList.contains("hidden"),false);
  assert.equal(ui.get("resume-import").classList.contains("hidden"),false);
  assert.equal(ui.get("error").textContent,"Временная ошибка Telegram");
  ui.get("resume-import").onclick();await idle(ui);
  assert.equal(ui.get("resume-import").classList.contains("hidden"),true);
  assert.equal(attempts,2);
});

test("expired auth yields a useful recovery message",async()=>{
  const ui=boot(()=>({status:401,data:{detail:"expired"}}));
  await idle(ui);
  assert.match(ui.get("error").textContent,/откройте его заново/);
  assert.equal(ui.get("busy").classList.contains("hidden"),true);
});

test("deletion requires confirmation and cancellation never calls the API",async()=>{
  const pack={id:"p1",title:"Мой набор",name:"my_by_bot",status:"ready",count:0,source_name:"Original",stickers:[]};
  let deleted=false;
  const ui=boot((path,options)=>{
    if(path==="/api/packs")return {data:{packs:deleted?[]:[pack]}};
    if(path==="/api/packs/p1" && options.method==="DELETE"){deleted=true;return {status:204};}
    if(path==="/api/packs/p1")return {data:pack};
    throw Error("Unexpected "+path);
  });
  await idle(ui);
  ui.get("packs").children[0].onclick();await idle(ui);
  ui.get("delete-pack").onclick();
  assert.equal(ui.get("delete-dialog").open,true);
  assert.match(ui.get("delete-description").textContent,/навсегда удалён из Telegram/);
  assert.match(ui.get("delete-description").textContent,/Исходный набор/);
  assert.equal(deleted,false);
  ui.get("cancel-delete").onclick();
  assert.equal(ui.get("delete-dialog").open,false);
  assert.equal(deleted,false);
  ui.get("delete-pack").onclick();ui.get("back").onclick();
  assert.equal(ui.get("delete-dialog").open,false);
  assert.equal(ui.get("pack").classList.contains("hidden"),false);
  ui.get("delete-pack").onclick();ui.get("confirm-delete").onclick();await idle(ui);
  assert.equal(deleted,true);
  assert.equal(ui.get("home").classList.contains("hidden"),false);
  assert.equal(ui.get("packs").children.length,0);
  assert.equal(ui.get("empty").classList.contains("hidden"),false);
});

test("failed deletion keeps the pack and shows the Telegram error",async()=>{
  const pack={id:"p1",title:"Мой набор",name:"my_by_bot",status:"ready",count:0,stickers:[]};
  const ui=boot((path,options)=>{
    if(path==="/api/packs")return {data:{packs:[pack]}};
    if(options.method==="DELETE")return {status:502,data:{detail:"Telegram недоступен"}};
    return {data:pack};
  });
  await idle(ui);
  ui.get("packs").children[0].onclick();await idle(ui);
  ui.get("delete-pack").onclick();ui.get("confirm-delete").onclick();await idle(ui);
  assert.equal(ui.get("pack").classList.contains("hidden"),false);
  assert.equal(ui.get("error").textContent,"Telegram недоступен");
  assert.equal(ui.get("delete-dialog").open,false);
});

test("Telegram safe areas update globally and fixed workspace uses stable height",async()=>{
  const callbacks={};const sdk={viewportHeight:500,viewportStableHeight:700,
    safeAreaInset:{top:44,bottom:34,left:0,right:0},contentSafeAreaInset:{top:56,bottom:0,left:0,right:0},
    onEvent(name,fn){callbacks[name]=fn;}};
  const ui=boot(()=>({data:{packs:[]}}),true,sdk);await idle(ui);
  const root=vm.runInContext("document.documentElement",ui.context);
  assert.equal(root.style["--app-height"],"700px");assert.equal(root.style["--device-top"],"44px");assert.equal(root.style["--content-top"],"56px");
  sdk.safeAreaInset.top=20;callbacks.safeAreaChanged();assert.equal(root.style["--device-top"],"20px");
  assert.equal(typeof callbacks.fullscreenChanged,"function");
});

test("sticker viewer, order cancellation and save, and individual deletion",async()=>{
  const pack={id:"p1",title:"Реакции",name:"my_by_bot",status:"ready",count:3,
    stickers:[0,1,2].map(i=>({id:"s"+i,emoji:"🙂",preview_id:"thumb"+i}))};
  const ui=boot((path,options)=>{
    if(path==="/api/packs")return {data:{packs:[pack]}};
    if(path.endsWith("/order")){const ids=JSON.parse(options.body).sticker_ids;pack.stickers=ids.map(id=>pack.stickers.find(s=>s.id===id));return {data:pack};}
    if(options.method==="DELETE"){pack.stickers=pack.stickers.filter(s=>!path.endsWith("/"+s.id));pack.count=pack.stickers.length;return {data:pack};}
    return {data:pack};
  });await idle(ui);
  ui.get("packs").children[0].onclick();await idle(ui);
  await vm.runInContext("openViewer(0)",ui.context);
  assert.equal(ui.get("sticker-viewer").open,true);assert.equal(ui.get("viewer-position").textContent,"1 из 3");
  ui.get("back").onclick();assert.equal(ui.get("sticker-viewer").open,false);
  ui.get("edit-stickers").onclick();vm.runInContext('moveSticker("s0",2)',ui.context);
  assert.equal(vm.runInContext('state.order.join(",")',ui.context),"s1,s2,s0");
  ui.get("cancel-order").onclick();assert.equal(ui.requests.some(r=>r.options.method==="PUT"),false);
  ui.get("edit-stickers").onclick();vm.runInContext('moveSticker("s0",2)',ui.context);
  ui.get("save-order").onclick();await idle(ui);assert.equal(pack.stickers[2].id,"s0");
  await vm.runInContext("openViewer(1)",ui.context);ui.get("delete-sticker").onclick();
  assert.equal(ui.get("delete-dialog").open,true);assert.equal(pack.count,3);
  ui.get("confirm-delete").onclick();await idle(ui);assert.equal(pack.count,2);
  assert.equal(pack.stickers.some(s=>s.id==="s2"),false);assert.equal(ui.get("pack").classList.contains("hidden"),false);
});


test("reordering preserves loaded tiles and handle supports keyboard movement",async()=>{
  const pack={id:"p1",title:"Test",name:"test_by_bot",status:"ready",count:3,
    stickers:[0,1,2].map(i=>({id:"s"+i,emoji:"🙂",preview_id:"t"+i}))};
  const ui=boot(path=>({data:path==="/api/packs"?{packs:[pack]}:pack}));
  await idle(ui);ui.get("packs").children[0].onclick();await idle(ui);
  ui.get("edit-stickers").onclick();
  const row=ui.get("stickers").children[0];
  row.children[0].onkeydown({key:"ArrowDown",preventDefault(){}});row.children[0].onkeydown({key:"ArrowDown",preventDefault(){}});
  assert.equal(vm.runInContext('state.order.join(",")',ui.context),"s1,s2,s0");
  assert.equal(ui.get("stickers").children[2],row);
});


test("empty home has one create action and supported fullscreen is opt-in",async()=>{
  let requests=0;
  const ui=boot(()=>({data:{packs:[]}}),true,{requestFullscreen(){requests++;},isVersionAtLeast:()=>true});
  await idle(ui);
  assert.equal(ui.get("create").classList.contains("hidden"),true);
  assert.equal(ui.get("empty").classList.contains("hidden"),false);
  assert.equal(ui.get("fullscreen-prompt").classList.contains("hidden"),false);
  assert.equal(requests,0);ui.get("enter-fullscreen").onclick();assert.equal(requests,1);
});

test("video viewer has no native controls and cached media survives home navigation",async()=>{
  const pack={id:"p",title:"Test",name:"test",status:"ready",count:1,stickers:[{id:"s",emoji:"🙂",preview_id:"t",is_video:true}]};
  const ui=boot(path=>({data:path==="/api/packs"?{packs:[pack]}:pack}));await idle(ui);
  ui.get("packs").children[0].onclick();await idle(ui);
  await vm.runInContext("openViewer(0)",ui.context);
  const video=ui.get("viewer-media").children[0];
  assert.equal(video.controls,false);assert.equal(video.playsInline,true);assert.equal(video.loop,true);
  ui.get("close-viewer").onclick();await vm.runInContext("loadHome()",ui.context);
  ui.get("packs").children[0].onclick();await idle(ui);await vm.runInContext("openViewer(0)",ui.context);
  assert.equal(ui.requests.filter(r=>r.path.endsWith("/stickers/s/file")).length,1);
});

test("trim gestures stay within source duration and three second limit",async()=>{
  const ui=boot(()=>({data:{packs:[]}}));await idle(ui);
  vm.runInContext('state.source={id:"video",duration:60};state.timelineSpan=12;$("start").value=10;$("end").value=13;',ui.context);
  vm.runInContext('changeTrim("right",30)',ui.context);assert.equal(Number(ui.get("end").value),13);
  vm.runInContext('changeTrim("move",100)',ui.context);assert.equal(Number(ui.get("end").value),60);assert.equal(Number(ui.get("start").value),57);
  vm.runInContext('changeTrim("left",-100)',ui.context);assert.equal(Number(ui.get("start").value),57);
  vm.runInContext('changeTrim("left",100)',ui.context);assert.ok(Number(ui.get("end").value)-Number(ui.get("start").value)>=.0499);
});
