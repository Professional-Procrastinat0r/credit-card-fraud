# Credit Card Fraud Detection with ExpOps

This project trains class-weighted logistic-regression fraud detectors across
three split seeds and scores each held-out set in three partitions. The original
nested experiment now uses VFS mounts through the ordinary ExpOps runner. There
is one project configuration under `configs/`; the separate VFS baseline has
been retired.

## Experiment contract

- Target: `Class`, where `1` means fraud and `0` means genuine.
- Features: `Time`, `Amount`, and PCA components `V1` through `V28`.
- Split: stratified 80/20 holdout split, repeated with seeds `41`, `42`, and `43`.
- Preprocessing: `StandardScaler`, fitted only on the training partition.
- Model: `LogisticRegression(class_weight="balanced", max_iter=1000)`.
- Primary metric: held-out average precision.
- Secondary metrics: ROC-AUC, precision, recall, F1, confusion counts, and alert rate.
- Initial decision threshold: `0.5`.

The threshold is an initial operating point, not a tuned production threshold. Threshold selection must use a validation partition rather than the final test partition.

## Active seed + data-parallel pipeline

```text
validate_data
      |
      v
seed_parallel [41, 42, 43]
      |
      +-- S41: train -> prepare -> data_parallel -> P1/P2/P3 -> exact aggregate --+
      +-- S42: train -> prepare -> data_parallel -> P1/P2/P3 -> exact aggregate --+
      +-- S43: train -> prepare -> data_parallel -> P1/P2/P3 -> exact aggregate --+
                                                                                |
                                                                                v
                                                               aggregate_seed_data_metrics
                                                                                |
                                                                                v
                                                               plot_seed_data_parallel_metrics
```

- `validate_data` checks the dataset schema, types, missing values, finite values, labels, and class distribution.
- `seed_parallel` creates three outer branches and supplies seeds `41`, `42`, and `43`.
- Each `train_model` branch creates its seed-specific stratified split and fits one scaler-and-classifier pipeline on the complete training portion.
- Each `prepare_evaluation_data` reconstructs the matching held-out set and packages its features and labels as `evaluation_rows`.
- Each seed-specific `data_parallel` node divides those held-out rows into three partitions, producing nine scoring branches in total.
- `evaluate_partition` uses its seed's model to score one partition and returns local diagnostics plus row-level labels and fraud scores.
- `aggregate_partition_metrics` has `data_aggregation: true`, so ExpOps creates one exact data aggregator per seed. It concatenates that seed's three partitions and recomputes global metrics.
- `aggregate_seed_data_metrics` has `seed_aggregation: true`, so it collapses the remaining three seed branches and calculates cross-seed stability.
- `plot_seed_data_parallel_metrics` creates `fraud_seed_data_parallel_report.png`.

The parallel boundary is deliberately after training. Training independent logistic-regression models on row shards would change the statistical procedure and require an explicit model-aggregation or ensemble strategy. Parallel held-out scoring preserves the baseline model and can therefore be checked directly against the control result.

Average precision and ROC-AUC are not averaged across partitions. They are nonlinear ranking metrics, so the aggregator reconstructs the global label/score vectors and computes each metric once. Confusion-matrix metrics are also recomputed from the combined predictions.

The expanded pipeline contains 25 nodes: three training nodes, three held-out preparation nodes, three data splitters, nine partition evaluators, three exact data aggregators, one seed aggregator, and the shared validation, seed-split, and chart nodes.

## Configuration and mounted files

| File | Workers | Metadata | Input / cache / artefacts |
| --- | --- | --- | --- |
| `configs/project_config.yaml` | Same nested experiment in every deployment | — | Declares mounted scripts, requirements and training input |
| `configs/compute.local.yaml` | Two local Dask workers | Local SQLite | Local files under this project |
| `configs/compute.cloud.yaml` | Two local Dask workers | PostgreSQL | S3 input, GCS cache/artefacts |
| `configs/compute_config.yaml` | Two SLURM workers | PostgreSQL | GCS input/cache/artefacts, with commented S3 alternatives |
| `configs/compute.git.slurm.yaml` | Same SLURM deployment, project retrieved from pinned Git commit | PostgreSQL | Same GCS mounts; no fraud checkout required |

The default `compute_config.yaml` remains the SLURM deployment. Select the local
profile explicitly for a local run without cloud credentials. All profiles mount
this project as `local`, so scripts use `local/src/model.py` and
`local/src/plot_metrics.py`, and environment requirements use
`local/requirements.txt` and `local/requirements-charts.txt`.

The project declares:

```yaml
data:
  inputs:
    training:
      path: input/creditcard.csv
```

Deployment profiles supply the physical location of `input`. Local mount
`source` values resolve relative to the compute YAML file, rather than the
caller's working directory. In the local profile, `input` mounts `../data`;
in the SLURM profile it mounts:

```text
gs://expops-example-credit-card-fraud/credit-card-fraud/dataset/
```

The cloud profile instead selects
`s3://expops-test-bucket-755933694771-ap-southeast-1-an/credit-card-fraud/dataset/`.
GCS input remains a commented alternative in that profile.

No named dataset catalogue or legacy `object_stores` block is needed.
`vfs://input/creditcard.csv` is an equivalent optional spelling.

## Dataset and cache

Place the local dataset at `data/creditcard.csv`. Expected properties of the
full credit-card dataset are:

```text
Rows:             284,807
Columns:          31
Genuine records:  284,315
Fraud records:    492
Fraud prevalence: 0.1727%
```

The model still reads `context.data_paths["training"]` with `pandas.read_csv`.
ExpOps materializes the declared input on the execution worker and hashes its
contents for caching. Passing the logical role between processes lets each
worker resolve its own copy. Materialization is intentional here; the model
has not been rewritten to consume a declared streaming input.

The reserved `cache` and `artefact` mounts remain the unified storage interface
for process results and reports. Local metadata and output bytes live under
`.credit-card-fraud/storage/`; environments and logs remain under
`.credit-card-fraud/`. Remote cache and artefacts use new prefixes
`credit-card-fraud/vfs/cache` and `credit-card-fraud/vfs/artefact`, followed by
ExpOps' managed project/purpose keys. Existing cloud data and older outputs are
left in place. Treat the first migrated run as cold; do not expect old cache
records or the retired baseline's results to carry over.

Repeat the same deployment to check cache reuse. Changing input bytes or process
code should invalidate the affected results. The chart is published through the
`artefact` mount; use the run's chart reference to find its managed object,
rather than assuming a flat output filename in the bucket.

The raw dataset and `.credit-card-fraud/` runtime directory are excluded from Git.

## Run locally on Windows

Use the current sibling `expops-platform` checkout with VFS support installed in
its environment. From this project directory:

```powershell
cd D:\NUS\FYP\credit-card-fraud
& .\scripts\run_experiment.ps1 -Deployment local -ExpOpsExecutable "..\expops-platform\.venv\Scripts\expops.exe"
```

If `expops` is already on `PATH`, just run
`.\scripts\run_experiment.ps1`. The helper selects `configs/compute.local.yaml`,
sets writable workspace/materialization directories under `.credit-card-fraud`,
and restores the caller's working directory and environment when it exits.
ExpOps normally builds the two declared environments from their pinned
requirements. This can require package-index access on first use.

For this checkout's already prepared model and reporting environments, you can
skip environment construction and run the CLI from the model interpreter's
environment instead:

```powershell
$previousEnvReady = $env:MLOPS_ENV_READY
try {
    $env:MLOPS_ENV_READY = "1"
    & .\scripts\run_experiment.ps1 -Deployment local -ExpOpsExecutable ".\.credit-card-fraud\envs\fraud-model-env\Scripts\expops.exe"
} finally {
    $env:MLOPS_ENV_READY = $previousEnvReady
}
```

Use this shortcut only when both environments contain their required packages
and the current platform checkout. Launching from a bare platform interpreter
with `MLOPS_ENV_READY=1` can miss the model dependencies.

Without the helper, the equivalent CLI command from the parent workspace is:

```powershell
expops run credit-card-fraud --compute credit-card-fraud/configs/compute.local.yaml
```

Set writable `MLOPS_WORKSPACE_BASE_DIR` and
`MLOPS_DATA_MATERIALIZATION_DIR` yourself when using that direct command.

## Remote storage and SLURM

For local workers with remote storage, select `-Deployment cloud` in the helper.
PostgreSQL uses the `CREDIT_CARD_FRAUD_SQL_PASSWORD` environment reference;
GCS uses Application Default Credentials. The cloud profile selects the
S3 input store with the AWS `expops` profile and uses GCS for cache/artefacts;
the SLURM profile uses GCS for all three. Commented Redis metadata,
S3 input and alternative artefact providers remain available. Activate a complete
alternative block and install/configure its provider before using it. Credential
values belong in the environment or provider credential files, not YAML.

Inspect the public storage plan without opening clients or reading credentials:

```powershell
& "..\expops-platform\.venv\Scripts\python.exe" .\scripts\inspect_storage_auth.py
```

This prints the resolved GCS input URI, secret references and worker environment
names. It does not verify network access or write permissions.

See [slurm.md](slurm.md) for cluster setup, credentials and inline quota
commands. The full-data local/cloud-storage test on 9 October 2026 completed
all 25 processes, and its repeated run reused all 25 cached results. The three
seed branches, nine scoring branches and final PNG were verified. Mounted
SLURM/remote-worker support exists in the platform; the real fraud-project
cluster run still needs to be tested.

## Run the same project from Git

With the current ExpOps platform installed, copy only
[`configs/compute.git.slurm.yaml`](configs/compute.git.slurm.yaml) to the machine
running the driver. From a writable directory containing that file:

```bash
expops run --project local --compute compute.git.slurm.yaml --prepare-only
expops run --project local --compute compute.git.slurm.yaml
```

The first command retrieves the project without starting workers, building
environments or opening the metadata database. The second executes it and needs
the SLURM/storage setup in [slurm.md](slurm.md#git-mount-deploy-with-only-a-compute-file).
To test with local Dask workers first, add `--local` to the second command; this
keeps the same remote storage settings.

The Git profile mounts the repository root as `local`, so the project
configuration, scripts, requirements and nested parallel experiment are the
same as for a local checkout. `--project local` selects that mount; it is not a
local folder name. ExpOps retrieves `configs/project_config.yaml` from Git. No
separate project configuration or source archive is needed on the driver. The
profile pins source commit `242875f4b9f0f516174ac611cef1fd56582a87e3`; update
`storage.mounts.local.revision` deliberately when testing newer project code.

This fetches the fraud project only. Install a VFS-capable ExpOps platform
separately, keep Git on `PATH`, and configure the selected storage credentials.
The dataset remains in object storage. Source preparation has been tested;
execution on the real SLURM cluster remains to be validated.

## Historical results before VFS migration

The runs below are recorded controls from the original implementation. They are
not results of the newly consolidated configuration.

## Baseline result

Successful evaluation run:

```text
Run ID:                  project-credit-card-fraud-20260824052859-e26c7041
Test transactions:       56,962
Test frauds:              98
Average precision:        0.718971
ROC-AUC:                  0.972083
Precision at 0.5:         0.060976
Recall at 0.5:            0.918367
F1 at 0.5:                0.114358
False positives:          1,386
False negatives:          8
Alert rate:               2.5912%
```

The model catches 90 of 98 frauds at threshold `0.5`, but only about 6.1% of alerts are genuine fraud. This illustrates why threshold selection must incorporate operational costs.

The seed-42 branch should reproduce this control result because it uses the same split and model parameters. Seeds 41 and 43 show whether the conclusion is stable under nearby alternative holdout samples.

## Seed-parallel result

Successful seed-sensitivity run:

```text
Run ID: project-credit-card-fraud-20260824182212-eaf57918
```

| Seed | Average precision | ROC-AUC | Precision | Recall | F1 | Alert rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 41 | 0.699598 | 0.973703 | 0.060440 | 0.897959 | 0.113256 | 2.5561% |
| 42 | 0.718971 | 0.972083 | 0.060976 | 0.918367 | 0.114358 | 2.5912% |
| 43 | 0.730829 | 0.986894 | 0.061794 | 0.948980 | 0.116032 | 2.6421% |
| Mean | 0.716466 | 0.977560 | 0.061070 | 0.921769 | 0.114549 | 2.5965% |
| Population std. | 0.012872 | 0.006633 | 0.000557 | 0.020967 | 0.001141 | 0.0353 pp |

Average precision changes noticeably across the three holdout samples, while precision, F1, and alert rate remain comparatively stable. Recall ranges from about 89.8% to 94.9%. The broad operational conclusion is therefore stable—threshold `0.5` catches most frauds but produces many false alerts—although a single split understates uncertainty in recall and ranking quality.

The generated report is stored as `fraud_seed_report.png` under the run's ExpOps artifact directory.

## Data-parallel result

Successful three-partition evaluation run:

```text
Run ID: project-credit-card-fraud-20260824183907-91e23e52
```

| Partition | Test rows | Frauds | Local average precision | Local ROC-AUC | Alert rate |
| ---: | ---: | ---: | ---: | ---: | ---: |
| P1 | 18,988 | 25 | 0.782138 | 0.984244 | 2.4542% |
| P2 | 18,987 | 30 | 0.676164 | 0.935143 | 2.5860% |
| P3 | 18,987 | 43 | 0.725961 | 0.990722 | 2.7334% |

The exactly aggregated result is:

```text
Test transactions:       56,962
Test frauds:                  98
Average precision:      0.718971
ROC-AUC:                0.972083
Precision at 0.5:       0.060976
Recall at 0.5:          0.918367
F1 at 0.5:              0.114358
True negatives:           55,478
False positives:           1,386
False negatives:               8
True positives:               90
Alert rate:               2.5912%
```

These global values match the seed-42 baseline exactly. That is the main correctness check: splitting scoring work changed how the rows were processed, but not the resulting predictions or metrics. The different local average-precision values describe each shard only and should not be interpreted as three independent model runs.

The generated report is stored as `fraud_data_parallel_report.png` under the run's ExpOps artifact directory.

## Combined seed + data-parallel result

Successful nested run:

```text
Run ID: project-credit-card-fraud-20260824184934-b9a925fa
Expanded process nodes: 25
Seed branches:           3
Partitions per seed:     3
Scoring branches:        9
```

Each seed's three partitions contained 56,962 transactions and 98 frauds in total:

| Seed | P1 frauds | P2 frauds | P3 frauds | Total frauds |
| ---: | ---: | ---: | ---: | ---: |
| 41 | 34 | 21 | 43 | 98 |
| 42 | 25 | 30 | 43 | 98 |
| 43 | 37 | 29 | 32 | 98 |

After exact within-seed aggregation:

| Seed | Average precision | ROC-AUC | Precision | Recall | F1 | Alert rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 41 | 0.699598 | 0.973703 | 0.060440 | 0.897959 | 0.113256 | 2.5561% |
| 42 | 0.718971 | 0.972083 | 0.060976 | 0.918367 | 0.114358 | 2.5912% |
| 43 | 0.730829 | 0.986894 | 0.061794 | 0.948980 | 0.116032 | 2.6421% |
| Mean | 0.716466 | 0.977560 | 0.061070 | 0.921769 | 0.114549 | 2.5965% |

Every per-seed metric matches the earlier seed-only experiment. This verifies both aggregation boundaries: data aggregation reconstructs the original held-out result for each seed, and seed aggregation reproduces the earlier cross-seed summary. Local partition metrics vary because each shard contains a different subset of transactions; they are diagnostics, not independent experiments.

The generated report is stored as `fraud_seed_data_parallel_report.png` under the run's ExpOps artifact directory.

## Historical platform findings

The original Windows runs required a writable workspace instead of the default
`/tmp` location. Their cache manifests also encountered Windows filename rules,
and spilled DataFrames could lose column labels. Those observations belong to
the historical runs above; recheck cache reuse in the current platform before
using timing results. The model retains its validated array-to-frame fallback.

Seed aggregation receives ordinal branch keys, so evaluation outputs carry the
actual `random_seed` and aggregation treats that value as authoritative.

## Historical reproducibility snapshot

The successful baseline used:

```text
Python:          3.14.3
NumPy:           2.5.2
pandas:          3.0.5
scikit-learn:    1.9.0
joblib:          1.5.3
Matplotlib:      3.11.1
```

The direct dependencies are pinned in `requirements.txt` and `requirements-charts.txt`. Transitive dependencies are not yet represented by a lockfile.

ExpOps is installed from the editable local checkout at `../expops-platform`. Its observed base commit at this checkpoint was:

```text
a3e6107d8182b928a116098931af66e3df110208
```

The checkout was not clean at the checkpoint, so the commit hash alone is not a complete byte-for-byte platform snapshot. Commit or otherwise record the local ExpOps changes before presenting the experiment as exactly reproducible.

## Next checks

Validate the migrated experiment locally, including a repeated cached run, then
validate SLURM execution. Once those agree with the statistical controls, vary
worker and partition counts to measure scheduling overhead and memory use.
