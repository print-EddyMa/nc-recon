import puppeteer from "puppeteer-core";
const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: false,
  args: ["--no-sandbox", "--window-size=1960,1180", "--hide-scrollbars"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 2 },
});
const page = await browser.newPage();
page.on("pageerror", (e) => console.log("pageerror:", e.message));
page.on("console", (m) => m.type() === "error" && console.log("console.error:", m.text()));
await page.goto("http://localhost:4173/?rec=1#/assess", { waitUntil: "networkidle2" });
await new Promise(r=>setTimeout(r,2000));
await page.screenshot({ path: "/private/tmp/claude-501/-Users-eddyma/65537aee-f864-4055-8c12-fdb067d7d77a/scratchpad/assess_check.png" });
console.log(await page.evaluate(()=>document.body.innerText.includes("connected")));
await browser.close();
