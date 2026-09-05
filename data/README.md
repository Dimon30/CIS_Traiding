# Data layout

- `raw/` — исходные DBF-файлы курсов ЦБ РФ. Не редактировать на месте.
- `processed/` — воспроизводимые observations и labels, создаваемые
  `scripts/build_dataset.py`.
- `exploration/` — выгрузки исследовательских ноутбуков, не используемые основным
  pipeline.

По умолчанию сборщик читает `data/raw` и пишет в `data/processed`. Если для одной
валюты лежит несколько DBF, `select_input_file` выбирает самый большой файл, затем
имя — это защищает полный UZS-ряд от короткого свежего snapshot.

Запускать из корня репозитория:

```powershell
uv run python scripts/build_dataset.py --all-currencies
uv run python scripts/audit_pipeline.py
```

