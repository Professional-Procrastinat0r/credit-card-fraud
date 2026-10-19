# Run credit-card-fraud on NUS SLURM

This guide is ready for account `e1115319`. It uses Git code, the existing full
S3 dataset, GCS cache/reports, and SQLite on xcnc17. The platform installation and
credential files have already been provisioned. ExpOps loads deployment settings
from `expops.env`; no shell sourcing, environment exports, venv activation,
manual project dependency installation or manual wheel build is needed.

## 1. Connect and allocate the driver

From Windows PowerShell:

```powershell
ssh -J e1115319@stujump.comp.nus.edu.sg e1115319@xlogin.comp.nus.edu.sg
```

On the login node, use the usual xcnc17 allocation below. If it is busy, use
the [busy-node alternative](#busy-node-alternative) instead.


```bash
salloc --partition=normal --account=allusers --qos=normal \
  --nodes=1 --ntasks=1 --cpus-per-task=1 --mem=4G \
  --time=01:00:00 --nodelist=xcnc17 srun --pty bash
hostname
```

Wait until `hostname` reports xcnc17. Use an existing allocation there if you
already have one. Driver and workers share this physical host because the selected
SQLite database uses node-local WAL files. Other metadata providers can support
multiple hosts when their network service is reachable.

## 2. Prepare the run directory and dotenv files

In the allocated compute-node shell:

```bash
umask 077
mkdir -p /home/e/e1115319/fyp-expops/git-s3-gcs-sqlite
cd /home/e/e1115319/fyp-expops/git-s3-gcs-sqlite
mkdir -p tmp pip-cache cache dask joblib workspaces materializations
mkdir -p /home/e/e1115319/.config/expops
mkdir -p /var/tmp/e1115319-expops-credit-card-fraud
chmod 700 /var/tmp/e1115319-expops-credit-card-fraud
```

The account's files are already populated. For a new run directory or to refresh
this deployment, download the compute file:

```bash
curl --fail --location \
  https://raw.githubusercontent.com/Professional-Procrastinat0r/credit-card-fraud/main/configs/compute.git.slurm.yaml \
  -o compute.git.slurm.yaml
```

The following one-time commands install the two complete dotenv examples only
when those files do not already exist. If a file exists, compare it with the
linked example and merge needed settings while keeping private values.

```bash
if [ ! -f expops.env ]; then
  curl --fail --location \
    https://raw.githubusercontent.com/Professional-Procrastinat0r/credit-card-fraud/main/configs/env/slurm.env.example \
    -o expops.env
fi
if [ ! -f /home/e/e1115319/.config/expops/expops.env ]; then
  curl --fail --location \
    https://raw.githubusercontent.com/Professional-Procrastinat0r/credit-card-fraud/main/configs/env/slurm-worker.env.example \
    -o /home/e/e1115319/.config/expops/expops.env
fi
chmod 600 expops.env /home/e/e1115319/.config/expops/expops.env
```

[The driver example](configs/env/slurm.env.example) contains **all fields** for
this deployment, filled in. It sets:

| Fields | Purpose |
| --- | --- |
| `TMPDIR`, `TMP`, `TEMP` | Launcher temporary files under the run's `tmp/` |
| `PIP_CACHE_DIR`, `XDG_CACHE_HOME` | Launcher pip cache and automatic worker-package cache |
| `DASK_TEMPORARY_DIRECTORY`, `JOBLIB_TEMP_FOLDER` | Launcher library scratch directories |
| `MLOPS_WORKSPACE_BASE_DIR`, `MLOPS_DATA_MATERIALIZATION_DIR` | Launcher process workspaces and owned input copies |
| `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` | One numerical-computation thread per one-core task |
| `DASK_DISTRIBUTED__COMM__COMPRESSION` | Common `zlib` codec for Dask communication |
| `EXPOPS_WORKER_ENV` | Explicitly forwards the two thread limits to workers |
| `MLOPS_WORKER_PYTHON` | `/home/e/e1115319/fyp-expops/expops-platform/.venv/bin/python`, the provisioned base runtime |
| `MLOPS_WORKER_BASE_DIR` | `/var/tmp/e1115319-expops-credit-card-fraud`; contains worker `environments/`, `workspaces/`, `dask/` |
| `MLOPS_WORKER_ENV_FILE` | `/home/e/e1115319/.config/expops/expops.env`, explicitly loaded on each worker |
| `GOOGLE_APPLICATION_CREDENTIALS` | Existing `/home/e/e1115319/.config/expops/gcp-adc.json` |
| `AWS_PROFILE` | Existing `expops` profile |
| `AWS_SHARED_CREDENTIALS_FILE`, `AWS_CONFIG_FILE` | Existing `aws-expops-credentials` and `aws-expops-config` under `/home/e/e1115319/.config/expops/` |

[The worker example](configs/env/slurm-worker.env.example) contains just those
four AWS/GCP settings and the thread limits. It deliberately omits driver scratch
paths. The worker entry point parses it before retrieving bootstrap publications
or starting Dask. The compute YAML needs no credential-sourcing prologue.
The driver file does not automatically transfer or provision credential files.

No DB password is needed for this SQLite profile. The optional PostgreSQL profile
`compute_config.yaml` additionally requires
`CREDIT_CARD_FRAUD_SQL_PASSWORD=REPLACE_WITH_DATABASE_PASSWORD` in the driver file
and database network access. Redis/Supabase outbound connectivity is not a
prerequisite for the primary workflow.

Existing shell variables take precedence over dotenv, so start from a fresh
login shell when checking modified settings. No ordinary Python, pip, curl or
shell command automatically loads this file: ExpOps loads it for its invocation
and child processes. That is why the directories are created explicitly above.
The NUS small `/tmp` quota makes these configured launcher/worker scratch paths
necessary. For quota diagnostics, run `quota -s` if the command is available,
plus `df -h /tmp /var/tmp "$HOME"` and `df -i /tmp /var/tmp "$HOME"`; free global
disk space alone does not establish your per-user quota.

## 3. Retrieve the project, then run

Use the provisioned Python directly, so no activation is needed:

```bash
/home/e/e1115319/fyp-expops/expops-platform/.venv/bin/python -m expops.main run compute.git.slurm.yaml --prepare-only
/home/e/e1115319/fyp-expops/expops-platform/.venv/bin/python -m expops.main run compute.git.slurm.yaml
printf 'ExpOps exit code: %s\n' "$?"
```

The first command is an optional source check. The second is the full run. If
`expops` is already on PATH, `expops run compute.git.slurm.yaml` is equivalent.
No `--project` is necessary: `code` is the default project mount. Its source pin
is `7fdf2ee2d2510e8dbc21677630d65a317dbf4788`, independently of the deployment file.
A public compute URL can replace the local YAML path without changing dotenv
discovery in the invocation directory.

ExpOps retrieves the project into `.expops-sources/credit-card-fraud`, prepares
launcher environments, automatically packages/publishes its current worker code
and requirement snapshots through the GCS cache mount, then submits two worker
jobs. Each worker builds or reuses model/reporting venvs on its own disk before
starting Dask. Source delivery uses Dask; input and managed publications use VFS.
No project checkout, dataset upload or runtime mount is required.

Worker first-time installation counts against the 45-minute job walltime;
`startup_timeout_sec: 1800` allows up to 30 minutes for workers to become ready.
The base interpreter must already contain the current ExpOps, `python-dotenv`
and provider SDKs. This installation has been uploaded for you. Another cluster
can provision its base runtime/credential files separately on each worker.
The NUS paths explicitly use shared home for these deployment prerequisites;
project venvs and worker scratch are node-local.

## 4. Check completion and repeat

Expect CLI exit 0 and zero failed processes. Empty state gives 25 executed
processes; an unchanged repeat with valid cache entries gives 25 cached. Existing
metadata is preserved, so the first run you perform may already use cached values.
The configured process-result cache TTL is 24 hours.

```bash
latest_log=$(ls -t .expops-sources/credit-card-fraud/.credit-card-fraud/logs/*.log | head -n 1)
grep -E 'Process results:|Pipeline completed successfully' "$latest_log"

/home/e/e1115319/fyp-expops/expops-platform/.venv/bin/python -m expops.main run compute.git.slurm.yaml
printf 'ExpOps exit code: %s\n' "$?"
```

The chart is `fraud_seed_data_parallel_report.png`, published through the GCS
`artefact` mount; run metadata contains its managed reference. An unchanged cached
run reuses the report. Some Dask versions log closed-connection traces during
scheduler shutdown/job cancellation; distinguish those from task failures using
the CLI exit, process summary and completed run status.

After the run finishes:

```bash
exit
```

This releases the driver allocation. ExpOps releases its worker jobs itself.

## State and maintenance

| Location | Contents |
| --- | --- |
| `/home/e/e1115319/fyp-expops/expops-platform` | Provisioned platform and base `.venv` |
| Run `expops.env` | Driver deployment settings; never committed |
| `/home/e/e1115319/.config/expops/expops.env` | Worker deployment settings; credential bytes remain in their separate files |
| Run `.expops-sources/credit-card-fraud` | Retrieved source, launcher venvs and logs |
| Run `cache/expops/worker-packages` | Automatically built and verified reusable worker packages |
| `/var/tmp/e1115319-expops-credit-card-fraud/environments` | Worker-local installed environments |
| `/var/tmp/e1115319-expops-credit-card-fraud/metadata.sqlite` on xcnc17 | SQLite run records and cache indices |
| S3 `expops-test-bucket-755933694771-ap-southeast-1-an/credit-card-fraud/dataset` | Training CSV |
| GCS `expops-example-credit-card-fraud/credit-card-fraud/slurm-git-s3-sqlite/cache` and `/artefact` | Managed results, runtime publications and reports |

Node cleanup can remove SQLite records and node-local environments. Keep both
metadata and GCS results to reuse process caches. Installed environments and
published runtime files are not age/size garbage-collected; remove unused
entries only when no worker is using them. Temporary owned source/input copies
use the platform's materialization cleanup policy.

Platform installation/update is separate from running this project. The current
working platform has already been uploaded and installed at the path above.
When changing platform code later, update the driver and base worker installation
before running again. This does not require building a wheel manually or
reinstalling project requirements yourself. See the platform repository for its
development installation instructions.

## Busy-node alternative

If xcnc17 worker jobs cannot start within the configured 30-minute startup
window, choose an available host for both driver and workers. For example,
xcnc42 had capacity during validation on 19 October 2026. Availability changes;
check the queue before allocating. Changing hosts gives a separate node-local
SQLite database; records on xcnc17 remain there. The same dotenv settings work.

From the login node, use this allocation **instead of** the xcnc17 allocation:

```bash
salloc --partition=normal --account=allusers --qos=normal \
  --nodes=1 --ntasks=1 --cpus-per-task=1 --mem=4G \
  --time=01:00:00 --nodelist=xcnc42 srun --pty bash
```

Follow step 2 in that shell, then create a separate compute file and run it:

```bash
cd /home/e/e1115319/fyp-expops/git-s3-gcs-sqlite
sed 's/xcnc17/xcnc42/g' compute.git.slurm.yaml > compute.git.slurm.xcnc42.yaml
/home/e/e1115319/fyp-expops/expops-platform/.venv/bin/python -m expops.main run compute.git.slurm.xcnc42.yaml
printf 'ExpOps exit code: %s\n' "$?"
```

Do not run an xcnc17 driver with xcnc42 workers against these node-local SQLite
paths. Worker scratch and environments are local to the chosen host even though
the configured `/var/tmp` path text is identical on both hosts.
