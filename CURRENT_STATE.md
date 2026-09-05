# Текущее состояние CIS Trading

Этот файл — короткая карта репозитория: что является основным pipeline, что
сохранено как baseline, какие исследования уже завершены и чего в проекте пока
нет. Продуктовая семантика по-прежнему определяется `PRODUCT_CONTRACT.md`, а
детальная архитектура — `PROJECT_STRUCTURE.md`.

## Основной pipeline

```text
data/raw/*.dbf
  -> scripts/build_dataset.py
  -> data/processed/{observations,labels}.csv
  -> scripts/audit_pipeline.py
  -> hypotheses/*.toml + configs/*.toml
  -> scripts/run_experiment.py
  -> results/experiments/<run_id>/
  -> scripts/analyze_hypotheses.py
  -> results/hypothesis_study/HYPOTHESIS_REPORT.md
```

Именно `scripts/run_experiment.py` — основной runner для дальнейшего развития
моделей, feature sets и стратегий pooled/per-corridor.

Новые experiment bundles разделяют результаты на `model_metrics.csv`,
`candidate_policy_metrics.csv` и `signal_policy_metrics.csv`. Объединённый
`fold_metrics.csv` сохраняется для совместимости.

## Роли существующих файлов

| Объект | Роль | Нужно развивать дальше |
|---|---|---|
| `scripts/build_dataset.py` | основная сборка observations и labels | да |
| `scripts/audit_pipeline.py` | обязательный аудит данных и leakage | да |
| `scripts/run_experiment.py` | основной configurable experiment runner | да |
| `scripts/analyze_hypotheses.py` | единая агрегация результатов и статтесты | да |
| `scripts/run_backtest.py` | зафиксированный logistic reference baseline | только сохранять совместимость |
| `scripts/evaluate_indicators.py` | завершённое исследование простых правил | нет, пока не появится новая гипотеза |
| `scripts/evaluate_fast_slow.py` | завершённое исследование подтверждения сигнала | нет, пока не появится новая policy |
| `scripts/show_signal_as_of.py` | просмотр сохранённого OOT-сигнала | не является live inference |
| `notebooks/00..02` | review готовых артефактов | не переносить сюда pipeline-логику |
| `notebooks/exploration/` | ранний EDA | архивный исследовательский контекст |
| `deliverables/` | пользовательские материалы | не источник ML-логики |

## Текущая рабочая постановка

- Основной target: `message_hit`.
- Рабочий режим MVP: `h=3`, `epsilon=50 bp`, cooldown 4 календарных дня.
- Главная метрика: lift относительно случайного расписания с тем же числом
  сигналов и cooldown.
- Основной feature baseline: `H002_combined_factors`.
- Практический model candidate: random forest, pooled-модель с отдельными
  порогами по коридорам.
- Статус кандидата: перспективный, но не принятый — строгая устойчивость и
  статистическая значимость пока не подтверждены.

H002 как feature baseline и random forest из H007 benchmark пока не образуют
утверждённую единую конфигурацию. Их нужно сопоставить в одном factorial
эксперименте.

Текущие числа нужно брать только из:

1. `results/hypothesis_study/HYPOTHESIS_REPORT.md` — общий benchmark, гипотезы и
   статистические проверки;
2. `results/backtest/RESULTS.md` — зафиксированный logistic baseline.

Остальные Markdown-файлы внутри `results/experiments/` относятся к конкретным
историческим срезам и не являются главным отчётом.

## Статус ML-гипотез

TOML-файлы сохраняют предзаданные спецификации экспериментов. Таблица ниже
отражает текущий исследовательский вывод и не переписывает спецификацию задним
числом.

| Гипотеза | Текущий вывод | Роль дальше |
|---|---|---|
| H001 price core | недостаточно качества | нижний feature baseline |
| H002 combined factors | перспективно, но не подтверждено | основной feature baseline |
| H003 volatility | устойчивого отдельного улучшения нет | завершённое ablation |
| H004 momentum | устойчивого отдельного улучшения нет | завершённое ablation |
| H005 calendar | эффект нестабилен | завершённое ablation |
| H006 derivatives/reversal | улучшение не подтверждено | не включать по умолчанию без нового evidence |
| H007 USD/EUR | результат неустойчив | исследовать только в парном benchmark |
| H008 pooling | pooling помогает RF и CatBoost, но критерий lift 1.3 не достигнут | продолжить через калибровку и более устойчивую validation |

## Канонические результаты

| Каталог | Что содержит |
|---|---|
| `results/backtest/` | reference logistic baseline и product-policy studies |
| `results/experiments/20260904_model_benchmark/` | основной model benchmark |
| `results/experiments/20260904_feature_ablation/` | сравнение feature sets |
| `results/experiments/20260904_h_epsilon_sensitivity/` | sensitivity по horizon/epsilon |
| `results/experiments/20260904_h008_pooling_v2_rf_logistic/` | RF/logistic benchmark с corrected matched-random и разложением pooling |
| `results/experiments/20260905_h008_pooling_v2_catboost/` | CatBoost companion-run для H008 |
| `results/hypothesis_study/` | единый сводный отчёт, тесты и графики |

Каталоги `results/experiments/20260904_h3_*` и `smoke_h007` — промежуточные либо
узкие запуски. Они сохраняются для истории, но не определяют текущее решение.

## Что пока не реализовано

- Нет принятой production-модели.
- Нет final fit на всей доступной истории и model registry.
- Нет live inference: `show_signal_as_of.py` только читает сохранённые сигналы.
- Нет исторического банковского курса и продуктовых event logs.
- Нет доказанной калибровки model score как вероятности.
- Нет полноценного локального объяснения сигнала для random forest.

## Ближайший технический приоритет

Основной runner уже разделяет model, candidate-policy и signal-policy metrics,
учитывает inactive folds в coverage и календарной частоте, сохраняет validation
threshold frontier и использует matched-random при выборе threshold. Парные
проверки model score отделены от условного сравнения lift на common-active
периодах.

Существующие canonical results были созданы до этой схемы и намеренно не
перезаписаны. H008 на той же постановке дал для pooled Random Forest с отдельными
порогами общий lift 1.246, hit rate 85.8% и 0.40 сигнала в неделю. Он лучше пяти
отдельных Random Forest во всех пяти test-years, но не достигает критерия 1.3.
Старое значение lift 1.42 нельзя напрямую переносить на corrected random baseline.

Следующие шаги:

1. выполнить полный тестовый прогон в `uv`-окружении;
2. проверить time-safe calibration RF;
3. разделить выбор hyperparameters и threshold по разным временным validation-блокам;
4. повторить H002/H006/H007 на одинаковых Logistic, CatBoost и Random Forest;
5. пересоздать canonical experiment bundles из чистого Git-состояния;
6. только после проверки явно заменить ссылки на canonical runs.

Большой перенос файлов в `src/` следует делать после этих исправлений. До этого
сохраняются существующие CLI и пути к утверждённым артефактам.
