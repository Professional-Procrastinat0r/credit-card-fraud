"""Inspect the secret-free ExpOps storage plan without opening storage clients.

Run this example with the current ``expops-platform`` source on ``PYTHONPATH``.
It deliberately resolves configuration with an empty environment so no local
credential can affect, or accidentally enter, the displayed plan.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from expops.storage import (
    load_dataset_catalog,
    load_storage_config,
    resolve_data_plan,
    resolve_storage_plan,
)
from expops.storage.runtime_requirements import storage_worker_environment_for_specs


PROJECT_ID = "credit-card-fraud"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
PROJECT_CONFIG_PATH = PROJECT_ROOT / "configs" / "project_config.yaml"
DEPLOYMENT_CONFIG_PATH = PROJECT_ROOT / "configs" / "compute_config.yaml"


def main() -> None:
    """Print the plan and worker credential names without resolving secrets."""

    project_config = yaml.safe_load(
        PROJECT_CONFIG_PATH.read_text(encoding="utf-8")
    ) or {}
    storage_config = load_storage_config(DEPLOYMENT_CONFIG_PATH)

    plan = resolve_storage_plan(
        PROJECT_ID,
        env={},
        workspace_root=WORKSPACE_ROOT,
        project_root=PROJECT_ROOT,
        config_path=DEPLOYMENT_CONFIG_PATH,
        storage_config=storage_config,
    )
    data_plan = resolve_data_plan(
        PROJECT_ID,
        project_config,
        load_dataset_catalog(DEPLOYMENT_CONFIG_PATH),
        object_store_aliases=frozenset(plan.object_specs),
        config_path=DEPLOYMENT_CONFIG_PATH,
    )
    snapshot = plan.to_json()
    reconstructed = type(plan).from_json(snapshot)
    if reconstructed != plan:
        raise RuntimeError("Resolved storage plan did not survive JSON round-trip")
    wire_plan = json.loads(snapshot)
    worker_names = storage_worker_environment_for_specs(
        plan.metadata_spec,
        plan.object_specs.values(),
    )

    print("Secret-free resolved storage plan:")
    print(json.dumps(wire_plan, indent=2, sort_keys=True))
    print("\nStorage-plan JSON round-trip: OK")

    source = data_plan.inputs.get("training")
    source_mapping = source.to_mapping() if source is not None else {}
    object_spec = wire_plan["object_specs"].get(source_mapping.get("store"), {})
    object_type = object_spec.get("type")
    scheme = {"gcs": "gs", "s3": "s3"}.get(object_type)
    if source_mapping.get("type") == "object" and scheme is not None:
        key = str(source_mapping["key"]).lstrip("/")
        prefix = str(object_spec.get("prefix") or "").strip("/")
        qualified_key = f"{prefix}/{key}" if prefix else key
        print(
            "\nResolved training object: "
            f"{scheme}://{object_spec['bucket']}/{qualified_key}"
        )

    print("\nResolved logical dataset inputs:")
    print(json.dumps(data_plan.to_mapping()["dataset_names"], indent=2, sort_keys=True))

    print("\nStorage-related environment names eligible for worker propagation:")
    for name in worker_names:
        print(f"- {name}")
    print("\nNo credential value was read and no storage client was opened.")


if __name__ == "__main__":
    main()
