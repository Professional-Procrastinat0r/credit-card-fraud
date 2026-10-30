# Fraud analyses with process parallelism

A standalone copy of the experiment used for the FYP process-parallelism
comparison. It uses ordinary ExpOps processes and the latest platform's local
compute/storage configuration. The original root experiment remains available.

The 13-process graph has three independent analysis branches after a common
load/split: histogram gradient boosting, Isolation Forest and a reconstruction
autoencoder. Each branch prepares features, trains a model and scores validation
and test data. The final processes compare predictions and write reports.
One fixed seed (42) controls reproducibility; there is no seed/data fanout.
Three workers match the graph's maximum useful width.

## Setup and run

Use the current `staging` ExpOps platform (mounted storage APIs), rather than
the predecessor's `main` or an older PyPI release. With sibling platform and
fraud checkouts, run these commands from the **credit-card-fraud repository root**:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ../expops-platform -r experiments/process-parallelism/requirements.txt
.\.venv\Scripts\python.exe experiments/process-parallelism/run.py --workers 3
```

Place the original dataset at `data/creditcard.csv` first. It is the ULB/Kaggle
Credit Card Fraud Detection dataset: 284,807 transactions, 492 fraudulent,
columns `Time`, `V1` through `V28`, `Amount`, `Class`. It is not uploaded with code.
The pinned scientific dependencies match the measured study; Python 3.14 was used
for that study. ExpOps' own installation supplies Dask, YAML and platform dependencies.

Run the one-worker control with:

```powershell
.\.venv\Scripts\python.exe experiments/process-parallelism/run.py --workers 1
```

`run.py` invokes the native ExpOps platform with the project and compute YAML.
It sets local runtime/output directories and limits internal numerical threads
to one. The `--workers` option overrides the resolved compute plan, whose YAML
default is three. The project uses `environment: system`, sharing the installed
environment between local workers, as in the benchmark. There are no benchmark
timers, revision loaders, wheelhouses, five-repeat orchestration or instrumentation.

Repeated commands reuse cached process results. Changing worker count alone does
not force training. For a fresh run, stop any active run and remove the entire
generated `experiments/process-parallelism/.process-parallelism/` directory
(cache, metadata and ordinary output files together), then run again. Keep this
directory if you want to retain its models or history. Do not remove output files
alone while keeping cached path references, and do not run two invocations against
the same output directory concurrently.

## Scientific controls

- Stratified 60/20/20 train/validation/test split with seed 42; exclude `Time` and
  `Class` from features. This is not a temporal deployment evaluation.
- Gradient boosting: 150 iterations, 31 leaves, learning rate 0.08, balanced
  classes, no early stopping.
- Isolation Forest: 300 trees, at most 8,192 sampled training rows per tree,
  `n_jobs=1`, mixed training data without fraud labels.
- Autoencoder: sklearn MLP regressor, hidden layers 32/8/32, Adam, batch 512,
  exactly 50 epochs. Fit the scaler and model only on legitimate training rows;
  clip standardized inputs to [-8,8]. This uses labels to select normal rows.
  Budget-exhaustion convergence warnings are expected, not a convergence claim.
- Threshold each branch at the 99th percentile of legitimate validation scores.
  Test labels never choose thresholds. Report test average precision, ROC-AUC,
  precision, recall, F1, confusion matrix and deterministic score hashes.

## Outputs and reuse

All generated state is under this experiment's ignored `.process-parallelism/`:

| Path relative to `.process-parallelism/storage/` | Contents |
| --- | --- |
| `metadata.sqlite` | ExpOps execution records |
| `cache/` | ExpOps intermediate-result cache |
| `artefact/supervised/model.pkl` | Gradient-boosting model |
| `artefact/isolation/model.pkl` | Isolation Forest model |
| `artefact/autoencoder/model.pkl` | Reconstruction model |
| `artefact/autoencoder-scaler/model.pkl` | Fitted scaler |
| `artefact/*-scores/` | Saved validation/test predictions |
| `artefact/report/comparison.json` | Full scientific report |
| `artefact/report/comparison.md` | Readable comparison |
| `artefact/report/average-precision.svg` | Static comparison chart |

Load a trusted local model with `pickle.load`. For the autoencoder, also load its
scaler, apply the same feature order from the report, scale/clip inputs and use
mean squared reconstruction error. Isolation Forest scores are
`-model.score_samples(x)`; supervised scores are `model.predict_proba(x)[:, 1]`.
Use the report's validation-derived threshold to classify scores.

This preserves the benchmark's **local/shared-host file exchange**. Although the
directory is also the configured local artefact mount, the numerical workload
writes ordinary files and stores absolute path references. Those files are not
automatically remote managed-file exports or Monitor chart publications. Merely
switching to a cloud mount or SLURM does not make these references portable;
multi-host execution needs a shared filesystem or a separate VFS adaptation.

## Monitor and verification

In ExpOps Monitor, register project ID **process-parallelism**, upload this
experiment's `configs/compute_config.yaml` and `configs/project_config.yaml`,
and supply its absolute directory as the project root on the Monitor host.
After an execution, the graph and recorded statuses are available. Ordinary
report files above do not appear as published charts in Monitor.

Run the retained scientific safeguards from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s experiments/process-parallelism/tests -v
```

These check split disjointness, normal-training-only scaling, model reload and
independence of threshold selection from test labels. The numerical/file-output
functions are unchanged from the measured workload; only unused instrumentation
and the execution wrapper were removed/adapted for a standalone project.
This packaged run is a usability check, not a new five-repeat timing study.

Validated on 2026-10-31 with Python 3.14 and the companion current platform:
all three scientific tests passed; a full-budget three-worker run executed all
13 processes successfully; the one-worker rerun reused all 13 results. The full
scientific report matched the retained five-repeat benchmark report exactly,
including split membership and all validation/test prediction hashes.
