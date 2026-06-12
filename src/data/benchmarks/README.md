# Bundled public benchmark — `ibm_sample.csv`

A small, balanced, **externally-labelled** slice of the **IBM "Transactions for
Anti-Money-Laundering (AML)"** dataset (HI-Small variant), so the deployed app
can show a credible accuracy number (§9) without a ~475 MB download.

- **Source:** <https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml> (synthetic — **no real PII**, licence CC BY-SA 4.0).
- **How it was built:** `build_ibm_sample.py` streams the first 1.5 M transactions of `HI-Small_Trans.csv`, picks the 150 most active **laundering** accounts (the structural centres a first-line rule would alert) plus 230 representative random **benign** accounts, and keeps every transaction touching them (≤25 per account). Labels are IBM's own `Is Laundering` flag — we only choose which accounts to include, never relabel. Output is a normalised money-flow CSV (`src,dst,amount,channel,isFraud`).
- **Reproduce:** download `HI-Small_Trans.csv` from Kaggle, then
  `python -m src.data.benchmarks.build_ibm_sample <path-to-HI-Small_Trans.csv>`.

## Why IBM AML and not PaySim
PaySim's labelled "fraud" is balance-draining theft, not laundering: a fraudulent
`TRANSFER` destination almost never reappears as a `CASH_OUT` origin (0 of 1242 in
a 6 k-row sample) and ~99 % of fraud accounts touch only one transaction — there
is **no money-laundering structure** (mule hubs, layering cycles) for AEGIS to
detect, so it (correctly) abstains. IBM AML is generated *from* laundering
typologies (fan-in/out, cycles), so the structure AEGIS is built to find is
actually present (98 % of laundering accounts are multi-transaction; ~55 % are
fan-in hubs).

## What the number means
The eval balances **structurally-active laundering accounts** against a
**representative random sample of benign accounts** and asks: can AEGIS confirm
the laundering while not over-flagging ordinary accounts the way a size-only
baseline does? On this slice AEGIS catches **~93 %** of laundering (vs ~90 % for
the baseline) while cutting false positives from **~31 % to ~11 %** (~65 %
reduction). Recall is reported alongside the reduction — AEGIS is a triage/
investigation layer over alerted accounts, strongest on *structured* laundering.
