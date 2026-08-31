from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from expops.core import log_metric, process


DATA_PATH = Path("data/creditcard.csv")
TARGET_COLUMN = "Class"

FEATURE_COLUMNS = [
    "Time",
    *[f"V{i}" for i in range(1, 29)],
    "Amount",
]

EXPECTED_COLUMNS = FEATURE_COLUMNS + [TARGET_COLUMN]

SEED_SUMMARY_METRICS = (
    "average_precision",
    "roc_auc",
    "precision",
    "recall",
    "f1",
    "alert_rate",
)


def _load_train_test(
    data_path: str,
    test_size: float,
    random_seed: int,
):
    """Load the dataset and produce a deterministic stratified split."""

    path = Path(data_path)

    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found at {path}")

    if not 0.0 < float(test_size) < 1.0:
        raise ValueError(
            f"test_size must be between 0 and 1, got {test_size}"
        )

    df = pd.read_csv(path)

    x = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN].astype(int)

    return train_test_split(
        x,
        y,
        test_size=float(test_size),
        random_state=int(random_seed),
        stratify=y,
    )


def _seed_number(seed_key: Any) -> int:
    """Convert ExpOps aggregation keys such as ``seed42`` to integers."""

    if isinstance(seed_key, int):
        return seed_key

    text = str(seed_key)

    if text.startswith("seed"):
        text = text[4:]

    try:
        return int(text)
    except ValueError as error:
        raise ValueError(
            f"Expected a seed aggregation key such as 'seed42', got {seed_key!r}."
        ) from error


def _summarize_seed_metrics(
    evaluation_metrics: dict[str, dict[str, Any]],
) -> tuple[dict[int, dict[str, float]], dict[str, dict[str, float]]]:
    """Validate per-seed metrics and calculate stability statistics."""

    if not isinstance(evaluation_metrics, dict) or not evaluation_metrics:
        raise ValueError("Expected evaluation metrics from at least one seed branch.")

    results_by_seed: dict[int, dict[str, float]] = {}

    for seed_key, raw_metrics in evaluation_metrics.items():
        if not isinstance(raw_metrics, dict):
            raise TypeError(
                f"Expected metrics for branch {seed_key!r} to be a dictionary."
            )

        seed = _seed_number(raw_metrics.get("random_seed", seed_key))

        if seed in results_by_seed:
            raise ValueError(f"Received duplicate metrics for seed {seed}.")

        normalized_metrics: dict[str, float] = {}

        for metric_name in SEED_SUMMARY_METRICS:
            if metric_name not in raw_metrics:
                raise ValueError(
                    f"Seed {seed} is missing required metric '{metric_name}'."
                )

            try:
                metric_value = float(raw_metrics[metric_name])
            except (TypeError, ValueError) as error:
                raise TypeError(
                    f"Metric '{metric_name}' for seed {seed} must be numerical."
                ) from error

            if not np.isfinite(metric_value):
                raise ValueError(
                    f"Metric '{metric_name}' for seed {seed} is not finite."
                )

            normalized_metrics[metric_name] = metric_value

        results_by_seed[seed] = normalized_metrics

    ordered_results = dict(sorted(results_by_seed.items()))
    summary: dict[str, dict[str, float]] = {}

    for metric_name in SEED_SUMMARY_METRICS:
        values = np.asarray(
            [metrics[metric_name] for metrics in ordered_results.values()],
            dtype=float,
        )

        summary[metric_name] = {
            "mean": float(values.mean()),
            "std": float(values.std(ddof=0)),
            "min": float(values.min()),
            "max": float(values.max()),
        }

    return ordered_results, summary


@process()
def validate_data():
    """Validate the fraud dataset and expose its path to downstream processes."""

    if not DATA_PATH.is_file():
        raise FileNotFoundError(
            f"Dataset not found at {DATA_PATH}. "
            "Expected data/creditcard.csv inside the project."
        )

    df = pd.read_csv(DATA_PATH)

    if df.empty:
        raise ValueError("The fraud dataset is empty.")

    actual_columns = set(df.columns)
    expected_columns = set(EXPECTED_COLUMNS)

    missing_columns = sorted(expected_columns - actual_columns)
    unexpected_columns = sorted(actual_columns - expected_columns)

    if missing_columns or unexpected_columns:
        raise ValueError(
            "Dataset schema does not match the expected credit-card schema. "
            f"Missing columns: {missing_columns}. "
            f"Unexpected columns: {unexpected_columns}."
        )

    columns_with_missing_values = sorted(
        column for column in EXPECTED_COLUMNS if df[column].isna().any()
    )

    if columns_with_missing_values:
        raise ValueError(
            "Dataset contains missing values in columns: "
            f"{columns_with_missing_values}"
        )

    non_numeric_columns = sorted(
        column
        for column in EXPECTED_COLUMNS
        if not is_numeric_dtype(df[column])
    )

    if non_numeric_columns:
        raise ValueError(
            f"Expected numerical columns, but found: {non_numeric_columns}"
        )

    feature_values = df[FEATURE_COLUMNS].to_numpy(
        dtype=float,
        copy=False,
    )

    if not np.isfinite(feature_values).all():
        raise ValueError(
            "Feature columns contain infinite or non-finite values."
        )

    labels = set(df[TARGET_COLUMN].unique().tolist())

    if labels != {0, 1}:
        raise ValueError(
            "Class must contain both binary labels 0 and 1. "
            f"Found labels: {sorted(labels)}"
        )

    row_count = int(len(df))
    fraud_count = int((df[TARGET_COLUMN] == 1).sum())
    genuine_count = int((df[TARGET_COLUMN] == 0).sum())
    fraud_rate = float(fraud_count / row_count)

    log_metric("row_count", float(row_count))
    log_metric("fraud_count", float(fraud_count))
    log_metric("genuine_count", float(genuine_count))
    log_metric("fraud_rate", fraud_rate)

    return {
        "data_path": DATA_PATH.as_posix(),
        "row_count": row_count,
        "fraud_count": fraud_count,
        "genuine_count": genuine_count,
        "fraud_rate": fraud_rate,
    }


@process()
def train_model(
    data_path,
    test_size,
    random_seed,
    max_iter,
    class_weight,
):
    """Fit a class-weighted logistic-regression fraud classifier."""

    x_train, _, y_train, _ = _load_train_test(
        data_path=data_path,
        test_size=test_size,
        random_seed=random_seed,
    )

    model = Pipeline(
        steps=[
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "classifier",
                LogisticRegression(
                    class_weight=class_weight,
                    max_iter=int(max_iter),
                    random_state=int(random_seed),
                ),
            ),
        ]
    )

    model.fit(x_train, y_train)

    train_fraud_scores = model.predict_proba(x_train)[:, 1]

    train_average_precision = float(
        average_precision_score(
            y_train,
            train_fraud_scores,
        )
    )

    classifier = model.named_steps["classifier"]
    iterations = int(classifier.n_iter_[0])

    log_metric("training_row_count", float(len(y_train)))
    log_metric("training_fraud_count", float(y_train.sum()))
    log_metric("average_precision", train_average_precision)
    log_metric("iterations", float(iterations))

    return {
        "model": model,
        "data_path": str(data_path),
        "test_size": float(test_size),
        "random_seed": int(random_seed),
    }


@process()
def evaluate_model(
    model,
    data_path,
    test_size,
    random_seed,
    threshold,
):
    """Evaluate the fitted model on the held-out test partition."""

    if model is None or not hasattr(model, "predict_proba"):
        raise TypeError(
            "Expected a fitted classifier with predict_proba()."
        )

    threshold = float(threshold)

    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            f"threshold must be between 0 and 1, got {threshold}"
        )

    _, x_test, _, y_test = _load_train_test(
        data_path=data_path,
        test_size=test_size,
        random_seed=random_seed,
    )

    fraud_scores = model.predict_proba(x_test)[:, 1]

    predicted_labels = (
        fraud_scores >= threshold
    ).astype(int)

    average_precision = float(
        average_precision_score(
            y_test,
            fraud_scores,
        )
    )

    roc_auc = float(
        roc_auc_score(
            y_test,
            fraud_scores,
        )
    )

    precision = float(
        precision_score(
            y_test,
            predicted_labels,
            zero_division=0,
        )
    )

    recall = float(
        recall_score(
            y_test,
            predicted_labels,
            zero_division=0,
        )
    )

    f1 = float(
        f1_score(
            y_test,
            predicted_labels,
            zero_division=0,
        )
    )

    true_negatives, false_positives, false_negatives, true_positives = (
        confusion_matrix(
            y_test,
            predicted_labels,
            labels=[0, 1],
        ).ravel()
    )

    test_row_count = int(len(y_test))
    test_fraud_count = int(y_test.sum())
    fraud_prevalence = float(y_test.mean())
    predicted_fraud_count = int(predicted_labels.sum())
    alert_rate = float(predicted_labels.mean())

    evaluation_metrics = {
        "random_seed": int(random_seed),
        "test_row_count": test_row_count,
        "test_fraud_count": test_fraud_count,
        "fraud_prevalence": fraud_prevalence,
        "average_precision": average_precision,
        "roc_auc": roc_auc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_negatives": int(true_negatives),
        "false_positives": int(false_positives),
        "false_negatives": int(false_negatives),
        "true_positives": int(true_positives),
        "predicted_fraud_count": predicted_fraud_count,
        "alert_rate": alert_rate,
        "threshold": threshold,
    }

    for metric_name, metric_value in evaluation_metrics.items():
        log_metric(metric_name, float(metric_value))

    return {
        "evaluation_metrics": evaluation_metrics,
    }


@process()
def aggregate_seed_metrics(evaluation_metrics):
    """Collapse the seed branches and report cross-seed stability."""

    results_by_seed, summary = _summarize_seed_metrics(evaluation_metrics)

    for seed, seed_metrics in results_by_seed.items():
        for metric_name, metric_value in seed_metrics.items():
            log_metric(
                f"{metric_name}_seed{seed}",
                metric_value,
            )

    for metric_name, statistics in summary.items():
        for statistic_name, statistic_value in statistics.items():
            log_metric(
                f"{metric_name}_{statistic_name}",
                statistic_value,
            )

    log_metric("seed_count", float(len(results_by_seed)))

    return {
        "seed_results": {
            f"seed{seed}": metrics
            for seed, metrics in results_by_seed.items()
        },
        "seed_summary": summary,
    }


def _calculate_binary_metrics(
    labels: Any,
    fraud_scores: Any,
    threshold: float,
) -> dict[str, float | int]:
    """Calculate exact binary-classification metrics from labels and scores."""

    label_values = np.asarray(labels, dtype=int).reshape(-1)
    score_values = np.asarray(fraud_scores, dtype=float).reshape(-1)
    threshold = float(threshold)

    if label_values.size == 0:
        raise ValueError("Cannot evaluate an empty set of rows.")

    if label_values.size != score_values.size:
        raise ValueError(
            "Labels and fraud scores must contain the same number of rows."
        )

    if set(np.unique(label_values).tolist()) != {0, 1}:
        raise ValueError(
            "Every evaluation partition must contain both genuine and fraud labels."
        )

    if not np.isfinite(score_values).all():
        raise ValueError("Fraud scores contain non-finite values.")

    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            f"threshold must be between 0 and 1, got {threshold}"
        )

    predicted_labels = (score_values >= threshold).astype(int)

    true_negatives, false_positives, false_negatives, true_positives = (
        confusion_matrix(
            label_values,
            predicted_labels,
            labels=[0, 1],
        ).ravel()
    )

    return {
        "test_row_count": int(label_values.size),
        "test_fraud_count": int(label_values.sum()),
        "fraud_prevalence": float(label_values.mean()),
        "average_precision": float(
            average_precision_score(label_values, score_values)
        ),
        "roc_auc": float(roc_auc_score(label_values, score_values)),
        "precision": float(
            precision_score(
                label_values,
                predicted_labels,
                zero_division=0,
            )
        ),
        "recall": float(
            recall_score(
                label_values,
                predicted_labels,
                zero_division=0,
            )
        ),
        "f1": float(
            f1_score(
                label_values,
                predicted_labels,
                zero_division=0,
            )
        ),
        "true_negatives": int(true_negatives),
        "false_positives": int(false_positives),
        "false_negatives": int(false_negatives),
        "true_positives": int(true_positives),
        "predicted_fraud_count": int(predicted_labels.sum()),
        "alert_rate": float(predicted_labels.mean()),
        "threshold": threshold,
    }


def _partition_number(partition_key: Any) -> int:
    """Convert ExpOps aggregation keys such as ``data2`` to integers."""

    if isinstance(partition_key, int):
        return partition_key

    text = str(partition_key)

    if text.startswith("data"):
        text = text[4:]

    try:
        return int(text)
    except ValueError as error:
        raise ValueError(
            "Expected a data aggregation key such as "
            f"'data2', got {partition_key!r}."
        ) from error


@process()
def prepare_evaluation_data(
    model,
    data_path,
    test_size,
    random_seed,
):
    """Materialize the held-out rows that ExpOps will partition."""

    if model is None or not hasattr(model, "predict_proba"):
        raise TypeError(
            "Expected a fitted classifier with predict_proba()."
        )

    _, x_test, _, y_test = _load_train_test(
        data_path=data_path,
        test_size=test_size,
        random_seed=random_seed,
    )

    evaluation_rows = x_test.reset_index(drop=True).copy()
    evaluation_rows[TARGET_COLUMN] = y_test.reset_index(drop=True).astype(int)

    log_metric("evaluation_row_count", float(len(evaluation_rows)))
    log_metric(
        "evaluation_fraud_count",
        float(evaluation_rows[TARGET_COLUMN].sum()),
    )

    return {
        "model": model,
        "evaluation_rows": evaluation_rows,
        "random_seed": int(random_seed),
    }


@process()
def evaluate_partition(
    model,
    evaluation_rows,
    random_seed,
    threshold,
):
    """Score one ExpOps data partition and retain inputs for exact aggregation."""

    if model is None or not hasattr(model, "predict_proba"):
        raise TypeError(
            "Expected a fitted classifier with predict_proba()."
        )

    if isinstance(evaluation_rows, pd.DataFrame):
        evaluation_frame = evaluation_rows
    else:
        row_values = np.asarray(evaluation_rows)

        if (
            row_values.ndim != 2
            or row_values.shape[1] != len(EXPECTED_COLUMNS)
        ):
            raise TypeError(
                "Expected evaluation_rows to be a DataFrame or a two-dimensional "
                f"array with {len(EXPECTED_COLUMNS)} columns; got shape "
                f"{getattr(row_values, 'shape', None)}."
            )

        evaluation_frame = pd.DataFrame(
            row_values,
            columns=EXPECTED_COLUMNS,
        )

    missing_columns = sorted(
        set(EXPECTED_COLUMNS) - set(evaluation_frame.columns)
    )

    if missing_columns:
        raise ValueError(
            f"Evaluation partition is missing columns: {missing_columns}"
        )

    labels = evaluation_frame[TARGET_COLUMN].to_numpy(dtype=int)
    fraud_scores = model.predict_proba(
        evaluation_frame[FEATURE_COLUMNS]
    )[:, 1]

    partition_metrics = _calculate_binary_metrics(
        labels=labels,
        fraud_scores=fraud_scores,
        threshold=threshold,
    )

    for metric_name, metric_value in partition_metrics.items():
        log_metric(metric_name, float(metric_value))

    return {
        "partition_evaluation": {
            "random_seed": int(random_seed),
            "metrics": partition_metrics,
            "labels": labels.tolist(),
            "fraud_scores": fraud_scores.tolist(),
        },
    }


@process()
def aggregate_partition_metrics(partition_evaluation):
    """Collapse partition outputs and reconstruct exact global metrics."""

    if not isinstance(partition_evaluation, dict) or not partition_evaluation:
        raise ValueError(
            "Expected evaluation output from at least one data partition."
        )

    partitions: dict[int, dict[str, Any]] = {}
    random_seeds: set[int] = set()

    for partition_key, raw_partition in partition_evaluation.items():
        partition = _partition_number(partition_key)

        if partition in partitions:
            raise ValueError(
                f"Received duplicate evaluation output for partition {partition}."
            )

        if not isinstance(raw_partition, dict):
            raise TypeError(
                f"Expected partition {partition} output to be a dictionary."
            )

        metrics = raw_partition.get("metrics")
        labels = raw_partition.get("labels")
        fraud_scores = raw_partition.get("fraud_scores")

        try:
            random_seed = int(raw_partition["random_seed"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Partition {partition} is missing a valid random seed."
            ) from error

        random_seeds.add(random_seed)

        if not isinstance(metrics, dict):
            raise ValueError(
                f"Partition {partition} is missing its metric summary."
            )

        label_values = np.asarray(labels, dtype=int).reshape(-1)
        score_values = np.asarray(fraud_scores, dtype=float).reshape(-1)

        if label_values.size != score_values.size:
            raise ValueError(
                f"Partition {partition} labels and scores have different lengths."
            )

        if int(metrics.get("test_row_count", -1)) != label_values.size:
            raise ValueError(
                f"Partition {partition} row count does not match its payload."
            )

        partitions[partition] = {
            "metrics": metrics,
            "labels": label_values,
            "fraud_scores": score_values,
        }

    ordered_partitions = dict(sorted(partitions.items()))
    thresholds = {
        float(partition["metrics"]["threshold"])
        for partition in ordered_partitions.values()
    }

    if len(thresholds) != 1:
        raise ValueError(
            "All data partitions must use the same decision threshold."
        )

    if len(random_seeds) != 1:
        raise ValueError(
            "All data partitions must originate from the same random seed."
        )

    all_labels = np.concatenate(
        [partition["labels"] for partition in ordered_partitions.values()]
    )
    all_scores = np.concatenate(
        [partition["fraud_scores"] for partition in ordered_partitions.values()]
    )

    global_metrics = _calculate_binary_metrics(
        labels=all_labels,
        fraud_scores=all_scores,
        threshold=thresholds.pop(),
    )
    global_metrics["random_seed"] = random_seeds.pop()

    partition_summaries: dict[str, dict[str, float | int]] = {}

    for partition, partition_payload in ordered_partitions.items():
        metrics = partition_payload["metrics"]
        partition_name = f"data{partition}"
        partition_summaries[partition_name] = metrics

        for metric_name in (
            "test_row_count",
            "test_fraud_count",
            "average_precision",
            "roc_auc",
            "alert_rate",
        ):
            log_metric(
                f"partition_{metric_name}_{partition_name}",
                float(metrics[metric_name]),
            )

    for metric_name, metric_value in global_metrics.items():
        log_metric(metric_name, float(metric_value))

    log_metric("partition_count", float(len(ordered_partitions)))

    return {
        "global_evaluation_metrics": global_metrics,
        "partition_summaries": partition_summaries,
    }


@process()
def aggregate_seed_data_metrics(
    global_evaluation_metrics,
    partition_summaries,
):
    """Summarize exact per-seed results after each seed's data aggregation."""

    results_by_seed, summary = _summarize_seed_metrics(
        global_evaluation_metrics
    )

    if not isinstance(partition_summaries, dict) or not partition_summaries:
        raise ValueError(
            "Expected partition summaries from at least one seed branch."
        )

    partitions_by_seed: dict[int, dict[str, dict[str, float | int]]] = {}

    for seed_key, raw_partitions in partition_summaries.items():
        seed_metrics = global_evaluation_metrics.get(seed_key)

        if not isinstance(seed_metrics, dict):
            raise ValueError(
                f"Seed branch {seed_key!r} has partitions but no global metrics."
            )

        seed = _seed_number(seed_metrics.get("random_seed", seed_key))

        if not isinstance(raw_partitions, dict) or not raw_partitions:
            raise ValueError(
                f"Seed {seed} does not contain any partition summaries."
            )

        normalized_partitions: dict[str, dict[str, float | int]] = {}

        for partition_key, raw_metrics in raw_partitions.items():
            partition = _partition_number(partition_key)
            partition_name = f"data{partition}"

            if not isinstance(raw_metrics, dict):
                raise TypeError(
                    f"Seed {seed} partition {partition} metrics must be a dictionary."
                )

            normalized_metrics: dict[str, float | int] = {}

            for metric_name, metric_value in raw_metrics.items():
                if not isinstance(metric_value, (int, float)):
                    continue

                normalized_metrics[metric_name] = metric_value

            normalized_partitions[partition_name] = normalized_metrics

            for metric_name in (
                "test_row_count",
                "test_fraud_count",
                "average_precision",
                "roc_auc",
                "alert_rate",
            ):
                if metric_name not in normalized_metrics:
                    raise ValueError(
                        f"Seed {seed} partition {partition} is missing "
                        f"required metric '{metric_name}'."
                    )

                log_metric(
                    f"partition_{metric_name}_seed{seed}_{partition_name}",
                    float(normalized_metrics[metric_name]),
                )

        partitions_by_seed[seed] = dict(
            sorted(
                normalized_partitions.items(),
                key=lambda item: _partition_number(item[0]),
            )
        )

    if set(partitions_by_seed) != set(results_by_seed):
        raise ValueError(
            "The seed sets for global metrics and partition summaries differ."
        )

    for seed, seed_metrics in results_by_seed.items():
        for metric_name, metric_value in seed_metrics.items():
            log_metric(
                f"{metric_name}_seed{seed}",
                metric_value,
            )

    for metric_name, statistics in summary.items():
        for statistic_name, statistic_value in statistics.items():
            log_metric(
                f"{metric_name}_{statistic_name}",
                statistic_value,
            )

    log_metric("seed_count", float(len(results_by_seed)))
    log_metric(
        "partition_count_per_seed",
        float(len(next(iter(partitions_by_seed.values())))),
    )

    return {
        "seed_results": {
            f"seed{seed}": metrics
            for seed, metrics in results_by_seed.items()
        },
        "seed_summary": summary,
        "seed_partition_summaries": {
            f"seed{seed}": partitions
            for seed, partitions in sorted(partitions_by_seed.items())
        },
    }
