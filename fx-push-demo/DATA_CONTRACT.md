# Контракт ML → календарь демо

`scripts/export_demo_signals.py` является границей между меняющимся ML pipeline и
визуализацией. Frontend не читает внутренние CSV модели и не содержит имя
«лучшего» запуска. Он знает только публичный JSON-контракт schema version 1.

## Источник

Экспортёр читает `manifest.json` и `predictions.csv` выбранного experiment bundle.
Пять selectors (`hypothesis_id`, `model`, `strategy`, `horizon_days`,
`epsilon_bps`) должны однозначно задавать одну policy. Если selector не передан и
в файле есть несколько значений, CLI останавливается с ошибкой.

В JSON попадают только финальные строки `selected_signal=true`, то есть сигналы
после model threshold и cooldown. Обычный день календаря определяется отсутствием
такого сигнала. `coverage.decisionCount` сохраняет число всех проверенных OOT
решений, а `coverage.from/to` — границы доступного периода.

## Schema v1

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-09-05T00:00:00+00:00",
  "source": {
    "runId": "run_id",
    "datasetVersion": "fingerprint",
    "gitCommit": "commit",
    "hypothesisId": "H008_pooling_ablation",
    "model": "random_forest",
    "strategy": "pooled_with_corridor_thresholds",
    "horizonDays": 3,
    "epsilonBps": 50
  },
  "coverage": {
    "from": "2022-01-11",
    "to": "2026-08-29",
    "decisionCount": 5741,
    "signalCount": 466
  },
  "signals": [
    {
      "date": "2026-08-01",
      "corridor": "RUB_TJS",
      "countryCode": "TJ",
      "rateRubPerUnit": 8.59216,
      "score": 0.84,
      "threshold": 0.78,
      "signalType": "good_now",
      "signalSpeed": "fast",
      "candidate": true,
      "send": true,
      "reasonCode": "send",
      "priority": 0.06
    }
  ]
}
```

Календарь показывает последние три месяца относительно `coverage.to`. Если в один
день есть несколько коридоров, они сортируются по `score - threshold`, затем по
коду коридора. Сейчас интерфейс показывает один случайный mock-текст из трёх
существующих сценариев; тексты намеренно не являются частью schema v1. Позднее их
можно добавить отдельным versioned contract, не меняя механизм расписания.

Исторические `message_hit`, future regret и другие значения, известные только
после даты решения, в публичный JSON не экспортируются.
