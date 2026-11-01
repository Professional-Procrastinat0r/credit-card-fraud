# Original-main local validation

Validated on Windows, 1 November 2026, with the versions and setup in
[LEGACY_BASELINE.md](LEGACY_BASELINE.md). This is a prepared local environment,
not a clean bootstrap benchmark or a cloud/cluster acceptance test.

| Check | Observed result |
| --- | --- |
| Unmodified platform source | Original `main` at `a3e6107d8182b928a116098931af66e3df110208` |
| Contract tests | 3 passed: selected source/revision and LZ4, 25-node expansion, SQLite metadata binding |
| Full dataset pipeline | Run `project-credit-card-fraud-20261101081219-feb495e4`: `completed`; 23 process records `completed`, 2 `cached`, none failed |
| Chart delivery | Real run metadata yielded a PNG; original REST chart endpoint returned its 129,243 bytes |
| Original SDK 0.1.3 | Initial `run.status` SSE event received; changing a temporary unrelated SQLite key caused another event through its file watcher; key removed afterward |
| Original frontend | Production `npm run build` completed with exit code 0 |
| Original I/O service | Dependencies installed in separate Python 3.14 environment; original `server` module imported successfully |

The first execution finished the 24 computational nodes but failed the chart
subprocess after the original automatic environment bootstrap raced a pip
self-upgrade. The original CLI nevertheless printed a successful completion
message. Preparing both named project environments with the original platform
and scientific/chart dependencies resolved that subprocess failure for the
subsequent run above. The scripts retain that explicit preparation.

Original Windows cache-manifest filename warnings still occurred. This run
therefore demonstrates successful execution with the original implementation's
fallback behavior, not complete cache portability or a timing comparison.

Firebase sign-in, authenticated GitHub browsing/writes, Firestore metadata,
the original UI's pre-run checks, and remote cluster execution have not been
accepted here. The original UI pre-run endpoint/workspace mismatches are
described in the guide; start runs using the CLI and use the original webapp
for monitoring after configuring its existing authentication settings.
