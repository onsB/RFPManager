# Eval: synthetic_volunteer_platform.md

Run `20261101-174328` · commit `d7e0475-dirty` · extract prompt `b9053de8` · model `qwen/qwen3-8b` · judge `qwen/qwen3-8b`

## Metrics

| Metric | Value |
|---|---|
| Precision | 88% (21 of 25 predictions; 3 false positives) |
| Recall | 100% (21 of 21 gold requirements) |
| F1 | 0.93 |
| Mandatory accuracy (on matches) | 71% |
| Category accuracy (on matches) | 86% |
| Quotes found in source | 72% |
| Faithful descriptions (judge) | 84% {'same': 21, 'stronger': 3, 'contradicts': 1} |

## Traps

| Gold | Trap | Result | Why |
|---|---|---|---|
| G03 | should_not_must | **FAIL** | mandatory=True, expected False |
| G04 | should_not_must | **FAIL** | mandatory=True, expected False |
| G05 | list_split | pass |  |
| G06 | list_split | pass |  |
| G07 | list_split | pass |  |
| G08 | two_in_one_paragraph | pass |  |
| G09 | two_in_one_paragraph | pass |  |
| G11 | prohibition | pass |  |
| G13 | desirable_not_essential | **FAIL** | description contradicts: The description requires ISO 27001 certification, while the quote states it is desirable but not essential. |
| G14 | budget_cap | **FAIL** | description stronger: The description omits the requirement to include all licences and support for the first year. |
| G15 | in_table | **FAIL** | description stronger: The description adds a specific deadline (31 March 2027) that is earlier than the quote's date (30 June 2027). |
| G16 | in_table | pass |  |
| G18 | should_not_must | **FAIL** | mandatory=True, expected False |
| G19 | list_split | **FAIL** | mandatory=True, expected False |
| G20 | list_split | **FAIL** | mandatory=True, expected False |
| G21 | list_split | **FAIL** | mandatory=True, expected False |
| N01 | client_goal | pass |  |
| N02 | relaxation | pass |  |
| N03 | relaxation | **FAIL** | extracted as S07-R06: Do not require individual CVs |
| N04 | permission_or_option | **FAIL** | extracted as S07-R07: Accept applications from consortia |
| N05 | client_timeline | **FAIL** | extracted as S07-R08: Announce outcome by February 2027 |

Passed by trap type: budget_cap 0/1, client_goal 1/1, client_timeline 0/1, desirable_not_essential 0/1, in_table 1/2, list_split 3/6, permission_or_option 0/1, prohibition 1/1, relaxation 1/2, should_not_must 0/3, two_in_one_paragraph 2/2

## False positives

- S07-R06 (forbidden, N03): Do not require individual CVs
- S07-R07 (forbidden, N04): Accept applications from consortia
- S07-R08 (forbidden, N05): Announce outcome by February 2027

## Usage

| Step | Calls | Prompt tokens | Completion tokens | Latency (s) | Est. cost (USD) |
|---|---|---|---|---|---|
| extract | 7 | 2,746 | 1,205 | 64.0 | 0.0013 |
| judge | 25 | 6,566 | 609 | 37.5 | 0.0016 |
| **total** | 32 | 9,312 | 1,814 | 101.5 | 0.0029 |
