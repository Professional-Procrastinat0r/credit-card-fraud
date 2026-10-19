# Credit Card Fraud Detection with ExpOps

The fraud experiment trains three models with split seeds 41, 42 and 43, evaluates
three held-out partitions per seed, and publishes an aggregated metrics chart.
The expanded pipeline has 25 processes. The same project runs locally or on SLURM.

## Local Windows run

Use the current sibling `expops-platform` installation and save the full dataset
as `D:\NUS\FYP\credit-card-fraud\data\creditcard.csv`. From PowerShell:

```powershell
Set-Location D:\NUS\FYP\credit-card-fraud
# One-time setup. If expops.env already exists, merge the example's settings
# into it; keep any existing secrets. Do not replace it blindly.
if (-not (Test-Path expops.env)) { Copy-Item configs/env/local.windows.env.example expops.env }
New-Item -ItemType Directory -Force -Path .credit-card-fraud/tmp, .credit-card-fraud/pip-cache, .credit-card-fraud/cache, .credit-card-fraud/dask, .credit-card-fraud/joblib, .credit-card-fraud/workspaces, .credit-card-fraud/materializations | Out-Null

& ..\expops-platform\.venv\Scripts\python.exe -m expops.main run configs/compute.local.yaml --local
$LASTEXITCODE
```

Repeat the final run command to check caching. Expect exit 0, 25 completed
processes on an empty cache, and 25 cached on an unchanged repeat. Model and
reporting environments are prepared automatically. No cloud credentials, database
password, shell activation or manual environment exports are required.
If `expops` is already on PATH, the equivalent command is
`expops run configs/compute.local.yaml --local`.

## SLURM run

Follow [slurm.md](slurm.md) from connection through completion. It contains the
complete NUS setup, a [busy-node alternative](slurm.md#busy-node-alternative),
and these filled-in dotenv examples:

- [Local Windows](configs/env/local.windows.env.example): all launcher paths and thread settings.
- [NUS SLURM driver](configs/env/slurm.env.example): launcher scratch/cache paths,
  worker interpreter/base directory, worker dotenv location and credential-file references.
- [NUS SLURM worker](configs/env/slurm-worker.env.example): existing node-provisioned
  AWS/GCP credential references and thread settings, loaded by Python before bootstrap.
- [Windows cloud alternative](configs/env/cloud.windows.env.example): local settings
  plus the PostgreSQL password placeholder and existing GCP ADC location.

The primary SLURM profile uses Git code, S3 input, GCS outputs and node-local
SQLite. It needs no database password. Platform code and the NUS dotenv files
have been provisioned in the locations used by the guide. The AWS/GCP credential
files remain outside the project. On another deployment, provision equivalent
base Python and credentials on each worker and change these explicit paths.

## Deployment profiles and environment settings

| Compute file | Execution | Metadata | Mounted files | Dotenv example |
| --- | --- | --- | --- | --- |
| `configs/compute.local.yaml` | Two local workers | SQLite | Local code/input/cache/reports | `local.windows.env.example` |
| `configs/compute.cloud.yaml` | Two local workers | PostgreSQL | Git code, S3 input, GCS outputs | `cloud.windows.env.example` |
| `configs/compute.git.slurm.yaml` | Two SLURM workers on xcnc17 | SQLite | Git code, S3 input, GCS outputs | `slurm.env.example` + worker file |
| `configs/compute_config.yaml` | Two SLURM workers | PostgreSQL | Local code, GCS input/outputs | SLURM settings plus SQL password |

The primary local and SLURM SQLite profiles require no secret values in
`expops.env`. The PostgreSQL alternatives require
`CREDIT_CARD_FRAUD_SQL_PASSWORD=REPLACE_WITH_DATABASE_PASSWORD`; all other
connection fields are already in the YAML. The Windows cloud alternative also
requires an AWS `expops` profile provisioned once through the SDK credential chain.
Do not run the PostgreSQL alternative from NUS unless its database is reachable.
The Redis block is a commented alternative, not a prerequisite; if explicitly
enabled, use `CREDIT_CARD_FRAUD_REDIS_PASSWORD=REPLACE_WITH_REDIS_PASSWORD`.

ExpOps loads `expops.env` in the invocation directory before resolving storage
and compute. It is dotenv syntax, not a shell script: use `NAME=value`; `${NAME}`
references work, but commands, `source`, activation and `$(...)` are not executed.
Existing shell variables win. A file beside a local compute YAML is a lower
priority fallback; `--env-file /path/to/expops.env` selects an explicit file and
`--no-env-file` disables driver discovery. Existing shell values from an earlier
session can override edits, so use a fresh shell when testing changed settings.

`MLOPS_WORKER_ENV_FILE` selects a separately provisioned worker-native dotenv.
ExpOps passes its path in the compute plan and workers load it before provider
access and environment installation. It is not a launcher file copied to workers.
Only explicitly selected worker files are loaded; retrieved project dotenv files
are excluded from delivery and never automatically applied. Application variables
can be explicitly forwarded with `EXPOPS_WORKER_ENV=NAME,OTHER`; the examples
forward the two thread limits. Worker credential paths come from the worker file.

Compute configs accept relative/absolute local YAML paths and public HTTPS URLs:

```powershell
expops run configs/compute.local.yaml --local
expops run "D:\NUS\FYP\credit-card-fraud\configs\compute.local.yaml" --local
expops run https://github.com/Professional-Procrastinat0r/credit-card-fraud/blob/main/configs/compute.cloud.yaml --local
```

Relative local mount roots resolve beside the compute YAML. `code` supplies the
default project root, so `--project` is only needed for a mount/subtree override.
Use an explicit compute file: the no-argument default is the SLURM/PostgreSQL
profile. `--local` changes execution, while storage still comes from the selected
compute file. Use `compute.local.yaml` for a completely local run.

`options.materialization.cleanup` accepts `always`, `on_success`, or `never` for
owned driver input and worker source/input copies. Active leases defer deletion;
mounted originals, durable publications and installed environment caches remain.

## Mounted source and streaming input

`code` selects the default mount containing the project configuration. Use
`--project code/subtree` to explicitly select a subtree. The
source revision is pinned to `7fdf2ee2d2510e8dbc21677630d65a317dbf4788`, independently
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
| `.credit-card-fraud/` in the original Windows checkout | Configured launcher scratch/cache directories; local cache and artefact mount roots |
| `.expops-sources/credit-card-fraud/` for either code mount | Retrieved source; `.credit-card-fraud/` beneath it contains launcher environments, snapshots and logs |
| Retrieved project `.credit-card-fraud/storage/metadata.db` with the local profile | SQLite run metadata and cache indices |
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
