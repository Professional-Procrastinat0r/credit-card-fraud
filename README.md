# Credit Card Fraud Detection with ExpOps

Run the same fraud experiment locally or on SLURM with the ordinary ExpOps CLI.
The project trains three logistic-regression models with split seeds 41, 42 and
43, scores each held-out set in three partitions, and produces an aggregated
metrics report. The expanded pipeline has 25 processes.

## Run on SLURM: Git source, S3 dataset, GCS outputs

Follow [the end-to-end SLURM guide](slurm.md). It covers connecting, allocating
the driver, activating ExpOps, loading credentials, setting writable temporary
paths, and downloading the compute config. Once those steps are complete, run:

```bash
expops run compute.git.slurm.yaml
```

You only download the compute file. ExpOps retrieves the project from Git,
reads `configs/project_config.yaml`, prepares launcher environments, and submits
worker jobs that build their own model and reporting venvs before starting Dask.
ExpOps prepares and publishes its worker package automatically. Only the base
bootstrap installation and deployment credentials need provisioning, as described
in the guide. The dataset already lives in
S3; process results and reports go to GCS. SQLite stores metadata on `xcnc17`.
No project checkout, dataset upload, or project-specific launch script is needed.

The guide has a separate **development-only** section for uploading and installing
the platform source. That is installation/update work, not a step for every run.

## Run locally on Windows

Prerequisites: a VFS-capable ExpOps installation and the full dataset saved as
`data/creditcard.csv`. From PowerShell in this repository, activate your ExpOps
environment. For a sibling development checkout:

```powershell
& ..\expops-platform\.venv\Scripts\Activate.ps1

$env:MLOPS_WORKSPACE_BASE_DIR = Join-Path $PWD '.credit-card-fraud\workspaces'
New-Item -ItemType Directory -Force $env:MLOPS_WORKSPACE_BASE_DIR | Out-Null

expops run configs/compute.local.yaml --local
```

The writable workspace avoids the platform's `/tmp` default on Windows.
ExpOps uses the compute file's `code` mount as the default project root and
retrieves it into `.expops-sources/credit-card-fraud`. It creates the required project environments;
you do not install the model or plotting requirements manually. The local
profile uses two local Dask workers, SQLite, and local input/cache/report mounts,
so no cloud credentials are needed. No worker bootstrap or platform wheel is
required for local execution. The profile configures Dask's actual
`local_cluster_kwargs.memory_limit` option rather than a SLURM memory setting.

Repeat the same command to test caching. With an empty metadata database and
cache, expect 25 executed processes and zero failures. An unchanged repeat with
valid cache entries should report 25 cached processes and zero failures. The CLI
prints the run ID, summary, and log path. Check that it exits successfully.

## Choose a deployment

| Config | Compute | Metadata | Files |
| --- | --- | --- | --- |
| `configs/compute.local.yaml` | Two local Dask workers | Project-local SQLite | Local source, input, cache and artefacts |
| `configs/compute.cloud.yaml` | Two local Dask workers | PostgreSQL | Pinned Git source, S3 input, GCS cache and artefacts |
| `configs/compute_config.yaml` | Two SLURM workers with node-local venv bootstrap | PostgreSQL | Local source, GCS input, cache and artefacts |
| `configs/compute.git.slurm.yaml` | Two SLURM workers on `xcnc17` with node-local venv bootstrap | Node-local SQLite | Git source, S3 input, GCS cache and artefacts |

For local workers with cloud storage, provision the credentials and PostgreSQL
connection referenced by `compute.cloud.yaml`, then run from this repository:

```powershell
expops run configs/compute.cloud.yaml --local
```

Keep the writable workspace setting from the local example. Omitting `--compute`
selects `configs/compute_config.yaml`, which is a SLURM/PostgreSQL profile. Use an
explicit compute config for these examples. There is no `run --config` argument.
All deployments use the same project definition in `configs/project_config.yaml`.

`--local` overrides compute selection; it does not replace storage configuration.
In particular, it does not turn the Git/SLURM profile's Linux SQLite path into a
Windows path or remove database credential requirements from a cloud profile.
Use `compute.local.yaml` for a fully local run. When overriding a SLURM profile,
remote bootstrap, interpreter, prologue and scratch options are ignored.

Both SLURM profiles automatically prepare the running ExpOps distribution and
publish it with requirement snapshots to the configured GCS cache. Workers read
those verified publications through VFS and install environments on their own
node. No manual wheel build or runtime mount is required. The explicit NUS base
Python and credential-file paths still use shared home; another site can
provision those prerequisites independently on each node. See [the SLURM guide](slurm.md).

## Local deployment settings and remote compute URLs

Copy `expops.env.example` to `expops.env` in your invocation directory and fill
only the deployment values you need. ExpOps loads it before storage/compute
resolution; existing shell values take precedence. `--env-file path` selects an
explicit local file, and `--no-env-file` disables discovery. A local compute
file's adjacent `expops.env` is a lower-priority fallback. Downloaded project
environment files are never automatically applied.

After publishing these config changes, the portable cloud profile can be run as:

```bash
expops run https://github.com/Professional-Procrastinat0r/credit-card-fraud/blob/main/configs/compute.cloud.yaml --local
```

The code source remains pinned separately from the compute document. The pin
currently contains `local/...` file declarations, so the Git profiles explicitly
provide that alias alongside `code`. New project declarations use `code/...`.

Declare one dependency document per independent environment:

```yaml
environment:
  fraud-model-env:
    venv: code/requirements.txt
  fraud-reporting-env:
    venv: code/requirements-charts.txt
```

`options.materialization.cleanup` accepts `always` (default), `on_success`, or
`never` for worker-owned source/input copies. Active leases defer deletion;
mounted originals, durable outputs and installed environment caches are retained.
Application variables are explicitly forwarded with `EXPOPS_WORKER_ENV=NAME,OTHER`;
loading an env file does not add all its variables to that forwarding list.

## Mounted source and streaming input

`code` selects the default mount containing the project configuration. Use
`--project code/subtree` to explicitly select a subtree. The
source revision is pinned to `8e76706f5394483d82126dbab671e4ec92639cf3`, independently
of the branch supplying the compute file. After merging deployment/docs changes,
the compute-file URL can use `main` without changing that source pin.

Scripts and environment requirements are addressed as `code/src/model.py`,
`code/src/plot_metrics.py`, `code/requirements.txt`, and
`code/requirements-charts.txt`. Each compute file defines the actual providers.
Local mount `source` paths resolve relative to the compute YAML file.

The project declares its training input as:

```yaml
data:
  inputs:
    training:
      path: input/creditcard.csv
      mode: stream
```

Validation, training and held-out preparation open `context.inputs["training"]`
on the worker and pass the stream to `pandas.read_csv`. The raw CSV is not saved
as a materialized dataset. Pandas still loads the CSV into memory; each process
that needs it opens a fresh stream. This is not incremental training.

For a materialized input, change the mode to `materialize` or omit it. The loader
supports both modes; its commented materialized example remains in the source.
Input content identity supports caching in either mode. Changes to input bytes,
process code or parameters can invalidate dependent results.

The reserved `cache` and `artefact` mounts store process results and reports.
Cache entries in these profiles have a 24-hour TTL, so a later repeat can execute
again after expiry. SQLite holds metadata and cache indices; GCS holds output
bytes in the Git/SLURM deployment. Retain both to reuse cached results.

## Files created by a run

| Location | Purpose |
| --- | --- |
| `.credit-card-fraud/` in a native checkout | Project environments, requirement snapshots and logs |
| `.credit-card-fraud/storage/` with the local profile | SQLite metadata, cached results and artefacts |
| `.expops-sources/credit-card-fraud/` with the Git profile | Retrieved project source, including its `.credit-card-fraud/` runtime directory |
| Configured workspace directory | Temporary process workspaces |
| `/var/tmp/e1115319-expops-credit-card-fraud/environments` on each SLURM node | Reusable model and reporting venvs built by worker bootstrap |
| GCS `credit-card-fraud/slurm-git-s3-sqlite/cache` and `/artefact` | Managed cache payloads and report objects for the Git/SLURM profile |

The chart is `fraud_seed_data_parallel_report.png`. Use the run's chart metadata
to find its managed object reference; object keys include ExpOps-managed paths.
The raw dataset and generated runtime state are excluded from Git.

## Experiment and correctness controls

- Target: `Class`; 1 is fraud, 0 is genuine.
- Features: `Time`, `Amount`, and `V1` through `V28`.
- Split: stratified 80/20 holdout, with seeds 41, 42 and 43.
- Preprocessing: `StandardScaler` fitted only on the training split.
- Model: `LogisticRegression(class_weight="balanced", max_iter=1000)`.
- Primary metric: held-out average precision; secondary metrics include ROC-AUC,
  precision, recall, F1, confusion counts, and alert rate at threshold 0.5.

The full dataset contains 284,807 rows, 31 columns and 492 frauds. Training uses
each seed's complete training split; only held-out scoring is partitioned.
Each seed's three partitions are concatenated before computing global metrics.
Average precision and ROC-AUC are not averaged across partitions. The final
seed aggregator reports cross-seed stability.

Threshold 0.5 is an initial operating point. Threshold tuning needs a validation
partition rather than the final test set. See [historical experiment results](docs/experiment-results.md)
for the original baseline and parallelism controls; those records are historical,
not fresh measurements of the current deployment.
