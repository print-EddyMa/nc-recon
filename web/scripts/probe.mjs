import puppeteer from "puppeteer-core";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const b=await puppeteer.launch({executablePath:CHROME,headless:false,args:["--no-sandbox","--window-size=1500,950"],defaultViewport:{width:1400,height:880}});
const p=await b.newPage();
p.on("console",m=>console.log("  [console."+m.type()+"]",m.text()));
p.on("pageerror",e=>console.log("  [pageerror]",e.message));
p.on("requestfailed",r=>console.log("  [reqfail]",r.url().slice(0,90),r.failure()?.errorText));
await p.goto("http://localhost:4173/",{waitUntil:"networkidle2"});
await p.evaluate(()=>{[...document.querySelectorAll("button")].find(x=>/damage map/i.test(x.textContent||""))?.click();});
await new Promise(r=>setTimeout(r,6000));
const info=await p.evaluate(()=>{
  const c=document.querySelector('[aria-label^="Damage map"]');
  const canvases=[...document.querySelectorAll("canvas")].map(cv=>({w:cv.width,h:cv.height,cls:cv.className}));
  let gl=null;
  try{const t=document.createElement("canvas");gl=!!(t.getContext("webgl2")||t.getContext("webgl"));}catch(e){gl="err:"+e.message;}
  return {
    containerRect: c? {w:c.clientWidth,h:c.clientHeight}: "no container",
    mlCanvas: !!document.querySelector(".maplibregl-canvas"),
    canvases,
    webglSupported: gl,
    bodyH: document.body.clientHeight, rootH: document.getElementById("root")?.clientHeight,
    maplibreErr: window.__mlerr || null,
  };
});
console.log(JSON.stringify(info,null,2));
await b.close();
