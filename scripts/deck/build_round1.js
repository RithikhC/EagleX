// TechX Dubai'26 · AI Agent Arena · Round 1 submission, built on the official template's layout and order.
// node build_round1.js <repoRoot> <out.pptx>      (images: docs/img/round1/*.png, captured from the live demo)
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = process.argv[2];
const OUT = process.argv[3];
const IMG = (n) => path.join(ROOT, "docs", "img", "round1", `${n}.png`);
const LIVE = "https://aeroturn-eaglex.streamlit.app";
const CODE = "https://github.com/RithikhC/EagleX";
const EMAIL = "f20230348@dubai.bits-pilani.ac.in";

// Template palette
const THEME = {
  name: "TechX Round 1",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B2D6B", lt1: "FFFFFF", dk2: "1F2937", lt2: "EDF2FB",
    accent1: "1F5FC0", accent2: "1AA3E8", accent3: "15803D", accent4: "C2410C", accent5: "B91C1C", accent6: "6B7A90",
    hlink: "1F5FC0", folHlink: "6B7A90",
  },
};
const BORDER = "C9D8F0", MUTED = "6B7A90", GENERIC = "7A8699";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5, same 16:9 as the template
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "AeroTurn · EagleX · TechX Dubai'26 Round 1";
pres.author = "Team EagleX";
pres.subject = "AI Agent Arena · University Track · Aviation & Airport Operations";
const C = pres.SchemeColor;
const W = 13.333, M = 0.67;
const FOOT = "TechX Dubai'26 · AI Agent Arena · Round 1";

pres.defineSlideMaster({
  title: "Cover",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M + 0.13, y: 2.55, w: 11.5, h: 1.0, fontSize: 54, bold: true,
      color: C.background1, margin: 0, valign: "bottom", align: "left" }, text: "" } },
    { text: { text: FOOT, options: { x: M + 0.13, y: 6.72, w: 6, h: 0.3, fontSize: 12, color: "C9D8F0", margin: 0 } } },
  ],
});
pres.defineSlideMaster({
  title: "Criterion",
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.5, w: W - 2 * M, h: 0.85, fontSize: 40, bold: true,
      color: C.text1, margin: 0, valign: "middle", align: "left" }, text: "" } },
    { text: { text: FOOT, options: { x: M, y: 6.82, w: 6, h: 0.3, fontSize: 12, color: C.accent6, margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.6, y: 6.82, w: 0.6, h: 0.3, fontSize: 12, color: C.accent6, align: "right", margin: 0 },
});

// ------------------------------------------------------------------ helpers
const png = (f) => { const b = fs.readFileSync(f); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; };
function shot(s, name, box, { align = "center", valign = "middle", pad = 0.06, alt } = {}) {
  const z = png(IMG(name)), ar = z.w / z.h;
  let w = box.w - 2 * pad, h = w / ar;
  if (h > box.h - 2 * pad) { h = box.h - 2 * pad; w = h * ar; }
  const fw = w + 2 * pad, fh = h + 2 * pad;
  const fx = align === "left" ? box.x : align === "right" ? box.x + box.w - fw : box.x + (box.w - fw) / 2;
  const fy = valign === "top" ? box.y : valign === "bottom" ? box.y + box.h - fh : box.y + (box.h - fh) / 2;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: fx, y: fy, w: fw, h: fh, rectRadius: 0.06, fill: { color: "0D0D0D" },
    line: { color: BORDER, width: 0.75 }, objectName: `${name} frame` });
  s.addImage({ path: IMG(name), x: fx + pad, y: fy + pad, w, h, altText: alt || name, objectName: name });
  return { x: fx, y: fy, w: fw, h: fh };
}
function pill(s, label) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: W - M - 2.6, y: 0.54, w: 2.6, h: 0.64, rectRadius: 0.1,
    fill: { color: C.accent1 }, line: { color: C.accent1, width: 0 }, objectName: "criterion" });
  s.addText(label, { x: W - M - 2.6, y: 0.54, w: 2.6, h: 0.64, fontSize: 17, bold: true, color: C.background1,
    align: "center", valign: "middle", margin: 0, isTextBox: true });
}
function card(s, x, y, w, h, name) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.background2 },
    line: { color: BORDER, width: 1 }, objectName: name || "card" });
}
function num(s, x, y, n, size = 0.5) {
  s.addShape(pres.shapes.OVAL, { x, y, w: size, h: size, fill: { color: C.accent1 }, line: { color: C.accent1, width: 0 },
    objectName: `number ${n}` });
  s.addText(String(n), { x, y, w: size, h: size, fontSize: 18, bold: true, color: C.background1, align: "center",
    valign: "middle", margin: 0, isTextBox: true });
}
function text(s, runs, box, opts = {}) {
  s.addText(runs, { margin: 0, valign: "top", isTextBox: true, ...box, ...opts });
}
const bullets = (items, size = 15, color = C.dk2) => items.map((t, i) => ({ text: t, options: { bullet: true, fontSize: size,
  color, breakLine: i < items.length - 1 } }));
function slide(title, criterion) {
  const s = pres.addSlide({ masterName: "Criterion" });
  s.addText(title, { placeholder: "title" });
  if (criterion) pill(s, criterion);
  return s;
}

// ------------------------------------------------------------------ 1. cover
{
  const s = pres.addSlide({ masterName: "Cover" });
  s.addText("AeroTurn", { placeholder: "title" });
  text(s, "Autonomous aircraft turnaround and atomic disruption recovery agent",
    { x: M + 0.13, y: 3.65, w: 11, h: 0.5 }, { fontSize: 24, color: C.background1 });
  text(s, "EagleX  ·  University Track  ·  Domain 4: Aviation & Airport Operations",
    { x: M + 0.13, y: 4.3, w: 11, h: 0.45 }, { fontSize: 20, color: "C9D8F0" });
  text(s, [{ text: "Live demo  ", options: { color: "C9D8F0" } },
    { text: LIVE.replace("https://", ""), options: { color: C.background1, bold: true, hyperlink: { url: LIVE }, breakLine: true } },
    { text: "Code  ", options: { color: "C9D8F0" } },
    { text: CODE.replace("https://", ""), options: { color: C.background1, bold: true, hyperlink: { url: CODE } } }],
    { x: M + 0.13, y: 5.1, w: 11, h: 0.8 }, { fontSize: 16, paraSpaceAfter: 4 });
  s.addNotes("Round 1 submission for TechX Dubai'26 AI Agent Arena, University Track, Domain 4.");
}

// ------------------------------------------------------------------ 2. team
{
  const s = slide("Our team", "Problem Fit · 25%");
  text(s, "EagleX · BITS Pilani, Dubai Campus · University Track · Aviation & Airport Operations",
    { x: M, y: 1.55, w: 12, h: 0.4 }, { fontSize: 20, color: C.dk2 });
  const team = [
    ["RC", "Rithikh Chandran", "Team lead · system architecture and the AI agent"],
    ["MF", "Mohammed Fawwaz Husain", "Safety guards, atomic transactions and testing"],
    ["RT", "Reuben Thomas Thovelil", "Scenario data, aviation research and presentation"],
  ];
  const cw = 3.55, gap = 0.45, x0 = (W - (3 * cw + 2 * gap)) / 2;
  team.forEach(([ini, name, role], i) => {
    const x = x0 + i * (cw + gap), y = 2.3;
    card(s, x, y, cw, 3.9, `team ${name}`);
    s.addShape(pres.shapes.OVAL, { x: x + cw / 2 - 0.62, y: y + 0.35, w: 1.24, h: 1.24, fill: { color: "CFE0FA" },
      line: { color: C.accent1, width: 1.5 }, objectName: `avatar ${name}` });
    text(s, ini, { x: x + cw / 2 - 0.62, y: y + 0.35, w: 1.24, h: 1.24 },
      { fontSize: 30, bold: true, color: C.text1, align: "center", valign: "middle" });
    text(s, name, { x: x + 0.15, y: y + 1.8, w: cw - 0.3, h: 0.85 }, { fontSize: 21, bold: true, color: C.text1, align: "center", valign: "middle" });
    text(s, role, { x: x + 0.3, y: y + 2.75, w: cw - 0.6, h: 1.0 }, { fontSize: 16, color: MUTED, align: "center" });
  });
}

// ------------------------------------------------------------------ 3. problem
{
  const s = slide("The problem", "Problem Fit · 25%");
  card(s, M, 1.5, W - 2 * M, 1.3, "problem statement");
  text(s, [{ text: "Problem statement", options: { bold: true, fontSize: 18, color: C.text1, breakLine: true } },
    { text: "Flight EK-812 lands at Dubai 75 minutes late. 280 passengers connect onward and 45 of those connections break, "
      + "including vulnerable passengers. The inbound crew is 20 minutes from its legal duty limit, a hydraulic defect "
      + "needs a licensed engineer's sign-off, and the outbound captain reports fatigue. Recover the turnaround "
      + "safely, atomically and with a human in control.", options: { fontSize: 15, color: C.dk2 } }],
    { x: M + 0.3, y: 1.62, w: W - 2 * M - 0.6, h: 1.1 });
  const cols = [
    ["Who is affected", ["Operations controllers, crew control, maintenance engineers and ground staff at the hub",
      "280 connecting passengers, 10 of them vulnerable: children flying alone, wheelchair users, a medical case"]],
    ["Why it matters", ["45 broken connections: re-protecting them on tomorrow's flight costs AED 133,390 in compensation and care",
      "0 of 45 arrive the same day",
      "One wrong call breaks crew-duty law or dispatches an aircraft without its safety sign-off"]],
    ["How it is done now", ["Stands, crew rosters, maintenance and reservations live in separate systems",
      "Controllers reconcile them by phone and spreadsheet under a 25-minute deadline",
      "Default re-protection moves everyone to the next day; vulnerable passengers get no priority"]],
  ];
  const cw = (W - 2 * M - 2 * 0.3) / 3;
  cols.forEach(([h, items], i) => {
    const x = M + i * (cw + 0.3), y = 3.05;
    card(s, x, y, cw, 3.5, h);
    num(s, x + 0.25, y + 0.25, i + 1);
    text(s, h, { x: x + 0.9, y: y + 0.27, w: cw - 1.1, h: 0.45 }, { fontSize: 19, bold: true, color: C.text1, valign: "middle" });
    text(s, bullets(items, 14), { x: x + 0.3, y: y + 0.95, w: cw - 0.5, h: 2.45 }, { paraSpaceAfter: 6 });
  });
}

// ------------------------------------------------------------------ 4. solution and value
{
  const s = slide("Our solution and its value", "Problem Fit · 25%");
  card(s, M, 1.5, W - 2 * M, 1.05, "one sentence");
  text(s, [{ text: "In one sentence  ", options: { bold: true, color: C.text1 } },
    { text: "AeroTurn helps airline operations controllers recover a late-aircraft disruption by letting an AI agent plan "
      + "the stand, crew, retime and passenger rebooking while code enforces every safety rule, so that passengers still "
      + "arrive the same day, vulnerable travellers come first and no rule is ever broken.", options: { color: C.dk2 } }],
    { x: M + 0.3, y: 1.6, w: W - 2 * M - 0.6, h: 0.9 }, { fontSize: 16, valign: "middle" });
  const cw = (W - 2 * M - 2 * 0.3) / 3, y = 2.8, h = 3.85;
  [["Before", "45 connections at risk, 0/10 vulnerable passengers protected, a dispatch-blocking defect and a crew about to time out."],
   ["With our agent", "One click: legal stand, legal replacement captain, critical-path retime, 45 passengers and 48 bags rebooked in one transaction. The controller approves."],
   ["Impact", ""]].forEach(([title, d], i) => {
    const x = M + i * (cw + 0.3);
    card(s, x, y, cw, h, title);
    num(s, x + 0.25, y + 0.25, i + 1);
    text(s, title, { x: x + 0.9, y: y + 0.27, w: cw - 1.1, h: 0.45 }, { fontSize: 19, bold: true, color: C.text1, valign: "middle" });
    if (d) text(s, d, { x: x + 0.3, y: y + 0.85, w: cw - 0.55, h: 1.05 }, { fontSize: 13.5, color: C.dk2 });
  });
  shot(s, "map_before", { x: M + 0.25, y: y + 1.95, w: cw - 0.5, h: 1.75 }, { alt: "Network map before: 45 broken connections in red" });
  shot(s, "map_after", { x: M + cw + 0.3 + 0.25, y: y + 1.95, w: cw - 0.5, h: 1.75 }, { alt: "Network map after the agent: connections protected in green" });
  const ix = M + 2 * (cw + 0.3) + 0.3;
  [["−62%", "compensation and care: AED 133,390 → 50,440 (−70% with an 8-min hold)"],
   ["45/45", "passengers arrive the same day (legacy 0)"],
   ["10/10", "vulnerable passengers protected"],
   ["0", "safety rules broken"]].forEach(([v, l], i) => {
    text(s, [{ text: v + "  ", options: { bold: true, fontSize: 24, color: C.accent3 } }, { text: l, options: { fontSize: 13, color: C.dk2 } }],
      { x: ix, y: y + 0.85 + i * 0.72, w: cw - 0.55, h: 0.7 }, { valign: "middle" });
  });
  s.addNotes("Figures from the recorded live run. The −62% vs −70% difference is one decision: whether to hold the Sydney flight 8 minutes. See docs/NUMBERS_EXPLAINED.md.");
}

// ------------------------------------------------------------------ 5. what makes us different
{
  const s = slide("What makes us different", "Innovation · 25%");
  const hdr = (t, fill) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: fill }, fontSize: 17 } });
  const cell = (t, o = {}) => ({ text: t, options: { fontSize: 14, color: C.dk2, fill: { color: "EDF2FB" }, ...o } });
  const rows = [
    [{ text: "", options: { fill: { color: "FFFFFF" } } }, hdr("A generic agent", GENERIC), hdr("Our agent", "1F5FC0")],
    [cell("Approach", { fontSize: 16 }), cell("One prompt asks an LLM to solve the disruption"),
      cell("Plan-and-execute: code gathers facts with read-only tools, the LLM chooses actions, guarded tools execute them, and rejected choices go back to the LLM to correct")],
    [cell("Tools and data", { fontSize: 16 }), cell("No tools; answers from memory"),
      cell("13 aviation tools: legal standby-crew matcher, turnaround critical path, stand evaluator, priority rebooking planner, EU261 cost model; a database of 342 passengers, 356 bags, 33 crew")],
    [cell("Reliability", { fontSize: 16 }), cell("Trusts whatever the LLM says"),
      cell("25 sealed safety rules (SHA-256 pinned), all-or-nothing rebooking, controller approval that re-checks every rule, 86 tests")],
    [cell("Our unique idea", { fontSize: 16, bold: true }), cell("—"),
      cell("Continuous re-validation: when the world changes after the plan (ATC hold, a second fatigue report, a leak found), the agent withdraws its own now-illegal proposals, stages the next legal option or escalates to a human. 13 edge cases prove it", { bold: true, color: C.text1 })],
  ];
  s.addTable(rows, { x: M, y: 1.55, w: W - 2 * M, colW: [2.35, 3.4, W - 2 * M - 5.75], rowH: [0.6, 1.0, 1.15, 0.95, 1.25],
    border: { type: "solid", color: BORDER, pt: 1 }, valign: "middle", margin: [0.06, 0.12, 0.06, 0.12], fontFace: "Calibri" });
}

// ------------------------------------------------------------------ 6. what works today
{
  const s = slide("What works today", "Technical · 30%");
  shot(s, "agent_run", { x: M, y: 1.5, w: 7.3, h: 5.15 }, { align: "left", alt: "Agent run on the live demo: input, steps and output" });
  const x = M + 7.6, w = W - M - x;
  card(s, x, 1.5, w, 3.95, "working now");
  text(s, [{ text: "Working now  ✓", options: { bold: true, fontSize: 19, color: C.text1, breakLine: true } }],
    { x: x + 0.3, y: 1.65, w: w - 0.5, h: 0.45 });
  text(s, bullets([
    "The 3 required services run end to end: get_turnaround_and_crew_state, execute_atomic_passenger_rebook, stage_controller_schedule_change",
    "Real LLM (Groq) recovery: 45 passengers + 48 bags in one BEGIN / COMMIT / ROLLBACK transaction",
    "Immutable guards for crew duty, maintenance sign-off and vulnerable priority; the LLM corrects itself",
    "Controller approval, engineer sign-off, departure release",
    "All 3 stretch goals: standby-crew matcher, critical path, EU261 cost (AED); 13 edge cases",
  ], 12), { x: x + 0.3, y: 2.1, w: w - 0.45, h: 3.3 }, { paraSpaceAfter: 3 });
  card(s, x, 5.6, w, 1.05, "not finished");
  text(s, [{ text: "Not finished yet  ", options: { bold: true, fontSize: 14, color: C.text1 } },
    { text: "Data is synthetic, because the brief supplies none and live feeds need airline system access. Crew rules are a simplified EASA model, not UAE-certified.",
      options: { fontSize: 11.5, color: C.dk2 } }], { x: x + 0.25, y: 5.66, w: w - 0.4, h: 0.95 }, { valign: "middle" });
  s.addNotes("Screenshot from the live demo after pressing Run recovery agent: the banner shows the LLM run with a guard correction (TURN-001) and a rollback-and-retry; KPIs show 0 at risk and 10/10 vulnerable protected; the feed shows each step.");
}

// ------------------------------------------------------------------ 7. how our agent works
{
  const s = slide("How our agent works", "Technical · 30%");
  const steps = [
    ["Trigger", "Controller presses Run recovery agent, or a world event arrives (ATC hold, fatigue report, leak)"],
    ["Plan", "Code collects facts with 6 read-only tools; the LLM returns a JSON plan: stand, captain, retime, holds, rebooking goal"],
    ["Act", "Each decision runs through a guarded tool: stage a network change, or execute the rebooking atomically"],
    ["Check", "Sealed rules, schemas and database constraints; rejected decisions go back to the LLM; re-validation after"],
    ["Output", "Changes waiting for approval, committed rebooking, passenger messages, AED cost, an executive brief"],
  ];
  const n = steps.length, gap = 0.28, cw = (W - 2 * M - (n - 1) * gap) / n, y = 1.5, h = 2.55;
  steps.forEach(([t, d], i) => {
    const x = M + i * (cw + gap);
    card(s, x, y, cw, h, t);
    num(s, x + 0.2, y + 0.22, i + 1);
    text(s, t, { x: x + 0.8, y: y + 0.24, w: cw - 0.9, h: 0.45 }, { fontSize: 19, bold: true, color: C.text1, valign: "middle" });
    text(s, d, { x: x + 0.2, y: y + 0.85, w: cw - 0.35, h: h - 1.0 }, { fontSize: 13.5, color: C.dk2 });
    if (i < n - 1) s.addShape(pres.shapes.CHEVRON, { x: x + cw + 0.04, y: y + h / 2 - 0.17, w: 0.2, h: 0.34,
      fill: { color: C.accent2 }, line: { color: C.accent2, width: 0 }, objectName: `chevron ${i}` });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 4.18, w: W - 2 * M, h: 0.42, rectRadius: 0.08,
    fill: { color: C.text1 }, line: { color: C.text1, width: 0 }, objectName: "required services" });
  text(s, [{ text: "Required services:  ", options: { bold: true, color: "FFFFFF" } },
    { text: "get_turnaround_and_crew_state()  ·  stage_controller_schedule_change()  ·  execute_atomic_passenger_rebook()",
      options: { color: "DBE6F7", fontFace: "Courier New" } }],
  { x: M + 0.25, y: 4.18, w: W - 2 * M - 0.5, h: 0.42 }, { fontSize: 11, valign: "middle" });
  const bw = (W - 2 * M - 0.3) / 2, by = 4.75, bh = 1.9;
  card(s, M, by, bw, bh, "tech stack");
  text(s, [{ text: "Tech stack", options: { bold: true, fontSize: 18, color: C.text1, breakLine: true } },
    ...bullets(["LLM: Groq openai/gpt-oss-120b (Ollama or Gemini also work; offline policy if no key)",
      "Python 3.12+ with our own agent loop, no framework",
      "SQLite with atomic transactions · Streamlit + Plotly UI",
      "Hosted on Streamlit Community Cloud"], 13)], { x: M + 0.3, y: by + 0.15, w: bw - 0.5, h: bh - 0.25 }, { paraSpaceAfter: 2 });
  card(s, M + bw + 0.3, by, bw, bh, "llm vs code");
  text(s, [{ text: "LLM vs code", options: { bold: true, fontSize: 18, color: C.text1, breakLine: true } },
    { text: "LLM decides: ", options: { bold: true, fontSize: 13, color: C.dk2 } },
    { text: "which stand, captain, retime and holds, how to rebook, message wording, the brief.", options: { fontSize: 13, color: C.dk2, breakLine: true } },
    { text: "Code decides: ", options: { bold: true, fontSize: 13, color: C.dk2 } },
    { text: "what is legal (crew duty, maintenance, priority, connection times), every seat and bag write, every number in messages, the costs.", options: { fontSize: 13, color: C.dk2, breakLine: true } },
    { text: "A human decides: ", options: { bold: true, fontSize: 13, color: C.dk2 } },
    { text: "every network change.", options: { fontSize: 13, color: C.dk2 } }],
  { x: M + bw + 0.6, y: by + 0.15, w: bw - 0.5, h: bh - 0.25 }, { paraSpaceAfter: 3 });
}

// ------------------------------------------------------------------ 8. code quality and safety
{
  const s = slide("Code quality and safety", "Technical · 30%");
  const tw = 4.15;
  card(s, M, 1.5, tw, 5.15, "repository structure");
  text(s, "Repository structure", { x: M + 0.25, y: 1.62, w: tw - 0.4, h: 0.4 }, { fontSize: 17, bold: true, color: C.text1 });
  // mirrors the GitHub repository (github.com/RithikhC/EagleX)
  const tree = [
    ["aeroturn/", "agent package, 22 modules"], ["  agent.py", "LLM planning loop"], ["  llm.py", "Groq / Ollama / Gemini"],
    ["  tools.py", "13 tools, dispatcher"], ["  guards.py", "sealed rules (+ .sha256)"], ["  sanitize.py", "injection filter"],
    ["  hitl.py", "human approval"], ["  reconcile.py", "re-validation"], ["  audit.py", "hash-chained log"],
    ["  recovery.py…", "rebook, crew, CPM, cost"], ["app.py", "Streamlit dashboard"], ["run_demo.py", "terminal demo"],
    ["tests/", "86 pytest tests"], ["data/", "synthetic scenario"], ["scripts/", "data, guard pin, decks"],
    ["docs/", "architecture, sources"], ["requirements.txt", "dependencies"], ["README.md", "how to run"],
  ];
  text(s, tree.map(([a, b], i) => [{ text: a.padEnd(17, " "), options: { fontFace: "Courier New", fontSize: 10, color: C.text1, bold: !a.startsWith(" ") } },
    { text: b, options: { fontFace: "Calibri", fontSize: 10.5, color: MUTED, breakLine: i < tree.length - 1 } }]).flat(),
  { x: M + 0.22, y: 2.05, w: tw - 0.3, h: 4.55 }, { paraSpaceAfter: 1.5 });
  const boxes = [
    ["Input validation", "Strict JSON schema on every tool. Unknown arguments are rejected (\"no overrides exist\"); IDs and times are checked; bad LLM JSON is retried"],
    ["Prompt-injection defence", "Passenger text is untrusted. Instruction-like text is withheld before it reaches the LLM and logged; message templates cannot carry facts"],
    ["Human approval", "Gate, crew swap, retime, holds and departure release pause for a named controller. Rules re-run at approval; decisions expire"],
    ["Logging", "Every tool call, guard verdict, approval and transaction goes into a hash-chained audit log; editing any entry breaks the chain"],
    ["Read/write separation", "Each tool is read, propose or write. The planner's fact phase is locked to read tools; approval is not a tool"],
    ["Deterministic validation", "25 rules in a sealed, SHA-256-pinned module; 86 tests and 13 edge cases, all passing"],
  ];
  const gx = M + tw + 0.3, gw = (W - M - gx - 0.3) / 2, gh = 1.6, gg = 0.17;
  boxes.forEach(([h, d], i) => {
    const x = gx + (i % 2) * (gw + 0.3), y = 1.5 + Math.floor(i / 2) * (gh + gg);
    card(s, x, y, gw, gh, h);
    text(s, [{ text: h, options: { bold: true, fontSize: 16, color: C.text1, breakLine: true } },
      { text: d, options: { fontSize: 12.5, color: C.dk2 } }], { x: x + 0.22, y: y + 0.12, w: gw - 0.4, h: gh - 0.2 }, { paraSpaceAfter: 3 });
  });
  s.addNotes("The five University-track guardrails are all here: deterministic validation, prompt-injection defence, read/write separation, human-in-the-loop pause and logging. The live demo's Guardrails tab shows live evidence for each (Appendix A).");
}

// ------------------------------------------------------------------ 9. architecture
{
  const s = slide("System architecture", "Architecture · 20%");
  // diagram: user -> interface -> agent -> dispatcher -> tools/data -> output, with guards, approval and audit
  const y = 1.6, h = 1.1, gap = 0.24, bw = (W - 2 * M - 6 * gap) / 7;
  const flow = [["Operations controller", "user", "DBE6F7"], ["OCC dashboard", "Streamlit", "DBE6F7"],
    ["AeroTurn agent", "LLM planner (Groq)", "1F5FC0"], ["Tool dispatcher", "schema · read/write · injection filter", "0B2D6B"],
    ["Aviation tools", "crew, stands, critical path, rebooking, cost", "DBE6F7"], ["Scenario database", "SQLite, atomic", "DBE6F7"],
    ["Output", "approval queue, rebooking, messages, AED cost, brief", "E8F5EC"]];
  const x0 = M;
  flow.forEach(([t, d, fill], i) => {
    const x = x0 + i * (bw + gap), dark = fill === "1F5FC0" || fill === "0B2D6B";
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: bw, h, rectRadius: 0.08, fill: { color: fill },
      line: { color: dark ? fill : BORDER, width: 1 }, objectName: `arch ${t}` });
    text(s, [{ text: t, options: { bold: true, fontSize: 13, color: dark ? "FFFFFF" : C.text1, breakLine: true } },
      { text: d, options: { fontSize: 10, color: dark ? "DBE6F7" : MUTED } }], { x: x + 0.06, y, w: bw - 0.12, h }, { align: "center", valign: "middle" });
    if (i < flow.length - 1) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + bw + 0.04, y: y + h / 2 - 0.12, w: 0.24, h: 0.24,
      fill: { color: C.accent2 }, line: { color: C.accent2, width: 0 }, objectName: `flow arrow ${i}` });
  });
  // guards under dispatcher + tools, approval under dashboard, audit spanning
  const gy = y + h + 0.42;
  const gx = x0 + 3 * (bw + gap);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: gx, y: gy, w: 2 * bw + gap, h: 0.72, rectRadius: 0.08, fill: { color: "FDECEC" },
    line: { color: "B91C1C", width: 1 }, objectName: "guards" });
  text(s, [{ text: "Validation: sealed guards", options: { bold: true, fontSize: 13, color: "B91C1C", breakLine: true } },
    { text: "every proposal and write is checked; illegal = blocked", options: { fontSize: 11, color: C.dk2 } }],
  { x: gx + 0.1, y: gy, w: 2 * bw + gap - 0.2, h: 0.72 }, { align: "center", valign: "middle" });
  const ax = x0 + (bw + gap);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ax, y: gy, w: 2 * bw + gap, h: 0.72, rectRadius: 0.08, fill: { color: "E8F5EC" },
    line: { color: "15803D", width: 1 }, objectName: "approval" });
  text(s, [{ text: "Human approval (HITL)", options: { bold: true, fontSize: 13, color: "15803D", breakLine: true } },
    { text: "network changes wait for the controller; rules re-run", options: { fontSize: 11, color: C.dk2 } }],
  { x: ax + 0.1, y: gy, w: 2 * bw + gap - 0.2, h: 0.72 }, { align: "center", valign: "middle" });
  [gx + bw / 2, gx + bw + gap + bw / 2, ax + bw / 2].forEach((cx, i) => s.addShape(pres.shapes.LINE,
    { x: cx, y: y + h, w: 0, h: 0.42, line: { color: MUTED, width: 1, dashType: "dash" }, objectName: `link ${i}` }));
  const uy = gy + 0.85;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x0 + (bw + gap), y: uy, w: 5 * bw + 4 * gap, h: 0.5, rectRadius: 0.08,
    fill: { color: "F3F4F6" }, line: { color: BORDER, width: 1 }, objectName: "audit" });
  text(s, [{ text: "Hash-chained audit log  ", options: { bold: true, color: C.text1 } },
    { text: "records every call, verdict, approval and transaction", options: { color: MUTED } }],
  { x: x0 + (bw + gap) + 0.1, y: uy, w: 5 * bw + 4 * gap - 0.2, h: 0.5 }, { fontSize: 12, align: "center", valign: "middle" });
  const by = 4.75, bw2 = (W - 2 * M - 0.3) / 2, bh = 1.9;
  card(s, M, by, bw2, bh, "modules");
  text(s, [{ text: "Modules", options: { bold: true, fontSize: 17, color: C.text1, breakLine: true } },
    ...bullets(["agent.py plans · tools.py dispatches 13 tools · guards.py owns every safety rule",
      "recovery, crew, turnaround, costs: domain engines · hitl.py: approvals",
      "reconcile.py: re-validation · audit.py: log · app.py: the dashboard"], 13)],
  { x: M + 0.3, y: by + 0.15, w: bw2 - 0.5, h: bh - 0.25 }, { paraSpaceAfter: 3 });
  card(s, M + bw2 + 0.3, by, bw2, bh, "data flow");
  text(s, [{ text: "Data flow", options: { bold: true, fontSize: 17, color: C.text1, breakLine: true } },
    ...bullets(["Synthetic scenario (seed 812) is copied into a private SQLite database per visitor",
      "Read tools build the facts; the LLM returns a plan; guarded writes commit in one transaction",
      "Every step is logged; the dashboard reads a cached snapshot of the database"], 13)],
  { x: M + bw2 + 0.6, y: by + 0.15, w: bw2 - 0.5, h: bh - 0.25 }, { paraSpaceAfter: 3 });
}

// ------------------------------------------------------------------ 10. user experience
{
  const s = slide("User experience", "UX · 20%");
  const items = [["ux_1", "Open the link: a Start-here guide explains the situation in four clicks. Press Run recovery agent"],
    ["ux_2", "The agent explains every step in the live feed. Each network change waits in the approval queue with Approve / Reject"],
    ["ux_3", "Approve and release: 0 connections at risk, 10/10 vulnerable passengers safe, EK813 released, AED saved"]];
  const cw = (W - 2 * M - 2 * 0.35) / 3, y = 1.5;
  items.forEach(([n, d], i) => {
    const x = M + i * (cw + 0.35);
    num(s, x, y, i + 1);
    shot(s, n, { x, y: y + 0.65, w: cw, h: 2.75 }, { valign: "top", alt: d });
    text(s, d, { x, y: y + 3.5, w: cw, h: 0.95 }, { fontSize: 13.5, color: C.dk2 });
  });
  card(s, M, 6.0, W - 2 * M, 0.62, "easy");
  text(s, "No training or install: a Start-here guide, plain-language buttons and tiles with hover help, a private copy per visitor.",
    { x: M + 0.3, y: 6.0, w: W - 2 * M - 0.6, h: 0.62 }, { fontSize: 15, color: C.text1, valign: "middle", bold: true });
}

// ------------------------------------------------------------------ 11. limitations and next steps
{
  const s = slide("Limitations and next steps", null);
  const bw = (W - 2 * M - 0.35) / 2, y = 1.5, h = 5.15;
  card(s, M, y, bw, h, "limitations");
  text(s, [{ text: "Current limitations", options: { bold: true, fontSize: 20, color: C.text1, breakLine: true } },
    ...bullets(["Runs on a synthetic but realistic scenario: one hub, one late aircraft, no live airline feeds yet",
      "Crew rules are a simplified EASA model, not a certified UAE GCAA implementation; cost rates are stated assumptions",
      "Known edge cases are handled by re-validation, but cancellations and multi-aircraft disruptions are not modelled",
      "Free-tier LLM rate limits: the agent waits and retries, and falls back to a labelled offline policy"], 15)],
  { x: M + 0.35, y: y + 0.25, w: bw - 0.6, h: h - 0.4 }, { paraSpaceAfter: 10 });
  card(s, M + bw + 0.35, y, bw, h, "next steps");
  text(s, [{ text: "If we advance", options: { bold: true, fontSize: 20, color: C.text1, breakLine: true } },
    ...bullets(["Adapters to real systems (reservations, baggage, crew, maintenance, airport A-CDM) through industry message standards; the guards stay unchanged",
      "Harder inputs: cancellations, diversions and several late aircraft at once, each with new edge cases before release",
      "Learn from controller approvals and rejections to rank options",
      "To deploy for real: shadow mode at one hub, an on-premise LLM, security review and certified crew rules"], 15)],
  { x: M + bw + 0.7, y: y + 0.25, w: bw - 0.6, h: h - 0.4 }, { paraSpaceAfter: 10 });
}

// ------------------------------------------------------------------ 12. try our agent
{
  const s = slide("Try our agent", null);
  card(s, M, 1.55, W - 2 * M, 2.3, "links");
  text(s, [{ text: "Project link:  ", options: { bold: true, color: C.text1 } },
    { text: LIVE, options: { color: C.accent1, hyperlink: { url: LIVE }, breakLine: true } },
    { text: "Code:  ", options: { bold: true, color: C.text1 } },
    { text: CODE, options: { color: C.accent1, hyperlink: { url: CODE }, breakLine: true } },
    { text: "Contact:  ", options: { bold: true, color: C.text1 } },
    { text: EMAIL, options: { color: C.accent1, hyperlink: { url: `mailto:${EMAIL}` } } }],
  { x: M + 0.4, y: 1.65, w: W - 2 * M - 0.8, h: 2.1 }, { fontSize: 21, valign: "middle", paraSpaceAfter: 10 });
  const steps = [["Open the link", "The Start-here guide explains the disruption and the four clicks"],
    ["Press Run recovery agent", "Watch the LLM plan, the guards check and the rebooking commit"],
    ["Approve all, then Sign-off & release", "You are the controller. The Try-to-break-it row shows the guards stopping a rogue AI"]];
  const cw = (W - 2 * M - 2 * 0.3) / 3;
  steps.forEach(([h, d], i) => {
    const x = M + i * (cw + 0.3), y = 4.15;
    card(s, x, y, cw, 1.95, h);
    num(s, x + 0.25, y + 0.25, i + 1);
    text(s, [{ text: h, options: { bold: true, fontSize: 17, color: C.text1, breakLine: true } },
      { text: d, options: { fontSize: 14, color: C.dk2 } }], { x: x + 0.9, y: y + 0.22, w: cw - 1.1, h: 1.65 });
  });
  text(s, "Run it locally: pip install -r requirements.txt, then streamlit run app.py (works with no API key). Tests: python -m pytest -q",
    { x: M, y: 6.25, w: W - 2 * M, h: 0.4 }, { fontSize: 13, color: MUTED });
}

// ------------------------------------------------------------------ appendix
{
  const s = slide("Appendix A · Guardrails in the live demo", null);
  shot(s, "guardrails", { x: M, y: 1.5, w: W - 2 * M, h: 4.75 }, { alt: "Guardrails tab of the live demo" });
  text(s, "The Guardrails tab shows live evidence for each University-track guardrail, computed from the session's database and audit log. The Injection test button sends a planted malicious passenger remark through the agent's tools.",
    { x: M, y: 6.3, w: W - 2 * M, h: 0.45 }, { fontSize: 13, color: MUTED });
}
{
  const s = slide("Appendix B · 13 edge cases, all passing", null);
  shot(s, "edge_kpis", { x: M, y: 1.5, w: W - 2 * M, h: 0.95 }, { align: "left", alt: "Edge case summary" });
  const cw = (W - 2 * M - 2 * 0.3) / 3;
  ["edge_ec02", "edge_ec07", "edge_ec09"].forEach((n, i) => shot(s, n, { x: M + i * (cw + 0.3), y: 2.65, w: cw, h: 4.05 }, { valign: "top" }));
}
{
  const s = slide("Appendix C · Data and sources", null);
  const bw = (W - 2 * M - 0.35) / 2;
  card(s, M, 1.5, bw, 5.15, "data");
  text(s, [{ text: "Datasets", options: { bold: true, fontSize: 18, color: C.text1, breakLine: true } },
    ...bullets(["Scenario database data/aircraft_turnaround_disruption.sqlite: synthetic and byte-reproducible (seed 812)",
      "342 passengers (280 connecting, 45 broken), 356 bags, 44 flights, 33 crew, 3 maintenance items, 11 turnaround tasks",
      "Scenario facts from the Domain 4 problem statement",
      "Airport codes and coordinates: OurAirports open data",
      "Names, timetables and the partner airline are synthetic; SSR codes are industry standard"], 13)],
  { x: M + 0.3, y: 1.65, w: bw - 0.55, h: 4.9 }, { paraSpaceAfter: 6 });
  card(s, M + bw + 0.35, 1.5, bw, 5.15, "sources");
  text(s, [{ text: "Rules and public sources", options: { bold: true, fontSize: 18, color: C.text1, breakLine: true } },
    ...bullets(["Crew duty: EASA ORO.FTL.205 Table 2; standby CS FTL.1.225; rest ORO.FTL.235",
      "Engineer licences: EASA Part-66 (B1 for hydraulics)",
      "Bag-passenger matching: ICAO Annex 17; IATA Hold Baggage Reconciliation",
      "Compensation and care: EU Regulation 261/2004 Arts. 3, 7, 9; CJEU Sturgeon, Folkerts, Wegener; Gahan v Emirates [2017] EWCA Civ 1530",
      "Delay cost: EUROCONTROL / University of Westminster reference values; 1 EUR = 4.10 AED",
      "Every assumption and calculation: docs/DATA_SOURCES.md and docs/NUMBERS_EXPLAINED.md"], 13)],
  { x: M + bw + 0.65, y: 1.65, w: bw - 0.55, h: 4.9 }, { paraSpaceAfter: 6 });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  const { applyTheme } = require(process.env.APPLY_THEME);
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
