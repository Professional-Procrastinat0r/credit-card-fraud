"""Run with the isolated original platform interpreter, not staging."""
from pathlib import Path
import subprocess

import expops
import lz4.frame
import yaml

PROJECT = Path(__file__).resolve().parents[1]
PLATFORM = PROJECT.parent / "expops-platform"


def test_original_platform_source_is_selected():
    assert Path(expops.__file__).resolve().is_relative_to(PLATFORM / "src")
    commit = subprocess.check_output([
        "git", "-c", f"safe.directory={PLATFORM.as_posix()}", "-C", str(PLATFORM), "rev-parse", "HEAD",
    ], text=True).strip()
    assert commit == "a3e6107d8182b928a116098931af66e3df110208"
    assert lz4.frame.decompress(lz4.frame.compress(b"original-platform")) == b"original-platform"


def test_original_engine_expands_nested_pipeline():
    from expops.core.graph.pipeline_utils import get_process_graph_summary_from_project
    graph = get_process_graph_summary_from_project(PROJECT.parent, PROJECT.name)
    assert len(graph["nodes"]) == 25
    assert sum("train_model" in str(node) for node in graph["nodes"]) == 3
    assert sum("evaluate_partition" in str(node) for node in graph["nodes"]) == 9


def test_legacy_sqlite_binding_matches_original_webapp(tmp_path):
    from expops.storage.factory import create_kv_store
    config = yaml.safe_load((PROJECT / "configs/project_config.yaml").read_text())
    assert "path" in config["data"] and "inputs" not in config["data"]
    backend = config["experiment"]["cache"]["backend"]
    assert backend == {"type": "local", "path": "kv_store.db"}
    store = create_kv_store(PROJECT.name, backend, env={}, project_root=tmp_path)
    assert store.db_path == tmp_path / "kv_store.db"
    store.mark_pipeline_started("contract-run")
    assert store.get_run_status("contract-run") == "running"
