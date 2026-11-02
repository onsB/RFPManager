# Assumptions

## Data
- No RFP brief was provided in /inputs, so I used publicly available procurement
  documents published on UK Contracts Finder and US government sites, as allowed
  by the brief ("provided inputs or synthetic data").
- These documents are public notices, not client data. They contain the names and
  emails of procurement contacts, which were published for bidders to use;
  they are kept as-is / redacted.
- Synthetic briefs were written for this project, with fictional organisations: the
  gold-labelled test brief in `eval/briefs/` and three demo briefs in `inputs/demo/`. Both
  contain planted traps (see DECISIONS.md and `inputs/README.md`). The real documents are in
  `inputs/public/`.

## Scope
- "RFP brief" is read broadly: RFPs, invitations to tender and RFQs. Documents that
  aren't solicitations (e.g. an expression of interest) should be flagged, not summarised.
- The summary is written from the bidder's point of view.

## Environment
- The LLM runs locally (LM Studio, OpenAI-compatible API). No paid API is required.
- Cost is reported as an estimate at reference hosted prices, since local inference is free.
  Reference: Qwen3 8B at $0.18 / 1M input and $0.70 / 1M output tokens, Alibaba's listed
  price as shown on [TypingMind's cost estimator](https://custom.typingmind.com/tools/estimate-llm-usage-costs/alibaba/qwen3-8b)
  (checked 2026-10-31). Other hosts list $0.05–$0.12 input, so this is an upper estimate.
  Prices are set in `app/config.py`.
- Latency is wall-clock time on the local machine (GPU-dependent), not comparable to a hosted API.