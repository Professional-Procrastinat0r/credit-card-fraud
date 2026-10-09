"""Offline statistical controls for the canonical nested experiment."""

import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def model():
    from expops.core.runtime.step_system import isolated_step_registries
    with isolated_step_registries():
        module = load_module("fraud_model_control", ROOT / "src/model.py")
        module.log_metric = lambda *args: None
        yield module


def synthetic_transactions(rows=120):
    rng = np.random.default_rng(42)
    features = rng.normal(size=(rows, 30))
    labels = np.tile([0, 0, 0, 1], rows // 4)
    features[:, 1] += labels * 1.5
    frame = pd.DataFrame(features, columns=["Time", *[f"V{i}" for i in range(1, 29)], "Amount"])
    frame["Class"] = labels
    return frame


def context_for(frame, tmp_path):
    path = tmp_path / "training.csv"
    frame.to_csv(path, index=False)
    return SimpleNamespace(data_paths={"training": path})


@pytest.mark.parametrize("failure", ["empty", "missing-column", "extra-column", "nonnumeric", "nan", "inf", "one-class", "nonbinary"])
def test_invalid_dataset_is_rejected(model, failure, tmp_path):
    frame = synthetic_transactions()
    if failure == "empty":
        frame = frame.iloc[:0]
    elif failure == "missing-column":
        frame = frame.drop(columns="V1")
    elif failure == "extra-column":
        frame["extra"] = 1
    elif failure == "nonnumeric":
        frame["V1"] = "not-a-number"
    elif failure in {"nan", "inf"}:
        frame.loc[0, "V1"] = float(failure)
    elif failure == "one-class":
        frame["Class"] = 0
    else:
        frame.loc[0, "Class"] = 2
    with pytest.raises(ValueError):
        inspect.unwrap(model.validate_data)(context=context_for(frame, tmp_path))


def test_missing_declared_input_does_not_guess_a_native_file(model, tmp_path, monkeypatch):
    synthetic_transactions().to_csv(tmp_path / "creditcard.csv", index=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(KeyError, match="not supplied"):
        inspect.unwrap(model.validate_data)(context=SimpleNamespace(data_paths={}))


@pytest.mark.parametrize("seed", [41, 42, 43])
def test_partition_aggregation_matches_unsplit_holdout_and_train_only_scaling(model, seed, tmp_path):
    context = context_for(synthetic_transactions(), tmp_path)
    trained = inspect.unwrap(model.train_model)(
        data_source="training", test_size=0.2, random_seed=seed,
        max_iter=1000, class_weight="balanced", context=context,
    )
    x_train, _, _, _ = model._load_train_test(context.data_paths["training"], 0.2, seed)
    np.testing.assert_allclose(trained["model"].named_steps["scaler"].mean_, x_train.mean())
    heldout = inspect.unwrap(model.prepare_evaluation_data)(**trained, context=context)
    partitions = {}
    for index, rows in enumerate(np.array_split(np.arange(len(heldout["evaluation_rows"])), 3), start=1):
        partitions[f"data{index}"] = inspect.unwrap(model.evaluate_partition)(
            model=trained["model"], evaluation_rows=heldout["evaluation_rows"].iloc[rows],
            random_seed=seed, threshold=0.5,
        )["partition_evaluation"]
    exact = inspect.unwrap(model.aggregate_partition_metrics)(partitions)["global_evaluation_metrics"]
    control = inspect.unwrap(model.evaluate_model)(**trained, threshold=0.5, context=context)["evaluation_metrics"]
    assert exact == control
    assert sum(partition["metrics"]["test_row_count"] for partition in partitions.values()) == control["test_row_count"]


def test_seed_summary_retains_real_seeds_and_chart_renders(model, tmp_path, monkeypatch):
    context = context_for(synthetic_transactions(), tmp_path)
    globals_by_seed, partitions_by_seed = {}, {}
    for ordinal, seed in enumerate((41, 42, 43), start=1):
        trained = inspect.unwrap(model.train_model)("training", 0.2, seed, 1000, "balanced", context=context)
        heldout = inspect.unwrap(model.prepare_evaluation_data)(**trained, context=context)
        partition_outputs = {
            f"data{index}": inspect.unwrap(model.evaluate_partition)(
                trained["model"], heldout["evaluation_rows"].iloc[rows], seed, 0.5
            )["partition_evaluation"]
            for index, rows in enumerate(np.array_split(np.arange(len(heldout["evaluation_rows"])), 3), start=1)
        }
        aggregated = inspect.unwrap(model.aggregate_partition_metrics)(partition_outputs)
        globals_by_seed[f"seed{ordinal}"] = aggregated["global_evaluation_metrics"]
        partitions_by_seed[f"seed{ordinal}"] = aggregated["partition_summaries"]
    logged = {}
    monkeypatch.setattr(model, "log_metric", lambda key, value: logged.update({key: {"1": value}}))
    summary = inspect.unwrap(model.aggregate_seed_data_metrics)(globals_by_seed, partitions_by_seed)
    assert set(summary["seed_results"]) == {"seed41", "seed42", "seed43"}
    expected = np.mean([value["average_precision"] for value in globals_by_seed.values()])
    assert summary["seed_summary"]["average_precision"]["mean"] == expected
    from expops.reporting.registry import CHART_FUNCS
    original_charts = dict(CHART_FUNCS)
    try:
        reporting = load_module("fraud_reporting_control", ROOT / "src/plot_metrics.py")
        monkeypatch.chdir(tmp_path)
        inspect.unwrap(reporting.plot_seed_data_parallel_metrics)({"combined_summary": logged})
    finally:
        CHART_FUNCS.clear()
        CHART_FUNCS.update(original_charts)
    assert (tmp_path / "fraud_seed_data_parallel_report.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
