# Git source, S3 input and GCS outputs on SLURM

This deployment uses the current 25-process nested fraud experiment with
streaming training input and Supabase PostgreSQL metadata. It needs an installed
ExpOps runtime and credentials, but no existing fraud checkout or local CSV.

| Resource | Location |
|---|---|
| Project source | Git commit `8e76706f5394483d82126dbab671e4ec92639cf3` |
| Training CSV | `s3://expops-test-bucket-755933694771-ap-southeast-1-an/credit-card-fraud/dataset/creditcard.csv` |
| Cache | `gs://expops-example-credit-card-fraud/credit-card-fraud/slurm-git-s3-supabase/cache/` |
| Artefacts | `gs://expops-example-credit-card-fraud/credit-card-fraud/slurm-git-s3-supabase/artefact/` |
| Metadata | Supabase PostgreSQL, selected by the compute YAML |

The deployment branch is `feature/git-s3-gcs-supabase-slurm`. It builds on the
streaming fraud branch without adding the earlier backend-matrix fixture trees.
After merging, download the same files from `main`. The compute file's Git commit
pin remains independent of the branch used to download the deployment files;
update that pin deliberately when you want to execute changed project code.

## Current verification and blocker

The latest tested platform source, including the helper-import and environment
bootstrap fixes, is under `~/fyp-expops/vfs-test-2026-10-12/platform`. The prepared
interpreter is
`~/fyp-expops/vfs-test-2026-10-12/cloud-preflight/.venv/bin/python`.
It imports that source and has the PostgreSQL, S3, GCS and SLURM libraries.
The older `~/fyp-expops/expops-platform` directory is not the current deployment.
The prepared test environment has no `expops` console script, so the commands
below use `python -m expops.main` through an explicit interpreter variable.

On 12 October, TCP connections to the currently configured Supabase host timed
out from both `xlogin2` and `xcnc17`, on ports 5432 and 6543. This exact PostgreSQL
deployment has therefore not passed end-to-end acceptance. Confirm the current
endpoint in Supabase Dashboard before training; if it remains unreachable,
resolve database/network availability first. A password cannot fix a TCP timeout.
The earlier combined SLURM acceptance used Redis metadata, not Supabase.

The profile selects the **session pooler** on port 5432, suited to the ordinary
PostgreSQL client. Supabase's transaction pooler on 6543 requires driver changes
for prepared statements; do not switch only the port to bypass a failure.
See [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).

## 1. Connect to the cluster

From your Windows terminal:

```powershell
ssh -J e1115319@stujump.comp.nus.edu.sg e1115319@xlogin.comp.nus.edu.sg
```

All following commands are Bash on the cluster unless marked PowerShell.

## 2. Choose the runtime and create an empty run directory

```bash
export EXPOPS_PYTHON="$HOME/fyp-expops/vfs-test-2026-10-12/cloud-preflight/.venv/bin/python"
"$EXPOPS_PYTHON" -c 'import expops, psycopg, s3fs, gcsfs, dask_jobqueue; print(expops.__file__)'
"$EXPOPS_PYTHON" -m expops.main run --help

mkdir -p "$HOME/fyp-expops/git-s3-gcs-supabase"
cd "$HOME/fyp-expops/git-s3-gcs-supabase"
umask 077
export TMPDIR="$PWD/tmp" TMP="$PWD/tmp" TEMP="$PWD/tmp"
export MLOPS_WORKSPACE_BASE_DIR="$PWD/workspaces"
export XDG_CACHE_HOME="$PWD/cache" PIP_CACHE_DIR="$PWD/pip-cache"
mkdir -p "$TMPDIR" "$MLOPS_WORKSPACE_BASE_DIR" "$XDG_CACHE_HOME" "$PIP_CACHE_DIR"
"$EXPOPS_PYTHON" -c 'import tempfile; print(tempfile.gettempdir())'
quota -s
```

The temporary path should be below this run directory. Shared home storage lets
the driver and workers see the environments, credential files and source delivery.
The inline redirection avoids this cluster's small per-user `/tmp` quota.

For a future release, activate a shared venv containing the released package and
set `EXPOPS_PYTHON="$(command -v python)"` instead. The installed `expops` command
is equivalent to `"$EXPOPS_PYTHON" -m expops.main`. Installing the platform does
not install the fraud experiment; the project controls its own requirements.

## 3. Download deployment files only

```bash
FRAUD_DEPLOY_REF="feature/git-s3-gcs-supabase-slurm"
RAW="https://raw.githubusercontent.com/Professional-Procrastinat0r/credit-card-fraud/$FRAUD_DEPLOY_REF"
curl --fail --location "$RAW/configs/compute.git.slurm.yaml" -o compute.git.slurm.yaml
curl --fail --location "$RAW/configs/storage-constraints.txt" -o storage-constraints.txt
curl --fail --location "$RAW/scripts/run_git_slurm.sbatch" -o run.slurm
curl --fail --location "$RAW/scripts/slurm_deployment.py" -o deployment.py
export PIP_CONSTRAINT="$PWD/storage-constraints.txt"
```

The constraints keep the storage SDK versions compatible while ExpOps creates
the model and reporting environments. Only the compute file is needed by the
ExpOps CLI itself; the other files provide the batch driver, dependency constraints
and project-specific checks used by this walkthrough.

You do not need to clone or upload the fraud repository. `--project local`
selects the Git mount containing `configs/project_config.yaml`; that configuration
selects `local/src/model.py`, reporting code and requirement files. ExpOps retrieves
the source into `.expops-sources/credit-card-fraud`. Here `local` is a namespace
alias for Git, not a statement that the source was already on local disk.

## 4. Load credentials and confirm Supabase

GCP ADC, the AWS `expops` profile and Git credentials were configured separately
on the shared cluster home. Load the cloud environment file:

```bash
source "$HOME/.config/expops/cloud.env"
git ls-remote https://github.com/Professional-Procrastinat0r/credit-card-fraud.git \
  refs/heads/feature/git-s3-gcs-supabase-slurm
```

That file selects the existing GCP ADC and AWS credential/config files. Do not
copy credentials into the fraud source or compute YAML. A user setting this up
from scratch must provision their own ADC, AWS profile and Git authentication;
these existing files are specific to this account. Workers inherit selected
environment settings and read credential files through shared home storage.

Open Supabase Dashboard, choose **Connect -> Session pooler**, and compare its
host, port, username and database with `storage.metadata.connection` in the YAML:

```bash
nano compute.git.slurm.yaml
```

Keep `sslmode: require`. Use the PostgreSQL database password, not a Supabase API
key. Read it without putting its literal value in the shell command:

```bash
read -r -s -p "Supabase database password: " CREDIT_CARD_FRAUD_SQL_PASSWORD
printf '\n'
export CREDIT_CARD_FRAUD_SQL_PASSWORD
```

The reference `CREDIT_CARD_FRAUD_SQL_PASSWORD` in YAML selects this variable.
SLURM inherits it when you submit the driver job; it is also available to the
worker metadata clients. Do not unset it before submitting both test runs.

## 5. Check access and optionally retrieve source without running

```bash
"$EXPOPS_PYTHON" deployment.py preflight --compute compute.git.slurm.yaml
```

Expected stages: Git model source, S3 CSV size/header, GCS cache write/read,
GCS artefact write/read, then **Supabase PostgreSQL SELECT 1: OK**. The two tiny
GCS `_preflight` objects are retained as check evidence; no training runs are
created. It does not create the application metadata schema.

To check only files while diagnosing PostgreSQL:

```bash
"$EXPOPS_PYTHON" deployment.py preflight --compute compute.git.slurm.yaml --files-only
```

Optionally exercise CLI source retrieval:

```bash
"$EXPOPS_PYTHON" -m expops.main run --project local \
  --compute compute.git.slurm.yaml --prepare-only
ls .expops-sources/credit-card-fraud/configs
```

`--prepare-only` retrieves project source without submitting workers, building
environments or connecting to PostgreSQL. The actual run refreshes the named
source directory while preserving its runtime directory. It does not download
the S3 training CSV as a prepared local dataset in streaming mode.

## 6. Submit the driver and let ExpOps provision workers

Proceed when database access works:

```bash
JOB_ID=$(sbatch --parsable --export=ALL run.slurm)
JOB_ID=${JOB_ID%%;*}
printf 'Driver job: %s\n' "$JOB_ID"
squeue -u "$USER"
tail -F "driver-$JOB_ID.log"
```

Use Ctrl+C to stop following the log; it does not cancel the job. The driver job
runs on `xcnc17`. Its preflight checks access from the compute node before invoking:

```bash
"$EXPOPS_PYTHON" -m expops.main run --project local --compute compute.git.slurm.yaml
```

The SLURM provider submits two additional worker jobs in the configured pool.
Do not add `--local`: that would replace the requested SLURM provider. Environment
setup installs the declared model/reporting dependencies, then workers validate
the CSV, train three models, score nine held-out partitions, aggregate metrics
and publish the PNG to GCS. Raw CSV bytes stream from S3 into pandas; pandas
still holds the dataset in memory. Models, spilled payloads and result cache
objects use GCS; PostgreSQL keeps metadata and cache indices.

The default worker walltime is 30 minutes and driver walltime is one hour. Pending
jobs can exceed the 10-minute worker startup timeout; increase it deliberately
if necessary rather than assuming a pending job is a VFS failure.

## 7. Verify the first run and retrieve its report

After the driver exits:

```bash
sacct -j "$JOB_ID" -X --format=JobID,JobName,State,ExitCode,Elapsed
grep -E 'Run ID|run_id|Pipeline|Process results|exit status|ERROR|Traceback' "driver-$JOB_ID.log"
ls -lt .expops-sources/credit-card-fraud/.credit-card-fraud/logs/
"$EXPOPS_PYTHON" deployment.py inspect --compute compute.git.slurm.yaml
```

The driver must be `COMPLETED` with `0:0`, and the matching PostgreSQL run must
be `completed`. Take the run ID from the log or inspection output:

```bash
RUN_ID="paste-the-first-run-id-here"
"$EXPOPS_PYTHON" deployment.py inspect --compute compute.git.slurm.yaml \
  --run-id "$RUN_ID" --download-report reports/first
```

For a fresh metadata/cache namespace, expect `{"completed": 25}` and one chart
group. Confirm all 25 process records, not merely the final success line. If
this namespace was used already, legitimate cache hits can appear on the first
run. The helper downloads and verifies the published GCS PNG.

From Windows, copy it for viewing:

```powershell
scp -J e1115319@stujump.comp.nus.edu.sg `
  e1115319@xlogin.comp.nus.edu.sg:~/fyp-expops/git-s3-gcs-supabase/reports/first/fraud_seed_data_parallel_report.png `
  .\fraud_seed_data_parallel_report.png
```

## 8. Repeat to verify cache reuse

Return to the same directory and keep the same source revision, configuration,
dataset, credentials and storage prefixes:

```bash
WARM_JOB_ID=$(sbatch --parsable --export=ALL run.slurm)
WARM_JOB_ID=${WARM_JOB_ID%%;*}
tail -F "driver-$WARM_JOB_ID.log"
```

After completion, inspect that run ID exactly as above. Expect `{"cached": 25}`,
run status `completed`, identical metrics and a retrievable PNG. The controller
still provisions workers, checks inputs and retrieves source on a warm run;
cache reuse avoids process recomputation, not all startup or network work.
Worker jobs cancelled by the controller during normal teardown are expected;
use the driver exit and pipeline/process records to judge success.

When finished submitting runs:

```bash
unset CREDIT_CARD_FRAUD_SQL_PASSWORD
```

To cancel an active driver, use `scancel "$JOB_ID"` and inspect `squeue -u "$USER"`
for any remaining worker jobs. Keep the workspaces and GCS objects when comparing
runs; do not clear cache between the cold and warm tests.

## Release installation and current pain points

The package already declares extras for PostgreSQL, S3, GCS and SLURM. Once the
correct project is published to PyPI, the normal installation will be a versioned
`pip install 'expops[postgres,aws,gcp,slurm]==<released-version>'` in a shared venv.
Until then, pip also accepts a wheel or a commit-pinned Git package URL; see
[pip VCS support](https://pip.pypa.io/en/stable/topics/vcs-support/). The platform
commits from this test are local and should not be assumed available through a
remote Git installation yet.

The main current friction is identifying a pre-release runtime, loading provider
credentials, confirming database network reachability, constraining SDK versions,
and collecting run/cache/report evidence through an example helper. A packaged
runtime and platform-level deployment/status commands could simplify that later.
The experiment source and CSV already avoid manual archive upload in this flow.
