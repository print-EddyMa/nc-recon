import puppeteer from "puppeteer-core";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const b=await puppeteer.launch({executablePath:CHROME,headless:false,args:["--no-sandbox"],defaultViewport:{width:1400,height:880}});
const p=await b.newPage();
const urls=[];
p.on("request",r=>urls.push(r.url()));
p.on("console",m=>console.log("  ["+m.type()+"]",m.text().slice(0,240)));
p.on("pageerror",e=>console.log("  [pageerror]",e.message));
await p.goto("http://localhost:4173/",{waitUntil:"networkidle2"});
await p.evaluate(()=>[...document.querySelectorAll("button")].find(x=>/damage map/i.test(x.textContent||""))?.click());
await new Promise(r=>setTimeout(r,7000));
const diag=await p.evaluate(async()=>{
  // find the maplibre map instance via the canvas' parent
  const el=document.querySelector(".maplibregl-map");
  return {
    hasMap: !!el,
    mapClient: el? {w:el.clientWidth,h:el.clientHeight}: null,
  };
});
console.log("DIAG", JSON.stringify(diag));
console.log("\n-- unique request hosts --");
console.log([...new Set(urls.map(u=>{try{return new URL(u).host}catch{return u}}))].join("\n"));
console.log("\n-- tile-ish requests --");
console.log(urls.filter(u=>/tile|\.mvt|\.pbf|\.png|\.jpg|cartocdn/.test(u)).slice(0,25).join("\n"));
await b.close();
