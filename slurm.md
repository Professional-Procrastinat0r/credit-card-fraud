# Slurm deployment

This deployment bundles the code and credit-card dataset into one self-contained
archive. The cluster's `/tmp` filesystem has a small per-user quota, so both pip
temporary files and ExpOps process workspaces are redirected to persistent
storage under `~/fyp-expops`.

## 1. Build the code archive locally (PowerShell)

Run this from the Windows checkout. The archive contains
`credit-card-fraud/`, including `data/creditcard.csv`, and `expops-platform/`,
but excludes environments, runtime files, and frontend dependencies.

```powershell
Set-Location "D:\NUS\FYP"

$archive = "credit-card-fraud-slurm-deploy-$(Get-Date -Format yyyyMMdd).tar.gz"

tar.exe -czf $archive `
  --exclude="expops-platform/.git" `
  --exclude="expops-platform/.venv" `
  --exclude="expops-platform/.pytest_cache" `
  --exclude="expops-platform/ts-sdk/node_modules" `
  --exclude="credit-card-fraud/.credit-card-fraud" `
  --exclude="credit-card-fraud/.venv" `
  --exclude="__pycache__" `
  --exclude="*.pyc" `
  credit-card-fraud `
  expops-platform

Get-Item $archive | Select-Object Name, Length
```

Check that large or generated paths were not bundled accidentally:

```powershell
$unexpected = tar.exe -tzf $archive |
  Select-String -Pattern '(^|/)(node_modules|\.venv|\.credit-card-fraud)(/|$)'

if ($unexpected) {
  $unexpected
  throw "Archive contains excluded deployment files."
}

$dataset = tar.exe -tzf $archive |
  Select-String -SimpleMatch 'credit-card-fraud/data/creditcard.csv'

if (-not $dataset) {
  throw "Archive does not contain credit-card-fraud/data/creditcard.csv."
}
```

Upload the code archive under a stable remote filename:

```powershell
scp -o ProxyJump=e1115319@stujump.comp.nus.edu.sg `
  $archive `
  e1115319@xlogin.comp.nus.edu.sg:~/credit-card-fraud-slurm-deploy.tar.gz
```

## 2. Extract the bundle on the Slurm cluster (Bash)

```bash
mkdir -p "$HOME/fyp-expops"

tar -xzf "$HOME/credit-card-fraud-slurm-deploy.tar.gz" \
  -C "$HOME/fyp-expops"

ls -la "$HOME/fyp-expops"
ls -lh "$HOME/fyp-expops/credit-card-fraud/data/creditcard.csv"
```

The second `ls` must succeed before running the pipeline. It confirms that the
dataset was bundled and extracted to the path expected by the project.

## 3. Configure persistent temporary storage

Run these commands after every new login, before installing packages or invoking
ExpOps. `TMPDIR` protects pip builds; `MLOPS_WORKSPACE_BASE_DIR` protects the
per-process workspaces created by ExpOps.

```bash
cd "$HOME/fyp-expops"

mkdir -p \
  "$HOME/fyp-expops/.tmp" \
  "$HOME/fyp-expops/.workspaces"

chmod 700 \
  "$HOME/fyp-expops/.tmp" \
  "$HOME/fyp-expops/.workspaces"

export TMPDIR="$HOME/fyp-expops/.tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"

export MLOPS_WORKSPACE_DIR="$HOME/fyp-expops"
export MLOPS_WORKSPACE_BASE_DIR="$HOME/fyp-expops/.workspaces"
export MLOPS_WORKSPACE_CLEANUP="always"

quota -s
python3 -c 'import tempfile; print(tempfile.gettempdir())'
```

The Python command must print a path under `~/fyp-expops`, not `/tmp`.

## 4. Create and verify the Linux driver environment

```bash
cd "$HOME/fyp-expops"

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --no-cache-dir --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -e "./expops-platform[gcp,slurm]"

python -m pip check
python -c 'import expops, dask_jobqueue; print(expops.__file__)'
command -v expops
```

Do not continue until the checks above succeed.

## 5. Submit the pipeline

After a new login, reactivate the environment and repeat the exports before
running ExpOps:

```bash
cd "$HOME/fyp-expops"
source .venv/bin/activate

export TMPDIR="$HOME/fyp-expops/.tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"

export MLOPS_WORKSPACE_DIR="$HOME/fyp-expops"
export MLOPS_WORKSPACE_BASE_DIR="$HOME/fyp-expops/.workspaces"
export MLOPS_WORKSPACE_CLEANUP="always"

ls -lh "$HOME/fyp-expops/credit-card-fraud/data/creditcard.csv"
python -c 'import tempfile; print(tempfile.gettempdir())'

expops run credit-card-fraud
```

If an install or run reports `Disk quota exceeded`, check both the selected
temporary directory and the filesystem quota before deleting project data:

```bash
quota -s
df -h "$TMPDIR" "$HOME"
df -i "$TMPDIR" "$HOME"
du -sh "$TMPDIR" "$HOME/fyp-expops/.workspaces" 2>/dev/null
```
