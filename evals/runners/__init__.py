from __future__ import annotations


def run_trace_eval(*args, **kwargs):
    from .run_deepeval_from_trace import run_trace_eval as _run_trace_eval

    return _run_trace_eval(*args, **kwargs)

__all__ = ["run_trace_eval"]
