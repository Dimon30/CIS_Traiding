"""Create statistical tests, figures and a human-readable hypothesis report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact, mannwhitneyu, wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_backtest import load_model_frame  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=Path("results/experiments/20260904_model_benchmark"))
    parser.add_argument("--ablation", type=Path, default=Path("results/experiments/20260904_feature_ablation"))
    parser.add_argument("--sensitivity", type=Path, default=Path("results/experiments/20260904_h_epsilon_sensitivity"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/hypothesis_study"))
    return parser.parse_args()


def holm_adjust(values: list[float]) -> list[float]:
    order = np.argsort(values)
    adjusted = np.ones(len(values))
    running = 0.0
    size = len(values)
    for rank, index in enumerate(order):
        current = min(1.0, (size - rank) * values[index])
        running = max(running, current)
        adjusted[index] = running
    return adjusted.tolist()


def paired_lift_test(
    folds: pd.DataFrame,
    left_filter: dict[str, object],
    right_filter: dict[str, object],
    name: str,
) -> dict[str, object]:
    keys = ["horizon_days", "epsilon_bps", "model", "corridor", "test_year"]
    left = folds.copy()
    right = folds.copy()
    for column, value in left_filter.items():
        left = left[left[column] == value]
    for column, value in right_filter.items():
        right = right[right[column] == value]
    pair = left[keys + ["lift"]].merge(
        right[keys + ["lift"]], on=keys, suffixes=("_left", "_right")
    ).dropna()
    # Corridors in the same year share RUB and macro shocks. Aggregate them
    # before inference so five test-years, not correlated corridor-year rows,
    # are the independent blocks.
    blocks = pair.groupby(
        ["horizon_days", "epsilon_bps", "model", "test_year"], as_index=False
    )[["lift_left", "lift_right"]].mean()
    difference = blocks["lift_right"] - blocks["lift_left"]
    if len(difference) and not np.allclose(difference, 0):
        result = wilcoxon(difference, alternative="greater", zero_method="wilcox")
        p_value = float(result.pvalue)
    else:
        p_value = 1.0
    return {
        "hypothesis": name,
        "n_time_blocks": len(blocks),
        "left_mean_lift": float(blocks["lift_left"].mean()) if len(blocks) else np.nan,
        "right_mean_lift": float(blocks["lift_right"].mean()) if len(blocks) else np.nan,
        "mean_delta_lift": float(difference.mean()) if len(blocks) else np.nan,
        "median_delta_lift": float(difference.median()) if len(blocks) else np.nan,
        "p_value_one_sided": p_value,
    }


def percentile_proxy(data_dir: Path) -> dict[str, object]:
    rows = []
    for currency in ("TJS", "UZS", "KGS", "AMD", "KZT"):
        frame = load_model_frame(data_dir, currency, 3, 50)
        frame = frame.dropna(subset=["range_position_60", "future_regret_bps"])
        frame["top_15pct_historical"] = frame["range_position_60"] <= 0.15
        rows.append(frame[["top_15pct_historical", "future_regret_bps", "message_hit"]])
    combined = pd.concat(rows, ignore_index=True)
    selected = combined[combined["top_15pct_historical"]]
    other = combined[~combined["top_15pct_historical"]]
    mw = mannwhitneyu(selected["future_regret_bps"], other["future_regret_bps"], alternative="less")
    table = np.array(
        [
            [int(selected["message_hit"].sum()), int((1 - selected["message_hit"]).sum())],
            [int(other["message_hit"].sum()), int((1 - other["message_hit"]).sum())],
        ]
    )
    odds_ratio, fisher_p = fisher_exact(table, alternative="greater")
    return {
        "selected_days": len(selected),
        "other_days": len(other),
        "selected_hit_rate": float(selected["message_hit"].mean()),
        "other_hit_rate": float(other["message_hit"].mean()),
        "selected_regret_bps_median": float(selected["future_regret_bps"].median()),
        "other_regret_bps_median": float(other["future_regret_bps"].median()),
        "mann_whitney_p": float(mw.pvalue),
        "odds_ratio_hit": float(odds_ratio),
        "fisher_p": float(fisher_p),
    }


def cooldown_proxy(predictions: pd.DataFrame, seed: int = 42) -> dict[str, object]:
    frame = predictions[
        (predictions["model"] == "logistic")
        & (predictions["strategy"] == "pooled_with_corridor_thresholds")
    ].copy()
    candidate = frame[frame["candidate"].astype(str).str.lower().eq("true")]
    selected = frame[frame["selected_signal"].astype(str).str.lower().eq("true")]
    observed = float(selected["message_hit"].mean() - candidate["message_hit"].mean())
    blocks = list(frame.groupby(["corridor", "test_year"]))
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(2000):
        sampled = [blocks[i][1] for i in rng.integers(0, len(blocks), len(blocks))]
        boot = pd.concat(sampled, ignore_index=True)
        before = boot[boot["candidate"].astype(str).str.lower().eq("true")]
        after = boot[boot["selected_signal"].astype(str).str.lower().eq("true")]
        if len(before) and len(after):
            deltas.append(float(after["message_hit"].mean() - before["message_hit"].mean()))
    return {
        "candidate_signals": len(candidate),
        "sent_after_cooldown": len(selected),
        "precision_before": float(candidate["message_hit"].mean()),
        "precision_after": float(selected["message_hit"].mean()),
        "precision_delta": observed,
        "bootstrap_ci_low": float(np.quantile(deltas, 0.025)),
        "bootstrap_ci_high": float(np.quantile(deltas, 0.975)),
    }


def fast_slow_test() -> dict[str, object]:
    path = Path("results/backtest/fast_slow_folds.csv")
    frame = pd.read_csv(path)
    frame = frame[(frame["horizon_days"] == 3) & frame["signal_hit_rate"].notna()]
    pair = frame.pivot_table(index=["corridor", "test_year"], columns="policy", values="signal_hit_rate").dropna()
    difference = pair["slow"] - pair["fast"]
    p_value = float(wilcoxon(difference, alternative="greater").pvalue) if len(difference) and not np.allclose(difference, 0) else 1.0
    slow = frame[frame["policy"] == "slow"]
    return {
        "paired_folds": len(pair),
        "mean_hit_delta_slow_minus_fast": float(difference.mean()),
        "p_value_one_sided": p_value,
        "mean_wait_days": float(slow["wait_days_mean"].mean()),
        "mean_waiting_cost_bps": float(slow["waiting_cost_bps_mean"].mean()),
    }


def model_vs_random_tests(folds: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (strategy, model), group in folds.groupby(["strategy", "model"]):
        # Average corridors within each test year so the unit of inference is a
        # non-overlapping time block rather than five correlated FX observations.
        yearly = group.groupby("test_year")["lift"].mean().dropna()
        difference = yearly - 1.0
        p_value = (
            float(wilcoxon(difference, alternative="greater").pvalue)
            if len(difference) and not np.allclose(difference, 0)
            else 1.0
        )
        rows.append(
            {
                "strategy": strategy,
                "model": model,
                "n_test_years": len(yearly),
                "mean_yearly_lift": float(yearly.mean()),
                "min_yearly_lift": float(yearly.min()),
                "p_value_one_sided": p_value,
            }
        )
    adjusted = holm_adjust([float(row["p_value_one_sided"]) for row in rows])
    for row, value in zip(rows, adjusted):
        row["p_value_holm"] = value
        row["significant_5pct"] = value < 0.05
    return pd.DataFrame(rows).sort_values("mean_yearly_lift", ascending=False)


def make_figures(benchmark: pd.DataFrame, sensitivity: pd.DataFrame, predictions: pd.DataFrame, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")

    ranking = benchmark.groupby(["strategy", "model"], as_index=False).agg(lift=("lift", "mean"), min_fold=("min_fold_lift", "mean"))
    ranking["label"] = ranking["model"] + "\n" + ranking["strategy"].str.replace("pooled_with_corridor_thresholds", "pooled")
    ranking = ranking.sort_values("lift")
    fig, ax = plt.subplots(figsize=(11, 7))
    colors = np.where(ranking["strategy"].eq("per_corridor"), "#E76F51", "#2A9D8F")
    ax.barh(ranking["label"], ranking["lift"], color=colors)
    ax.axvline(1.0, color="#444444", linewidth=1)
    ax.axvline(1.3, color="#264653", linestyle="--", linewidth=1.5, label="Цель MVP: 1,3")
    ax.set_xlabel("Средний lift по коридорам")
    ax.set_title("Сравнение моделей: h=3, epsilon=50 б.п.")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "model_benchmark.png", dpi=170)
    plt.close(fig)

    view = sensitivity[(sensitivity["model"] == "logistic") & (sensitivity["strategy"] == "pooled_with_corridor_thresholds")]
    heat = view.groupby(["horizon_days", "epsilon_bps"])["lift"].mean().unstack()
    fig, ax = plt.subplots(figsize=(8, 5))
    image = ax.imshow(heat.to_numpy(), cmap="RdYlGn", aspect="auto", vmin=0.8, vmax=max(1.4, float(heat.max().max())))
    ax.set_xticks(range(len(heat.columns)), [f"{value} bp" for value in heat.columns])
    ax.set_yticks(range(len(heat.index)), [f"h={value}" for value in heat.index])
    for y in range(len(heat.index)):
        for x in range(len(heat.columns)):
            ax.text(x, y, f"{heat.iloc[y, x]:.2f}", ha="center", va="center", fontsize=10)
    ax.set_title("Чувствительность среднего lift к h и epsilon")
    fig.colorbar(image, ax=ax, label="Средний lift")
    fig.tight_layout()
    fig.savefig(output / "h_epsilon_heatmap.png", dpi=170)
    plt.close(fig)

    product = benchmark.groupby(["strategy", "model"], as_index=False).agg(
        lift=("lift", "mean"), hit=("signal_hit_rate", "mean"), frequency=("signals_per_week", "mean")
    )
    fig, ax = plt.subplots(figsize=(8, 6))
    scatter = ax.scatter(product["frequency"], product["hit"], c=product["lift"], cmap="viridis", s=100)
    for row in product.itertuples():
        ax.annotate(row.model, (row.frequency, row.hit), xytext=(5, 4), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Сигналов в неделю на коридор")
    ax.set_ylabel("Доля правдивых сигналов")
    ax.set_title("Продуктовый баланс частоты, правдивости и lift")
    fig.colorbar(scatter, ax=ax, label="Lift")
    fig.tight_layout()
    fig.savefig(output / "product_metric_tradeoff.png", dpi=170)
    plt.close(fig)

    if not predictions.empty:
        leaders = benchmark.groupby(["strategy", "model"])["lift"].mean().sort_values(ascending=False)
        leader_strategy, leader_model = leaders.index[0]
        top = benchmark[
            (benchmark["model"] == leader_model) & (benchmark["strategy"] == leader_strategy)
        ].sort_values(["min_fold_lift", "lift"], ascending=False).iloc[0]
        view = predictions[
            (predictions["model"] == leader_model)
            & (predictions["strategy"] == leader_strategy)
            & (predictions["corridor"] == top["corridor"])
        ].copy()
        view["date"] = pd.to_datetime(view["date"])
        view = view[view["date"] >= view["date"].max() - pd.DateOffset(years=2)]
        selected = view["selected_signal"].astype(str).str.lower().eq("true")
        sent = view[selected]
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(view["date"], view["rub_per_unit"], color="#264653", linewidth=1.1)
        good = sent[sent["message_hit"] == 1]
        bad = sent[sent["message_hit"] == 0]
        ax.scatter(good["date"], good["rub_per_unit"], color="#2A9D8F", s=30, label="Правдивый сигнал")
        ax.scatter(bad["date"], bad["rub_per_unit"], color="#E76F51", marker="x", s=40, label="Ложный сигнал")
        ax.set_title(f"Сигналы на графике курса: {top['corridor']}, {leader_model}, pooled")
        ax.set_ylabel("RUB за единицу валюты получателя")
        ax.legend()
        fig.tight_layout()
        fig.savefig(output / "signal_timeline.png", dpi=170)
        plt.close(fig)


def markdown_table(frame: pd.DataFrame) -> str:
    display = frame.copy()
    for column in display.select_dtypes(include=["float"]).columns:
        display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "|" + "|".join(["---"] * len(display.columns)) + "|"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in display.itertuples(index=False, name=None)]
    return "\n".join([header, separator, *rows])


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    benchmark_folds = pd.read_csv(args.benchmark / "fold_metrics.csv")
    benchmark_summary = pd.read_csv(args.benchmark / "summary.csv")
    benchmark_predictions = pd.read_csv(args.benchmark / "predictions.csv", low_memory=False)
    ablation_folds = pd.read_csv(args.ablation / "fold_metrics.csv")
    sensitivity_summary = pd.read_csv(args.sensitivity / "summary.csv")

    tests = [
        paired_lift_test(ablation_folds, {"hypothesis_id": "H001_price_core", "strategy": "pooled_with_corridor_thresholds"}, {"hypothesis_id": "H002_combined_factors", "strategy": "pooled_with_corridor_thresholds"}, "H2 combination vs price-only"),
        paired_lift_test(ablation_folds, {"hypothesis_id": "H002_combined_factors", "strategy": "pooled_with_corridor_thresholds"}, {"hypothesis_id": "H006_add_derivatives", "strategy": "pooled_with_corridor_thresholds"}, "Derivatives vs case factors"),
        paired_lift_test(ablation_folds, {"hypothesis_id": "H006_add_derivatives", "strategy": "pooled_with_corridor_thresholds"}, {"hypothesis_id": "H007_add_usd_eur", "strategy": "pooled_with_corridor_thresholds"}, "USD/EUR factors vs derivatives"),
        paired_lift_test(benchmark_folds, {"strategy": "per_corridor", "model": "logistic"}, {"strategy": "pooled_with_corridor_thresholds", "model": "logistic"}, "H4 pooled vs per-corridor logistic"),
    ]
    adjusted = holm_adjust([float(item["p_value_one_sided"]) for item in tests])
    for item, value in zip(tests, adjusted):
        item["p_value_holm"] = value
        item["significant_5pct"] = value < 0.05
    tests_frame = pd.DataFrame(tests)
    tests_frame.to_csv(args.output_dir / "statistical_tests.csv", index=False)
    random_tests = model_vs_random_tests(benchmark_folds)
    random_tests.to_csv(args.output_dir / "model_vs_random_tests.csv", index=False)

    proxy_h1 = percentile_proxy(args.data_dir)
    proxy_h3 = cooldown_proxy(benchmark_predictions)
    proxy_h5 = fast_slow_test()
    proxy_frame = pd.DataFrame(
        [
            {"hypothesis": "H1 relative-format market proxy", **proxy_h1},
            {"hypothesis": "H3 rarity/cooldown proxy", **proxy_h3},
            {"hypothesis": "H5 fast-vs-slow proxy", **proxy_h5},
        ]
    )
    proxy_frame.to_csv(args.output_dir / "proxy_hypothesis_tests.csv", index=False)

    test_lookup = {row["hypothesis"]: row for row in tests}
    verdicts = pd.DataFrame(
        [
            {"hypothesis": "H1 relative-format proxy", "verdict": "rejected_proxy", "evidence": f"hit {proxy_h1['selected_hit_rate']:.1%} vs {proxy_h1['other_hit_rate']:.1%}; Mann-Whitney p={proxy_h1['mann_whitney_p']:.3f}", "what_remains": "Original understandability claim needs user research"},
            {"hypothesis": "H2 combined factors", "verdict": "promising_not_confirmed", "evidence": f"paired delta lift {test_lookup['H2 combination vs price-only']['mean_delta_lift']:.3f}; raw p={test_lookup['H2 combination vs price-only']['p_value_one_sided']:.4g}; Holm p={test_lookup['H2 combination vs price-only']['p_value_holm']:.4g}", "what_remains": "Need more independent test periods"},
            {"hypothesis": "H3 rarity/cooldown proxy", "verdict": "rejected_proxy", "evidence": f"precision delta {proxy_h3['precision_delta']:.1%}; CI [{proxy_h3['bootstrap_ci_low']:.1%}, {proxy_h3['bootstrap_ci_high']:.1%}]", "what_remains": "Loyalty needs notification interaction logs"},
            {"hypothesis": "H4 pooled vs per-corridor", "verdict": "inconclusive", "evidence": f"logistic delta lift {test_lookup['H4 pooled vs per-corridor logistic']['mean_delta_lift']:.3f}; Holm p={test_lookup['H4 pooled vs per-corridor logistic']['p_value_holm']:.3f}", "what_remains": "Pooled random forest is the practical candidate"},
            {"hypothesis": "H5 fast vs slow", "verdict": "rejected_for_current_rule", "evidence": f"slow-fast hit delta {proxy_h5['mean_hit_delta_slow_minus_fast']:.1%}; p={proxy_h5['p_value_one_sided']:.3f}", "what_remains": "A different adaptive policy can be tested later"},
            {"hypothesis": "H6 honest UX and trust", "verdict": "not_testable", "evidence": "No user reaction data", "what_remains": "Controlled message test or pilot"},
            {"hypothesis": "H7 CBR vs bank benefit", "verdict": "blocked_by_data", "evidence": "No historical bank rate/spread", "what_remains": "Parallel bank and CBR time series"},
            {"hypothesis": "ML-H006 derivatives", "verdict": "rejected", "evidence": f"median delta lift {test_lookup['Derivatives vs case factors']['median_delta_lift']:.3f}; Holm p={test_lookup['Derivatives vs case factors']['p_value_holm']:.3f}", "what_remains": "Keep only if a later fold shows stable gain"},
            {"hypothesis": "ML-H007 USD/EUR", "verdict": "inconclusive", "evidence": f"mean delta {test_lookup['USD/EUR factors vs derivatives']['mean_delta_lift']:.3f}, median {test_lookup['USD/EUR factors vs derivatives']['median_delta_lift']:.3f}; Holm p={test_lookup['USD/EUR factors vs derivatives']['p_value_holm']:.3f}", "what_remains": "Effect is unstable and driven by a few folds"},
        ]
    )
    verdicts.to_csv(args.output_dir / "hypothesis_verdicts.csv", index=False)

    ranking = benchmark_summary.groupby(["strategy", "model"], as_index=False).agg(
        corridors=("corridor", "nunique"), mean_lift=("lift", "mean"),
        worst_fold_lift=("min_fold_lift", "min"), mean_hit_rate=("signal_hit_rate", "mean"),
        mean_roc_auc=("roc_auc", "mean"), mean_pr_auc=("pr_auc", "mean"),
        mean_brier=("brier", "mean"), mean_frequency=("signals_per_week", "mean"),
    ).sort_values(["mean_lift", "worst_fold_lift"], ascending=False)
    ranking.to_csv(args.output_dir / "model_ranking.csv", index=False)
    make_figures(benchmark_summary, sensitivity_summary, benchmark_predictions, args.output_dir / "figures")

    best = ranking.iloc[0]
    sensitivity_best = sensitivity_summary.groupby(["horizon_days", "epsilon_bps", "strategy"], as_index=False).agg(
        mean_lift=("lift", "mean"), mean_hit_rate=("signal_hit_rate", "mean"),
        mean_frequency=("signals_per_week", "mean"), worst_fold_lift=("min_fold_lift", "min"),
        mean_advantage_bps=("mean_advantage_bps", "mean"), mean_regret_bps=("mean_regret_bps", "mean")
    ).sort_values(["mean_lift", "worst_fold_lift"], ascending=False)
    sensitivity_best.to_csv(args.output_dir / "h_epsilon_summary.csv", index=False)

    report = f"""# Проверка гипотез и benchmark моделей

## Главный вывод

Лучший средний результат benchmark: **{best['model']} / {best['strategy']}**, средний lift по коридорам **{best['mean_lift']:.2f}**, hit rate **{best['mean_hit_rate']:.1%}**, частота **{best['mean_frequency']:.2f} сигнала в неделю**. Выбор финальной модели нельзя делать только по среднему lift: дополнительно смотрим худший временной fold, PR-AUC, Brier score и стабильность между коридорами.

## Зачем нужны эти метрики

- `lift = signal hit rate / matched-random hit rate` отвечает на главный продуктовый вопрос: насколько уведомление лучше случайного дня при той же частоте и cooldown.
- `hit rate` и `false push rate` измеряют правдивость сообщений и риск потери доверия.
- `PR-AUC` проверяет ранжирование полезных моментов и лучше ROC-AUC отражает качество положительного класса.
- `ROC-AUC` остаётся порог-независимой диагностикой разделимости классов.
- `Brier score` показывает качество вероятностного score; он важен, если score позже показывается как надёжность.
- `balanced accuracy` не даёт частому классу полностью определить результат.
- `advantage/regret bps` и их рублёвый эквивалент для перевода 100 000 ₽ связывают ML-ошибки с экономикой клиента. Это proxy на курсе ЦБ, не доказанная выгода по банковскому курсу.

## Benchmark моделей

{markdown_table(ranking)}

## Парные статистические проверки

Сначала lift усредняется по коридорам внутри каждого test-year, затем односторонний Wilcoxon проверяет пять независимых временных блоков. Так общие RUB-шоки не создают искусственную значимость. Поправка Holm контролирует множественные сравнения. Пять лет дают низкую мощность, поэтому практический размер эффекта и устойчивость важнее одного p-value.

{markdown_table(tests_frame)}

## Значимость относительно случайного расписания

Единица теста здесь — календарный test-year: lift сначала усредняется по коридорам, затем проверяется против 1. Поправка Holm применяется ко всем 12 комбинациям модели и стратегии. При пяти test-year минимально достижимый p-value дискретен, поэтому отсутствие `p<0.05` не равнозначно отсутствию практического эффекта.

{markdown_table(random_tests)}

## Гипотезы из исходного документа

{markdown_table(verdicts)}

- **H1 (относительная выгода понятнее): частично проверена только рыночная proxy-версия.** У top-15% исторически выгодных дней hit rate {proxy_h1['selected_hit_rate']:.1%} против {proxy_h1['other_hit_rate']:.1%}; Mann–Whitney p={proxy_h1['mann_whitney_p']:.4g}. Понятность текста и доверие требуют пользовательского теста.
- **H2 (комбинация факторов):** результат в таблице парных тестов сравнивает H002 с price-only на одинаковых фолдах.
- **H3 (редкость): proxy через cooldown.** Precision до фильтра {proxy_h3['precision_before']:.1%}, после {proxy_h3['precision_after']:.1%}, delta {proxy_h3['precision_delta']:.1%}; block-bootstrap 95% CI [{proxy_h3['bootstrap_ci_low']:.1%}, {proxy_h3['bootstrap_ci_high']:.1%}]. Лояльность клиента по рыночным данным измерить нельзя.
- **H4 (единая или отдельные модели):** предзаданный logistic comparison приведён в таблице; оба режима используют одни и те же test-даты.
- **H5 (быстрый или медленный сигнал):** средняя разница hit rate slow-fast {proxy_h5['mean_hit_delta_slow_minus_fast']:.1%}, p={proxy_h5['p_value_one_sided']:.4g}, среднее ожидание {proxy_h5['mean_wait_days']:.2f} дня.
- **H6 (честный UX сохраняет доверие): не проверяема** без логов открытий, жалоб, отключений или controlled user study.
- **H7 (курс ЦБ отражает банковскую выгоду): не проверяема** без параллельного исторического ряда банковского курса и спреда.
- **Новая ML-гипотеза USD/EUR:** H007 сравнивается с H006 без внешних валют в парном тесте. Все USD/EUR признаки присоединены backward-as-of.

## Чувствительность h и epsilon

Формально максимальный lift даёт `h=1, epsilon=0`, но этот режим преимущественно учится распознавать календарные дни, после которых курс ЦБ не обновляется. Его средняя выгода составляет лишь несколько базисных пунктов. Для продуктового MVP разумнее оставить `h=3, epsilon=50 bp`: hit rate около 80%, экономический допуск интерпретируем, а ложный пуш остаётся существенно дороже пропуска. `h=3, epsilon=0` повышает lift ценой hit rate около 55%, что неприемлемо для доверительного push-продукта.

{markdown_table(sensitivity_best.head(20))}

## Ограничения продуктовых выводов

`false push rate`, частота и стабильность по фолдам являются proxy риска раздражения и доверия, но не метриками лояльности. Для реальной оценки нужны delivery/open/click/unsubscribe/transfer logs и банковский курс. Исторический backtest доказывает только качество рыночного сигнала.
"""
    (args.output_dir / "HYPOTHESIS_REPORT.md").write_text(report, encoding="utf-8")
    print(report[:4000])


if __name__ == "__main__":
    main()
