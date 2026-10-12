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
: "${CREDIT_CARD_FRAUD_SQL_PASSWORD:?Export the Supabase database password}"
export TMPDIR="$PWD/tmp" TMP="$PWD/tmp" TEMP="$PWD/tmp"
export MLOPS_WORKSPACE_BASE_DIR="$PWD/workspaces"
export XDG_CACHE_HOME="$PWD/cache" PIP_CACHE_DIR="$PWD/pip-cache"
export PIP_CONSTRAINT="$PWD/storage-constraints.txt"
export DASK_DISTRIBUTED__COMM__COMPRESSION=zlib
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
mkdir -p "$TMPDIR" "$MLOPS_WORKSPACE_BASE_DIR" "$XDG_CACHE_HOME" "$PIP_CACHE_DIR"
"$EXPOPS_PYTHON" deployment.py preflight --compute compute.git.slurm.yaml
"$EXPOPS_PYTHON" -m expops.main run --project local --compute compute.git.slurm.yaml
printf 'ExpOps exit status: 0\n'
