// TechX Dubai'26 · AI Agent Arena · Round 1 submission: the official template's design and content,
// condensed to the 8 slides the submission form allows.
// node build_round1.js <repoRoot> <out.pptx>      (images: docs/img/round1/*.png, captured from the live demo)
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = process.argv[2];
const OUT = process.argv[3];
const IMG = (n) => n === "architecture" ? path.join(ROOT, "docs", "img", "architecture.png")
  : path.join(ROOT, "docs", "img", "round1", `${n}.png`);
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

// ------------------------------------------------------------------ 1. cover and team
{
  const s = pres.addSlide({ masterName: "Cover" });
  s.addText("AeroTurn", { placeholder: "title" });
  text(s, "Autonomous aircraft turnaround and atomic disruption recovery agent",
    { x: M + 0.13, y: 3.65, w: 11, h: 0.5 }, { fontSize: 24, color: C.background1 });
  text(s, "EagleX  ·  BITS Pilani, Dubai Campus  ·  University Track  ·  Domain 4: Aviation & Airport Operations",
    { x: M + 0.13, y: 4.25, w: 12, h: 0.45 }, { fontSize: 18, color: "C9D8F0" });
  const team = [["Rithikh Chandran", "Team lead · architecture and the AI agent"],
    ["Mohammed Fawwaz Husain", "Safety guards, atomic transactions, testing"],
    ["Reuben Thomas Thovelil", "Scenario data, aviation research, presentation"]];
  team.forEach(([n, r], i) => text(s, [{ text: n, options: { bold: true, fontSize: 16, color: C.background1, breakLine: true } },
    { text: r, options: { fontSize: 13, color: "C9D8F0" } }], { x: M + 0.13 + i * 4.0, y: 4.95, w: 3.85, h: 0.75 }));
  text(s, [{ text: "Live demo  ", options: { color: "C9D8F0" } },
    { text: LIVE.replace("https://", ""), options: { color: C.background1, bold: true, hyperlink: { url: LIVE } } },
    { text: "      Code  ", options: { color: "C9D8F0" } },
    { text: CODE.replace("https://", ""), options: { color: C.background1, bold: true, hyperlink: { url: CODE } } }],
    { x: M + 0.13, y: 5.95, w: 12, h: 0.4 }, { fontSize: 15 });
  s.addNotes("Round 1 submission for TechX Dubai'26 AI Agent Arena, University Track, Domain 4. Team EagleX.");
}

// ------------------------------------------------------------------ 2. problem, solution and value
{
  const s = slide("The problem and our solution", "Problem Fit · 25%");
  card(s, M, 1.45, W - 2 * M, 0.95, "problem statement");
  text(s, [{ text: "Problem  ", options: { bold: true, color: C.text1 } },
    { text: "EK-812 lands at Dubai 75 min late: 45 of its 280 connecting passengers miss their flights (10 vulnerable), the crew "
      + "is 20 min from its legal duty limit, a hydraulic defect needs an engineer's sign-off and the next captain is fatigued.",
      options: { color: C.dk2 } }], { x: M + 0.25, y: 1.45, w: W - 2 * M - 0.5, h: 0.95 }, { fontSize: 14, valign: "middle" });
  const cols = [
    ["Who is affected", "Operations controllers, crew control, engineers and ground staff; 280 connecting passengers, including children alone, wheelchair users and a medical case"],
    ["Why it matters", "Re-protecting them on tomorrow's flight costs AED 133,390 in compensation and care, and 0 of 45 arrive the same day. One wrong call breaks crew-duty law"],
    ["How it is done now", "Stands, crews, maintenance and reservations sit in separate systems; controllers reconcile them by phone under a 25-minute deadline"],
  ];
  const cw = (W - 2 * M - 2 * 0.25) / 3;
  cols.forEach(([h, d], i) => {
    const x = M + i * (cw + 0.25), y = 2.55;
    card(s, x, y, cw, 1.75, h);
    num(s, x + 0.2, y + 0.18, i + 1, 0.42);
    text(s, h, { x: x + 0.75, y: y + 0.18, w: cw - 0.9, h: 0.42 }, { fontSize: 16, bold: true, color: C.text1, valign: "middle" });
    text(s, d, { x: x + 0.2, y: y + 0.7, w: cw - 0.35, h: 1.0 }, { fontSize: 12.5, color: C.dk2 });
  });
  const y = 4.45, h = 2.2;
  card(s, M, y, W - 2 * M, h, "solution");
  text(s, [{ text: "Our agent  ", options: { bold: true, color: C.text1, breakLine: true } },
    { text: "AeroTurn helps controllers recover the disruption: the AI plans the stand, captain, retime and rebooking of 45 "
      + "passengers and 48 bags in one transaction, code enforces every safety rule, and the controller approves.",
      options: { color: C.dk2 } }], { x: M + 0.25, y: y + 0.15, w: 4.1, h: h - 0.3 }, { fontSize: 13.5 });
  shot(s, "map_before", { x: M + 4.45, y: y + 0.12, w: 2.3, h: h - 0.24 }, { alt: "Before: 45 broken connections in red" });
  s.addShape(pres.shapes.RIGHT_ARROW, { x: M + 6.83, y: y + h / 2 - 0.16, w: 0.32, h: 0.32, fill: { color: C.accent2 },
    line: { color: C.accent2, width: 0 }, objectName: "before after arrow" });
  shot(s, "map_after", { x: M + 7.22, y: y + 0.12, w: 2.3, h: h - 0.24 }, { alt: "After: connections protected in green" });
  [["−62%", "compensation + care"], ["45/45", "arrive the same day"], ["10/10", "vulnerable protected"]].forEach(([v, l], i) =>
    text(s, [{ text: v + "  ", options: { bold: true, fontSize: 22, color: C.accent3 } }, { text: l, options: { fontSize: 12, color: C.dk2 } }],
      { x: M + 9.65, y: y + 0.2 + i * 0.62, w: 2.4, h: 0.6 }, { valign: "middle" }));
  s.addNotes("AED 133,390 legacy vs AED 50,440 with AeroTurn in the recorded live run (−70% with an 8-minute hold on EK418). See docs/NUMBERS_EXPLAINED.md.");
}

// ------------------------------------------------------------------ 3. what makes us different
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

// ------------------------------------------------------------------ 4. what works today
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

// ------------------------------------------------------------------ 5. how our agent works
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

// ------------------------------------------------------------------ 6. code quality and safety
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
  s.addNotes("The five University-track guardrails are all here: deterministic validation, prompt-injection defence, read/write separation, human-in-the-loop pause and logging. The live demo's Guardrails tab shows live evidence for each.");
}

// ------------------------------------------------------------------ 7. architecture and user experience
{
  const s = slide("Architecture and user experience", "Architecture & UX · 20%");
  const z = png(IMG("architecture"));
  const aw = 7.15, ah = aw * z.h / z.w;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 1.45, w: aw + 0.1, h: ah + 0.1, rectRadius: 0.06, fill: { color: "FFFFFF" },
    line: { color: BORDER, width: 1 }, objectName: "architecture frame" });
  s.addImage({ path: IMG("architecture"), x: M + 0.05, y: 1.5, w: aw, h: ah, objectName: "architecture",
    altText: "Architecture: controller, dashboard, LLM agent, tool dispatcher, aviation tools, SQLite, output; guards, human approval, re-validation and audit log" });
  const ty = 1.5 + ah + 0.15;
  text(s, [{ text: "Modules  ", options: { bold: true, color: C.text1 } },
    { text: "agent.py plans · tools.py dispatches 13 tools · guards.py owns every rule · hitl.py approvals · reconcile.py re-validation · audit.py log · app.py dashboard",
      options: { color: C.dk2, breakLine: true } },
    { text: "Data flow  ", options: { bold: true, color: C.text1 } },
    { text: "seed-812 scenario copied into a private SQLite per visitor → read tools → LLM plan → guarded writes in one transaction → audit log → dashboard",
      options: { color: C.dk2 } }], { x: M, y: ty, w: aw + 0.1, h: 6.65 - ty }, { fontSize: 11.5, paraSpaceAfter: 4 });
  const ux = M + aw + 0.4, uw = W - M - ux;
  text(s, "User experience: four clicks", { x: ux, y: 1.45, w: uw, h: 0.4 }, { fontSize: 17, bold: true, color: C.text1 });
  [["ux_1", "A Start-here guide explains the situation; press Run recovery agent"],
   ["ux_2", "The live feed explains every step; changes wait in the approval queue"],
   ["ux_3", "Approve all, then Sign-off & release: 0 at risk, 10/10 safe, EK813 released"]].forEach(([n, d], i) => {
    const y = 1.95 + i * 1.5;
    num(s, ux, y + 0.42, i + 1, 0.4);
    shot(s, n, { x: ux + 0.5, y, w: 2.25, h: 1.35 }, { align: "left", alt: d });
    text(s, d, { x: ux + 2.85, y, w: uw - 2.85, h: 1.35 }, { fontSize: 12, color: C.dk2, valign: "middle" });
  });
  text(s, "No training or install: plain-language buttons, hover help, a private copy per visitor.",
    { x: ux, y: 6.4, w: uw, h: 0.3 }, { fontSize: 11.5, bold: true, color: C.text1 });
}

// ------------------------------------------------------------------ 8. limitations, next steps and links
{
  const s = slide("Limitations, next steps and try it", null);
  const bw = (W - 2 * M - 0.3) / 2, y = 1.45, h = 2.75;
  card(s, M, y, bw, h, "limitations");
  text(s, [{ text: "Current limitations", options: { bold: true, fontSize: 17, color: C.text1, breakLine: true } },
    ...bullets(["Synthetic scenario (one hub, one late aircraft): the brief supplies no data and live feeds need airline access",
      "Crew rules are a simplified EASA model, not UAE-certified; cost rates are stated assumptions",
      "Free-tier LLM rate limits: the agent retries, then falls back to a labelled offline policy"], 12.5)],
  { x: M + 0.25, y: y + 0.15, w: bw - 0.45, h: h - 0.25 }, { paraSpaceAfter: 5 });
  card(s, M + bw + 0.3, y, bw, h, "next steps");
  text(s, [{ text: "If we advance", options: { bold: true, fontSize: 17, color: C.text1, breakLine: true } },
    ...bullets(["Adapters to real reservation, baggage, crew, maintenance and airport (A-CDM) systems; guards unchanged",
      "Cancellations, diversions and several late aircraft at once, each with new edge cases",
      "Deploy for real: shadow mode at one hub, on-premise LLM, security review, certified crew rules"], 12.5)],
  { x: M + bw + 0.55, y: y + 0.15, w: bw - 0.45, h: h - 0.25 }, { paraSpaceAfter: 5 });
  const ly = 4.4;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: ly, w: W - 2 * M, h: 1.65, rectRadius: 0.08, fill: { color: C.text1 },
    line: { color: C.text1, width: 0 }, objectName: "links" });
  text(s, [{ text: "Try our agent", options: { bold: true, fontSize: 18, color: "FFFFFF", breakLine: true } },
    { text: "Project link:  ", options: { bold: true, color: "DBE6F7" } },
    { text: LIVE, options: { color: "FFFFFF", hyperlink: { url: LIVE }, breakLine: true } },
    { text: "Code:  ", options: { bold: true, color: "DBE6F7" } },
    { text: CODE, options: { color: "FFFFFF", hyperlink: { url: CODE } } },
    { text: "      Contact:  ", options: { bold: true, color: "DBE6F7" } },
    { text: EMAIL, options: { color: "FFFFFF", hyperlink: { url: `mailto:${EMAIL}` } } }],
  { x: M + 0.3, y: ly + 0.12, w: W - 2 * M - 0.6, h: 1.45 }, { fontSize: 15, valign: "middle", paraSpaceAfter: 4 });
  text(s, "Data and sources: synthetic seed-812 scenario (342 passengers, 356 bags, 33 crew); OurAirports; EASA ORO.FTL and Part-66; ICAO Annex 17; EU Regulation 261/2004. Full list: docs/DATA_SOURCES.md. Run locally: pip install -r requirements.txt, streamlit run app.py",
    { x: M, y: 6.13, w: W - 2 * M, h: 0.6 }, { fontSize: 11, color: MUTED });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  const { applyTheme } = require(process.env.APPLY_THEME);
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
