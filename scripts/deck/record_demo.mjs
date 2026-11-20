// Record a subtitled walkthrough of the LIVE demo (no voice-over) with Chrome's screencast.
// node record_demo.mjs <outDir> [appUrl]  ->  <outDir>/frames/*.jpg, frames.json, captions.json
// Then: python assemble_video.py <outDir> <out.mp4>
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const OUT = process.argv[2];
const APP = process.argv[3] || "https://aeroturn-eaglex.streamlit.app/~/+/";
const FR = path.join(OUT, "frames");
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(FR, { recursive: true });
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9334;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${path.join(OUT, "..", "chromeprof_rec")}`,
  "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--window-size=1920,1080", "about:blank"], { stdio: "ignore" });

let targets;
for (let i = 0; i < 60; i++) { try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); break; } catch { await sleep(250); } }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let nextId = 1; const pending = new Map(); const frames = []; let recording = false;
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); return; }
  if (m.method === "Page.screencastFrame") {
    const p = m.params;
    if (recording) {
      const f = path.join(FR, `${String(frames.length).padStart(5, "0")}.jpg`);
      fs.writeFileSync(f, Buffer.from(p.data, "base64"));
      frames.push({ file: path.basename(f), ts: p.metadata.timestamp });
    }
    ws.send(JSON.stringify({ id: nextId++, method: "Page.screencastFrameAck", params: { sessionId: p.sessionId } }));
  }
});
const send = (method, params = {}) => new Promise((res, rej) => { const id = nextId++; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const js = async (e) => (await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true })).result.value;

const captions = [];
async function cap(text, sub = "", hold = 4200) {
  await js(`(() => { let el = document.getElementById('__cap');
    if (!el) { el = document.createElement('div'); el.id = '__cap';
      Object.assign(el.style, {position:'fixed', left:'50%', bottom:'30px', transform:'translateX(-50%)', maxWidth:'1560px',
        background:'rgba(11,45,107,0.95)', color:'#fff', font:'600 27px "Segoe UI", Arial, sans-serif', padding:'14px 28px',
        borderRadius:'14px', zIndex:2147483647, textAlign:'center', boxShadow:'0 10px 30px rgba(0,0,0,.55)', lineHeight:'1.35',
        border:'2px solid #1AA3E8'}); document.body.appendChild(el); }
    el.innerHTML = ${JSON.stringify(text)} + (${JSON.stringify(sub)} ? '<div style="font-weight:400;font-size:21px;opacity:.9;margin-top:4px">' + ${JSON.stringify(sub)} + '</div>' : '');
    el.style.display = ${JSON.stringify(text)} ? 'block' : 'none'; })()`);
  captions.push({ t: Date.now() / 1000, text: text + (sub ? ` · ${sub}` : "") });
  if (hold) await sleep(hold);
}
async function card(title, lines, hold = 4500) {
  await js(`(() => { let el = document.getElementById('__card'); if (!el) { el = document.createElement('div'); el.id = '__card';
    Object.assign(el.style, {position:'fixed', inset:'0', background:'#0B2D6B', color:'#fff', zIndex:2147483646, display:'flex',
      flexDirection:'column', justifyContent:'center', padding:'0 160px', font:'400 30px "Segoe UI", Arial, sans-serif'}); document.body.appendChild(el); }
    el.innerHTML = '<div style="font:700 84px Segoe UI, Arial">' + ${JSON.stringify(title)} + '</div>' +
      ${JSON.stringify(lines)}.map(l => '<div style="margin-top:18px;opacity:.92">' + l + '</div>').join('');
    el.style.display = 'flex'; })()`);
  captions.push({ t: Date.now() / 1000, text: [title, ...lines].join(" · ").replace(/<[^>]+>/g, "") });
  await sleep(hold);
  await js(`(() => { const el = document.getElementById('__card'); if (el) el.style.display = 'none'; })()`);
}
async function idle(timeoutMs = 60000, quietMs = 1500) {
  const t0 = Date.now(); let q = null; await sleep(600);
  while (Date.now() - t0 < timeoutMs) {
    const busy = await js(`(() => { const s = document.querySelector('[data-testid="stStatusWidget"]');
      return !!(s && /running|connecting/i.test(s.innerText || '')) || !document.body.innerText.includes('AEROTURN OCC'); })()`);
    if (!busy) { q ??= Date.now(); if (Date.now() - q > quietMs) return; } else q = null;
    await sleep(250);
  }
}
const banner = () => js(`(document.querySelector('.inc .t') || {}).innerText || ''`);
async function waitFor(fn, ms) { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await fn()) return true; await sleep(400); } return false; }
async function find(textInc, sel = "button, [role=tab], summary") {
  return js(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(sel)})].filter(e => e.offsetParent !== null)
    .find(e => e.innerText.includes(${JSON.stringify(textInc)})); if (!el) return false;
    el.scrollIntoView({block:'center', behavior:'smooth'}); window.__target = el; return true; })()`);
}
async function click(textInc, sel) {
  if (!(await find(textInc, sel))) { console.log("! missing", textInc); return false; }
  await sleep(700);
  await js(`(() => { const r = window.__target.getBoundingClientRect(); const d = document.createElement('div');
    Object.assign(d.style, {position:'fixed', left:(r.left-8)+'px', top:(r.top-8)+'px', width:(r.width+16)+'px', height:(r.height+16)+'px',
      border:'4px solid #1AA3E8', borderRadius:'12px', boxShadow:'0 0 0 6px rgba(26,163,232,.35)', zIndex:2147483645, pointerEvents:'none'});
    document.body.appendChild(d); setTimeout(() => d.remove(), 1100); })()`);
  await sleep(900);
  await js(`window.__target.click()`);
  return true;
}
async function scrollTo(textInc) {
  await js(`(() => { const el = [...document.querySelectorAll('.sec')].find(e => e.innerText.toUpperCase().includes(${JSON.stringify(textInc.toUpperCase())}));
    if (el) el.scrollIntoView({block:'start', behavior:'smooth'}); })()`);
  await sleep(1200);
}
const top = async () => { await js(`window.scrollTo({top:0, behavior:'smooth'}); document.querySelector('[data-testid="stMain"]')?.scrollTo({top:0, behavior:'smooth'})`); await sleep(1200); };
async function press(label, until, ms = 120000) {
  const before = await banner(); await click(label);
  await waitFor(async () => { const b = await banner(); return until ? b.includes(until) : b !== before; }, ms); await idle(30000);
}

await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: APP }); await idle(120000, 2500); await sleep(1500);
await send("Page.startScreencast", { format: "jpeg", quality: 82, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
recording = true; await sleep(500);

await card("AeroTurn", ["Autonomous aircraft turnaround and disruption recovery agent", "Team EagleX · TechX Dubai'26 · AI Agent Arena",
  "<span style='opacity:.75'>Recorded on the live demo · aeroturn-eaglex.streamlit.app</span>"], 5000);
await cap("EK812 lands at Dubai 75 minutes late", "45 connections break · the crew is 20 min from its duty limit · a hydraulic defect · a fatigued captain", 5500);
await cap("One screen for the operations controller", "A Start-here guide explains the four clicks to a first-time visitor", 4500);
await click("Hide guide"); await idle(); await top();

await cap("Step 1 · Run the AI recovery agent", "", 2200);
const before = await banner(); await click("Run recovery agent");
const lines = [["The LLM (Groq gpt-oss-120b) reads the situation through read-only tools", ""],
  ["It proposes a stand, a replacement captain, a new departure time and the rebooking", ""],
  ["Code checks every decision against sealed safety rules", "A seat is sold mid-run on purpose to test the all-or-nothing save"]];
let li = 0; const t0 = Date.now();
while (Date.now() - t0 < 300000) {
  const b = await banner(); if (b.includes("Recovery run complete")) break;
  if (li < lines.length) { await cap(lines[li][0], lines[li][1], 0); li++; }
  await sleep(4500);
}
await idle(30000); await top();
const kpi = await js(`[...document.querySelectorAll('.kpi')].map(k => k.querySelector('.lab').innerText + ': ' + k.querySelector('.val').innerText)`);
const get = (lab) => (kpi.find((k) => k.toUpperCase().startsWith(lab)) || "").split(": ")[1] || "";
await cap(`Done: ${get("CONNECTIONS")} connections at risk · ${get("VULNERABLE")} vulnerable protected · ${get("PASSENGER COST")} saved`,
  "45 passengers and 48 bags rebooked in one transaction", 5500);
const b1 = await banner(), bl = await js(`(document.querySelector('.inc') || {}).innerText || ''`);
if (bl.includes("TURN-001")) await cap("The guard blocked the LLM's too-early departure time (TURN-001)", "The LLM corrected itself: code decides what is legal", 5000);
await scrollTo("Connection network"); await cap("Every broken connection (red) is now protected (green)", "", 4200);
await scrollTo("Live event feed"); await cap("The live feed shows every LLM decision, tool call and guard verdict", "", 4500);
await cap("The AI may only propose network changes", "They wait in the approval queue for a human controller", 4500);

await top(); await cap("Step 2 · Try to break it: a rogue AI attacks the rules", "", 3000);
await press("Use tired crew"); await cap("Fly with the tired inbound crew → BLOCKED", "FTL-001: crew duty limit, for every crew member", 4500);
await press("Skip engineer sign-off"); await cap("Dispatch before the engineer signs → BLOCKED", "MX-001: no certificate of release to service", 4500);
await press("Try an override"); await cap("Call a tool with override=True → REJECTED", "No override exists anywhere in the system", 4500);
await press("Crash mid-save"); await cap("A failure halfway through rebooking → everything rolls back", "State identical, 0 double bookings, then a clean retry", 5200);
await press("Naive AI vs rules"); await cap("A revenue-first AI that ignores the rules → 15 violations, blocked", "Vulnerable passengers always come first", 4800);

await cap("Step 3 · The world changes after the plan", "", 2500);
await click("What if"); await sleep(1500);
const bw = await banner(); await click("Medical diversion takes stand C31");
await waitFor(async () => (await banner()).includes("World event"), 120000); await idle(20000);
for (const t of ["keyDown", "keyUp"]) await send("Input.dispatchKeyEvent", { type: t, key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
await top();
await cap("A diversion takes stand C31", "AeroTurn withdraws its own C31 proposal and stages the next legal stand, R205", 5500);

await cap("Step 4 · You are the controller", "", 2500);
await press("Approve all"); await cap("Approve all: the rules are checked again at approval", "The AI cannot approve anything itself", 4800);
await press("Sign-off & release"); await cap("The wrong engineer (B2) is refused · the licensed B1 engineer signs", "EK813 is released", 5200);

await cap("", "", 0);
await click("Guardrails", "[role=tab]"); await idle(); await sleep(800);
await cap("Guardrails tab: live evidence for all five guardrails", "Validation · prompt-injection defence · read/write separation · human approval · logging", 5000);
await click("Injection test"); await idle(); await sleep(800);
await cap("Injection test: a passenger remark that tries to command the AI", "is withheld before it reaches the LLM, and logged", 5000);

await cap("", "", 0);
await click("Edge cases", "[role=tab]"); await idle(); await sleep(800);
await cap("13 edge cases: ATC holds, a second fatigue report, a leak, sold-out seats…", "Each runs on a throw-away copy of the scenario", 0);
await click("Run all 13");
await waitFor(() => js(`document.body.innerText.includes('CASES PASSED') || document.body.innerText.includes('Cases passed')`), 300000);
await idle(30000); await sleep(800);
await cap("13 of 13 pass, 67 checks", "9 resolved automatically · 4 escalated to a human because no legal option exists", 5500);
await js(`(document.querySelector('[data-testid="stMain"]') || window).scrollBy({top: 650, behavior: 'smooth'})`); await sleep(3500);

await card("Try it yourself", ["Live demo: <b>aeroturn-eaglex.streamlit.app</b>", "Code: <b>github.com/RithikhC/EagleX</b>",
  "Rithikh Chandran · Mohammed Fawwaz Husain · Reuben Thomas Thovelil"], 5500);
recording = false;
await send("Page.stopScreencast");
fs.writeFileSync(path.join(OUT, "frames.json"), JSON.stringify(frames));
fs.writeFileSync(path.join(OUT, "captions.json"), JSON.stringify(captions));
console.log(`frames ${frames.length}, captions ${captions.length}`);
ws.close(); chrome.kill(); process.exit(0);
