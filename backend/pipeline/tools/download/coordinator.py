"""
Download coordinator - routes download requests to appropriate handlers
다운로드 코디네이터 - 다운로드 요청을 적절한 핸들러로 라우팅
🚀 Auto Plugin System Integration with Auto Tool Registration
"""

import json
import sqlite3
import logging
from typing import Dict

from backend.pipeline.tools.base_coordinator import BaseCoordinator

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class DownloadCoordinator(BaseCoordinator):
    """다운로드 코디네이터 - 자동 tool 등록 시스템 사용"""
    
    def __init__(self):
        super().__init__("download")
        logger.info(f"🚀 [DOWNLOAD-COORDINATOR] Initialized with {len(self.tools)} tools")
    
    def execute(self, job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
        """데이터 다운로드/복사 실행 - 자동 등록된 tools 사용"""
        job_id = job_step['job_id']
        step_id = job_step['step_id']
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}

        # 다운로드 방식 결정
        method = parameters.get('dataInputMethod', 'local')
        
        logger.info(f"[DOWNLOAD] Starting data download/copy using method: {method}")
        logger.info(f"[DOWNLOAD] Available tools: {list(self.tools.keys())}")

        try:
            # 자동 등록된 tool에서 적절한 함수 찾기
            tool_func = self.tools.get(method)
            if not tool_func:
                raise ValueError(f"Unsupported download method: {method}. Available: {list(self.tools.keys())}")
            
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
                error_msg = f"Download method '{method}' failed: {error_detail}"
                logger.error(f"❌ [DOWNLOAD] {error_msg}")
                raise Exception(error_msg)
            
            logger.info(f"✅ [DOWNLOAD] Download completed successfully using method: {method}")
            
        except Exception as e:
            error_msg = f"Critical download failure in method '{method}': {str(e)}"
            logger.error(f"🚨 [DOWNLOAD] {error_msg}")
            
            # 전체 파이프라인 중단을 위해 예외 재발생
            raise Exception(f"PIPELINE_CRITICAL_FAILURE: {error_msg}")

        return result
    

# 코디네이터 인스턴스 생성
_coordinator = DownloadCoordinator()

def REGISTER_COORDINATOR(job_worker):
    """🔌 자동 플러그인 등록 함수 - PipelineJobWorker에 코디네이터 등록"""
    logger.info(f"🔌 [PLUGIN-REG] Registering download coordinator...")
    return job_worker.register_step_handler('download', _coordinator.execute)