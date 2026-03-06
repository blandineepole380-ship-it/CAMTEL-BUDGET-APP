import { useState, useEffect } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from "recharts";

// ── Palette ────────────────────────────────────────────────────────────────
const C = {
  bg: "#0a0d14",
  surface: "#10141f",
  card: "#151b2e",
  border: "#1e2840",
  accent: "#3b82f6",
  accentGlow: "#3b82f620",
  green: "#22c55e",
  amber: "#f59e0b",
  red: "#ef4444",
  gray: "#6b7280",
  text: "#e2e8f0",
  muted: "#64748b",
  gold: "#f5c518",
};

// ── Seed Data ──────────────────────────────────────────────────────────────
const PROCESSES = [
  "Mobilisation des Ressources Financières",
  "Gestion des Opérations",
  "Développement RH",
  "Qualité & Conformité",
  "Innovation & Projets",
];

const MONTHS = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"];

const SEED_KPIS = [
  { id: 1, process: PROCESSES[0], name: "Taux de réalisation des Recettes", unit: "%", target: 90, frequency: "monthly", formula: "ratio" },
  { id: 2, process: PROCESSES[0], name: "Taux de recouvrement", unit: "%", target: 85, frequency: "monthly", formula: "ratio" },
  { id: 3, process: PROCESSES[0], name: "Délai moyen de facturation", unit: "jours", target: 5, frequency: "monthly", formula: "count" },
  { id: 4, process: PROCESSES[1], name: "Taux de disponibilité système", unit: "%", target: 99, frequency: "monthly", formula: "availability" },
  { id: 5, process: PROCESSES[1], name: "Nombre d'incidents critiques", unit: "", target: 0, frequency: "monthly", formula: "count" },
  { id: 6, process: PROCESSES[1], name: "Délai résolution incidents", unit: "h", target: 4, frequency: "monthly", formula: "count" },
  { id: 7, process: PROCESSES[2], name: "Taux de formation réalisée", unit: "%", target: 80, frequency: "monthly", formula: "ratio" },
  { id: 8, process: PROCESSES[2], name: "Taux de satisfaction employés", unit: "%", target: 75, frequency: "quarterly", formula: "ratio" },
  { id: 9, process: PROCESSES[3], name: "Taux de conformité audits", unit: "%", target: 95, frequency: "monthly", formula: "ratio" },
  { id: 10, process: PROCESSES[3], name: "Non-conformités résolues", unit: "%", target: 90, frequency: "monthly", formula: "ratio" },
  { id: 11, process: PROCESSES[4], name: "Projets livrés à temps", unit: "%", target: 85, frequency: "monthly", formula: "ratio" },
  { id: 12, process: PROCESSES[4], name: "Budget projets maîtrisé", unit: "%", target: 95, frequency: "monthly", formula: "ratio" },
];

function genHistory(kpi) {
  return MONTHS.map((m, i) => {
    const base = kpi.formula === "count" ? kpi.target * (0.5 + Math.random()) : kpi.target * (0.7 + Math.random() * 0.4);
    return { month: m, objective: kpi.target, actual: parseFloat(base.toFixed(1)) };
  });
}

const SEED_HISTORY = {};
SEED_KPIS.forEach(k => { SEED_HISTORY[k.id] = genHistory(k); });

function calcScore(kpi, actual, objective) {
  if (actual == null || objective == null) return null;
  if (kpi.formula === "count") {
    if (kpi.target === 0) return actual === 0 ? 100 : 0;
    return parseFloat(Math.max(0, (1 - (actual - objective) / objective) * 100).toFixed(1));
  }
  return parseFloat(((actual / objective) * 100).toFixed(1));
}

function statusColor(score, target) {
  if (score == null) return C.gray;
  if (score >= target) return C.green;
  if (score >= target * 0.85) return C.amber;
  return C.red;
}

function statusLabel(score, target) {
  if (score == null) return "Manquant";
  if (score >= target) return "Atteint";
  if (score >= target * 0.85) return "En risque";
  return "Non atteint";
}

// ── Components ─────────────────────────────────────────────────────────────
const Badge = ({ color, children }) => (
  <span style={{
    background: color + "22", color, border: `1px solid ${color}44`,
    borderRadius: 6, padding: "2px 10px", fontSize: 11, fontWeight: 700,
    letterSpacing: 0.5, textTransform: "uppercase"
  }}>{children}</span>
);

const Card = ({ children, style = {} }) => (
  <div style={{
    background: C.card, border: `1px solid ${C.border}`,
    borderRadius: 16, padding: 24, ...style
  }}>{children}</div>
);

const StatCard = ({ label, value, sub, color = C.accent }) => (
  <Card style={{ flex: 1, minWidth: 140 }}>
    <div style={{ color: C.muted, fontSize: 11, fontWeight: 600, letterSpacing: 1, textTransform: "uppercase", marginBottom: 8 }}>{label}</div>
    <div style={{ color, fontSize: 36, fontWeight: 900, lineHeight: 1 }}>{value}</div>
    {sub && <div style={{ color: C.muted, fontSize: 12, marginTop: 6 }}>{sub}</div>}
  </Card>
);

const NavBtn = ({ active, onClick, children }) => (
  <button onClick={onClick} style={{
    background: active ? C.accent : "transparent",
    color: active ? "#fff" : C.muted,
    border: "none", borderRadius: 10, padding: "10px 18px",
    cursor: "pointer", fontWeight: 600, fontSize: 13,
    transition: "all 0.2s", letterSpacing: 0.3
  }}>{children}</button>
);

// ── Main App ───────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [kpis] = useState(SEED_KPIS);
  const [history, setHistory] = useState(SEED_HISTORY);
  const [entries, setEntries] = useState({});  // { kpiId: { objective, actual, comment } }
  const [selectedMonth, setSelectedMonth] = useState(11); // Décembre = index 11
  const [selectedKpi, setSelectedKpi] = useState(null);
  const [form, setForm] = useState({ objective: "", actual: "", comment: "" });
  const [submitted, setSubmitted] = useState({});
  const [toast, setToast] = useState(null);
  const [generating, setGenerating] = useState(false);

  function showToast(msg, type = "success") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }

  function saveEntry() {
    if (!selectedKpi || form.actual === "") return;
    const key = `${selectedKpi.id}_${selectedMonth}`;
    const objective = parseFloat(form.objective) || selectedKpi.target;
    const actual = parseFloat(form.actual);
    const score = calcScore(selectedKpi, actual, objective);
    setEntries(prev => ({ ...prev, [key]: { objective, actual, score, comment: form.comment } }));
    // update history
    setHistory(prev => {
      const h = [...(prev[selectedKpi.id] || [])];
      h[selectedMonth] = { ...h[selectedMonth], actual, objective };
      return { ...prev, [selectedKpi.id]: h };
    });
    setSubmitted(prev => ({ ...prev, [key]: true }));
    showToast(`KPI enregistré avec succès`);
    setForm({ objective: "", actual: "", comment: "" });
    setSelectedKpi(null);
  }

  function getEntry(kpiId) {
    return entries[`${kpiId}_${selectedMonth}`] || null;
  }

  // Dashboard stats
  const kpiStatuses = kpis.map(k => {
    const e = getEntry(k.id);
    const score = e ? e.score : calcScore(k, history[k.id]?.[selectedMonth]?.actual, history[k.id]?.[selectedMonth]?.objective);
    return { kpi: k, score, color: statusColor(score, k.target), label: statusLabel(score, k.target) };
  });

  const achieved = kpiStatuses.filter(s => s.label === "Atteint").length;
  const atRisk = kpiStatuses.filter(s => s.label === "En risque").length;
  const notAchieved = kpiStatuses.filter(s => s.label === "Non atteint").length;
  const missing = kpiStatuses.filter(s => s.label === "Manquant").length;

  const pieData = [
    { name: "Atteint", value: achieved, color: C.green },
    { name: "En risque", value: atRisk, color: C.amber },
    { name: "Non atteint", value: notAchieved, color: C.red },
    { name: "Manquant", value: missing, color: C.gray },
  ].filter(d => d.value > 0);

  const processSummary = PROCESSES.map(p => {
    const pkpis = kpiStatuses.filter(s => s.kpi.process === p);
    const valid = pkpis.filter(s => s.score != null);
    const avg = valid.length ? valid.reduce((a, b) => a + b.score, 0) / valid.length : 0;
    return { process: p.split(" ").slice(0, 3).join(" "), avg: parseFloat(avg.toFixed(1)), full: p };
  });

  const topKpis = [...kpiStatuses].filter(s => s.score != null).sort((a, b) => b.score - a.score).slice(0, 5);
  const bottomKpis = [...kpiStatuses].filter(s => s.score != null).sort((a, b) => a.score - b.score).slice(0, 5);

  async function generatePPT() {
    setGenerating(true);
    await new Promise(r => setTimeout(r, 2500));
    setGenerating(false);
    showToast("Présentation PowerPoint générée ! (simulation)");
  }

  return (
    <div style={{
      fontFamily: "'DM Sans', 'Segoe UI', sans-serif",
      background: C.bg, color: C.text, minHeight: "100vh",
      display: "flex", flexDirection: "column"
    }}>
      {/* Header */}
      <div style={{
        background: C.surface, borderBottom: `1px solid ${C.border}`,
        padding: "0 32px", display: "flex", alignItems: "center", gap: 24,
        height: 64, position: "sticky", top: 0, zIndex: 100
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: `linear-gradient(135deg, ${C.accent}, #818cf8)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, fontWeight: 900, color: "#fff"
          }}>K</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: -0.5 }}>KPI Manager</div>
            <div style={{ fontSize: 10, color: C.muted, letterSpacing: 1 }}>TDBQ · DÉCEMBRE 2025</div>
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <select value={selectedMonth} onChange={e => setSelectedMonth(+e.target.value)}
          style={{ background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 12px", fontSize: 13, cursor: "pointer" }}>
          {MONTHS.map((m, i) => <option key={i} value={i}>{m} 2025</option>)}
        </select>
        <NavBtn active={tab === "dashboard"} onClick={() => setTab("dashboard")}>📊 Dashboard</NavBtn>
        <NavBtn active={tab === "entry"} onClick={() => setTab("entry")}>✏️ Saisie</NavBtn>
        <NavBtn active={tab === "analytics"} onClick={() => setTab("analytics")}>📈 Analytique</NavBtn>
        <NavBtn active={tab === "report"} onClick={() => setTab("report")}>🎯 Rapport</NavBtn>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", top: 80, right: 32, zIndex: 999,
          background: toast.type === "success" ? C.green : C.red,
          color: "#fff", borderRadius: 10, padding: "12px 20px",
          fontWeight: 700, fontSize: 13, boxShadow: "0 8px 32px #0008",
          animation: "slideIn 0.3s ease"
        }}>
          {toast.type === "success" ? "✓" : "✗"} {toast.msg}
        </div>
      )}

      <div style={{ flex: 1, padding: "28px 32px", maxWidth: 1400, margin: "0 auto", width: "100%" }}>

        {/* ── DASHBOARD ── */}
        {tab === "dashboard" && (
          <div>
            <div style={{ marginBottom: 28 }}>
              <h1 style={{ fontSize: 26, fontWeight: 900, margin: 0, letterSpacing: -1 }}>
                Tableau de Bord — {MONTHS[selectedMonth]} 2025
              </h1>
              <p style={{ color: C.muted, margin: "4px 0 0", fontSize: 14 }}>
                Vue d'ensemble des indicateurs de performance clés
              </p>
            </div>

            {/* Stat cards */}
            <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
              <StatCard label="KPIs Total" value={kpis.length} sub="indicateurs définis" color={C.accent} />
              <StatCard label="Atteints" value={achieved} sub={`${Math.round(achieved / kpis.length * 100)}% du total`} color={C.green} />
              <StatCard label="En Risque" value={atRisk} sub="surveillance requise" color={C.amber} />
              <StatCard label="Non Atteints" value={notAchieved} sub="actions correctives" color={C.red} />
              <StatCard label="Manquants" value={missing} sub="données à saisir" color={C.gray} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1.6fr", gap: 20, marginBottom: 20 }}>
              {/* Pie chart */}
              <Card>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16, color: C.muted, letterSpacing: 0.5 }}>STATUT GLOBAL</div>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85}
                      dataKey="value" paddingAngle={3}>
                      {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "center" }}>
                  {pieData.map(d => (
                    <div key={d.name} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                      <div style={{ width: 10, height: 10, borderRadius: 3, background: d.color }} />
                      <span style={{ color: C.muted }}>{d.name}: </span>
                      <span style={{ fontWeight: 700 }}>{d.value}</span>
                    </div>
                  ))}
                </div>
              </Card>

              {/* Process bar */}
              <Card>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16, color: C.muted, letterSpacing: 0.5 }}>PERFORMANCE PAR PROCESSUS</div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={processSummary} layout="vertical" margin={{ left: 0, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.border} horizontal={false} />
                    <XAxis type="number" domain={[0, 120]} tick={{ fill: C.muted, fontSize: 11 }} />
                    <YAxis dataKey="process" type="category" width={130} tick={{ fill: C.muted, fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8 }}
                      formatter={(v) => [`${v}%`, "Score moyen"]} />
                    <ReferenceLine x={100} stroke={C.accent} strokeDasharray="4 4" />
                    <Bar dataKey="avg" radius={[0, 6, 6, 0]}>
                      {processSummary.map((entry, i) => (
                        <Cell key={i} fill={entry.avg >= 90 ? C.green : entry.avg >= 76 ? C.amber : C.red} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            </div>

            {/* KPI Status table */}
            <Card>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16, color: C.muted, letterSpacing: 0.5 }}>
                DÉTAIL DES KPIs — {MONTHS[selectedMonth]}
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                      {["Processus", "Indicateur", "Objectif", "Réalisé", "Score", "Statut"].map(h => (
                        <th key={h} style={{ textAlign: "left", padding: "8px 12px", color: C.muted, fontWeight: 600, fontSize: 11, letterSpacing: 0.5, textTransform: "uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {kpiStatuses.map(({ kpi, score, color, label }, i) => {
                      const h = history[kpi.id]?.[selectedMonth];
                      const e = getEntry(kpi.id);
                      const obj = e?.objective ?? h?.objective ?? kpi.target;
                      const act = e?.actual ?? h?.actual ?? null;
                      return (
                        <tr key={kpi.id} style={{
                          borderBottom: `1px solid ${C.border}`,
                          background: i % 2 === 0 ? "transparent" : "#ffffff04"
                        }}>
                          <td style={{ padding: "10px 12px", color: C.muted, fontSize: 11, maxWidth: 180 }}>
                            {kpi.process.split(" ").slice(0, 3).join(" ")}
                          </td>
                          <td style={{ padding: "10px 12px", fontWeight: 600 }}>{kpi.name}</td>
                          <td style={{ padding: "10px 12px", color: C.muted }}>{obj}{kpi.unit}</td>
                          <td style={{ padding: "10px 12px", fontWeight: 700 }}>{act != null ? `${act}${kpi.unit}` : "—"}</td>
                          <td style={{ padding: "10px 12px", fontWeight: 800, color }}>
                            {score != null ? `${score}%` : "—"}
                          </td>
                          <td style={{ padding: "10px 12px" }}>
                            <Badge color={color}>{label}</Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* ── ENTRY ── */}
        {tab === "entry" && (
          <div>
            <div style={{ marginBottom: 28 }}>
              <h1 style={{ fontSize: 26, fontWeight: 900, margin: 0, letterSpacing: -1 }}>
                Saisie des Données — {MONTHS[selectedMonth]} 2025
              </h1>
              <p style={{ color: C.muted, margin: "4px 0 0", fontSize: 14 }}>
                Sélectionnez un KPI et entrez les valeurs du mois
              </p>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 24 }}>
              {/* KPI list */}
              <div>
                {PROCESSES.map(proc => {
                  const procKpis = kpis.filter(k => k.process === proc);
                  return (
                    <div key={proc} style={{ marginBottom: 20 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: C.accent, letterSpacing: 1, textTransform: "uppercase", marginBottom: 10 }}>
                        {proc}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {procKpis.map(kpi => {
                          const e = getEntry(kpi.id);
                          const h = history[kpi.id]?.[selectedMonth];
                          const act = e?.actual ?? h?.actual ?? null;
                          const score = e?.score ?? (act != null ? calcScore(kpi, act, e?.objective ?? h?.objective ?? kpi.target) : null);
                          const color = statusColor(score, kpi.target);
                          const isSelected = selectedKpi?.id === kpi.id;
                          return (
                            <div key={kpi.id} onClick={() => {
                              setSelectedKpi(kpi);
                              const existing = getEntry(kpi.id);
                              setForm({
                                objective: existing?.objective ?? kpi.target,
                                actual: existing?.actual ?? "",
                                comment: existing?.comment ?? ""
                              });
                            }}
                              style={{
                                background: isSelected ? C.accentGlow : C.card,
                                border: `1px solid ${isSelected ? C.accent : C.border}`,
                                borderRadius: 12, padding: "12px 16px", cursor: "pointer",
                                display: "flex", justifyContent: "space-between", alignItems: "center",
                                transition: "all 0.15s"
                              }}>
                              <div>
                                <div style={{ fontWeight: 600, fontSize: 13 }}>{kpi.name}</div>
                                <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>
                                  Cible: {kpi.target}{kpi.unit} · {kpi.frequency}
                                </div>
                              </div>
                              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                {act != null && <span style={{ fontWeight: 800, color, fontSize: 13 }}>{act}{kpi.unit}</span>}
                                <div style={{ width: 8, height: 8, borderRadius: 99, background: color }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Entry form */}
              <div style={{ position: "sticky", top: 88 }}>
                {selectedKpi ? (
                  <Card>
                    <div style={{ fontSize: 11, fontWeight: 700, color: C.accent, letterSpacing: 1, textTransform: "uppercase", marginBottom: 4 }}>
                      Saisie KPI
                    </div>
                    <div style={{ fontWeight: 800, fontSize: 18, marginBottom: 20, lineHeight: 1.3 }}>
                      {selectedKpi.name}
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <div>
                        <label style={{ fontSize: 11, color: C.muted, fontWeight: 600, display: "block", marginBottom: 6 }}>
                          OBJECTIF ({selectedKpi.unit || "valeur"})
                        </label>
                        <input type="number" value={form.objective}
                          onChange={e => setForm(f => ({ ...f, objective: e.target.value }))}
                          placeholder={`ex: ${selectedKpi.target}`}
                          style={{
                            width: "100%", background: C.surface, border: `1px solid ${C.border}`,
                            borderRadius: 10, padding: "12px 14px", color: C.text, fontSize: 14,
                            outline: "none", boxSizing: "border-box"
                          }} />
                      </div>
                      <div>
                        <label style={{ fontSize: 11, color: C.muted, fontWeight: 600, display: "block", marginBottom: 6 }}>
                          RÉALISÉ ({selectedKpi.unit || "valeur"}) *
                        </label>
                        <input type="number" value={form.actual}
                          onChange={e => setForm(f => ({ ...f, actual: e.target.value }))}
                          placeholder="Valeur réalisée"
                          style={{
                            width: "100%", background: C.surface, border: `1px solid ${C.border}`,
                            borderRadius: 10, padding: "12px 14px", color: C.text, fontSize: 14,
                            outline: "none", boxSizing: "border-box"
                          }} />
                      </div>

                      {/* Live score preview */}
                      {form.actual !== "" && (
                        <div style={{
                          background: C.surface, border: `1px solid ${C.border}`,
                          borderRadius: 10, padding: "14px 16px"
                        }}>
                          <div style={{ fontSize: 11, color: C.muted, marginBottom: 4 }}>SCORE CALCULÉ</div>
                          {(() => {
                            const sc = calcScore(selectedKpi, parseFloat(form.actual), parseFloat(form.objective) || selectedKpi.target);
                            const col = statusColor(sc, selectedKpi.target);
                            const lbl = statusLabel(sc, selectedKpi.target);
                            return (
                              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                <span style={{ fontSize: 32, fontWeight: 900, color: col }}>{sc}%</span>
                                <Badge color={col}>{lbl}</Badge>
                              </div>
                            );
                          })()}
                        </div>
                      )}

                      <div>
                        <label style={{ fontSize: 11, color: C.muted, fontWeight: 600, display: "block", marginBottom: 6 }}>
                          COMMENTAIRE
                        </label>
                        <textarea value={form.comment}
                          onChange={e => setForm(f => ({ ...f, comment: e.target.value }))}
                          placeholder="Explication, contexte ou action corrective..."
                          rows={3}
                          style={{
                            width: "100%", background: C.surface, border: `1px solid ${C.border}`,
                            borderRadius: 10, padding: "12px 14px", color: C.text, fontSize: 13,
                            outline: "none", resize: "vertical", boxSizing: "border-box",
                            fontFamily: "inherit"
                          }} />
                      </div>

                      <div style={{ display: "flex", gap: 10 }}>
                        <button onClick={saveEntry} style={{
                          flex: 1, background: C.accent, color: "#fff", border: "none",
                          borderRadius: 10, padding: "14px", fontWeight: 800, fontSize: 14,
                          cursor: "pointer", letterSpacing: 0.5
                        }}>
                          ✓ Enregistrer
                        </button>
                        <button onClick={() => { setSelectedKpi(null); setForm({ objective: "", actual: "", comment: "" }); }}
                          style={{
                            background: C.surface, color: C.muted, border: `1px solid ${C.border}`,
                            borderRadius: 10, padding: "14px 18px", cursor: "pointer", fontSize: 14
                          }}>
                          ✕
                        </button>
                      </div>
                    </div>
                  </Card>
                ) : (
                  <Card style={{ textAlign: "center", padding: 48 }}>
                    <div style={{ fontSize: 48, marginBottom: 16 }}>←</div>
                    <div style={{ fontWeight: 700, color: C.muted, fontSize: 14 }}>
                      Sélectionnez un KPI à saisir
                    </div>
                  </Card>
                )}

                {/* Progress summary */}
                <Card style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.muted, letterSpacing: 1, marginBottom: 12 }}>AVANCEMENT SAISIE</div>
                  {(() => {
                    const done = kpis.filter(k => {
                      const e = getEntry(k.id);
                      const h = history[k.id]?.[selectedMonth];
                      return (e?.actual != null) || (h?.actual != null);
                    }).length;
                    const pct = Math.round(done / kpis.length * 100);
                    return (
                      <>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                          <span style={{ fontSize: 13 }}>{done}/{kpis.length} KPIs saisis</span>
                          <span style={{ fontWeight: 800, color: C.accent }}>{pct}%</span>
                        </div>
                        <div style={{ background: C.border, borderRadius: 99, height: 6 }}>
                          <div style={{ width: `${pct}%`, background: C.accent, borderRadius: 99, height: 6, transition: "width 0.5s" }} />
                        </div>
                      </>
                    );
                  })()}
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* ── ANALYTICS ── */}
        {tab === "analytics" && (
          <div>
            <div style={{ marginBottom: 28 }}>
              <h1 style={{ fontSize: 26, fontWeight: 900, margin: 0, letterSpacing: -1 }}>Analytique & Tendances</h1>
              <p style={{ color: C.muted, margin: "4px 0 0", fontSize: 14 }}>Évolution mensuelle des KPIs Jan–Déc 2025</p>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
              {/* Top performers */}
              <Card>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16, color: C.green, letterSpacing: 0.5 }}>🏆 TOP 5 — MEILLEURS KPIs</div>
                {topKpis.map((s, i) => (
                  <div key={s.kpi.id} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                    <div style={{ width: 24, height: 24, borderRadius: 6, background: C.green + "22", color: C.green, fontSize: 11, fontWeight: 900, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {i + 1}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>{s.kpi.name}</div>
                      <div style={{ fontSize: 11, color: C.muted }}>{s.kpi.process.split(" ")[0]}</div>
                    </div>
                    <span style={{ fontWeight: 900, color: C.green, fontSize: 14 }}>{s.score}%</span>
                  </div>
                ))}
              </Card>

              {/* Bottom performers */}
              <Card>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16, color: C.red, letterSpacing: 0.5 }}>⚠️ TOP 5 — À AMÉLIORER</div>
                {bottomKpis.map((s, i) => (
                  <div key={s.kpi.id} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                    <div style={{ width: 24, height: 24, borderRadius: 6, background: C.red + "22", color: C.red, fontSize: 11, fontWeight: 900, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {i + 1}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>{s.kpi.name}</div>
                      <div style={{ fontSize: 11, color: C.muted }}>{s.kpi.process.split(" ")[0]}</div>
                    </div>
                    <span style={{ fontWeight: 900, color: C.red, fontSize: 14 }}>{s.score}%</span>
                  </div>
                ))}
              </Card>
            </div>

            {/* Trend charts per KPI */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              {kpis.slice(0, 8).map(kpi => {
                const data = (history[kpi.id] || []).map((d, i) => ({
                  month: MONTHS[i],
                  actual: d.actual,
                  target: kpi.target
                }));
                return (
                  <Card key={kpi.id} style={{ padding: "20px 20px 12px" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 12, lineHeight: 1.3 }}>{kpi.name}</div>
                    <ResponsiveContainer width="100%" height={120}>
                      <LineChart data={data} margin={{ top: 0, right: 10, bottom: 0, left: -20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                        <XAxis dataKey="month" tick={{ fill: C.muted, fontSize: 9 }} />
                        <YAxis tick={{ fill: C.muted, fontSize: 9 }} />
                        <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 11 }} />
                        <ReferenceLine y={kpi.target} stroke={C.accent} strokeDasharray="4 4" strokeWidth={1.5} />
                        <Line type="monotone" dataKey="actual" stroke={C.green} dot={false} strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                    <div style={{ fontSize: 10, color: C.muted, marginTop: 6, display: "flex", gap: 16 }}>
                      <span>— Réalisé</span>
                      <span style={{ color: C.accent }}>- - Cible ({kpi.target}{kpi.unit})</span>
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>
        )}

        {/* ── REPORT ── */}
        {tab === "report" && (
          <div>
            <div style={{ marginBottom: 28 }}>
              <h1 style={{ fontSize: 26, fontWeight: 900, margin: 0, letterSpacing: -1 }}>Centre de Rapports</h1>
              <p style={{ color: C.muted, margin: "4px 0 0", fontSize: 14 }}>Générez votre présentation PowerPoint mensuelle en un clic</p>
            </div>

            {/* PPT Preview */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
              {[
                { slide: 1, title: "Page de Titre", icon: "🎯", desc: "Revue mensuelle KPI · Décembre 2025 · TDBQ" },
                { slide: 2, title: "Vue Exécutive", icon: "📊", desc: `${kpis.length} KPIs · ${achieved} atteints · ${notAchieved} non atteints · ${missing} manquants` },
                { slide: 3, title: "Statut Global", icon: "🍩", desc: "Graphique donut : Atteint / En risque / Non atteint / Manquant" },
                { slide: 4, title: "Performance Processus", icon: "📉", desc: "Classement des processus par score moyen" },
                { slide: 5, title: "Top Succès", icon: "🏆", desc: `5 meilleurs KPIs — Top: ${topKpis[0]?.kpi.name}` },
                { slide: 6, title: "Points d'Alerte", icon: "⚠️", desc: `5 KPIs critiques — ${bottomKpis[0]?.kpi.name}` },
                { slide: "7+", title: "Détail par Processus", icon: "📋", desc: `${PROCESSES.length} slides — tableaux + graphiques tendance` },
                { slide: "Fin", title: "Plan d'Actions", icon: "✅", desc: "Actions correctives · Responsables · Échéances" },
              ].map(s => (
                <Card key={s.slide} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: 10, background: C.accentGlow,
                    border: `1px solid ${C.accent}44`, display: "flex", alignItems: "center",
                    justifyContent: "center", fontSize: 22, flexShrink: 0
                  }}>{s.icon}</div>
                  <div>
                    <div style={{ fontSize: 10, color: C.muted, fontWeight: 600, letterSpacing: 1 }}>SLIDE {s.slide}</div>
                    <div style={{ fontWeight: 800, fontSize: 15, marginTop: 2 }}>{s.title}</div>
                    <div style={{ fontSize: 12, color: C.muted, marginTop: 4, lineHeight: 1.5 }}>{s.desc}</div>
                  </div>
                </Card>
              ))}
            </div>

            {/* Generate buttons */}
            <Card style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 800, fontSize: 16 }}>Prêt à générer votre rapport</div>
                <div style={{ color: C.muted, fontSize: 13, marginTop: 4 }}>
                  Le système va créer automatiquement une présentation complète avec tous les graphiques, tableaux et commentaires.
                </div>
              </div>
              <button onClick={generatePPT} disabled={generating}
                style={{
                  background: generating ? C.muted : `linear-gradient(135deg, ${C.accent}, #818cf8)`,
                  color: "#fff", border: "none", borderRadius: 12,
                  padding: "16px 32px", fontWeight: 800, fontSize: 15,
                  cursor: generating ? "wait" : "pointer", letterSpacing: 0.5,
                  boxShadow: generating ? "none" : `0 8px 32px ${C.accent}44`,
                  transition: "all 0.3s", minWidth: 220
                }}>
                {generating ? "⏳ Génération en cours..." : "🎯 Générer PowerPoint"}
              </button>
              <button style={{
                background: C.surface, color: C.text, border: `1px solid ${C.border}`,
                borderRadius: 12, padding: "16px 24px", fontWeight: 700, fontSize: 14,
                cursor: "pointer"
              }}>
                📊 Exporter Excel
              </button>
              <button style={{
                background: C.surface, color: C.text, border: `1px solid ${C.border}`,
                borderRadius: 12, padding: "16px 24px", fontWeight: 700, fontSize: 14,
                cursor: "pointer"
              }}>
                📄 Exporter PDF
              </button>
            </Card>

            {/* Summary stats for report */}
            <div style={{ marginTop: 24 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.muted, letterSpacing: 1, marginBottom: 16, textTransform: "uppercase" }}>
                Aperçu du Contenu du Rapport
              </div>
              <Card>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={processSummary}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                    <XAxis dataKey="process" tick={{ fill: C.muted, fontSize: 10 }} />
                    <YAxis tick={{ fill: C.muted, fontSize: 10 }} domain={[0, 120]} />
                    <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8 }}
                      formatter={(v) => [`${v}%`, "Score moyen"]} />
                    <ReferenceLine y={100} stroke={C.accent} strokeDasharray="4 4" label={{ value: "Cible", fill: C.accent, fontSize: 11 }} />
                    <Bar dataKey="avg" radius={[6, 6, 0, 0]}>
                      {processSummary.map((entry, i) => (
                        <Cell key={i} fill={entry.avg >= 90 ? C.green : entry.avg >= 76 ? C.amber : C.red} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700;800;900&display=swap');
        * { box-sizing: border-box; }
        input:focus, textarea:focus { border-color: ${C.accent} !important; box-shadow: 0 0 0 3px ${C.accentGlow}; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: ${C.bg}; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 99px; }
        @keyframes slideIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
      `}</style>
    </div>
  );
}
