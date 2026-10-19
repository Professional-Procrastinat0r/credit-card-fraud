# Run credit-card-fraud on SLURM

This workflow uses Git source, the full S3 dataset, GCS cache and artefacts, and
SQLite metadata. Download one compute config and run the ordinary ExpOps CLI.
ExpOps retrieves the project, prepares launcher environments and submits two
worker jobs. Each job builds/reuses node-local project venvs before starting
Dask. No project-specific launch or inspection scripts are required. ExpOps
automatically prepares and publishes the worker package for the current code.

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

Set the bootstrap interpreter and worker disk root once for this deployment:

```bash
export MLOPS_WORKER_PYTHON="$HOME/fyp-expops/expops-platform/.venv/bin/python"
export MLOPS_WORKER_BASE_DIR="/var/tmp/$USER-expops-credit-card-fraud"
```

These variables are real alternatives to YAML settings: the compute file does
not need matching entries or variable references. Explicit `options.worker_python`
and `options.worker_base_dir` override the environment. ExpOps records launcher
values in the run's compute plan and communicates them to the worker jobs.
The base installation still relies on NUS shared home explicitly. It must
contain the updated ExpOps with `expops.environment.worker_bootstrap` and the
cache mount's provider dependencies. Verify that before running:

```bash
python -c 'import expops.environment.worker_bootstrap'
```

If that import fails, install the current platform source using the development
section below first.
Project model/reporting environments are now installed on each worker's disk;
no shared project-venv activation or `worker_environments` map is needed. On a
cluster without shared home, provision the base runtime and credentials on each
node and set `MLOPS_WORKER_PYTHON` and the prologue to those worker-side paths.
Project source is delivered through Dask; installation inputs and dataset/output
files are obtained through VFS.

The base directory contains separate
`environments`, `workspaces` and `dask` directories; cleaning temporary
workspaces does not remove the retained environments. You can alternatively
provision the worker variables in the sourced deployment file on each node;
launcher/YAML settings take precedence. Python defaults to `python3` from the
worker's PATH and the disk root defaults under its SLURM temporary directory or
`/tmp`; use the explicit `/var/tmp` root on NUS to avoid its small `/tmp` quota.
Update ExpOps on the driver and in the base bootstrap installation after code
changes. No manual wheel build or shared project environment activation is needed.

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
The printed launcher temporary directory should be inside the run directory.
Worker process workspaces, environment caches and Dask scratch use separate
directories below the explicitly configured `/var/tmp` root. The thread limits
suit the one-core workers; `zlib` selects a common Dask compression codec.
The private `/var/tmp` directory is the SQLite location in the compute file.

## 4. Obtain the compute config

ExpOps automatically builds its worker package from an isolated snapshot of the
running platform source, or retrieves and verifies the matching installed release
wheel. Verified packages are cached under `$XDG_CACHE_HOME/expops/worker-packages`.
Changed source contents select a new package even when the version label stays
the same. The build does not modify the active source checkout.

The controller publishes that package and the project's requirements through the
GCS cache mount and communicates their references to workers. No `runtime` mount,
`platform_wheel` setting or manual build step is needed. The driver needs access
to build dependencies or its matching release artifact; worker pip needs package
access. Offline deployments can still supply an advanced
`worker_bootstrap: {platform_wheel: <mounted-wheel>, wheelhouse: <mounted-wheels>}`
override containing the required compatible packages.

Transfer the updated compute file from this working checkout. Until these changes
are published, downloading an older branch URL will retrieve the previous setup.
From Windows PowerShell in `D:\NUS\FYP`:

```powershell
scp -o ProxyJump=e1115319@stujump.comp.nus.edu.sg .\credit-card-fraud\configs\compute.git.slurm.yaml e1115319@xlogin.comp.nus.edu.sg:~/fyp-expops/git-s3-gcs-sqlite/compute.git.slurm.yaml
```

Once published, the same compute file can be downloaded without a local project
checkout. Its project Git source remains pinned to
`8e76706f5394483d82126dbab671e4ec92639cf3` independently of the deployment file.

## 5. Run, check completion and repeat for caching

Back in the allocated compute-node shell, from the run directory:

```bash
expops run compute.git.slurm.yaml
printf 'ExpOps exit code: %s\n' "$?"
```

The positional argument selects the compute config; its `code` mount selects
the default project containing `configs/project_config.yaml`. Use `--project`
only for an explicit mount/subtree override. The pinned source still uses
`local/...` declarations, so the config provides that Git alias too.
ExpOps retrieves the project into `.expops-sources/credit-card-fraud`, loads its
scripts and requirements, and runs the declared pipeline. You do not separately
clone/upload the repo or download/upload the already available S3 dataset.

To check only source retrieval, you may add `--prepare-only` to the same command.
That prepares the source without executing the pipeline.

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
expops run compute.git.slurm.yaml
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
| `$XDG_CACHE_HOME/expops/worker-packages/` | Automatically prepared and verified driver-side worker packages |
| `~/fyp-expops/git-s3-gcs-sqlite/` | Compute config, retrieved fraud source, logs, launcher project environments and temporary workspaces |
| `/var/tmp/e1115319-expops-credit-card-fraud/environments` on each worker node | Reusable worker-local model and reporting environments |
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

Worker environment caches are separate from SQLite and the process-result cache.
Identical bootstrap inputs reuse a validated local environment; changed inputs
create a new cache entry. Old environment entries and staged GCS runtime files
are not automatically garbage-collected. Remove unused entries only when no
worker is using them. Use pinned requirements or a locked compatible wheelhouse
when identical dependency resolutions across nodes/runs are required.

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
