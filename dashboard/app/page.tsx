"use client";
import { useEffect, useRef, useState } from "react";

type Ev = { actor: string; kind: string; authority: string; room?: string; payload: any };
type Result = {
  verdict: string; confidence: number; decision: string; rationale: string;
  evidence: { agent: string; claim: string; source: string; verified: boolean | null; confidence: number | null; supports: string }[];
  rejected_claims: string[]; consortium_confirmation: string | null; report: string;
};
type AccountResult = {
  account: string; alert_type: string; transactions: number;
  result: Result & { case_id: string; qa_score: number | null; qa_findings: string[] };
  case?: { uid: string; priority: number; sla_due: string | null; status: string };
};
type Plan = { filename: string; accounts: { account: string; alert_type: string; transactions: number }[] };
type CaseRow = {
  uid: string; created_at: string; source_file: string; account: string; alert_type: string;
  txn_count: number; exposure: number; verdict: string; confidence: number; status: string;
  priority: number; sla_due: string | null; qa_score: number | null; counterparties: string[];
  officer_decision: string | null;
};
type CaseDetail = CaseRow & { result: Result & { qa_score: number | null; qa_findings: string[] } };
type Ops = {
  cases_total: number; auto_cleared: number; pending_review: number;
  confirmed_suspicious: number; dismissed_false_positive: number; overdue_reviews: number;
  auto_clear_rate: number; avg_qa_score: number | null; analyst_hours_saved: number;
  workload_assumptions: { manual_minutes_per_alert: number; review_minutes_with_aegis: number };
  policy: { clear_confidence: number; escalate_suspicion_floor: number };
  recent_feedback: { ts: string; case_uid: string; officer_decision: string; agreed: boolean;
    clear_confidence_before: number; clear_confidence_after: number }[];
};
type Briefing = {
  cases_reviewed: number; cases_flagged: number; headline: string;
  emerging_typologies: { typology: string; cases: number }[];
  repeat_subjects: { account: string; case_uids: string[] }[];
  cross_case_links: { counterparty: string; links_cases: string[]; also_under_investigation: boolean }[];
  shareable_patterns: { typology: string; cases: number; scope: string }[];
};

// Optional production auth: if an API key was stored (localStorage "aegis_api_key"),
// attach it; otherwise requests go out plain (the default open mode).
function apiHeaders(): Record<string, string> {
  const k = typeof window !== "undefined" ? localStorage.getItem("aegis_api_key") : null;
  return k ? { "X-API-Key": k } : {};
}

function hoursLeft(iso: string | null): number | null {
  if (!iso) return null;
  return (new Date(iso).getTime() - Date.now()) / 3_600_000;
}
type EvalR = {
  dataset?: string;
  baseline: { false_positive_rate: number; recall_catch_rate: number; false_positives: number };
  aegis: { false_positive_rate: number; recall_catch_rate: number; false_positives: number };
  false_positive_reduction_pct: number;
};

const KIND_TAG: Record<string, string> = {
  joined: "👥", evidence: "🔎", challenge: "🥊", verify: "✅", rejected: "⛔",
  consortium: "🤝", verdict: "⚖️", gate: "🧑‍⚖️", clear: "🟢", plan: "📋", room_opened: "📂",
};

type Tab = "analyze" | "command" | "benchmark";

export default function Home() {
  const [tab, setTab] = useState<Tab>("analyze");

  // ── command center: queue + KPIs + intelligence (one human, whole desk) ──
  const [ops, setOps] = useState<Ops | null>(null);
  const [queue, setQueue] = useState<CaseRow[]>([]);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [openCase, setOpenCase] = useState<CaseDetail | null>(null);
  const [deciding, setDeciding] = useState("");
  const [lastAction, setLastAction] = useState("");
  const [cmdErr, setCmdErr] = useState("");

  async function loadCommand() {
    setCmdErr("");
    try {
      const [o, q, b] = await Promise.all([
        fetch("/api/operations").then((r) => r.json()),
        fetch("/api/cases?status=pending_review").then((r) => r.json()),
        fetch("/api/intel/briefing").then((r) => r.json()),
      ]);
      setOps(o); setQueue(q.cases); setBriefing(b);
    } catch (e: any) {
      setCmdErr(String(e.message || e));
    }
  }

  useEffect(() => {
    if (tab === "command") loadCommand();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  async function viewCase(uid: string) {
    if (openCase?.uid === uid) { setOpenCase(null); return; }
    const r = await fetch(`/api/cases/${encodeURIComponent(uid)}`);
    if (r.ok) setOpenCase(await r.json());
  }

  async function decideCase(uid: string, decision: "confirm" | "dismiss") {
    setDeciding(uid); setCmdErr("");
    try {
      const r = await fetch(`/api/cases/${encodeURIComponent(uid)}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...apiHeaders() },
        body: JSON.stringify({ decision }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || `decision failed (${r.status})`);
      setLastAction(
        `${uid}: ${decision === "confirm" ? "confirmed suspicious" : "dismissed as false positive"}` +
        ` — auto-clear bar ${body.clear_confidence_before} → ${body.clear_confidence_after}` +
        ` (the system just learned from you)`);
      if (openCase?.uid === uid) setOpenCase(null);
      await loadCommand();
    } catch (e: any) {
      setCmdErr(String(e.message || e));
    } finally {
      setDeciding("");
    }
  }

  // ── analyze (the product): upload -> live investigation -> verdicts ──────
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadFocus, setUploadFocus] = useState("");
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [results, setResults] = useState<AccountResult[]>([]);
  const [doneN, setDoneN] = useState<number | null>(null);
  const [uploadErr, setUploadErr] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [events]);

  async function runUpload() {
    if (!uploadFile || busy) return;
    setBusy(true); setUploadErr(""); setPlan(null); setEvents([]); setResults([]); setDoneN(null);
    const fd = new FormData();
    fd.append("file", uploadFile);
    const qs = uploadFocus.trim() ? `?focus=${encodeURIComponent(uploadFocus.trim())}` : "";
    try {
      const r = await fetch(`/api/analyze/stream${qs}`, { method: "POST", body: fd, headers: apiHeaders() });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `analysis failed (${r.status})`);
      }
      if (!r.body) throw new Error("streaming not supported by this browser");
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const item = JSON.parse(line);
          if (item.kind === "plan") setPlan(item.payload);
          else if (item.kind === "event") setEvents((p) => [...p, item.payload]);
          else if (item.kind === "account_result") setResults((p) => [...p, item.payload]);
          else if (item.kind === "done") setDoneN(item.payload.accounts_analyzed);
        }
      }
    } catch (e: any) {
      setUploadErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  function downloadReport() {
    if (!results.length || !uploadFile) return;
    const lines: string[] = [
      `AEGIS INVESTIGATION REPORT`,
      `File: ${uploadFile.name}`,
      `Generated: ${new Date().toISOString()}`,
      `Accounts investigated: ${results.length}`,
      ``,
    ];
    for (const r of results) {
      lines.push(`${"=".repeat(60)}`);
      lines.push(`ACCOUNT ${r.account} — ${r.result.verdict.toUpperCase()} (confidence ${r.result.confidence})`);
      lines.push(`Alert type: ${r.alert_type} · ${r.transactions} transactions reviewed`);
      lines.push(`Decision: ${r.result.decision === "auto_clear" ? "auto-cleared" : "escalated for human review"}`);
      lines.push(`Rationale: ${r.result.rationale}`);
      const v = r.result.evidence.filter((e) => e.verified);
      if (v.length) {
        lines.push(``, `Verified evidence:`);
        v.forEach((e) => lines.push(`  • ${e.claim}  [${e.source}]`));
      }
      if (r.result.rejected_claims.length) {
        lines.push(``, `Claims rejected by the Verifier:`);
        r.result.rejected_claims.forEach((c) => lines.push(`  ✗ ${c}`));
      }
      lines.push(``);
    }
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `aegis-report-${uploadFile.name.replace(/\.[^.]+$/, "")}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ── benchmark: scored against external labels (IBM AML, public) ─────────
  const [evalR, setEvalR] = useState<EvalR | null>(null);
  const [evalBusy, setEvalBusy] = useState(false);
  const [evalErr, setEvalErr] = useState("");

  function runEvalPublic() {
    setEvalBusy(true); setEvalErr("");
    fetch("/api/eval/public?limit=200")
      .then(async (r) => {
        const body = await r.json();
        if (body.error) throw new Error(body.error);
        setEvalR(body);
      })
      .catch((e) => setEvalErr(String(e.message || e)))
      .finally(() => setEvalBusy(false));
  }

  const suspiciousN = results.filter((r) => r.result.verdict === "suspicious").length;
  const reviewN = results.filter((r) => r.result.verdict === "uncertain").length;
  const clearedN = results.filter((r) => r.result.verdict === "benign").length;
  const investigating = busy && plan ? plan.accounts[results.length]?.account : null;

  return (
    <div className="wrap">
      <header className="topbar">
        <div className="brand">
          <span className="logo">⬡</span>
          <div>
            <h1>AEGIS</h1>
            <div className="tagline">Financial-Crime Investigation Mesh</div>
          </div>
        </div>
        <span className="badge">12 governed agents · evidence-verified verdicts · one-human ops</span>
      </header>

      <nav className="tabs">
        <button className={`tab ${tab === "analyze" ? "active" : ""}`} onClick={() => setTab("analyze")}>
          Analyze
        </button>
        <button className={`tab ${tab === "command" ? "active" : ""}`} onClick={() => setTab("command")}>
          Command Center
        </button>
        <button className={`tab ${tab === "benchmark" ? "active" : ""}`} onClick={() => setTab("benchmark")}>
          Benchmark
        </button>
      </nav>

      {/* ════════ ANALYZE ════════ */}
      {tab === "analyze" && (
        <>
          <div className="panel hero">
            <h2>Upload a transaction file</h2>
            <div
              className={`dropzone ${dragOver ? "over" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault(); setDragOver(false);
                const f = e.dataTransfer.files?.[0];
                if (f) setUploadFile(f);
              }}
              onClick={() => document.getElementById("file-input")?.click()}
            >
              <input id="file-input" type="file" hidden
                accept=".csv,.xlsx,.xls,.json,.pdf,text/csv"
                onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)} />
              <div className="drop-icon">📄</div>
              {uploadFile
                ? <div className="drop-name">{uploadFile.name} · {(uploadFile.size / 1024).toFixed(0)} KB</div>
                : <div>Drop a file here or click to browse</div>}
              <div className="formats">CSV · Excel · JSON · PDF (text-based statements)</div>
            </div>
            <div className="controls" style={{ marginTop: 14, marginBottom: 0 }}>
              <input className="input" type="text" placeholder="Focus on one account (optional)"
                value={uploadFocus} onChange={(e) => setUploadFocus(e.target.value)} />
              <button className="primary" onClick={runUpload} disabled={!uploadFile || busy}>
                {busy ? "Investigating…" : "Run investigation"}
              </button>
              {results.length > 0 && !busy && <button className="ghost" onClick={downloadReport}>⬇ Download report</button>}
            </div>
            <div className="finehint">
              Needs columns for source account, destination account and amount — common header
              names (from/to, nameOrig/nameDest, sender/beneficiary…) are detected automatically.
              Files are analyzed in memory and never stored.
            </div>
            {uploadErr && <div className="error">⚠ {uploadErr}</div>}
          </div>

          {plan && (
            <>
              <div className="summary">
                <div className="chip">{plan.filename}</div>
                <div className="chip">{plan.accounts.length} account{plan.accounts.length === 1 ? "" : "s"} selected by risk triage</div>
                {doneN !== null && (
                  <>
                    <div className="chip red">{suspiciousN} suspicious</div>
                    {reviewN > 0 && <div className="chip amber">{reviewN} needs human review</div>}
                    <div className="chip green">{clearedN} cleared</div>
                  </>
                )}
              </div>

              <div className="grid">
                <div className="panel">
                  <h2>Live investigation (governed audit stream)
                    {investigating && <span className="src"> · investigating {investigating}</span>}
                  </h2>
                  <div className="feed" ref={feedRef}>
                    {events.length === 0 && <div className="sub">Agent actions appear here as they happen.</div>}
                    {events.map((e, i) => {
                      const isReject = e.kind === "rejected" || (e.kind === "verify" && e.payload?.verified === false);
                      const tag = e.kind === "verify" ? (e.payload?.verified ? "✅" : "❌") : (KIND_TAG[e.kind] ?? "•");
                      const text = e.payload?.claim || e.payload?.note || e.payload?.argument ||
                        e.payload?.verdict || e.payload?.role || e.kind;
                      return (
                        <div className={`ev ${isReject ? "reject" : ""}`} key={i}>
                          <span>{tag}</span>
                          <span className="who">{e.actor}</span>
                          <span>{typeof text === "string" ? text : JSON.stringify(text)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="panel">
                  <h2>Verdicts & evidence ({results.length}/{plan.accounts.length})</h2>
                  {results.length === 0 && <div className="sub">Each account&apos;s verdict lands here once its investigation completes.</div>}
                  {results.map((r, i) => {
                    const v = r.result.evidence.filter((e) => e.verified);
                    return (
                      <div key={i} style={{ marginBottom: 14 }}>
                        <div className={`verdict-box ${r.result.verdict}`}>
                          <div className="verdict-big">{r.result.verdict}</div>
                          <div>account <b>{r.account}</b> · {r.transactions} txns reviewed · confidence {r.result.confidence}</div>
                          <div className="decision">
                            {r.result.decision === "auto_clear" ? "🟢 Auto-cleared" : "🧑‍⚖️ Escalated for human review"}
                            <br />{r.result.rationale}
                          </div>
                          {r.case && (
                            <div className="filed">
                              📁 Filed as <b>{r.case.uid}</b> · priority {r.case.priority}
                              {r.case.status === "pending_review" && " · waiting in the Command Center queue"}
                            </div>
                          )}
                        </div>
                        {v.map((e, j) => (
                          <div className="evi" key={j}>{e.claim}<br />
                            <span className="src">{e.agent} · {e.source} · conf {e.confidence}</span></div>
                        ))}
                        {r.result.rejected_claims.length > 0 && (
                          <div className="evi rej">Verifier rejected {r.result.rejected_claims.length} uncited claim{r.result.rejected_claims.length === 1 ? "" : "s"}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* ════════ COMMAND CENTER ════════ */}
      {tab === "command" && (
        <>
          {cmdErr && <div className="error">⚠ {cmdErr}</div>}
          {lastAction && <div className="toast">🧠 {lastAction}</div>}

          {ops && (
            <div className="metrics kpis">
              <div className="metric"><div className="big">{ops.cases_total}</div><div className="lbl">cases on file</div></div>
              <div className="metric"><div className="big" style={{ color: "var(--green)" }}>{(ops.auto_clear_rate * 100).toFixed(0)}%</div><div className="lbl">auto-cleared by the agents</div></div>
              <div className="metric"><div className="big" style={{ color: ops.overdue_reviews ? "var(--red)" : "var(--amber)" }}>{ops.pending_review}</div><div className="lbl">awaiting your decision{ops.overdue_reviews ? ` · ${ops.overdue_reviews} overdue` : ""}</div></div>
              <div className="metric"><div className="big" style={{ color: "var(--blue)" }}>{ops.analyst_hours_saved}h</div><div className="lbl">analyst-hours saved*</div></div>
              <div className="metric"><div className="big">{ops.avg_qa_score !== null ? (ops.avg_qa_score * 100).toFixed(0) + "%" : "—"}</div><div className="lbl">avg QA score</div></div>
              <div className="metric"><div className="big" style={{ color: "var(--accent)" }}>{ops.policy.clear_confidence}</div><div className="lbl">auto-clear bar (learned)</div></div>
            </div>
          )}
          {ops && (
            <div className="finehint" style={{ marginTop: 6 }}>
              *assumes {ops.workload_assumptions.manual_minutes_per_alert} min of manual L1+L2 work per alert vs{" "}
              {ops.workload_assumptions.review_minutes_with_aegis} min to review an AEGIS-prepared case — the
              assumption is part of the API payload, not hidden.
            </div>
          )}

          {ops && ops.cases_total === 0 && (
            <div className="panel" style={{ marginTop: 14 }}>
              <h2>The casebook is empty</h2>
              <div className="sub" style={{ margin: 0 }}>
                Run an investigation on the Analyze tab (or via the CLI) — every verdict files itself
                here as a case: auto-cleared ones for the record, escalated ones into your review queue.
                Nothing in this view is canned.
              </div>
            </div>
          )}

          {ops && ops.cases_total > 0 && (
            <div className="grid" style={{ marginTop: 14 }}>
              <div className="panel">
                <h2>Review queue — sorted by priority, SLA clocks running</h2>
                {queue.length === 0 && <div className="sub" style={{ margin: 0 }}>Queue clear. The agents are handling everything that doesn&apos;t need you.</div>}
                {queue.map((c) => {
                  const left = hoursLeft(c.sla_due);
                  const open = openCase?.uid === c.uid;
                  return (
                    <div className="qcase" key={c.uid}>
                      <div className="qrow">
                        <span className={`prio ${c.priority >= 75 ? "hi" : c.priority >= 50 ? "mid" : "lo"}`}>P{c.priority}</span>
                        <div className="qmain">
                          <div><b>{c.account}</b> · {c.verdict} (conf {c.confidence}) · {c.alert_type}</div>
                          <div className="src">
                            {c.uid} · ${c.exposure.toLocaleString()} exposure · {c.txn_count} txns · from {c.source_file || "CLI"}
                            {left !== null && (
                              <span style={{ color: left < 0 ? "var(--red)" : left < 24 ? "var(--amber)" : undefined }}>
                                {" "}· {left < 0 ? `OVERDUE ${Math.abs(left).toFixed(0)}h` : `due in ${left.toFixed(0)}h`}
                              </span>
                            )}
                            {c.qa_score !== null && c.qa_score < 1 && <span style={{ color: "var(--amber)" }}> · QA {(c.qa_score * 100).toFixed(0)}%</span>}
                          </div>
                        </div>
                        <button className="ghost" onClick={() => viewCase(c.uid)}>{open ? "Hide" : "Evidence"}</button>
                        <button className="confirm" disabled={deciding === c.uid} onClick={() => decideCase(c.uid, "confirm")}>Confirm</button>
                        <button className="dismiss" disabled={deciding === c.uid} onClick={() => decideCase(c.uid, "dismiss")}>Dismiss</button>
                      </div>
                      {open && openCase && (
                        <div className="qdetail">
                          {openCase.result.evidence.filter((e) => e.verified).map((e, j) => (
                            <div className="evi" key={j}>{e.claim}<br /><span className="src">{e.agent} · {e.source} · conf {e.confidence}</span></div>
                          ))}
                          {openCase.result.rejected_claims.length > 0 && (
                            <div className="evi rej">Verifier rejected {openCase.result.rejected_claims.length} claim(s)</div>
                          )}
                          {openCase.result.qa_findings.length > 0 && (
                            <div className="evi" style={{ borderLeftColor: "var(--amber)" }}>
                              QA findings: {openCase.result.qa_findings.join("; ")}
                            </div>
                          )}
                          {openCase.result.report && <pre className="sar">{openCase.result.report}</pre>}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <div>
                <div className="panel" style={{ marginBottom: 16 }}>
                  <h2>Strategic intelligence — across the whole casebook</h2>
                  {briefing && (
                    <>
                      <div className="sub" style={{ marginBottom: 10 }}>{briefing.headline}</div>
                      {briefing.emerging_typologies.length > 0 && (
                        <div className="summary" style={{ marginTop: 0 }}>
                          {briefing.emerging_typologies.map((t) => (
                            <div className="chip amber" key={t.typology}>{t.typology} ×{t.cases}</div>
                          ))}
                        </div>
                      )}
                      {briefing.cross_case_links.map((l, i) => (
                        <div className="evi" key={i} style={{ borderLeftColor: "var(--accent)" }}>
                          <b>{l.counterparty}</b> bridges {l.links_cases.length} separate investigations
                          {l.also_under_investigation && " — and is itself under investigation"}
                          <br /><span className="src">{l.links_cases.join(" · ")}</span>
                        </div>
                      ))}
                      {briefing.repeat_subjects.map((s, i) => (
                        <div className="evi" key={`r${i}`} style={{ borderLeftColor: "var(--amber)" }}>
                          repeat subject <b>{s.account}</b> — {s.case_uids.length} cases
                        </div>
                      ))}
                      {briefing.shareable_patterns.length > 0 && (
                        <div className="consortium">
                          <b>Consortium-ready descriptors</b> (this is ALL that would cross to peer banks):
                          {briefing.shareable_patterns.map((p, i) => (
                            <div className="mono" key={i}>{JSON.stringify(p)}</div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>

                <div className="panel">
                  <h2>Learning loop — every decision retunes the autonomy policy</h2>
                  {ops.recent_feedback.length === 0 && (
                    <div className="sub" style={{ margin: 0 }}>No human decisions yet. Decide a queued case and watch the auto-clear bar move.</div>
                  )}
                  {ops.recent_feedback.map((f, i) => (
                    <div className="evi" key={i} style={{ borderLeftColor: f.agreed ? "var(--green)" : "var(--amber)" }}>
                      {f.case_uid}: officer said <b>{f.officer_decision}</b> ({f.agreed ? "agents agreed" : "agents corrected"})
                      <br /><span className="src">auto-clear bar {f.clear_confidence_before} → {f.clear_confidence_after}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* ════════ BENCHMARK ════════ */}
      {tab === "benchmark" && (
        <div className="panel">
          <h2>Measured accuracy — single-pass baseline vs AEGIS
            {evalR && <span className="src"> · IBM AML public benchmark (external labels)</span>}
          </h2>
          <div className="controls">
            <button className="primary" onClick={runEvalPublic} disabled={evalBusy}>
              {evalBusy ? "Scoring…" : "Score on IBM AML benchmark"}
            </button>
          </div>
          {evalErr && <div className="error">⚠ {evalErr}</div>}
          {!evalR && <div className="sub">Scores AEGIS on a slice of the public IBM
            Anti-Money-Laundering dataset whose labels were authored externally —
            measuring how many false alerts AEGIS clears while keeping the catch rate.
            Nothing here is self-graded.</div>}
          {evalR && (
            <>
              <div className="metrics">
                <div className="metric">
                  <div className="big" style={{ color: "var(--green)" }}>{evalR.false_positive_reduction_pct}%</div>
                  <div className="lbl">false-positive reduction</div>
                </div>
                <div className="metric">
                  <div className="big">{(evalR.aegis.recall_catch_rate * 100).toFixed(0)}%</div>
                  <div className="lbl">true-positive catch rate (AEGIS)</div>
                </div>
              </div>
              <div style={{ marginTop: 14 }}>
                <div className="src">Baseline false-positive rate: {(evalR.baseline.false_positive_rate * 100).toFixed(0)}%</div>
                <div className="bar"><span style={{ width: `${evalR.baseline.false_positive_rate * 100}%` }} /></div>
                <div className="src" style={{ marginTop: 8 }}>AEGIS false-positive rate: {(evalR.aegis.false_positive_rate * 100).toFixed(0)}%</div>
                <div className="bar aegis"><span style={{ width: `${evalR.aegis.false_positive_rate * 100}%` }} /></div>
              </div>
            </>
          )}
        </div>
      )}

      <p className="footer">
        Coordinated through Band · CrewAI specialists + LangGraph verification ·
        AI/ML API + Featherless · no real PII.
      </p>
    </div>
  );
}
