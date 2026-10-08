"""Offline statistical parity and verified-I/O contracts for the VFS control."""

from __future__ import annotations

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
def modules():
    # Importing decorated project functions mutates registries; this test owns
    # only those changes and restores the previous caller state after each case.
    from expops.core.runtime.step_system import isolated_step_registries
    from expops.reporting.source_chart import isolated_chart_registry

    with isolated_step_registries(), isolated_chart_registry():
        baseline = load_module("vfs_control", ROOT / "vfs/project/src/main.py")
        legacy = load_module("legacy_control", ROOT / "src/model.py")
        baseline.log_metric = lambda *args: None
        yield baseline, legacy


def synthetic_transactions(rows=120):
    """Small test-only data with both classes; never model-quality evidence."""
    rng = np.random.default_rng(42)
    features = rng.normal(size=(rows, 30))
    labels = np.tile([0, 0, 0, 1], rows // 4)
    features[:, 1] += labels * 1.5
    frame = pd.DataFrame(
        features, columns=["Time", *[f"V{i}" for i in range(1, 29)], "Amount"]
    )
    frame["Class"] = labels
    return frame


def context_for(frame, tmp_path):
    path = tmp_path / "training.csv"
    frame.to_csv(path, index=False)
    return SimpleNamespace(data_paths={"training": path})


def test_metrics_are_logged_in_python(modules, tmp_path, monkeypatch):
    baseline, _ = modules
    logged = []
    monkeypatch.setattr(
        baseline, "log_metric", lambda key, value: logged.append((key, value))
    )
    context = context_for(synthetic_transactions(), tmp_path)
    trained = inspect.unwrap(baseline.train_model)(0.2, 42, 1000, "balanced", context)
    assert {key for key, _ in logged} == {
        "training_row_count",
        "training_fraud_count",
        "average_precision",
        "iterations",
    }
    logged.clear()
    result = inspect.unwrap(baseline.evaluate_model)(
        trained["model"], 0.2, 42, 0.5, context
    )
    assert dict(logged) == result


def test_same_model_and_holdout_metrics_as_legacy_control(
    modules, tmp_path, monkeypatch
):
    baseline, legacy = modules
    frame = synthetic_transactions()
    context = context_for(frame, tmp_path)
    native = tmp_path / "creditcard.csv"
    native.write_bytes(context.data_paths["training"].read_bytes())
    legacy_context = SimpleNamespace(data_paths={"training": native})
    monkeypatch.setattr(legacy, "log_metric", lambda *args: None)
    arguments = dict(
        test_size=0.2, random_seed=42, max_iter=1000, class_weight="balanced"
    )
    actual = inspect.unwrap(baseline.train_model)(**arguments, context=context)
    expected = inspect.unwrap(legacy.train_model)(
        data_source="training",
        **arguments,
        context=legacy_context,
    )
    for step, attribute in (("scaler", "mean_"), ("classifier", "coef_")):
        np.testing.assert_array_equal(
            getattr(actual["model"].named_steps[step], attribute),
            getattr(expected["model"].named_steps[step], attribute),
        )
    evaluation = inspect.unwrap(baseline.evaluate_model)(
        model=actual["model"],
        test_size=0.2,
        random_seed=42,
        threshold=0.5,
        context=context,
    )
    original = inspect.unwrap(legacy.evaluate_model)(
        model=expected["model"],
        data_source="training",
        test_size=0.2,
        random_seed=42,
        threshold=0.5,
        context=legacy_context,
    )["evaluation_metrics"]
    assert evaluation == original
    # The fitted scaler must see training rows only, not all input rows.
    x_train, _, _, _ = baseline.split_transactions(context, 0.2, 42)
    np.testing.assert_allclose(
        actual["model"].named_steps["scaler"].mean_, x_train.mean()
    )


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "missing-column",
        "extra-column",
        "nonnumeric",
        "nan",
        "inf",
        "one-class",
        "nonbinary",
    ],
)
def test_invalid_data_fails(modules, failure, tmp_path):
    baseline, _ = modules
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
    context = context_for(frame, tmp_path)
    with pytest.raises(ValueError):
        baseline.read_transactions(context)


def test_missing_input_never_guesses_native_file(modules, tmp_path, monkeypatch):
    baseline, _ = modules
    native = tmp_path / "creditcard.csv"
    synthetic_transactions().to_csv(native, index=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="training input"):
        baseline.read_transactions(SimpleNamespace(data_paths={}))


@pytest.mark.parametrize("test_size", [0, 1, -1, float("nan")])
def test_invalid_holdout_fraction_fails_before_io(modules, test_size, tmp_path):
    baseline, _ = modules
    context = context_for(synthetic_transactions(), tmp_path)
    with pytest.raises(ValueError, match="test_size"):
        baseline.split_transactions(context, test_size, 42)


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan")])
def test_invalid_threshold_fails_before_io(modules, threshold, tmp_path):
    baseline, _ = modules
    context = context_for(synthetic_transactions(), tmp_path)
    with pytest.raises(ValueError, match="threshold"):
        inspect.unwrap(baseline.evaluate_model)(
            None, 0.2, 42, threshold, context=context
        )


def test_baseline_has_an_admitted_three_node_graph(tmp_path):
    import yaml

    from expops.core.graph.networkx_parser import parse_networkx_pipeline_from_config

    project = yaml.safe_load(
        (ROOT / "vfs/project/configs/project_config.yaml").read_text()
    )
    parsed = parse_networkx_pipeline_from_config(project["experiment"]["pipeline"])
    assert {p.name for p in parsed.processes} == {
        "train_model",
        "evaluate_model",
        "report",
    }


def test_report_writes_png_to_platform_owned_output(modules, tmp_path):
    baseline, _ = modules
    metrics = {"evaluation": {name: {"1": 0.5} for name in baseline.REPORT_METRICS}}
    metrics["evaluation"].update(random_seed={"1": 42}, threshold={"1": 0.5})
    baseline.report(metrics, SimpleNamespace(output_dir=tmp_path))
    assert (
        (tmp_path / "fraud_baseline.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    )
