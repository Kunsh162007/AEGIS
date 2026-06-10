"""Seed corpus of AML typologies + synthetic adverse-media snippets.

SYNTHETIC ONLY. These are the documents the External Intelligence agent
retrieves over. Reviewed precedent from the feedback loop is appended at runtime.
"""

TYPOLOGIES = [
    {"id": "typology/structuring",
     "text": "Structuring (smurfing): breaking a large sum into multiple deposits "
             "below the $10,000 currency-transaction-report threshold to avoid "
             "reporting. Indicators: many cash deposits just under 10k in a short "
             "window from related parties."},
    {"id": "typology/mule_network",
     "text": "Money-mule network: many feeder accounts fan money into a single hub "
             "account which then rapidly transfers it onward, often to a foreign "
             "business account. Indicators: high fan-in, fast pass-through, "
             "near-100% pass-through ratio."},
    {"id": "typology/layering",
     "text": "Layering: moving funds through a chain or cycle of accounts to obscure "
             "origin. Indicators: round-tripping, cycles in the money-flow graph, "
             "rapid sequential transfers."},
    {"id": "typology/round_tripping",
     "text": "Round-tripping: funds leave and return to the originator through "
             "intermediaries to fabricate legitimate-looking activity."},
    {"id": "adverse/cy_shell",
     "text": "Adverse media: business accounts domiciled in certain low-scrutiny "
             "jurisdictions have been associated with shell-company layering."},
    {"id": "benign/property",
     "text": "Benign property completion: a single very large credit from a "
             "regulated conveyancer, conveyancing, or solicitor is consistent with "
             "a property sale completion and is usually not suspicious on its own."},
    {"id": "benign/payroll",
     "text": "Benign payroll: a one-off large credit from a known employer with a "
             "payroll, bonus, or salary reference is consistent with employment "
             "income and usually not suspicious on its own."},
]
