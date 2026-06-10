"use client";
import { useEffect, useRef, useState } from "react";

type Ev = { actor: string; kind: string; authority: string; payload: any };
type Result = {
  verdict: string; confidence: number; decision: string; rationale: string;
  evidence: { agent: string; claim: string; source: string; verified: boolean | null; confidence: number | null; supports: string }[];
  rejected_claims: string[]; consortium_confirmation: string | null; report: string;
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

export default function Home() {
  const [fixtures, setFixtures] = useState<string[]>([]);
  const [fixture, setFixture] = useState("structuring");
  const [consortium, setConsortium] = useState(false);
  const [events, setEvents] = useState<Ev[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [running, setRunning] = useState(false);
  const [evalR, setEvalR] = useState<EvalR | null>(null);
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
  const [evalBusy, setEvalBusy] = useState(false);
  function runEval() {
    fetch("/api/eval?limit=48").then((r) => r.json()).then(setEvalR).catch(() => {});
  }
  function runEvalPublic() {
    setEvalBusy(true);
    fetch("/api/eval/public?limit=200").then((r) => r.json())
      .then(setEvalR).catch(() => {}).finally(() => setEvalBusy(false));
  }

  const verified = result?.evidence.filter((e) => e.verified) ?? [];
  const rejected = result?.evidence.filter((e) => e.verified === false) ?? [];

  return (
    <div className="wrap">
      <h1>AEGIS — Autonomous Financial-Crime Investigation Mesh</h1>
      <p className="sub">An adversarial team of governed agents investigates each alert, argues against
        itself, refuses any uncited claim, and decides what a human even needs to see.</p>

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
        <button onClick={runEval}>📊 Run accuracy eval (synthetic)</button>
        <button onClick={runEvalPublic} disabled={evalBusy}>
          {evalBusy ? "Scoring…" : "🏦 Run public benchmark (IBM AML)"}
        </button>
      </div>

      <div className="grid">
        {/* Live feed */}
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

        {/* Verdict + evidence */}
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

      {/* Accuracy panel */}
      <div className="panel" style={{ marginTop: 16 }}>
        <h2>Baseline (single-pass) vs AEGIS — accuracy
          {evalR?.dataset && <span className="src"> · {evalR.dataset.startsWith("public")
            ? "IBM AML public benchmark (external labels)" : "synthetic sanity check"}</span>}
        </h2>
        {!evalR && <div className="sub">“Run accuracy eval (synthetic)” is a quick sanity check;
          “Run public benchmark (IBM AML)” scores a slice of a real AML dataset with
          externally-authored labels — the credible number (§9).</div>}
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

      <p className="sub" style={{ marginTop: 20 }}>
        Coordinated, governed, and audited through Band · CrewAI specialists + LangGraph verification ·
        AI/ML API + Featherless · synthetic & public-benchmark data only, no real PII.
      </p>
    </div>
  );
}
