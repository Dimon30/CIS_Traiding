# Проверенные альтернативы canonical Random Forest

Выбранное решение остаётся
`20260905_wave0_temporal_v3_baseline`: pooled Random Forest на `message_hit`,
`full_market_with_fx`, отдельные thresholds, h=3, epsilon=50 bp и cooldown 4 дня.
Его aggregate lift равен 1.214, hit rate 84.7%, частота 0.426 сигнала в неделю,
mean regret 23.4 bp.

| Проверка | Изменялось | Результат | Решение |
|---|---|---|---|
| H013 | Random Forest → CatBoost | lift 1.197, hit rate 79.8%, mean regret 35.3 bp | отклонена |
| H015 | добавлены implied-USD признаки | lift 1.165, hit rate 82.9%, 21 active cell | отклонена |
| H016 smoke | target → `target_good_now` | target lift 1.551, но future-safety 61.4%, mean/p90 regret 71.7/215.8 bp | отклонена |
| H017 smoke | causal 28-day attractiveness gate | 0.259–0.362 сигнала/неделю; conditional lift <1 во всех коридорах | отклонена |
| H018 smoke | focused RF regularization grid | lift 1.195, hit rate 84.1%, 0.336 сигнала/неделю; paired P(improves)=32.5% | отклонена |

Эти результаты являются отрицательными проверками альтернатив, а не кандидатами
для объединения. Они сохраняются, чтобы не повторять уже проверенные ветки без
новых данных или новой причинной гипотезы.

H018 показал, что прежний RF tuning действительно был узким: сравнивались только
глубины 4 и 8 при фиксированных остальных параметрах. Расширение до девяти
комбинаций (`max_depth` 2/3/4 × `min_samples_leaf` 5/10/20) повысило inner
PR-AUC, но ухудшило итоговую OOT policy. Поэтому текущая evidence-backed точка
возврата — canonical RF, а не более регуляризованный H018.

Все сравнения относятся к историческим proxy-курсам ЦБ. H016–H018 smoke и
повторно просмотренные outer years не являются независимым подтверждением.
