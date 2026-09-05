# AGENTS.md

Этот файл задаёт контекст и правила для всего репозитория. Команды ниже выполняются
из корня проекта.

## Что это за проект

CIS Trading — исследовательский ML-прототип для объяснимого сигнала «выгодно
сейчас» при переводе рублей в валюты стран СНГ. Сервис не прогнозирует абсолютный
минимум и не даёт инвестиционных рекомендаций: он ищет редкие даты, когда ожидание
в пределах выбранного горизонта, вероятно, не даст существенно более выгодный курс.

Основные коридоры: RUB→TJS, RUB→UZS, RUB→KGS, RUB→AMD и RUB→KZT. USD, EUR и CNY
используются только как внешние point-in-time факторы. Источник — открытые курсы
ЦБ РФ; это proxy рынка, а не банковский курс перевода.

## Источники истины и их приоритет

1. `PRODUCT_CONTRACT.md` — продукт, target, ограничения и критерии качества.
2. `configs/*.toml` и `hypotheses/*.toml` — параметры воспроизводимого запуска.
3. `scripts/` и `tests/` — фактическая реализация.
4. `results/**/manifest.json` и табличные артефакты — параметры конкретных запусков.
5. `results/**.md`, ноутбуки и презентации — интерпретация результатов.

Если код или презентация расходятся с продуктовым контрактом, сначала согласованно
обновить контракт, затем конфиги, код, тесты и документацию. Материалы в
`docs/archive/` не являются актуальными требованиями.

## Ключевая семантика

- Нормированный курс: `q_t = value_rub / nominal`, рублей за единицу валюты
  получателя. Чем ниже `q_t`, тем выгоднее перевод.
- Основной target — `message_hit`: в следующие `h` календарных дней ожидание не
  дало курс лучше текущего более чем на `epsilon`.
- `target_good_now` — вспомогательная метка положения курса в симметричном окне
  `±h`; не подменять ею основной продуктовый target.
- Рабочий режим MVP: `h=3`, `epsilon=50 bp`, cooldown 4 календарных дня.
- Главная метрика: `signal_hit_rate / matched_random_hit_rate`. Случайное
  расписание обязано иметь тот же период, число сигналов и cooldown.
- Ложный пуш дороже пропуска. Ориентир частоты 1–2 сигнала в неделю — sanity check,
  а не квота.
- Признаки на дату `T` используют только доступные к `T` значения. Будущие данные
  допустимы только в labels и OOT-оценке.

## Поток данных и эксперимента

```text
data/raw/*.dbf
  → scripts/build_dataset.py
  → data/processed/{observations,labels}.csv
  → scripts/audit_pipeline.py
  → hypothesis TOML + configs TOML
  → scripts/run_experiment.py
  → results/experiments/<run_id>/{manifest,fold_metrics,summary,...}
  → scripts/analyze_hypotheses.py
  → results/hypothesis_study/ + review-notebooks + deliverables
```

`scripts/run_backtest.py` — отдельно сохраняемый, проверенный logistic baseline.
`scripts/evaluate_indicators.py` и `scripts/evaluate_fast_slow.py` проверяют
продуктовые альтернативы на той же временной схеме. `show_signal_as_of.py` только
читает сохранённые out-of-time сигналы и не переобучает модель задним числом.

## Структура репозитория

- `configs/` — data, feature groups, model grids и validation policy.
- `hypotheses/` — предзаданные H001–H007 и критерии принятия.
- `data/raw/` — неизменяемые исходные DBF.
- `data/processed/` — воспроизводимые observations и future-label tables.
- `data/exploration/` — одноразовые исследовательские выгрузки; не вход pipeline.
- `scripts/` — текущая реализация и CLI. Это ещё не installable Python package.
- `tests/` — unit-тесты критичных формул и signal policy.
- `notebooks/` — три review-notebook, читающие готовые результаты.
- `notebooks/exploration/` — ранний EDA; не источник бизнес-логики.
- `results/backtest/` — зафиксированный baseline.
- `results/experiments/` — bundles отдельных запусков.
- `results/hypothesis_study/` — сводный отчёт, статтесты и графики.
- `deliverables/presentation/` — финальные PDF/PPTX и исходная status-версия.
- `docs/archive/` — исторические документы.
- `tmp/` — локальные временные файлы; Git их игнорирует.

Подробнее об экспериментальной архитектуре: `PROJECT_STRUCTURE.md`.

## Окружение и проверки

Проект объявляет Python `>=3.14` и фиксирует зависимости в `uv.lock`.

```powershell
uv sync
uv run python -m unittest discover -s tests -v
```

Не считать `ModuleNotFoundError` для `dbfread` или `catboost` дефектом кода, если
тесты запущены системным Python вне uv-окружения. Не менять Python constraint или
lock-файл без отдельной причины и полной проверки.

Быстрые проверки после изменений:

```powershell
uv run python scripts/build_dataset.py --help
uv run python scripts/run_backtest.py --help
uv run python scripts/run_experiment.py --help
uv run python -m unittest discover -s tests -v
```

Полные model benchmark и sensitivity-запуски тяжёлые. Не перезапускать и не
перезаписывать утверждённые `results/` без явной задачи; для smoke-test использовать
новый уникальный `--run-id`.

## Инварианты реализации

- Walk-forward: train — вся ранняя история, validation — год `T-1`, test — год
  `T`; перед validation и test выдерживать purge gap не короче `h`.
- Threshold и hyperparameters выбираются только на validation, никогда на test.
- Даты одной календарной точки из разных коридоров должны попадать в одну часть
  временного split.
- Повторяющиеся неизменившиеся курсы не считаются независимыми датами отправки.
- Любое изменение labels, cooldown, random baseline или split сопровождается
  тестом; это наиболее рискованные участки.
- Сохранять seed, dataset fingerprint, git commit и все параметры запуска в
  manifest.
- Не редактировать сгенерированные CSV и графики вручную. Исправлять генератор и
  пересоздавать артефакт осознанно.
- Не переносить вычислительную или продуктовую логику в notebook.
- Сохранять существующие CLI при рефакторинге. Скрипты сейчас импортируют функции
  друг друга через `scripts`; перенос в `src/cis_trading/` делать постепенно.
- Все пути по умолчанию задавать относительно корня и через `pathlib.Path`.
- Новые scratch/render/inspection outputs направлять в `tmp/`, финальные
  пользовательские материалы — в `deliverables/`, ML-метрики — в `results/`.

## Текущие выводы, которые нельзя переобещать

- Logistic baseline для RUB→TJS, `h=3`, `epsilon=50 bp`: lift 1.36, hit rate
  86.3%, 0.59 сигнала в неделю; 4 из 5 folds имеют lift ≥ 1.3, поэтому строгий
  критерий устойчивости ещё не выполнен.
- Лучший средний benchmark — random forest с pooled model и отдельными порогами по
  коридорам: mean lift 1.42, hit rate 85.4%, 0.43 сигнала в неделю.
- После поправки Holm статистической значимости на 5% нет; данные дают
  перспективный, но не финально доказанный результат.
- Простые индикаторы и slow-confirmation не улучшили текущую policy.
- Реальная банковская выгода и влияние пушей на доверие не проверены без
  исторического банковского курса и продуктовых event logs.

Актуальные числа брать из `results/hypothesis_study/HYPOTHESIS_REPORT.md` и
`results/backtest/RESULTS.md`, а не из памяти или презентации.

## Порядок работы агента

1. Перед изменениями прочитать релевантные разделы `PRODUCT_CONTRACT.md`, проверить
   `git status` и найти все ссылки на затрагиваемые пути/функции через `rg`.
2. Делать минимальный связный change set; не смешивать новый эксперимент с
   рефакторингом pipeline.
3. Добавить или обновить тесты для изменившейся логики.
4. Запустить максимально доступные проверки через `uv`; если среда не готова,
   точно описать, что выполнено и что заблокировано окружением.
5. Обновить README/PROJECT_STRUCTURE/AGENTS, если поменялись команды, каталоги,
   инварианты или источники истины.

