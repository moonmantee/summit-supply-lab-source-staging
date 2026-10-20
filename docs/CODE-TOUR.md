# Code tour

| Start here | What to inspect |
| --- | --- |
| [Purchase probe](../competition-code/score01/shop_probe.py) | Real order submission, order token/history matching and rejection of static substitutes |
| [Scorer](../competition-code/score01/scorer.py) and [lifecycle](../competition-code/score01/lifecycle.py) | Probe results, event state, availability and SLA behavior |
| [Portal store](../competition-code/score01/portal_store.py) and [inject services](../competition-code/score01/inject_services.py) | Task release, verification, completion and persistent state |
| [Shop routes](../competition-code/shop/public/order.php) | PHP validation and database-backed order flow |
| [Controller](../competition-code/red-team/controller/fixture_coordinator.py) and [panel service](../competition-code/red-team/controller/panel_service.py) | Event coordination, profiles and operator control |
| [CALDERA policy](../competition-code/red-team/caldera/stage_policy.py) | Scope and framework integration |
| [Aeacus definitions](../competition-code/aeacus/shop01/definitions/scoring.conf) and [native probes](../competition-code/aeacus/shop01/support/probes/check.py) | Readable host checks and native-state verification |
| [Test source](../preparation/tests/score01/test_shop_probe.py) | Positive behavior plus broken database, missing history and static-response cases |

Read the [contribution statement](../CONTRIBUTIONS.md) before attributing code. The custom source contains substantial AI-assisted implementation. Configuration and orchestration build on upstream platforms; these are identified in [dependencies](DEPENDENCIES.md).
