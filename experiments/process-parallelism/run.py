"""Run the standalone native ExpOps experiment; no benchmark controller needed."""
from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=[1, 3], default=3)
    args = parser.parse_args()
    project = Path(__file__).resolve().parent
    dataset = project.parents[1] / "data/creditcard.csv"
    if not dataset.is_file():
        parser.error(f"Place the credit-card fraud dataset at {dataset}")
    runtime = project / ".process-parallelism"
    for variable, directory in {
        "XDG_CACHE_HOME": "cache", "PIP_CACHE_DIR": "pip-cache",
        "MLOPS_WORKSPACE_BASE_DIR": "workspaces", "DASK_TEMPORARY_DIRECTORY": "dask",
        "MLOPS_DATA_MATERIALIZATION_DIR": "materializations", "JOBLIB_TEMP_FOLDER": "joblib",
        "TMPDIR": "tmp", "TMP": "tmp", "TEMP": "tmp",
    }.items():
        path = runtime / directory
        path.mkdir(parents=True, exist_ok=True)
        os.environ[variable] = str(path)
    # The numerical workload exchanges paths to ordinary files. Every local
    # worker must use the same absolute directory, retained alongside the cache.
    outputs = runtime / "storage/artefact"
    outputs.mkdir(parents=True, exist_ok=True)
    os.environ["FRAUD_ANALYSIS_ARTIFACTS"] = str(outputs)
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    os.environ["MLOPS_WORKSPACE_DIR"] = str(project.parent)
    os.environ["MLOPS_PROJECT_ID"] = project.name
    os.environ["MLOPS_COMPUTE_CONFIG_PATH"] = str(project / "configs/compute_config.yaml")
    os.chdir(project.parent)

    from expops.core.compute_config import resolve_compute_plan
    from expops.platform import MLPlatform

    plan = replace(resolve_compute_plan(project / "configs/compute_config.yaml"), num_workers=args.workers)
    result = MLPlatform().run_pipeline_for_project(
        project.name, str(project / "configs/project_config.yaml"), compute_plan=plan,
    )
    print(f"Completed run: {result['run_id']}")
    print(f"Models and reports: {outputs}")


if __name__ == "__main__":
    main()
