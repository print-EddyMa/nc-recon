import puppeteer from "puppeteer-core";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const b=await puppeteer.launch({executablePath:CHROME,headless:false,args:["--no-sandbox"],defaultViewport:{width:1400,height:880}});
const p=await b.newPage();
p.on("console",m=>console.log("  ["+m.type()+"]",m.text().slice(0,300)));
p.on("pageerror",e=>console.log("  [pageerror]",e.message));
await p.goto("http://localhost:4173/",{waitUntil:"networkidle2"});
await p.evaluate(()=>[...document.querySelectorAll("button")].find(x=>/damage map/i.test(x.textContent||""))?.click());
await new Promise(r=>setTimeout(r,7000));
const d=await p.evaluate(()=>{
  const canvases=[...document.querySelectorAll("canvas")].map(c=>({w:c.width,h:c.height,cls:c.className,z:getComputedStyle(c).zIndex,pos:getComputedStyle(c).position,vis:getComputedStyle(c).visibility}));
  // sample center pixel of each canvas via a 2d copy (webgl canvases need preserveDrawingBuffer; try anyway)
  return {nCanvas:canvases.length, canvases};
});
console.log(JSON.stringify(d,null,2));
// Also: check the geojson actually has features with coords
const g=await p.evaluate(async()=>{
  const r=await fetch("/data/old_fort.geojson"); const j=await r.json();
  return {n:j.features.length, sample:j.features[0].geometry.coordinates[0].slice(0,2), props:j.features[0].properties};
});
console.log("geojson:",JSON.stringify(g));
await b.close();
