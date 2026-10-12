"""Deterministic transport/parallelism example; not an ML quality benchmark."""

import csv
import hashlib
import json
import os
import socket

from helper import model_factor

from expops.core import log_metric, process
from expops.core.runtime.custom_model_base import MLOpsCustomModelBase

SOURCE_OFFSET = 0


class ScalingModel(MLOpsCustomModelBase):
    def __init__(self, factor):
        super().__init__()
        self.factor = factor

    def predict(self, rows):
        return [row["value"] * self.factor for row in rows]


@process()
def load(context=None):
    with context.inputs["samples"].open(newline="", encoding="utf-8") as file:
        rows = [{"id": int(row["id"]), "value": int(row["value"])}
                for row in csv.DictReader(file)]
    if not rows or any(row["value"] < 0 for row in rows):
        raise ValueError("Samples must contain nonnegative values")
    # The same namespace facade remains available inside ordinary processes.
    assert context.fs.is_file("input/vfs-slurm-fixtures/data/samples.csv")
    log_metric("loaded_rows", len(rows))
    return {"rows": rows}


@process()
def train(rows=None, random_seed=0, context=None):
    assert all(isinstance(row, dict) for row in rows)
    model = ScalingModel(model_factor(random_seed) + SOURCE_OFFSET)
    model.training_value_sum = sum(row["value"] for row in rows)
    log_metric("factor", model.factor)
    return {"rows": rows, "model": model,
            "training_stats": [model.factor, model.training_value_sum]}


@process()
def evaluate(rows=None, model=None, training_stats=None, random_seed=0, context=None):
    assert training_stats == [model.factor, model.training_value_sum]
    total = sum(model.predict(rows))
    result = {"total": total, "count": len(rows), "id_sum": sum(row["id"] for row in rows)}
    log_metric("total", total)
    log_metric("count", len(rows))
    # Test-owned VFS exports also prove which variants actually execute.
    identity = hashlib.sha256(context.current_process.encode()).hexdigest()[:20]
    context.fs.write_text("output/leaf-" + identity + ".json", json.dumps({
        **result, "seed": random_seed, "factor": model.factor,
        "training_value_sum": model.training_value_sum,
        "process": context.current_process, "pid": os.getpid(), "hostname": socket.gethostname(),
        "data_hash": context.current_data_hash,
    }))
    return result


def numbers(value):
    if isinstance(value, dict):
        return [item for child in value.values() for item in numbers(child)]
    return [value]


@process()
def aggregate(total=None, count=None, id_sum=None, context=None):
    result = {"total": sum(numbers(total)), "count": sum(numbers(count)),
              "id_sum": sum(numbers(id_sum))}
    for key, value in result.items():
        log_metric(key, value)
    return result
