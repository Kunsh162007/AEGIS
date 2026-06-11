"use client";
import { useEffect, useRef, useState } from "react";

type Ev = { actor: string; kind: string; authority: string; payload: any };
type Result = {
  verdict: string; confidence: number; decision: string; rationale: string;
  evidence: { agent: string; claim: string; source: string; verified: boolean | null; confidence: number | null; supports: string }[];
  rejected_claims: string[]; consortium_confirmation: string | null; report: string;
};
type UploadR = {
  filename: string; accounts_analyzed: number;
  results: { account: string; alert_type: string; transactions: number; result: Result & { case_id: string } }[];
};
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

type Tab = "analyze" | "demo" | "validation";

export default function Home() {
  const [tab, setTab] = useState<Tab>("analyze");

  // ── live demo state ────────────────────────────────────────────────────
  const [fixtures, setFixtures] = useState<string[]>([]);
  const [fixture, setFixture] = useState("structuring");
  const [consortium, setConsortium] = useState(false);
  const [events, setEvents] = useState<Ev[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [running, setRunning] = useState(false);
  const [evalR, setEvalR] = useState<EvalR | null>(null);
  const [evalBusy, setEvalBusy] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/fixtures").then((r) => r.json()).then((d) => setFixtures(d.fixtures)).catch(() => {});
  }, []);
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [events]);

  function run() {
    setEvents([]); setResult(null); setRunning(true);
    const url = `/api/investigate/stream?fixture=${fixture}&consortium=${consortium}`;
    const es = new EventSource(url);
    es.onmessage = (m) => {
      const item = JSON.parse(m.data);
      if (item.kind === "result") { setResult(item.payload); setRunning(false); es.close(); }
      else setEvents((prev) => [...prev, item]);
    };
    es.onerror = () => { setRunning(false); es.close(); };
  }
  function runEval() {
    fetch("/api/eval?limit=48").then((r) => r.json()).then(setEvalR).catch(() => {});
  }
  function runEvalPublic() {
    setEvalBusy(true);
    fetch("/api/eval/public?limit=200").then((r) => r.json())
      .then(setEvalR).catch(() => {}).finally(() => setEvalBusy(false));
  }

  // ── bring-your-own-data state ──────────────────────────────────────────
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadFocus, setUploadFocus] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadR, setUploadR] = useState<UploadR | null>(null);
  const [uploadErr, setUploadErr] = useState("");
  const [dragOver, setDragOver] = useState(false);

  function runUpload() {
    if (!uploadFile) return;
    setUploadBusy(true); setUploadErr(""); setUploadR(null);
    const fd = new FormData();
    fd.append("file", uploadFile);
    const qs = uploadFocus.trim() ? `?focus=${encodeURIComponent(uploadFocus.trim())}` : "";
    fetch(`/api/analyze${qs}`, { method: "POST", body: fd })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail || "analysis failed");
        setUploadR(body);
      })
      .catch((e) => setUploadErr(String(e.message || e)))
      .finally(() => setUploadBusy(false));
  }

  function downloadReport() {
    if (!uploadR) return;
    const lines: string[] = [
      `AEGIS INVESTIGATION REPORT`,
      `File: ${uploadR.filename}`,
      `Generated: ${new Date().toISOString()}`,
      `Accounts investigated: ${uploadR.accounts_analyzed}`,
      ``,
    ];
    for (const r of uploadR.results) {
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
    a.download = `aegis-report-${uploadR.filename.replace(/\.[^.]+$/, "")}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const verified = result?.evidence.filter((e) => e.verified) ?? [];
  const rejected = result?.evidence.filter((e) => e.verified === false) ?? [];
  const suspiciousN = uploadR?.results.filter((r) => r.result.verdict === "suspicious").length ?? 0;
  const clearedN = uploadR?.results.filter((r) => r.result.verdict !== "suspicious").length ?? 0;

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
          Analyze your data
        </button>
        <button className={`tab ${tab === "demo" ? "active" : ""}`} onClick={() => setTab("demo")}>
          Live demo
        </button>
        <button className={`tab ${tab === "validation" ? "active" : ""}`} onClick={() => setTab("validation")}>
          Validation
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
              <button className="primary" onClick={runUpload} disabled={!uploadFile || uploadBusy}>
                {uploadBusy ? "Investigating…" : "Run investigation"}
              </button>
              {uploadR && <button className="ghost" onClick={downloadReport}>⬇ Download report</button>}
            </div>
            <div className="finehint">
              Needs columns for source account, destination account and amount — common header
              names (from/to, nameOrig/nameDest, sender/beneficiary…) are detected automatically.
              Files are analyzed in memory and never stored.
            </div>
            {uploadErr && <div className="error">⚠ {uploadErr}</div>}
          </div>

          {uploadR && (
            <>
              <div className="summary">
                <div className="chip">{uploadR.filename}</div>
                <div className="chip red">{suspiciousN} suspicious</div>
                <div className="chip green">{clearedN} cleared</div>
              </div>
              {uploadR.results.map((r, i) => {
                const v = r.result.evidence.filter((e) => e.verified);
                return (
                  <div className="panel" style={{ marginTop: 12 }} key={i}>
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
                  </div>
                );
              })}
            </>
          )}
        </>
      )}

      {/* ════════ LIVE DEMO ════════ */}
      {tab === "demo" && (
        <>
          <div className="controls">
            <select value={fixture} onChange={(e) => setFixture(e.target.value)}>
              {fixtures.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <label className="chk">
              <input type="checkbox" checked={consortium} onChange={(e) => setConsortium(e.target.checked)} />
              cross-bank consortium
            </label>
            <button className="primary" onClick={run} disabled={running}>
              {running ? "Investigating…" : "▶ Run investigation"}
            </button>
          </div>

          <div className="grid">
            <div className="panel">
              <h2>Live investigation (governed audit stream)</h2>
              <div className="feed" ref={feedRef}>
                {events.length === 0 && <div className="sub">Press “Run investigation” to watch the agents work.</div>}
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
              <h2>Verdict & evidence chain</h2>
              {!result && <div className="sub">The verdict, evidence chain, and autonomy decision appear here.</div>}
              {result && (
                <>
                  <div className={`verdict-box ${result.verdict}`}>
                    <div className="verdict-big">{result.verdict}</div>
                    <div>confidence {result.confidence}</div>
                    <div className="decision">
                      {result.decision === "auto_clear" ? "🟢 Auto-cleared autonomously" : "🧑‍⚖️ Escalated to compliance officer"}
                      <br />{result.rationale}
                    </div>
                  </div>
                  {result.consortium_confirmation && (
                    <div className="consortium">🤝 {result.consortium_confirmation}</div>
                  )}
                  <h2 style={{ marginTop: 16 }}>Verified claims ({verified.length})</h2>
                  {verified.map((e, i) => (
                    <div className="evi" key={i}>{e.claim}<br /><span className="src">{e.agent} · {e.source} · conf {e.confidence}</span></div>
                  ))}
                  {rejected.length > 0 && <h2 style={{ marginTop: 16 }}>Rejected by Verifier ({rejected.length})</h2>}
                  {rejected.map((e, i) => (
                    <div className="evi rej" key={i}>{e.claim}<br /><span className="src">{e.agent} · {e.source || "no source"}</span></div>
                  ))}
                </>
              )}
            </div>
          </div>
        </>
      )}

      {/* ════════ VALIDATION ════════ */}
      {tab === "validation" && (
        <div className="panel">
          <h2>Measured accuracy — single-pass baseline vs AEGIS
            {evalR?.dataset && <span className="src"> · {evalR.dataset.startsWith("public")
              ? "IBM AML public benchmark (external labels)" : "synthetic sanity check"}</span>}
          </h2>
          <div className="controls">
            <button onClick={runEval}>Synthetic sanity check</button>
            <button className="primary" onClick={runEvalPublic} disabled={evalBusy}>
              {evalBusy ? "Scoring…" : "Score on IBM AML benchmark"}
            </button>
          </div>
          {!evalR && <div className="sub">The benchmark scores AEGIS on a slice of the IBM
            Anti-Money-Laundering dataset whose labels were authored externally —
            measuring how many false alerts AEGIS clears while keeping the catch rate.</div>}
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
