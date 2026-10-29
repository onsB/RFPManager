# Assumptions

## Data
- No RFP brief was provided in /inputs, so I used publicly available procurement
  documents published on UK Contracts Finder and US government sites, as allowed
  by the brief ("provided inputs or synthetic data").
- These documents are public notices, not client data. They contain the names and
  emails of procurement contacts, which were published for bidders to use;
  they are kept as-is / redacted.
- Synthetic briefs in eval/ were written for this project and contain planted
  traps (see DECISIONS.md).

## Scope
- "RFP brief" is read broadly: RFPs, invitations to tender and RFQs. Documents that
  aren't solicitations (e.g. an expression of interest) should be flagged, not summarised.
- The summary is written from the bidder's point of view.

## Environment
- The LLM runs locally (LM Studio, OpenAI-compatible API). No paid API is required.
- Cost is reported as an estimate at reference hosted prices, since local inference is free.