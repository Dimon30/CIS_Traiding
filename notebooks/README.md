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

