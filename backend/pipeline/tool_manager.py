"""
ToolManager - 전역 도구 관리자
모든 pipeline tools를 한 번만 로딩하여 워커들이 공유하도록 관리합니다.
"""

import os
import importlib
import sqlite3
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class ToolManager:
    """전역 도구 관리자 - 한 번만 로딩, 모든 워커가 공유"""
    
    def __init__(self):
        self.coordinators = {}
        self._load_all_coordinators()
        
    def _load_all_coordinators(self):
        """모든 코디네이터를 한 번에 로드"""
        logger.info("🔌 [TOOL-MANAGER] Loading all coordinators...")
        
        # tools 디렉토리 경로
        tools_path = Path(__file__).parent / "tools"
        
        if not tools_path.exists():
            logger.warning(f"⚠️ [TOOL-MANAGER] Tools directory not found: {tools_path}")
            return
        
        # 각 도구 디렉토리 스캔
        for step_dir in tools_path.iterdir():
            if step_dir.is_dir() and not step_dir.name.startswith('__'):
                try:
                    coordinator = self._load_coordinator(step_dir.name)
                    if coordinator:
                        self.coordinators[step_dir.name] = coordinator
                        logger.info(f"✅ [TOOL-MANAGER] Loaded coordinator: {step_dir.name}")
                except Exception as e:
                    logger.error(f"❌ [TOOL-MANAGER] Failed to load coordinator {step_dir.name}: {e}")
                    
        logger.info(f"🎉 [TOOL-MANAGER] Successfully loaded {len(self.coordinators)} coordinators")
        logger.info(f"📦 [TOOL-MANAGER] Available coordinators: {list(self.coordinators.keys())}")
    
    def _load_coordinator(self, step_name: str) -> Optional[Any]:
        """개별 코디네이터 로드"""
        try:
            # coordinator.py 모듈 import
            module_name = f"backend.pipeline.tools.{step_name}.coordinator"
            coordinator_module = importlib.import_module(module_name)
            
            # REGISTER_COORDINATOR 함수 찾기
            if hasattr(coordinator_module, 'REGISTER_COORDINATOR'):
                # Mock worker 객체 생성 (register_step_handler 메서드만 필요)
                mock_worker = MockWorker()
                
                # 코디네이터 등록
                register_func = coordinator_module.REGISTER_COORDINATOR
                coordinator_execute_func = register_func(mock_worker)
                
                logger.info(f"🔌 [TOOL-MANAGER] Registered coordinator for '{step_name}'")
                return coordinator_execute_func
            else:
                logger.warning(f"⚠️ [TOOL-MANAGER] No REGISTER_COORDINATOR found in {module_name}")
                return None
                
        except ImportError as e:
            logger.error(f"❌ [TOOL-MANAGER] Import failed for {step_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [TOOL-MANAGER] Unexpected error loading {step_name}: {e}")
            return None
    
    def get_coordinator(self, step_name: str) -> Any:
        """워커들이 코디네이터를 요청할 때 사용"""
        coordinator = self.coordinators.get(step_name)
        if not coordinator:
            raise ValueError(f"Coordinator '{step_name}' not found. Available: {list(self.coordinators.keys())}")
        return coordinator
    
    def execute_step(self, step_name: str, job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, Any]:
        """워커를 대신해서 단계 실행"""
        try:
            coordinator_func = self.get_coordinator(step_name)
            logger.info(f"🔧 [TOOL-MANAGER] Executing step '{step_name}' with worker '{worker_id}'")
            
            # 코디네이터 실행
            result = coordinator_func(job_step, worker_id)
            
            if hasattr(result, 'get'):
                # 딕셔너리인 경우
                success = result.get('success', True)
                error_msg = result.get('error', result.get('stderr', 'Unknown error'))
            else:
                # sqlite3.Row인 경우
                success = result['success'] if 'success' in result else True
                error_msg = result['error'] if 'error' in result else (result['stderr'] if 'stderr' in result else 'Unknown error')
                
            if success:
                logger.info(f"✅ [TOOL-MANAGER] Step '{step_name}' completed successfully")
            else:
                logger.error(f"❌ [TOOL-MANAGER] Step '{step_name}' failed: {error_msg}")
            
            return result
            
        except Exception as e:
            error_msg = f"Step '{step_name}' execution failed: {str(e)}"
            logger.error(f"💥 [TOOL-MANAGER] {error_msg}")
            
            return {
                'success': False,
                'error': error_msg,
                'step_name': step_name,
                'worker_id': worker_id
            }
    
    def get_available_coordinators(self) -> Dict[str, str]:
        """사용 가능한 코디네이터 목록 반환"""
        return {
            name: str(type(coordinator).__name__) 
            for name, coordinator in self.coordinators.items()
        }
    
    def reload_coordinator(self, step_name: str) -> bool:
        """특정 코디네이터를 다시 로드"""
        try:
            logger.info(f"🔄 [TOOL-MANAGER] Reloading coordinator: {step_name}")
            
            # 기존 코디네이터 제거
            if step_name in self.coordinators:
                del self.coordinators[step_name]
            
            # 모듈 캐시 제거
            module_name = f"backend.pipeline.tools.{step_name}.coordinator"
            if module_name in importlib.sys.modules:
                del importlib.sys.modules[module_name]
            
            # 다시 로드
            coordinator = self._load_coordinator(step_name)
            if coordinator:
                self.coordinators[step_name] = coordinator
                logger.info(f"✅ [TOOL-MANAGER] Successfully reloaded coordinator: {step_name}")
                return True
            else:
                logger.error(f"❌ [TOOL-MANAGER] Failed to reload coordinator: {step_name}")
                return False
                
        except Exception as e:
            logger.error(f"❌ [TOOL-MANAGER] Error reloading coordinator {step_name}: {e}")
            return False


class MockWorker:
    """코디네이터 등록을 위한 Mock Worker 클래스"""
    
    def __init__(self):
        self.step_handlers = {}
    
    def register_step_handler(self, step_name: str, handler_func: Any) -> Any:
        """코디네이터 등록 메서드"""
        self.step_handlers[step_name] = handler_func
        logger.debug(f"🔗 [MOCK-WORKER] Registered step handler: {step_name}")
        return handler_func


# 전역 인스턴스 생성용 함수 (필요시 사용)
_global_tool_manager = None

def get_global_tool_manager() -> ToolManager:
    """전역 ToolManager 인스턴스 반환 (싱글톤 패턴)"""
    global _global_tool_manager
    if _global_tool_manager is None:
        _global_tool_manager = ToolManager()
    return _global_tool_manager


def create_tool_manager() -> ToolManager:
    """새로운 ToolManager 인스턴스 생성"""
    return ToolManager()