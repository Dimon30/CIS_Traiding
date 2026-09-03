# Experiment outputs

Каждый запуск получает уникальный `experiment_id` и создаёт отдельный каталог:

```text
artifacts/experiments/<experiment_id>/
├── manifest.json
├── fold_metrics.csv
├── summary.csv
├── predictions.csv
├── signals.csv
├── thresholds.csv
└── models/
    └── <fold_id>.joblib
```

`manifest.json` обязан содержать hypothesis id, dataset version, feature sets, model config, validation config, random seed, git commit и время запуска.

Эксперимент нельзя перезаписывать. Повторный запуск создаёт новый id.

