from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReportArtifacts:
    report_path: str
    manifest_path: str
    trace_path: str
