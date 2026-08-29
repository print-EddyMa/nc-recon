import puppeteer from "puppeteer-core";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const b=await puppeteer.launch({executablePath:CHROME,headless:false,args:["--no-sandbox"],defaultViewport:{width:1400,height:880}});
const p=await b.newPage();
await p.goto("http://localhost:4173/",{waitUntil:"networkidle2"});
await p.evaluate(()=>[...document.querySelectorAll("button")].find(x=>/damage map/i.test(x.textContent||""))?.click());
await new Promise(r=>setTimeout(r,3000));
const chain=await p.evaluate(()=>{
  const out=[];
  let el=document.querySelector('[aria-label^="Damage map"]');
  while(el && el!==document.documentElement){
    const cs=getComputedStyle(el);
    out.push({tag:el.tagName, cls:el.getAttribute("class")||"", h:el.clientHeight, disp:cs.display, flex:cs.flex, pos:cs.position});
    el=el.parentElement;
  }
  return out;
});
console.log(JSON.stringify(chain,null,2));
await b.close();
