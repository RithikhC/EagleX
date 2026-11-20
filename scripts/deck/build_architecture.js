// AeroTurn architecture and workflow diagram (single 16:9 slide, exported to docs/img/architecture.png).
// node build_architecture.js <out.pptx>
const pptxgen = require("pptxgenjs");
const OUT = process.argv[2];
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: "Calibri", bodyFontFace: "Calibri" };
const s = pres.addSlide();
s.background = { color: "FFFFFF" };
const NAVY = "0B2D6B", BLUE = "1F5FC0", CYAN = "1AA3E8", LIGHT = "DBE6F7", BORDER = "C9D8F0", MUTED = "5B6B82";
const W = 13.333, M = 0.5;
const T = (t, o) => s.addText(t, { margin: 0, isTextBox: true, fontFace: "Calibri", ...o });

T("AeroTurn · architecture and workflow", { x: M, y: 0.3, w: 9, h: 0.6, fontSize: 30, bold: true, color: NAVY });
T("LLM proposes · code decides what is legal · a human approves network changes", { x: M, y: 0.88, w: 12, h: 0.4, fontSize: 16, color: MUTED });

// main pipeline
const y = 1.75, h = 1.35, gap = 0.3, n = 7, bw = (W - 2 * M - (n - 1) * gap) / n;
const flow = [
  ["Operations controller", "the user", LIGHT, NAVY],
  ["OCC dashboard", "Streamlit + Plotly", LIGHT, NAVY],
  ["AeroTurn agent", "LLM planner (Groq gpt-oss-120b)", BLUE, "FFFFFF"],
  ["Tool dispatcher", "schema check · read / propose / write · injection filter", NAVY, "FFFFFF"],
  ["13 aviation tools", "crew matcher, stands, critical path, rebooking, EU261 cost", LIGHT, NAVY],
  ["Scenario database", "SQLite · atomic BEGIN / COMMIT / ROLLBACK", LIGHT, NAVY],
  ["Output", "approval queue, rebooking, messages, AED cost, brief", "E8F5EC", "15803D"],
];
flow.forEach(([t, d, fill, ink], i) => {
  const x = M + i * (bw + gap);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: bw, h, rectRadius: 0.1, fill: { color: fill },
    line: { color: fill === LIGHT ? BORDER : fill, width: 1 } });
  T([{ text: t, options: { bold: true, fontSize: 15, color: ink, breakLine: true } },
    { text: d, options: { fontSize: 11, color: ink === "FFFFFF" ? LIGHT : MUTED } }],
    { x: x + 0.08, y, w: bw - 0.16, h, align: "center", valign: "middle" });
  if (i < n - 1) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + bw + 0.03, y: y + h / 2 - 0.13, w: gap - 0.06, h: 0.26,
    fill: { color: CYAN }, line: { color: CYAN, width: 0 } });
});
const cx = (i) => M + i * (bw + gap);

// control layer
const gy = y + h + 0.55, gh = 0.95;
function box(x, w, title, sub, fill, line) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: gy, w, h: gh, rectRadius: 0.1, fill: { color: fill }, line: { color: line, width: 1.25 } });
  T([{ text: title, options: { bold: true, fontSize: 14, color: line, breakLine: true } },
    { text: sub, options: { fontSize: 11, color: "1F2937" } }], { x: x + 0.1, y: gy, w: w - 0.2, h: gh, align: "center", valign: "middle" });
}
box(cx(1), 2 * bw + gap, "Human approval (HITL)", "gate, crew, retime, holds, release wait for a named controller; guards re-run; decisions expire", "E8F5EC", "15803D");
box(cx(3), 2 * bw + gap, "Validation: sealed guards", "25 rules (crew duty, maintenance sign-off, passenger priority), SHA-256 pinned; illegal = blocked", "FDECEC", "B91C1C");
box(cx(5), 2 * bw + gap, "Continuous re-validation", "when the world changes: withdraw what became illegal, stage the next legal option or escalate", "FFF7E6", "B45309");
[[1.5, 1], [3.5, 3], [5.5, 5]].forEach(([c]) => s.addShape(pres.shapes.LINE, { x: M + c * (bw + gap) + bw / 2 - (bw + gap) / 2 + (bw + gap) / 2, y: y + h, w: 0, h: 0.55,
  line: { color: MUTED, width: 1, dashType: "dash" } }));
const ay = gy + gh + 0.3;
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx(1), y: ay, w: 6 * bw + 5 * gap, h: 0.5, rectRadius: 0.08, fill: { color: "F3F4F6" }, line: { color: BORDER, width: 1 } });
T([{ text: "Hash-chained audit log  ", options: { bold: true, color: NAVY } }, { text: "every tool call, guard verdict, approval and transaction; editing any entry breaks the chain", options: { color: MUTED } }],
  { x: cx(1) + 0.15, y: ay, w: 6 * bw + 5 * gap - 0.3, h: 0.5, fontSize: 12.5, align: "center", valign: "middle" });

// workflow
const wy = ay + 0.8;
T("Workflow", { x: M, y: wy, w: 3, h: 0.4, fontSize: 18, bold: true, color: NAVY });
const steps = [["Trigger", "controller presses Run recovery agent, or a world event arrives"],
  ["Plan", "code gathers facts with 6 read-only tools; the LLM returns a JSON plan"],
  ["Act", "each decision runs through a guarded tool (stage a change / atomic rebooking)"],
  ["Check", "guards and DB constraints; rejected choices go back to the LLM"],
  ["Approve", "the controller approves; the engineer signs; the flight is released"]];
const sw = (W - 2 * M - 4 * 0.2) / 5;
steps.forEach(([t, d], i) => {
  const x = M + i * (sw + 0.2), yy = wy + 0.45;
  s.addShape(pres.shapes.OVAL, { x, y: yy, w: 0.42, h: 0.42, fill: { color: BLUE }, line: { color: BLUE, width: 0 } });
  T(String(i + 1), { x, y: yy, w: 0.42, h: 0.42, fontSize: 15, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
  T([{ text: t, options: { bold: true, fontSize: 14, color: NAVY, breakLine: true } }, { text: d, options: { fontSize: 11.5, color: MUTED } }],
    { x: x + 0.52, y: yy - 0.02, w: sw - 0.55, h: 0.95, valign: "top" });
});
T("github.com/RithikhC/EagleX · live demo: aeroturn-eaglex.streamlit.app", { x: M, y: 7.08, w: 9, h: 0.3, fontSize: 11, color: MUTED });
pres.writeFile({ fileName: OUT }).then(() => console.log("wrote", OUT));
