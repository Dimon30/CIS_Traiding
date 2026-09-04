# Проверка гипотез и benchmark моделей

## Главный вывод

Лучший средний результат benchmark: **random_forest / pooled_with_corridor_thresholds**, средний lift по коридорам **1.42**, hit rate **85.4%**, частота **0.43 сигнала в неделю**. Выбор финальной модели нельзя делать только по среднему lift: дополнительно смотрим худший временной fold, PR-AUC, Brier score и стабильность между коридорами.

## Зачем нужны эти метрики

- `lift = signal hit rate / matched-random hit rate` отвечает на главный продуктовый вопрос: насколько уведомление лучше случайного дня при той же частоте и cooldown.
- `hit rate` и `false push rate` измеряют правдивость сообщений и риск потери доверия.
- `PR-AUC` проверяет ранжирование полезных моментов и лучше ROC-AUC отражает качество положительного класса.
- `ROC-AUC` остаётся порог-независимой диагностикой разделимости классов.
- `Brier score` показывает качество вероятностного score; он важен, если score позже показывается как надёжность.
- `balanced accuracy` не даёт частому классу полностью определить результат.
- `advantage/regret bps` и их рублёвый эквивалент для перевода 100 000 ₽ связывают ML-ошибки с экономикой клиента. Это proxy на курсе ЦБ, не доказанная выгода по банковскому курсу.

## Benchmark моделей

| strategy | model | corridors | mean_lift | worst_fold_lift | mean_hit_rate | mean_roc_auc | mean_pr_auc | mean_brier | mean_frequency |
|---|---|---|---|---|---|---|---|---|---|
| pooled_with_corridor_thresholds | random_forest | 5 | 1.4183 | 1.1098 | 0.8537 | 0.6319 | 0.7767 | 0.2465 | 0.4343 |
| per_corridor | catboost | 5 | 1.3647 | 0.0000 | 0.8096 | 0.6203 | 0.7562 | 0.2262 | 0.4596 |
| pooled_with_corridor_thresholds | catboost | 5 | 1.3413 | 0.9318 | 0.8151 | 0.6328 | 0.7556 | 0.2214 | 0.4984 |
| per_corridor | random_forest | 5 | 1.3213 | 0.7587 | 0.8092 | 0.6164 | 0.7626 | 0.2483 | 0.4778 |
| per_corridor | logistic | 5 | 1.3016 | 0.8190 | 0.7999 | 0.6230 | 0.7665 | 0.2388 | 0.6563 |
| pooled_with_corridor_thresholds | logistic | 5 | 1.2886 | 0.9008 | 0.7944 | 0.6279 | 0.7713 | 0.2376 | 0.6944 |
| per_corridor | knn | 5 | 1.2838 | 0.9997 | 0.7713 | 0.6020 | 0.7485 | 0.2218 | 0.4693 |
| pooled_with_corridor_thresholds | svm | 5 | 1.2762 | 0.9105 | 0.7902 | 0.6215 | 0.7717 | 0.2224 | 0.6559 |
| pooled_with_corridor_thresholds | knn | 5 | 1.2745 | 0.9373 | 0.7699 | 0.6033 | 0.7417 | 0.2285 | 0.4774 |
| per_corridor | svm | 5 | 1.2630 | 0.8219 | 0.7745 | 0.6218 | 0.7731 | 0.2156 | 0.6080 |
| pooled_with_corridor_thresholds | naive_bayes | 5 | 1.0533 | 0.7965 | 0.6500 | 0.5715 | 0.7224 | 0.3839 | 0.6120 |
| per_corridor | naive_bayes | 5 | 1.0336 | 0.7596 | 0.6444 | 0.5678 | 0.7258 | 0.3909 | 0.5886 |

## Парные статистические проверки

Сначала lift усредняется по коридорам внутри каждого test-year, затем односторонний Wilcoxon проверяет пять независимых временных блоков. Так общие RUB-шоки не создают искусственную значимость. Поправка Holm контролирует множественные сравнения. Пять лет дают низкую мощность, поэтому практический размер эффекта и устойчивость важнее одного p-value.

| hypothesis | n_time_blocks | left_mean_lift | right_mean_lift | mean_delta_lift | median_delta_lift | p_value_one_sided | p_value_holm | significant_5pct |
|---|---|---|---|---|---|---|---|---|
| H2 combination vs price-only | 5 | 1.1218 | 1.4342 | 0.3125 | 0.3705 | 0.0312 | 0.1250 | False |
| Derivatives vs case factors | 5 | 1.4342 | 1.4413 | 0.0071 | -0.0006 | 0.5938 | 1.0000 | False |
| USD/EUR factors vs derivatives | 5 | 1.3986 | 1.6131 | 0.2145 | 0.0410 | 0.2188 | 0.6562 | False |
| H4 pooled vs per-corridor logistic | 4 | 1.3228 | 1.4822 | 0.1594 | -0.0021 | 0.5625 | 1.0000 | False |

## Значимость относительно случайного расписания

Единица теста здесь — календарный test-year: lift сначала усредняется по коридорам, затем проверяется против 1. Поправка Holm применяется ко всем 12 комбинациям модели и стратегии. При пяти test-year минимально достижимый p-value дискретен, поэтому отсутствие `p<0.05` не равнозначно отсутствию практического эффекта.

| strategy | model | n_test_years | mean_yearly_lift | min_yearly_lift | p_value_one_sided | p_value_holm | significant_5pct |
|---|---|---|---|---|---|---|---|
| pooled_with_corridor_thresholds | random_forest | 5 | 1.6161 | 1.1817 | 0.0312 | 0.3750 | False |
| pooled_with_corridor_thresholds | logistic | 5 | 1.6131 | 1.0582 | 0.0312 | 0.3750 | False |
| per_corridor | random_forest | 5 | 1.5710 | 1.0534 | 0.0312 | 0.3750 | False |
| pooled_with_corridor_thresholds | svm | 5 | 1.5189 | 0.9894 | 0.0625 | 0.3750 | False |
| per_corridor | svm | 5 | 1.4864 | 0.9241 | 0.0625 | 0.3750 | False |
| pooled_with_corridor_thresholds | catboost | 5 | 1.4796 | 1.1508 | 0.0312 | 0.3750 | False |
| per_corridor | knn | 5 | 1.4348 | 1.0609 | 0.0312 | 0.3750 | False |
| per_corridor | catboost | 5 | 1.4116 | 1.1677 | 0.0312 | 0.3750 | False |
| pooled_with_corridor_thresholds | knn | 5 | 1.3449 | 1.0538 | 0.0312 | 0.3750 | False |
| per_corridor | logistic | 5 | 1.3156 | 1.0829 | 0.0312 | 0.3750 | False |
| pooled_with_corridor_thresholds | naive_bayes | 5 | 1.2289 | 0.9447 | 0.4062 | 0.6250 | False |
| per_corridor | naive_bayes | 5 | 1.2070 | 0.9021 | 0.3125 | 0.6250 | False |

## Гипотезы из исходного документа

| hypothesis | verdict | evidence | what_remains |
|---|---|---|---|
| H1 relative-format proxy | rejected_proxy | hit 67.4% vs 67.0%; Mann-Whitney p=0.589 | Original understandability claim needs user research |
| H2 combined factors | promising_not_confirmed | paired delta lift 0.312; raw p=0.03125; Holm p=0.125 | Need more independent test periods |
| H3 rarity/cooldown proxy | rejected_proxy | precision delta -1.2%; CI [-5.4%, 3.0%] | Loyalty needs notification interaction logs |
| H4 pooled vs per-corridor | inconclusive | logistic delta lift 0.159; Holm p=1.000 | Pooled random forest is the practical candidate |
| H5 fast vs slow | rejected_for_current_rule | slow-fast hit delta -0.8%; p=0.561 | A different adaptive policy can be tested later |
| H6 honest UX and trust | not_testable | No user reaction data | Controlled message test or pilot |
| H7 CBR vs bank benefit | blocked_by_data | No historical bank rate/spread | Parallel bank and CBR time series |
| ML-H006 derivatives | rejected | median delta lift -0.001; Holm p=1.000 | Keep only if a later fold shows stable gain |
| ML-H007 USD/EUR | inconclusive | mean delta 0.215, median 0.041; Holm p=0.656 | Effect is unstable and driven by a few folds |

- **H1 (относительная выгода понятнее): частично проверена только рыночная proxy-версия.** У top-15% исторически выгодных дней hit rate 67.4% против 67.0%; Mann–Whitney p=0.5887. Понятность текста и доверие требуют пользовательского теста.
- **H2 (комбинация факторов):** результат в таблице парных тестов сравнивает H002 с price-only на одинаковых фолдах.
- **H3 (редкость): proxy через cooldown.** Precision до фильтра 80.4%, после 79.3%, delta -1.2%; block-bootstrap 95% CI [-5.4%, 3.0%]. Лояльность клиента по рыночным данным измерить нельзя.
- **H4 (единая или отдельные модели):** предзаданный logistic comparison приведён в таблице; оба режима используют одни и те же test-даты.
- **H5 (быстрый или медленный сигнал):** средняя разница hit rate slow-fast -0.8%, p=0.5606, среднее ожидание 1.01 дня.
- **H6 (честный UX сохраняет доверие): не проверяема** без логов открытий, жалоб, отключений или controlled user study.
- **H7 (курс ЦБ отражает банковскую выгоду): не проверяема** без параллельного исторического ряда банковского курса и спреда.
- **Новая ML-гипотеза USD/EUR:** H007 сравнивается с H006 без внешних валют в парном тесте. Все USD/EUR признаки присоединены backward-as-of.

## Чувствительность h и epsilon

Формально максимальный lift даёт `h=1, epsilon=0`, но этот режим преимущественно учится распознавать календарные дни, после которых курс ЦБ не обновляется. Его средняя выгода составляет лишь несколько базисных пунктов. Для продуктового MVP разумнее оставить `h=3, epsilon=50 bp`: hit rate около 80%, экономический допуск интерпретируем, а ложный пуш остаётся существенно дороже пропуска. `h=3, epsilon=0` повышает lift ценой hit rate около 55%, что неприемлемо для доверительного push-продукта.

| horizon_days | epsilon_bps | strategy | mean_lift | mean_hit_rate | mean_frequency | worst_fold_lift | mean_advantage_bps | mean_regret_bps |
|---|---|---|---|---|---|---|---|---|
| 1 | 0 | pooled_with_corridor_thresholds | 1.8713 | 0.9715 | 0.8342 | 1.6285 | 1.9520 | 1.0033 |
| 1 | 0 | per_corridor | 1.7868 | 0.9424 | 0.7807 | 1.3194 | 2.0461 | 3.6294 |
| 3 | 0 | pooled_with_corridor_thresholds | 1.3798 | 0.5537 | 0.5974 | 0.0000 | 3.6031 | 27.6550 |
| 3 | 0 | per_corridor | 1.3559 | 0.5415 | 0.4774 | 0.7917 | 6.1390 | 36.9939 |
| 3 | 50 | per_corridor | 1.3016 | 0.7999 | 0.6563 | 0.8190 | 13.6150 | 31.6596 |
| 3 | 50 | pooled_with_corridor_thresholds | 1.2886 | 0.7944 | 0.6944 | 0.9008 | 9.2673 | 32.0019 |
| 5 | 0 | per_corridor | 1.2370 | 0.4228 | 0.5527 | 0.0000 | 7.0766 | 80.8181 |
| 1 | 50 | pooled_with_corridor_thresholds | 1.2355 | 0.9717 | 0.6932 | 1.0323 | 0.2586 | 3.7417 |
| 1 | 50 | per_corridor | 1.2178 | 0.9510 | 0.7737 | 1.0000 | -0.5346 | 6.6510 |
| 10 | 0 | per_corridor | 1.2088 | 0.2809 | 0.5207 | 0.0000 | 7.5073 | 188.2515 |
| 3 | 100 | pooled_with_corridor_thresholds | 1.1728 | 0.8885 | 0.5983 | 0.9696 | 10.2919 | 34.2503 |
| 3 | 100 | per_corridor | 1.1562 | 0.8703 | 0.5955 | 0.5020 | 11.4991 | 39.4933 |
| 5 | 50 | per_corridor | 1.1105 | 0.6063 | 0.5849 | 0.7110 | 17.2696 | 76.2239 |
| 5 | 50 | pooled_with_corridor_thresholds | 1.1104 | 0.6219 | 0.5162 | 0.5470 | 10.2488 | 74.8191 |
| 10 | 0 | pooled_with_corridor_thresholds | 1.1080 | 0.2677 | 0.5897 | 0.0000 | -2.2153 | 173.0787 |
| 10 | 50 | per_corridor | 1.0958 | 0.4630 | 0.6196 | 0.0000 | 4.5215 | 148.9517 |
| 1 | 100 | pooled_with_corridor_thresholds | 1.0807 | 0.9487 | 0.7544 | 0.9338 | -1.6864 | 14.7971 |
| 5 | 0 | pooled_with_corridor_thresholds | 1.0777 | 0.3771 | 0.5109 | 0.0000 | 0.0624 | 77.8280 |
| 20 | 0 | per_corridor | 1.0702 | 0.2087 | 0.5773 | 0.0000 | 29.2043 | 241.3225 |
| 20 | 50 | per_corridor | 1.0547 | 0.3659 | 0.6358 | 0.0000 | 19.4860 | 223.3436 |

## Ограничения продуктовых выводов

`false push rate`, частота и стабильность по фолдам являются proxy риска раздражения и доверия, но не метриками лояльности. Для реальной оценки нужны delivery/open/click/unsubscribe/transfer logs и банковский курс. Исторический backtest доказывает только качество рыночного сигнала.
