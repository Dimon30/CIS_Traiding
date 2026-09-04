# Review notebooks

Notebook используется для разбора уже выполненного эксперимента, а не как единственное место обучения и бизнес-логики.

Шаблон notebook для гипотезы:

1. Hypothesis spec.
2. Experiment manifest.
3. Target distribution.
4. Baseline и простые индикаторы.
5. Сравнение моделей.
6. Uplift и benefit bps по folds/коридорам.
7. Частота и кучность.
8. Ошибки на временном графике.
9. Коэффициенты или feature importance.
10. Verdict и ограничения.

Notebook должен только читать артефакты из `artifacts/experiments/<experiment_id>/` и не менять dataset, labels или test-результаты.

Три воспроизводимых checkpoint-notebook в этом каталоге читают зафиксированные
артефакты из `results/`:

1. `00_data_pipeline_audit.ipynb` — качество данных и leakage controls;
2. `01_model_benchmark.ipynb` — модели и pooled/per-corridor;
3. `02_hypotheses_and_sensitivity.ipynb` — статтесты, h/epsilon и product proxy.

Запуск:

```powershell
jupyter nbconvert --to notebook --execute --inplace notebooks/00_data_pipeline_audit.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/01_model_benchmark.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/02_hypotheses_and_sensitivity.ipynb
```
