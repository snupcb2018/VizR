"""
QC coordinator - routes QC requests to appropriate handlers
QC 코디네이터 - QC 요청을 적절한 핸들러로 라우팅
🚀 Auto Plugin System Integration with Auto Tool Registration
"""

import json
import sqlite3
import logging
from typing import Dict

from backend.pipeline.tools.base_coordinator import BaseCoordinator

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class QCCoordinator(BaseCoordinator):
    """QC 코디네이터 - 자동 tool 등록 시스템 사용"""
    
    def __init__(self):
        super().__init__("qc")
        logger.info(f"🚀 [QC-COORDINATOR] Initialized with {len(self.tools)} tools")
    
    def execute(self, job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
        """QC 실행 - 자동 등록된 tools 사용"""
        step_id = job_step['step_id']
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        
        logger.info(f"[QC] Starting quality control analysis")
        logger.info(f"  Step ID: {step_id}")
        logger.info(f"  Available tools: {list(self.tools.keys())}")
        
        try:
            # 기본적으로 fastqc 사용 (향후 확장 가능)
            qc_tool = 'fastqc'
            tool_func = self.tools.get(qc_tool)
            
            if not tool_func:
                raise ValueError(f"QC tool '{qc_tool}' not found. Available: {list(self.tools.keys())}")
            
            # Tool 실행
            result = tool_func(job_step, worker_id)
            
            # 성공 여부 확인
            if not result.get('success', True):
                error_msg = f"QC tool '{qc_tool}' failed: {result.get('stderr', 'Unknown error')}"
                logger.error(f"❌ [QC] {error_msg}")
                raise Exception(error_msg)
            
            logger.info(f"✅ [QC] Quality control analysis completed successfully using {qc_tool}")
            
        except Exception as e:
            error_msg = f"Critical QC failure: {str(e)}"
            logger.error(f"🚨 [QC] {error_msg}")
            
            # 전체 파이프라인 중단을 위해 예외 재발생
            raise Exception(f"PIPELINE_CRITICAL_FAILURE: {error_msg}")

        return result


# 코디네이터 인스턴스 생성
_coordinator = QCCoordinator()

def REGISTER_COORDINATOR(job_worker):
    """🔌 자동 플러그인 등록 함수 - PipelineJobWorker에 코디네이터 등록"""
    logger.info(f"🔌 [PLUGIN-REG] Registering QC coordinator...")
    return job_worker.register_step_handler('qc', _coordinator.execute)