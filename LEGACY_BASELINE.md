# Original ExpOps baseline

This branch is for testing the original implementations before the staging/SDK
migration. It restores the pre-VFS fraud application from `b1e3ee6`, with portable
local deployment settings and Windows-compatible dependency pins. The model,
evaluation and reporting source is unchanged from that historical revision.

## Pinned stack

| Repository | Revision | Role |
| --- | --- | --- |
| expops-platform | `a3e6107d8182b928a116098931af66e3df110208` | Original `main`, executed without source patches |
| expops-webapp | `3d7d5ee` | Original frontend, listener SDK **0.1.3** from its lockfile |
| expops-services | `405a534` | Original I/O service and cluster service source |
| credit-card-fraud | `b1e3ee6` plus this branch | Legacy fraud application and local test setup |

The prepared checkouts on this PC are siblings under `D:\NUS\FYP\legacy-main`.
The existing repositories under `D:\NUS\FYP` retain their branches and working
changes. The other baseline repositories are detached worktrees at the revisions
above. Do not use the migrated webapp or platform staging for this comparison.
The prepared run launcher uses the original `MLOPS_ENV_READY` switch to keep
execution in the foreground after setup; this is a prepared-environment run,
not a measurement of the original cold bootstrap.

## What is original

- Project files use `data.path`, native `src/...` script paths, dependency-file
  lists, and `experiment.cache.backend`.
- The default experiment has three seed branches, three scoring partitions per
  seed, exact aggregation and one PNG report: **25 expanded process nodes**.
- SQLite metadata uses the original KV schema. Local artifact/cache handling is
  the original implementation, without managed `published_file` bindings.
- The old webapp uses SDK 0.1.3. Its local Next.js SSE adapter watches SQLite files
  and re-fetches the original Python REST endpoints when files change.
- The explicit `path: kv_store.db` and `EXPOPS_SQLITE_DIR` align the application's
  SQLite file with that original SDK's filename convention.
- Firebase Authentication still handles sign-in. A Firestore metadata deployment
  is a separate optional legacy backend, not required by this local profile.

The original SLURM compute example is retained as `configs/compute.slurm.yaml`.
The default compute file now selects two local workers. SLURM/cloud acceptance
is not implied by the local checks.

## Runtime and dataset

The old platform pins `lz4==4.0.2`; its published Windows wheels stop at Python
3.10. Execution therefore uses isolated **Python 3.10.22** with NumPy 2.2.6,
pandas 2.3.3, scikit-learn 1.7.2 and Matplotlib 3.10.8. This is an implementation
baseline, not a reproduction of the historical Python 3.14 numerical/timing
snapshot in README. Dependency locks record the tested environments.

The original I/O service uses a separate Python >=3.11 environment. Its module
contains inline parsing helpers and never imports ExpOps; setup omits that unused
declared dependency rather than installing a different execution platform there.

`data/creditcard.csv` is ignored by Git. On this PC an independent local copy of
the existing dataset has been placed in the baseline checkout. On another PC,
provide the dataset there before running. It is never included in this branch.

## First-time preparation

Keep the four pinned repositories in the sibling layout above. From PowerShell:

```powershell
cd D:\NUS\FYP\legacy-main\credit-card-fraud
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
```

Execution-policy bypass applies only to this invocation. Setup keeps the Python
download inside `legacy-main/.python`, does not register a system interpreter,
and prepares the model/reporting environments sequentially. Both receive the
unchanged original platform and chart dependencies; this avoids the old bootstrap's
pip self-upgrade race and missing chart-subprocess imports on this PC.

The environments and original webapp dependencies are already installed on this
PC. `setup-local.ps1` is for rebuilding them, not required for every launch.

## Start and observe

Use separate PowerShell windows, starting from the fraud baseline checkout.
Start the original run server:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\serve-local.ps1
```

Start the original I/O service after supplying Firebase Admin/GitHub App settings:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-io.ps1
```

Copy `configs/env/io.env.example` to the original I/O service's `.env`, and
`configs/env/webapp.env.example` to the original webapp's `.env.local`; replace
the placeholders with your existing settings. The templates contain no secrets.

Start the original webapp:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-webapp.ps1
```

Open `http://localhost:3000`, choose the fraud repository and branch
`compat/platform-main`, and use `http://127.0.0.1:8765` for the run server.
Webpack is selected as a launch option; the frontend source/configuration remains
unchanged. The script sets the old SDK's SQLite directory explicitly.

Start a real run in another window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

Observe it in the existing run-monitor view. Start with CLI execution because
the original I/O service has no version-hash endpoint, while the old frontend's
external-backend configuration sends that check there. Also, the original
workspace Git check assumes a Git repository above the workspace root; this
sibling-worktree layout does not meet that assumption. These original pre-run
UI limitations are retained rather than silently patched.

## Known baseline behaviors

- Canonical XPath characters in Windows cache-manifest filenames can produce
  `Invalid argument` warnings. Full-payload fallback allows computation to
  continue, but cache reuse is incomplete. Do not interpret cached reruns as a
  clean performance comparison.
- The original automatic environment setup can race a pip self-upgrade, and
  chart subprocesses can select the model interpreter. The explicit preparation
  above supplies the required platform/chart packages to both named environments.
- The original CLI can print a successful completion message even when a chart
  process failed. Check the run status and process records, not only that message.
- Authentication, GitHub writes, Firestore rules and cluster execution require
  their own configured environments; no credentials are bundled here.

## Check the source selection

```powershell
..\.venv-platform\Scripts\python.exe -m pytest tests -q
```

These checks verify the original platform revision/import path, the 25-node
expansion and the SQLite binding used by the original frontend. The historical
results below the README banner are retained as historical evidence.

See [VALIDATION.md](VALIDATION.md) for the successful full run, SDK/file-watcher
and chart checks, and the original behaviors encountered during preparation.
