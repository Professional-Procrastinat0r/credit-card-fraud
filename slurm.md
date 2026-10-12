# Run Git source, S3 input and GCS outputs on SLURM

Once ExpOps and provider credentials are installed, download one compute config
and run the ordinary CLI. No project-specific launch, backup or inspection
scripts are required. ExpOps retrieves the project from Git, creates its model
and reporting environments, submits the Dask worker jobs, and runs the pipeline.

This profile uses Git source commit `8e76706f5394483d82126dbab671e4ec92639cf3`,
the full S3 dataset, GCS cache and artefacts, and SQLite metadata. Download the
deployment config from `feature/git-s3-gcs-sqlite-slurm`; after merging, use `main`.
The Git mount's source pin is independent of the deployment config branch.

## 1. Connect and obtain a driver allocation

From Windows PowerShell:

```powershell
ssh -J e1115319@stujump.comp.nus.edu.sg e1115319@xlogin.comp.nus.edu.sg
```

Then in Bash on the login node:

```bash
salloc --partition=normal --account=allusers --qos=normal \
  --nodes=1 --ntasks=1 --cpus-per-task=1 --mem=4G \
  --time=01:00:00 --nodelist=xcnc17 srun --pty bash
hostname
```

Wait for the allocation. `hostname` should report `xcnc17`. This is normal SLURM
allocation handling, not an ExpOps script. ExpOps submits the two worker jobs
using the options in the compute file. See [salloc](https://slurm.schedmd.com/salloc.html)
and [srun](https://slurm.schedmd.com/srun.html).

## 2. Set the runtime, credentials and writable temporary paths

The current prepared platform interpreter is already installed on shared home.
This pre-release environment has no `expops` console script, so invoke the module:

```bash
export EXPOPS_PYTHON="$HOME/fyp-expops/vfs-test-2026-10-12/cloud-preflight/.venv/bin/python"
source "$HOME/.config/expops/cloud.env"

mkdir -p "$HOME/fyp-expops/git-s3-gcs-sqlite"
cd "$HOME/fyp-expops/git-s3-gcs-sqlite"
umask 077

export TMPDIR="$PWD/tmp" TMP="$PWD/tmp" TEMP="$PWD/tmp"
export MLOPS_WORKSPACE_BASE_DIR="$PWD/workspaces"
export XDG_CACHE_HOME="$PWD/cache" PIP_CACHE_DIR="$PWD/pip-cache"
export DASK_DISTRIBUTED__COMM__COMPRESSION=zlib
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
mkdir -p "$TMPDIR" "$MLOPS_WORKSPACE_BASE_DIR" "$XDG_CACHE_HOME" "$PIP_CACHE_DIR"

# Match the private node-local SQLite directory in the compute config.
mkdir -p /var/tmp/e1115319-expops-credit-card-fraud
chmod 700 /var/tmp/e1115319-expops-credit-card-fraud

"$EXPOPS_PYTHON" -c 'import expops, tempfile; print(expops.__file__); print(tempfile.gettempdir())'
quota -s
```

The inline temporary-path setup avoids this cluster's small per-user `/tmp`
quota. The existing cloud credential file selects GCP ADC and the AWS `expops`
profile; Git uses its configured credential helper. No database password is
needed. A fresh user must install a VFS-capable ExpOps runtime with AWS, GCP and
SLURM dependencies and provision their own provider credentials once.

For a released package, activate its venv and use `expops` directly. The current
test platform source is under `~/fyp-expops/vfs-test-2026-10-12/platform`; the older
`~/fyp-expops/expops-platform` directory is not the current deployment.

## 3. Download one config and run

```bash
curl --fail --location \
  "https://raw.githubusercontent.com/Professional-Procrastinat0r/credit-card-fraud/feature/git-s3-gcs-sqlite-slurm/configs/compute.git.slurm.yaml" \
  -o compute.git.slurm.yaml

"$EXPOPS_PYTHON" -m expops.main run --project local --compute compute.git.slurm.yaml
printf 'ExpOps exit code: %s\n' "$?"
grep -h 'Process results:' .expops-sources/credit-card-fraud/.credit-card-fraud/logs/*.log | tail -n 2
```

With a normal package installation, the equivalent command is:

```bash
expops run --project local --compute compute.git.slurm.yaml
```

There is no `--config` flag for `run`. `--project local` selects the Git mount
containing `configs/project_config.yaml`; `--compute` selects the deployment
config. ExpOps retrieves the source into `.expops-sources/credit-card-fraud`.
You do not need to clone/upload the project or upload the already available S3
dataset. Training input streams from S3; intermediate results and the report
are stored through the GCS cache and artefact mounts.

An optional source-only check uses the same config:

```bash
"$EXPOPS_PYTHON" -m expops.main run --project local \
  --compute compute.git.slurm.yaml --prepare-only
```

## 4. Repeat to check caching, then leave the allocation

Run the identical command again:

```bash
"$EXPOPS_PYTHON" -m expops.main run --project local --compute compute.git.slurm.yaml
printf 'ExpOps exit code: %s\n' "$?"
```

The first run with an empty database should report 25 executed processes and
zero failures; the repeat should report 25 cached processes and zero failures.
Both commands should exit zero. The CLI prints the run ID and project log path.
The saved logs are under `.expops-sources/credit-card-fraud/.credit-card-fraud/logs`.
Reports remain in the GCS artefact mount; the platform's chart metadata records
their managed object references. Inspecting/downloading reports is separate from
launching an experiment and does not require a launch helper.

```bash
exit
```

This ends the interactive shell and releases the driver allocation. A later
allocation on `xcnc17` can reuse the same SQLite file and GCS cache.

## SQLite deployment choice

The compute config points to
`/var/tmp/e1115319-expops-credit-card-fraud/metadata.sqlite` on `xcnc17`.
The platform uses WAL, so driver and workers must access the same local database
on the same physical host. See [SQLite WAL requirements](https://sqlite.org/wal.html).
Shared home is a network filesystem; it is not the live WAL database location.
On this cluster `/dev/shm` is isolated between separate allocations, while
`/var/tmp` is local XFS and is visible to separate jobs on the same node.

This simple profile leaves metadata on the node instead of automatically
backing it up to shared home. Node cleanup or disk loss can remove those run
records and cache indices; the GCS objects remain, but a new empty database may
require recomputation. Choose a reachable network database when metadata
durability or workers across multiple nodes are needed. These are database
deployment choices, not VFS policies.

The earlier Git/S3/GCS SQLite acceptance passed all 25 processes cold (`936194`)
and all 25 cached in a new allocation (`936241`), with identical metrics and
report bytes. Those tests used additional snapshot and evidence collection
scaffolding. That scaffolding has been removed from the user workflow.
The direct CLI was also verified in an interactive allocation (`936423`) with
the prepared environments and existing metadata: all 25 processes cached, zero
failures, exit code zero. It used no launch/inspection helper or external pip
constraints file, and left its stable node-local database available for reuse.
