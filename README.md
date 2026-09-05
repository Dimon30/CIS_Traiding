# CIS Trading

Сервис объяснимых уведомлений о выгодном моменте для трансграничного перевода из России в страны СНГ. Проект создаётся для хакатонного кейса Альфа-Банка.

Система следит за динамикой валютного курса вместо клиента и формирует редкий сигнал, когда текущий момент статистически заметно лучше обычного. Это не прогноз курса, не инвестиционная рекомендация и не обещание абсолютного минимума.

## Документация

Начинать знакомство с проектом нужно с [CURRENT_STATE.md](CURRENT_STATE.md): там
указаны основной pipeline, роль каждого скрипта, канонические результаты и
ближайший технический приоритет.

Навигация по документации:

1. [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md) — продукт, target и критерии качества;
2. [CURRENT_STATE.md](CURRENT_STATE.md) — что является текущим, завершённым и планируемым;
3. [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) — подробная экспериментальная архитектура.

Организация гипотез, feature sets, моделей, walk-forward экспериментов и review-notebooks описана в [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

В нём зафиксированы:

- пользователь, проблема и границы MVP;
- математическое определение выгодного момента;
- параметры разметки и политика ошибок;
- метрики, схема walk-forward-валидации и критерии приёмки;
- контракт результата модели и правила отправки пушей;
- принятые решения, эксперименты, риски и открытые вопросы;
- конкретная постановка для двух AI-инженеров.

Если реализация, презентация или устная договорённость расходится с этим документом, команда сначала обновляет контракт, а затем код.

## Структура репозитория

```text
.
├── AGENTS.md             # быстрый технический контекст для AI-агентов
├── CURRENT_STATE.md      # единая карта текущего состояния и основного pipeline
├── PRODUCT_CONTRACT.md   # единственный источник продуктовых и ML-требований
├── PROJECT_STRUCTURE.md  # архитектура экспериментов и границы модулей
├── configs/              # data, features, models и validation в TOML
├── data/
│   ├── raw/              # неизменяемые исходные DBF
│   ├── processed/        # воспроизводимые observations и labels
│   └── exploration/      # исследовательские выгрузки, не входящие в pipeline
├── hypotheses/           # реестр проверяемых ML-гипотез
├── scripts/              # исполняемый pipeline и CLI-точки входа
├── tests/                # unit-тесты разметки, признаков и signal policy
├── notebooks/            # review-notebooks и отдельная exploration-зона
├── results/              # зафиксированные backtest/experiment/research outputs
├── deliverables/         # финальные PDF/PPTX и исходник презентации
└── docs/archive/         # устаревшие материалы, не являющиеся source of truth
```

Команды запускаются из корня репозитория. Временные рендеры и промежуточные
файлы создавайте в `tmp/`: каталог игнорируется Git.

## Текущий приоритет

Новая схема оценки разделяет качество ML score, threshold policy и delivery
policy после cooldown. Ближайший шаг — проверить её новым smoke run и повторить
сопоставимый benchmark feature sets × model families. Текущий random forest —
кандидат, а не принятая финальная модель. Подробный статус зафиксирован в
[CURRENT_STATE.md](CURRENT_STATE.md).

## Окружение

Проект зафиксирован в `pyproject.toml` и `uv.lock` для Python 3.14+:

```powershell
uv sync
uv run python -m unittest discover -s tests -v
```

## Подготовка датасетов

Один запуск создаёт наблюдения и разметку для TJS, UZS, KGS, AMD и KZT на горизонтах 1, 3, 5, 10 и 20 календарных дней:

```powershell
uv run python scripts/build_dataset.py --all-currencies
```

USD и EUR используются только как point-in-time признаки. Для них не нужны
future labels:

```powershell
uv run python scripts/build_dataset.py --currencies USD,EUR --observations-only
uv run python scripts/audit_pipeline.py
```

Для проверки чувствительности к определению правдивого сообщения:

```powershell
uv run python scripts/build_dataset.py --all-currencies --epsilon 0
uv run python scripts/build_dataset.py --all-currencies --epsilon 0.01
```

Для одного коридора или горизонта доступны совместимые параметры:

```powershell
uv run python scripts/build_dataset.py --currency TJS --horizon 5
uv run python scripts/build_dataset.py --currency TJS --horizons 1,3,5
```

Файлы разделены по назначению:

- `rub_<currency>_observations.csv` — только информация, доступная модели на дату расчёта;
- `rub_<currency>_labels_h<horizon>_e50bp.csv` — будущие outcomes для обучения и проверки.

`message_hit=1` означает, что ожидание в пределах горизонта не дало курс выгоднее более чем на 0,5%. `target_good_now` оставлен как вспомогательная метка положения курса в окне `±h`.

## Reference baseline

Это зафиксированный logistic baseline для контроля совместимости и исторического
сравнения. Новые модели и feature-гипотезы нужно запускать через
`scripts/run_experiment.py`.

```powershell
uv run python scripts/run_backtest.py
```

## Основной experiment pipeline

Главный runner поддерживает семь классификаторов: Logistic Regression,
HistGradientBoosting, CatBoost, Random Forest, SVM, KNN и Gaussian Naive Bayes.
Основной сохранённый benchmark сравнивает шесть из них без HistGradientBoosting.
Основные режимы:

- `per_corridor` — отдельная модель и порог для каждого направления;
- `pooled_with_corridor_thresholds` — одна модель на все направления и отдельная
  калибровка порога на validation для каждого направления;
- `pooled_without_corridor_feature` — диагностический вариант общей модели без
  признака валюты, но с отдельными порогами;
- `pooled` — общая модель с признаком валюты и единым порогом.

Год `T-1` служит validation, год `T` — test, вся более ранняя история — expanding
train. Перед validation и test стоит purge gap длиной `h`, поэтому future label
обучающей строки не пересекает следующий период.

```powershell
# Benchmark моделей на основном h=3, epsilon=50 bp
uv run python scripts/run_experiment.py `
  --hypotheses H007_add_usd_eur `
  --horizons 3 --epsilon-bps 50 `
  --models logistic,catboost,random_forest,svm,knn,naive_bayes `
  --strategies per_corridor,pooled_with_corridor_thresholds `
  --run-id 20260904_model_benchmark

# Ablation: price → факторы кейса → производные → USD/EUR
uv run python scripts/run_experiment.py `
  --hypotheses H001_price_core,H002_combined_factors,H006_add_derivatives,H007_add_usd_eur `
  --horizons 3 --epsilon-bps 50 --models logistic `
  --strategies per_corridor,pooled_with_corridor_thresholds `
  --run-id 20260904_feature_ablation

# Чувствительность к h и epsilon
uv run python scripts/run_experiment.py `
  --hypotheses H007_add_usd_eur `
  --horizons 1,3,5,10,20 --epsilon-bps 0,50,100 `
  --models logistic `
  --strategies per_corridor,pooled_with_corridor_thresholds `
  --run-id 20260904_h_epsilon_sensitivity

uv run python scripts/analyze_hypotheses.py
```

Контролируемое сравнение способов объединения валют задаёт
`hypotheses/H008_pooling_ablation.toml`. Его первый v2-run сохранён в
`results/experiments/20260904_h008_pooling_v2_rf_logistic/`.

Итоговый человекочитаемый отчёт: `results/hypothesis_study/HYPOTHESIS_REPORT.md`.
Рядом лежат statistical tests, model ranking, sensitivity table и графики.

Backtest:

- обучает L2-логистическую регрессию на `message_hit`;
- использует только прошлые данные и отдельный предыдущий год для threshold;
- исключает повторные неизменившиеся курсы из доступных дат отправки;
- применяет cooldown 4 календарных дня;
- сравнивает сигнал с 300+ случайными расписаниями того же размера и с тем же cooldown;
- сохраняет результаты по каждому временному фолду и каждой паре коридор/горизонт.

Основные артефакты:

- `results/backtest/walk_forward_folds.csv` — честные результаты каждого фолда;
- `results/backtest/summary_by_corridor_horizon.csv` — сводка устойчивости;
- `results/backtest/validation_threshold_tradeoffs.csv` — связь threshold, качества и частоты;
- `results/backtest/signals.csv` — отправленные после cooldown сигналы;
- `results/backtest/run_metadata.json` — точные допущения запуска.

Текущий лучший кандидат — RUB→TJS на горизонте 3 дня: совокупный lift 1,36, signal hit rate 86,3%, 0,59 сигнала в неделю. Lift ≥ 1,3 получен в четырёх из пяти фолдов, поэтому критерий устойчивости пока не пройден.

Проверка допусков 0%, 0,5% и 1% показала лучший баланс у 0,5%: при 1% hit rate растёт до 87,3%, но lift падает до 1,10 из-за слишком высокого random baseline. Полная таблица находится в `results/backtest/tolerance_summary.csv`.

## Завершённые product-policy studies

Эти команды воспроизводят боковые исследования, но не являются вторым основным
pipeline:

```powershell
uv run python scripts/evaluate_indicators.py
uv run python scripts/evaluate_fast_slow.py
```

Momentum, level, reversal и seasonality проверены на той же walk-forward-схеме. Ни одно простое правило не достигло устойчивого lift ≥ 1,3. Для RUB→TJS/3 дня двухшаговое подтверждение также не улучшило результат: hit rate 80,7% против 86,3% у раннего сигнала и средняя цена ожидания 10,4 б.п. Поэтому slow-сигнал не входит в текущую продуктовую политику.

## Исторический срез

Решение на конкретную дату можно восстановить из сохранённого out-of-time результата:

```powershell
uv run python scripts/show_signal_as_of.py --date 2025-05-14 --corridor RUB_TJS --horizon 3
```

Отсутствие строки сигнала возвращает `send=false`; это не пересчитывает историю с использованием будущих параметров.

## Проверки

```powershell
uv run python -m unittest discover -s tests -v
```

Курс ЦБ используется только как открытый воспроизводимый proxy рыночного движения и не равен курсу перевода в банковском приложении.
