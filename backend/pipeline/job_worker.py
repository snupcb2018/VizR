#!/usr/bin/env python3
"""
Pipeline Job Worker
파이프라인 Job 스텝을 실제로 실행하는 워커
"""

import json
import sqlite3
import subprocess
import os
import shutil
import psutil
import time
import threading
import glob
import signal
import sys
import importlib
import importlib.util
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from pathlib import Path
import logging
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from config.backend_settings import BackendConfig as Config
from backend.utils.files import decompress_gzip_files, cleanup_temp_files, compress_gzip_files, cleanup_uncompressed_raw_data
from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema

# ✅ Shared Memory 시스템 import
from .utils.shared_state import shared_state

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'DEBUG')
JOB_WORKER_GSEA_MARKER = "JOB_WORKER_GSEA_QUEUE_FIX_V2026_03_14_01"



class PipelineJobWorker:
    def __init__(self, worker_id: str = "worker_1", tool_manager=None, db_path: str = 'vizr.db'):
        self.worker_id = worker_id
        self.db_path = db_path
        self.kst = timezone(timedelta(hours=9))
        self.running = False
        self.current_job = None
        self.resource_monitor = None
        self._job_lock = None  # Job 큐 접근 동기화를 위한 락 (외부에서 설정됨)
        self._shutdown_event = None  # 외부 shutdown 이벤트 (매니저에서 설정)
        
        # psutil 기반 프로세스 관리
        self.worker_process = psutil.Process()
        self.should_stop = False  # ✅ 로컬 플래그 유지 (호환성용)
        self.cleanup_functions = []  # 정리 함수들 등록용
        
        # ToolManager 인스턴스 할당
        if tool_manager is None:
            # 기본값으로 새 ToolManager 생성 (권장하지 않음, 경고 출력)
            logger.warning(f"⚠️ [WORKER-{worker_id}] No ToolManager provided, creating new instance (not recommended)")
            from .tool_manager import ToolManager
            self.tool_manager = ToolManager()
        else:
            self.tool_manager = tool_manager
            
        logger.info(f"🚀 [WORKER-{worker_id}] Initialized with ToolManager")
        logger.info(f"📦 [WORKER-{worker_id}] Available tools: {list(self.tool_manager.coordinators.keys())}")
    
    def get_db_connection(self):
        """데이터베이스 연결"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_system_setting(self, key: str, default_value: str = None) -> str:
        """시스템 설정 값 조회"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            return result['value'] if result else default_value
        finally:
            conn.close()
    
    def get_concurrent_jobs_count(self, tool_name: str) -> int:
        """특정 tool의 concurrent jobs 수 조회"""
        setting_key = f"{tool_name}_concurrent_jobs"
        default_key = "default_concurrent_jobs"
        
        # 해당 tool 전용 설정 조회
        concurrent_count = self.get_system_setting(setting_key)
        
        # 없으면 기본값 사용
        if not concurrent_count:
            concurrent_count = self.get_system_setting(default_key, "2")
        
        try:
            return int(concurrent_count)
        except (ValueError, TypeError):
            logger.warning(f"Invalid concurrent_jobs value: {concurrent_count}, using default: 2")
            return 2
    
    def start_worker(self):
        """워커 시작 - Job Queue를 모니터링하며 작업 실행"""
        self.running = True

        # ✅ Worker 시작 시 이전 stop 상태 초기화
        shared_state.reset_worker(self.worker_id)
        logger.info(f"🔄 [WORKER-{self.worker_id}] Reset stop state before starting")

        logger.info(f"Pipeline Worker {self.worker_id} started - PID: {os.getpid()}, TID: {threading.get_ident()}")
        logger.info(f"[{self.worker_id}] Lock object ID: {id(self._job_lock)} - Type: {type(self._job_lock)}")
        
        while self.running and (self._shutdown_event is None or not self._shutdown_event.is_set()):
            try:
                job_step = self._get_next_queued_job()
                
                if job_step:
                    logger.info(f"Processing job: worker_id: {self.worker_id}, job_id: {job_step['job_id']}, step: {job_step['step_id']}")
                    
                    # 작업 시작 - running 상태로 전환
                    self._update_step_status(job_step, 'running')
                    
                    self._execute_job_step(job_step)
                else:
                    # 작업이 없으면 1초 대기
                    time.sleep(1)
                    
            except BrokenPipeError as e:
                logger.error(f"❌ [WORKER-{self.worker_id}] BrokenPipeError error: {e}")
                continue

            except ConnectionRefusedError as e:
                continue

            except Exception as e:
                logger.error(f"❌ [WORKER-{self.worker_id}] ConnectionRefusedError error: {e}")
                
                # 기타 에러 시에도 시스템 종료만 체크하고 계속 실행
                for i in range(10):
                    if self._shutdown_event and self._shutdown_event.is_set():
                        break  # 시스템 전체 종료 시에만
                    time.sleep(1)
        
        logger.info(f"Pipeline Worker {self.worker_id} shutting down gracefully")
    
    def stop_worker(self):
        """워커 중지"""
        self.running = False
        if self.resource_monitor:
            self.resource_monitor.stop()
        
        # ✅ Shared Memory에서 워커 등록 해제
        shared_state.unregister_worker(self.worker_id)
        logger.info(f"🗑️ [WORKER-{self.worker_id}] Unregistered from shared memory")
        
        logger.info(f"Pipeline Worker {self.worker_id} stopped")
    
    def _handle_stop_request(self):
        """중단 요청 처리 - SharedState 폴링에서 호출됨"""
        logger.info(f"🛑 [WORKER-{self.worker_id}] Processing stop request")
        
        # ✅ 로컬과 Shared Memory 모두 업데이트 (child workers 포함)
        self.should_stop = True
        stopped_count = shared_state.stop_worker_and_children(self.worker_id)
        
        logger.info(f"🔄 [WORKER-{self.worker_id}] Updated stop flag for {stopped_count} workers (including children)")
        
        try:
            # 현재 프로세스의 모든 자식들 찾기 (recursive=True로 손자까지)
            children = self.worker_process.children(recursive=True)
            logger.info(f"🔍 [WORKER-{self.worker_id}] Found {len(children)} child processes to terminate")
            
            # 모든 자식 프로세스들 먼저 SIGTERM으로 정중하게 종료 요청
            for child in children:
                try:
                    logger.info(f"🔄 [WORKER-{self.worker_id}] Terminating child process PID:{child.pid}")
                    child.terminate()
                except psutil.NoSuchProcess:
                    logger.debug(f"[WORKER-{self.worker_id}] Child process PID:{child.pid} already terminated")
                    pass
            
            # 최대 5초 대기
            logger.info(f"⏳ [WORKER-{self.worker_id}] Waiting up to 5 seconds for processes to terminate...")
            gone, still_alive = psutil.wait_procs(children, timeout=5)
            
            # 아직 살아있는 프로세스들은 강제 Kill
            for child in still_alive:
                try:
                    logger.warning(f"🔨 [WORKER-{self.worker_id}] Force killing stubborn process PID:{child.pid}")
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            
            logger.info(f"✅ [WORKER-{self.worker_id}] Process cleanup completed. {len(gone)} terminated gracefully, {len(still_alive)} force killed")
                    
        except Exception as e:
            logger.error(f"❌ [WORKER-{self.worker_id}] Process cleanup error: {e}")
        
        # 사용자 정의 정리 함수들 실행
        self._run_cleanup_functions()
        
        # 현재 작업 상태를 'stopped'로 업데이트
        if self.current_job:
            self._update_step_status(
                self.current_job['id'], 
                'stopped', 
                error_message=f'Analysis stopped by user signal at {datetime.now()}'
            )
        
        logger.info(f"🛑 [WORKER-{self.worker_id}] Stop signal processing completed")
    
    def register_cleanup_function(self, func: Callable, *args, **kwargs):
        """정리 함수 등록"""
        def wrapper():
            try:
                logger.info(f"🧹 [WORKER-{self.worker_id}] Running cleanup function: {func.__name__}")
                func(*args, **kwargs)
            except Exception as e:
                logger.error(f"❌ [WORKER-{self.worker_id}] Cleanup function {func.__name__} error: {e}")
        
        self.cleanup_functions.append(wrapper)
        logger.debug(f"📝 [WORKER-{self.worker_id}] Registered cleanup function: {func.__name__}")
    
    def _run_cleanup_functions(self):
        """등록된 모든 정리 함수들 실행"""
        logger.info(f"🧹 [WORKER-{self.worker_id}] Running {len(self.cleanup_functions)} cleanup functions...")
        
        for cleanup_func in self.cleanup_functions:
            cleanup_func()
        
        # 실행 후 정리
        self.cleanup_functions.clear()
        logger.info(f"✅ [WORKER-{self.worker_id}] All cleanup functions completed")
    
    def _get_next_queued_job(self) -> Optional[sqlite3.Row]:
        """DAG 시스템용 단순 큐 작업 조회 (FIFO) - 의존성은 DAG에서 이미 해결됨"""
        
        if self._job_lock is None:
            logger.warning(f"[{self.worker_id}] No job lock available - proceeding without synchronization")
        
        # 락이 있으면 사용, 없으면 그냥 진행
        lock_context = self._job_lock if self._job_lock else None
        
        def _get_job():
            with database.get_db_connection() as conn:
                # DAG에서 이미 의존성이 해결된 작업만 큐에 있으므로 단순 FIFO
                job_step = conn.execute('''
                    SELECT jq.id as queue_id, jq.queued_at,
                           pjs.job_id, pjs.step_id, pjs.step_name, pjs.tool_name,
                           pjs.input_files, pjs.parameters,
                           pjs.input_dir, pjs.output_dir, pjs.output_files,
                           pjs.workbench_id, pjs.step_order
                    FROM job_queue jq
                    JOIN pipeline_job_steps pjs ON jq.step_id = pjs.step_id AND jq.job_id = pjs.job_id
                    WHERE pjs.status = 'pending'
                    ORDER BY jq.queued_at ASC
                    LIMIT 1
                ''').fetchone()
                
                if job_step:
                    job_id = job_step['job_id']
                    step_id = job_step['step_id']
                    queue_id = job_step['queue_id']

                    # ✨ DAG 초기화는 이제 Generator에서 수행됨 (pipeline_job_generator.py)
                    # ✨ Worker는 _execute_job_step에서 필요시 DAG를 로드만 함

                    # 상태 갱신 및 worker_id 기록
                    conn.execute('''
                        UPDATE pipeline_job_steps
                        SET status = 'running', worker_id = ?
                        WHERE job_id = ? AND step_id = ?
                    ''', (self.worker_id, job_id, step_id))

                    # 즉시 커밋으로 DB에 반영
                    conn.commit()
                    
                    # 큐에서 제거 (실행 상태 변경은 _execute_job_step에서 처리)
                    conn.execute('DELETE FROM job_queue WHERE id = ?', (queue_id,))
                    conn.commit()
                    logger.debug(f"[{self.worker_id}] ✅ Job dequeued: {queue_id}")
                    
                return job_step
        
        # 락이 있으면 사용, 없으면 그냥 실행
        if lock_context:
            with lock_context:
                return _get_job()
        else:
            return _get_job()
    
    def _update_step_status(self, job_step: sqlite3.Row, status: str, **kwargs):
        """파이프라인 작업 단계의 상태를 업데이트"""
        job_id = job_step['job_id']
        step_id = job_step['step_id']
        queue_id = job_step['queue_id'] if 'queue_id' in job_step else None
        
        try:
            with database.get_db_connection() as conn:
                # 기본 업데이트 쿼리 구성
                update_fields = ['status = ?', 'updated_at = CURRENT_TIMESTAMP']
                params = [status]
                
                # 상태별 추가 필드 설정
                if status == 'running':
                    update_fields.append('started_at = CURRENT_TIMESTAMP')
                elif status in ['completed', 'failed', 'stopped']:
                    update_fields.append('completed_at = CURRENT_TIMESTAMP')
                    if status == 'failed' and 'error_message' in kwargs:
                        update_fields.append('error_message = ?')
                        params.append(kwargs['error_message'])
                    elif status == 'stopped' and 'error_message' in kwargs:
                        update_fields.append('error_message = ?')
                        params.append(kwargs['error_message'])
                
                # pipeline_job_steps 업데이트
                conn.execute(f'''
                    UPDATE pipeline_job_steps 
                    SET {', '.join(update_fields)}
                    WHERE job_id = ? AND step_id = ?
                ''', params + [job_id, step_id])
                
                # job_queue도 함께 업데이트 (queue_id가 있는 경우)
                if queue_id:
                    queue_fields = ['status = ?']
                    queue_params = [status]
                    
                    if status == 'running':
                        queue_fields.extend(['started_at = CURRENT_TIMESTAMP', 'worker_id = ?'])
                        queue_params.append(self.worker_id)
                    elif status in ['completed', 'failed', 'stopped']:
                        queue_fields.append('completed_at = CURRENT_TIMESTAMP')
                    
                    conn.execute(f'''
                        UPDATE job_queue 
                        SET {', '.join(queue_fields)}
                        WHERE id = ?
                    ''', queue_params + [queue_id])
                
                conn.commit()
                logger.info(f"🔄 [STATUS-UPDATE] Step {step_id} status changed to '{status}'")
                
        except Exception as e:
            logger.error(f"❌ [STATUS-ERROR] Failed to update step {step_id} to {status}: {e}")
    
    def _execute_job_step(self, job_step: sqlite3.Row):
        """Job 스텝 실행"""
        job_id = job_step['job_id']
        step_id = job_step['step_id']
        tool_name = job_step['tool_name']
        workbench_id = job_step['workbench_id']

        # ✅ 새 작업 시작 시 이전 stop 신호 초기화 (다른 워크벤치의 stop이 영향 주지 않도록)
        shared_state.reset_worker(self.worker_id)
        logger.debug(f"🔄 [EXECUTE-STEP] Reset stop signal for new job (workbench: {workbench_id})")

        # Stop 신호 체크
        if self.should_stop:
            logger.info(f"🛑 [EXECUTE-STEP] Stop signal detected, aborting job execution")
            self._update_step_status(job_step['id'], 'stopped', error_message='Analysis stopped by user signal')
            return

        logger.info(f"🚀 [EXECUTE-STEP] Starting job step execution")
        logger.info(f"   ├─ Job ID: {job_id}")
        logger.info(f"   ├─ Step ID: {step_id}")
        logger.info(f"   ├─ Tool: {tool_name}")
        logger.info(f"   ├─ Workbench: {workbench_id}")
        logger.info(f"   └─ Worker: {self.worker_id}")
        
        try:
            result = self._run_step(job_step)
        except Exception as e:
            logger.error(f"💥 " + "=" * 80)
            logger.error(f"💥 [WORKER] CRITICAL FAILURE - STEP EXECUTION FAILED")
            logger.error(f"💥 " + "=" * 80)
            logger.error(f"❌ [FAILURE] Job ID: {job_id}")
            logger.error(f"❌ [FAILURE] Step ID: {step_id}")
            logger.error(f"❌ [FAILURE] Tool: {tool_name}")
            logger.error(f"❌ [FAILURE] Workbench: {workbench_id}")
            logger.error(f"❌ [FAILURE] Worker: {self.worker_id}")
            logger.error(f"❌ [FAILURE] Exception Type: {type(e).__name__}")
            logger.error(f"❌ [FAILURE] Exception Message: {str(e)}")
            logger.error(f"❌ [FAILURE] Function: execute_job_step()")
            logger.error(f"❌ [FAILURE] Timestamp: {datetime.now().isoformat()}")
            
            # 상세 스택 트레이스
            import traceback
            tb_lines = traceback.format_exc().split('\n')
            logger.error(f"📋 [FAILURE] Full Stack Trace:")
            for i, line in enumerate(tb_lines, 1):
                if line.strip():
                    logger.error(f"   {i:3d} │ {line}")
            
            logger.error(f"💥 " + "=" * 80)
            logger.error(f"💥 [WORKER] STEP EXECUTION TERMINATED WITH FAILURE")
            logger.error(f"💥 " + "=" * 80)
            
            # 실패 결과 반환
            result = {
                'success': False,
                'error': f"Critical execution failure: {str(e)}",
                'exception_type': type(e).__name__,
                'timestamp': datetime.now().isoformat()
            }
        
        logger.info(f"🔍 [TOOL-RESULT] Tool execution completed")
        logger.info(f"   ├─ Result type: {type(result)}")
        logger.info(f"   ├─ Result value: {result}")
        if result:
            logger.info(f"   ├─ Success: {result.get('success', 'Not specified')}")
            if 'error' in result:
                logger.info(f"   └─ Error: {result.get('error', 'No error message')}")
        else:
            logger.info(f"   └─ Result is None or empty")

        # result 결과에 따라 상태 업데이트
        try:
            if result and result.get('success', False):
                # 성공 시 - completed 상태로 전환
                self._update_step_status(job_step, 'completed')
                logger.info(f"✅ [STEP-UPDATE] Updated step {step_id} status to completed")
            elif result and result.get('stopped_by_user', False):
                # 사용자 중단 시 - cancelled 상태로 전환
                self._update_step_status(job_step, 'cancelled', error_message='Stopped by user')
                logger.warning(f"🛑 [STEP-CANCELLED] Updated step {step_id} status to cancelled: Stopped by user")
            else:
                # 실패 시 - failed 상태로 전환
                error_msg = result.get('error', 'Unknown error') if result else 'Tool execution failed'
                self._update_step_status(job_step, 'failed', error_message=error_msg)
                logger.error(f"❌ [STEP-FAILED] Updated step {step_id} status to failed: {error_msg}")
                
                # 화려한 파이프라인 실패 종료 로그
                logger.error("💥" + "═" * 80 + "💥")
                logger.error("💥" + " " * 80 + "💥")
                logger.error("💥" + "🚨 PIPELINE EXECUTION TERMINATED - FAILURE 🚨".center(80) + "💥")
                logger.error("💥" + " " * 80 + "💥")
                logger.error("💥" + "═" * 80 + "💥")
                logger.error(f"💥 🔴 Job ID: {job_id}")
                logger.error(f"💥 🔴 Failed Step: {step_id}")
                logger.error(f"💥 🔴 Error Reason: {error_msg}")
                logger.error(f"💥 🔴 Termination Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.error(f"💥 🔴 Pipeline Status: FAILED - NO FURTHER PROCESSING")
                logger.error("💥" + "═" * 80 + "💥")
                logger.error("💥" + "🛑 All subsequent steps have been canceled 🛑".center(80) + "💥")
                logger.error("💥" + "═" * 80 + "💥")
                return
        except Exception as e:
            logger.error(f"❌ [STEP-UPDATE] Failed to update step status: {e}")
            return

        # pipeline_job_steps 테이블에서 job_id에 해당하는 모든 steps가 completed인지 확인한다.
        try:
            with database.get_db_connection() as conn:
                stats = conn.execute('''
                    SELECT 
                        COUNT(*) as total_steps,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_steps,
                        SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_steps,
                        SUM(CASE WHEN status = 'pending' AND should_run = 1 THEN 1 ELSE 0 END) as pending_marked_steps
                    FROM pipeline_job_steps 
                    WHERE job_id = ?
                ''', (job_id,)).fetchone()
                
                total_steps = stats['total_steps']
                completed_steps = stats['completed_steps']
                cancelled_steps = stats['cancelled_steps']
                pending_marked_steps = stats['pending_marked_steps']
                finished_steps = completed_steps + cancelled_steps  # 완료 + 취소 = 종료
                
                logger.info(f"📊 [JOB-PROGRESS] Job {job_id}: {completed_steps} completed, {cancelled_steps} cancelled, {finished_steps}/{total_steps} finished")
                
                # 모든 단계가 완료되었거나 취소되었으면 종료 메시지 출력 및 워크벤치 상태 업데이트
                logger.info(
                    f"[GSEA-AUTO][MARKER] {JOB_WORKER_GSEA_MARKER} job_id={job_id} step_id={step_id} step_name={job_step['step_name']} total_steps={total_steps} finished_steps={finished_steps} pending_marked_steps={pending_marked_steps}"
                )
                if total_steps > 0 and finished_steps == total_steps and pending_marked_steps == 0:
                    if cancelled_steps > 0:
                        # 사용자 중단된 경우
                        logger.warning(f"🛑 [JOB-STOPPED] Job stopped by user: {job_id}")

                        # 워크벤치 상태를 'stopped'로 업데이트
                        conn.execute('''
                            UPDATE vizr_workbench
                            SET status = 'stopped', updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (workbench_id,))
                        conn.commit()
                        logger.info(f"🔄 [WORKBENCH-UPDATE] Workbench {workbench_id} status updated to 'stopped'")

                        # 사용자 중단 메시지
                        logger.info("🛑" + "═" * 80 + "🛑")
                        logger.info("🛑" + " " * 80 + "🛑")
                        logger.info("🛑" + "🛑 PIPELINE EXECUTION STOPPED BY USER 🛑".center(80) + "🛑")
                        logger.info("🛑" + " " * 80 + "🛑")
                        logger.info("🛑" + "═" * 80 + "🛑")
                        logger.info(f"🛑 ⏹️ Job ID: {job_id}")
                        logger.info(f"🛑 ⏹️ Completed Steps: {completed_steps}/{total_steps}")
                        logger.info(f"🛑 ⏹️ Cancelled Steps: {cancelled_steps}/{total_steps}")
                        logger.info(f"🛑 ⏹️ Stop Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        logger.info(f"🛑 ⏹️ Pipeline Status: STOPPED BY USER")
                        logger.info("🛑" + "═" * 80 + "🛑")
                        logger.info("🛑" + "⏹️ Analysis Stopped - User Requested ⏹️".center(80) + "🛑")
                        logger.info("🛑" + "═" * 80 + "🛑")
                    else:
                        # 정상적으로 성공 완료된 경우
                        logger.info(f"🎉 [JOB-COMPLETE] All steps completed for job {job_id}")

                        # 워크벤치 상태를 'completed'로 업데이트
                        conn.execute('''
                            UPDATE vizr_workbench
                            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (workbench_id,))
                        conn.commit()
                        logger.info(f"🔄 [WORKBENCH-UPDATE] Workbench {workbench_id} status updated to 'completed'")

                        # 화려한 파이프라인 성공 완료 로그
                        logger.info("🎊" + "═" * 80 + "🎊")
                        logger.info("🎊" + " " * 80 + "🎊")
                        logger.info("🎊" + "🎉 PIPELINE EXECUTION COMPLETED - SUCCESS! 🎉".center(80) + "🎊")
                        logger.info("🎊" + " " * 80 + "🎊")
                        logger.info("🎊" + "═" * 80 + "🎊")
                        logger.info(f"🎊 ✅ Job ID: {job_id}")
                        logger.info(f"🎊 ✅ Total Steps Completed: {completed_steps}/{total_steps}")
                        logger.info(f"🎊 ✅ Completion Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        logger.info(f"🎊 ✅ Pipeline Status: SUCCESSFULLY COMPLETED")
                        logger.info(f"🎊 ✅ All Analysis Steps Finished: 100% Success Rate")
                        logger.info("🎊" + "═" * 80 + "🎊")
                        logger.info("🎊" + "🏆 RNA-Seq Analysis Pipeline Complete! 🏆".center(80) + "🎊")
                        logger.info("🎊" + "═" * 80 + "🎊")

                        # ✨ 파이프라인 완료 후 압축 해제된 Raw Data 정리
                        try:
                            # 워크벤치 정보 조회하여 workbench schema 확인
                            workbench_info = conn.execute('''
                                SELECT name, user_id FROM vizr_workbench WHERE id = ?
                            ''', (workbench_id,)).fetchone()

                            if workbench_info:
                                workbench_name = workbench_info['name'].replace(' ', '_').replace('/', '_').replace('\\', '_')
                                user_id = workbench_info['user_id']
                                schema = get_workbench_schema(workbench_name, user_id)
                                raw_data_dir = schema['quanti']['raw']

                                logger.info(f"")
                                logger.info(f"🧹 [POST-PROCESS] Starting post-pipeline processing...")
                                logger.info(f"🧹 [POST-PROCESS] Cleaning up uncompressed raw data files...")

                                cleanup_result = cleanup_uncompressed_raw_data(raw_data_dir, logger)

                                if cleanup_result and cleanup_result.get('files_deleted', 0) > 0:
                                    logger.info(f"✅ [POST-PROCESS] Raw data cleanup successful!")
                                    logger.info(f"   ├─ Files deleted: {cleanup_result['files_deleted']}")
                                    logger.info(f"   ├─ Space freed: {cleanup_result['space_freed']:,} bytes ({cleanup_result['space_freed']/1024/1024:.1f} MB)")
                                    logger.info(f"   └─ Cleanup time: {cleanup_result['cleanup_time']:.2f}s")
                                else:
                                    logger.info(f"📭 [POST-PROCESS] No uncompressed raw data files found")
                            else:
                                logger.warning(f"⚠️  [POST-PROCESS] Could not find workbench {workbench_id}")

                        except Exception as cleanup_error:
                            # 정리 실패는 파이프라인 완료를 방해하지 않음 (경고만 출력)
                            logger.warning(f"⚠️  [POST-PROCESS] Raw data cleanup failed: {cleanup_error}")
                            logger.warning(f"⚠️  [POST-PROCESS] Pipeline completed successfully, but cleanup was skipped")
                    return
                elif total_steps > 0 and finished_steps == total_steps and pending_marked_steps > 0:
                    logger.info(f"[JOB-PROGRESS] Primary steps are finished, but {pending_marked_steps} marked step(s) remain queued or pending for job {job_id}")
        except Exception as e:
            logger.error(f"❌ [JOB-CHECK] Failed to check job completion: {e}")
            return

        # pipeline_job_steps 테이블에서 should_run=1이고 status가 pending인 것을 하나 뽑아 job_queue에 insert한다.
        try:
            with database.get_db_connection() as conn:
                # should_run=1인 다음 step 찾기 (step_order 순서대로)
                next_step = conn.execute('''
                    SELECT job_id, step_id, workbench_id
                    FROM pipeline_job_steps
                    WHERE job_id = ? AND status = 'pending' AND should_run = 1
                    ORDER BY step_order ASC
                    LIMIT 1
                ''', (job_id,)).fetchone()

                logger.info(
                    f"[GSEA-AUTO][MARKER] {JOB_WORKER_GSEA_MARKER} queue-check job_id={job_id} current_step={step_id} next_step={'none' if not next_step else next_step['step_id']}"
                )
                if next_step:
                    logger.info(
                        f"[GSEA-AUTO][NEXT] Found next pending step for job {job_id}: step_id={next_step['step_id']}, workbench_id={next_step['workbench_id']}"
                    )
                    # job_queue에 다음 단계 추가 (workbench_id 포함)
                    conn.execute('''
                        INSERT INTO job_queue (job_id, step_id, status, workbench_id, queued_at)
                        VALUES (?, ?, 'queued', ?, ?)
                    ''', (next_step['job_id'], next_step['step_id'], next_step['workbench_id'], datetime.now().isoformat()))
                    conn.commit()
                    logger.info(f"➡️ [NEXT-STEP] Queued next marked step (should_run=1): {next_step['step_id']} for job {job_id}")
                else:
                    logger.info(f"✅ [NO-MORE-STEPS] No more marked steps (should_run=1) for job {job_id}")
        except Exception as e:
            logger.error(f"❌ [NEXT-STEP] Failed to queue next step: {e}")

        return

    def _run_step(self, job_step: sqlite3.Row) -> Dict[str, str]:
        """도구별 실행 로직 - ToolManager를 통한 실행"""
        step_name = job_step['step_name']
        
        logger.info(f"🔧 [WORKER-{self.worker_id}] Starting step execution: {step_name}")
        
        # job_step 정보 출력 (간소화)
        def safe_get(row, key, default='N/A'):
            try:
                return row[key] if row[key] is not None else default
            except (KeyError, IndexError):
                return default
        
        logger.info(f"📋 [WORKER-{self.worker_id}] Step details:")
        logger.info(f"   ├─ job_id: {safe_get(job_step, 'job_id')}")
        logger.info(f"   ├─ step_id: {safe_get(job_step, 'step_id')}")
        logger.info(f"   ├─ step_name: {step_name}")
        logger.info(f"   └─ workbench_id: {safe_get(job_step, 'workbench_id')}")
        
        try:
            # ToolManager를 통해 단계 실행
            logger.info(f"🚀 [WORKER-{self.worker_id}] Delegating to ToolManager...")
            result = self.tool_manager.execute_step(step_name, job_step, self.worker_id)
            
            if hasattr(result, 'get'):
                # 딕셔너리인 경우
                success = result.get('success', True)
                error_msg = result.get('error', result.get('stderr', 'Unknown error'))
            else:
                # sqlite3.Row인 경우
                success = result['success'] if 'success' in result else True
                error_msg = result['error'] if 'error' in result else (result['stderr'] if 'stderr' in result else 'Unknown error')
                
            if success:
                logger.info(f"✅ [WORKER-{self.worker_id}] Step '{step_name}' completed successfully")
            else:
                logger.error(f"❌ [WORKER-{self.worker_id}] Step '{step_name}' failed: {error_msg}")
            
            return result
            
        except Exception as e:
            error_msg = f"Step '{step_name}' execution failed: {str(e)}"
            logger.error(f"💥 [WORKER-{self.worker_id}] {error_msg}")
            
            return {
                'success': False,
                'error': error_msg,
                'step_name': step_name,
                'worker_id': self.worker_id
            }
    

    def _log_job_event(self, job_id: str, step_id: str, event_type: str, message: str, severity: str = 'info'):
        """Job 이벤트 로그"""
        conn = self.get_db_connection()
        
        conn.execute('''
            INSERT INTO job_events (job_id, step_id, event_type, message, severity)
            VALUES (?, ?, ?, ?, ?)
        ''', (job_id, step_id, event_type, message, severity))
        
        conn.commit()
        conn.close()
    

class ResourceMonitor:
    """리소스 사용량 모니터링"""
    def __init__(self, job_id: str, step_id: str, db_path: str):
        self.job_id = job_id
        self.step_id = step_id
        self.db_path = db_path
        self.running = False
        self.thread = None
        self.kst = timezone(timedelta(hours=9))
    
    def start(self):
        """모니터링 시작"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """모니터링 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def _monitor_loop(self):
        """리소스 모니터링 루프"""
        while self.running:
            try:
                # 시스템 리소스 수집
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                memory_mb = memory.used // (1024 * 1024)
                
                # 디스크 사용량 (현재 프로세스)
                process = psutil.Process()
                disk_io = psutil.disk_io_counters()
                disk_mb = (disk_io.read_bytes + disk_io.write_bytes) // (1024 * 1024) if disk_io else 0
                
                # DB에 저장
                conn = sqlite3.connect(self.db_path)
                conn.execute('''
                    INSERT INTO resource_usage 
                    (job_id, step_id, cpu_usage_percent, memory_usage_mb, disk_usage_mb, peak_memory_mb)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (self.job_id, self.step_id, cpu_percent, memory_mb, disk_mb, memory_mb))
                
                conn.commit()
                conn.close()
                
                time.sleep(30)  # 30초마다 수집
                
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                time.sleep(60)  # 에러 시 1분 대기


# 사용 예제
if __name__ == '__main__':
    import signal
    import sys
    
    worker = PipelineJobWorker(worker_id="worker_1")
    
    def signal_handler(sig, frame):
        print("Stopping worker...")
        worker.stop_worker()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        worker.start_worker()
    except KeyboardInterrupt:
        worker.stop_worker()
