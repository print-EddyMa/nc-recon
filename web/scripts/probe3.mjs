import puppeteer from "puppeteer-core";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const b=await puppeteer.launch({executablePath:CHROME,headless:false,args:["--no-sandbox"],defaultViewport:{width:1400,height:880}});
const p=await b.newPage();
const reqs={carto:0,cartoFail:0,tiles:0,tilesFail:0,other:[]};
p.on("response",async r=>{const u=r.url();
  if(u.includes("cartocdn")){r.ok()?reqs.carto++:reqs.cartoFail++;}
  else if(u.includes("/tiles/")){r.ok()?reqs.tiles++:reqs.tilesFail++;}
});
p.on("requestfailed",r=>{const u=r.url(); if(u.includes("cartocdn"))reqs.cartoFail++; else if(u.includes("/tiles/"))reqs.tilesFail++; else reqs.other.push(u.slice(0,80)+" "+r.failure()?.errorText);});
p.on("console",m=>{if(m.type()==="error"||m.type()==="warning")console.log("  ["+m.type()+"]",m.text().slice(0,200));});
await p.goto("http://localhost:4173/",{waitUntil:"networkidle2"});
await p.evaluate(()=>[...document.querySelectorAll("button")].find(x=>/damage map/i.test(x.textContent||""))?.click());
await new Promise(r=>setTimeout(r,8000));
const st=await p.evaluate(()=>{
  const cvs=[...document.querySelectorAll("canvas")].map(c=>({w:c.width,h:c.height,cls:c.className||"(deck?)"}));
  // pixel sample from the largest canvas
  let sample=null;
  const big=[...document.querySelectorAll("canvas")].sort((a,b)=>b.width*b.height-a.width*a.height)[0];
  return {canvases:cvs, nCanvas:cvs.length};
});
console.log(JSON.stringify({reqs,st},null,2));
await b.close();
