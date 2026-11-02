# Eval: synthetic_volunteer_platform.md

Run `20261102-115651` · commit `bd26ab4-dirty` · extract prompt `b3a998ee` · model `qwen/qwen3-8b` · judge `qwen/qwen3-8b`

## Metrics

| Metric | Value |
|---|---|
| Precision | 100% (21 of 22 predictions; 0 false positives) |
| Recall | 100% (21 of 21 gold requirements) |
| F1 | 1.00 |
| Mandatory accuracy (on matches) | 71% |
| Category accuracy (on matches) | 81% |
| Quotes found in source | 73% |
| Faithful descriptions (judge) | 96% {'same': 21, 'stronger': 1} |

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
| G13 | desirable_not_essential | **FAIL** | description stronger: The quote says 'desirable but not essential' while the description states it as a requirement. |
| G14 | budget_cap | pass |  |
| G15 | in_table | pass |  |
| G16 | in_table | pass |  |
| G18 | should_not_must | **FAIL** | mandatory=True, expected False |
| G19 | list_split | **FAIL** | mandatory=True, expected False |
| G20 | list_split | **FAIL** | mandatory=True, expected False |
| G21 | list_split | **FAIL** | mandatory=True, expected False |
| N01 | client_goal | pass |  |
| N02 | relaxation | pass |  |
| N03 | relaxation | pass |  |
| N04 | permission_or_option | pass |  |
| N05 | client_timeline | pass |  |

Passed by trap type: budget_cap 1/1, client_goal 1/1, client_timeline 1/1, desirable_not_essential 0/1, in_table 2/2, list_split 3/6, permission_or_option 1/1, prohibition 1/1, relaxation 2/2, should_not_must 0/3, two_in_one_paragraph 2/2

## Usage

| Step | Calls | Prompt tokens | Completion tokens | Latency (s) | Est. cost (USD) |
|---|---|---|---|---|---|
| extract | 5 | 2,719 | 1,111 | 61.2 | 0.0013 |
| judge | 4 | 2,028 | 775 | 44.6 | 0.0009 |
| **total** | 9 | 4,747 | 1,886 | 105.9 | 0.0022 |
