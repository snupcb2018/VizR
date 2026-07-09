"""
Shared Worker State Management
워커들의 공유 상태 관리를 위한 멀티프로세싱 기반 시스템
SharedMemoryManager와 통합하여 프로세스 간 진짜 공유 상태 관리 지원
"""

import multiprocessing
import logging
import uuid
import time
import json
from typing import List, Dict, Any, Optional
from queue import Empty

# SharedMemoryManager 임포트
from .shared_memory_manager import SharedMemoryManager, get_shared_memory_manager

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'DEBUG')


class SharedWorkerState:
    """워커들의 공유 상태 관리 클래스 - 극한 단순화"""
    
    def __init__(self):
        """Shared Memory 기반 워커 상태 관리 초기화"""
        self.manager = multiprocessing.Manager()
        
        # 동기화를 위한 락
        self.lock = self.manager.Lock()
        
        # ✅ Event 기반 중단 시스템 {worker_id: Event}
        self.worker_events = self.manager.dict()
        
        # 워커별 실행 중인 프로세스 추적 {worker_id: [pid1, pid2, ...]}
        self.worker_processes = self.manager.dict()
        
        # 실시간 진행상황 저장 {worker_id: {task_type: progress_data}}
        self.progress_data = self.manager.dict()
        
        # ✅ SSE 클라이언트별 진행상황 큐 {client_id: Queue} (Manager 기반 유지)
        self.client_queues = self.manager.dict()
        
        # 🧠 SharedMemoryManager 통합 (SSE 클라이언트 및 진행률 관리용)
        self.shared_memory = get_shared_memory_manager()
        logger.info("🧠 [SHARED-STATE] SharedMemoryManager integration enabled")
        
        logger.info("🚀 [SHARED-STATE] Initialized shared worker state management with Event-based stop system and SSE support")
    
    def register_worker(self, worker_id: str):
        """워커 등록 시 Event 미리 생성"""
        if worker_id not in self.worker_events:
            self.worker_events[worker_id] = self.manager.Event()
            logger.info(f"📝 [SHARED-STATE] Registered worker with Event: {worker_id}")
        else:
            logger.warning(f"⚠️ [SHARED-STATE] Worker {worker_id} already registered")
    
    def unregister_worker(self, worker_id: str):
        """워커 등록 해제 및 Event 정리"""
        if worker_id in self.worker_events:
            del self.worker_events[worker_id]
            logger.info(f"🗑️ [SHARED-STATE] Unregistered worker and cleaned Event: {worker_id}")
        else:
            logger.warning(f"⚠️ [SHARED-STATE] Worker {worker_id} not found for unregistration")
    
    def get_worker_event(self, worker_id: str):
        """worker_id에 해당하는 Event 가져오기 (미리 생성되어 있어야 함)"""
        if worker_id not in self.worker_events:
            raise ValueError(f"Worker {worker_id} not registered! Call register_worker() first.")
        return self.worker_events[worker_id]
    
    def set_worker_stop(self, worker_id: str):
        """특정 워커에 stop 신호 전송"""
        try:
            event = self.get_worker_event(worker_id)
            event.set()
            logger.warning(f"🛑 [SHARED-STATE] Stop signal sent to worker: {worker_id}")
        except ValueError as e:
            logger.error(f"❌ [SHARED-STATE] Failed to stop worker: {e}")
    
    def reset_worker(self, worker_id: str):
        """워커 이벤트 초기화 (ready 상태로 복구)"""
        try:
            event = self.get_worker_event(worker_id)
            event.clear()
            logger.info(f"🔄 [SHARED-STATE] Reset worker to ready state: {worker_id}")
        except ValueError as e:
            logger.error(f"❌ [SHARED-STATE] Failed to reset worker: {e}")
    
    def is_worker_stopped(self, worker_id: str) -> bool:
        """워커가 중단 상태인지 확인"""
        try:
            event = self.get_worker_event(worker_id)
            return event.is_set()
        except ValueError:
            return False
    
    def get_registered_workers(self) -> List[str]:
        """등록된 모든 워커들 목록"""
        return list(self.worker_events.keys())
    
    def get_stopped_workers(self) -> List[str]:
        """중단 상태인 워커들 목록"""
        return [worker_id for worker_id in self.worker_events.keys() if self.is_worker_stopped(worker_id)]
    
    def set_current_process(self, worker_id: str, pid: int):
        """워커의 현재 실행 중인 프로세스 PID 등록"""
        with self.lock:
            if worker_id not in self.worker_processes:
                self.worker_processes[worker_id] = []
            
            # PID 추가 (중복 방지)
            process_list = list(self.worker_processes[worker_id])
            if pid not in process_list:
                process_list.append(pid)
                self.worker_processes[worker_id] = process_list
                logger.debug(f"📝 [SHARED-STATE] Registered process PID {pid} for worker {worker_id}")
    
    def remove_current_process(self, worker_id: str, pid: int):
        """워커의 완료된 프로세스 PID 제거"""
        with self.lock:
            if worker_id in self.worker_processes:
                process_list = list(self.worker_processes[worker_id])
                if pid in process_list:
                    process_list.remove(pid)
                    self.worker_processes[worker_id] = process_list
                    logger.debug(f"🗑️ [SHARED-STATE] Removed process PID {pid} for worker {worker_id}")
    
    def get_worker_processes(self, worker_id: str) -> List[int]:
        """워커의 실행 중인 프로세스들 목록"""
        return list(self.worker_processes.get(worker_id, []))
    
    def cleanup(self):
        """Shared Memory 정리"""
        logger.info("🧹 [SHARED-STATE] Cleaning up shared memory...")
        self.worker_events.clear()
        self.worker_processes.clear()
        logger.info("✅ [SHARED-STATE] Cleanup completed")
    
    def send_progress_update(self, worker_id: str, task_type: str, progress_data: dict):
        """실시간 진행상황 업데이트 전송 (SharedMemoryManager와 Manager 병행 사용)"""
        try:
            # 🧠 SharedMemoryManager에 진행률 저장 (프로세스 간 공유)
            success = self.shared_memory.store_progress_data(worker_id, task_type, progress_data)
            
            if success:
                logger.debug(f"📊 [SHARED-STATE] Progress stored in SharedMemory - Worker: {worker_id}, Task: {task_type}")
            else:
                logger.warning(f"⚠️ [SHARED-STATE] Failed to store progress in SharedMemory - Worker: {worker_id}, Task: {task_type}")
            
            # Manager 기반 저장도 유지 (기존 호환성)
            with self.lock:
                # 워커별 진행상황 데이터 초기화
                if worker_id not in self.progress_data:
                    self.progress_data[worker_id] = self.manager.dict()
                
                worker_progress = self.progress_data[worker_id]
                
                # task_type별 진행상황 업데이트
                if task_type not in worker_progress:
                    worker_progress[task_type] = self.manager.dict()
                
                # 진행상황 데이터 저장
                task_progress = worker_progress[task_type]
                for key, value in progress_data.items():
                    task_progress[key] = value
                
                logger.debug(f"📊 [SHARED-STATE] Progress update - Worker: {worker_id}, Task: {task_type}")
                
        except Exception as e:
            logger.error(f"❌ [SHARED-STATE] Failed to send progress update: {e}")
    
    def get_progress_data(self, worker_id: str, task_type: str = None) -> dict:
        """워커의 진행상황 데이터 조회"""
        try:
            with self.lock:
                if worker_id not in self.progress_data:
                    return {}
                
                worker_progress = dict(self.progress_data[worker_id])
                
                if task_type:
                    # 특정 task_type의 진행상황만 반환
                    return dict(worker_progress.get(task_type, {}))
                else:
                    # 모든 진행상황 반환
                    result = {}
                    for task_type, progress in worker_progress.items():
                        result[task_type] = dict(progress)
                    return result
                    
        except Exception as e:
            logger.error(f"❌ [SHARED-STATE] Failed to get progress data: {e}")
            return {}
    
    def get_all_progress_data(self) -> dict:
        """모든 워커의 진행상황 데이터 조회"""
        try:
            with self.lock:
                result = {}
                for worker_id, worker_progress in self.progress_data.items():
                    result[worker_id] = {}
                    for task_type, progress in worker_progress.items():
                        result[worker_id][task_type] = dict(progress)
                return result
                
        except Exception as e:
            logger.error(f"❌ [SHARED-STATE] Failed to get all progress data: {e}")
            return {}
    
    def clear_progress_data(self, worker_id: str, task_type: str = None):
        """워커의 진행상황 데이터 정리"""
        try:
            with self.lock:
                if worker_id not in self.progress_data:
                    return
                
                if task_type:
                    # 특정 task_type만 정리
                    worker_progress = self.progress_data[worker_id]
                    if task_type in worker_progress:
                        del worker_progress[task_type]
                        logger.debug(f"🧹 [SHARED-STATE] Cleared progress data - Worker: {worker_id}, Task: {task_type}")
                else:
                    # 워커의 모든 진행상황 정리
                    del self.progress_data[worker_id]
                    logger.debug(f"🧹 [SHARED-STATE] Cleared all progress data for worker: {worker_id}")
                    
        except Exception as e:
            logger.error(f"❌ [SHARED-STATE] Failed to clear progress data: {e}")

    # ===============================
    # SSE 클라이언트 관리 메서드들
    # ===============================
    
    def register_sse_client(self, workbench_id: int, task_type: str) -> Optional[str]:
        """SSE 클라이언트 등록 및 고유 ID 반환 (SharedMemoryManager 사용)"""
        # 🧠 SharedMemoryManager를 통한 프로세스 간 공유 등록
        client_id = self.shared_memory.register_sse_client(workbench_id, task_type)
        
        if client_id:
            # 클라이언트 전용 큐는 Manager에서 생성 (큐는 SharedMemory로 공유하기 어려움)
            with self.lock:
                self.client_queues[client_id] = self.manager.Queue()
            logger.info(f"🧠 [SHARED-STATE] SSE client registered via SharedMemory: {client_id}")
        else:
            logger.error("❌ [SHARED-STATE] Failed to register SSE client via SharedMemory")
        
        return client_id
    
    def unregister_sse_client(self, client_id: str):
        """SSE 클라이언트 등록 해제 (SharedMemoryManager 사용)"""
        # 🧠 SharedMemoryManager에서 클라이언트 정보 제거
        success = self.shared_memory.unregister_sse_client(client_id)
        
        # Manager 기반 큐 정리
        with self.lock:
            try:
                if client_id in self.client_queues:
                    queue = self.client_queues[client_id]
                    try:
                        while not queue.empty():
                            queue.get_nowait()
                    except:
                        pass
                    del self.client_queues[client_id]
                
                if success:
                    logger.info(f"🧠 [SHARED-STATE] SSE client unregistered via SharedMemory: {client_id}")
                else:
                    logger.warning(f"⚠️ [SHARED-STATE] Failed to unregister SSE client: {client_id}")
                
            except Exception as e:
                logger.error(f"❌ [SHARED-STATE] Error during SSE client cleanup: {e}")
    
    def broadcast_progress_to_sse(self, workbench_id: int, task_type: str, progress_data: Dict[str, Any], custom_logger=None):
        """해당 워크벤치와 태스크 타입의 SSE 클라이언트들에게 진행상황 브로드캐스트 (SharedMemoryManager 사용)"""
        
        # 사용할 logger 결정
        active_logger = custom_logger if custom_logger is not None else logger
        
        # 🔍 함수 진입점 로그 (파일과 콘솔 모두)
        active_logger.info(f"🚀 [BROADCAST-ENTRY] Function called with workbench_id={workbench_id}, task_type={task_type}")
        print(f"🚀 [BROADCAST-ENTRY] Function called with workbench_id={workbench_id}, task_type={task_type}")
        
        try:
            # 🧠 SharedMemoryManager에서 매칭되는 클라이언트들 조회
            matching_clients = self.shared_memory.get_sse_clients(workbench_id, task_type)
            
            # 모든 SSE 클라이언트 정보 조회
            all_clients = self.shared_memory.get_all_sse_clients()
            active_logger.info(f"🔍 [SSE-CLIENTS] Total clients in SharedMemory: {len(all_clients)}, clients: {list(all_clients.keys())}")
            
            active_logger.info(f"📡 [MATCH-RESULT] Found {len(matching_clients)} matching clients via SharedMemory: {matching_clients}")
            
            if not matching_clients:
                active_logger.info(f"📡 [SHARED-STATE] No SSE clients found in SharedMemory for workbench={workbench_id}, task={task_type}")
                return
            
            # 진행상황 데이터 준비
            sse_message = {
                'event': 'progress_update',
                'workbench_id': workbench_id,
                'task_type': task_type,
                'data': progress_data,
                'timestamp': time.time()
            }
            
            # 🔍 SSE 브로드캐스트 디버그 로그
            active_logger.info(f"📡 [SHARED-STATE-DEBUG] Broadcasting SSE message: {sse_message}")
            active_logger.info(f"📡 [SHARED-STATE-DEBUG] Matching clients: {matching_clients}")
            
            # 매칭되는 클라이언트들에게 브로드캐스트 (큐는 여전히 Manager 기반)
            for client_id in matching_clients:
                try:
                    if client_id in self.client_queues:
                        self.client_queues[client_id].put(sse_message)
                        active_logger.debug(f"📡 [SHARED-STATE] Progress broadcasted to SSE client: {client_id}")
                    else:
                        active_logger.warning(f"⚠️ [SHARED-STATE] Client queue not found: {client_id}")
                except Exception as e:
                    active_logger.warning(f"⚠️ [SHARED-STATE] Failed to send to SSE client {client_id}: {e}")
            
            active_logger.debug(f"📡 [SHARED-STATE] Progress broadcasted to {len(matching_clients)} SSE clients")
            
        except Exception as e:
            error_msg = f"❌ [SHARED-STATE] Failed to broadcast progress to SSE: {e}"
            active_logger.error(error_msg)
    
    def get_sse_client_queue(self, client_id: str):
        """SSE 클라이언트의 진행상황 큐 반환"""
        return self.client_queues.get(client_id)
    
    def get_sse_clients_count(self, workbench_id: int = None, task_type: str = None) -> int:
        """SSE 클라이언트 수 조회 (SharedMemoryManager 사용)"""
        if workbench_id is None and task_type is None:
            # 전체 클라이언트 수
            all_clients = self.shared_memory.get_all_sse_clients()
            return len(all_clients)
        
        # 특정 조건의 클라이언트들만 계산
        all_clients = self.shared_memory.get_all_sse_clients()
        count = 0
        for client_info in all_clients.values():
            if ((workbench_id is None or client_info.get('workbench_id') == workbench_id) and
                (task_type is None or client_info.get('task_type') == task_type)):
                count += 1
        
        return count

    def __repr__(self):
        """디버깅용 문자열 표현"""
        registered_count = len(self.get_registered_workers())
        stopped_count = len(self.get_stopped_workers())
        ready_count = registered_count - stopped_count
        progress_count = len(self.progress_data)
        return f"SharedWorkerState(registered={registered_count}, ready={ready_count}, stopped={stopped_count}, progress_workers={progress_count})"


# 전역 인스턴스 생성
shared_state = SharedWorkerState()


def get_shared_state() -> SharedWorkerState:
    """전역 shared_state 인스턴스 반환"""
    return shared_state


# 정리 함수 (프로그램 종료 시 호출)
def cleanup_shared_state():
    """프로그램 종료 시 Shared Memory 정리"""
    shared_state.cleanup()


# 모듈 로드 시 정보 출력
logger.info("📦 [SHARED-STATE] Shared worker state module loaded")