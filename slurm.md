# Slurm deployment

This deployment bundles the code and credit-card dataset into one self-contained
archive. The cluster's `/tmp` filesystem has a small per-user quota, so both pip
temporary files and ExpOps process workspaces are redirected to persistent
storage under `~/fyp-expops`. The current smoke test uses local SQLite metadata
and local filesystem artifacts, so `~/fyp-expops` must be the same shared
filesystem when viewed from the login node and every allocated worker node.

This local-storage setup is suitable only for the initial controlled smoke test.
SQLite locking, particularly WAL mode, is not reliable on every network
filesystem, and it should not be treated as the coordination backend for later
multi-node scaling. A lock or I/O failure is a failed storage test; ExpOps will
not substitute in-memory state.

## 1. Build the code archive locally (PowerShell)

Run this from the Windows checkout. The archive contains
`credit-card-fraud/`, including `data/creditcard.csv`, and `expops-platform/`,
but excludes environments, runtime files, and frontend dependencies.

```powershell
Set-Location "D:\NUS\FYP"

$archive = "credit-card-fraud-slurm-deploy-$(Get-Date -Format yyyyMMdd-HHmmss).tar.gz"

tar.exe -czf $archive '--exclude=.git' '--exclude=.venv' '--exclude=.pytest_cache' '--exclude=node_modules' '--exclude=.credit-card-fraud' '--exclude=__pycache__' '--exclude=*.pyc' credit-card-fraud expops-platform
```


Upload the code archive under a stable remote filename:

```powershell
scp -o 'ProxyJump=e1115319@stujump.comp.nus.edu.sg' $archive 'e1115319@xlogin.comp.nus.edu.sg:~/credit-card-fraud-slurm-deploy.tar.gz'
```

## 2. Extract the bundle on the Slurm cluster (Bash)

```bash
mkdir -p "$HOME/fyp-expops"

tar -xzf "$HOME/credit-card-fraud-slurm-deploy.tar.gz" \
  -C "$HOME/fyp-expops"

ls -la "$HOME/fyp-expops"
```

## 3. Configure persistent temporary storage

Run the complete block after every new login, before creating a virtual
environment, installing packages, or invoking ExpOps. `TMPDIR` protects Python
and pip builds; `MLOPS_WORKSPACE_BASE_DIR` protects ExpOps process workspaces;
the Dask and joblib variables keep their spill files off `/tmp` too.

```bash
cd "$HOME/fyp-expops"

export TMPDIR="$HOME/fyp-expops/.tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export JOBLIB_TEMP_FOLDER="$TMPDIR/joblib"

export PIP_CACHE_DIR="$HOME/fyp-expops/.pip-cache"
export XDG_CACHE_HOME="$HOME/fyp-expops/.cache"
export DASK_TEMPORARY_DIRECTORY="$HOME/fyp-expops/.dask"

export MLOPS_WORKSPACE_DIR="$HOME/fyp-expops"
export MLOPS_WORKSPACE_BASE_DIR="$HOME/fyp-expops/.workspaces"
export MLOPS_WORKSPACE_CLEANUP="always"

mkdir -p \
  "$TMPDIR" \
  "$JOBLIB_TEMP_FOLDER" \
  "$PIP_CACHE_DIR" \
  "$XDG_CACHE_HOME" \
  "$DASK_TEMPORARY_DIRECTORY" \
  "$MLOPS_WORKSPACE_BASE_DIR"

chmod 700 \
  "$TMPDIR" \
  "$JOBLIB_TEMP_FOLDER" \
  "$PIP_CACHE_DIR" \
  "$XDG_CACHE_HOME" \
  "$DASK_TEMPORARY_DIRECTORY" \
  "$MLOPS_WORKSPACE_BASE_DIR"

quota -s
python3 -c 'import tempfile; print(tempfile.gettempdir())'
touch "$TMPDIR/.write-test"
rm "$TMPDIR/.write-test"
```

The Python command must print a path under `~/fyp-expops`, not `/tmp`.

## 4. Create and verify the Linux driver environment

Run this immediately after Step 3 in the same login so the temporary-storage
environment remains active.

```bash
cd "$HOME/fyp-expops"

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --no-cache-dir --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -e "./expops-platform[slurm]"

python -m pip check
python -c 'import expops, dask_jobqueue; from expops.cluster import ComputeSession; print(expops.__file__)'
command -v expops
```

Do not continue until the checks above succeed.

## 5. Submit the pipeline

After a new login, reactivate the environment and repeat the exports before
running ExpOps:

```bash
cd "$HOME/fyp-expops"

export TMPDIR="$HOME/fyp-expops/.tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export JOBLIB_TEMP_FOLDER="$TMPDIR/joblib"
export PIP_CACHE_DIR="$HOME/fyp-expops/.pip-cache"
export XDG_CACHE_HOME="$HOME/fyp-expops/.cache"
export DASK_TEMPORARY_DIRECTORY="$HOME/fyp-expops/.dask"
export MLOPS_WORKSPACE_DIR="$HOME/fyp-expops"
export MLOPS_WORKSPACE_BASE_DIR="$HOME/fyp-expops/.workspaces"
export MLOPS_WORKSPACE_CLEANUP="always"

mkdir -p \
  "$TMPDIR" \
  "$JOBLIB_TEMP_FOLDER" \
  "$PIP_CACHE_DIR" \
  "$XDG_CACHE_HOME" \
  "$DASK_TEMPORARY_DIRECTORY" \
  "$MLOPS_WORKSPACE_BASE_DIR"

source .venv/bin/activate

ls -lh "$HOME/fyp-expops/credit-card-fraud/data/creditcard.csv"
python -c 'import tempfile; print(tempfile.gettempdir())'

expops run credit-card-fraud
run_status=$?
```
