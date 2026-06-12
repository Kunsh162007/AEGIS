"""Strategic Intelligence (agent #12) — the cross-case typology analyst. Every
other agent sees one case at a time; this one reads the department's whole
casebook and surfaces what no per-case view can:

  * emerging typologies — the same laundering pattern recurring across cases,
  * repeat subjects — accounts investigated more than once,
  * bridge counterparties — one account quietly linking otherwise separate
    investigations (the classic sign of an undetected ring),
  * consortium-ready descriptors — abstract patterns safe to share with peer
    banks under §7 (typology + count only; never accounts or records).

Input rows come from the CaseStore; the briefing is pure computation, so it is
identical in mock and live mode.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .base import BaseAgent


class StrategicIntelAgent(BaseAgent):
    name = "strategic_intel"
    tier = "reasoning"

    def brief(self, rows: list[dict]) -> dict:
        flagged = [r for r in rows if r.get("verdict") in ("suspicious", "uncertain")]

        typologies = Counter(r["alert_type"] for r in flagged)
        emerging = [{"typology": t, "cases": n}
                    for t, n in typologies.most_common() if n >= 2]

        by_account: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            by_account[r["account"]].append(r["uid"])
        repeat_subjects = [{"account": a, "case_uids": uids}
                           for a, uids in by_account.items() if len(uids) >= 2]

        bridges: dict[str, set[str]] = defaultdict(set)
        for r in rows:
            for cp in r.get("counterparties") or []:
                bridges[cp].add(r["uid"])
        cross_links = sorted(
            ({"counterparty": cp, "links_cases": sorted(uids),
              "also_under_investigation": cp in by_account}
             for cp, uids in bridges.items() if len(uids) >= 2),
            key=lambda x: len(x["links_cases"]), reverse=True)[:10]

        shareable = [{"typology": e["typology"], "cases": e["cases"],
                      "scope": "pattern-only — no accounts, no records"}
                     for e in emerging]

        parts = [f"{len(rows)} case(s) on file, {len(flagged)} flagged"]
        if emerging:
            parts.append("recurring typology: "
                         + ", ".join(f"{e['typology']} ×{e['cases']}" for e in emerging))
        if cross_links:
            parts.append(f"{len(cross_links)} counterparty link(s) bridging "
                         "separate investigations — possible undetected ring")
        if repeat_subjects:
            parts.append(f"{len(repeat_subjects)} repeat subject(s)")

        return {
            "cases_reviewed": len(rows),
            "cases_flagged": len(flagged),
            "emerging_typologies": emerging,
            "repeat_subjects": repeat_subjects,
            "cross_case_links": cross_links,
            "shareable_patterns": shareable,
            "headline": "; ".join(parts) + ".",
        }
