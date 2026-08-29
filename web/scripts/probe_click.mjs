import puppeteer from "puppeteer-core";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const b=await puppeteer.launch({executablePath:CHROME,headless:false,args:["--no-sandbox"],defaultViewport:{width:1400,height:880}});
const p=await b.newPage();
p.on("pageerror",e=>console.log("[pageerror]",e.message));
await p.goto("http://localhost:4173/",{waitUntil:"networkidle2"});
await p.evaluate(()=>[...document.querySelectorAll("button")].find(x=>/damage map/i.test(x.textContent||""))?.click());
await new Promise(r=>setTimeout(r,6000));
// click a hotspot row -> fly to
await p.evaluate(()=>[...document.querySelectorAll("button")].find(x=>/Cluster A/.test(x.textContent||""))?.click());
await new Promise(r=>setTimeout(r,2500));
await p.screenshot({path:"/tmp/tt_shots_gpu/05-flyto.png"});
// click somewhere on the map to select a building
await p.mouse.click(950,780);
await new Promise(r=>setTimeout(r,1800));
await p.screenshot({path:"/tmp/tt_shots_gpu/06-select.png"});
console.log("done");
await b.close();
