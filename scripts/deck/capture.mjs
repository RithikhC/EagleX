// Drive headless Chrome over the DevTools protocol and capture the AeroTurn dashboard scenario by scenario.
// Usage: node capture.mjs <outDir>
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const OUT = process.argv[2];
const APP = process.argv[3] || "http://localhost:8501/";
fs.mkdirSync(OUT, { recursive: true });
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333;
const PROFILE = path.join(OUT, "..", "chromeprof");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`,
  "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--disable-gpu", "about:blank"],
  { stdio: "ignore" });

async function json(p) { const r = await fetch(`http://127.0.0.1:${PORT}${p}`); return r.json(); }
let targets;
for (let i = 0; i < 60; i++) { try { targets = await json("/json/list"); break; } catch { await sleep(250); } }
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let nextId = 1; const pending = new Map();
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); }
});
const send = (method, params = {}) => new Promise((res, rej) => { const id = nextId++; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const evalJs = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result.value;

const W = Number(process.env.CAP_W || 1600);
async function viewport(h) { await send("Emulation.setDeviceMetricsOverride", { width: W, height: h, deviceScaleFactor: 2, mobile: false }); await sleep(600); }

async function idle(timeoutMs = 60000, quietMs = 1800) {
  const t0 = Date.now(); let quietSince = null;
  await sleep(700);
  while (Date.now() - t0 < timeoutMs) {
    const running = await evalJs(`(() => { const s = document.querySelector('[data-testid="stStatusWidget"]');
      return !!(s && /running|connecting/i.test(s.innerText || s.getAttribute('aria-label') || '')) ||
             !!document.querySelector('[data-testid="stSkeleton"]') ||
             !document.body.innerText.includes('AEROTURN OCC'); })()`);
    if (!running) { quietSince ??= Date.now(); if (Date.now() - quietSince > quietMs) return true; }
    else quietSince = null;
    await sleep(300);
  }
  console.log("  (idle timeout)"); return false;
}

async function click(text, { exact = false, selector = "button, [role=tab], summary, label" } = {}) {
  const ok = await evalJs(`(() => { const t = ${JSON.stringify(text)};
    const els = [...document.querySelectorAll(${JSON.stringify(selector)})].filter(e => e.offsetParent !== null);
    const el = els.find(e => ${exact} ? e.innerText.trim() === t : e.innerText.includes(t));
    if (!el) return false; el.scrollIntoView({block: 'center'}); el.click(); return true; })()`);
  if (!ok) console.log(`  ! could not click "${text}"`);
  return ok;
}

async function rects() {
  return evalJs(`(() => {
    const R = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return [r.left, r.top + window.scrollY, r.width, r.height]; };
    const box = (el) => el && (el.closest('[data-testid="stVerticalBlockBorderWrapper"]') || el);
    const sec = (prefix) => box([...document.querySelectorAll('.sec')].find(e => e.innerText.trim().toUpperCase().startsWith(prefix.toUpperCase())));
    const union = (els) => { els = els.filter(Boolean).map(R); if (!els.length) return null;
      const x0 = Math.min(...els.map(r => r[0])), y0 = Math.min(...els.map(r => r[1]));
      const x1 = Math.max(...els.map(r => r[0] + r[2])), y1 = Math.max(...els.map(r => r[1] + r[3])); return [x0, y0, x1 - x0, y1 - y0]; };
    const btn = [...document.querySelectorAll('button')].find(b => b.innerText.includes('Run recovery agent'));
    return {
      header: R(document.querySelector('.hdr')),
      bar: R(box(btn)),
      banner: R(document.querySelector('.inc')),
      kpis: union([...document.querySelectorAll('.kpi')]),
      map: R(sec('Connection network')), gantt: R(sec('EK813 turnaround')), crew: R(sec('Crew duty legality')),
      flow: R(sec('Passenger recovery flow')), queue: R(sec('Priority queue')), cost: R(sec('Compensation')),
      feed: R(sec('Live event feed')), ctrl: R(sec('Operations Controller queue')), guard: R(sec('Guard interventions')),
      page: [0, 0, document.documentElement.scrollWidth, Math.max(document.documentElement.scrollHeight, window.innerHeight)],
    }; })()`);
}

async function shot(name, extra = {}) {
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  fs.writeFileSync(path.join(OUT, `${name}.png`), Buffer.from(r.data, "base64"));
  const rr = { ...(await rects()), ...extra };
  fs.writeFileSync(path.join(OUT, `${name}.json`), JSON.stringify(rr, null, 1));
  const banner = await evalJs(`(document.querySelector('.inc .t') || {}).innerText || ''`);
  console.log(`saved ${name}  ${banner.replace(/\s+/g, " ").slice(0, 110)}`);
}

const bannerText = () => evalJs(`(document.querySelector('.inc .t') || {}).innerText || ''`);
async function waitFor(pred, timeoutMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) { if (await pred()) return true; await sleep(400); }
  console.log("  (waitFor timeout)"); return false;
}
async function press(label, waitText = null, timeoutMs = 120000) {
  const before = await bannerText();
  await click(label);
  await waitFor(async () => { const b = await bannerText(); return waitText ? b.includes(waitText) : b !== before; }, timeoutMs);
  await idle(30000);
}

async function escape() {
  for (const type of ["keyDown", "keyUp"]) await send("Input.dispatchKeyEvent", { type, key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await sleep(400);
}

await send("Page.enable"); await send("Runtime.enable");
const stage = process.argv[4] || "all";

// ---------------- session 1: the main story
if (stage === "all" || stage === "main") {
  await viewport(2300);
  await send("Page.navigate", { url: APP }); await idle(90000, 2500);
  await shot("01_initial");
  await press("Run recovery agent", "Recovery run complete", 420000);
  await shot("02_agent");
  for (const [b, n] of [["Duty breach", "03_duty"], ["No CRS", "04_nocrs"], ["Override", "05_override"],
                        ["Rollback", "06_rollback"], ["Naive AI", "07_naive"], ["✅ Approve", "08_approve"],
                        ["🔧 Release", "09_release"]]) {
    await press(b); await shot(n);
  }
  await viewport(1300);
  await click("Crew & duty", { selector: "[role=tab]" }); await idle(); await shot("13_crew");
  await click("Cost & network", { selector: "[role=tab]" }); await idle(); await shot("12_cost");
  await click("Turnaround & MX", { selector: "[role=tab]" }); await idle(); await shot("14_turn");
  await viewport(1000);
  await click("Edge cases", { selector: "[role=tab]" }); await idle();
  await click("Run all 13");
  await waitFor(() => evalJs(`document.body.innerText.includes('CASES PASSED') || document.body.innerText.includes('Cases passed')`), 300000);
  await idle(30000, 3000);
  await viewport(4600); await idle(20000);
  await evalJs(`(() => { const card = [...document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"]')]
      .find(c => c.innerText.includes('EC-07') && c.innerText.includes('Timeline'));
      const s = card && card.querySelector('summary'); if (s) s.click(); return !!s; })()`);
  await sleep(1500);
  const ec = await evalJs(`(() => { const R = (el) => { const r = el.getBoundingClientRect(); return [r.left, r.top + window.scrollY, r.width, r.height]; };
      const cards = [...document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"]')];
      const find = (id) => { const c = cards.filter(c => c.innerText.includes(id + ' ·')); return c.length ? R(c[c.length - 1]) : null; };
      return { ec01: find('EC-01'), ec05: find('EC-05'), ec07: find('EC-07'), ec09: find('EC-09') }; })()`);
  await shot("11_edge", ec);
}

// ---------------- banners only, at a narrower width so their text reads at slide size
if (stage === "banners") {
  await viewport(1400);
  await send("Page.navigate", { url: APP }); await idle(90000, 2500);
  for (const [b, n] of [["Duty breach", "b_duty"], ["No CRS", "b_nocrs"], ["Override", "b_override"],
                        ["Naive AI", "b_naive"]]) {
    await press(b); await shot(n);
  }
}

// ---------------- session 2: a world event after the plan
if (stage === "all" || stage === "whatif") {
  await viewport(2300);
  await send("Page.navigate", { url: APP }); await idle(90000, 2500);
  await press("Run recovery agent", "Recovery run complete", 420000);
  await click("What if"); await sleep(1200);
  const before = await bannerText();
  await click("Medical diversion takes stand C31");
  await waitFor(async () => (await bannerText()).includes("World event"), 120000); await idle(30000);
  await escape(); await idle(10000);
  await shot("10_whatif");
}

ws.close(); chrome.kill();
console.log("done");
process.exit(0);
