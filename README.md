# Credit Card Fraud Detection with ExpOps

For the new local-worker VFS workflow, see [the separate mounted baseline](vfs/README.md).
It uses seed 42 and the same scaler/classifier/holdout procedure in one environment.
The active nested seed/data-parallel experiment below is unchanged and still uses
the existing runner; its dataset declarations have not been migrated to VFS paths.

This project uses ExpOps to train class-weighted logistic-regression fraud detectors across several split seeds and evaluate each model's held-out predictions with data parallelism. Earlier baseline, seed-only, and data-only results remain documented below as controls.

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

The configurations are:

- `configs/project_config.yaml`: active nested seed + data experiment. It maps
  the logical `training` input to a named dataset without owning its location.
- `configs/compute_config.yaml`: deployment settings: SQL metadata, named GCS
  and S3 object stores, GCS cache/artifacts, and the GCS-backed named training
  dataset.

The active SQL + GCS configuration requires an `expops-platform`
checkout containing named dataset materialization, `ResolvedDataPlan`,
`ResolvedStoragePlan`, and plugin-owned authentication.

## Storage authentication example

The active configuration demonstrates two authentication strategies owned by
the selected storage plugins:

- PostgreSQL uses an explicit `EnvironmentSecretRef` named
  `CREDIT_CARD_FRAUD_SQL_PASSWORD`. The variable name is part of the safe
  storage specification; its value is not.
- GCS delegates authentication to Google Application Default Credentials, so
  ExpOps does not define or serialize a provider-specific key structure. The
  additional S3 store demonstrates a second plugin-owned strategy: Boto3's
  standard provider chain using the non-secret `expops` profile.

Inspect what ExpOps may serialize and send to workers without connecting to
either backend:

```powershell
cd D:\NUS\FYP\credit-card-fraud
$env:PYTHONPATH = "D:\NUS\FYP\expops-platform\src"
& "..\expops-platform\.venv\Scripts\python.exe" scripts\inspect_storage_auth.py
```

The credential portion of the printed metadata spec contains only this
reference:

```json
{
  "password_ref": {
    "name": "CREDIT_CARD_FRAUD_SQL_PASSWORD",
    "required": true,
    "source": "environment"
  }
}
```

The actual value is resolved only when the SQL plugin constructs its client in
the driver or worker process. The script deliberately supplies an empty
environment and does not open a storage client, so it works without credentials
or network access.

To use a mounted secret instead, the SQL plugin can be configured with a file
reference such as the following. The deployment—not ExpOps task payloads—must
mount the same path wherever the client is constructed:

```yaml
password_ref:
  source: file
  path: /run/secrets/expops/sql-password
  required: true
```

## Dataset

The active configuration reads the training dataset from:

```text
gs://expops-example-credit-card-fraud/credit-card-fraud/dataset/creditcard.csv
```

The deployment catalogue gives the physical dataset a stable name:

```yaml
storage:
  object_stores:
    dataset_2:
      type: gcs
      bucket: expops-example-credit-card-fraud
      gcp_project: exp-ops-506607

datasets:
  credit_card_transactions:
    type: object
    store: dataset_2
    # Relative to the resolved project prefix shown below.
    key: dataset/creditcard.csv
```

The project configuration maps the role expected by model code to that name:

```yaml
data:
  inputs:
    training:
      dataset: credit_card_transactions
```

For this project, the resolved GCS storage spec contributes the
`credit-card-fraud` prefix and the dataset contributes
`dataset/creditcard.csv`. Together they address the bucket key
`credit-card-fraud/dataset/creditcard.csv`; the project prefix must not be
repeated in the data source.

ExpOps downloads the object into a run-scoped path on each execution worker.
The model reads that local path from `context.data_paths["training"]` and uses
`pandas.read_csv`; it does not contain GCS or provider-SDK code. Process results pass
the logical source name rather than a temporary absolute path, so subsequent
tasks can resolve their own worker-local copy. ExpOps hashes the materialized
bytes for cache correctness; there is no checksum field in either YAML file.

To switch to a local file, change only the named dataset definition in
`compute_config.yaml` to `type: local` with `path: data/creditcard.csv`; every
project configuration continues to reference `credit_card_transactions`.

Expected dataset properties:

```text
Rows:             284,807
Columns:          31
Genuine records:  284,315
Fraud records:    492
Fraud prevalence: 0.1727%
```

The raw dataset and `.credit-card-fraud/` runtime directory are intentionally excluded from Git.

## Run locally

From the workspace containing both `credit-card-fraud/` and `expops-platform/`:

```powershell
cd D:\NUS\FYP
$env:MLOPS_WORKSPACE_DIR = "D:\NUS\FYP"
$env:CREDIT_CARD_FRAUD_SQL_PASSWORD = Read-Host "PostgreSQL password" -MaskInput
try {
    & ".\expops-platform\.venv\Scripts\expops.exe" run credit-card-fraud --local
} finally {
    Remove-Item Env:CREDIT_CARD_FRAUD_SQL_PASSWORD -ErrorAction SilentlyContinue
}
```

With the current Windows checkout, existing environments can be run without package-index access and with an explicit writable worker directory:

```powershell
$runtimeTemp = "D:\NUS\FYP\credit-card-fraud\.credit-card-fraud\tmp"
$env:MLOPS_WORKSPACE_DIR = "D:\NUS\FYP"
$env:MLOPS_WORKSPACE_BASE_DIR = $runtimeTemp
$env:MLOPS_ENV_READY = "1"
$env:PIP_NO_INDEX = "1"
$env:PYTHONPATH = "D:\NUS\FYP\expops-platform\src"
$env:CREDIT_CARD_FRAUD_SQL_PASSWORD = Read-Host "PostgreSQL password" -MaskInput

try {
    & ".\credit-card-fraud\.credit-card-fraud\envs\fraud-model-env\Scripts\python.exe" `
        -m expops.main run credit-card-fraud --local
} finally {
    Remove-Item Env:CREDIT_CARD_FRAUD_SQL_PASSWORD -ErrorAction SilentlyContinue
}
```

This workaround assumes the pinned model and reporting environments have already been created.

The commands above match the active PostgreSQL metadata and GCS cache, artifact,
and dataset configuration. The SQL plugin resolves
`CREDIT_CARD_FRAUD_SQL_PASSWORD`, and GCS requires Google Application Default
Credentials. Because the deployment also declares the S3 example store, the
`expops` AWS profile and the platform's AWS optional dependency must remain
available until that unused store is removed from the configuration.

ExpOps stores environments, logs, metrics, caches, model spill files, and chart artifacts under:

```text
credit-card-fraud/.credit-card-fraud/
```

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

## Known ExpOps issues exposed by this run

- On this Windows checkout, the default process workspace `/tmp` resolved to an inaccessible `D:\tmp`; `MLOPS_WORKSPACE_BASE_DIR` was required.
- The seed aggregator received ordinal keys (`seed1`, `seed2`, `seed3`) even though the expanded process IDs used seeds `41`, `42`, and `43`. Evaluation outputs therefore carry `random_seed` explicitly, and the aggregator treats that value as authoritative.
- Cache-manifest filenames for seed-parallel nodes contain canonical XPath characters and exceed or violate Windows path rules. The run completed by returning full payloads, but the affected training, evaluation, and aggregation nodes were not persisted as reusable manifests.
- A partitioned pandas `DataFrame` was spilled and restored by ExpOps as a two-dimensional NumPy array, so its column labels were lost at the parallel boundary. `evaluate_partition` validates the array width and reconstructs the known dataset columns before scoring.
- The same Windows cache-path limitation affects some data-parallel and aggregation manifests. Full-payload fallback allowed the pipeline to finish correctly, but cache reuse is incomplete for the affected nodes.

## Reproducibility snapshot

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

## Next experiment

The next useful step is performance scaling rather than another statistical variant: repeat the same nested graph with different worker counts and partition counts, then compare wall-clock time, scheduling overhead, and memory use. Before treating those timings as representative, the Windows cache-path and DataFrame-serialization issues should be isolated as platform fixes because failed manifest reuse can distort repeated-run performance.
