"""
SharedMemoryManager - 프로세스 간 공유 메모리 관리
윈도우와 리눅스 환경을 모두 지원하는 SharedMemory 기반 상태 관리 시스템
"""

import multiprocessing
import multiprocessing.shared_memory as shm
import json
import threading
import uuid
import time
import logging
import os
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class SharedMemoryManager:
    """프로세스 간 진짜 공유되는 상태 관리자"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, name: str = "vizr_shared_state", size_mb: int = 2):
        """
        SharedMemoryManager 초기화

        Args:
            name: 공유 메모리 이름
            size_mb: 공유 메모리 크기 (MB)
        """
        self.shm_name = name
        self.shm_size = size_mb * 1024 * 1024  # MB to bytes
        self.shm = None
        self.local_lock = threading.Lock()
        self.process_lock = None
        self._initialized = False

        logger.info(f"🧠 [SHARED-MEMORY] Initializing SharedMemoryManager: {self.shm_name} ({size_mb}MB)")

    @classmethod
    def get_instance(cls, name: str = "vizr_shared_state", size_mb: int = 2):
        """
        싱글톤 패턴으로 SharedMemoryManager 인스턴스 반환

        SSE 클라이언트 및 진행률 관리용 전역 싱글톤 인스턴스.
        ProcessWrapper에서 멀티프로세싱 작업 시에는 create_temporary() 사용.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(name, size_mb)
                    cls._instance._initialize()
        return cls._instance

    @classmethod
    def create_temporary(cls, size_mb: int = 2):
        """
        임시 공유 메모리 인스턴스 생성 (멀티프로세싱 워커용)

        고유한 UUID 기반 이름으로 생성되며, 사용 후 반드시 cleanup() 호출 필요.
        컨텍스트 매니저와 함께 사용 권장.

        Returns:
            SharedMemoryManager: 고유 이름을 가진 임시 인스턴스
        """
        temp_name = f"vizr_temp_{uuid.uuid4().hex[:12]}"
        instance = cls(temp_name, size_mb)
        instance._initialize()
        logger.info(f"🔧 [SHARED-MEMORY] Created temporary instance: {temp_name}")
        return instance
    
    def _initialize(self):
        """공유 메모리 초기화 또는 기존 메모리에 연결"""
        if self._initialized:
            return
            
        try:
            # 기존 공유 메모리에 연결 시도
            self.shm = shm.SharedMemory(name=self.shm_name)
            logger.info(f"📡 [SHARED-MEMORY] Connected to existing shared memory: {self.shm_name}")
            
        except FileNotFoundError:
            try:
                # 새로운 공유 메모리 생성
                self.shm = shm.SharedMemory(
                    name=self.shm_name, 
                    create=True, 
                    size=self.shm_size
                )
                
                # 초기 데이터 구조 설정
                initial_data = {
                    'sse_clients': {},
                    'worker_events': {},
                    'progress_data': {},
                    'metadata': {
                        'created_at': time.time(),
                        'version': '1.0.0',
                        'process_id': os.getpid()
                    }
                }
                
                self._write_data(initial_data)
                logger.info(f"✨ [SHARED-MEMORY] Created new shared memory: {self.shm_name}")
                
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Failed to create shared memory: {e}")
                raise
        
        except Exception as e:
            logger.error(f"❌ [SHARED-MEMORY] Failed to initialize shared memory: {e}")
            raise
        
        # 프로세스 간 락 초기화 (multiprocessing.Lock 사용)
        try:
            self.process_lock = multiprocessing.Lock()
        except Exception as e:
            logger.warning(f"⚠️ [SHARED-MEMORY] Failed to create process lock, using thread lock: {e}")
            self.process_lock = threading.Lock()
        
        self._initialized = True
        logger.info("🚀 [SHARED-MEMORY] SharedMemoryManager initialized successfully")
    
    @contextmanager
    def _safe_access(self):
        """안전한 공유 메모리 접근을 위한 컨텍스트 매니저"""
        if not self._initialized:
            self._initialize()
        
        # 프로세스 락과 스레드 락 모두 사용
        with self.process_lock:
            with self.local_lock:
                try:
                    yield
                except Exception as e:
                    logger.error(f"❌ [SHARED-MEMORY] Error during safe access: {e}")
                    raise
    
    def _read_data(self) -> Dict[str, Any]:
        """공유 메모리에서 데이터 읽기"""
        try:
            if not self.shm:
                logger.warning("⚠️ [SHARED-MEMORY] SharedMemory not initialized")
                return {}
            
            # 메모리에서 데이터 읽기
            data_bytes = bytes(self.shm.buf[:self.shm_size])
            
            # null 바이트 제거
            data_str = data_bytes.decode('utf-8', errors='ignore').rstrip('\x00')
            
            if not data_str:
                logger.debug("📄 [SHARED-MEMORY] Empty data in shared memory")
                return {}
            
            # JSON 파싱
            data = json.loads(data_str)
            logger.debug(f"📖 [SHARED-MEMORY] Read data from shared memory: {len(data)} keys")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ [SHARED-MEMORY] JSON decode error: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ [SHARED-MEMORY] Error reading data: {e}")
            return {}
    
    def _write_data(self, data: Dict[str, Any]):
        """공유 메모리에 데이터 쓰기"""
        try:
            if not self.shm:
                logger.error("❌ [SHARED-MEMORY] SharedMemory not initialized for writing")
                return False
            
            # JSON 직렬화
            data_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            data_bytes = data_str.encode('utf-8')
            
            # 크기 검증
            if len(data_bytes) > self.shm_size:
                logger.error(f"❌ [SHARED-MEMORY] Data too large: {len(data_bytes)} bytes > {self.shm_size} bytes")
                raise ValueError(f"Data too large for shared memory: {len(data_bytes)} > {self.shm_size}")
            
            # 버퍼 초기화 후 데이터 쓰기
            self.shm.buf[:len(data_bytes)] = data_bytes
            if len(data_bytes) < self.shm_size:
                self.shm.buf[len(data_bytes):] = b'\x00' * (self.shm_size - len(data_bytes))
            
            logger.debug(f"📝 [SHARED-MEMORY] Wrote data to shared memory: {len(data_bytes)} bytes")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SHARED-MEMORY] Error writing data: {e}")
            return False
    
    def register_sse_client(self, workbench_id: int, task_type: str) -> Optional[str]:
        """SSE 클라이언트 등록"""
        with self._safe_access():
            try:
                client_id = f"sse_{workbench_id}_{task_type}_{uuid.uuid4().hex[:8]}"
                
                data = self._read_data()
                if 'sse_clients' not in data:
                    data['sse_clients'] = {}
                
                data['sse_clients'][client_id] = {
                    'workbench_id': workbench_id,
                    'task_type': task_type,
                    'timestamp': time.time(),
                    'process_id': os.getpid()
                }
                
                success = self._write_data(data)
                if success:
                    logger.info(f"📡 [SHARED-MEMORY] Registered SSE client: {client_id} (workbench={workbench_id}, task={task_type})")
                    return client_id
                else:
                    logger.error(f"❌ [SHARED-MEMORY] Failed to write SSE client data: {client_id}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Error registering SSE client: {e}")
                return None
    
    def unregister_sse_client(self, client_id: str) -> bool:
        """SSE 클라이언트 등록 해제"""
        with self._safe_access():
            try:
                data = self._read_data()
                if 'sse_clients' not in data:
                    data['sse_clients'] = {}
                
                if client_id in data['sse_clients']:
                    del data['sse_clients'][client_id]
                    success = self._write_data(data)
                    
                    if success:
                        logger.info(f"📡 [SHARED-MEMORY] Unregistered SSE client: {client_id}")
                        return True
                    else:
                        logger.error(f"❌ [SHARED-MEMORY] Failed to write after unregistering: {client_id}")
                        return False
                else:
                    logger.warning(f"⚠️ [SHARED-MEMORY] SSE client not found for unregistration: {client_id}")
                    return True  # 이미 없으므로 성공으로 처리
                    
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Error unregistering SSE client: {e}")
                return False
    
    def get_sse_clients(self, workbench_id: int, task_type: str) -> List[str]:
        """특정 워크벤치/태스크의 SSE 클라이언트 조회"""
        with self._safe_access():
            try:
                data = self._read_data()
                clients = []
                
                for client_id, info in data.get('sse_clients', {}).items():
                    if (info.get('workbench_id') == workbench_id and 
                        info.get('task_type') == task_type):
                        clients.append(client_id)
                
                logger.debug(f"🔍 [SHARED-MEMORY] Found {len(clients)} SSE clients for workbench={workbench_id}, task={task_type}")
                return clients
                
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Error getting SSE clients: {e}")
                return []
    
    def get_all_sse_clients(self) -> Dict[str, Dict[str, Any]]:
        """모든 SSE 클라이언트 정보 조회"""
        with self._safe_access():
            try:
                data = self._read_data()
                return data.get('sse_clients', {})
                
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Error getting all SSE clients: {e}")
                return {}
    
    def store_progress_data(self, worker_id: str, task_type: str, progress_data: Dict[str, Any]) -> bool:
        """워커의 진행률 데이터 저장"""
        with self._safe_access():
            try:
                data = self._read_data()
                if 'progress_data' not in data:
                    data['progress_data'] = {}
                
                if worker_id not in data['progress_data']:
                    data['progress_data'][worker_id] = {}
                
                data['progress_data'][worker_id][task_type] = {
                    **progress_data,
                    'timestamp': time.time(),
                    'process_id': os.getpid()
                }
                
                success = self._write_data(data)
                if success:
                    logger.debug(f"📊 [SHARED-MEMORY] Stored progress data: worker={worker_id}, task={task_type}")
                    return True
                else:
                    logger.error(f"❌ [SHARED-MEMORY] Failed to store progress data: worker={worker_id}")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Error storing progress data: {e}")
                return False
    
    def get_progress_data(self, worker_id: str = None, task_type: str = None) -> Dict[str, Any]:
        """진행률 데이터 조회"""
        with self._safe_access():
            try:
                data = self._read_data()
                progress_data = data.get('progress_data', {})
                
                if worker_id is None:
                    # 모든 워커의 진행률 반환
                    return progress_data
                
                worker_progress = progress_data.get(worker_id, {})
                
                if task_type is None:
                    # 특정 워커의 모든 태스크 진행률 반환
                    return worker_progress
                
                # 특정 워커의 특정 태스크 진행률 반환
                return worker_progress.get(task_type, {})
                
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Error getting progress data: {e}")
                return {}
    
    def cleanup_old_data(self, max_age_seconds: int = 3600):
        """오래된 데이터 정리 (1시간 기본)"""
        with self._safe_access():
            try:
                data = self._read_data()
                current_time = time.time()
                cleaned = False
                
                # 오래된 SSE 클라이언트 정리
                if 'sse_clients' in data:
                    old_clients = []
                    for client_id, info in data['sse_clients'].items():
                        if current_time - info.get('timestamp', 0) > max_age_seconds:
                            old_clients.append(client_id)
                    
                    for client_id in old_clients:
                        del data['sse_clients'][client_id]
                        cleaned = True
                        logger.debug(f"🧹 [SHARED-MEMORY] Cleaned old SSE client: {client_id}")
                
                # 오래된 진행률 데이터 정리
                if 'progress_data' in data:
                    for worker_id in list(data['progress_data'].keys()):
                        worker_data = data['progress_data'][worker_id]
                        old_tasks = []
                        
                        for task_type, task_data in worker_data.items():
                            if current_time - task_data.get('timestamp', 0) > max_age_seconds:
                                old_tasks.append(task_type)
                        
                        for task_type in old_tasks:
                            del data['progress_data'][worker_id][task_type]
                            cleaned = True
                            logger.debug(f"🧹 [SHARED-MEMORY] Cleaned old progress data: {worker_id}/{task_type}")
                        
                        # 워커의 모든 데이터가 정리된 경우
                        if not data['progress_data'][worker_id]:
                            del data['progress_data'][worker_id]
                            logger.debug(f"🧹 [SHARED-MEMORY] Cleaned empty worker: {worker_id}")
                
                if cleaned:
                    self._write_data(data)
                    logger.info("🧹 [SHARED-MEMORY] Completed data cleanup")
                
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Error during cleanup: {e}")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """메모리 사용 통계 조회"""
        with self._safe_access():
            try:
                data = self._read_data()
                data_str = json.dumps(data, ensure_ascii=False)
                used_bytes = len(data_str.encode('utf-8'))
                
                stats = {
                    'total_size': self.shm_size,
                    'used_size': used_bytes,
                    'free_size': self.shm_size - used_bytes,
                    'usage_percent': (used_bytes / self.shm_size) * 100,
                    'sse_clients_count': len(data.get('sse_clients', {})),
                    'progress_workers_count': len(data.get('progress_data', {}))
                }
                
                return stats
                
            except Exception as e:
                logger.error(f"❌ [SHARED-MEMORY] Error getting memory stats: {e}")
                return {}
    
    def cleanup(self):
        """공유 메모리 정리"""
        try:
            if self.shm:
                logger.info(f"🧹 [SHARED-MEMORY] Cleaning up shared memory: {self.shm_name}")
                self.shm.close()

                try:
                    # 마지막 프로세스가 unlink (다른 프로세스가 사용 중이면 실패)
                    self.shm.unlink()
                    logger.info(f"✅ [SHARED-MEMORY] Shared memory unlinked: {self.shm_name}")
                except FileNotFoundError:
                    logger.debug(f"🔍 [SHARED-MEMORY] Shared memory already unlinked: {self.shm_name}")
                except Exception as e:
                    logger.warning(f"⚠️ [SHARED-MEMORY] Failed to unlink shared memory {self.shm_name}: {e}")

                self.shm = None
                self._initialized = False

        except Exception as e:
            logger.error(f"❌ [SHARED-MEMORY] Error during cleanup of {self.shm_name}: {e}")

    def __enter__(self):
        """컨텍스트 매니저 진입 (with 문 지원)"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료 - 자동 정리"""
        self.cleanup()
        return False

    def __del__(self):
        """소멸자 - 자동 정리 (임시 인스턴스용)"""
        # 싱글톤 인스턴스는 프로그램 종료 시까지 유지
        if self.shm_name.startswith("vizr_temp_"):
            self.cleanup()

    def __repr__(self):
        """디버깅용 문자열 표현"""
        if not self._initialized:
            return f"SharedMemoryManager(name={self.shm_name}, status=not_initialized)"

        try:
            stats = self.get_memory_stats()
            return (f"SharedMemoryManager(name={self.shm_name}, "
                   f"usage={stats.get('usage_percent', 0):.1f}%, "
                   f"clients={stats.get('sse_clients_count', 0)}, "
                   f"workers={stats.get('progress_workers_count', 0)})")
        except:
            return f"SharedMemoryManager(name={self.shm_name}, status=error)"


# 전역 인스턴스 (지연 초기화)
_shared_memory_manager = None

def get_shared_memory_manager() -> SharedMemoryManager:
    """전역 SharedMemoryManager 인스턴스 반환"""
    global _shared_memory_manager
    if _shared_memory_manager is None:
        _shared_memory_manager = SharedMemoryManager.get_instance()
    return _shared_memory_manager

def cleanup_shared_memory():
    """전역 SharedMemoryManager 정리"""
    global _shared_memory_manager
    if _shared_memory_manager:
        _shared_memory_manager.cleanup()
        _shared_memory_manager = None

# 모듈 로드 시 정보
logger.info("📦 [SHARED-MEMORY] SharedMemoryManager module loaded")