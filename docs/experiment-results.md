# Historical experiment results

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

Average precision changes noticeably across the three holdout samples, while precision, F1, and alert rate remain comparatively stable. Recall ranges from about 89.8% to 94.9%. The broad operational conclusion is therefore stable: threshold `0.5` catches most frauds but produces many false alerts: although a single split understates uncertainty in recall and ranking quality.

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
