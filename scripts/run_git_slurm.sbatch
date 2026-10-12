#!/bin/bash
#SBATCH --job-name=fraud-git-s3-gcs
#SBATCH --partition=normal
#SBATCH --account=allusers
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --nodelist=xcnc17
#SBATCH --output=driver-%j.log
#SBATCH --error=driver-%j.log
set -euo pipefail
umask 077
cd "$SLURM_SUBMIT_DIR"
source "$HOME/.config/expops/cloud.env"
: "${EXPOPS_PYTHON:?Export the shared interpreter containing ExpOps}"
export TMPDIR="$PWD/tmp" TMP="$PWD/tmp" TEMP="$PWD/tmp"
export MLOPS_WORKSPACE_BASE_DIR="$PWD/workspaces"
export XDG_CACHE_HOME="$PWD/cache" PIP_CACHE_DIR="$PWD/pip-cache"
export PIP_CONSTRAINT="$PWD/storage-constraints.txt"
export DASK_DISTRIBUTED__COMM__COMPRESSION=zlib
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
mkdir -p "$TMPDIR" "$MLOPS_WORKSPACE_BASE_DIR" "$XDG_CACHE_HOME" "$PIP_CACHE_DIR"

# SQLite WAL is node-local. Pin driver and worker jobs to the same host in
# both this script and the compute profile; shared home holds snapshots only.
mkdir -p "$PWD/sqlite-state" "$PWD/results"
exec 9>"$PWD/sqlite-state/run.lock"
if ! flock -n 9; then
    printf 'Another driver owns this SQLite snapshot; wait for it to finish.\n' >&2
    exit 1
fi
# On this cluster /dev/shm is private to each allocation. /var/tmp is local XFS
# shared by jobs on the same node, so independent Dask worker jobs see this DB.
SQLITE_RUNTIME_DIR=$(mktemp -d "/var/tmp/expops-fraud-${UID}-${SLURM_JOB_ID}-XXXXXX")
export SQLITE_DATABASE="$SQLITE_RUNTIME_DIR/metadata.sqlite"
"$EXPOPS_PYTHON" deployment.py sqlite-backup \
    --source "$PWD/sqlite-state/metadata.sqlite" --destination "$SQLITE_DATABASE" --allow-missing

cleanup() {
    status=$?
    trap - EXIT
    if ! "$EXPOPS_PYTHON" deployment.py sqlite-backup \
        --source "$SQLITE_DATABASE" --destination "$PWD/sqlite-state/metadata.sqlite"; then
        printf 'SQLite snapshot failed; live database retained at %s\n' "$SQLITE_DATABASE" >&2
        exit 1
    fi
    # Only remove the private directory created above, after a verified backup.
    "$EXPOPS_PYTHON" - <<'PY'
import os, pathlib, shutil
database = pathlib.Path(os.environ['SQLITE_DATABASE'])
assert database.parent.parent == pathlib.Path('/var/tmp')
assert database.parent.name.startswith('expops-fraud-')
shutil.rmtree(database.parent)
PY
    exit "$status"
}
trap cleanup EXIT

# Store the absolute database path in YAML so interpreter handoff and all
# serialized worker plans select the same database, with no environment magic.
export COMPUTE_CONFIG="$PWD/compute.resolved-${SLURM_JOB_ID}.yaml"
"$EXPOPS_PYTHON" - <<'PY'
import os, pathlib, socket, yaml
config = yaml.safe_load(pathlib.Path('compute.git.slurm.yaml').read_text())
config['storage']['metadata']['connection']['database'] = os.environ['SQLITE_DATABASE']
pathlib.Path(os.environ['COMPUTE_CONFIG']).write_text(yaml.safe_dump(config, sort_keys=False))
print('SQLite driver host:', socket.gethostname(), 'database:', os.environ['SQLITE_DATABASE'], flush=True)
PY
"$EXPOPS_PYTHON" deployment.py preflight --compute "$COMPUTE_CONFIG"
"$EXPOPS_PYTHON" -m expops.main run --project local --compute "$COMPUTE_CONFIG"
"$EXPOPS_PYTHON" deployment.py inspect --compute "$COMPUTE_CONFIG" --run-id latest \
    --save-summary "results/run-${SLURM_JOB_ID}.json" --download-report "results/report-${SLURM_JOB_ID}"
printf 'ExpOps exit status: 0\n'
