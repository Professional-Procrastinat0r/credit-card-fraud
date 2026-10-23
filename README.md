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
- [NUS SLURM worker](configs/env/slurm-worker.env.example): additional driver-readable
  credential references and thread settings, transferred before worker bootstrap.
- [Windows cloud alternative](configs/env/cloud.windows.env.example): local settings
  plus the PostgreSQL password placeholder and existing GCP ADC location.

The primary SLURM profile uses Git code, S3 input, GCS outputs and node-local
SQLite. It needs no database password. Platform code and the NUS dotenv files
have been provisioned in the locations used by the guide. The AWS/GCP credential
files remain outside the project. On another deployment, provision equivalent
base Python on each worker and driver credentials. ExpOps transfers supported
credential-file bytes and creates private worker-local copies.

The driver retrieves project source through VFS and sends selected experiment
code, helper files and reporting code to workers as a verified Dask source bundle.
Workers execute their own local copies without accessing the original code mount
or driver checkout. Datasets, cache and artefact operations continue through VFS;
local mounts used by those operations must be accessible to their consumers.
Source copies follow `options.cleanup`; mount originals are retained.

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

ExpOps discovers `expops.env` in the invocation directory before resolving
storage and compute. You can instead select a file and explicit values in compute
YAML:

```yaml
deployment:
  env_file: ../expops.env  # Relative to a local YAML in configs/.
  variables:
    OMP_NUM_THREADS: "1"
```

For a YAML copied beside its dotenv file, or a public compute URL, use
`env_file: ./expops.env`; remote compute declarations refer to local deployment
files relative to the invocation directory. The checked-in profiles keep
automatic file discovery so the same file also works when copied to SLURM.
Their explicit thread limits demonstrate `deployment.variables`.

Precedence is explicit YAML variables, then existing shell variables, then dotenv.
Quote YAML values as strings. `--env-file /path/to/expops.env` overrides file
selection; `--no-env-file` disables file loading but retains inline variables.
Dotenv supports `${NAME}` references; shell commands, `source`, activation and
`$(...)` are not executed. Use a fresh shell when testing changed dotenv values.

All effective values declared by dotenv or `deployment.variables` are forwarded
to workers automatically, before SLURM environment installation and project
imports. `MLOPS_WORKER_ENV` is only needed for extra shell-only variables.
The driver reads known credential files through VFS and delivers their bytes;
workers use private local copies, so original credential paths need not exist
there. Ordinary temporary/cache directory settings still apply on consuming
workers; those directories are not files to transfer. The filled-in NUS paths use accessible shared home; worker execution
workspaces and environment installation roots still come from the worker options.

`MLOPS_WORKER_ENV_FILE` optionally selects another driver-readable dotenv. Its
values and credential-file bytes are transferred before bootstrap; workers never
read the original dotenv path. Main driver deployment values take precedence. Downloaded project dotenv files are excluded from code delivery
and are never automatically loaded.

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

All four compute profiles explicitly use:

```yaml
options:
  cleanup: on_success
```

This removes automatically retrieved driver code, temporary dependency/code
snapshots, driver inputs and worker source/input copies after a successful
run and retains them after a failed run for debugging. The framework default is
`always`, which requests cleanup after success or failure; `never` retains completed
copies in either case. Active leases defer deletion, and incomplete failed delivery
is removed regardless of policy. Cleanup does not remove mounted originals,
reports/cache publications, logs, `--prepare-only` checkouts or installed
environment caches. Retained trees have no automatic age/size garbage collector;
remove them only when no run/worker is using them. `--local` preserves this policy.
Ordinary runs use unique `.expops-sources/run-*/credit-card-fraud/` checkouts;
retained launcher environments and logs live in `.credit-card-fraud/` beside
`.expops-sources/`. Existing files from older runs are not swept automatically.

## Mounted source and streaming input

`code` selects the default mount containing the project configuration. Use
`--project code/subtree` to explicitly select a subtree. The
Git/SLURM profile follows the code repository's default branch. Its resolved
commit is fixed for the run and recorded during retrieval. The cloud/local-worker
profile retains its explicit commit URL. To freeze a Git source, use a normal
GitHub `/tree/<full-commit>` URL; `/tree/<branch-or-tag>` selects that ref.
No separate repository/revision fields or custom URL fragments are needed.

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
| `.expops-sources/run-*/credit-card-fraud/` for either code mount | Temporary retrieved source; cleaned according to `options.cleanup` |
| `.credit-card-fraud/envs/` and `.credit-card-fraud/logs/` | Retained launcher environments and run logs |
| `.expops-sources/credit-card-fraud/` with `--prepare-only` | Explicitly prepared checkout, retained |
| Invocation `.credit-card-fraud/storage/metadata.db` with the local profile | Retained SQLite run metadata and cache indices |
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
