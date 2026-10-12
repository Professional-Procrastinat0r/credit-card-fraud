# Git source, S3 input and GCS outputs on SLURM

This deployment runs the 25-process nested fraud experiment with streaming input
and SQLite metadata. It needs an installed ExpOps runtime and cloud credentials,
but no existing fraud checkout, local CSV, database server or database password.

| Resource | Location |
|---|---|
| Project source | Git commit `8e76706f5394483d82126dbab671e4ec92639cf3` |
| Training CSV | `s3://expops-test-bucket-755933694771-ap-southeast-1-an/credit-card-fraud/dataset/creditcard.csv` |
| Cache | `gs://expops-example-credit-card-fraud/credit-card-fraud/slurm-git-s3-sqlite/cache/` |
| Artefacts | `gs://expops-example-credit-card-fraud/credit-card-fraud/slurm-git-s3-sqlite/artefact/` |
| Metadata | Node-local SQLite; persistent snapshot at `sqlite-state/metadata.sqlite` |

The deployment branch is `feature/git-s3-gcs-sqlite-slurm`. After merging, download
the same files from `main`. The Git source commit pin is independent of the
branch used to download deployment files. Update that pin deliberately when
you want to execute changed project code.

## SQLite placement and persistence

The platform uses SQLite WAL. All processes accessing that live database must
run on one physical host; WAL does not support a network filesystem. See
[SQLite's WAL requirements](https://sqlite.org/wal.html).

The supplied batch driver and both Dask workers request **`xcnc17`**. They are
separate SLURM jobs on the same node. The driver creates a private database under
node-local `/var/tmp`, restores the preceding snapshot if present, and records its absolute
path in `compute.resolved-<job-id>.yaml`. The platform's interpreter handoff and
worker plans therefore select the same database. Shared home still holds source,
environments, credentials and workspaces; GCS holds cache bytes and artefacts.
On this cluster `/dev/shm` is private to each allocation, so separate worker jobs
cannot share a database there even on the same host. `/var/tmp` is local XFS
and was verified visible across separate allocations on `xcnc17`.

Before normal job exit, including an ordinary command failure, the driver uses
SQLite's backup API to save an integrity-checked snapshot atomically into shared
home. The snapshot uses rollback journaling; it is not the live worker database.
A file lock prevents two driver allocations from restoring and overwriting the
same snapshot. Successful backup removes the private node-local directory.
The next allocation restores metadata and can discover the existing GCS cache.

This choice trades multi-node scaling for a server-free test. To change nodes,
edit **both** the batch driver and compute file to request the same replacement
node. Do not broaden the worker node list while retaining SQLite. For workers
on different physical nodes, choose a reachable network metadata service.
This is a deployment decision, not a VFS restriction.

The snapshot is saved at exit, not after every process. A hard kill or node loss
can lose the current allocation's metadata; the previous snapshot remains.
An unsuccessful backup fails the job and retains the live database for recovery.
Preserve `sqlite-state` and the cloud objects between cache tests.

The initial `/dev/shm` attempt (`936125`) failed when workers in separate job
namespaces could not find the producer's metadata. The driver preserved its
failed-run snapshot. Independent allocations then confirmed that `/var/tmp`
is visible across jobs while `/dev/shm` is isolated. The supplied driver uses
the verified `/var/tmp` placement.

Verified on 12 October 2026 with the full 284,807-row S3 dataset:

| Allocation | Result | Driver elapsed |
|---|---|---|
| Cold `936194` | All 25 processes completed; one chart group | 7m 11s |
| New allocation `936241` | All 25 processes cached; one chart group | 1m 33s |

Both drivers exited `0:0`. The second restored the snapshot into a different
node-local path. Aggregate metrics and the verified GCS PNG were identical;
they also matched the preceding Redis test. The saved snapshot passed SQLite's
integrity check. These timings exclude the fresh environment installation done
during the initial attempt; allow additional time on your first run.

That initial setup printed temporary pip dependency warnings before the platform
dependencies were installed. Dask also reported differing ancillary package
versions between the outer scheduler and project environment. Those messages
were not the pipeline failure: the failure was isolated database placement.
Use the final driver exit code, process records and snapshot check below to
verify a run rather than treating every log line labelled `ERROR` as fatal.

## Current runtime

The tested platform source is under
`~/fyp-expops/vfs-test-2026-10-12/platform`. The prepared interpreter is
`~/fyp-expops/vfs-test-2026-10-12/cloud-preflight/.venv/bin/python`.
It imports that source and has SQLite/SQLAlchemy, S3, GCS and SLURM dependencies.
The older `~/fyp-expops/expops-platform` is not the current deployment.
This test venv has no `expops` console script, so use the explicit interpreter
with `-m expops.main` below.

Hosted PostgreSQL and Redis endpoints timed out from the cluster in earlier
tests; the cause was not established. This SQLite profile needs neither endpoint
nor the Redis binary/password used by the preceding allocation-owned Redis test.

## 1. Connect

From Windows PowerShell:

```powershell
ssh -J e1115319@stujump.comp.nus.edu.sg e1115319@xlogin.comp.nus.edu.sg
```

All remaining commands are Bash on the cluster unless marked PowerShell.

## 2. Select the runtime and create a run directory

```bash
export EXPOPS_PYTHON="$HOME/fyp-expops/vfs-test-2026-10-12/cloud-preflight/.venv/bin/python"
"$EXPOPS_PYTHON" -c 'import expops, sqlite3, sqlalchemy, s3fs, gcsfs, dask_jobqueue; print(expops.__file__)'
"$EXPOPS_PYTHON" -m expops.main run --help

mkdir -p "$HOME/fyp-expops/git-s3-gcs-sqlite"
cd "$HOME/fyp-expops/git-s3-gcs-sqlite"
umask 077
export TMPDIR="$PWD/tmp" TMP="$PWD/tmp" TEMP="$PWD/tmp"
export MLOPS_WORKSPACE_BASE_DIR="$PWD/workspaces"
export XDG_CACHE_HOME="$PWD/cache" PIP_CACHE_DIR="$PWD/pip-cache"
mkdir -p "$TMPDIR" "$MLOPS_WORKSPACE_BASE_DIR" "$XDG_CACHE_HOME" "$PIP_CACHE_DIR"
"$EXPOPS_PYTHON" -c 'import tempfile; print(tempfile.gettempdir())'
quota -s
```

The temporary path should be below this run directory. The inline redirection
avoids this cluster's small per-user `/tmp` quota. Only the small live metadata
database uses node-local `/var/tmp`; datasets and workspaces do not.

For a future release, activate a shared venv containing the released package and
set `EXPOPS_PYTHON="$(command -v python)"`. The installed `expops` command is
equivalent to `"$EXPOPS_PYTHON" -m expops.main`. Installing the platform does not
install fraud model/reporting requirements; ExpOps prepares those separately.

## 3. Download deployment files only

```bash
FRAUD_DEPLOY_REF="feature/git-s3-gcs-sqlite-slurm"
RAW="https://raw.githubusercontent.com/Professional-Procrastinat0r/credit-card-fraud/$FRAUD_DEPLOY_REF"
curl --fail --location "$RAW/configs/compute.git.slurm.yaml" -o compute.git.slurm.yaml
curl --fail --location "$RAW/configs/storage-constraints.txt" -o storage-constraints.txt
curl --fail --location "$RAW/scripts/run_git_slurm.sbatch" -o run.slurm
curl --fail --location "$RAW/scripts/slurm_deployment.py" -o deployment.py
export PIP_CONSTRAINT="$PWD/storage-constraints.txt"
```

The constraints retain storage SDK versions verified together while project
environments are built. The batch driver handles SQLite placement and snapshots;
`deployment.py` provides project checks, report retrieval and the backup helper.

You do not need to clone or upload the fraud repository. `--project local`
selects the Git mount containing `configs/project_config.yaml`; that configuration
selects model code, reporting code and requirements. ExpOps retrieves the source
into `.expops-sources/credit-card-fraud`. Here `local` is a mount alias for Git.
The S3 dataset is already uploaded, so no dataset upload is needed either.

## 4. Load existing cloud and Git credentials

```bash
source "$HOME/.config/expops/cloud.env"
git ls-remote https://github.com/Professional-Procrastinat0r/credit-card-fraud.git \
  refs/heads/feature/git-s3-gcs-sqlite-slurm
```

This uses the existing GCP ADC, AWS `expops` profile and Git credential helper.
Workers read the credential files through shared home. No database credentials
or Redis environment variables are required. A fresh user must provision their
own provider credentials; they do not belong in YAML or source control.

## 5. Check files and optionally retrieve source

```bash
"$EXPOPS_PYTHON" deployment.py preflight --compute compute.git.slurm.yaml --files-only
"$EXPOPS_PYTHON" -m expops.main run --project local \
  --compute compute.git.slurm.yaml --prepare-only
ls .expops-sources/credit-card-fraud/configs
```

The preflight reads Git source and the S3 CSV size/header, then writes and reads
two tiny GCS `_preflight` objects retained as evidence. Use `--files-only` on the
login node: the full metadata check runs inside the allocated driver.

`--prepare-only` retrieves source without building environments, submitting
workers or connecting to metadata. Streaming input does not save a raw local
CSV, though pandas still holds the dataset in memory. Intermediate results,
models and workspace files can still use disk and GCS.

## 6. Submit the driver

```bash
JOB_ID=$(sbatch --parsable --export=ALL run.slurm)
JOB_ID=${JOB_ID%%;*}
printf 'Driver job: %s\n' "$JOB_ID"
squeue -u "$USER"
tail -F "driver-$JOB_ID.log"
```

Ctrl+C stops following the log without cancelling the job. The driver restores
SQLite, checks the mounted files and database, then invokes:

```bash
"$EXPOPS_PYTHON" -m expops.main run --project local --compute "$COMPUTE_CONFIG"
```

ExpOps submits two additional SLURM worker jobs. Do not add `--local`, which
replaces the selected provider. The model and reporting environments are
prepared automatically. The pipeline validates the full CSV, trains three
models, scores nine partitions, aggregates metrics and publishes a PNG to GCS.

The workers have 30-minute walltime and the driver one hour. Pending worker jobs
can exceed the 10-minute startup timeout; adjust it deliberately if necessary.

## 7. Verify completion and retrieve the report

After the driver exits:

```bash
sacct -j "$JOB_ID" -X --format=JobID,JobName,State,ExitCode,Elapsed,NodeList
grep -E 'Pipeline|Process results|exit status|snapshot|ERROR|Traceback' "driver-$JOB_ID.log"
"$EXPOPS_PYTHON" -m json.tool "results/run-$JOB_ID.json"
ls -lh sqlite-state/metadata.sqlite
ls -lh "results/report-$JOB_ID/fraud_seed_data_parallel_report.png"

"$EXPOPS_PYTHON" - <<'PY'
import sqlite3
with sqlite3.connect('file:sqlite-state/metadata.sqlite?mode=ro', uri=True) as db:
    print('Snapshot integrity:', db.execute('PRAGMA integrity_check').fetchone()[0])
PY
```

The driver must be `COMPLETED` with exit code `0:0`. The JSON must show
`status: completed`, 25 process records and one chart group. An empty metadata
snapshot starts cold: expect `{"completed": 25}`. Later runs can be cached.
The exported JSON and verified PNG remain readable after the live database has
been removed. The saved SQLite snapshot contains metadata for the next run.
Do not use the per-job resolved config after exit; its node-local DB is gone.

From Windows, replace the job ID and copy the report:

```powershell
$jobId = "YOUR_DRIVER_JOB_ID"
scp -J e1115319@stujump.comp.nus.edu.sg `
  "e1115319@xlogin.comp.nus.edu.sg:~/fyp-expops/git-s3-gcs-sqlite/results/report-$jobId/fraud_seed_data_parallel_report.png" `
  .\fraud_seed_data_parallel_report.png
```

## 8. Repeat to verify cache reuse

Wait for the first job to finish; retain the same run directory, snapshot,
source revision, dataset and GCS prefixes:

```bash
WARM_JOB_ID=$(sbatch --parsable --export=ALL run.slurm)
WARM_JOB_ID=${WARM_JOB_ID%%;*}
tail -F "driver-$WARM_JOB_ID.log"
```

After the second job exits:

```bash
sacct -j "$WARM_JOB_ID" -X --format=JobID,JobName,State,ExitCode,Elapsed,NodeList
"$EXPOPS_PYTHON" - "$JOB_ID" "$WARM_JOB_ID" <<'PY'
import hashlib, json, sys
from pathlib import Path
cold, warm = [json.loads(Path(f'results/run-{job}.json').read_text()) for job in sys.argv[1:]]
print('Cold:', cold['status'], cold['processes'])
print('Warm:', warm['status'], warm['processes'])
assert cold['status'] == warm['status'] == 'completed'
assert cold['processes'] == {'completed': 25}
assert warm['processes'] == {'cached': 25}
assert cold['summary_metrics'] == warm['summary_metrics']
reports = [Path(f'results/report-{job}/fraud_seed_data_parallel_report.png') for job in sys.argv[1:]]
assert len({hashlib.sha256(p.read_bytes()).hexdigest() for p in reports}) == 1
print('Cache reuse, identical metrics and report verified')
PY
```

The new allocation restores metadata into a different node-local pathname;
cached result objects remain in GCS. Changing this database pathname does not
change experiment content identity. A cache hit still involves source/input
checks and worker startup. Worker cancellation during normal teardown does not
itself indicate a failed pipeline.

To cancel a job, use `scancel "$JOB_ID"` and check `squeue -u "$USER"` for remaining
workers. Preserve the state and cloud objects when comparing cold and warm runs.

## Release installation

Once a VFS-capable version is published to PyPI, installation can use a versioned
`pip install 'expops[aws,gcp,slurm]==<released-version>'` in a shared venv; SQLite
support needs no extra database service. Until then, install a platform wheel or
an available commit-pinned Git package. Do not assume unpublished local platform
commits are installable from GitHub or PyPI.
