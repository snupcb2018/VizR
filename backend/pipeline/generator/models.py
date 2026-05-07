#!/usr/bin/env python3
"""
Pipeline Job Models
"""

import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


class PipeLineStep:
    """파이프라인 스텝 정의 클래스"""
    def __init__(self, 
                 step_id: str,
                 step: str, 
                 name: str, 
                 tool: str, 
                 order: int, 
                 status: str,
                 parameters: Optional[Dict[str, Any]] = None):
        
        self.step_id = step_id
        self.step = step
        self.name = name
        self.tool = tool
        self.order = order
        self.status = status
        self.parameters = parameters
        self.input_dir = None
        self.input_files = []
        self.output_dir = None
        self.output_files = []
        self.resources = {}
        
        # ❌ depends_on 제거됨 - DAG 시스템에서 의존성 관리


class PipelineJobDefinition:
    """파이프라인 작업 정의 클래스"""
    def __init__(self, workbench: sqlite3.Row, pipeline_config: sqlite3.Row, samples: List[sqlite3.Row]):
        self.job_id = f"job_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self.workbench = workbench
        self.pipeline_config = pipeline_config
        self.samples = samples
        self.steps = []