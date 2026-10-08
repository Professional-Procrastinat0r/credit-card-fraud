"""Single-seed VFS control, independent of the legacy nested experiment.

The statistical procedure matches the seed-42 control: stratified holdout,
training-only scaling, balanced logistic regression, and held-out evaluation.
Only the execution graph changes; this is not a parallelism benchmark.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
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
from expops.reporting import chart

FEATURE_COLUMNS = ["Time", *[f"V{i}" for i in range(1, 29)], "Amount"]
TARGET_COLUMN = "Class"
REPORT_METRICS = (
    "average_precision",
    "roc_auc",
    "precision",
    "recall",
    "f1",
    "alert_rate",
)


def read_transactions(context):
    """Read the materialized input chosen by project YAML, as before VFS."""
    if context is None or "training" not in getattr(context, "data_paths", {}):
        raise ValueError("Fraud baseline requires the training input")
    frame = pd.read_csv(context.data_paths["training"])
    expected = set(FEATURE_COLUMNS + [TARGET_COLUMN])
    if (
        frame.empty
        or set(frame.columns) != expected
        or len(frame.columns) != len(expected)
    ):
        raise ValueError("Fraud dataset must have exactly the expected 31 columns")
    if any(not pd.api.types.is_numeric_dtype(frame[column]) for column in frame):
        raise ValueError("Fraud dataset columns must be numeric")
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Fraud dataset must contain only finite, nonmissing values")
    if set(frame[TARGET_COLUMN].unique()) != {0, 1}:
        raise ValueError("Fraud dataset must contain both binary classes")
    return frame


def split_transactions(context, test_size, random_seed):
    """Repeat the same deterministic split in training and evaluation workers."""
    if not 0 < float(test_size) < 1:
        raise ValueError("test_size must be between zero and one")
    frame = read_transactions(context)
    features = frame[FEATURE_COLUMNS]
    labels = frame[TARGET_COLUMN].astype(int)
    split = train_test_split(
        features,
        labels,
        test_size=float(test_size),
        random_state=int(random_seed),
        stratify=labels,
    )
    if any(set(part.unique()) != {0, 1} for part in split[2:]):
        raise ValueError("Both holdout partitions must contain both classes")
    return split


@process()
def train_model(test_size, random_seed, max_iter, class_weight, context=None):
    """Fit one scaler/classifier on the training partition only."""
    x_train, _, y_train, _ = split_transactions(context, test_size, random_seed)
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
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
    result = {
        # ExpOps persists this supported sklearn model and transports a reference.
        "model": model,
        "test_size": float(test_size),
        "random_seed": int(random_seed),
        "training_row_count": int(len(y_train)),
        "training_fraud_count": int(y_train.sum()),
        "average_precision": float(
            average_precision_score(
                y_train,
                model.predict_proba(x_train)[:, 1],
            )
        ),
        "iterations": int(model.named_steps["classifier"].n_iter_[0]),
    }
    for name in (
        "training_row_count",
        "training_fraud_count",
        "average_precision",
        "iterations",
    ):
        log_metric(name, float(result[name]))
    return result


@process()
def evaluate_model(model, test_size, random_seed, threshold, context=None):
    """Compute global held-out metrics, not averages of row-partition metrics."""
    if not 0 <= float(threshold) <= 1:
        raise ValueError("threshold must be between zero and one")
    _, x_test, _, y_test = split_transactions(context, test_size, random_seed)
    scores = model.predict_proba(x_test)[:, 1]
    predictions = (scores >= float(threshold)).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, predictions, labels=[0, 1]).ravel()
    result = {
        "random_seed": int(random_seed),
        "test_row_count": int(len(y_test)),
        "test_fraud_count": int(y_test.sum()),
        "fraud_prevalence": float(y_test.mean()),
        "average_precision": float(average_precision_score(y_test, scores)),
        "roc_auc": float(roc_auc_score(y_test, scores)),
        "precision": float(precision_score(y_test, predictions, zero_division=0)),
        "recall": float(recall_score(y_test, predictions, zero_division=0)),
        "f1": float(f1_score(y_test, predictions, zero_division=0)),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
        "predicted_fraud_count": int(predictions.sum()),
        "alert_rate": float(predictions.mean()),
        "threshold": float(threshold),
    }
    for name, value in result.items():
        log_metric(name, float(value))
    return result


@chart()
def report(metrics, ctx):
    """Render current-run histories, including replayed cached evaluation."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    values = [float(metrics["evaluation"][name]["1"]) for name in REPORT_METRICS]
    if not all(np.isfinite(value) and 0 <= value <= 1 for value in values):
        raise ValueError("Fraud report requires finite evaluation metrics in [0, 1]")
    figure = Figure(figsize=(9, 4))
    FigureCanvasAgg(figure)
    try:
        axis = figure.subplots()
        axis.bar([name.replace("_", "\n") for name in REPORT_METRICS], values)
        axis.set_ylim(0, 1)
        axis.set_ylabel("Held-out score / fraction")
        seed = int(metrics["evaluation"]["random_seed"]["1"])
        threshold = float(metrics["evaluation"]["threshold"]["1"])
        axis.set_title(f"Fraud VFS baseline: seed {seed}, threshold {threshold:g}")
        figure.tight_layout()
        # The platform selects temporary output and publishes to /artefact.
        figure.savefig(ctx.output_dir / "fraud_baseline.png", format="png")
    finally:
        figure.clear()
