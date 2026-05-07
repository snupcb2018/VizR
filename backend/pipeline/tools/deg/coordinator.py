"""
DEG 분석 코디네이터

차등발현분석을 위한 도구 선택 및 라우팅을 담당합니다.
- edgeR: Trinity 기반 edgeR 분석
- DESeq2: R 스크립트 기반 DESeq2 분석
🚀 Auto Plugin System Integration with Auto Tool Registration
"""

import json
import sqlite3
from typing import Dict
import logging

from backend.pipeline.tools.base_coordinator import BaseCoordinator

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class DEGCoordinator(BaseCoordinator):
    """DEG 코디네이터 - 자동 tool 등록 시스템 사용"""
    
    def __init__(self):
        super().__init__("deg")
        logger.info(f"🚀 [DEG-COORDINATOR] Initialized with {len(self.tools)} tools")
    
    def execute(self, job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
        """DEG 실행 - 자동 등록된 tools 사용"""
        step_id = job_step['step_id']
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        
        logger.info(f"[DEG] Starting differential expression analysis")
        logger.info(f"  Step ID: {step_id}")
        logger.info(f"  Available tools: {list(self.tools.keys())}")
        
        try:
            # DEG 도구 결정 (tool_name이나 parameters에서)
            deg_tool = job_step['tool_name'] if 'tool_name' in job_step.keys() else 'deseq2'  # 기본값: deseq2
            if not deg_tool and parameters:
                deg_tool = parameters.get('deg_tool', 'deseq2')
            
            logger.info(f"[DEG] Selected tool: {deg_tool}")
            
            tool_func = self.tools.get(deg_tool)
            if not tool_func:
                raise ValueError(f"DEG tool '{deg_tool}' not found. Available: {list(self.tools.keys())}")
            
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
                error_msg = f"DEG tool '{deg_tool}' failed: {error_detail}"
                logger.error(f"❌ [DEG] {error_msg}")
                raise Exception(error_msg)
            
            logger.info(f"✅ [DEG] DEG analysis completed successfully using {deg_tool}")
            
        except Exception as e:
            error_msg = f"Critical DEG failure: {str(e)}"
            logger.error(f"🚨 [DEG] {error_msg}")
            
            # 전체 파이프라인 중단을 위해 예외 재발생
            raise Exception(f"PIPELINE_CRITICAL_FAILURE: {error_msg}")

        return result


# 코디네이터 인스턴스 생성
_coordinator = DEGCoordinator()

def REGISTER_COORDINATOR(job_worker):
    """🔌 자동 플러그인 등록 함수 - PipelineJobWorker에 코디네이터 등록"""
    logger.info(f"🔌 [PLUGIN-REG] Registering DEG coordinator...")
    return job_worker.register_step_handler('deg', _coordinator.execute)