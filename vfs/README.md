# Fraud baseline with VFS

This separate seed-42 control preserves the original nested experiment in the
repository's root configs and source. It uses the same stratified 80/20 split,
training-only StandardScaler, balanced logistic regression and held-out metrics.
It is not a parallelism benchmark.

Install the current ExpOps checkout through the usual Python workflow.
The complete code is on platform branch `feature/mount-based-vfs` and fraud branch
`feature/vfs-baseline`; an older published ExpOps package does not contain this
integration. See the next section for a fresh-device setup.
From the repository root on Windows:

```powershell
.\scripts\run_vfs_baseline.ps1
# Optional cloud storage and metadata:
.\scripts\run_vfs_baseline.ps1 -Deployment cloud
```

Or, from this `vfs` directory:

```powershell
expops run --project project --compute compute.local.yaml
expops run --project project --compute compute.cloud.yaml
```

These are ordinary ExpOps runs. No custom wheel, operator SHA-256, source snapshot
manifest, transport mount or separate mounted runtime is required. The original
environment manager installs the declared requirements. The launcher restores
its caller's working directory and temporary environment settings.

`project/configs/project_config.yaml` uses the original `experiment.pipeline`
shape and selects `vfs://input/creditcard.csv`. Processes keep reading
`context.data_paths["training"]` and use Python `log_metric` as before.
The local profile reads `../data/creditcard.csv` relative to this directory.
Durable local state lives in `.storage`; runtime/materialized files use `.run`
when launched through the helper. The normal runner's project ID is its folder
name (`project`); the display name remains `credit-card-fraud-vfs-baseline`.

The cloud profile retains the existing GCS input prefix and uses separate
cache/artefact prefixes. S3 artefacts use AWS profile `expops`.
Supply `CREDIT_CARD_FRAUD_SQL_PASSWORD` and `MLOPS_SQL_USERNAME` in your
environment; never put password values in YAML. A Redis alternative remains
commented and requires `CREDIT_CARD_FRAUD_REDIS_PASSWORD`. Install the needed
cloud provider dependencies and configure AWS/GCP credentials before running.
Cloud runs may write their configured managed output prefixes.

Standalone IO is available through `expops.storage.VFS.from_config(...)`.
Remote project trees can be retrieved with `--project vfs://source/<folder>`,
then executed by the original runner. Only run source and requirements you trust.

Offline tests preserve statistical parity and verify configs, Python metric
logging, PNG output and launcher restoration. Real Windows/local-worker tests
exercise normal CLI cold/cache/changed-input/failure cycles on synthetic data.
These redesign tests do not access live clouds, the full dataset or SLURM.
macOS and mounted SLURM validation remain deferred.

## Set up another Windows device

Use Python 3.14 to match the tested baseline's numerical dependency pins. Clone
both repositories into the same parent folder, then create and activate a native
Python virtual environment there (do not copy an environment from another PC):

```powershell
git clone --branch feature/mount-based-vfs https://github.com/local-minima-lab/expops-platform.git
git clone --branch feature/vfs-baseline https://github.com/Professional-Procrastinat0r/credit-card-fraud.git
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ./expops-platform
```

If these folders already exist, fetch and switch each repository to its branch,
then `git pull --ff-only` instead of cloning. Preserve any unrelated local edits.
The original environment manager installs the baseline's declared requirements.

For the local deployment, separately place the real CSV at
`credit-card-fraud/data/creditcard.csv`; it is intentionally not stored in Git.
From the parent folder:

```powershell
cd credit-card-fraud
.\scripts\run_vfs_baseline.ps1
```

For cloud deployment, install the provider extras in the activated environment:

```powershell
# From the parent folder containing both repositories:
python -m pip install -e './expops-platform[aws,gcp,postgres]'
```

Configure GCP credentials, the AWS `expops` profile, and the SQL environment
settings described above on the new device before invoking the cloud launcher.
Git transfers code/configuration, not passwords, cloud credentials or datasets.
