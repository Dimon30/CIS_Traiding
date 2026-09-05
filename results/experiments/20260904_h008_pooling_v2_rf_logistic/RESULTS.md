# H008: pooling ablation

## Что проверялось

Одинаковый `h=3`, `epsilon=50 bp`, feature set `full_market_with_fx` и одинаковые
OOT-даты применены к четырём стратегиям. В этом запуске выполнены Logistic
Regression и Random Forest. CatBoost досчитан отдельным companion-run после
синхронизации `uv`-окружения:
`results/experiments/20260905_h008_pooling_v2_catboost/`.

Стратегии:

- `per_corridor`: пять отдельных моделей и thresholds;
- `pooled_with_corridor_thresholds`: одна модель с one-hot валюты, thresholds
  отдельные;
- `pooled_without_corridor_feature`: одна модель без идентификатора валюты,
  thresholds отдельные;
- `pooled`: одна модель с one-hot валюты и один общий threshold.

Все восемь комбинаций получили одни и те же 5 741 OOT-наблюдение.

## Агрегированный результат

Метрики policy агрегированы через суммарные hits и ожидаемые matched-random hits,
а не простым средним по активным folds.

| strategy | model | lift | hit rate | random | signals/week | active cells | ROC-AUC | PR-AUC gain | Brier skill |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | Random Forest | 1.264 | 88.0% | 69.6% | 0.33 | 20/25 | 0.636 | +0.113 | -0.054 |
| pooled + corridor thresholds | Random Forest | 1.246 | 85.8% | 68.9% | 0.40 | 23/25 | 0.636 | +0.113 | -0.054 |
| pooled without corridor feature | Random Forest | 1.230 | 85.2% | 69.2% | 0.38 | 23/25 | 0.637 | +0.114 | -0.054 |
| per corridor | Random Forest | 1.149 | 79.1% | 68.9% | 0.46 | 24/25 | 0.619 | +0.105 | -0.057 |
| per corridor | Logistic | 1.175 | 80.2% | 68.2% | 0.56 | 22/25 | 0.624 | +0.096 | -0.022 |
| pooled + corridor thresholds | Logistic | 1.172 | 80.1% | 68.4% | 0.56 | 21/25 | 0.611 | +0.088 | -0.042 |
| pooled without corridor feature | Logistic | 1.161 | 79.7% | 68.6% | 0.59 | 21/25 | 0.617 | +0.091 | -0.028 |
| pooled | Logistic | 1.138 | 75.7% | 66.5% | 0.39 | 21/25 | 0.611 | +0.088 | -0.042 |

CatBoost (тот же протокол, companion-run):

| strategy | lift | hit rate | random | signals/week | active cells | ROC-AUC | PR-AUC gain | Brier skill |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled + corridor thresholds | 1.208 | 82.3% | 68.1% | 0.51 | 25/25 | 0.640 | +0.114 | +0.054 |
| pooled | 1.194 | 81.5% | 68.3% | 0.55 | 25/25 | 0.640 | +0.114 | +0.054 |
| per corridor | 1.173 | 79.5% | 67.8% | 0.52 | 25/25 | 0.617 | +0.096 | +0.029 |
| pooled without corridor feature | 1.157 | 79.5% | 68.7% | 0.56 | 25/25 | 0.648 | +0.112 | +0.063 |

## Интерпретация

Pooling практически полезен для Random Forest: вариант с отдельными thresholds
превысил отдельные леса по lift во всех пяти test-years. Средняя годовая разница
lift равна `+0.155`, медианная `+0.109`; односторонний exact Wilcoxon даёт raw
`p=0.03125`. После учёта нескольких сравнений этот результат нельзя считать
окончательным подтверждением.

Удаление признака валюты почти не изменило score: ROC-AUC 0.637 против 0.636 и
PR-AUC gain +0.114 против +0.113. Значит, общий лес в основном использует
универсальные относительные признаки, а не запоминает идентификатор коридора.

Единый threshold дал самый высокий aggregate lift, но полностью потерял 2022 год:
там не было ни одного сигнала ни по одной валюте. Поэтому он не является текущим
продуктовым кандидатом несмотря на lift 1.264.

Ни один вариант не достиг заранее заданного lift 1.3. У RF-вариантов Brier skill
отрицательный: score хорошо ранжирует дни, но плохо откалиброван как вероятность.
CatBoost калиброван заметно лучше (положительный Brier skill), однако его policy
lift ниже RF. Это разделяет две задачи: качество score и качество сигнальной policy.

## Вывод и следующий тест

Гипотеза pooling для Random Forest и CatBoost перспективна, но пока не принята:
критерий lift 1.3 не достигнут. Рабочим кандидатом остаётся общая RF-модель с
отдельными thresholds благодаря лучшему policy lift и приемлемому покрытию.
CatBoost следует сохранить как альтернативу, если приоритетом станет качество
вероятностного score. Следующая проверка — time-safe calibration RF и разнесение
выбора hyperparameters и threshold по разным временным validation-блокам.
