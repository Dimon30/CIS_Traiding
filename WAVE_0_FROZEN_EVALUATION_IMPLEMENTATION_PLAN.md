# Wave 0 — план реализации frozen evaluation framework

Статус документа: implementation source of truth для H009, H011, H012, H029 и H042.  
Область: только measurement/evaluation infrastructure.  
Не входит: новые targets, feature families, model families, calibration research, ensembles и новые источники данных.

## Implementation status — 2026-09-05

- W0.1–W0.12 реализованы: contracts/schema, universe, temporal splitter, nested
  selection, identity calibration, policy frontier, matched-random v3,
  synchronized uncertainty, runner integration, legacy regression и real-data
  smoke integration.
- Проверочный bundle: `tmp/wave0_v3_smoke_20260905_h`; post-run audit — `pass`.
- W0.13–W0.15 остаются отдельным gate: clean-worktree canonical run с 2000
  random draws и 5000 bootstrap replicates, review артефактов и формальная freeze
  отметка. До него Wave 1 заблокирована.

---

## 1. Current-state findings

### 1.1. Target и eligible universe

Основной target формируется в `scripts/build_dataset.py::build_label_rows`.

Для effective-date наблюдения `T`:

```text
q_T = value_rub / nominal
future_min = min(q_[T+1:T+h]) по календарным дням
future_regret = max(0, (q_T - future_min) / q_T)
message_hit = 1[future_regret <= epsilon]
```

Календарные пропуски внутри label-window заполняются последним действующим курсом через `build_daily_rates`. День `T` в future-window не входит. Для `h=3` будущий интервал — `T+1`, `T+2`, `T+3`.

`has_full_window` требует наличие как прошлого, так и будущего плеча `±h`, потому что та же таблица содержит вспомогательный `target_good_now`. Это означает, что строки без полного прошлого окна также исключаются, хотя `message_hit` требует только будущего окна.

Текущий eligible universe задаётся в двух местах:

- `scripts/run_backtest.py::add_features`: `eligible_for_signal = not same_rate_as_previous`;
- `scripts/run_backtest.py::load_model_frame`: остаются только `has_full_window=true` и `eligible_for_signal=true`.

Точное текущее правило:

```text
effective-date row
AND has_full_window
AND rate != immediately previous effective-date rate
```

Feature completeness не является eligibility-условием: пропуски дальше заполняются imputer, обученным на train.

Выходные и календарные дни без отдельной DBF-записи не становятся decision dates. Forward fill используется для labels, но не создаёт строки inference universe.

Диапазон данных:

| Corridor | Observations | Raw range | Eligible h=3/e=50 |
|---|---:|---|---:|
| RUB_TJS | 2468 | 2016-09-02…2026-09-02 | 2461 |
| RUB_UZS | 2468 | 2016-09-02…2026-09-02 | 2462 |
| RUB_KGS | 2468 | 2016-09-02…2026-09-02 | 2464 |
| RUB_AMD | 2468 | 2016-09-02…2026-09-02 | 2462 |
| RUB_KZT | 2468 | 2016-09-02…2026-09-02 | 2463 |

Фактически одинаковые повторные значения встречаются редко: 0–3 строки на коридор. Это не моделирование weekend staleness: weekend rows вообще отсутствуют.

### 1.2. Current temporal protocol

Основной runner — `scripts/run_experiment.py`.

`split_frame(frame, test_year=T, horizon=h)` создаёт:

```text
train:      date < January 1 of T-1 minus h days
validation: January 1 of T-1 <= date < January 1 of T minus h days
test:       January 1 of T <= date < January 1 of T+1
```

Таким образом, при `h=3` последние три календарных дня перед validation и test исключаются из предыдущего блока. Строки одной даты для pooled-стратегий остаются в одной временной части.

Текущие outer test years: 2022, 2023, 2024, 2025 и partial 2026.

Один validation block сейчас одновременно используется для:

- выбора hyperparameters;
- получения reference probability для Brier baseline;
- выбора threshold;
- проверки frequency;
- вычисления matched-random при threshold selection.

Отдельного calibration stage нет.

### 1.3. Model selection

`scripts/run_experiment.py::best_model`:

- строит `ParameterGrid`;
- для каждого кандидата заново fit-ит preprocessing и estimator на train;
- оценивает на validation;
- выбирает максимальный validation PR-AUC;
- validation ROC-AUC сохраняется диагностически;
- model family и feature set задаются hypothesis/config, а не выбираются внутри fold.

После выбора возвращается уже обученная на исходном train модель. Refit с выбранными hyperparameters на train+validation не выполняется.

### 1.4. Threshold и delivery policy

Corridor threshold выбирается в `threshold_for_group` и `global_threshold`.

Candidate thresholds — 81 quantile validation scores. Для каждого threshold:

1. берутся строки `score >= threshold`;
2. применяется greedy cooldown;
3. считается hit rate;
4. считается Wilson lower bound;
5. считается matched-random hit rate/lift.

Выбор лексикографический:

```text
max(
    Wilson lower hit-rate bound,
    matched-random lift,
    signal count
)
```

Текущие ограничения:

```text
signals >= 12
signals_per_week <= 2.0
```

Если feasible point отсутствует, код ослабляет minimum до пяти сигналов, а затем может выбрать любую точку. Это silent fallback, нарушающий смысл hard constraint.

Ограничение `<=2 signals/week` практически не является hard guardrail: при cooldown 4 дня соседние сигналы должны находиться более чем в четырёх календарных днях друг от друга, поэтому теоретический предел около `7/5 = 1.4` сигнала в неделю.

Cooldown применяется независимо по коридору. Условие:

```text
next_date > last_sent_date + 4 calendar days
```

То есть минимальный допустимый интервал — пять календарных дней.

### 1.5. Corrected matched-random v2

Текущая исправленная реализация находится в `scripts/run_backtest.py`:

- `random_schedule_state`;
- `random_schedule_completion_counts`;
- `sample_random_schedule`;
- `random_baseline`.

Положительная сторона текущей реализации: это не последовательный biased sampler. Dynamic programming подсчитывает количество допустимых completion schedules и затем равномерно выбирает одно расписание из всех cooldown-feasible расписаний заданной длины.

Matching сейчас обеспечивает:

- тот же corridor;
- тот же outer fold/test period;
- тот же filtered frame;
- то же число post-cooldown model signals;
- тот же cooldown.

Random выбирает из всех строк `test`, а `test` уже является текущим model eligible universe.

Что отсутствует:

- materialized/versioned universe ID;
- random draw IDs и schedules в artifacts;
- стабильный seed derivation, независимый от порядка `groupby`;
- гарантированное common-random-number reuse между моделями;
- paired uncertainty;
- matching или sensitivity по calendar composition;
- явная проверка update-gap composition;
- Monte Carlo standard error.

Текущие random seeds частично зависят от позиции corridor в `groupby`. При рефакторинге порядка групп числа могут измениться.

### 1.6. Сохраняемые predictions и metric layers

Evaluation schema v2 уже сохраняет:

- `predictions.csv` — все outer OOT eligible rows;
- `score`;
- `candidate`;
- `selected_signal`;
- `threshold`;
- target/regret;
- corridor/model/strategy/fold identity;
- `signals.csv` — post-policy subset;
- `validation_policy_tradeoffs.csv`;
- `model_metrics.csv`;
- `candidate_policy_metrics.csv`;
- `signal_policy_metrics.csv`;
- backward-compatible combined `fold_metrics.csv`.

Следовательно:

- raw OOT scores сохраняются;
- pre-policy и post-policy decisions различимы;
- отдельного `raw_score` и `calibrated_score` пока нет;
- validation scores не сохраняются;
- frontier сохраняется только для validation и только по threshold quantiles;
- outer policy frontier отсутствует.

### 1.7. Existing metrics

Уже реализованы:

- ROC-AUC;
- PR-AUC, baseline/gain/ratio;
- Brier score и Brier skill;
- log loss;
- candidate precision/recall/balanced accuracy;
- hit rate и Wilson interval;
- false pushes/rate;
- signals/week;
- inactive folds;
- matched-random hit rate и lift;
- mean future regret;
- mean moment advantage;
- RUB proxy для перевода 100 000 ₽.

Агрегированный v2 lift в H008 корректно считается через суммарные hits и ожидаемые matched-random hits, а не средним по fold lifts.

Не реализованы:

- signals/month;
- score coverage;
- active-month coverage;
- clustering metrics;
- regret quantiles/tail;
- conditional false-push regret;
- synchronized uncertainty;
- paired policy comparison;
- comparable-frequency frontier.

### 1.8. Manifests и фактические result contracts

H008 corrected bundles имеют `evaluation_schema_version=2` и сохраняют configs, dataset fingerprint, Git commit, strategy definitions, leakage statements, threshold/random descriptions и timestamps.

Недостатки manifest:

- fingerprint один на все CSV в `data/processed`, а не на фактически прочитанные inputs;
- нет per-file hashes;
- нет dirty-worktree marker/diff hash;
- нет exact split boundaries;
- нет eligible universe hash;
- нет dependency versions;
- нет versions для target, policy, random и uncertainty как отдельных контрактов;
- текстовое описание алгоритмов не заменяет machine-readable config.

Большинство старых manifests не имеют `evaluation_schema_version`. Они должны считаться legacy v1.

Canonical current evidence:

- reference logistic baseline: `results/backtest/`;
- corrected H008 RF/Logistic: `results/experiments/20260904_h008_pooling_v2_rf_logistic/`;
- H008 CatBoost companion: `results/experiments/20260905_h008_pooling_v2_catboost/`.

Число 1.42 из historical benchmark не является canonical corrected H008 result.

### 1.9. Existing audits и tests

Полезные reusable tests:

- `tests/test_build_dataset.py` — target boundary/full-window;
- `tests/test_feature_pipeline.py` — causal features, backward as-of join, purge;
- `tests/test_run_backtest.py` — cooldown и exact uniform schedule DP;
- `tests/test_run_experiment_metrics.py` — metric layers, inactive folds, threshold matched-random, legacy warning, paired coverage;
- `tests/test_evaluate_fast_slow.py` — event confirmation semantics.

`scripts/audit_pipeline.py` проверяет raw ordering/uniqueness/rate positivity, пересчёт targets, feature allowlist, auxiliary backward-as-of dates, наличие производных и один synthetic purge case.

Пока не проверяются exact production universe, synchronized corridors, split-role disjointness, calibration/policy/test boundaries, score coverage, model-independent universe, artifact schemas и future-label mutation invariants.

### 1.10. Дублирование

Temporal splitting, thresholding, cooldown, random baseline и aggregation частично дублируются между:

- `run_backtest.py`;
- `run_experiment.py`;
- `evaluate_indicators.py`;
- `evaluate_fast_slow.py`.

`run_experiment.py` импортирует evaluation helpers из legacy baseline script. Это делает `run_backtest.py` одновременно executable baseline и неформальной shared library.

### 1.11. Что способно сломать H008 reproduction

Любое из следующего изменит corrected H008 numbers:

- новая split-схема;
- смена threshold grid;
- удаление threshold fallback;
- новое frequency denominator;
- изменение seed derivation или corridor ordering;
- calendar-matched random вместо count-only random;
- refit модели после hyperparameter selection;
- изменение feature columns или sort stability перед cooldown;
- изменение dependency versions;
- изменение eligibility/full-window;
- изменение aggregation weights.

Поэтому v3 нельзя выдавать за пересчёт старого H008. Это новый protocol и новый evidence bundle.

---

## 2. Gap analysis

| Hypothesis | Уже есть | Частично | Отсутствует/нужно исправить |
|---|---|---|---|
| H009 | expanding outer walk-forward, purge, OOT predictions | train/validation/test и fold synchronization | отдельные model-selection, calibration и policy blocks; inner temporal selection; exact role manifests; refit contract |
| H011 | validation threshold tradeoffs, pre/post-policy flags, score metrics | 81-point validation curve | honest outer frontier по заранее выбранным budgets; score frontier; equal-frequency comparison; pre/post-thinning metrics |
| H012 | exact uniform sampling по cooldown-feasible schedules; same corridor/fold/count | общий filtered frame используется неявно | versioned universe, stable draw bank, paired draws, calendar/update-state controls, draw artifacts, MCSE |
| H029 | простые year-level Wilcoxon и ad hoc bootstrap proxy | paired fold joins | synchronized calendar-block bootstrap, cross-corridor dependence, paired model deltas, uncertainty schema |
| H042 | signals/week, inactive folds, cooldown, max 2/week | frequency участвует в threshold feasibility | hard constraints без fallback, meaningful budget grid, signals/month, active months, clustering, downside/tail regret, comparable-budget tables |

Основной архитектурный вывод: schema v2 уже содержит правильное начало разделения model/candidate/signal. Wave 0 должна расширить его до versioned reusable components, а не строить новый runner рядом.

---

## 3. Target architecture

```text
processed data snapshot
  → frozen eligible universe
  → temporal protocol v3 / FoldSpec
  → inner expanding model selection
  → base-model refit through selection cutoff
  → calibration adapter fit on calibration block
  → frozen scoring of policy and outer blocks
  → policy-block threshold/frontier selection
  → frozen outer OOT scores
  → selected delivery policy + budget-indexed frontier
  → matched-random v3 draw bank
  → synchronized paired block bootstrap
  → canonical metric tables
  → versioned manifest and reports
```

### 3.1. Model score

Model contract returns a continuous score where larger means safer/more attractive for sending. Model layer may use only model-development train, inner selection labels and fixed feature/model configs. It may not see calibration, policy or outer labels while choosing hyperparameters.

Required columns:

```text
raw_score
score_direction = "higher_is_better"
score_semantics
```

`score_semantics` distinguishes probability-like classification scores from future regression/risk scores introduced later.

### 3.2. Calibration

Calibration becomes an explicit adapter:

```python
fit(raw_score, target, corridor, date)
transform(raw_score, corridor)
```

Wave 0 implements only `IdentityCalibrator`. It reserves and audits the calibration block but does not run H021-style Platt/isotonic/beta comparisons.

Outputs:

```text
raw_score
calibrated_score
calibration_method = "identity"
```

Future calibration hypotheses must use the already frozen calibration block and interface.

### 3.3. Delivery policy

Policy receives only calibrated score, date, corridor and eligibility metadata. It owns threshold, budget mapping, cooldown, comparison-only thinning и coverage/inactivity reasons. Policy never trains the model and does not reinterpret score as probability.

### 3.4. Evaluation

Evaluation consumes frozen outer scores/decisions and labels. It must not return information to model selection, calibration or policy selection.

Два distinct outer products:

- selected-policy evaluation;
- diagnostic budget-indexed policy frontier.

Outer frontier points are thresholds selected on the policy block for fixed communication budgets, not thresholds optimized on outer labels.

### 3.5. Uncertainty

Uncertainty operates over frozen OOT decisions and aligned calendar blocks. It does not retrain models or reselect thresholds in bootstrap samples. Это оценивает uncertainty conditional on the fitted walk-forward experiment, а не researcher/model-selection uncertainty.

---

## 4. Exact temporal protocol v3

### 4.1. Outer fold roles

Для outer test year `T` и horizon `h`:

| Role | Calendar allocation |
|---|---|
| Inner model selection history | validation years 2019…`T-3` |
| Base-model refit | all eligible data strictly before `January 1 of T-2 - h` |
| Calibration | calendar year `T-2`, ending `h` days before next block |
| Policy selection | calendar year `T-1`, ending `h` days before outer test |
| Outer test | calendar year `T`, or available partial period |

Для каждого завершённого pre-test блока `[start, next_start)` retain only rows satisfying:

```text
date >= start
date < next_start - h calendar days
```

Это обеспечивает завершение target-window до следующего decision block.

### 4.2. Inner model selection

Для каждого hyperparameter candidate и каждого inner validation year `V` от 2019 до `T-3`:

```text
inner train: all eligible dates < January 1 of V - h
inner validation: year V, truncated at January 1 of V+1 - h
```

Minimum requirements:

- минимум 500 inner-train eligible rows на corridor;
- минимум 100 inner-validation rows на corridor;
- оба target class в каждой required training unit;
- все пять corridors для pooled experiments;
- минимум один valid inner fold.

Selection metric:

```text
mean corridor-year PR-AUC gain
= mean(PR-AUC - target prevalence)
```

Использовать equal weight per corridor-year cell, а не pooled row count.

Tie-breakers:

1. higher worst inner-year mean PR-AUC gain;
2. higher mean ROC-AUC;
3. simpler/config-earlier candidate;
4. deterministic serialized parameter order.

Model family здесь не выбирается: каждая family остаётся отдельным registered candidate.

### 4.3. Refit points

После выбора hyperparameters:

1. discard inner fitted estimators;
2. refit preprocessing и base model from scratch;
3. использовать всю eligible history до calibration start с purge;
4. не включать calibration или policy labels;
5. держать base model неизменной через calibration, policy и outer test.

Не refit-ить после calibration или policy selection: это изменило бы score distribution, на котором обучались calibrator/threshold.

### 4.4. Concrete folds для h=3

Dates use half-open end boundaries.

| Outer | Inner selection years | Final refit cutoff | Calibration | Policy | Test |
|---:|---|---|---|---|---|
| 2022 | 2019 | `<2019-12-29` | 2020-01-01…2020-12-26 | 2021-01-01…2021-12-28 | 2022 |
| 2023 | 2019–2020 | `<2020-12-29` | 2021-01-01…2021-12-28 | 2022-01-01…2022-12-28 | 2023 |
| 2024 | 2019–2021 | `<2021-12-29` | 2022-01-01…2022-12-28 | 2023-01-01…2023-12-28 | 2024 |
| 2025 | 2019–2022 | `<2022-12-29` | 2023-01-01…2023-12-28 | 2024-01-01…2024-12-28 | 2025 |
| 2026 | 2019–2023 | `<2023-12-29` | 2024-01-01…2024-12-28 | 2025-01-01…2025-12-27 | partial 2026 |

Observed sizes достаточны:

- outer 2022 final model history: 822–823 rows/corridor;
- calibration: 239–247;
- policy: 243–247;
- full tests: 246–248;
- partial 2026: 158–160.

Earliest inner 2019 fold имеет 576 train rows/corridor и 244–245 validation rows. Он valid, но только один независимый inner validation year существует для outer 2022. Manifest/report должен показывать `inner_fold_count=1`.

### 4.5. Partial 2026

```text
is_partial_fold = true
raw_data_cutoff = 2026-09-02
label_complete_through = 2026-08-29
```

Rules:

- не annualize counts как полный год;
- frequency использует фактическую synchronized exposure;
- aggregates сохраняются с partial 2026 и без него;
- partial fold не может один удовлетворить stability gate;
- worst-full-year и partial metrics разделены;
- 2026 labels не используются ни для одного выбора.

### 4.6. Corridor synchronization

Один master `FoldSpec` владеет boundaries всех corridors. Fold validity проверяется сразу для всех required corridors. Pooled/paired experiment не может молча удалить один corridor.

Shared exposure:

```text
exposure_start = January 1 of test year
exposure_end = minimum common label-complete date across required corridors
```

Signals/week/month denominators одинаковы для corridors и models внутри fold.

### 4.7. Leakage paths and blocks

| Leakage path | Control |
|---|---|
| Label window crosses next role | calendar-day purge перед каждой boundary |
| Hyperparameters see later labels | inner-fold API получает только development frames |
| Calibration sees policy labels | calibrator fit принимает только `role=calibration` |
| Threshold sees outer labels | selector принимает только `role=policy` |
| Outer frontier optimized on test | budget thresholds fitted on policy score distribution |
| Preprocessing fit on future | pipeline cloned/refit inside each fold |
| Post-calibration refit | запрещён engine state machine |
| Future auxiliary quote | backward-as-of assertion |
| Corridor split drift | single shared `FoldSpec` |
| Model changes universe | universe built before model adapter и hashed |
| Target field enters features | typed allowlist + forbidden-column audit |
| Partial labels near cutoff | full future-window eligibility |
| Test labels affect thinning | score/date-only thinning API |

---

## 5. Policy frontier design

### 5.1. Two frontiers

`score_frontier.csv` работает до threshold/cooldown, использует fixed top-score coverage grid и диагностирует ranking.

`policy_frontier.csv` использует policy-block thresholds, применяет cooldown до измерения frequency и оценивает заранее заданные communication budgets на outer test.

### 5.2. Threshold candidates

На policy block evaluate all distinct finite calibrated scores плюс zero/max-policy sentinels. Текущие 81 quantile сохраняются только в v2 mode.

### 5.3. Frozen budget grid

Canonical post-cooldown budget grid per corridor:

```text
0.10, 0.20, 0.30, …, 1.40 signals/calendar week
```

Comparison/integration region:

```text
0.25–1.25 signals/calendar week
```

Grid включает текущий 0.33–0.56 regime и feasible lower part продуктового ориентира; верхняя граница учитывает cooldown ceiling. Budgets 1.5 и 2.0 должны быть помечены structurally infeasible, а не пропущены.

Для budget выбирать threshold с наибольшей post-cooldown frequency, не превышающей budget. Tie: higher threshold, затем serialized threshold. Labels в mapping не используются.

### 5.4. Selected operating policy

Feasibility:

- cooldown violations = 0;
- минимум 12 policy-block post-cooldown signals;
- configured maximum frequency;
- finite score;
- required corridor coverage.

Нет fallback до пяти или unconstrained point. При отсутствии точки:

```text
policy_status = "inactive"
inactive_reason = "no_feasible_policy"
```

Сохраняется текущий objective, чтобы Wave 0 не смешивалась с H022:

```text
max Wilson lower hit-rate bound
then matched-random lift
then signal count
```

Только на policy block.

### 5.5. Cooldown and thinning

```text
eligible rows
→ score threshold
→ candidates
→ greedy chronological cooldown
→ delivered signals
```

Metrics сохраняются pre- и post-cooldown.

Thinning — только для exact-frequency paired comparison:

1. взять post-cooldown signals;
2. common count = меньший count двух models в corridor/fold/budget;
3. оставить highest policy score, tie по earlier date;
4. cooldown повторно не применять;
5. labels не передавать.

Оригинальные и thinned metrics сохраняются отдельно. При zero signals hit comparison undefined, но coverage difference обязателен.

### 5.6. Frontier metrics

Для model/fold/corridor/budget сохранять policy threshold, requested/achieved/outer frequency, eligible/score coverage, candidates, signals, hit/random/lift/delta, regret, active reason, cooldown suppression, clustering и composition diagnostics.

Summary:

- trapezoidal area under `delta_hit_rate(frequency)` over 0.25–1.25;
- worst-budget delta;
- feasible point count/share;
- dominance count против frozen baseline;
- no interpolation across inactive gaps.

### 5.7. Inactive cells

Каждый expected `(model, strategy, fold, corridor, budget)` row существует. Inactive rows имеют `signals=0`, `active=false`, null rates и `inactive_reason`. Их нельзя удалять перед coverage/frequency aggregation.

---

## 6. Matched-random v3 design

### 6.1. Keep versus change

Keep current exact DP schedule sampling, same count/cooldown/corridor and expected-hit aggregation.

Change: reusable module, explicit universe hash, stable seeds, persisted draw metadata, calendar matching, paired draw IDs и MCSE.

### 6.2. Canonical eligible universe

```text
universe_id
date
corridor
outer_fold
effective_rate
days_since_previous
same_rate_as_previous
has_full_target_window
eligible
ineligible_reason
```

Eligibility не зависит от feature/model. Missing score — score-coverage failure, а не удаление random date.

### 6.3. Primary sampling algorithm

Для delivered model schedule и corridor/fold:

1. compute exact model signal count per calendar month;
2. use same eligible universe;
3. require same monthly count vector;
4. enforce same cooldown across month boundaries;
5. uniformly sample all schedules satisfying constraints.

Quota-aware DP:

```text
ways(index, remaining_month_quotas)
  = ways(skip)
  + ways(take and jump past cooldown)
```

Monthly matching removes lift только от high-base-rate month composition; score metrics продолжают показывать seasonality ranking.

### 6.4. Sensitivity baselines

- `calendar_month_matched_v3` — primary;
- `fold_count_only_v2_compatible` — current corrected behavior;
- `month_update_gap_matched` — diagnostic with gap buckets `1`, `2`, `>=3`.

### 6.5. Draw count and seeds

```text
random_draws = 2000
smoke_random_draws = 200
base_seed = 42
```

RNG state derives from SHA-256 of protocol version, universe, corridor, fold, stratification, quota vector and draw ID. Не использовать Python `hash()` или group order.

Report MCSE; canonical aggregate matched-random MCSE должен быть `<=0.005`.

### 6.6. Paired reuse

`RandomDrawBank` keyed by universe, quotas and draw ID. Compared models используют same draw IDs/uniform stream; при identical quotas получают identical dates. Primary paired model effect использует direct model-minus-model differences, чтобы random noise не определял вывод.

### 6.7. Artifacts and aggregation

Persist:

- `random_draw_metrics.csv.gz`;
- `random_draw_registry.json`;
- optional `random_schedules.csv.gz` для canonical baseline/fixture.

Aggregate:

```text
expected_random_hits = mean(draw_hit_count)
random_hit_rate = sum(expected_random_hits) / sum(model_signal_count)
lift = sum(model_hits) / sum(expected_random_hits)
```

Не average cell lifts.

---

## 7. Uncertainty design

### 7.1. Resampling unit

Synchronized stratified moving-block bootstrap over calendar dates.

```text
primary block = 28 calendar days
sensitivity = 14 and 56 days
```

### 7.2. Synchronization

Для каждого outer year создать master calendar, sample moving blocks внутри года и применить одни block indices ко всем corridors, models и random schedules. Missing corridor date остаётся missing.

Это сохраняет common RUB shocks, local serial dependence и paired decisions.

### 7.3. Stratification by outer fold

Resample within fold, not across years. Preserve exposure weights. Дополнить:

- leave-one-full-year-out;
- full-years-only aggregate;
- worst full year;
- partial-2026 standalone.

### 7.4. Frozen decisions

Bootstrap input уже содержит `candidate`, `selected_signal`, budget signal и thinned signal. Не retrain, recalibrate, reselect threshold или reapply cooldown. Искусственные block boundaries не создают новую cooldown adjacency.

### 7.5. Paired comparisons

Для candidate B vs baseline A считать:

- `Δ hit rate`;
- `Δ matched-random hit rate`;
- `Δ lift`;
- `Δ mean/false-push/tail regret`;
- `Δ signals/week`;
- `Δ active-cell share`;
- `Δ frontier area`;
- score-level deltas.

Обе models/random draws/corridors получают same bootstrap sample.

### 7.6. Interaction with random

В каждом replicate resample contributions model decisions и date-level contributions random schedules одними blocks, average по draw IDs, затем считать aggregate lift. Сохранить conditional variant с expected random contributions.

### 7.7. Replicates and outputs

```text
bootstrap_replicates = 5000
bootstrap_seed = 42029
CI = percentile 2.5% / 97.5%
```

Также сохранять median, SE, probability of improvement и probability of practical-threshold crossing. P-values — только diagnostic.

`uncertainty_summary.csv`:

```text
comparison_id, scope, metric, estimate,
baseline_estimate, candidate_estimate, delta,
ci_low, ci_high, bootstrap_median, bootstrap_se,
probability_delta_gt_zero, probability_lift_ge_1_3,
block_length_days, replicates, full_years_only,
partial_fold_included, active_cells
```

CI относится к observed development OOT history, не доказывает future regimes или business validity.

---

## 8. Metrics contract

### 8.1. Identity columns

```text
artifact_schema_version
evaluation_protocol_version
run_id
hypothesis_id
model_id
feature_set_id
target_id
strategy
policy_id
frontier_point_id
corridor
outer_fold
test_year
is_partial_fold
universe_id
```

### 8.2. Primary metrics

Score layer:

- `pr_auc`;
- `pr_auc_gain`;
- `roc_auc`;
- score risk/coverage frontier;
- paired `delta_pr_auc_gain`.

Policy layer:

- `signal_hit_rate`;
- `matched_random_hit_rate`;
- `lift`;
- `delta_hit_rate`;
- `mean_realized_regret_bps`;
- budget-indexed performance;
- frontier area over 0.25–1.25/week.

Product headline remains lift, but maximum-lift point alone cannot declare a winner.

### 8.3. Hard guardrails

- cooldown violations;
- signals/week/month и total signals;
- eligible rows и score coverage;
- active/inactive cells и months;
- candidate count и cooldown suppression;
- false pushes/rate;
- no-feasible-policy count;
- budget feasibility.

Current product contract не задаёт hard minimum 1/week. Поэтому v3 freezes:

```text
hard maximum = cooldown-feasible configured maximum
hard minimum = null
minimum policy-block sample = 12
```

Business minimum требует изменения `PRODUCT_CONTRACT.md` до freeze.

### 8.4. Downside metrics

- mean/median/p90/p95/max realized regret;
- false-push regret mean/p90;
- severe false-push count с versioned threshold;
- existing moment advantage;
- RUB proxy, явно marked as proxy.

До numerical business utility не объединять false pushes и bps в якобы optimal scalar.

### 8.5. Clustering metrics

- median/p10 inter-signal gap;
- share gaps `<=7` days;
- max signals in rolling 28 days;
- max signals in calendar month;
- active month share;
- longest no-signal gap;
- cooldown violations.

First signal исключается из gap-distribution denominator.

### 8.6. Diagnostic-only metrics

- Brier/skill, log loss;
- calibration slope/intercept, fixed-bin ECE;
- balanced accuracy, candidate precision/recall;
- random sensitivities;
- RUB proxy;
- per-threshold policy tradeoffs;
- block-length sensitivity.

Calibration metrics diagnostic while using `IdentityCalibrator`.

### 8.7. Aggregation rules

- hit = total hits / total signals;
- random = expected random hits / total signals;
- lift = ratio of aggregate rates;
- regret signal-weighted;
- frequency = signals / shared exposure;
- score metrics have micro and corridor-year macro views;
- zero-signal cells remain;
- partial 2026 included/excluded views;
- canonical aggregate never averages fold lifts.

---

## 9. File-by-file implementation plan

### 9.1. New `scripts/evaluation/` package

#### `contracts.py`

Add protocol/schema enums, `EligibilitySpec`, `TemporalFoldSpec`, `TemporalRole`, score/policy/random/bootstrap contracts and role/column validators. No estimator dependency.

#### `universe.py`

Add `build_eligible_universe`, `validate_universe_independent_of_model`, `compute_universe_id`, `common_exposure_bounds`, `write_universe_audit`. Preserve current eligibility exactly.

#### `temporal.py`

Add `build_v3_outer_folds`, `build_inner_selection_folds`, `slice_role`, role-disjointness, purge and corridor synchronization assertions, partial-fold metadata.

#### `model_selection.py`

Move/adapt estimator/design matrix/safe metrics. Add `select_hyperparameters_temporal`, `refit_selected_model`, inner-fold records and deterministic ties. No new model families.

#### `calibration.py`

Add `Calibrator` protocol and `IdentityCalibrator` with role guard. Do not add Platt/isotonic/beta in Wave 0.

#### `policy.py`

Move cooldown/threshold mechanics. Add exhaustive points, budget mapping, selected policy, common-count thinning, inactivity reasons и clustering.

#### `random_baseline.py`

Move current DP without behavior change first. Add quota DP, `RandomDrawBank`, stable seeds, calendar/update-gap modes, MCSE и registry serialization.

#### `metrics.py`

Extract intervals, score/policy/frontier/regret metrics, inactive completion and explicit numerator/denominator aggregation.

#### `uncertainty.py`

Add master calendar, synchronized block indices, contribution resampling, paired comparison, leave-one-year-out and block sensitivity.

#### `artifacts.py`

Add schema constants, atomic writers, manifest builder, per-input hashes, dirty/diff metadata, dependency versions, artifact validation and compatibility checks.

#### `engine.py`

Implement v3 orchestration state machine from universe through persisted reports. Typed inputs; no hidden config globals.

### 9.2. Existing scripts

#### `scripts/run_experiment.py`

- keep canonical CLI;
- add `--evaluation-protocol`;
- dispatch v2/v3;
- load v3 config explicitly;
- refuse mixed protocols in one run;
- preserve current functions as deprecated v2 wrappers.

#### `scripts/run_backtest.py`

Keep CLI/reference behavior. Import/wrap count-only extracted implementations only after exact regression. Preserve signatures, seeds, outputs and paths.

#### `scripts/analyze_hypotheses.py`

Read versions before combining, reject cross-protocol comparison by default, load frontier/uncertainty, report paired effects and coverage, retain legacy warning.

#### `scripts/audit_pipeline.py`

Add universe, target-boundary, role, synchronization, score-coverage and version audits.

#### `scripts/evaluate_indicators.py` and `scripts/evaluate_fast_slow.py`

Keep current results legacy. Remove duplicated helpers only after v2 regression. Future v3 evaluation must be explicit.

#### `scripts/export_demo_signals.py`

Keep current schema support; add explicit v3 aliases and reject incompatible bundles rather than guessing.

### 9.3. Configs/specs

Keep `configs/validation.toml` unchanged for v2.

Add `configs/evaluation_v3.toml` with `[temporal]`, `[calibration]`, `[policy]`, `[random]`, `[bootstrap]` sections and all frozen values.

Add `hypotheses/H009_evaluation_v3.toml` referencing `message_hit`, h=3/e=50, current H008 baseline and `temporal_v3`. Это protocol validation run, не model improvement evidence.

### 9.4. Required v3 artifacts

```text
manifest.json
fold_boundaries.csv
eligible_universe.csv.gz
inner_selection_metrics.csv
model_fits.csv
calibration_metrics.csv
oot_scores.csv.gz
selected_policies.csv
policy_decisions.csv.gz
score_frontier.csv
policy_frontier.csv
model_metrics.csv
candidate_policy_metrics.csv
signal_policy_metrics.csv
corridor_year_metrics.csv
summary.csv
random_draw_metrics.csv.gz
random_draw_registry.json
uncertainty_summary.csv
paired_comparisons.csv
RESULTS.md
```

Optional `predictions.csv`/`fold_metrics.csv` are compatibility projections, not canonical v3 tables.

### 9.5. Documentation

После implementation update `PRODUCT_CONTRACT.md` только при semantic changes, а также `PROJECT_STRUCTURE.md`, `CURRENT_STATE.md`, `AGENTS.md` и backlog statuses.

---

## 10. Test plan

### 10.1. `tests/test_temporal_protocol_v3.py`

Tests exact outer-2022 boundaries, role disjointness, label-window purge, expanding folds, inner-fold counts, partial cutoff, corridor synchronization и atomic fold rejection.

### 10.2. `tests/test_evaluation_universe.py`

Tests unchanged-rate exclusion, no weekend decision rows, full-window exclusion, feature-NaN independence, same universe across models, horizon-sensitive hash, feature-insensitive hash, legacy parity, random eligibility и score-coverage failures.

### 10.3. `tests/test_policy_frontier.py`

Tests cooldown boundary, exhaustive thresholds, score-only budget mapping, outer-label independence, policy-label scope, no fallback, complete budget rows, infeasible budgets, count reconciliation, thinning determinism/cooldown и shared denominators.

### 10.4. `tests/test_random_baseline_v3.py`

Extend current DP tests: analytical uniformity on tiny universe, exact count/cooldown/quotas, month boundary, stable order-independent seeds, paired reuse, eligibility, calendar/update-gap matching, aggregation, MCSE and v2 fixture parity.

### 10.5. `tests/test_uncertainty.py`

Tests synchronized blocks across corridors/models, within-block order, year boundaries, partial handling, common shocks, identical-model zero deltas, known effects, paired draw IDs, no cooldown replay, deterministic block sensitivities, leave-one-year-out and inactive cells.

### 10.6. `tests/test_evaluation_leakage.py`

Mutation tests for calibration, policy and outer labels; future features/rates. Assert which downstream objects may change and which must remain byte-identical.

### 10.7. `tests/test_metrics_contract_v3.py`

Tests aggregate lift, partial/full views, inactive coverage, regret subsets/quantiles, frequency denominators, clustering, mandatory identity columns, duplicate rows and incompatible-protocol rejection.

### 10.8. Regression tests

Extend existing backtest/experiment/feature tests. Preserve v2 fixture outputs, CLI defaults and schema. Optional full H008 regression checks corrected 1.246/85.8%/0.40 within serialization tolerance. V3 is not expected to equal v2.

### 10.9. Integration test

`tests/test_wave0_integration.py` runs a small synthetic five-corridor panel through all stages and verifies artifacts, hashes, deterministic rerun, leakage invariants, complete rows and report-from-artifacts behavior.

### 10.10. Environment checks

```powershell
uv sync
uv run python scripts/build_dataset.py --help
uv run python scripts/run_backtest.py --help
uv run python scripts/run_experiment.py --help
uv run python -m unittest discover -s tests -v
```

Current inspection environment did not expose `uv` on `PATH`; Wave 0 acceptance must use the locked uv environment.

---

## 11. Migration strategy

### 11.1. Independent versions

```text
target_contract_version = 2
eligibility_version = 1
evaluation_protocol_version = "temporal_v3"
artifact_schema_version = 3
policy_version = 3
matched_random_version = 3
uncertainty_version = 1
```

### 11.2. H008 preservation

- Never overwrite H008 directories.
- Preserve `configs/validation.toml` and explicit v2 path.
- Freeze v2 seeds/threshold fallback.
- Keep `run_backtest.py` reference baseline.
- Add golden regression before extraction.
- Use wrappers before deleting duplicate bodies.

### 11.3. Legacy classification

- no schema: `legacy-v1`;
- current H008: `corrected-v2`;
- Wave 0: `canonical-v3`.

Cross-protocol comparison requires explicit override and must be descriptive, not causal model effect.

### 11.4. Canonical status

During transition old specs without protocol remain v2; v3 requires explicit declaration. После acceptance все H013+ specs обязаны declare v3. H008 remains corrected-v2 history.

### 11.5. Reproducibility metadata

Manifest includes input/output SHA-256, universe hashes, boundaries, configs, candidate order, RNG algorithm/seeds, dependencies, Git commit, dirty flag/diff hash, command and protocol versions. Dirty run may complete but has `canonical_eligible=false`.

---

## 12. Execution DAG

```text
W0.1 Freeze contracts/schema
  ├── W0.2 Eligible universe
  │     └── W0.5 Matched-random extraction/v3
  ├── W0.3 Temporal splitter v3
  │     ├── W0.4 Temporal model selection/refit
  │     └── W0.6 Calibration adapter
  └── W0.7 Metric schema

W0.4 + W0.6 + W0.7
  └── W0.8 Policy frontier and selected policy

W0.2 + W0.5 + W0.7 + W0.8
  └── W0.9 Synchronized uncertainty

W0.3…W0.9
  └── W0.10 Engine/CLI/artifact integration
        ├── W0.11 Legacy v2 regression
        ├── W0.12 Synthetic end-to-end tests
        └── W0.13 Canonical Wave 0 run

W0.13
  └── W0.14 Audit/report review
        └── W0.15 Freeze v3 contracts and update docs
```

| Task | Scope | Parallelism |
|---|---|---|
| W0.1 | contracts, schemas, config, manifest spec | first/sequential |
| W0.2 | universe extraction/audit/tests | parallel after W0.1 |
| W0.3 | temporal folds/purge/tests | parallel after W0.1 |
| W0.5 | sampler extraction, draw bank/strata | after universe contract |
| W0.7 | metrics/aggregation/schema tests | parallel after W0.1 |
| W0.4 | inner selection/refit | after W0.3 |
| W0.6 | identity calibrator/role guards | after W0.3 |
| W0.8 | policy/frontier/thinning | after W0.3 + W0.7 |
| W0.9 | bootstrap/paired comparison | after W0.5 + W0.7 + W0.8 |
| W0.10 | runner integration | after components |
| W0.11 | v2 regression | parallel with integration, before merge |
| W0.13 | full canonical run | after tests |
| W0.15 | freeze/docs | after artifact review |

Каждый coding agent получает один bounded component плюс tests. Ни один agent не переопределяет dates, universe, metric names или seeds самостоятельно.

---

## 13. Wave 0 acceptance criteria

Canonical command:

```powershell
uv run python scripts/run_experiment.py `
  --evaluation-protocol temporal_v3 `
  --hypotheses H009_evaluation_v3 `
  --models random_forest `
  --strategies pooled_with_corridor_thresholds `
  --run-id 2026XXXX_wave0_v3_baseline
```

### Temporal safety

- outer folds 2022–2026, 2026 explicitly partial;
- all role/purge assertions pass;
- test labels cannot affect fit/calibration/threshold/decision;
- all corridors share boundaries/exposure.

### Frozen scores and policy

- every eligible outer row has raw/calibrated score;
- identity calibration explicit;
- thresholds only from policy block;
- every budget has active/infeasible row;
- no outer threshold optimization;
- no silent constraint relaxation.

### Random baseline

- same universe IDs;
- exact corridor/fold/cooldown/month counts;
- deterministic order-independent draws;
- sensitivity modes present;
- aggregate MCSE `<=0.005` or run non-canonical.

### Frequency/downside

- shared exposure denominators;
- inactive cells/months explicit;
- clustering/cooldown metrics;
- mean/false-push/tail regret;
- unattainable budgets reported.

### Uncertainty

- 5000 synchronized 28-day replicates;
- 14/56-day sensitivity;
- paired deltas;
- full-only, partial-inclusive, worst-year and leave-one-year-out views;
- no p-value-only conclusion.

### Artifacts/reproducibility

- manifest/schema v3 validation;
- all hashes and protocol versions;
- deterministic numerical rerun;
- dirty canonical promotion rejected;
- incompatible protocols cannot mix.

### Tests/compatibility

- full uv suite and synthetic integration pass;
- v2 regression passes;
- optional H008 full regression stays within tolerance;
- no existing result directory overwritten.

Any failure blocks Wave 1.

---

## 14. Decisions that must be frozen before Wave 1

После Wave 0 acceptance H013+ agents не меняют без отдельного methodology proposal и нового protocol version:

1. `message_hit` v2 semantics для binary experiments.
2. Calendar-day horizon/forward-fill label semantics.
3. Eligibility rule и universe hashing.
4. Treatment of unchanged effective-date rates.
5. Conservative effective-date availability.
6. Outer folds и partial-2026 treatment.
7. Inner selection/expanding rules.
8. Purge inequality.
9. Minimum-history/fold validity.
10. Corridor synchronization/exposure.
11. Hyperparameter objective/ties.
12. Final refit cutoff.
13. Calibration block/interface.
14. Policy block allocation.
15. Identity calibration baseline.
16. Cooldown semantics.
17. Threshold enumeration.
18. Frequency grid and comparison region.
19. Policy objective/no-fallback rule.
20. Pre/post-cooldown metrics.
21. Thinning algorithm.
22. Primary matched-random construction.
23. Draw count/seeds/draw-bank contract.
24. Random sensitivity modes.
25. Aggregate formulas.
26. Bootstrap unit/block lengths.
27. Bootstrap replicates/paired fields.
28. Partial/full reporting views.
29. Metric classifications.
30. Inactive-cell handling.
31. Clustering definitions.
32. Downside definitions.
33. Artifact schemas.
34. Manifest compatibility rules.
35. Canonical comparison tables и baseline run ID.
36. Prohibition on treating legacy-v1/corrected-v2 comparison as a pure model change.

Wave 1 может заменить score/model/feature/target adapter, но проходит через frozen contracts и выдаёт ту же artifact/metric structure. Изменение measurement layer создаёт новый evaluation protocol, а не обычную model hypothesis.
