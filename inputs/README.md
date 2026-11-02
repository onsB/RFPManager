# Inputs

Documents to run the app on: upload one on the web page, or
`uv run python -m app.main inputs/<folder>/<file>`.

The gold-labelled test brief for the eval harness lives separately, in `eval/briefs/`, so
the test set is never tuned on.

## public/: real procurement documents

Published for bidders on UK Contracts Finder and US government sites (see ASSUMPTIONS.md).
Long documents: a full run with the critic takes 10-30 minutes on a laptop.

| File | What it is | Why it's here |
|---|---|---|
| `InvitationtoTender_CommunitiesofPracticeDevelopment.pdf` | National Trust ITT, Nature Towns and Cities communities of practice (~16 sections) | The default input. Deadline in a table cell; the "CVs are not required" negation trap |
| `GATE_JBU_Beach+Clubs_RFP_final.pdf` | NPS lease of the Rockaway beach clubs (~50 sections) | Long and messy: table of contents, buyer rights, as-is property, a 2026 vs 2027 lease-start contradiction. The critic's acceptance test |
| `ContractTender2027.pdf` | Hertford festive lighting tender | Deadline inside a sentence ("by midday, 4th September"), next to a delivery deadline decoy |
| `SolicitationAmendmentN0018926QL2410001.pdf` | US Navy paint RFQ | Key data in PDF form fields, which the parser doesn't read |
| `ReedinPartnership_FutureEmploymentSupport_EOISupportingInformation.pdf` | Expression of interest, not a solicitation | Negative example: no deadline, few real requirements |

## demo/: short synthetic briefs for the demo

Written for this project, with fictional organisations and places. About 7 sections each,
so a full run with the critic takes a few minutes. Each one plants things the app should
catch:

| File | Domain | Look for |
|---|---|---|
| `harbourside_tenant_portal_itt.md` | UK housing association, IT (tenant portal) | **Deadline** "12 noon on 4 December 2026" picked from a table next to a questions deadline. **Contradiction:** contract start 11 January 2027 (Key dates) vs "will commence on 4 January 2027" (Budget). **Weighted evaluation criteria** for the approach. Buyer rights ("reserves the right not to award"). "Individual CVs are not required" and "consortia are welcome" (not requirements). Should vs must (SMS, availability). Concrete facts for risks: £180,000 cap, Keystone HMS API, 3,100 account migration, Cyber Essentials Plus |
| `port_alder_beach_cafe_rfp.md` | US city parks, concession | **Deadline** "3:00 PM PST on Friday, December 11, 2026" among four other dates. **Contradiction:** "five-year concession agreement" vs "initial term … three (3) years" (no date, so only `search_rfp` finds it). **As-is premises** with uncosted roof and grease-trap works: the risk the brief should name. $48,000 minimum or 12% of receipts, $25,000 deposit, $2M insurance. City rights and City duties (parking lot) that aren't the bidder's |
| `northvale_youth_evaluation_brief.md` | UK charity, research services | The clean one: **no planted contradiction**, so the critic should approve quickly. Deadline in a sentence, report dates as decoys. "Would welcome … not essential" and "should have experience" (optional). Enhanced DBS checks, 30 interviews including 10 early leavers, £35,000 budget |
