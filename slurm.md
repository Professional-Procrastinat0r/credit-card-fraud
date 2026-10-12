# Git source, S3 input and GCS outputs on SLURM

This deployment uses the current 25-process nested fraud experiment with
streaming training input and Redis metadata inside the driver allocation. It needs an installed
ExpOps runtime and credentials, but no existing fraud checkout or local CSV.

| Resource | Location |
|---|---|
| Project source | Git commit `8e76706f5394483d82126dbab671e4ec92639cf3` |
| Training CSV | `s3://expops-test-bucket-755933694771-ap-southeast-1-an/credit-card-fraud/dataset/creditcard.csv` |
| Cache | `gs://expops-example-credit-card-fraud/credit-card-fraud/slurm-git-s3-redis/cache/` |
| Artefacts | `gs://expops-example-credit-card-fraud/credit-card-fraud/slurm-git-s3-redis/artefact/` |
| Metadata | Allocation-owned Redis with snapshots in shared home storage |

The deployment branch is `feature/git-s3-gcs-redis-slurm`. It builds on the
streaming fraud branch without adding the earlier backend-matrix fixture trees.
After merging, download the same files from `main`. The compute file's Git commit
pin remains independent of the branch used to download the deployment files;
update that pin deliberately when you want to execute changed project code.

## Current deployment

The latest tested platform source, including the helper-import and environment
bootstrap fixes, is under `~/fyp-expops/vfs-test-2026-10-12/platform`. The prepared
interpreter is
`~/fyp-expops/vfs-test-2026-10-12/cloud-preflight/.venv/bin/python`.
It imports that source and has the Redis, S3, GCS and SLURM libraries.
The older `~/fyp-expops/expops-platform` directory is not the current deployment.
The prepared test environment has no `expops` console script, so the commands
below use `python -m expops.main` through an explicit interpreter variable.

The configured Supabase endpoint timed out from the login and compute nodes.
Redis Cloud also timed out from `xlogin2` and `xcnc17`/`xcnc18`/`xcnc19`; the older
commented Redis hostname no longer resolved. These observations do not establish
the cause of the network restriction. This test therefore runs Redis inside the
SLURM allocation, as in the earlier combined acceptance.

The batch driver starts an authenticated Redis server on its allocated cluster
IP and a free port, then exports `MLOPS_REDIS_HOST`, `MLOPS_REDIS_PORT` and the
generated password before ExpOps resolves the worker plans. It also writes
`compute.resolved-<job-id>.yaml` with that endpoint, so controller interpreter
handoff uses the same address. It contains credential references, not passwords.
A worker does not
connect to its own localhost. Normal shutdown saves `redis-state/metadata.rdb`;
the next allocation reloads those cache indices and run records. GCS continues
to hold cached result bytes and artefacts.

Keep the same run directory for the cache test. A file lock prevents concurrent
drivers from using the same Redis state. Redis is stopped at job completion;
summaries and verified PNGs are exported before shutdown so they remain readable
afterward. This is a test deployment, not a continuously available metadata
service. An abrupt kill can lose changes since the last snapshot.

Verified on 12 October 2026 using the full 284,807-row S3 CSV:

| Allocation | Result | Driver elapsed |
|---|---|---|
| Cold `936020` | Completed; all 25 processes executed | 7m 27s |
| New allocation `936044` | Reloaded Redis snapshot; all 25 processes cached | 2m 41s |

Both parent jobs exited `0:0`. Metrics and the verified GCS PNG were identical.
The new allocation used a different port and password, confirming that metadata
reload preserved cache discovery. Redis was shut down after each job. Access
to the driver's Redis was also checked from `xcnc18` and `xcnc19`.
An initial attempt failed because controller handoff used the template localhost
endpoint; rendering the per-job compute file fixed that deployment error.
These timings used already prepared project environments after the initial
attempt built them; a fresh user's first environment setup takes additional time.

## 1. Connect to the cluster

From your Windows terminal:

```powershell
ssh -J e1115319@stujump.comp.nus.edu.sg e1115319@xlogin.comp.nus.edu.sg
```

All following commands are Bash on the cluster unless marked PowerShell.

## 2. Choose the runtime and create an empty run directory

```bash
export EXPOPS_PYTHON="$HOME/fyp-expops/vfs-test-2026-10-12/cloud-preflight/.venv/bin/python"
"$EXPOPS_PYTHON" -c 'import expops, redis, s3fs, gcsfs, dask_jobqueue; print(expops.__file__)'
"$EXPOPS_PYTHON" -m expops.main run --help
export EXPOPS_REDIS_SERVER="$HOME/fyp-expops/vfs-test-2026-10-12/redis/usr/bin/redis-server"
export EXPOPS_REDIS_LIBRARY_DIR="$HOME/fyp-expops/vfs-test-2026-10-12/redis/usr/lib/x86_64-linux-gnu"
test -x "$EXPOPS_REDIS_SERVER"

mkdir -p "$HOME/fyp-expops/git-s3-gcs-redis"
cd "$HOME/fyp-expops/git-s3-gcs-redis"
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
FRAUD_DEPLOY_REF="feature/git-s3-gcs-redis-slurm"
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

## 4. Load the existing cloud and Git credentials

```bash
source "$HOME/.config/expops/cloud.env"
git ls-remote https://github.com/Professional-Procrastinat0r/credit-card-fraud.git \
  refs/heads/feature/git-s3-gcs-redis-slurm
```

The cloud file selects the existing GCP ADC and AWS `expops` credential/config
files. Git uses its existing credential helper. Workers read these files through
shared home storage. A new user must provision their own credentials separately.

No Supabase or Redis Cloud password is required for this test. The driver creates
an allocation password and passes it through the configured environment secret
reference. Password values are not written into source, YAML or Redis config
files. The `redis-server` binary is separate from the Python `redis` client; both
already exist in the prepared test environment. A fresh deployment must install
a server binary or use a reachable managed Redis service instead.

## 5. Check mounted files and optionally retrieve source

```bash
"$EXPOPS_PYTHON" deployment.py preflight --compute compute.git.slurm.yaml --files-only
"$EXPOPS_PYTHON" -m expops.main run --project local \
  --compute compute.git.slurm.yaml --prepare-only
ls .expops-sources/credit-card-fraud/configs
```

The file check reads Git source and the S3 CSV size/header, then writes and reads
two tiny GCS `_preflight` objects retained as evidence. It starts no training run.
Use `--files-only` on the login node: metadata is checked inside the allocated
driver after Redis starts.

`--prepare-only` retrieves project source without submitting workers, building
environments or connecting to metadata. The actual run refreshes the named
source directory while preserving its runtime directory. It does not save a
prepared raw S3 CSV in streaming mode.

## 6. Submit the driver and let ExpOps provision workers

Submit from this run directory:

```bash
JOB_ID=$(sbatch --parsable --export=ALL run.slurm)
JOB_ID=${JOB_ID%%;*}
printf 'Driver job: %s\n' "$JOB_ID"
squeue -u "$USER"
tail -F "driver-$JOB_ID.log"
```

Use Ctrl+C to stop following the log; it does not cancel the job. The driver job
runs on `xcnc17`, starts Redis and checks authenticated PING plus a temporary
metadata write/read/delete from that compute node before invoking:

```bash
"$EXPOPS_PYTHON" -m expops.main run --project local --compute "$COMPUTE_CONFIG"
```

The SLURM provider submits two additional worker jobs in the configured pool.
Do not add `--local`: that would replace the requested SLURM provider. Environment
setup installs the declared model/reporting dependencies, then workers validate
the CSV, train three models, score nine held-out partitions, aggregate metrics
and publish the PNG to GCS. Raw CSV bytes stream from S3 into pandas; pandas
still holds the dataset in memory. Models, spilled payloads and result cache
objects use GCS; Redis keeps metadata and cache indices.

The default worker walltime is 30 minutes and driver walltime is one hour. Pending
jobs can exceed the 10-minute worker startup timeout; increase it deliberately
if necessary rather than assuming a pending job is a VFS failure.

## 7. Verify the first run and retrieve its report

After the driver exits:

```bash
sacct -j "$JOB_ID" -X --format=JobID,JobName,State,ExitCode,Elapsed
grep -E 'Pipeline|Process results|exit status|ERROR|Traceback' "driver-$JOB_ID.log"
"$EXPOPS_PYTHON" -m json.tool "results/run-$JOB_ID.json"
ls -lh redis-state/metadata.rdb
ls -lh "results/report-$JOB_ID/fraud_seed_data_parallel_report.png"
```

The driver must be `COMPLETED` with `0:0`. The summary must have `status: completed`,
25 process records and one chart group. A fresh state/cache namespace should show
`{"completed": 25}`. The summary also records metrics and managed chart references.
Redis is now stopped; use this exported JSON rather than a live metadata query
from the login node. `metadata.rdb` retains the backing metadata for the next run.

From Windows, copy the report (replace the example job ID):

```powershell
$jobId = "YOUR_DRIVER_JOB_ID"
scp -J e1115319@stujump.comp.nus.edu.sg `
  "e1115319@xlogin.comp.nus.edu.sg:~/fyp-expops/git-s3-gcs-redis/results/report-$jobId/fraud_seed_data_parallel_report.png" `
  .\fraud_seed_data_parallel_report.png
```

## 8. Repeat to verify cache reuse

Keep the same directory, source revision, configuration, dataset, Redis state
and GCS prefixes. Wait for the first driver to finish:

```bash
WARM_JOB_ID=$(sbatch --parsable --export=ALL run.slurm)
WARM_JOB_ID=${WARM_JOB_ID%%;*}
tail -F "driver-$WARM_JOB_ID.log"
```

After completion, inspect and compare both exported summaries:

```bash
"$EXPOPS_PYTHON" - "$JOB_ID" "$WARM_JOB_ID" <<'PY'
import json,sys
from pathlib import Path
cold,warm = [json.loads(Path(f"results/run-{job}.json").read_text()) for job in sys.argv[1:]]
print("Cold:",cold["status"],cold["processes"])
print("Warm:",warm["status"],warm["processes"])
assert cold["status"] == warm["status"] == "completed"
assert warm["processes"] == {"cached":25}
assert cold["summary_metrics"] == warm["summary_metrics"]
print("Cache reuse and identical metrics verified")
PY
ls -lh "results/report-$WARM_JOB_ID/fraud_seed_data_parallel_report.png"
```

The second driver reloads the saved Redis metadata, while cached results and
charts remain in GCS. It generates a new connection password and cluster endpoint;
neither changes the declared source/input/cache content identity. Startup still
retrieves source, checks inputs and provisions workers. Expected worker-job
cancellation during normal teardown does not imply a failed pipeline.

To cancel the driver, use `scancel "$JOB_ID"` and check `squeue -u "$USER"` for
remaining workers. Keep `redis-state`, the run directory and GCS objects when
comparing runs. Do not clear them between cold and warm tests.

## Release installation and current pain points

The package already declares extras for Redis, S3, GCS and SLURM. Once the
correct project is published to PyPI, the normal installation will be a versioned
`pip install 'expops[redis,aws,gcp,slurm]==<released-version>'` in a shared venv.
Until then, pip also accepts a wheel or a commit-pinned Git package URL; see
[pip VCS support](https://pip.pypa.io/en/stable/topics/vcs-support/). The platform
commits from this test are local and should not be assumed available through a
remote Git installation yet.

The main current friction is identifying a pre-release runtime, loading provider
credentials, confirming database network reachability, constraining SDK versions,
and collecting run/cache/report evidence through an example helper. A packaged
runtime and platform-level deployment/status commands could simplify that later.
The experiment source and CSV already avoid manual archive upload in this flow.
