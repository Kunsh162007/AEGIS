# Bundled public benchmark — `ibm_sample.csv`

A small, balanced, **externally-labelled** slice of the **IBM "Transactions for
Anti-Money-Laundering (AML)"** dataset (HI-Small variant), so the deployed app
can show a credible accuracy number (§9) without a ~475 MB download.

- **Source:** <https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml> (synthetic — **no real PII**, licence CC BY-SA 4.0).
- **How it was built:** a one-off build script (removed from the repo after use) streamed the first 1.5 M transactions of `HI-Small_Trans.csv`, picked the 150 most active **laundering** accounts (the structural centres a first-line rule would alert) plus 230 representative random **benign** accounts, and kept every transaction touching them (≤25 per account). Labels are IBM's own `Is Laundering` flag — we only choose which accounts to include, never relabel. Output is a normalised money-flow CSV (`src,dst,amount,channel,isFraud`).
- **Reproduce:** download `HI-Small_Trans.csv` from Kaggle and point `PUBLIC_DATASET_PATH` at it to score the full dataset with `python -m src.eval.harness`.

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
baseline does? On this slice (200 cases) AEGIS cuts false positives by **~77 %** while holding the catch rate at the baseline's level (**~89 % vs ~90 %**). Recall is reported alongside the reduction — AEGIS is a triage/
investigation layer over alerted accounts, strongest on *structured* laundering.
