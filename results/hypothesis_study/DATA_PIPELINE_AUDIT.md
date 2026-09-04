# Аудит пайплайна данных

Проверено сырьё ЦБ, нормировка `curs / nominal`, формулы меток, временная доступность USD/EUR, производные и purge gap. Итог: **20/20 проверок пройдено**.

## Проверки

| check | status | detail |
|---|---|---|
| raw_TJS | PASS | 2468 rows; 2016-09-02..2026-09-02; normalized by nominal |
| raw_UZS | PASS | 2468 rows; 2016-09-02..2026-09-02; normalized by nominal |
| raw_KGS | PASS | 2468 rows; 2016-09-02..2026-09-02; normalized by nominal |
| raw_AMD | PASS | 2468 rows; 2016-09-02..2026-09-02; normalized by nominal |
| raw_KZT | PASS | 2468 rows; 2016-09-02..2026-09-02; normalized by nominal |
| raw_USD | PASS | 2468 rows; 2016-09-02..2026-09-02; normalized by nominal |
| raw_EUR | PASS | 2468 rows; 2016-09-02..2026-09-02; normalized by nominal |
| labels_TJS | PASS | recomputed 2464 complete h=3/e=50bp labels |
| features_TJS | PASS | past-only first/second derivatives and reversal features available |
| labels_UZS | PASS | recomputed 2464 complete h=3/e=50bp labels |
| features_UZS | PASS | past-only first/second derivatives and reversal features available |
| labels_KGS | PASS | recomputed 2464 complete h=3/e=50bp labels |
| features_KGS | PASS | past-only first/second derivatives and reversal features available |
| labels_AMD | PASS | recomputed 2464 complete h=3/e=50bp labels |
| features_AMD | PASS | past-only first/second derivatives and reversal features available |
| labels_KZT | PASS | recomputed 2464 complete h=3/e=50bp labels |
| features_KZT | PASS | past-only first/second derivatives and reversal features available |
| auxiliary_asof | PASS | USD/EUR source_date never exceeds corridor date |
| feature_allowlist | PASS | 52 configured features; forbidden=[] |
| walk_forward_purge | PASS | 20-day label window ends before validation/test starts |

## Покрытие рядов

| currency | rows | date_min | date_max | min_rate | max_rate |
|---|---|---|---|---|---|
| TJS | 2468 | 2016-09-02 | 2026-09-02 | 4.72982 | 10.6719 |
| UZS | 2468 | 2016-09-02 | 2026-09-02 | 0.00473661 | 0.0220296 |
| KGS | 2468 | 2016-09-02 | 2026-09-02 | 0.643497 | 1.26242 |
| AMD | 2468 | 2016-09-02 | 2026-09-02 | 0.115184 | 0.278846 |
| KZT | 2468 | 2016-09-02 | 2026-09-02 | 0.112176 | 0.231488 |
| USD | 2468 | 2016-09-02 | 2026-09-02 | 51.158 | 120.3785 |
| EUR | 2468 | 2016-09-02 | 2026-09-02 | 52.7379 | 132.9581 |

## Граница интерпретации

DBF содержит дату начала действия курса, но не точное время публикации. Пайплайн использует значение не раньше effective date. Это консервативно по отношению к внутридневному инференсу. USD/EUR присоединяются только backward-as-of. Будущее используется в `labels`, но отсутствует в allowlist признаков.
