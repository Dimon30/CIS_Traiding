# CIS Trading: 10-дневная ML-программа

## Цель и границы

За 10 рабочих дней получить один воспроизводимый вывод: есть ли кандидат, который
под замороженным протоколом `temporal_v3` устойчиво превосходит matched-random и
текущий pooled Random Forest baseline.

В программу входят только:

1. фиксация Wave 0;
2. контроль Random Forest против CatBoost;
3. одна компактная абляция структурных FX-признаков;
4. итоговый ML-отчёт.

Программа не меняет target, split, cooldown, matched-random, policy selection или
версию evaluation protocol. `future_regret_bps` используется как готовая метрика.
Отрицательный или неопределённый результат считается полноценным завершением.

## Дни 1–2: заморозить Wave 0

Canonical run: `20260905_wave0_temporal_v3_baseline`.

- `h=3`, `epsilon=50 bp`;
- pooled Random Forest;
- corridor-specific thresholds;
- feature set `full_market_with_fx`;
- 2000 matched-random draws;
- 5000 synchronized bootstrap replicates.

Перед запуском выполняются targeted tests и полный `unittest discover`. Финальный
run выполняется из чистого Git worktree на проверенном commit. Wave 0 принимается,
только если `audit_evaluation_v3.py` проходит, aggregate MCSE не выше 0.005, все
policy cells материализованы и manifest содержит `canonical_eligible=true`.

Если протокол нельзя закрыть за два дня, новые эксперименты прекращаются и итогом
становится `EVALUATION_BLOCKED` с точным описанием блокера.

## Дни 3–4: CatBoost model-control

Гипотеза: `hypotheses/H013_temporal_v3_model_control.toml`.

CatBoost использует те же target, features, corridors, strategy и eligible
universe. После smoke-run выполняется один полный run и сравнение с RF через
`compare_evaluation_v3.py`.

CatBoost заменяет RF только при одновременном выполнении условий:

- paired bootstrap `P(delta_hit_rate > 0) >= 0.90`;
- `P(delta_mean_regret < 0) >= 0.80`;
- common-count frontier лучше в большинстве активных точек диапазона
  0.25–1.25 сигнала в неделю;
- потеря покрытия не больше двух corridor/year cells;
- ни один полный outer year не остаётся без сигналов.

При неоднозначном результате сохраняется RF. Logistic повторно не запускается:
исправленный H008 уже показал, что она не является конкурентом RF.

## Дни 5–8: H015 compact FX decomposition

Гипотеза: `hypotheses/H015_compact_fx_decomposition.toml`.

Поверх победившей модели добавляется только point-in-time decomposition:

```text
implied_usd_per_lcy = rub_per_lcy / rub_per_usd
```

USD присоединяется backward-as-of. На календаре обновлений коридора рассчитываются
implied returns за 1, 5 и 20 обновлений, rolling volatility за 20 обновлений и
range position за 60 обновлений. PCA, common factor, interactions, event-clock и
расширенный normalized feature zoo не выполняются.

После smoke-run выполняется один полный run на выбранной модели. H015 сравнивается
только с exact model baseline на том же eligible-universe ID и принимается, если:

- leakage/audit проверки проходят;
- `P(delta_hit_rate > 0) >= 0.90`;
- `P(delta_mean_regret < 0) >= 0.80`;
- знак улучшения положителен минимум в трёх из четырёх полных outer years;
- нет полного года без сигналов;
- active-cell coverage уменьшается не больше чем на два cells.

При провале любого gate сохраняется исходный feature stack. Вторая модель на H015
не запускается.

## Дни 9–10: итоговый вывод

Каталог `results/ten_day_model_program/` содержит:

- `FINAL_RESULTS.md` — RF, CatBoost, H015, frontier, uncertainty, regret,
  coverage и отрицательные результаты;
- `DECISION.json` — выбранный run ID, model, feature set, status и причины;
- machine-readable paired comparisons совместимой v3-схемы.

Статус выбирается однозначно:

- `OFFLINE_CRITERION_MET`: aggregate lift не ниже 1.3, lift не ниже 1.3 во всех
  четырёх полных outer years, активны несколько коридоров и bootstrap
  `P(lift >= 1.3) >= 0.95`;
- `PROMISING_NOT_PROVEN`: aggregate lift не ниже 1.3, но не пройден temporal или
  uncertainty gate;
- `CRITERION_NOT_MET`: aggregate lift ниже 1.3;
- `EVALUATION_BLOCKED`: canonical audit или воспроизводимость не закрыты.

После публикации решения программа останавливается независимо от результата.

## Интерфейсы и проверки

- Публичные CLI сохраняются; новые варианты задаются через H013/H015 TOML и
  feature config.
- Изменения labels, cooldown, random baseline, split и policy-selection запрещены.
- Проверяются формула implied USD/LCY, causal backward-as-of, неизменность
  существующих feature values, общий universe ID, audit smoke bundle и отказ
  сравнения несовместимых протоколов.
- Утверждённые результаты не перезаписываются; каждый run получает новый ID.
- `fx-push-demo` и несвязанные пользовательские изменения не входят в commits.

## Deferred backlog

До нового решения человека не выполнять: calibration; rolling/decay history;
severity-weighted, quantile, ordinal и survival targets; pooling/residual heads;
ensembles; новый policy search; CNY, RUONIA, нефть, macro/remittances; conformal
uncertainty; frontend, live inference, объяснения и банковский pilot.
