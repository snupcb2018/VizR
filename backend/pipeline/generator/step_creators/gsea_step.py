#!/usr/bin/env python3
"""
GSEA Step Creator
"""

from __future__ import annotations

from typing import List

from ..models import PipeLineStep, PipelineJobDefinition


def create_gsea_step(
    job_definition: PipelineJobDefinition,
    deg_tool: str,
    step_counter: int,
    built_in_databases: list[str] | None = None,
) -> List[PipeLineStep]:
    database_scope = "selected" if built_in_databases is not None else "legacy"
    step = PipeLineStep(
        step_id=f"gsea_builtin_preranked_{deg_tool}",
        step="gsea",
        name="Precompute built-in GSEA results",
        tool="builtin_preranked",
        order=step_counter,
        status="pending",
        parameters={
            "deg_tool": deg_tool,
            "built_in_databases": built_in_databases or [],
            "ranking_metric": "logFC",
            "database_refresh": "always",
            "database_scope": database_scope,
        },
    )
    return [step]
