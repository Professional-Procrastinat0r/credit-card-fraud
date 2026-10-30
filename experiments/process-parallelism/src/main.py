"""Ordinary ExpOps process wrapper for the three-branch fraud experiment."""
from expops.core import process

import workload


@process()
def run_stage(operation, dependency_keys, arguments, output_key, context=None, **kwargs):
    value = workload.perform(
        "fraud-processes", operation, [kwargs[key] for key in dependency_keys],
        arguments, None, context,
    )
    return {"report" if output_key == "collect" else output_key: value}
