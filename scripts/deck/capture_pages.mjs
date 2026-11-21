// Capture the Dashboard, Implementation, Business and Simulation pages (light theme) for the Round 3 deck.
// node capture_pages.mjs <outDir> [baseUrl]
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const OUT = process.argv[2];
const BASE = (process.argv[3] || "http://localhost:8501").replace(/\/$/, "");
fs.mkdirSync(OUT, { recursive: true });
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9335;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${path.join(OUT, "..", "chromeprof_pages")}`, "--no-first-run", "--hide-scrollbars", "about:blank"],
  { stdio: "ignore" });
let targets;
for (let i = 0; i < 60; i++) { try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); break; } catch { await sleep(250); } }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 1; const pend = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id); } });
const send = (method, params = {}) => new Promise((res) => { const i = id++; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const js = async (e) => (await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true })).result.value;
async function idle(ms = 60000) {
  const t0 = Date.now(); let q = null; await sleep(1500);
  while (Date.now() - t0 < ms) {
    const busy = await js(`(() => { const s = document.querySelector('[data-testid="stStatusWidget"]');
      return !!(s && /running|connecting/i.test(s.innerText || '')) || !!document.querySelector('[data-testid="stSkeleton"]'); })()`);
    if (!busy) { q ??= Date.now(); if (Date.now() - q > 2500) return; } else q = null;
    await sleep(300);
  }
}
await send("Page.enable"); await send("Runtime.enable");
const ONLY = process.argv[4];
for (const [name, url, h] of [["p_dashboard", "/", 2050], ["p_implementation", "/implementation", 2900],
                              ["p_business", "/business", 2500], ["p_simulation", "/simulation", 1300]]) {
  if (ONLY && name !== ONLY) continue;
  await send("Emulation.setDeviceMetricsOverride", { width: 1500, height: h, deviceScaleFactor: 2, mobile: false });
  await send("Page.navigate", { url: BASE + url }); await idle(); await sleep(2500);
  const r = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(OUT, `${name}.png`), Buffer.from(r.data, "base64"));
  const err = await js(`[...document.querySelectorAll('[data-testid="stException"]')].length`);
  console.log("saved", name, err ? `(${err} errors!)` : "");
}
ws.close(); chrome.kill(); process.exit(0);
