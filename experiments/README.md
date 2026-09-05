# Experiment outputs

Основной runner — `scripts/run_experiment.py`. Роль канонических и промежуточных
запусков описана в `CURRENT_STATE.md`; имя каталога само по себе не означает, что
результат принят как текущая модель.

Каждый запуск получает уникальный `experiment_id` и создаёт отдельный каталог:

```text
results/experiments/<experiment_id>/
├── manifest.json
├── fold_metrics.csv
├── summary.csv
├── model_metrics.csv
├── candidate_policy_metrics.csv
├── signal_policy_metrics.csv
├── predictions.csv
├── signals.csv
├── thresholds.csv
├── validation_policy_tradeoffs.csv
└── models/                       # только при --save-models
    └── <fold_id>.joblib
```

`manifest.json` обязан содержать hypothesis id, dataset version, feature sets, model config, validation config, random seed, git commit и время запуска.

`fold_metrics.csv` сохраняется как совместимая объединённая таблица. Для анализа
нужно предпочитать разделённые таблицы: качество ML score, threshold policy и
delivery policy после cooldown.

Эксперимент нельзя перезаписывать. Повторный запуск создаёт новый id.

Основные сохранённые исследования:

- `20260904_model_benchmark` — сравнение model families;
- `20260904_feature_ablation` — сравнение feature sets;
- `20260904_h_epsilon_sensitivity` — sensitivity;
- `20260904_h008_pooling_v2_rf_logistic` — controlled pooling ablation на новой
  схеме метрик и corrected matched-random baseline;
- `20260904_h3_*` и `smoke_h007` — промежуточные или узкие запуски.

