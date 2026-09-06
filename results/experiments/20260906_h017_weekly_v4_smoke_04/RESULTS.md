# H017: attractiveness gate + future-safety RF

Decision: **failed**. Full Monte Carlo allowed: **False**. Accepted corridors: none.

| Corridor | Push/week | Safety | Mean regret, bp | P90 regret, bp | P90 gap, days | Active weeks |
|---|---:|---:|---:|---:|---:|---:|
| RUB_AMD | 0.292 | 69.0% | 64.5 | 203.8 | 35.8 | 29.1% |
| RUB_KGS | 0.321 | 64.1% | 83.4 | 285.0 | 29.0 | 32.0% |
| RUB_KZT | 0.329 | 61.3% | 78.1 | 215.2 | 36.2 | 32.8% |
| RUB_TJS | 0.259 | 60.3% | 103.8 | 283.5 | 28.5 | 25.8% |
| RUB_UZS | 0.362 | 63.6% | 64.6 | 197.6 | 42.4 | 36.1% |

The policy misses the preregistered cadence and quality guardrails in every corridor. The full Monte Carlo/model-zoo branch is therefore stopped.

| Corridor | Baseline | Model | Random | Delta | Lift |
|---|---|---:|---:|---:|---:|
| RUB_AMD | future_safety | 69.0% | 67.6% | +1.4% | 1.021 |
| RUB_AMD | product | 69.0% | 51.9% | +17.1% | 1.330 |
| RUB_AMD | conditional | 69.0% | 69.9% | -0.9% | 0.987 |
| RUB_KGS | future_safety | 64.1% | 68.1% | -3.9% | 0.942 |
| RUB_KGS | product | 64.1% | 52.2% | +11.9% | 1.229 |
| RUB_KGS | conditional | 64.1% | 66.6% | -2.5% | 0.963 |
| RUB_KZT | future_safety | 61.3% | 63.1% | -1.9% | 0.970 |
| RUB_KZT | product | 61.3% | 42.4% | +18.9% | 1.445 |
| RUB_KZT | conditional | 61.3% | 62.5% | -1.3% | 0.980 |
| RUB_TJS | future_safety | 60.3% | 66.8% | -6.4% | 0.903 |
| RUB_TJS | product | 60.3% | 48.3% | +12.0% | 1.248 |
| RUB_TJS | conditional | 60.3% | 62.9% | -2.6% | 0.959 |
| RUB_UZS | future_safety | 63.6% | 65.6% | -2.0% | 0.970 |
| RUB_UZS | product | 63.6% | 45.0% | +18.6% | 1.414 |
| RUB_UZS | conditional | 63.6% | 64.3% | -0.7% | 0.990 |

The product baseline can show lift while the conditional baseline is negative; acceptance therefore correctly uses incremental value among gate-days.

Canonical frozen RF remains a separate reference: 0.426 push/week, 84.7% safety, 23.4 bp mean regret, 70.5 bp p90 regret, lift 1.214. It is not the equal-frequency control.

This run is exploratory because its historical outer years were already inspected. Smoke uncertainty uses reduced draws/replicates and is diagnostic only. The CBR rate is a market proxy; bank-transfer benefit remains unverified.
