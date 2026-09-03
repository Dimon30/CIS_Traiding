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

## Целевая структура каталогов

```text
CIS_Traiding/
│
├── PRODUCT_CONTRACT.md
├── PROJECT_STRUCTURE.md
├── README.md
├── pyproject.toml
│
├── configs/
│   ├── data.toml                 # валюты, горизонты, epsilon
│   ├── features.toml             # наборы признаков
│   ├── models.toml               # модели и сетки гиперпараметров
│   └── validation.toml           # walk-forward, cooldown, baseline
│
├── hypotheses/
│   ├── README.md
│   └── H002_combined_factors.toml
│
├── data/
│   ├── *.dbf                     # сырые открытые данные
│   └── processed/                # observations и labels
│
├── src/cis_trading/
│   ├── data/                     # ingest, validate, availability
│   ├── features/                 # функции расчёта признаков
│   ├── labels/                   # message_hit и benefit_bps
│   ├── validation/               # walk-forward и purge gap
│   ├── models/                   # registry, fit, predict, persistence
│   ├── evaluation/               # baseline и метрики
│   └── inference/                # signal_as_of
│
├── scripts/
│   ├── build_dataset.py          # существующая точка сборки данных
│   ├── run_backtest.py           # существующий walk-forward
│   ├── run_experiment.py         # будущая единая точка эксперимента
│   └── show_signal_as_of.py
│
├── experiments/
│   └── README.md                 # правила запуска и хранения результатов
│
├── artifacts/
│   ├── datasets/                 # версии feature/label table
│   ├── experiments/              # predictions, metrics, manifests
│   └── models/                   # fitted model каждого fold
│
├── notebooks/
│   └── README.md                 # шаблон review-notebook
│
├── results/
│   └── backtest/                 # утверждённые результаты для защиты
│
└── tests/
    ├── test_build_dataset.py
    ├── test_features.py
    ├── test_walk_forward.py
    ├── test_models.py
    └── test_inference.py
```

Переезжать в `src/` нужно постепенно. Существующие рабочие скрипты не следует ломать перед сдачей.

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

Минимальный набор:

```text
dummy/random baseline
logistic regression
histogram gradient boosting
```

Сначала проверяется LogReg. Boosting нужен только для ответа на вопрос, дают ли нелинейности дополнительный OOT-эффект.

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
predictions.csv
signals.csv
thresholds.csv
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

## Команда будущего единого запуска

Целевой интерфейс:

```text
python scripts/run_experiment.py \
  --hypothesis H002_combined_factors \
  --strategy pooled_with_corridor_thresholds \
  --models logistic,hist_gradient_boosting
```

Runner должен сам:

1. загрузить hypothesis spec;
2. собрать нужный dataset;
3. выбрать feature groups;
4. сформировать walk-forward folds;
5. обучить все model candidates внутри каждого fold;
6. выбрать hyperparameters и threshold на validation;
7. получить OOT predictions;
8. применить cooldown;
9. посчитать matched random baseline и метрики;
10. сохранить полный experiment bundle.

## Что делать с текущим кодом

### Оставить сейчас

- `scripts/build_dataset.py` как рабочую сборку данных;
- `scripts/run_backtest.py` как проверенный baseline;
- существующие CSV в `results/backtest/` как версию текущего результата;
- тесты, фиксирующие labels, cooldown и random baseline.

### Следующий безопасный рефакторинг

1. Вынести `add_features` из `run_backtest.py` в `src/cis_trading/features/market.py`.
2. Вынести `LogisticModel` и новые sklearn-модели в `src/cis_trading/models/`.
3. Вынести split, threshold и random baseline в отдельные модули.
4. Сделать `run_experiment.py`, который читает TOML-конфиги.
5. После этого перевести существующие scripts на новые модули.
6. Только затем удалять дублирование старого кода.

Не нужно сначала переносить все файлы, а потом пытаться восстановить рабочий backtest. Каждый шаг должен сохранять прохождение тестов и текущие результаты.

