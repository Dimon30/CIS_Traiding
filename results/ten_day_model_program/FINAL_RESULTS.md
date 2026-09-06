# CIS Trading: итог 10-дневной ML-программы

**Статус: `CRITERION_NOT_MET`.** Выбран run `20260905_wave0_temporal_v3_baseline`.

Все три full bundles прошли `audit_evaluation_v3.py` и имеют `canonical_eligible=true`: **True**.

## Основные результаты

| Run | Model/features | Lift | Hit rate | Random | Signals/week | Mean regret bp | p90 regret bp |
|---|---|---:|---:|---:|---:|---:|---:|
| `20260905_wave0_temporal_v3_baseline` | random_forest / full_market_with_fx | 1.214 | 0.847 | 0.698 | 0.426 | 23.4 | 70.5 |
| `20260905_h013_temporal_v3_catboost_control` | catboost / full_market_with_fx | 1.197 | 0.798 | 0.667 | 0.433 | 35.3 | 108.2 |
| `20260906_h015_temporal_v3_implied_usd_rf` | random_forest / full_market_with_fx_and_implied_usd | 1.165 | 0.829 | 0.712 | 0.361 | 24.9 | 71.9 |

## Model-control и feature-ablation

- CatBoost: accepted=False; delta hit rate -0.0544; P(improves) 0.012; delta mean regret 12.40 bp; frontier wins 122/238.
- H015: accepted=False; delta hit rate -0.0210; P(improves) 0.049; delta mean regret 1.61 bp; positive full years 2/4.

## Финальный offline-критерий

Aggregate lift: **1.214**; full-year lifts: 2022: 1.580, 2023: 1.187, 2024: 1.128, 2025: 1.280; bootstrap P(lift >= 1.3): **0.012**.

Результат относится к proxy-курсам ЦБ РФ и не доказывает выгоду по историческим банковским курсам или влияние пушей на доверие клиентов.

Программа остановлена согласно timebox; deferred backlog автоматически не запускается.
