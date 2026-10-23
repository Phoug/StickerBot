const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor(id) {
    this.id=id; this.value=""; this.children=[]; this.dataset={}; this.style={};
    this.disabled=false; this.paused=true; this.videoWidth=640; this.videoHeight=360; this.clientWidth=320;
    const classes=new Set();
    this.classList={add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),
      toggle(c,force){if(force===undefined)force=!classes.has(c); if(force)classes.add(c);else classes.delete(c);}};
  }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this[name]=value;}
  removeAttribute(name){delete this[name];}
  pause(){this.paused=true;}
  play(){this.paused=false;return Promise.resolve();}
  load(){queueMicrotask(()=>this.onloadedmetadata?.());}
  reset(){}
}

function boot(responder, authenticated=true){
  const elements=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
  const screens=["home","new","pack","source","editor","preview"].map(get);
  const shapes=["square","rounded","circle"].map(shape=>{const e=new Element(shape);e.dataset.shape=shape;return e;});
  let blobId=0;
  const requests=[];
  const context=vm.createContext({
    console, Blob, FormData, queueMicrotask,
    URL:{createObjectURL:()=> "blob:test-"+(++blobId),revokeObjectURL:()=>{}},
    window:{Telegram:authenticated?{WebApp:{initData:"signed-test",ready(){},expand(){}}}:undefined,scrollTo(){},addEventListener(){}},
    document:{getElementById:get,querySelector:()=>get("brand"),querySelectorAll:selector=>selector===".screen"?screens:shapes,
      createElement:tag=>new Element(tag),body:new Element("body")},
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
  ui.shapes.find(s=>s.dataset.shape==="circle").onclick();
  ui.get("start").value="0.2";ui.get("end").value="2.5";ui.get("zoom").value="1.4";
  ui.get("render").onclick();await idle(ui);
  const request=ui.requests.find(r=>r.path==="/api/studio/render");
  const edit=JSON.parse(request.options.body);
  assert.equal(edit.shape,"circle");assert.equal(edit.start,.2);assert.equal(edit.end,2.5);assert.equal(edit.zoom,1.4);
  assert.equal(ui.get("preview").classList.contains("hidden"),false);
  ui.get("emoji").value="😂";
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
