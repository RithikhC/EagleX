// AeroTurn deck: simple, clean, screenshots straight from the demo.
// node build_deck.js <repoRoot> <out.pptx>
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = process.argv[2];
const OUT = process.argv[3];
const IMG = (n) => path.join(ROOT, "docs", "img", "demo", `${n}.png`);
const F = JSON.parse(fs.readFileSync(path.join(__dirname, "facts.json"), "utf8"));

const THEME = {
  name: "AeroTurn",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0E1726", lt1: "FFFFFF", dk2: "1B2A41", lt2: "F2F4F7",
    accent1: "F2A900", accent2: "3987E5", accent3: "0CA30C", accent4: "D03B3B", accent5: "EC835A", accent6: "667085",
    hlink: "3987E5", folHlink: "667085",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "AeroTurn: autonomous turnaround and disruption recovery";
pres.author = "Team EagleX";
pres.subject = "Domain 4: Aviation & Airport Operations";
const C = pres.SchemeColor;

const W = 13.333, H = 7.5, M = 0.6;

// ------------------------------------------------------------------ layouts
pres.defineSlideMaster({
  title: "Dark title",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.05, w: 5.9, h: 1.3, fontSize: 60, bold: true,
      color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 3.45, w: 5.6, h: 1.2, fontSize: 22,
      color: C.background2, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "Content",
  background: { color: C.background1 },
  margin: [0.5, M, 0.6, M],
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: M, y: 0.32, w: 9, h: 0.32, fontSize: 13, bold: true,
      color: C.accent1, charSpacing: 2, margin: 0, valign: "middle", align: "left" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.64, w: W - 2 * M, h: 0.72, fontSize: 34,
      bold: true, color: C.text1, margin: 0, valign: "middle", align: "left" }, text: "" } },
    { text: { text: "AeroTurn · Team EagleX", options: { x: M, y: 7.02, w: 5, h: 0.28, fontSize: 10, color: C.accent6,
      margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.6, y: 7.02, w: 0.6, h: 0.28, fontSize: 10, color: C.accent6, align: "right", margin: 0 },
});
pres.defineSlideMaster({
  title: "Dark closing",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.45, w: 6, h: 0.9, fontSize: 44, bold: true,
      color: C.background1, margin: 0, valign: "middle", align: "left" }, text: "" } },
  ],
});

// ------------------------------------------------------------------ helpers
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
// Screenshot in a dark rounded frame (the deck's one visual motif). Fits inside box, keeps aspect ratio.
function shot(slide, name, box, { align = "center", valign = "top", pad = 0.07, alt } = {}) {
  const s = pngSize(IMG(name));
  const ar = s.w / s.h;
  let w = box.w - 2 * pad, h = w / ar;
  if (h > box.h - 2 * pad) { h = box.h - 2 * pad; w = h * ar; }
  const fw = w + 2 * pad, fh = h + 2 * pad;
  const fx = align === "left" ? box.x : align === "right" ? box.x + box.w - fw : box.x + (box.w - fw) / 2;
  const fy = valign === "top" ? box.y : valign === "bottom" ? box.y + box.h - fh : box.y + (box.h - fh) / 2;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: fx, y: fy, w: fw, h: fh, rectRadius: 0.08, fill: { color: "0D0D0D" }, line: { color: "0D0D0D", width: 0.5 },
    shadow: { type: "outer", color: "0E1726", opacity: 0.22, blur: 8, offset: 3, angle: 90 }, objectName: `${name} frame`,
  });
  slide.addImage({ path: IMG(name), x: fx + pad, y: fy + pad, w, h, altText: alt || name, objectName: name });
  return { x: fx, y: fy, w: fw, h: fh };
}
function badge(slide, x, y, label, { color = C.accent1, size = 0.42, font = 14, txt = C.text1 } = {}) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: size, h: size, fill: { color }, line: { color, width: 0 }, objectName: `badge ${label}` });
  slide.addText(String(label), { x, y, w: size, h: size, fontSize: font, bold: true, color: txt, align: "center",
    valign: "middle", margin: 0, isTextBox: true });
}
// Rows of: badge + bold header + one-line description
function points(slide, items, { x, y, w, gap = 0.95, head = 16, body = 13.5, badgeColor = C.accent1 }) {
  items.forEach((it, i) => {
    const yy = y + i * gap;
    badge(slide, x, yy + 0.02, it.b ?? i + 1, { color: it.color || badgeColor, txt: it.txt || C.text1, font: it.font || 14 });
    slide.addText([
      { text: it.h, options: { bold: true, fontSize: head, color: C.text1, breakLine: true } },
      { text: it.d, options: { fontSize: body, color: C.accent6 } },
    ], { x: x + 0.6, y: yy - 0.04, w: w - 0.6, h: gap - 0.05, valign: "top", margin: 0, isTextBox: true,
      paraSpaceAfter: 2 });
  });
}
function stat(slide, x, y, w, value, label, { color = C.text1, size = 40, fill = C.background2 } = {}) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 1.25, rectRadius: 0.1, fill: { color: fill },
    line: { color: fill, width: 0 }, objectName: `stat ${label}` });
  slide.addText(value, { x: x + 0.2, y: y + 0.1, w: w - 0.4, h: 0.68, fontSize: size, bold: true, color, margin: 0,
    valign: "middle", isTextBox: true });
  slide.addText(label, { x: x + 0.2, y: y + 0.76, w: w - 0.4, h: 0.4, fontSize: 13, color: C.accent6, margin: 0,
    valign: "top", isTextBox: true });
}
function content(section, kicker, title) {
  const s = pres.addSlide({ masterName: "Content", sectionTitle: section });
  s.addText(kicker, { placeholder: "kicker" });
  s.addText(title, { placeholder: "title" });
  return s;
}
function label(slide, text, x, y, w, { color = C.accent6, size = 12, bold = true } = {}) {
  slide.addText(text, { x, y, w, h: 0.3, fontSize: size, bold, color, margin: 0, valign: "middle", isTextBox: true });
}

// ------------------------------------------------------------------ 1. title
pres.addSection({ title: "Introduction" });
{
  const s = pres.addSlide({ masterName: "Dark title", sectionTitle: "Introduction" });
  s.addText("AeroTurn", { placeholder: "title" });
  s.addText("Autonomous aircraft turnaround and atomic disruption recovery agent", { placeholder: "body" });
  s.addText("Domain 4 · Aviation & Airport Operations · Team EagleX", { x: M, y: 4.85, w: 5.8, h: 0.35, fontSize: 15,
    bold: true, color: C.accent1, margin: 0, isTextBox: true });
  s.addText([
    { text: "Live demo  ", options: { color: C.accent6, breakLine: false } },
    { text: "aeroturn-eaglex.streamlit.app", options: { color: C.background1, hyperlink: { url: "https://aeroturn-eaglex.streamlit.app" }, breakLine: true } },
    { text: "Code  ", options: { color: C.accent6 } },
    { text: "github.com/RithikhC/EagleX", options: { color: C.background1, hyperlink: { url: "https://github.com/RithikhC/EagleX" } } },
  ], { x: M, y: 5.45, w: 5.8, h: 0.8, fontSize: 14, margin: 0, isTextBox: true, paraSpaceAfter: 4 });
  shot(s, "overview", { x: 6.85, y: 0.9, w: 5.9, h: 5.7 }, { valign: "middle", alt: "AeroTurn OCC dashboard at 14:50" });
  s.addNotes("AeroTurn is an operations-control agent for a late-aircraft disruption at Dubai. The LLM decides what to try, code decides what is allowed, and a human approves every network change.");
}

// ------------------------------------------------------------------ 2. the disruption
{
  const s = content("Introduction", "THE PROBLEM · 14:50 AT DXB", "One late aircraft, five problems at once");
  shot(s, "overview", { x: M, y: 1.65, w: 7.4, h: 5.15 }, { align: "left", alt: "Dashboard before recovery" });
  points(s, [
    { h: "EK812 is 75 minutes late", d: "Blocks in at 15:20 instead of 14:05" },
    { h: "45 of 280 connections break", d: "10 of them vulnerable: unaccompanied minors, wheelchair, medical" },
    { h: "Inbound crew: 20 minutes of duty left", d: "Waiting for the planned stand breaks the limit" },
    { h: "Hydraulic defect, no sign-off yet", d: "A licensed B1 engineer must certify before departure" },
    { h: "Outbound captain reports fatigue", d: "EK813 needs a legal replacement" },
  ], { x: 8.45, y: 1.75, w: 4.3, gap: 1.0 });
  s.addNotes("These are the facts from the problem statement, recreated in a reproducible synthetic dataset (seed 812).");
}

// ------------------------------------------------------------------ 3. how it works
{
  const s = content("Introduction", "HOW AEROTURN DECIDES", "The LLM proposes, code decides, a human approves");
  const cols = [
    { n: "1", h: "LLM agent", c: C.accent2, lines: ["Reads the situation through tools", "Chooses gate, captain, retime, holds and how to rebook", "Writes passenger messages and the brief"] },
    { n: "2", h: "Code guards", c: C.accent1, lines: ["Sealed Python rules, SHA-256 pinned", "Crew duty, maintenance sign-off, vulnerable-passenger priority", "Atomic SQLite batches: vulnerable passengers first"] },
    { n: "3", h: "Human controller", c: C.accent3, lines: ["Approves gate, crew, retime and release", "Guards run again at approval", "Decisions expire when the window closes"] },
  ];
  const cw = 3.75, cg = 0.42, cy = 1.75, ch = 3.55;
  cols.forEach((col, i) => {
    const x = M + i * (cw + cg);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: cy, w: cw, h: ch, rectRadius: 0.12, fill: { color: C.background2 },
      line: { color: C.background2, width: 0 }, objectName: `card ${col.h}` });
    badge(s, x + 0.35, cy + 0.35, col.n, { color: col.c, size: 0.55, font: 18, txt: i === 1 ? C.text1 : C.background1 });
    s.addText(col.h, { x: x + 1.05, y: cy + 0.35, w: cw - 1.3, h: 0.55, fontSize: 22, bold: true, color: C.text1,
      margin: 0, valign: "middle", isTextBox: true });
    s.addText(col.lines.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < col.lines.length - 1 } })),
      { x: x + 0.35, y: cy + 1.15, w: cw - 0.6, h: ch - 1.35, fontSize: 15, color: C.text1, margin: 0, valign: "top",
        paraSpaceAfter: 8, isTextBox: true });
    if (i < 2) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + cw + 0.07, y: cy + ch / 2 - 0.18, w: 0.28, h: 0.36,
      fill: { color: C.accent6 }, line: { color: C.accent6, width: 0 }, objectName: `arrow ${i}` });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 5.65, w: W - 2 * M, h: 1.0, rectRadius: 0.12, fill: { color: C.text1 },
    line: { color: C.text1, width: 0 }, objectName: "revalidation banner" });
  s.addText([
    { text: "Continuous re-validation.  ", options: { bold: true, color: C.accent1 } },
    { text: "When the world changes after the plan, every pending decision is re-checked: illegal ones are withdrawn, a legal replacement is staged, or the problem is escalated to a human.", options: { color: C.background1 } },
  ], { x: M + 0.35, y: 5.65, w: W - 2 * M - 0.7, h: 1.0, fontSize: 15, margin: 0, valign: "middle", isTextBox: true });
  s.addNotes("This is the separation the judges asked for. The LLM never writes to the database directly; every action goes through a guarded tool, and network changes wait for a named human.");
}

// ------------------------------------------------------------------ 4. scenario 1
pres.addSection({ title: "Scenarios" });
{
  const s = content("Scenarios", "SCENARIO 1 · RUN RECOVERY AGENT", "One click: the agent recovers the network");
  shot(s, "agent_banner_kpis", { x: M, y: 1.6, w: W - 2 * M, h: 2.3 }, { align: "left", alt: "Banner and KPIs after the agent run" });
  shot(s, "agent_rowA", { x: M, y: 4.1, w: 8.3, h: 2.75 }, { align: "left", alt: "Network map, critical path and crew legality after the run" });
  stat(s, 9.25, 4.1, 3.48, F.at_risk, "connections at risk after the run", { color: C.accent3 });
  stat(s, 9.25, 5.55, 3.48, F.vulnerable, "vulnerable passengers protected", { color: C.accent3 });
  s.addNotes(F.agent_note);
}

// ------------------------------------------------------------------ 5. scenario 1 detail
{
  const s = content("Scenarios", "SCENARIO 1 · WHAT THE JUDGES SEE", "Every decision is visible and auditable");
  shot(s, "agent_rowC", { x: M, y: 1.6, w: W - 2 * M, h: 3.85 }, { align: "left", alt: "Event feed, controller queue and guard board" });
  const cap = [
    ["Live event feed", "LLM decisions, tool calls, guard blocks, commit and rollback, newest first"],
    ["Approval queue", "Gate, hold, crew swap and retime wait for a named human"],
    ["Guard board", "Every refusal with its rule code: the LLM is corrected, not trusted"],
  ];
  cap.forEach(([h, d], i) => {
    const x = M + i * 4.1;
    badge(s, x, 5.75, i + 1);
    s.addText([{ text: h, options: { bold: true, fontSize: 16, color: C.text1, breakLine: true } },
      { text: d, options: { fontSize: 13.5, color: C.accent6 } }], { x: x + 0.6, y: 5.7, w: 3.35, h: 1.1, margin: 0, valign: "top", isTextBox: true });
  });
  s.addNotes("The feed is rebuilt from the hash-chained audit log, so it survives a page reload and can be verified.");
}

// ------------------------------------------------------------------ 6. scenario 2
{
  const s = content("Scenarios", "SCENARIO 2 · USE TIRED CREW · SKIP SIGN-OFF · TRY AN OVERRIDE", "Guards stop a rogue AI");
  const rows = [["duty_breach", "Dispatch EK813 with the tired inbound crew"], ["no_crs", "Dispatch before the hydraulic sign-off"], ["override", "Call a tool with override=True"]];
  let y = 1.6;
  rows.forEach(([n, t]) => {
    label(s, t, M, y, 6.6, { color: C.text1, size: 14 });
    const r = shot(s, n, { x: M, y: y + 0.32, w: 6.6, h: 2.5 }, { align: "left", alt: t });
    y += 0.32 + r.h + 0.14;
  });
  points(s, [
    { h: "Plain Python, sealed", d: "Assigning to the guard module raises an error", b: "✓", color: C.accent3, txt: C.background1 },
    { h: "Tamper-evident", d: "guards.py is SHA-256 pinned; the agent refuses to start if it changes", b: "✓", color: C.accent3, txt: C.background1 },
    { h: "No override exists", d: "Strict tool schemas reject unknown arguments", b: "✓", color: C.accent3, txt: C.background1 },
  ], { x: 7.85, y: 1.75, w: 4.9, gap: 1.45 });
  s.addNotes("Each button is a rogue LLM proposal. The guard blocks it with the exact rule: FTL-001 for every crew member, MX-001 for the missing certificate, and a schema rejection for the override argument.");
}

// ------------------------------------------------------------------ 7. scenario 3
{
  const s = content("Scenarios", "SCENARIO 3 · CRASH MID-SAVE", "All or nothing: a failure leaves no trace");
  shot(s, "rollback", { x: M, y: 1.6, w: W - 2 * M, h: 1.8 }, { align: "left", alt: "Rollback banner" });
  const layers = [
    ["Guard pre-check", "The whole batch is validated before any write"],
    ["Database constraints", "Unique seat, one booking per leg, cabin trigger"],
    ["Invariant scan", "No double booking or orphaned bag inside the transaction"],
    ["Deferred foreign key", "A bag can't commit onto a flight without its owner"],
  ];
  layers.forEach(([h, d], i) => {
    const x = M + i * 3.08, y = 4.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.85, h: 2.55, rectRadius: 0.12, fill: { color: C.background2 },
      line: { color: C.background2, width: 0 }, objectName: `layer ${i + 1}` });
    badge(s, x + 0.3, y + 0.3, i + 1, { size: 0.5, font: 16 });
    s.addText([{ text: h, options: { bold: true, fontSize: 17, color: C.text1, breakLine: true } },
      { text: d, options: { fontSize: 14, color: C.accent6 } }], { x: x + 0.3, y: y + 0.95, w: 2.3, h: 1.45, margin: 0, valign: "top", paraSpaceAfter: 4, isTextBox: true });
  });
  s.addNotes("A seat is sold to someone else halfway through the rebooking. That transaction rolls back completely, the state fingerprint is identical, and the retry commits on fresh inventory. The agent itself writes in ordered batches (vulnerable passengers first, then batches of 10), so a failure only ever undoes its own batch.");
}

// ------------------------------------------------------------------ 8. scenario 4
{
  const s = content("Scenarios", "SCENARIO 4 · VULNERABLE PRIORITY · NAIVE AI VS RULES", "Vulnerable passengers first, always");
  shot(s, "priority", { x: M, y: 1.6, w: 7.6, h: 3.6 }, { align: "left", alt: "Recovery flow and priority queue" });
  shot(s, "naive", { x: M, y: 5.35, w: 7.6, h: 1.5 }, { align: "left", alt: "Naive optimiser blocked" });
  points(s, [
    { h: "P1 critical-vulnerable go first", d: "Unaccompanied minors, medical, wheelchair, blind" },
    { h: "Rules per passenger", d: "A minor flying alone stays on our flights and never leaves after 22:00" },
    { h: "Longer connection times", d: "A wheelchair user needs 80 min, so a 16:35 flight is illegal for him" },
    { h: F.naive_h, d: "An unconstrained revenue-first plan, blocked by the same guards" },
  ], { x: 8.65, y: 1.75, w: 4.1, gap: 1.22 });
  s.addNotes("Lina, 10, flying alone, gets the 18:25 to Bangkok. Mr Qureshi in a wheelchair needs 80 minutes to connect. The naive optimiser breaks these rules and is blocked.");
}

// ------------------------------------------------------------------ 9. scenario 5
{
  const s = content("Scenarios", "SCENARIO 5 · APPROVE ALL", "A human approves every network change");
  shot(s, "approve", { x: M, y: 1.6, w: W - 2 * M, h: 2.3 }, { align: "left", alt: "Controller approval banner and KPIs" });
  const items = [
    ["Staged, never executed", "Gate, hold, crew swap and retime wait in the controller queue"],
    ["Guards run again", "Approval re-checks every rule with fresh facts"],
    ["Decisions expire", "Miss the 15:15 gate window and the change is dead"],
    ["The agent can't approve", "Approval isn't one of its tools; non-human identities are refused"],
  ];
  items.forEach(([h, d], i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M + col * 6.15, y = 4.3 + row * 1.3;
    badge(s, x, y + 0.02, "✓", { color: C.accent3, txt: C.background1 });
    s.addText([{ text: h, options: { bold: true, fontSize: 17, color: C.text1, breakLine: true } },
      { text: d, options: { fontSize: 14, color: C.accent6 } }], { x: x + 0.6, y: y - 0.04, w: 5.3, h: 1.2, margin: 0, valign: "top", isTextBox: true });
  });
  s.addNotes("This is human-in-the-loop for real: the controller sees each change with its justification and deadline.");
}

// ------------------------------------------------------------------ 10. scenario 6
{
  const s = content("Scenarios", "SCENARIO 6 · SIGN-OFF & RELEASE", "Maintenance sign-off, then departure release");
  shot(s, "release", { x: M, y: 1.6, w: W - 2 * M, h: 2.95 }, { align: "left", alt: "Release banner and KPIs" });
  const steps = [
    ["Clock to 16:30", "The hydraulic inspection can now be finished", C.accent2, C.background1],
    ["B2 engineer: refused", "Wrong licence for a hydraulic system (MX-002)", C.accent4, C.background1],
    ["B1 engineer: signed", "Certificate of release to service recorded", C.accent3, C.background1],
    ["EK813 released", "Departure release approved by the controller", C.accent1, C.text1],
  ];
  steps.forEach(([h, d, col, txt], i) => {
    const x = M + i * 3.08, y = 4.8;
    badge(s, x, y, i + 1, { color: col, txt, size: 0.5, font: 16 });
    if (i < 3) s.addShape(pres.shapes.LINE, { x: x + 0.6, y: y + 0.25, w: 2.35, h: 0, line: { color: C.accent6, width: 1.25, dashType: "dash" }, objectName: `step line ${i}` });
    s.addText([{ text: h, options: { bold: true, fontSize: 17, color: C.text1, breakLine: true } },
      { text: d, options: { fontSize: 14, color: C.accent6 } }], { x, y: y + 0.65, w: 2.85, h: 1.35, margin: 0, valign: "top", isTextBox: true });
  });
  s.addNotes("The guard checks the engineer's licence category, type authorisation and timing before the certificate counts.");
}

// ------------------------------------------------------------------ 11. scenario 7
{
  const s = content("Scenarios", "SCENARIO 7 · WHAT IF…", "When the world changes, AeroTurn re-checks itself");
  shot(s, "whatif_banner", { x: M, y: 1.6, w: W - 2 * M, h: 1.7 }, { align: "left", alt: "World event banner" });
  shot(s, "whatif_queue_guard", { x: M, y: 3.55, w: 7.6, h: 3.3 }, { align: "left", alt: "Controller queue and guard board after the event" });
  points(s, [
    { h: "A diversion takes stand C31", d: "Injected live from the What if… menu" },
    { h: "C31 withdrawn by the agent", d: "GATE-001: never left for the controller to approve" },
    { h: "R205 staged instead", d: "The next legal stand, with the crew still legal" },
  ], { x: 8.65, y: 3.7, w: 4.1, gap: 1.05 });
  s.addNotes("Other events in the menu: ATC holds of 15 and 25 minutes, the standby captain reporting fatigue, and a leak found during the inspection.");
}

// ------------------------------------------------------------------ 12. edge cases
{
  const s = content("Scenarios", "EDGE CASES", "13 edge cases, 67 checks, all pass");
  shot(s, "edge_kpis", { x: M, y: 1.6, w: W - 2 * M, h: 1.0 }, { align: "left", alt: "Edge case summary: 13/13 passed" });
  const cw = (W - 2 * M - 2 * 0.3) / 3;
  [["edge_ec02", "Escalated: no legal stand after a 25-min ATC hold"], ["edge_ec07", "Resolved: gate rejected, 3-min hold saves 10"],
   ["edge_ec09", "Resolved: a leak cascades into a new retime and stand"]].forEach(([n, alt], i) => {
    shot(s, n, { x: M + i * (cw + 0.3), y: 2.85, w: cw, h: 4.0 }, { align: "center", alt });
  });
  s.addNotes("Each case runs on a throw-away copy of the scenario. 9 are resolved automatically and 4 are escalated to a human because no legal option exists. EC-07 shows the 3-minute hold on the last Kuala Lumpur flight that protects 10 passengers. The cases also found a bug in our own cost model, which we fixed.");
}

// ------------------------------------------------------------------ 12b. curveballs
{
  const s = content("Scenarios", "THE ORGANISERS' CURVEBALLS · U-4.1 TO U-4.5", "5 live tests, 34 checks, all pass");
  shot(s, "curveballs_kpis", { x: M, y: 1.55, w: W - 2 * M, h: 0.85 }, { align: "left", alt: "Curveballs summary: 5/5 live tests passed" });
  shot(s, "curveball_u41", { x: M, y: 2.55, w: 7.0, h: 4.3 }, { align: "left", alt: "U-4.1: seat conflict in batch 3, only batch 3 rolls back" });
  points(s, [
    { h: "U-4.1 Vulnerable first", d: "Own transaction, then batches of 10; batch 3 fails alone and is retried", b: "1" },
    { h: "U-4.2 \"Crew agree to extend\"", d: "Message = data; duty counters read-only; legal reserve staged", b: "2" },
    { h: "U-4.3 Forged sign-off", d: "Not on the roster, before the defect: rejected, MX control alerted", b: "3" },
    { h: "U-4.4 Bag can't make it", d: "Bag plan in the same transaction, or no commit", b: "4" },
    { h: "U-4.5 Stale approval", d: "Bound to a state hash: B7 taken, refused, re-staged", b: "5" },
  ], { x: 7.95, y: 2.65, w: 4.8, gap: 0.86, head: 15, body: 12.5 });
  s.addNotes("Open the Curveballs tab and press Run all 5. Each brief's exact live test runs on a throw-away copy of the scenario with the real tools, guards, transactions and controller workflow, then plain-language checks. The screenshot shows U-4.1: the injected seat conflict hits batch 3, only batch 3 rolls back, it is re-planned and committed; a second run shows a batch that fails twice being handed to the controller.");
}

// ------------------------------------------------------------------ 13. cost
pres.addSection({ title: "Results" });
{
  const s = content("Results", "COST & NETWORK · AED", "Cheaper, and everyone still arrives today");
  shot(s, "agent_rowB", { x: M, y: 1.6, w: 8.3, h: 3.6 }, { align: "left", alt: "Recovery flow, priority queue and compensation chart" });
  stat(s, 9.25, 1.6, 3.48, F.legacy, "legacy re-protection (+24 h)", { color: C.accent4, size: 34 });
  stat(s, 9.25, 3.0, 3.48, F.aeroturn, "AeroTurn compensation + care", { color: C.accent3, size: 34 });
  stat(s, 9.25, 4.4, 3.48, F.same_day, "arrive the same day (legacy 0)", { color: C.text1, size: 34 });
  s.addText("EU261 is fixed in euros by law and shown in dirhams at 1 EUR = 4.10 AED. Delay-cost rates are illustrative assumptions, editable in aeroturn/config.py.",
    { x: M, y: 5.95, w: W - 2 * M, h: 0.6, fontSize: 13, color: C.accent6, margin: 0, valign: "top", isTextBox: true });
  s.addNotes(F.cost_note);
}

// ------------------------------------------------------------------ 14. results
{
  const s = content("Results", "RESULTS AT A GLANCE", "Safe by construction, fast in practice");
  const cells = [
    ["45/45", "broken connections recovered"], ["10/10", "vulnerable passengers protected"], ["−62%", "compensation and care vs legacy"],
    ["0", "double bookings or orphaned bags"], ["5 + 13", "curveballs and edge cases pass"], ["103", "automated tests pass"],
  ];
  cells.forEach(([v, l], i) => {
    const col = i % 3, row = Math.floor(i / 3);
    stat(s, M + col * 4.1, 1.75 + row * 1.6, 3.85, v, l, { size: 44, color: i === 2 ? C.accent3 : C.text1 });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 5.15, w: W - 2 * M, h: 1.55, rectRadius: 0.12, fill: { color: C.text1 },
    line: { color: C.text1, width: 0 }, objectName: "tagline" });
  s.addText([
    { text: "The LLM decides what to try. Code decides what is allowed.", options: { color: C.background1, breakLine: true } },
    { text: "A human decides what changes the network.", options: { color: C.accent1 } },
  ], { x: M + 0.4, y: 5.15, w: W - 2 * M - 0.8, h: 1.55, fontSize: 24, bold: true, margin: 0, valign: "middle", isTextBox: true });
  s.addNotes("Close on the separation of concerns, then go to questions.");
}

// ------------------------------------------------------------------ 15. real world: integration
pres.addSection({ title: "Real world" });
{
  const s = content("Real world", "FROM DEMO TO A REAL OCC", "How AeroTurn plugs into an airline");
  const sys = [
    ["Reservations & check-in", "Bookings, seats, SSR codes (airline APIs, IATA NDC)"],
    ["Baggage system", "Bag tags and routing (IATA BSM / BPM messages)"],
    ["Crew management", "Rosters, duty clocks, standby list"],
    ["Maintenance (M&E)", "Tech log, MEL items, CRS sign-off"],
    ["Airport AODB & A-CDM", "Stands, in-block times, TOBT / TSAT"],
    ["Flight operations", "Movement messages (MVT), ATC delays"],
  ];
  const bx = M, bw = 4.55, bh = 0.68, by = 1.55, bg = 0.11;
  label(s, "SYSTEMS THE AIRLINE ALREADY RUNS", bx, by - 0.02, bw, { size: 12 });
  sys.forEach(([h, d], i) => {
    const y = by + 0.36 + i * (bh + bg);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: bx, y, w: bw, h: bh, rectRadius: 0.08, fill: { color: C.background2 },
      line: { color: C.background2, width: 0 }, objectName: `system ${h}` });
    s.addText([{ text: h, options: { bold: true, fontSize: 14, color: C.text1, breakLine: true } },
      { text: d, options: { fontSize: 12, color: C.accent6 } }], { x: bx + 0.2, y, w: bw - 0.3, h: bh, margin: 0, valign: "middle", isTextBox: true });
  });
  const midY = by + 0.36, midH = 6 * bh + 5 * bg;
  s.addShape(pres.shapes.LEFT_RIGHT_ARROW, { x: 5.3, y: midY + midH / 2 - 0.25, w: 0.6, h: 0.5, fill: { color: C.accent6 },
    line: { color: C.accent6, width: 0 }, objectName: "arrow systems" });
  // adapters
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.05, y: midY, w: 2.35, h: midH, rectRadius: 0.12, fill: { color: C.accent1 },
    line: { color: C.accent1, width: 0 }, objectName: "adapters" });
  s.addText([{ text: "Tool adapters", options: { bold: true, fontSize: 18, breakLine: true } },
    { text: "The only part that changes: each tool reads and writes a real system instead of SQLite", options: { fontSize: 13 } }],
    { x: 6.25, y: midY + 0.2, w: 1.95, h: midH - 0.4, color: C.text1, margin: 0, valign: "middle", isTextBox: true, paraSpaceAfter: 6 });
  s.addShape(pres.shapes.RIGHT_ARROW, { x: 8.5, y: midY + midH / 2 - 0.2, w: 0.4, h: 0.4, fill: { color: C.accent6 },
    line: { color: C.accent6, width: 0 }, objectName: "arrow core" });
  // core
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 9.0, y: midY, w: W - M - 9.0, h: midH, rectRadius: 0.12, fill: { color: C.text1 },
    line: { color: C.text1, width: 0 }, objectName: "core" });
  s.addText([
    { text: "AeroTurn core, unchanged", options: { bold: true, fontSize: 18, color: C.accent1, breakLine: true } },
    { text: "Sealed guards for crew, maintenance and passengers", options: { bullet: true, fontSize: 14, color: C.background1, breakLine: true } },
    { text: "Atomic all-or-nothing rebooking", options: { bullet: true, fontSize: 14, color: C.background1, breakLine: true } },
    { text: "Controller approval for every network change", options: { bullet: true, fontSize: 14, color: C.background1, breakLine: true } },
    { text: "Tamper-evident audit log", options: { bullet: true, fontSize: 14, color: C.background1, breakLine: true } },
    { text: "Any LLM: cloud, or an open model on the airline's own servers", options: { bullet: true, fontSize: 14, color: C.background1, breakLine: true } },
    { text: "Approved changes are written back through the same adapters", options: { fontSize: 14, italic: true, color: C.accent1 } },
  ], { x: 9.25, y: midY + 0.25, w: W - M - 9.5, h: midH - 0.5, margin: 0, valign: "top", paraSpaceAfter: 8, isTextBox: true });
  s.addNotes("Integration is an adapter job, not a rewrite. The three required services already sit behind a tool layer; in production each tool talks to the airline's reservation, baggage, crew, maintenance and airport systems using the industry message standards they already exchange. Approved changes are written back through the same systems.");
}

// ------------------------------------------------------------------ 16. real world: rollout and business case
{
  const s = content("Real world", "PATH TO PRODUCTION", "Start in shadow mode, earn trust, then automate");
  const phases = [
    ["Shadow", "Read-only feeds at one hub. AeroTurn proposes, controllers work as today. Measure agreement and minutes saved."],
    ["Advisor", "Proposals appear in the controller's console with one-click approval. Guards and audit live."],
    ["Supervised automation", "Passenger and bag rebooking runs automatically inside the guards. Network changes still need a human."],
  ];
  const px = M, pw = 6.3;
  phases.forEach(([h, d], i) => {
    const y = 1.7 + i * 1.62;
    badge(s, px, y, i + 1, { size: 0.55, font: 18, color: [C.accent6, C.accent2, C.accent3][i], txt: C.background1 });
    if (i < 2) s.addShape(pres.shapes.LINE, { x: px + 0.275, y: y + 0.6, w: 0, h: 1.0, line: { color: C.accent6, width: 1.25, dashType: "dash" }, objectName: `phase line ${i}` });
    s.addText([{ text: `Phase ${i + 1} · ${h}`, options: { bold: true, fontSize: 18, color: C.text1, breakLine: true } },
      { text: d, options: { fontSize: 14, color: C.accent6 } }], { x: px + 0.8, y: y - 0.05, w: pw - 0.8, h: 1.45, margin: 0, valign: "top", isTextBox: true });
  });
  // business case card
  const cx = 7.25, cw = W - M - cx;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx, y: 1.6, w: cw, h: 5.25, rectRadius: 0.12, fill: { color: C.background2 },
    line: { color: C.background2, width: 0 }, objectName: "business case" });
  s.addText("The business case", { x: cx + 0.35, y: 1.8, w: cw - 0.7, h: 0.45, fontSize: 20, bold: true, color: C.text1, margin: 0, isTextBox: true });
  const bc = [
    ["Value", "Lower compensation and care (−62% in our demo run), more same-day arrivals, decisions made before deadlines expire"],
    ["Model", "Annual licence per hub, priced against the compensation it saves. Pilot on one connection bank first"],
    ["Customers", "Hub airlines with tight connection banks, their ground handlers, and airports running A-CDM"],
    ["Trust", "Rules owned by the safety team and pinned, an audit trail for regulators, passenger data kept minimal"],
  ];
  bc.forEach(([h, d], i) => {
    s.addText([{ text: h, options: { bold: true, fontSize: 15, color: C.accent2, breakLine: true } },
      { text: d, options: { fontSize: 13.5, color: C.text1 } }], { x: cx + 0.35, y: 2.4 + i * 1.08, w: cw - 0.7, h: 1.0, margin: 0, valign: "top", isTextBox: true });
  });
  s.addNotes("A staged rollout lets controllers verify AeroTurn against their own decisions before it touches anything. The guards are code owned by the airline's safety and compliance team, so a rule change is a reviewed, pinned release, which is easy to audit.");
}

// ------------------------------------------------------------------ 17. thank you + datasets and sources
{
  const s = pres.addSlide({ masterName: "Dark closing", sectionTitle: "Real world" });
  s.addText("Thank you", { placeholder: "title" });
  s.addText("Questions? Try it live at aeroturn-eaglex.streamlit.app", { x: W - M - 6.0, y: 0.55, w: 6.0, h: 0.7, fontSize: 16,
    color: C.background2, margin: 0, valign: "middle", align: "right", isTextBox: true,
    hyperlink: { url: "https://aeroturn-eaglex.streamlit.app" } });
  const colW = 5.95, top = 1.65;
  const head = (t, x) => s.addText(t, { x, y: top, w: colW, h: 0.4, fontSize: 18, bold: true, color: C.accent1, margin: 0, isTextBox: true });
  head("Datasets", M);
  head("Rules and their public sources", M + colW + 0.23);
  const list = (items, x) => s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })),
    { x, y: top + 0.5, w: colW, h: 4.75, fontSize: 12, color: C.background1, margin: 0, valign: "top", paraSpaceAfter: 5, isTextBox: true });
  list([
    "Scenario database: data/aircraft_turnaround_disruption.sqlite, synthetic and byte-reproducible (seed 812)",
    "342 passengers (280 connecting, 45 broken), 356 bags, 44 flights, 33 crew, 3 maintenance items, 11 turnaround tasks",
    "17,112 seats and 15,966 bookings, including synthetic sales to other customers",
    "Readable copy: data/scenario_snapshot.json",
    "Scenario facts (EK-812, 75 min late, crew 20 min from limit, hydraulic defect): the Domain 4 problem statement",
    "Airport codes, names and coordinates: OurAirports open data (ourairports.com/data)",
    "Names, crews, timetables and the partner airline are synthetic; SSR codes are industry standard",
    "LLM: Groq openai/gpt-oss-120b, or Ollama / Gemini; offline policy when no key is set",
  ], M);
  list([
    "Crew duty limits: EASA ORO.FTL.205 Table 2 (Reg. 965/2012)",
    "Standby: CS FTL.1.225 and ORO.FTL.225; rest: ORO.FTL.235",
    "Cabin crew minimum: ORO.CC.100",
    "Engineer licences: EASA Part-66 categories (B1 for hydraulic systems)",
    "Bag-passenger matching: ICAO Annex 17, IATA Hold Baggage Reconciliation (2025)",
    "Compensation and care: EU Regulation 261/2004, Articles 3, 7 and 9",
    "Case law: CJEU Sturgeon (C-402/07), Folkerts (C-11/11), Wegener (C-537/17); Gahan v Emirates [2017] EWCA Civ 1530",
    "Delay cost: EUROCONTROL and University of Westminster reference values",
    "Exchange rate: 1 EUR = 4.10 AED (mid-market, 27 Oct 2026)",
  ], M + colW + 0.23);
  s.addText("Every assumption (connection times, hold policy, costs) is listed with links in docs/DATA_SOURCES.md in the repository.",
    { x: M, y: 6.85, w: W - 2 * M, h: 0.35, fontSize: 12, color: C.accent6, margin: 0, isTextBox: true });
  s.addNotes("All operational data is synthetic and reproducible; every rule is sourced. Judges can regenerate the data with python scripts/build_dataset.py and run the 103 tests.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  const { applyTheme } = require(process.env.APPLY_THEME);
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
