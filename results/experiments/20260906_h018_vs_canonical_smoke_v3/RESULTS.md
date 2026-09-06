# H018: focused Random Forest tuning

Status: **rejected_smoke**. Full run allowed: **False**.

| Metric | Canonical RF | H018 smoke | Delta |
|---|---:|---:|---:|
| Lift | 1.214 | 1.195 | -0.019 |
| Hit rate | 84.7% | 84.1% | -0.7% |
| Signals/week | 0.426 | 0.336 | -0.090 |
| Mean regret, bp | 23.4 | 22.6 | -0.9 |
| Active cells | 24 | 22 | -2 |

Paired bootstrap P(hit rate improves): 32.5%.

Selected hyperparameters by outer fold:

- `{"max_depth": 2, "min_samples_leaf": 5}`: 3 folds
- `{"max_depth": 3, "min_samples_leaf": 5}`: 2 folds

The stronger inner-validation PR-AUC did not improve the delivered OOT policy. H018 is retained as a rejected alternative; canonical RF remains selected.

Historical outer years were previously inspected. This smoke comparison is exploratory.
