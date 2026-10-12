# Run credit-card-fraud on SLURM

This workflow uses Git source, the full S3 dataset, GCS cache and artefacts, and
SQLite metadata. Download one compute config and run the ordinary ExpOps CLI.
ExpOps retrieves the project, prepares its environments and submits two Dask
worker jobs. No project-specific launch or inspection scripts are required.

The commands below target the existing NUS account `e1115319` and node `xcnc17`.
ExpOps is installed at `~/fyp-expops/expops-platform`, and credentials are already
configured. A different account must adapt the compute file's node, account,
SQLite path, buckets and AWS profile, and provision its own credentials once.

## 1. Connect and allocate the driver

In Windows PowerShell:

```powershell
ssh -J e1115319@stujump.comp.nus.edu.sg e1115319@xlogin.comp.nus.edu.sg
```

On the login node, obtain a compute-node shell:

```bash
salloc --partition=normal --account=allusers --qos=normal \
  --nodes=1 --ntasks=1 --cpus-per-task=1 --mem=4G \
  --time=01:00:00 --nodelist=xcnc17 srun --pty bash
hostname
```

Wait for the allocation; `hostname` should report `xcnc17`. This places the
ExpOps driver on the same node as the workers specified in the compute config,
so they can use the same node-local SQLite database. If you already have an
interactive shell on that node, use it rather than requesting another allocation.

## 2. Activate ExpOps and load credentials

In that compute-node shell:

```bash
source "$HOME/fyp-expops/expops-platform/.venv/bin/activate"
source "$HOME/.config/expops/cloud.env"
command -v expops
```

Activation makes the installed `expops` and `python` commands available in this
shell. The existing credential file selects GCP application-default credentials
and AWS profile `expops`; Git uses the configured credential helper. Activate and
load these variables again in each new shell. Credentials stay outside the repo.

## 3. Choose the run directory and writable temporary paths

```bash
umask 077
mkdir -p "$HOME/fyp-expops/git-s3-gcs-sqlite"
cd "$HOME/fyp-expops/git-s3-gcs-sqlite"

export TMPDIR="$PWD/tmp" TMP="$PWD/tmp" TEMP="$PWD/tmp"
export MLOPS_WORKSPACE_BASE_DIR="$PWD/workspaces"
export XDG_CACHE_HOME="$PWD/cache" PIP_CACHE_DIR="$PWD/pip-cache"
export DASK_DISTRIBUTED__COMM__COMPRESSION=zlib
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
mkdir -p "$TMPDIR" "$MLOPS_WORKSPACE_BASE_DIR" "$XDG_CACHE_HOME" "$PIP_CACHE_DIR"

mkdir -p /var/tmp/e1115319-expops-credit-card-fraud
chmod 700 /var/tmp/e1115319-expops-credit-card-fraud

python -c 'import tempfile; print(tempfile.gettempdir())'
quota -s
```

This cluster has a small per-user `/tmp` quota. Redirecting Python temporary
files, pip caches and ExpOps workspaces to shared home avoids that limit.
The printed temporary directory should be inside the run directory. The thread
limits suit the one-core workers; `zlib` selects a common Dask compression codec.
The private `/var/tmp` directory is the SQLite location in the compute file.

## 4. Download the compute config and run

```bash
curl --fail --location \
  "https://raw.githubusercontent.com/Professional-Procrastinat0r/credit-card-fraud/feature/git-s3-gcs-sqlite-slurm/configs/compute.git.slurm.yaml" \
  -o compute.git.slurm.yaml

expops run --project local --compute compute.git.slurm.yaml
printf 'ExpOps exit code: %s\n' "$?"
```

After this branch is merged, replace `feature/git-s3-gcs-sqlite-slurm` in the URL
with `main`. The config independently pins the Git source to
`8e76706f5394483d82126dbab671e4ec92639cf3`.

`--project local` selects the Git mount containing `configs/project_config.yaml`.
Here `local` is an alias for Git, not a local-filesystem provider. `--compute`
selects the downloaded deployment config; there is no `run --config` argument.
ExpOps retrieves the project into `.expops-sources/credit-card-fraud`, loads its
scripts and requirements, and runs the declared pipeline. You do not separately
clone/upload the repo or download/upload the already available S3 dataset.

To check only source retrieval, you may add `--prepare-only` to the same command.
That prepares the source without executing the pipeline.

## 5. Check completion and repeat for caching

The CLI prints the run ID, log path and process summary. Expect exit code 0 and
zero failed processes. With an empty database and cache, the first run should
execute all 25 processes. An unchanged repeat with valid cache entries should
report all 25 cached. Existing metadata was preserved during cleanup, so your
next run may already be a cache hit. The cache TTL is 24 hours.

To inspect the latest log:

```bash
latest_log=$(ls -t .expops-sources/credit-card-fraud/.credit-card-fraud/logs/*.log | head -n 1)
grep -E 'Process results:|Pipeline completed successfully' "$latest_log"
```

Repeat the normal command:

```bash
expops run --project local --compute compute.git.slurm.yaml
printf 'ExpOps exit code: %s\n' "$?"
```

Reports are saved through the GCS `artefact` mount; the run's chart metadata
records the managed object reference. A cache hit reuses stored process outputs,
including the report. Once finished:

```bash
exit
```

This leaves the compute-node shell and releases the driver allocation. A later
allocation on `xcnc17` can reuse the SQLite database and GCS cache.

## Where files and state live

| Location | Purpose |
| --- | --- |
| `~/fyp-expops/expops-platform/` | Installed platform source and `.venv` |
| `~/fyp-expops/git-s3-gcs-sqlite/` | Compute config, retrieved fraud source, logs, project environments and temporary workspaces |
| `/var/tmp/e1115319-expops-credit-card-fraud/metadata.sqlite` on `xcnc17` | Run metadata and cache indices |
| S3 `expops-test-bucket-755933694771-ap-southeast-1-an/credit-card-fraud/dataset/` | Streaming input dataset |
| GCS `expops-example-credit-card-fraud/credit-card-fraud/slurm-git-s3-sqlite/cache` and `/artefact` | Managed process outputs and reports |
| `~/.config/expops/` | Provider credentials, outside the run and source directories |

SQLite WAL requires driver and workers to access the database on the same host.
Shared home is NFS and is not the live WAL location. On this cluster `/dev/shm`
is isolated between allocations; `/var/tmp` is node-local and visible to separate
jobs on `xcnc17`. Node cleanup or disk loss can remove its metadata and cache
indices even while GCS objects remain. Choose a reachable network database for
durable metadata or workers across multiple hosts. This is a database deployment
choice, not a VFS policy.

## Development only: upload or update expops-platform

This section installs the platform from a development checkout. It is separate
from running the fraud experiment. Your current installation already exists,
so skip it for normal runs. A published release would be installed as a versioned
package into a Python environment; production users would not upload our checkout.

### Export and upload the source

From Windows PowerShell in `D:\NUS\FYP`, commit the platform changes you intend
to test, then export tracked files from that commit:

```powershell
git -C .\expops-platform archive --format=tar.gz --output=..\expops-platform.tar.gz HEAD
ssh -J e1115319@stujump.comp.nus.edu.sg e1115319@xlogin.comp.nus.edu.sg 'mkdir -p ~/fyp-expops'
scp -o ProxyJump=e1115319@stujump.comp.nus.edu.sg .\expops-platform.tar.gz e1115319@xlogin.comp.nus.edu.sg:~/fyp-expops/expops-platform.tar.gz
```

The archive contains committed source, not local credentials, environments, Git
history or untracked files. Uncommitted changes are intentionally not uploaded.

### Install into the canonical location

In Bash on the login node, while no ExpOps runs are active:

```bash
umask 077
mkdir -p "$HOME/fyp-expops/expops-platform"
cd "$HOME/fyp-expops/expops-platform" || exit
export TMPDIR="$PWD/.tmp" TMP="$PWD/.tmp" TEMP="$PWD/.tmp"
export PIP_CACHE_DIR="$PWD/.pip-cache"
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR"

# Replace the previously uploaded source; retain this environment and its caches.
test -s ../expops-platform.tar.gz || exit
find . -mindepth 1 -maxdepth 1 \
  ! -name .venv ! -name .tmp ! -name .pip-cache -exec rm -rf -- {} +
tar -xzf ../expops-platform.tar.gz -C .

# On the first installation only; subsequent updates reuse the existing venv.
test -x .venv/bin/python || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[aws,gcp,slurm]'
python -m pip check
expops run --help
rm -- ../expops-platform.tar.gz
```

This requires a Python version supported by the project's dependencies; this
cluster installation uses Python 3.12. Upgrade pip before resolving the S3/GCS
dependencies to avoid the resolver failure encountered with pip 24. Editable
installation points at this stable source directory, so future source updates
do not need a new run directory. An archive has no `.git` history, so the package
can report fallback version `0.0.0`; record the exported commit separately when
tracking which development build was tested.

ExpOps normally installs itself into each project environment. After changing
the platform's declared dependencies, reinstall that editable package into any
existing project environments before rerunning:

```bash
platform="$HOME/fyp-expops/expops-platform"
for env in "$HOME/fyp-expops/git-s3-gcs-sqlite/.expops-sources/credit-card-fraud/.credit-card-fraud/envs/"*; do
  [ -x "$env/bin/python" ] || continue
  "$env/bin/python" -m pip install -e "$platform"
  "$env/bin/python" -m pip check
done
```

For a fresh run, ExpOps creates those project environments itself. Return to
step 1 for the normal experiment workflow; no development scripts are involved.
