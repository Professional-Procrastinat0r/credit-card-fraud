"""Offline mounted bindings and the original nested experiment contract."""

import json
from pathlib import Path

import pytest
import yaml

from expops.core.graph.networkx_parser import parse_networkx_pipeline_from_config
from expops.core.graph.graph_expansion import expand_process_graph
from expops.storage.config import load_storage_config
from expops.storage.data_sources import DatasetCatalog, resolve_data_plan
from expops.storage.plan import resolve_storage_plan

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "credit-card-fraud"


def project_config():
    return yaml.safe_load((ROOT / "configs/project_config.yaml").read_text(encoding="utf-8"))


def resolved(profile):
    path = ROOT / "configs" / profile
    return resolve_storage_plan(
        PROJECT_ID, config_path=path, project_root=ROOT,
        storage_config=load_storage_config(path), env={},
    )


@pytest.mark.parametrize("profile", ["compute.local.yaml", "compute.cloud.yaml", "compute_config.yaml"])
def test_profiles_resolve_scripts_requirements_and_input_without_clients(profile, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # Caller CWD must not change mount roots.
    plan = resolved(profile)
    project = project_config()
    assert plan.schema_version == 2
    assert Path(plan.mounts["local"].backend.root).resolve() == ROOT
    for name, script in project["scripts"].items():
        path = plan.resolve_namespace_path(script, field_name=f"scripts.{name}")
        assert path.alias == "local"
        assert (ROOT / path.key).is_file()
    for definition in project["environment"].values():
        for requirement in definition["venv"]:
            path = plan.resolve_namespace_path(requirement, field_name="environment.venv")
            assert path.alias == "local"
            assert (ROOT / path.key).is_file()
    data = resolve_data_plan(
        PROJECT_ID, project, DatasetCatalog(), storage_plan=plan,
        object_store_aliases=frozenset(plan.object_specs), project_root=ROOT,
    )
    assert data.inputs["training"].store == "input"
    assert str(data.inputs["training"].key) == "creditcard.csv"
    assert data.modes.get("training", "materialize") == "materialize"
    assert plan.mounts["cache"].cache_ttl_hours == 24
    for alias in ("cache", "artefact"):
        if plan.mounts[alias].type == "local":
            assert plan.mounts[alias].access == "shared"


def test_local_profile_has_project_owned_state_and_no_remote_credentials():
    plan = resolved("compute.local.yaml")
    for alias, directory in (("input", "data"), ("cache", ".credit-card-fraud/storage/cache"),
                             ("artefact", ".credit-card-fraud/storage/artefact")):
        assert Path(plan.mounts[alias].backend.root).resolve() == ROOT / directory
    assert Path(plan.metadata_spec.connection.database).resolve() == ROOT / ".credit-card-fraud/storage/metadata.db"
    assert not plan.metadata_spec.password_ref.required


@pytest.mark.parametrize("profile", ["compute.cloud.yaml", "compute_config.yaml"])
def test_remote_profiles_preserve_dataset_and_public_secret_reference(profile):
    plan = resolved(profile)
    assert plan.mounts["input"].backend.prefix == "credit-card-fraud/dataset"
    if profile == "compute.cloud.yaml":
        assert plan.mounts["input"].type == "s3"
        assert plan.mounts["input"].backend.bucket == "expops-test-bucket-755933694771-ap-southeast-1-an"
        assert plan.mounts["input"].backend.profile == "expops"
    else:
        assert plan.mounts["input"].type == "gcs"
        assert plan.mounts["input"].backend.bucket == "expops-example-credit-card-fraud"
    assert plan.mounts["cache"].backend.prefix == "credit-card-fraud/vfs/cache"
    assert plan.mounts["artefact"].backend.prefix == "credit-card-fraud/vfs/artefact"
    assert plan.mounts["cache"].type == "gcs"
    assert plan.mounts["artefact"].type == "gcs"
    public = json.dumps(plan.to_mapping())
    assert "CREDIT_CARD_FRAUD_SQL_PASSWORD" in public
    assert type(plan).from_mapping(plan.to_mapping()) == plan


def test_original_parallel_graph_and_parameters_are_preserved():
    project = project_config()
    pipeline = project["experiment"]["pipeline"]
    processes = {p["name"]: p for p in pipeline["processes"]}
    assert processes["seed_parallel"]["seed_parallelism"]["seeds"] == [41, 42, 43]
    assert processes["data_parallel"]["data_parallelism"] == {"size": 3, "data_name": "evaluation_rows"}
    assert processes["train_model"]["parameters"] == {"test_size": 0.2, "max_iter": 1000, "class_weight": "balanced"}
    assert processes["evaluate_partition"]["parameters"]["threshold"] == 0.5
    assert processes["aggregate_partition_metrics"]["data_aggregation"] is True
    assert processes["aggregate_seed_data_metrics"]["seed_aggregation"] is True
    parsed = parse_networkx_pipeline_from_config(pipeline)
    assert len(parsed.processes) == 9
    assert len(expand_process_graph(parsed.processes)) == 25
    assert set(project["environment"]) == {"fraud-model-env", "fraud-reporting-env"}
    assert project["data"]["inputs"]["training"] == {"path": "input/creditcard.csv"}
    for profile in ("compute.local.yaml", "compute.cloud.yaml", "compute_config.yaml"):
        compute = yaml.safe_load((ROOT / "configs" / profile).read_text(encoding="utf-8"))
        assert "datasets" not in compute
        assert "object_stores" not in compute["storage"]
