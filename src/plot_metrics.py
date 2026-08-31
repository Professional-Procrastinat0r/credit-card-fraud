from __future__ import annotations

from pathlib import Path
from typing import Any

from expops.reporting import chart


OUTPUT_PATH = Path("fraud_report.png")
SEED_OUTPUT_PATH = Path("fraud_seed_report.png")
DATA_PARALLEL_OUTPUT_PATH = Path("fraud_data_parallel_report.png")
SEED_DATA_OUTPUT_PATH = Path("fraud_seed_data_parallel_report.png")


def _latest_metric(
    metric_block: dict[str, Any],
    metric_name: str,
) -> float | None:
    """Return the value with the greatest numerical metric step."""

    series = metric_block.get(metric_name)

    if isinstance(series, dict):
        points: list[tuple[int, float]] = []

        for raw_step, raw_value in series.items():
            try:
                step = int(raw_step)
                value = float(raw_value)
            except (TypeError, ValueError):
                continue

            points.append((step, value))

        if points:
            return max(points, key=lambda point: point[0])[1]

    if isinstance(series, (int, float)):
        return float(series)

    return None


def _required_metric(
    metric_block: dict[str, Any],
    metric_name: str,
    block_name: str,
) -> float:
    """Retrieve a metric or fail with a useful chart error."""

    value = _latest_metric(metric_block, metric_name)

    if value is None:
        raise ValueError(
            f"Missing metric '{metric_name}' in probe block '{block_name}'."
        )

    return value


def _seed_metric_values(
    metric_block: dict[str, Any],
    metric_name: str,
) -> dict[int, float]:
    """Read metrics whose names encode seed identity, such as ``f1_seed42``."""

    metric_prefix = f"{metric_name}_seed"
    points: dict[int, float] = {}

    for stored_name in metric_block:
        if not str(stored_name).startswith(metric_prefix):
            continue

        raw_seed = str(stored_name)[len(metric_prefix):]

        try:
            seed = int(raw_seed)
        except ValueError:
            continue

        value = _latest_metric(metric_block, str(stored_name))

        if value is not None:
            points[seed] = value

    if not points:
        raise ValueError(
            f"No per-seed metrics found with prefix '{metric_prefix}'."
        )

    return dict(sorted(points.items()))


def _partition_metric_values(
    metric_block: dict[str, Any],
    metric_name: str,
) -> dict[int, float]:
    """Read metrics such as ``partition_test_row_count_data2``."""

    metric_prefix = f"partition_{metric_name}_data"
    points: dict[int, float] = {}

    for stored_name in metric_block:
        if not str(stored_name).startswith(metric_prefix):
            continue

        raw_partition = str(stored_name)[len(metric_prefix):]

        try:
            partition = int(raw_partition)
        except ValueError:
            continue

        value = _latest_metric(metric_block, str(stored_name))

        if value is not None:
            points[partition] = value

    if not points:
        raise ValueError(
            f"No partition metrics found with prefix '{metric_prefix}'."
        )

    return dict(sorted(points.items()))


def _seed_partition_metric_values(
    metric_block: dict[str, Any],
    metric_name: str,
) -> dict[int, dict[int, float]]:
    """Read metrics such as ``partition_test_fraud_count_seed42_data2``."""

    metric_prefix = f"partition_{metric_name}_seed"
    points: dict[int, dict[int, float]] = {}

    for stored_name in metric_block:
        stored_text = str(stored_name)

        if not stored_text.startswith(metric_prefix):
            continue

        identity = stored_text[len(metric_prefix):]

        try:
            raw_seed, raw_partition = identity.split("_data", maxsplit=1)
            seed = int(raw_seed)
            partition = int(raw_partition)
        except (ValueError, TypeError):
            continue

        value = _latest_metric(metric_block, stored_text)

        if value is not None:
            points.setdefault(seed, {})[partition] = value

    if not points:
        raise ValueError(
            f"No seed-partition metrics found with prefix '{metric_prefix}'."
        )

    return {
        seed: dict(sorted(partitions.items()))
        for seed, partitions in sorted(points.items())
    }


def _label_bars(axis, bars) -> None:
    """Place numerical values above a collection of bars."""

    for bar in bars:
        height = float(bar.get_height())

        axis.text(
            bar.get_x() + bar.get_width() / 2,
            height + 0.025,
            f"{height:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )


@chart()
def plot_metrics(metrics: dict[str, Any]) -> None:
    """Create a static report from ExpOps process metrics."""

    if not isinstance(metrics, dict):
        raise TypeError("Expected ExpOps metrics to be a dictionary.")

    validation_metrics = metrics.get("validation")
    training_metrics = metrics.get("train")
    evaluation_metrics = metrics.get("eval")

    if not isinstance(validation_metrics, dict):
        raise ValueError("Missing validation metric probe block.")

    if not isinstance(training_metrics, dict):
        raise ValueError("Missing training metric probe block.")

    if not isinstance(evaluation_metrics, dict):
        raise ValueError("Missing evaluation metric probe block.")

    dataset_fraud_rate = _required_metric(
        validation_metrics,
        "fraud_rate",
        "validation",
    )

    training_average_precision = _required_metric(
        training_metrics,
        "average_precision",
        "train",
    )

    test_average_precision = _required_metric(
        evaluation_metrics,
        "average_precision",
        "eval",
    )

    roc_auc = _required_metric(
        evaluation_metrics,
        "roc_auc",
        "eval",
    )

    precision = _required_metric(
        evaluation_metrics,
        "precision",
        "eval",
    )

    recall = _required_metric(
        evaluation_metrics,
        "recall",
        "eval",
    )

    f1 = _required_metric(
        evaluation_metrics,
        "f1",
        "eval",
    )

    threshold = _required_metric(
        evaluation_metrics,
        "threshold",
        "eval",
    )

    test_row_count = int(
        _required_metric(
            evaluation_metrics,
            "test_row_count",
            "eval",
        )
    )

    test_fraud_count = int(
        _required_metric(
            evaluation_metrics,
            "test_fraud_count",
            "eval",
        )
    )

    test_fraud_prevalence = _required_metric(
        evaluation_metrics,
        "fraud_prevalence",
        "eval",
    )

    predicted_fraud_count = int(
        _required_metric(
            evaluation_metrics,
            "predicted_fraud_count",
            "eval",
        )
    )

    alert_rate = _required_metric(
        evaluation_metrics,
        "alert_rate",
        "eval",
    )

    true_negatives = int(
        _required_metric(
            evaluation_metrics,
            "true_negatives",
            "eval",
        )
    )

    false_positives = int(
        _required_metric(
            evaluation_metrics,
            "false_positives",
            "eval",
        )
    )

    false_negatives = int(
        _required_metric(
            evaluation_metrics,
            "false_negatives",
            "eval",
        )
    )

    true_positives = int(
        _required_metric(
            evaluation_metrics,
            "true_positives",
            "eval",
        )
    )

    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        2,
        2,
        figsize=(12, 8),
    )

    ranking_axis = axes[0, 0]
    threshold_axis = axes[0, 1]
    confusion_axis = axes[1, 0]
    summary_axis = axes[1, 1]

    ranking_labels = [
        "Train AP",
        "Test AP",
        "ROC-AUC",
    ]

    ranking_values = [
        training_average_precision,
        test_average_precision,
        roc_auc,
    ]

    ranking_bars = ranking_axis.bar(
        ranking_labels,
        ranking_values,
        color=["#4C78A8", "#72B7B2", "#F58518"],
    )

    ranking_axis.axhline(
        test_fraud_prevalence,
        color="#E45756",
        linestyle="--",
        linewidth=1.5,
        label="No-skill AP baseline",
    )

    ranking_axis.set_ylim(0.0, 1.05)
    ranking_axis.set_ylabel("Score")
    ranking_axis.set_title("Ranking quality")
    ranking_axis.grid(axis="y", alpha=0.25)
    ranking_axis.legend(loc="lower right")
    _label_bars(ranking_axis, ranking_bars)

    threshold_labels = [
        "Precision",
        "Recall",
        "F1",
    ]

    threshold_values = [
        precision,
        recall,
        f1,
    ]

    threshold_bars = threshold_axis.bar(
        threshold_labels,
        threshold_values,
        color=["#E45756", "#54A24B", "#B279A2"],
    )

    threshold_axis.set_ylim(0.0, 1.05)
    threshold_axis.set_ylabel("Score")
    threshold_axis.set_title(
        f"Threshold-dependent metrics at {threshold:.2f}"
    )
    threshold_axis.grid(axis="y", alpha=0.25)
    _label_bars(threshold_axis, threshold_bars)

    confusion_values = [
        [true_negatives, false_positives],
        [false_negatives, true_positives],
    ]

    confusion_image = confusion_axis.imshow(
        confusion_values,
        cmap="Blues",
    )

    confusion_axis.set_xticks([0, 1])
    confusion_axis.set_xticklabels(
        ["Predicted genuine", "Predicted fraud"]
    )

    confusion_axis.set_yticks([0, 1])
    confusion_axis.set_yticklabels(
        ["Actual genuine", "Actual fraud"]
    )

    confusion_axis.set_title("Confusion matrix")

    largest_count = max(
        true_negatives,
        false_positives,
        false_negatives,
        true_positives,
    )

    for row_index, row in enumerate(confusion_values):
        for column_index, value in enumerate(row):
            text_colour = (
                "white"
                if value > largest_count / 2
                else "black"
            )

            confusion_axis.text(
                column_index,
                row_index,
                f"{value:,}",
                ha="center",
                va="center",
                color=text_colour,
                fontsize=12,
                fontweight="bold",
            )

    figure.colorbar(
        confusion_image,
        ax=confusion_axis,
        fraction=0.046,
        pad=0.04,
    )

    false_alerts_per_detected_fraud = (
        false_positives / true_positives
        if true_positives
        else float("inf")
    )

    summary_lines = [
        f"Decision threshold: {threshold:.2f}",
        "",
        f"Dataset fraud prevalence: {dataset_fraud_rate:.3%}",
        f"Test fraud prevalence: {test_fraud_prevalence:.3%}",
        "",
        f"Test transactions: {test_row_count:,}",
        f"Actual frauds: {test_fraud_count:,}",
        f"Flagged transactions: {predicted_fraud_count:,}",
        f"Alert rate: {alert_rate:.3%}",
        "",
        f"Detected frauds: {true_positives:,}",
        f"Missed frauds: {false_negatives:,}",
        f"False alerts: {false_positives:,}",
        (
            "False alerts per detected fraud: "
            f"{false_alerts_per_detected_fraud:.1f}"
        ),
    ]

    summary_axis.axis("off")
    summary_axis.set_title("Operational summary")

    summary_axis.text(
        0.05,
        0.95,
        "\n".join(summary_lines),
        transform=summary_axis.transAxes,
        ha="left",
        va="top",
        fontsize=11,
        family="monospace",
    )

    figure.suptitle(
        "Credit Card Fraud Detection Report",
        fontsize=16,
        fontweight="bold",
    )

    figure.tight_layout(
        rect=(0.0, 0.0, 1.0, 0.95)
    )

    figure.savefig(
        OUTPUT_PATH,
        dpi=160,
        bbox_inches="tight",
    )

    plt.close(figure)


@chart()
def plot_seed_metrics(metrics: dict[str, Any]) -> None:
    """Visualize metric stability across ExpOps seed branches."""

    if not isinstance(metrics, dict):
        raise TypeError("Expected ExpOps metrics to be a dictionary.")

    seed_metrics = metrics.get("seed_summary")

    if not isinstance(seed_metrics, dict):
        raise ValueError("Missing seed-summary metric probe block.")

    series_names = [
        "average_precision",
        "roc_auc",
        "precision",
        "recall",
        "f1",
        "alert_rate",
    ]

    series = {
        name: _seed_metric_values(seed_metrics, name)
        for name in series_names
    }

    seeds = list(series["average_precision"])
    expected_seeds = set(seeds)

    for metric_name, metric_series in series.items():
        if set(metric_series) != expected_seeds:
            raise ValueError(
                f"Metric '{metric_name}' does not contain the same seeds as "
                "average_precision."
            )

    summary = {
        metric_name: {
            statistic: _required_metric(
                seed_metrics,
                f"{metric_name}_{statistic}",
                "seed_summary",
            )
            for statistic in ("mean", "std", "min", "max")
        }
        for metric_name in series_names
    }

    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(13, 8))
    positions = list(range(len(seeds)))
    seed_labels = [str(seed) for seed in seeds]

    ranking_axis = axes[0, 0]
    ranking_width = 0.35

    ranking_axis.bar(
        [position - ranking_width / 2 for position in positions],
        [series["average_precision"][seed] for seed in seeds],
        width=ranking_width,
        label="Average precision",
        color="#4C78A8",
    )
    ranking_axis.bar(
        [position + ranking_width / 2 for position in positions],
        [series["roc_auc"][seed] for seed in seeds],
        width=ranking_width,
        label="ROC-AUC",
        color="#F58518",
    )
    ranking_axis.set_xticks(positions, seed_labels)
    ranking_axis.set_ylim(0.0, 1.05)
    ranking_axis.set_xlabel("Split seed")
    ranking_axis.set_ylabel("Score")
    ranking_axis.set_title("Ranking quality by seed")
    ranking_axis.grid(axis="y", alpha=0.25)
    ranking_axis.legend(loc="lower right")

    threshold_axis = axes[0, 1]
    threshold_names = ["precision", "recall", "f1"]
    threshold_colours = ["#E45756", "#54A24B", "#B279A2"]
    threshold_width = 0.24

    for metric_index, (metric_name, colour) in enumerate(
        zip(threshold_names, threshold_colours)
    ):
        offset = (metric_index - 1) * threshold_width
        threshold_axis.bar(
            [position + offset for position in positions],
            [series[metric_name][seed] for seed in seeds],
            width=threshold_width,
            label=metric_name.title(),
            color=colour,
        )

    threshold_axis.set_xticks(positions, seed_labels)
    threshold_axis.set_ylim(0.0, 1.05)
    threshold_axis.set_xlabel("Split seed")
    threshold_axis.set_ylabel("Score")
    threshold_axis.set_title("Threshold metrics by seed")
    threshold_axis.grid(axis="y", alpha=0.25)
    threshold_axis.legend(loc="upper right")

    alert_axis = axes[1, 0]
    alert_values = [series["alert_rate"][seed] * 100.0 for seed in seeds]
    alert_bars = alert_axis.bar(
        positions,
        alert_values,
        color="#72B7B2",
    )
    alert_axis.set_xticks(positions, seed_labels)
    alert_axis.set_xlabel("Split seed")
    alert_axis.set_ylabel("Flagged transactions (%)")
    alert_axis.set_title("Operational alert rate")
    alert_axis.grid(axis="y", alpha=0.25)

    for bar, value in zip(alert_bars, alert_values):
        alert_axis.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.2f}%",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    summary_axis = axes[1, 1]
    summary_axis.axis("off")
    summary_axis.set_title("Cross-seed stability")

    summary_lines = [
        "Metric             Mean      Std       Min       Max",
        "-" * 53,
    ]

    display_names = {
        "average_precision": "Average precision",
        "roc_auc": "ROC-AUC",
        "precision": "Precision",
        "recall": "Recall",
        "f1": "F1",
        "alert_rate": "Alert rate",
    }

    for metric_name in series_names:
        statistics = summary[metric_name]
        summary_lines.append(
            f"{display_names[metric_name]:<18} "
            f"{statistics['mean']:>7.4f}   "
            f"{statistics['std']:>7.4f}   "
            f"{statistics['min']:>7.4f}   "
            f"{statistics['max']:>7.4f}"
        )

    summary_axis.text(
        0.02,
        0.92,
        "\n".join(summary_lines),
        transform=summary_axis.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        family="monospace",
    )

    figure.suptitle(
        "Credit Card Fraud Detection: Split-Seed Sensitivity",
        fontsize=16,
        fontweight="bold",
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    figure.savefig(SEED_OUTPUT_PATH, dpi=160, bbox_inches="tight")
    plt.close(figure)


@chart()
def plot_data_parallel_metrics(metrics: dict[str, Any]) -> None:
    """Visualize partition workloads and the exactly aggregated result."""

    if not isinstance(metrics, dict):
        raise TypeError("Expected ExpOps metrics to be a dictionary.")

    data_metrics = metrics.get("data_summary")

    if not isinstance(data_metrics, dict):
        raise ValueError("Missing data-summary metric probe block.")

    partition_metric_names = [
        "test_row_count",
        "test_fraud_count",
        "average_precision",
        "roc_auc",
        "alert_rate",
    ]

    partition_series = {
        name: _partition_metric_values(data_metrics, name)
        for name in partition_metric_names
    }

    partitions = list(partition_series["test_row_count"])
    expected_partitions = set(partitions)

    for metric_name, metric_series in partition_series.items():
        if set(metric_series) != expected_partitions:
            raise ValueError(
                f"Partition metric '{metric_name}' does not contain the same "
                "partitions as test_row_count."
            )

    global_metric_names = [
        "average_precision",
        "roc_auc",
        "precision",
        "recall",
        "f1",
    ]

    global_metrics = {
        name: _required_metric(data_metrics, name, "data_summary")
        for name in global_metric_names
    }

    threshold = _required_metric(
        data_metrics,
        "threshold",
        "data_summary",
    )
    test_row_count = int(
        _required_metric(
            data_metrics,
            "test_row_count",
            "data_summary",
        )
    )
    test_fraud_count = int(
        _required_metric(
            data_metrics,
            "test_fraud_count",
            "data_summary",
        )
    )
    alert_rate = _required_metric(
        data_metrics,
        "alert_rate",
        "data_summary",
    )
    true_positives = int(
        _required_metric(
            data_metrics,
            "true_positives",
            "data_summary",
        )
    )
    false_positives = int(
        _required_metric(
            data_metrics,
            "false_positives",
            "data_summary",
        )
    )
    false_negatives = int(
        _required_metric(
            data_metrics,
            "false_negatives",
            "data_summary",
        )
    )

    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(13, 8))
    positions = list(range(len(partitions)))
    partition_labels = [f"P{partition}" for partition in partitions]

    workload_axis = axes[0, 0]
    row_counts = [
        partition_series["test_row_count"][partition]
        for partition in partitions
    ]
    fraud_counts = [
        int(partition_series["test_fraud_count"][partition])
        for partition in partitions
    ]
    workload_bars = workload_axis.bar(
        positions,
        row_counts,
        color="#4C78A8",
    )
    workload_axis.set_xticks(positions, partition_labels)
    workload_axis.set_ylim(0.0, max(row_counts) * 1.18)
    workload_axis.set_ylabel("Transactions")
    workload_axis.set_title("Partition workload")
    workload_axis.grid(axis="y", alpha=0.25)

    for bar, row_count, fraud_count in zip(
        workload_bars,
        row_counts,
        fraud_counts,
    ):
        workload_axis.text(
            bar.get_x() + bar.get_width() / 2,
            row_count,
            f"{int(row_count):,} rows\n{fraud_count} frauds",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    partition_axis = axes[0, 1]
    partition_width = 0.35
    partition_axis.bar(
        [position - partition_width / 2 for position in positions],
        [
            partition_series["average_precision"][partition]
            for partition in partitions
        ],
        width=partition_width,
        label="Average precision",
        color="#72B7B2",
    )
    partition_axis.bar(
        [position + partition_width / 2 for position in positions],
        [
            partition_series["roc_auc"][partition]
            for partition in partitions
        ],
        width=partition_width,
        label="ROC-AUC",
        color="#F58518",
    )
    partition_axis.set_xticks(positions, partition_labels)
    partition_axis.set_ylim(0.0, 1.05)
    partition_axis.set_ylabel("Score")
    partition_axis.set_title("Local partition metrics")
    partition_axis.grid(axis="y", alpha=0.25)
    partition_axis.legend(loc="lower right")

    global_axis = axes[1, 0]
    global_labels = ["AP", "ROC-AUC", "Precision", "Recall", "F1"]
    global_values = [
        global_metrics["average_precision"],
        global_metrics["roc_auc"],
        global_metrics["precision"],
        global_metrics["recall"],
        global_metrics["f1"],
    ]
    global_bars = global_axis.bar(
        global_labels,
        global_values,
        color=["#4C78A8", "#F58518", "#E45756", "#54A24B", "#B279A2"],
    )
    global_axis.set_ylim(0.0, 1.05)
    global_axis.set_ylabel("Score")
    global_axis.set_title("Exactly aggregated global metrics")
    global_axis.grid(axis="y", alpha=0.25)
    _label_bars(global_axis, global_bars)

    summary_axis = axes[1, 1]
    summary_axis.axis("off")
    summary_axis.set_title("Aggregation summary")

    summary_lines = [
        f"Decision threshold: {threshold:.2f}",
        f"Partitions: {len(partitions)}",
        "",
        f"Recombined transactions: {test_row_count:,}",
        f"Recombined frauds: {test_fraud_count:,}",
        f"Alert rate: {alert_rate:.3%}",
        "",
        f"Detected frauds: {true_positives:,}",
        f"Missed frauds: {false_negatives:,}",
        f"False alerts: {false_positives:,}",
        "",
        "Global AP and ROC-AUC were recomputed",
        "after concatenating all labels and scores.",
        "Partition scores were not averaged.",
    ]

    summary_axis.text(
        0.04,
        0.94,
        "\n".join(summary_lines),
        transform=summary_axis.transAxes,
        ha="left",
        va="top",
        fontsize=10.5,
        family="monospace",
    )

    figure.suptitle(
        "Credit Card Fraud Detection: Data-Parallel Evaluation",
        fontsize=16,
        fontweight="bold",
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    figure.savefig(
        DATA_PARALLEL_OUTPUT_PATH,
        dpi=160,
        bbox_inches="tight",
    )
    plt.close(figure)


@chart()
def plot_seed_data_parallel_metrics(metrics: dict[str, Any]) -> None:
    """Visualize exact per-seed results from nested data-parallel scoring."""

    if not isinstance(metrics, dict):
        raise TypeError("Expected ExpOps metrics to be a dictionary.")

    combined_metrics = metrics.get("combined_summary")

    if not isinstance(combined_metrics, dict):
        raise ValueError("Missing combined-summary metric probe block.")

    metric_names = [
        "average_precision",
        "roc_auc",
        "precision",
        "recall",
        "f1",
        "alert_rate",
    ]
    series = {
        name: _seed_metric_values(combined_metrics, name)
        for name in metric_names
    }
    seeds = list(series["average_precision"])
    expected_seeds = set(seeds)

    for metric_name, metric_series in series.items():
        if set(metric_series) != expected_seeds:
            raise ValueError(
                f"Metric '{metric_name}' does not contain the expected seeds."
            )

    fraud_counts = _seed_partition_metric_values(
        combined_metrics,
        "test_fraud_count",
    )

    if set(fraud_counts) != expected_seeds:
        raise ValueError(
            "Partition fraud-count metrics do not contain the expected seeds."
        )

    partition_sets = {tuple(counts) for counts in fraud_counts.values()}

    if len(partition_sets) != 1:
        raise ValueError("Seeds do not contain the same data partitions.")

    partitions = list(next(iter(fraud_counts.values())))
    summary = {
        metric_name: {
            statistic: _required_metric(
                combined_metrics,
                f"{metric_name}_{statistic}",
                "combined_summary",
            )
            for statistic in ("mean", "std", "min", "max")
        }
        for metric_name in metric_names
    }

    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(13, 8))
    positions = list(range(len(seeds)))
    seed_labels = [str(seed) for seed in seeds]

    ranking_axis = axes[0, 0]
    ranking_width = 0.35
    ranking_axis.bar(
        [position - ranking_width / 2 for position in positions],
        [series["average_precision"][seed] for seed in seeds],
        width=ranking_width,
        label="Average precision",
        color="#4C78A8",
    )
    ranking_axis.bar(
        [position + ranking_width / 2 for position in positions],
        [series["roc_auc"][seed] for seed in seeds],
        width=ranking_width,
        label="ROC-AUC",
        color="#F58518",
    )
    ranking_axis.set_xticks(positions, seed_labels)
    ranking_axis.set_ylim(0.0, 1.05)
    ranking_axis.set_xlabel("Split seed")
    ranking_axis.set_ylabel("Score")
    ranking_axis.set_title("Exactly aggregated ranking metrics")
    ranking_axis.grid(axis="y", alpha=0.25)
    ranking_axis.legend(loc="lower right")

    threshold_axis = axes[0, 1]
    threshold_names = ["precision", "recall", "f1"]
    threshold_colours = ["#E45756", "#54A24B", "#B279A2"]
    threshold_width = 0.24

    for metric_index, (metric_name, colour) in enumerate(
        zip(threshold_names, threshold_colours)
    ):
        offset = (metric_index - 1) * threshold_width
        threshold_axis.bar(
            [position + offset for position in positions],
            [series[metric_name][seed] for seed in seeds],
            width=threshold_width,
            label=metric_name.title(),
            color=colour,
        )

    threshold_axis.set_xticks(positions, seed_labels)
    threshold_axis.set_ylim(0.0, 1.05)
    threshold_axis.set_xlabel("Split seed")
    threshold_axis.set_ylabel("Score")
    threshold_axis.set_title("Exactly aggregated threshold metrics")
    threshold_axis.grid(axis="y", alpha=0.25)
    threshold_axis.legend(loc="upper right")

    partition_axis = axes[1, 0]
    partition_width = 0.22
    partition_colours = ["#72B7B2", "#FF9DA6", "#9D755D"]

    for partition_index, partition in enumerate(partitions):
        offset = (
            partition_index - (len(partitions) - 1) / 2
        ) * partition_width
        partition_axis.bar(
            [position + offset for position in positions],
            [fraud_counts[seed][partition] for seed in seeds],
            width=partition_width,
            label=f"P{partition}",
            color=partition_colours[partition_index % len(partition_colours)],
        )

    partition_axis.set_xticks(positions, seed_labels)
    partition_axis.set_xlabel("Split seed")
    partition_axis.set_ylabel("Held-out frauds")
    partition_axis.set_title("Fraud distribution across data partitions")
    partition_axis.grid(axis="y", alpha=0.25)
    partition_axis.legend(loc="upper left")

    summary_axis = axes[1, 1]
    summary_axis.axis("off")
    summary_axis.set_title("Cross-seed stability after exact aggregation")
    summary_lines = [
        "Metric             Mean      Std       Min       Max",
        "-" * 53,
    ]
    display_names = {
        "average_precision": "Average precision",
        "roc_auc": "ROC-AUC",
        "precision": "Precision",
        "recall": "Recall",
        "f1": "F1",
        "alert_rate": "Alert rate",
    }

    for metric_name in metric_names:
        statistics = summary[metric_name]
        summary_lines.append(
            f"{display_names[metric_name]:<18} "
            f"{statistics['mean']:>7.4f}   "
            f"{statistics['std']:>7.4f}   "
            f"{statistics['min']:>7.4f}   "
            f"{statistics['max']:>7.4f}"
        )

    summary_axis.text(
        0.02,
        0.92,
        "\n".join(summary_lines),
        transform=summary_axis.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        family="monospace",
    )

    figure.suptitle(
        "Credit Card Fraud Detection: Seed + Data Parallelism",
        fontsize=16,
        fontweight="bold",
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    figure.savefig(
        SEED_DATA_OUTPUT_PATH,
        dpi=160,
        bbox_inches="tight",
    )
    plt.close(figure)
