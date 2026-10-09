# Slurm deployment

These instructions use the original nested experiment in `configs/`, now with
VFS mounts. Platform support is implemented; the real cluster run remains to be
validated. The full-data local/cloud-storage cold and cached runs have passed.

This deployment bundles the project and platform code. The training dataset is
materialized from GCS by ExpOps on each execution worker. The cluster's `/tmp`
filesystem has a small per-user quota, so pip temporary files, ExpOps process
workspaces, and materialized data are redirected to persistent storage under
`~/fyp-expops`.

The active `configs/compute_config.yaml` uses PostgreSQL metadata, GCS for cache,
artifacts, and the training dataset, with commented S3 mount alternatives.
The same project can use Redis metadata by activating the commented block. The login node and every allocated worker
therefore need outbound access to the selected metadata and object stores.
`~/fyp-expops` must still be a shared filesystem so workers see the extracted
source, environments, and configured temporary roots.

Credential values are not stored in YAML or bundled in the archive. The SQL
plugin reads the active PostgreSQL password from the deployment-selected
`CREDIT_CARD_FRAUD_SQL_PASSWORD` environment reference. The GCS plugin uses
Google Application Default Credentials, while an optional S3 mount
delegates AWS authentication to Boto3's standard credential chain. The
commented Redis alternative selects a separate environment reference.

Before building the archive, use an `expops-platform` checkout containing mounted
worker delivery, data materialization, resolved storage plans, plugin-owned
authentication, and the SQL, GCS, and S3 storage implementations. The required-file
checks below reject an older platform checkout before it can be uploaded.

## 1. Build the code archive locally (PowerShell)

Run this from the Windows checkout. The archive contains `credit-card-fraud/`
and `expops-platform/`, but excludes the remotely hosted dataset, environments,
runtime files, and frontend dependencies.

```powershell
Set-Location "D:\NUS\FYP"

$archive = "credit-card-fraud-slurm-deploy-$(Get-Date -Format yyyyMMdd-HHmmss).tar.gz"

tar.exe -czf $archive '--exclude=.git' '--exclude=.venv' '--exclude=.pytest_cache' '--exclude=graphify-out' '--exclude=.pytest-task-workspaces' '--exclude=.test-workspace' '--exclude=.venvs' '--exclude=.expops-sources' '--exclude=node_modules' '--exclude=.credit-card-fraud' '--exclude=__pycache__' '--exclude=*.pyc' '--exclude=creditcard.csv' credit-card-fraud expops-platform

if ($LASTEXITCODE -ne 0) {
    throw "tar.exe failed; do not upload the partial archive"
}

$entries = @(tar.exe -tzf $archive)
if ($LASTEXITCODE -ne 0) {
    throw "The archive could not be read back"
}

$required = @(
    'credit-card-fraud/configs/project_config.yaml'
    'credit-card-fraud/configs/compute_config.yaml'
    'credit-card-fraud/scripts/inspect_storage_auth.py'
    'expops-platform/pyproject.toml'
    'credit-card-fraud/src/model.py'
    'credit-card-fraud/src/plot_metrics.py'
    'expops-platform/src/expops/worker_delivery.py'
    'expops-platform/src/expops/worker_runtime.py'
    'expops-platform/src/expops/storage/filesystem.py'
    'expops-platform/src/expops/storage/sql_config.py'
    'expops-platform/src/expops/storage/adapters/gcs_object_store.py'
    'expops-platform/src/expops/storage/adapters/s3_object_store.py'
)
$missing = @($required | Where-Object { $_ -notin $entries })
if ($missing.Count -ne 0) {
    throw "Archive is missing required files: $($missing -join ', ')"
}

$unexpected = @($entries | Where-Object {
    $_ -match '(^|/)(\.git|\.venv|\.pytest_cache|graphify-out|\.pytest-task-workspaces|\.test-workspace|\.venvs|\.expops-sources|node_modules|\.credit-card-fraud|__pycache__)(/|$)|(^|/)creditcard\.csv$|\.pyc$'
})
if ($unexpected.Count -ne 0) {
    throw "Archive contains excluded files: $($unexpected[0..([Math]::Min(9, $unexpected.Count - 1))] -join ', ')"
}

Get-Item -LiteralPath $archive | Select-Object FullName, Length, LastWriteTime
```

Upload the code archive under a stable remote filename:

```powershell
scp -o 'ProxyJump=e1115319@stujump.comp.nus.edu.sg' $archive 'e1115319@xlogin.comp.nus.edu.sg:~/credit-card-fraud-slurm-deploy.tar.gz'

if ($LASTEXITCODE -ne 0) {
    throw "scp failed; the remote bundle was not accepted"
}
```

## 2. Extract the bundle on the Slurm cluster (Bash)

```bash
mkdir -p "$HOME/fyp-expops"

tar -xzf "$HOME/credit-card-fraud-slurm-deploy.tar.gz" \
  -C "$HOME/fyp-expops"

ls -la "$HOME/fyp-expops"

test -f "$HOME/fyp-expops/credit-card-fraud/configs/project_config.yaml"
test -f "$HOME/fyp-expops/credit-card-fraud/configs/compute_config.yaml"
test -f "$HOME/fyp-expops/credit-card-fraud/scripts/inspect_storage_auth.py"
test -f "$HOME/fyp-expops/credit-card-fraud/src/model.py"
test -f "$HOME/fyp-expops/credit-card-fraud/src/plot_metrics.py"
test -f "$HOME/fyp-expops/expops-platform/src/expops/worker_delivery.py"
test -f "$HOME/fyp-expops/expops-platform/src/expops/worker_runtime.py"
test -f "$HOME/fyp-expops/expops-platform/src/expops/storage/filesystem.py"
test -f "$HOME/fyp-expops/expops-platform/pyproject.toml"
test -f "$HOME/fyp-expops/expops-platform/src/expops/storage/sql_config.py"
test -f "$HOME/fyp-expops/expops-platform/src/expops/storage/adapters/gcs_object_store.py"
test -f "$HOME/fyp-expops/expops-platform/src/expops/storage/adapters/s3_object_store.py"
```

Do not continue if extraction or any required-file check returns a nonzero exit
status. The archive contains the current worktrees, including uncommitted source
changes; that is useful for this smoke test but is not a reproducible release.

## 3. Configure persistent temporary storage

Run the complete block after every new login, before creating a virtual
environment, installing packages, or invoking ExpOps. `TMPDIR` protects Python
and pip builds; `MLOPS_WORKSPACE_BASE_DIR` protects ExpOps process workspaces;
`MLOPS_DATA_MATERIALIZATION_DIR` holds worker-local object inputs; the Dask and
joblib variables keep their spill files off `/tmp` too.

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
export MLOPS_DATA_MATERIALIZATION_DIR="$HOME/fyp-expops/.materialized-data"
export MLOPS_WORKSPACE_CLEANUP="always"
export MLOPS_DASK_WAIT_FOR_WORKERS_SEC="120"

mkdir -p \
  "$TMPDIR" \
  "$JOBLIB_TEMP_FOLDER" \
  "$PIP_CACHE_DIR" \
  "$XDG_CACHE_HOME" \
  "$DASK_TEMPORARY_DIRECTORY" \
  "$MLOPS_WORKSPACE_BASE_DIR" \
  "$MLOPS_DATA_MATERIALIZATION_DIR"

chmod 700 \
  "$TMPDIR" \
  "$JOBLIB_TEMP_FOLDER" \
  "$PIP_CACHE_DIR" \
  "$XDG_CACHE_HOME" \
  "$DASK_TEMPORARY_DIRECTORY" \
  "$MLOPS_WORKSPACE_BASE_DIR" \
  "$MLOPS_DATA_MATERIALIZATION_DIR"

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
python -m pip install --no-cache-dir -e "./expops-platform[slurm,aws,gcp,postgres]"

python -m pip check
python -c 'import boto3, dask_jobqueue, expops, psycopg; from google.cloud import storage; from expops.cluster import ComputeSession; print(expops.__file__)'
command -v expops
```

Those commands install the active PostgreSQL/GCS backends and the optional S3
alternative. The commented Redis alternative can be installed and verified with:

```bash
# python -m pip install --no-cache-dir -e "./expops-platform[slurm,aws,gcp,redis]"
# python -c 'import boto3, dask_jobqueue, expops, redis; from google.cloud import storage; from expops.cluster import ComputeSession; print(expops.__file__)'
```

Optional extras can be combined to match any selected metadata/object-store
pair.

Do not continue until `pip check` and the relevant imports succeed. ExpOps also
installs the selected storage dependencies into the model and reporting
environments it constructs, so they do not need to be added to the experiment's
requirements files solely for backend reconstruction.

## 5. Configure and verify remote storage credentials

Run the PostgreSQL password prompt after each new login. Its name matches the
explicit `password_ref` in `compute_config.yaml`. Input is hidden and the value
is not written into shell history:

```bash
read -rsp "CREDIT_CARD_FRAUD_SQL_PASSWORD: " CREDIT_CARD_FRAUD_SQL_PASSWORD
printf '\n'
export CREDIT_CARD_FRAUD_SQL_PASSWORD

test -n "${CREDIT_CARD_FRAUD_SQL_PASSWORD:-}"

python -c 'import os, psycopg; c=psycopg.connect(host="aws-0-ap-southeast-1.pooler.supabase.com", port=6543, dbname="postgres", user="postgres.dzzzeqtjpdfknbggnotp", password=os.environ["CREDIT_CARD_FRAUD_SQL_PASSWORD"], sslmode="require", connect_timeout=5); c.execute("SELECT 1").fetchone(); print("PostgreSQL preflight: OK"); c.close()'
```

For the commented Redis alternative, use its independently selected environment
reference:

```bash
# read -rsp "CREDIT_CARD_FRAUD_REDIS_PASSWORD: " CREDIT_CARD_FRAUD_REDIS_PASSWORD
# printf '\n'
# export CREDIT_CARD_FRAUD_REDIS_PASSWORD
# test -n "${CREDIT_CARD_FRAUD_REDIS_PASSWORD:-}"
# python -c 'import os, redis; c=redis.Redis(host="afterthought-cakes-button-30026.db.redis.io", port=17421, db=0, password=os.environ["CREDIT_CARD_FRAUD_REDIS_PASSWORD"], socket_connect_timeout=5); print("Redis preflight:", c.ping()); c.close()'
```

### Google Cloud Storage (active)

For the active GCS backend, use Application Default Credentials that
are readable at the same path on the login node and workers. If you must use a
credential JSON file, keep it outside the project and upload it separately from
the code archive. Run this locally in PowerShell. This uses one cluster
connection instead of separate setup, upload, and verification connections:

```powershell
$gcpCredentials = 'C:\Users\User\AppData\Roaming\gcloud\application_default_credentials.json'
$sshTarget = 'e1115319@xlogin.comp.nus.edu.sg'
$proxyJump = 'e1115319@stujump.comp.nus.edu.sg'

scp -o "ProxyJump=$proxyJump" $gcpCredentials "${sshTarget}:~/.expops-gcp-credentials-upload.json"
if ($LASTEXITCODE -ne 0) {
    throw "Google credentials upload failed"
}
```

Then run this in the cluster login session you already use for setup and the
pipeline. The move and permissions are needed only after uploading a new file;
the two exports are needed after every new login:

```bash
mkdir -p "$HOME/.config/expops"
mv "$HOME/.expops-gcp-credentials-upload.json" \
  "$HOME/.config/expops/gcp-service-account.json"
chmod 700 "$HOME/.config/expops"
chmod 600 "$HOME/.config/expops/gcp-service-account.json"

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/expops/gcp-service-account.json"
export GOOGLE_CLOUD_PROJECT="exp-ops-506607"

python -c 'from google.cloud import storage; c=storage.Client(); b=c.bucket("expops-example-credit-card-fraud"); o=b.blob("credit-card-fraud/dataset/creditcard.csv"); print("GCS training object visible:", o.exists()); c.close()'
```

The service account should have only the permissions needed for the configured
bucket. A service-account key is a long-lived secret; use workload identity or
short-lived credentials instead if the cluster supports them, and delete or
rotate a temporary test key when it is no longer needed.

### Amazon S3 (optional mount alternative)

Skip this section for the active all-GCS SLURM profile. The commented S3 alternatives
select the `expops` profile. If that
profile is backed by your local AWS shared credentials file, upload only the
credentials file. The region is already configured in YAML, so a separate AWS
config file is unnecessary for this case. If the profile does not exist yet,
first run `aws configure --profile expops` locally, or change the profile name
in YAML. This PowerShell block makes only one cluster connection:

```powershell
$awsCredentials = Join-Path $HOME '.aws\credentials'
$sshTarget = 'e1115319@xlogin.comp.nus.edu.sg'
$proxyJump = 'e1115319@stujump.comp.nus.edu.sg'

scp -o "ProxyJump=$proxyJump" $awsCredentials "${sshTarget}:~/.expops-aws-credentials-upload"
if ($LASTEXITCODE -ne 0) {
    throw "AWS credentials upload failed"
}
```

This copies temporary session tokens too when they are present in the shared
credentials file, but those credentials will stop working when they expire. If
the profile uses AWS IAM Identity Center (SSO), configure the AWS CLI on the
cluster and run `aws sso login --profile expops` there instead of copying its
local SSO cache.

Then run this in the existing cluster login session. The move and permissions
are needed only after uploading a new file; the exports are needed after every
new login. Do not copy AWS keys into the repository or project config:

```bash
mkdir -p "$HOME/.config/expops"
mv "$HOME/.expops-aws-credentials-upload" \
  "$HOME/.config/expops/aws-credentials"
chmod 700 "$HOME/.config/expops"
chmod 600 "$HOME/.config/expops/aws-credentials"

export AWS_PROFILE="expops"
export AWS_DEFAULT_REGION="ap-southeast-1"
export AWS_SHARED_CREDENTIALS_FILE="$HOME/.config/expops/aws-credentials"

python -c 'import boto3; c=boto3.Session(profile_name="expops", region_name="ap-southeast-1").client("s3"); c.head_object(Bucket="expops-test-bucket-755933694771-ap-southeast-1-an", Key="credit-card-fraud/creditcard.csv"); print("S3 training object visible")'
```

Use the AWS credential block only after activating an S3 mount in
`compute_config.yaml`. The active input, cache and artefact mounts use GCS.
These checks must run on a host with the same network policy and shared home
filesystem used by the worker jobs.

## 6. Submit the pipeline

The project mounts its source as `local` with `access: staged`. ExpOps delivers
the mounted source and declared input to workers; model code keeps using
worker-local materialized paths. The reserved `cache` and `artefact` mounts
retain managed output storage. Their new GCS prefixes are
`credit-card-fraud/vfs/cache` and `credit-card-fraud/vfs/artefact`; a first
migrated run should be treated as cold.

Keep the driver and worker environment setup consistent. On this shared-home
cluster, the extracted project and its prepared environments are available at
the same paths. The platform uses these environment paths when they exist on
the worker; separate hosts can instead supply `options.worker_python` and
`options.worker_environments`. These are compute-runtime settings. Mounts
do not select the database or construct Python environments.

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
export MLOPS_DATA_MATERIALIZATION_DIR="$HOME/fyp-expops/.materialized-data"
export MLOPS_WORKSPACE_CLEANUP="always"
export MLOPS_DASK_WAIT_FOR_WORKERS_SEC="120"

mkdir -p \
  "$TMPDIR" \
  "$JOBLIB_TEMP_FOLDER" \
  "$PIP_CACHE_DIR" \
  "$XDG_CACHE_HOME" \
  "$DASK_TEMPORARY_DIRECTORY" \
  "$MLOPS_WORKSPACE_BASE_DIR" \
  "$MLOPS_DATA_MATERIALIZATION_DIR"

source .venv/bin/activate

read -rsp "CREDIT_CARD_FRAUD_SQL_PASSWORD: " CREDIT_CARD_FRAUD_SQL_PASSWORD
printf '\n'
export CREDIT_CARD_FRAUD_SQL_PASSWORD

# Redis metadata alternative:
# read -rsp "CREDIT_CARD_FRAUD_REDIS_PASSWORD: " CREDIT_CARD_FRAUD_REDIS_PASSWORD
# printf '\n'
# export CREDIT_CARD_FRAUD_REDIS_PASSWORD

# Only for an activated S3 alternative:
# export AWS_PROFILE="expops"
# export AWS_DEFAULT_REGION="ap-southeast-1"
# export AWS_SHARED_CREDENTIALS_FILE="$HOME/.config/expops/aws-credentials"

export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/expops/gcp-service-account.json"
export GOOGLE_CLOUD_PROJECT="exp-ops-506607"

python -c 'import tempfile; print(tempfile.gettempdir())'
python credit-card-fraud/scripts/inspect_storage_auth.py

expops run credit-card-fraud --compute credit-card-fraud/configs/compute_config.yaml
run_status=$?
unset CREDIT_CARD_FRAUD_SQL_PASSWORD

latest_log=$(ls -1t "$HOME/fyp-expops/credit-card-fraud/.credit-card-fraud/logs/"*.log 2>/dev/null | head -n 1)
printf 'ExpOps exit status: %s\n' "$run_status"
printf 'Latest log: %s\n' "$latest_log"

if [ -n "$latest_log" ]; then
  grep -nE ' - ERROR - |Traceback|Process .* failed|pipeline execution completed successfully' "$latest_log"
fi
```

Accept the run only when `run_status` is `0`, the run metadata says `completed`,
the latest log contains the final success message, and it contains no `ERROR`, traceback, or failed-process line.
For S3, lowercase Botocore handler names containing words such as
`redirect_from_error` are debug internals; the ` - ERROR - ` level marker above
is the meaningful failure check.
