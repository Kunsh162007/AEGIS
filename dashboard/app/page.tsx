"use client";
import { useEffect, useRef, useState } from "react";

type Ev = { actor: string; kind: string; authority: string; room?: string; payload: any };
type Result = {
  verdict: string; confidence: number; decision: string; rationale: string;
  evidence: { agent: string; claim: string; source: string; verified: boolean | null; confidence: number | null; supports: string }[];
  rejected_claims: string[]; consortium_confirmation: string | null; report: string;
};
type AccountResult = { account: string; alert_type: string; transactions: number; result: Result & { case_id: string } };
type Plan = { filename: string; accounts: { account: string; alert_type: string; transactions: number }[] };
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

type Tab = "analyze" | "benchmark";

export default function Home() {
  const [tab, setTab] = useState<Tab>("analyze");

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
      const r = await fetch(`/api/analyze/stream${qs}`, { method: "POST", body: fd });
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
        <span className="badge">10 governed agents · evidence-verified verdicts</span>
      </header>

      <nav className="tabs">
        <button className={`tab ${tab === "analyze" ? "active" : ""}`} onClick={() => setTab("analyze")}>
          Analyze
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
