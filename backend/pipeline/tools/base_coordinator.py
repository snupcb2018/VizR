"""
Base Coordinator Class
모든 코디네이터의 베이스 클래스 - 자동 tool 등록 시스템 제공
🚀 Auto Plugin System Integration
"""

import importlib.util
import sys
import logging
from pathlib import Path
from typing import Dict, Callable, List, Optional
from abc import ABC, abstractmethod

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class BaseCoordinator(ABC):
    """모든 코디네이터의 베이스 클래스"""
    
    def __init__(self, coordinator_name: str):
        self.coordinator_name = coordinator_name
        self.tools = {}  # tool_name -> execute_function 매핑
        self.tool_metadata = {}  # tool_name -> metadata 매핑
        
        # 자동 tool 등록 실행
        self._auto_register_tools()
    
    def _auto_register_tools(self):
        """현재 코디네이터 디렉토리의 tool들 자동 스캔 및 등록"""
        # 코디네이터가 위치한 디렉토리의 plugins 폴더 경로
        coordinator_dir = Path(sys.modules[self.__module__].__file__).parent
        plugins_dir = coordinator_dir / "plugins"
        
        logger.info(f"🔍 [TOOL-SCAN-{self.coordinator_name.upper()}] Scanning tools in: {plugins_dir}")
        
        if not plugins_dir.exists():
            logger.warning(f"⚠️ [TOOL-SCAN-{self.coordinator_name.upper()}] Plugins directory not found: {plugins_dir}")
            return
        
        loaded_count = 0
        for tool_file in plugins_dir.glob("*.py"):
            # __init__.py는 제외 (plugins 폴더 내의 모든 .py 파일이 도구)
            if tool_file.name not in ['__init__.py']:
                tool_name = tool_file.stem  # 파일명에서 확장자 제거
                success = self._load_tool(tool_name, tool_file)
                if success:
                    loaded_count += 1
        
        logger.info(f"📊 [TOOL-SCAN-{self.coordinator_name.upper()}] Scan completed: {loaded_count} tools loaded")
    
    def _load_tool(self, tool_name: str, tool_file: Path) -> bool:
        """개별 tool 로드 및 등록"""
        try:
            logger.info(f"  🔄 [TOOL-LOAD-{self.coordinator_name.upper()}] Loading tool: {tool_name}")
            logger.info(f"     📁 File: {tool_file}")
            
            # plugins 폴더의 모듈 로드
            module_name = f"backend.pipeline.tools.{self.coordinator_name}.plugins.{tool_name}"
            
            # 기존 모듈이 이미 로드되어 있으면 사용
            if module_name in sys.modules:
                module = sys.modules[module_name]
                logger.info(f"     ♻️ Using cached module: {module_name}")
            else:
                # 새로운 모듈 로드
                spec = importlib.util.spec_from_file_location(module_name, tool_file)
                module = importlib.util.module_from_spec(spec)
                
                # sys.modules에 등록 (상대 import 지원을 위해)
                sys.modules[module_name] = module
                
                # 모듈 실행
                spec.loader.exec_module(module)
            
            # REGISTER_TOOL 함수 확인 및 호출
            if hasattr(module, 'REGISTER_TOOL'):
                logger.info(f"     ✅ Found REGISTER_TOOL function")
                tool_func = module.REGISTER_TOOL(self)
                
                # tools에 등록 검증
                if tool_name in self.tools:
                    logger.info(f"  ✅ [TOOL-LOAD-{self.coordinator_name.upper()}] Successfully registered: {tool_name}")
                    return True
                else:
                    logger.error(f"  ❌ [TOOL-LOAD-{self.coordinator_name.upper()}] Registration failed: {tool_name} not in tools")
                    return False
            else:
                logger.warning(f"  ⚠️ [TOOL-LOAD-{self.coordinator_name.upper()}] No REGISTER_TOOL found in {tool_name}")
                return False
                
        except Exception as e:
            logger.error(f"  ❌ [TOOL-LOAD-{self.coordinator_name.upper()}] Failed to load {tool_name}: {e}")
            import traceback
            logger.error(f"     📋 Traceback: {traceback.format_exc()}")
            return False
    
    def register_tool(self, tool_name: str, execute_func: Callable, metadata: Optional[Dict] = None) -> Callable:
        """Tool 등록용 메서드 (REGISTER_TOOL에서 호출)"""
        logger.info(f"     📝 Registering tool: {tool_name}")
        self.tools[tool_name] = execute_func
        
        # 메타데이터 저장
        if metadata:
            self.tool_metadata[tool_name] = metadata
        
        return execute_func
    
    def get_available_tools(self) -> List[str]:
        """사용 가능한 도구 목록 반환"""
        return list(self.tools.keys())
    
    def get_tool_metadata(self, tool_name: str) -> Optional[Dict]:
        """도구 메타데이터 반환"""
        return self.tool_metadata.get(tool_name)
    
    @abstractmethod
    def execute(self, job_step, worker_id: str = "worker"):
        """코디네이터 실행 로직 - 각 코디네이터에서 구현해야 함"""
        pass
    
    def _select_tool(self, parameters: Dict, default_tool: Optional[str] = None) -> Optional[str]:
        """파라미터를 기반으로 적절한 도구 선택"""
        # 기본 구현 - 하위 클래스에서 오버라이드 가능
        available_tools = list(self.tools.keys())
        
        if not available_tools:
            return None
        
        # 첫 번째 도구를 기본으로 사용
        return default_tool if default_tool in available_tools else available_tools[0]