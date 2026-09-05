# Структура ML-проекта

## Главный принцип

Единицей работы является не notebook и не файл модели, а **эксперимент по проверке гипотезы**.

```text
hypothesis_spec
      ↓
dataset_version + feature_set + target
      ↓
model_suite + hyperparameter_search
      ↓
nested walk-forward
      ↓
predictions + signals + metrics
      ↓
review notebook
      ↓
hypothesis_verdict
```

Notebook не должен сам очищать данные, создавать labels или обучать модель по собственной логике. Он получает уже сохранённый результат эксперимента, визуализирует его и помогает принять решение по гипотезе.

## Текущая структура каталогов

```text
itmophack/
├── AGENTS.md                     # контекст и правила работы AI-агентов
├── CURRENT_STATE.md              # основной flow, статусы и канонические результаты
├── PRODUCT_CONTRACT.md
├── PROJECT_STRUCTURE.md
├── README.md
├── pyproject.toml
├── configs/
│   ├── data.toml                 # валюты, горизонты, epsilon
│   ├── features.toml             # наборы признаков
│   ├── models.toml               # модели и сетки гиперпараметров
│   └── validation.toml           # walk-forward, cooldown, baseline
├── hypotheses/
│   ├── README.md
│   └── H001...H007.toml           # предзаданные ML-гипотезы
├── data/
│   ├── raw/                       # неизменяемые исходные DBF
│   ├── processed/                # observations и labels
│   └── exploration/              # одноразовые исследовательские выгрузки
├── scripts/
│   ├── build_dataset.py          # ingest, observations и labels
│   ├── run_backtest.py           # проверенный logistic baseline
│   ├── run_experiment.py         # единый configurable experiment runner
│   ├── audit_pipeline.py         # leakage и data-quality checks
│   ├── evaluate_*.py             # product-policy эксперименты
│   ├── analyze_hypotheses.py     # итоговые таблицы, тесты и графики
│   └── show_signal_as_of.py      # чтение сохранённого OOT-сигнала
├── experiments/
│   └── README.md                 # правила запуска и хранения результатов
├── notebooks/
│   ├── 00_data_pipeline_audit.ipynb
│   ├── 01_model_benchmark.ipynb
│   ├── 02_hypotheses_and_sensitivity.ipynb
│   ├── exploration/              # ранний EDA, не source of truth
│   └── README.md                 # правила review-notebook
├── results/
│   ├── backtest/                 # утверждённый logistic baseline
│   ├── experiments/              # immutable experiment bundles
│   └── hypothesis_study/         # итоговый анализ и отчёт
├── deliverables/presentation/    # финальные PPTX/PDF и исходная версия
├── docs/archive/                 # устаревшие материалы
└── tests/
    └── test_*.py                 # labels, features, cooldown и baseline
```

Фактические результаты полного исследования лежат в
`results/experiments/20260904_*`. Каталог `results/hypothesis_study/` содержит
сводные таблицы, статистические тесты, графики и итоговый Markdown-отчёт.

Исполняемая логика пока сосредоточена в `scripts/`: скрипты импортируют функции
друг друга через каталог `scripts`. Переезд в пакет `src/cis_trading/` остаётся
следующим этапом и должен выполняться постепенно, с сохранением CLI и тестов.

## Объекты системы

### 1. Гипотеза

Гипотеза отвечает на вопрос «какой рыночный паттерн должен улучшить качество сигнала?».

```text
hypothesis_id
statement
feature_sets
target
corridors
horizons
model_suite
acceptance_criteria
status
```

Гипотеза не содержит обученную модель. Она только задаёт эксперимент.

### 2. Dataset version

Одна версия dataset определяется комбинацией:

```text
исходные файлы
версия кода очистки
правило времени доступности
epsilon
горизонты labels
версия feature pipeline
```

Каждый эксперимент сохраняет `dataset_version`, чтобы результат можно было повторить.

### 3. Feature set

Признаки объединяются в именованные группы:

```text
price_core       — returns, level, range position
momentum         — тренд и последовательности движения
reversal         — отскок от прошлого минимума
volatility       — rolling volatility и ширина диапазона
calendar         — месяц, день недели, праздники
cross_currency   — USD/EUR/CNY факторы
```

Гипотеза выбирает группы, а не вручную перечисляет колонки внутри notebook.

### 4. Model config

Model config описывает класс модели и пространство гиперпараметров, но не хранит данные и результат.

Стартовый benchmark:

```text
dummy/random baseline
logistic regression
CatBoost
random forest
SVM
KNN
Gaussian naive Bayes
```

Логистическая регрессия остаётся интерпретируемым baseline. Остальные модели
проверяют, дают ли нелинейности и локальная структура дополнительный OOT-эффект.
Победителя выбираем по lift и устойчивости, а не по train score.

### 5. Experiment run

Один запуск получает:

```text
hypothesis_id
dataset_version
feature_set
model_config
walk_forward_config
random_seed
```

И сохраняет:

```text
manifest.json
fold_metrics.csv
summary.csv
model_metrics.csv
candidate_policy_metrics.csv
signal_policy_metrics.csv
predictions.csv
signals.csv
thresholds.csv
validation_policy_tradeoffs.csv
models/<fold_id>.joblib
```

### 6. Hypothesis verdict

Notebook или отчёт возвращает решение:

```text
accepted   — работает устойчиво;
rejected   — не превосходит baseline;
limited    — работает только на части коридоров/режимов;
inconclusive — недостаточно наблюдений.
```

## Как организовать обучение моделей

### Внешний walk-forward

Нужен для честной итоговой оценки:

```text
Fold 1: train до 2020 → validation 2021 → test 2022
Fold 2: train до 2021 → validation 2022 → test 2023
Fold 3: train до 2022 → validation 2023 → test 2024
...
```

### Что происходит внутри каждого fold

```text
TRAIN
  ├── fit preprocessing
  ├── fit нескольких hyperparameter candidates
  └── получить кандидаты моделей

VALIDATION
  ├── выбрать hyperparameters
  ├── выбрать threshold
  └── проверить frequency/cooldown

TEST
  └── один раз посчитать финальные OOT-метрики
```

Нельзя выбирать гиперпараметры по test-year. Иначе walk-forward формально есть, но оценка всё равно подогнана.

### После выбора подхода

Для демонстрационного `signal_as_of` обучается отдельная final model:

```text
model family и hyperparameters уже выбраны walk-forward
                         ↓
fit на всей доступной истории до cutoff
                         ↓
threshold калибруется на последнем выделенном периоде
                         ↓
сохраняются model + preprocessing + threshold + metadata
```

Backtest-модели по folds и final model — разные артефакты. Нельзя подменять результаты backtest метриками final model на её train-истории.

## Одна модель на разные коридоры

Да, это имеет смысл проверять. Данных по одному коридору мало, а движения валют имеют общие RUB-факторы.

Нужно сравнить три стратегии:

### A. Отдельная модель на каждый коридор

```text
RUB_TJS → model_TJS
RUB_UZS → model_UZS
...
```

Плюсы: учитывает специфику валюты. Минусы: мало данных и высокий риск переобучения.

### B. Pooled-модель

```text
все коридоры → одна model
```

В признаки добавляется `corridor` через one-hot encoding. Временной split общий: строки одной даты из разных коридоров должны находиться в одной части fold.

Плюсы: больше наблюдений и единая переносимая логика. Минусы: модель может скрыть различия коридоров.

### C. Pooled-модель + пороги по коридорам

```text
одна модель вероятности
       +
отдельный threshold/cooldown для каждого коридора
```

Это основной рекомендуемый кандидат: общая модель изучает рыночные зависимости, а политика отправки учитывает разную базовую частоту событий.

### D. Диагностика pooling

`H008_pooling_ablation` дополнительно разделяет два эффекта:

- `pooled_without_corridor_feature` проверяет общие закономерности без подсказки,
  к какой валюте относится строка;
- `pooled` использует признак коридора, но один threshold для всех валют.

Эти варианты нужны для анализа. Они не считаются автоматически более подходящими
для продукта только из-за более высокого среднего lift: отдельно проверяются
покрытие валют и лет, false-push rate и отсутствие периодов без сигналов.

### Честное сравнение

Все три стратегии должны получать:

- одинаковые feature sets;
- одинаковые временные test-folds;
- одинаковое определение `message_hit`;
- одинаковый random baseline;
- метрики отдельно по каждому коридору.

Нельзя считать строки пяти коридоров полностью независимыми наблюдениями: в один день ими движут общие RUB-факторы.

## Как использовать notebook для гипотезы

Для каждой важной гипотезы можно иметь review-notebook:

```text
notebooks/H002_combined_factors_review.ipynb
```

Рекомендуемые ячейки:

1. Загрузить `hypothesis_spec`.
2. Загрузить `manifest.json` выполненного эксперимента.
3. Проверить версии dataset, features и модели.
4. Показать распределение target по коридорам/folds.
5. Показать baseline → single indicators → models.
6. Показать uplift и bps по коридорам и годам.
7. Показать частоту и кучность после cooldown.
8. Показать ошибки на временном графике.
9. Показать feature importance/coefficients.
10. Записать verdict и ограничения.

Notebook **не должен**:

- строить собственную альтернативную разметку;
- делать случайный train/test split;
- подбирать параметры по test;
- содержать единственную копию важной функции;
- перезаписывать утверждённые результаты автоматически.

## Текущий единый runner

Рабочий интерфейс:

```text
uv run python scripts/run_experiment.py `
  --hypotheses H002_combined_factors `
  --strategies pooled_with_corridor_thresholds `
  --models logistic,hist_gradient_boosting
```

Runner сейчас:

1. загрузить hypothesis spec;
2. загрузить заранее собранный dataset;
3. выбрать feature groups;
4. сформировать walk-forward folds;
5. обучить все model candidates внутри каждого fold;
6. выбрать hyperparameters и threshold на validation;
7. получить OOT predictions;
8. применить cooldown;
9. посчитать matched random baseline и метрики;
10. сохранить полный experiment bundle.

Сборка dataset остаётся отдельным явным шагом через `scripts/build_dataset.py`.
Краткая карта актуальных и вспомогательных частей находится в
`CURRENT_STATE.md`.

## Граница текущей реализации

### Оставить сейчас

- `scripts/build_dataset.py` как рабочую сборку данных;
- `scripts/run_backtest.py` как проверенный baseline;
- существующие CSV в `results/backtest/` как версию текущего результата;
- тесты, фиксирующие labels, cooldown и random baseline.

### Следующий безопасный рефакторинг

1. Вынести `add_features` из `run_backtest.py` в `src/cis_trading/features/market.py`.
2. Вынести `LogisticModel` и новые sklearn-модели в `src/cis_trading/models/`.
3. Вынести split, threshold и random baseline в отдельные модули.
4. Перевести существующие scripts на общие модули без изменения CLI.
5. Только затем удалять дублирование старого baseline-кода.

Не нужно сначала переносить все файлы, а потом пытаться восстановить рабочий backtest. Каждый шаг должен сохранять прохождение тестов и текущие результаты.
