"""
GSEA coordinator.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Dict

from backend.pipeline.tools.base_coordinator import BaseCoordinator
from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'INFO')


class GSEACoordinator(BaseCoordinator):
    def __init__(self):
        super().__init__("gsea")
        logger.info(f"✅ [GSEA-COORDINATOR] Initialized with {len(self.tools)} tools")

    def execute(self, job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        tool_name = job_step['tool_name'] if 'tool_name' in job_step.keys() else None
        if not tool_name:
            tool_name = parameters.get('tool', 'builtin_preranked')

        logger.info(f"[GSEA] Starting precompute step with tool '{tool_name}'")
        tool_func = self.tools.get(tool_name)
        if not tool_func:
            return {
                'success': True,
                'warning': f"GSEA tool '{tool_name}' was not found",
                'had_failures': True,
            }

        result = tool_func(job_step, worker_id)
        if not isinstance(result, dict):
            return {'success': True}
        return result


_coordinator = GSEACoordinator()


def REGISTER_COORDINATOR(job_worker):
    logger.info("🔌 [PLUGIN-REG] Registering GSEA coordinator...")
    return job_worker.register_step_handler('gsea', _coordinator.execute)
