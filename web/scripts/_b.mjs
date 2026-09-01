import puppeteer from "puppeteer-core";
const OUT="/private/tmp/claude-501/-Users-eddyma/891daedb-073c-4385-868a-a9eb1bc955b5/scratchpad/shots";
const f="file:///private/tmp/claude-501/-Users-eddyma/891daedb-073c-4385-868a-a9eb1bc955b5/scratchpad/art/preview.html";
const b=await puppeteer.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",headless:false,args:["--no-sandbox"],defaultViewport:{width:1440,height:1000,deviceScaleFactor:2}});
const p=await b.newPage();
const errs=[]; p.on("pageerror",e=>errs.push("PE "+e.message)); p.on("console",m=>m.type()==="error"&&errs.push("CE "+m.text()));
for (const theme of ["light","dark"]) {
  await p.emulateMediaFeatures([{name:"prefers-color-scheme",value:theme}]);
  await p.goto(f,{waitUntil:"networkidle0"}); await new Promise(r=>setTimeout(r,1400));
  await p.evaluate(()=>document.getElementById("sizebars").scrollIntoView({block:"center"}));
  await new Promise(r=>setTimeout(r,2200));
  await p.screenshot({path:`${OUT}/w4-${theme}-size.png`});
  await p.evaluate(()=>document.getElementById("years").scrollIntoView({block:"center"}));
  await new Promise(r=>setTimeout(r,2200));
  await p.screenshot({path:`${OUT}/w4-${theme}-years.png`});
  await p.evaluate(()=>document.getElementById("bcard").scrollIntoView({block:"start"}));
  await new Promise(r=>setTimeout(r,1500));
  await p.screenshot({path:`${OUT}/w4-${theme}-bcard.png`});
}
console.log(errs.length?"ERR "+[...new Set(errs)].join("|"):"clean");
await b.close();
