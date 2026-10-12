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

# This test uses allocation-owned Redis, not an externally hosted database.
# Persist metadata for the next allocation, and prohibit concurrent writers.
mkdir -p "$PWD/redis-state" "$PWD/results"
chmod 700 "$PWD/redis-state"
exec 9>"$PWD/redis-state/run.lock"
if ! flock -n 9; then
    printf 'Another driver owns this Redis state directory; wait for it to finish.\n' >&2
    exit 1
fi
: "${EXPOPS_REDIS_SERVER:?Export the redis-server executable path}"
test -x "$EXPOPS_REDIS_SERVER"
export MLOPS_REDIS_HOST="$("$EXPOPS_PYTHON" -c 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("192.168.51.149",22)); print(s.getsockname()[0]); s.close()')"
export MLOPS_REDIS_PORT="$("$EXPOPS_PYTHON" -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1]); s.close()')"
export MLOPS_REDIS_DB=0
export CREDIT_CARD_FRAUD_REDIS_PASSWORD="$("$EXPOPS_PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"
export LD_LIBRARY_PATH="${EXPOPS_REDIS_LIBRARY_DIR:+$EXPOPS_REDIS_LIBRARY_DIR:}${LD_LIBRARY_PATH:-}"

cleanup() {
    if test -n "${REDIS_PID:-}"; then
        # SHUTDOWN SAVE preserves the cache indices/run history before exit.
        "$EXPOPS_PYTHON" - <<'PY' || true
import os, redis
client = redis.Redis(host=os.environ['MLOPS_REDIS_HOST'], port=int(os.environ['MLOPS_REDIS_PORT']),
                     password=os.environ['CREDIT_CARD_FRAUD_REDIS_PASSWORD'],
                     socket_connect_timeout=5, socket_timeout=30)
try:
    client.shutdown(save=True)
finally:
    client.close()
PY
        kill "$REDIS_PID" 2>/dev/null || true
        wait "$REDIS_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT
STATE_DIR="$("$EXPOPS_PYTHON" -c 'import json,pathlib; print(json.dumps(str(pathlib.Path("redis-state").resolve())))')"
printf 'bind %s\nport %s\nprotected-mode yes\nrequirepass %s\ndir %s\ndbfilename metadata.rdb\nsave 60 1\nappendonly no\n' \
    "$MLOPS_REDIS_HOST" "$MLOPS_REDIS_PORT" "$CREDIT_CARD_FRAUD_REDIS_PASSWORD" "$STATE_DIR" \
    | "$EXPOPS_REDIS_SERVER" - > "results/redis-${SLURM_JOB_ID}.log" 2>&1 &
REDIS_PID=$!
"$EXPOPS_PYTHON" - <<'PY'
import os,time,redis
client=redis.Redis(host=os.environ['MLOPS_REDIS_HOST'],port=int(os.environ['MLOPS_REDIS_PORT']),
                   password=os.environ['CREDIT_CARD_FRAUD_REDIS_PASSWORD'],socket_connect_timeout=1,socket_timeout=1)
try:
    for attempt in range(60):
        try:
            if client.ping():
                print('Allocation-owned Redis ready; prior metadata loaded if present',flush=True)
                break
        except redis.RedisError:
            time.sleep(0.5)
    else:
        raise SystemExit('Redis did not become ready; see results/redis job log')
finally:
    client.close()
PY
# The controller exports raw YAML endpoint fields during interpreter handoff.
# Record the effective endpoint as data; credentials remain environment refs.
export COMPUTE_CONFIG="$PWD/compute.resolved-${SLURM_JOB_ID}.yaml"
"$EXPOPS_PYTHON" - <<'PY'
import os,pathlib,yaml
source=pathlib.Path('compute.git.slurm.yaml')
config=yaml.safe_load(source.read_text())
config['storage']['metadata'].update(host=os.environ['MLOPS_REDIS_HOST'],port=int(os.environ['MLOPS_REDIS_PORT']))
pathlib.Path(os.environ['COMPUTE_CONFIG']).write_text(yaml.safe_dump(config,sort_keys=False))
PY
"$EXPOPS_PYTHON" deployment.py preflight --compute "$COMPUTE_CONFIG"
"$EXPOPS_PYTHON" -m expops.main run --project local --compute "$COMPUTE_CONFIG"
"$EXPOPS_PYTHON" deployment.py inspect --compute "$COMPUTE_CONFIG" --run-id latest \
    --save-summary "results/run-${SLURM_JOB_ID}.json" --download-report "results/report-${SLURM_JOB_ID}"
printf 'ExpOps exit status: 0\n'
