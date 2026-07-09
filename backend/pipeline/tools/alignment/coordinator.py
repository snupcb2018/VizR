"""
Alignment coordinator - routes alignment requests to appropriate handlers
정렬 코디네이터 - 정렬 요청을 적절한 핸들러로 라우팅
🚀 Auto Plugin System Integration with Auto Tool Registration
"""

import json
import sqlite3
import logging
from typing import Dict

from backend.pipeline.tools.base_coordinator import BaseCoordinator

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class AlignmentCoordinator(BaseCoordinator):
    """Alignment 코디네이터 - 자동 tool 등록 시스템 사용"""
    
    def __init__(self):
        super().__init__("alignment")
        logger.info(f"🚀 [ALIGNMENT-COORDINATOR] Initialized with {len(self.tools)} tools")
    
    def execute(self, job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
        """Alignment 실행 - 자동 등록된 tools 사용"""
        step_id = job_step['step_id']
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        
        logger.info(f"[ALIGNMENT] Starting alignment process")
        logger.info(f"  Step ID: {step_id}")
        logger.info(f"  Available tools: {list(self.tools.keys())}")
        
        try:
            # Alignment 도구 결정 (tool_name이나 parameters에서)
            alignment_tool = job_step['tool_name'] if 'tool_name' in job_step.keys() else 'hisat2'  # 기본값: hisat2
            if not alignment_tool and parameters:
                alignment_tool = parameters.get('alignment_tool', 'hisat2')
            
            logger.info(f"[ALIGNMENT] Selected tool: {alignment_tool}")
            
            tool_func = self.tools.get(alignment_tool)
            if not tool_func:
                raise ValueError(f"Alignment tool '{alignment_tool}' not found. Available: {list(self.tools.keys())}")
            
            # Tool 실행
            result = tool_func(job_step, worker_id)
            
            # 성공 여부 확인
            if hasattr(result, 'get'):
                success = result.get('success', True)
                error_detail = result.get('stderr', 'Unknown error')
            else:
                success = result['success'] if 'success' in result else True
                error_detail = result['stderr'] if 'stderr' in result else 'Unknown error'
                
            if not success:
                error_msg = f"Alignment tool '{alignment_tool}' failed: {error_detail}"
                logger.error(f"❌ [ALIGNMENT] {error_msg}")
                raise Exception(error_msg)
            
            logger.info(f"✅ [ALIGNMENT] Alignment process completed successfully using {alignment_tool}")
            
        except Exception as e:
            error_msg = f"Critical Alignment failure: {str(e)}"
            logger.error(f"🚨 [ALIGNMENT] {error_msg}")
            
            # 전체 파이프라인 중단을 위해 예외 재발생
            raise Exception(f"PIPELINE_CRITICAL_FAILURE: {error_msg}")

        return result


# 코디네이터 인스턴스 생성
_coordinator = AlignmentCoordinator()

def REGISTER_COORDINATOR(job_worker):
    """🔌 자동 플러그인 등록 함수 - PipelineJobWorker에 코디네이터 등록"""
    logger.info(f"🔌 [PLUGIN-REG] Registering alignment coordinator...")
    return job_worker.register_step_handler('alignment', _coordinator.execute)