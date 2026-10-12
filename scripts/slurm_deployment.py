"""Checks and run inspection for standalone Git/S3/GCS deployments."""
from argparse import ArgumentParser
from collections import Counter
import json
from pathlib import Path
import socket
import uuid


def storage_plan(compute):
    from expops.storage.config import load_storage_config
    from expops.storage.plan import resolve_storage_plan
    from expops.storage.vpath import VPath
    return resolve_storage_plan("credit-card-fraud", config_path=compute,
                                storage_config=load_storage_config(compute),
                                project_root=compute.parent,
                                virtual_project_root=VPath('/local'))


def preflight(compute, files_only):
    from expops.storage import VFS
    print("Checking deployment from", socket.gethostname(), flush=True)
    with VFS.from_config(compute) as fs:
        with fs.open("local/src/model.py") as stream:
            assert stream.read(64), "Empty model source"
        print("Git model source: OK", flush=True)
        info = fs.stat("input/creditcard.csv")
        assert info.size_bytes > 0, "Empty dataset"
        with fs.open("input/creditcard.csv") as stream:
            assert len(next(stream).strip().split(",")) == 31, "Expected 31 CSV columns"
        print("S3 dataset: OK,", info.size_bytes, "bytes", flush=True)
        # Tiny isolated objects are retained as credential-check evidence.
        name = "_preflight/" + uuid.uuid4().hex + ".txt"
        for mount in ("cache", "artefact"):
            path = mount + "/" + name
            fs.write_bytes(path, b"expops-deployment-check\n")
            assert fs.read_bytes(path) == b"expops-deployment-check\n"
            print("GCS", mount, "write/read: OK", flush=True)
    if files_only:
        print("Filesystem checks passed; metadata was not checked.")
        return
    plan = storage_plan(compute)
    from expops.storage.secrets import StorageCredentialContext
    credentials = StorageCredentialContext.from_environment()
    if plan.metadata_spec.to_dict()['type'] == 'redis':
        import redis
        spec = plan.metadata_spec
        client = redis.Redis(host=spec.host, port=spec.port, db=spec.db,
                             password=credentials.resolve(spec.password_ref),
                             socket_connect_timeout=spec.connection_timeout,
                             socket_timeout=spec.connection_timeout)
        key = spec.namespace_prefix + ':_preflight:' + uuid.uuid4().hex
        try:
            if not client.ping():
                raise RuntimeError('Redis PING failed')
            if not client.set(key, 'expops-check', ex=60, nx=True):
                raise RuntimeError('Redis preflight write failed')
            if client.get(key) != b'expops-check':
                raise RuntimeError('Redis preflight read failed')
            if client.delete(key) != 1:
                raise RuntimeError('Redis preflight cleanup failed')
            print('Redis authenticated PING and write/read/delete: OK', flush=True)
        finally:
            client.close()
        return
    from sqlalchemy import create_engine, text
    from expops.storage.backends.sqlalchemy import sqlalchemy_url_from_spec
    engine = create_engine(sqlalchemy_url_from_spec(plan.metadata_spec, credentials))
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar() == 1
        print("Supabase PostgreSQL SELECT 1: OK", flush=True)
    finally:
        engine.dispose()


def inspect_run(compute, run_id, output, save_summary=None):
    from expops.storage.factory import create_storage_session_from_plan
    from expops.storage.managed_references import ManagedObjectRef, read_managed_object
    plan = storage_plan(compute)
    with create_storage_session_from_plan(plan) as session:
        metadata = session.metadata_store
        if run_id == 'latest':
            runs = metadata.list_runs(1)
            if not runs:
                raise ValueError('No runs were found')
            run_id = runs[0]
        if not run_id:
            print(json.dumps({run: metadata.get_run_status(run) for run in metadata.list_runs(10)}, indent=2))
            return
        status = metadata.get_run_status(run_id)
        if status is None:
            raise ValueError("Run ID was not found in this project's metadata")
        records = {key: value for key, value in metadata.list_run_steps(run_id).items()
                   if key.endswith(".__process__")}
        charts = metadata.list_run_charts(run_id)
        summary = {"run_id": run_id, "status": status,
                          "processes": dict(Counter(row.get("status", "unknown") for row in records.values())),
                          "chart_groups": len(charts),
                          "summary_metrics": metadata.get_probe_metrics_by_path(
                              run_id, "//process[@name='aggregate_seed_data_metrics']"),
                          "process_records": records, "charts": charts}
        print(json.dumps({key: value for key, value in summary.items()
                          if key not in ('process_records', 'charts')}, indent=2))
        if save_summary:
            save_summary.parent.mkdir(parents=True, exist_ok=True)
            save_summary.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        if output:
            output.mkdir(parents=True, exist_ok=True)
            for chart in charts.values():
                for item in chart.get("items", []):
                    ref = ManagedObjectRef.from_mapping(item["managed_object"])
                    path = output / Path(item.get("title") or "report.png").name
                    path.write_bytes(read_managed_object(ref))
                    print("Downloaded verified chart:", path)


def main():
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    checks = commands.add_parser("preflight")
    checks.add_argument("--compute", type=Path, required=True)
    checks.add_argument("--files-only", action="store_true")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--compute", type=Path, required=True)
    inspect.add_argument("--run-id")
    inspect.add_argument("--download-report", type=Path)
    inspect.add_argument("--save-summary", type=Path)
    args = parser.parse_args()
    try:
        compute = args.compute.resolve()
        if args.command == "preflight":
            preflight(compute, args.files_only)
        else:
            inspect_run(compute, args.run_id, args.download_report, args.save_summary)
    except Exception as error:
        # Do not dump credential-bearing SQL URLs or provider exceptions.
        raise SystemExit("Deployment check failed (" + type(error).__name__ +
                         "). Check the last successful stage, endpoint, credentials and permissions.") from None


if __name__ == "__main__":
    main()
