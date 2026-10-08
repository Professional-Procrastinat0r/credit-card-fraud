"""Pure migration bindings; no metadata/client construction or provider I/O."""

import json
from pathlib import Path

import yaml

from expops.storage.config import load_storage_config
from expops.storage.plan import resolve_storage_plan
from expops.storage.vpath import VPath

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "credit-card-fraud-vfs-baseline"


def test_cloud_profile_preserves_input_key_and_separates_managed_outputs():
    path = ROOT / "vfs/compute.cloud.yaml"
    plan = resolve_storage_plan(
        PROJECT_ID,
        config_path=path,
        storage_config=load_storage_config(path),
        virtual_project_root=VPath("/source"),
        env={
            "MLOPS_SQL_USERNAME": "deployment-user",
            "CREDIT_CARD_FRAUD_SQL_PASSWORD": "not-a-real-password",
        },
    )
    assert plan.schema_version == 2
    assert plan.mounts["input"].backend.prefix == "credit-card-fraud/dataset"
    assert plan.mounts["input"].backend.bucket == "expops-example-credit-card-fraud"
    assert plan.mounts["cache"].backend.prefix == "credit-card-fraud-vfs-baseline/cache"
    assert plan.mounts["cache"].cache_ttl_hours == 24
    assert (
        plan.mounts["artefact"].backend.prefix
        == "credit-card-fraud-vfs-baseline/artefact"
    )
    assert plan.mounts["artefact"].backend.profile == "expops"
    public = json.dumps(plan.to_mapping())
    assert "not-a-real-password" not in public
    assert "CREDIT_CARD_FRAUD_SQL_PASSWORD" in public


def test_baseline_does_not_use_legacy_dataset_catalogue_or_parallel_graph():
    compute = yaml.safe_load(
        (ROOT / "vfs/compute.local.yaml").read_text(encoding="utf-8")
    )
    project = yaml.safe_load(
        (ROOT / "vfs/project/configs/project_config.yaml").read_text(encoding="utf-8")
    )
    assert "datasets" not in compute
    assert "object_stores" not in compute["storage"]
    assert project["data"]["inputs"]["training"] == {
        "path": "vfs://input/creditcard.csv"
    }
    assert len(project["environment"]) == 1
    assert all(
        "data_parallelism" not in process and "seed_parallelism" not in process
        for process in project["experiment"]["pipeline"]["processes"]
    )
    assert all(
        "metrics" not in process
        for process in project["experiment"]["pipeline"]["processes"]
    )
