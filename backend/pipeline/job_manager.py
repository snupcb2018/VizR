#!/usr/bin/env python3
"""
Pipeline Job Manager
Job Queue 관리, 워커 조정, 스케줄링을 담당하는 마스터 프로세스
"""

import json
import os
import sqlite3
import threading
import time
import signal
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import logging
import psutil

from backend.pipeline.utils.shared_state import shared_state

# SQLite Threading 설정 - Thread-safe 모드 활성화
sqlite3.threadsafety = 3

from backend.pipeline.job_worker import PipelineJobWorker
from backend.pipeline.job_generator import PipelineJobGenerator
from config.backend_settings import BackendConfig as Config

# 사용자 이름 가져오기
import getpass
try:
    username = getpass.getuser()
except Exception:
    username = "unknown"

# Unified logging system
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'DEBUG')

class PipelineJobManager:
    def __init__(self, max_workers: int = 2, tool_manager=None):
        self.db_path = Config.DATABASE_FILE
        self.max_workers = max_workers
        self.workers = {}  # worker_id -> Thread
        self.running = False
        self.kst = timezone(timedelta(hours=9))
        self.tool_manager = tool_manager  # ToolManager 인스턴스
        
        # 워커 관리용 이벤트
        self.shutdown_event = threading.Event()
        
        # 스레드 간 공유 락
        self.job_lock = threading.Lock()
        
        if self.tool_manager:
            logger.info(f"🔧 [JOB-MANAGER] Initialized with ToolManager ({len(self.tool_manager.coordinators)} tools)")
        else:
            logger.warning("⚠️ [JOB-MANAGER] No ToolManager provided - workers will create individual instances")
        
        # Job Generator
        self.job_generator = PipelineJobGenerator()
        
        # 스케줄러 스레드
        self.scheduler_thread = None
        self.health_check_thread = None
    
    def start(self):
        """Job Manager 시작"""
        self.running = True
        logger.info(f"Starting Pipeline Job Manager with {self.max_workers} workers")
        
        # Signal handlers 설정 (메인 스레드에서만 가능)
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            logger.info("Signal handlers registered successfully")
        except ValueError as e:
            logger.warning(f"Cannot set signal handlers (not in main thread): {e}")
            # 서브 스레드에서 실행되는 경우 signal handler를 설정할 수 없음
        
        # 워커 프로세스 시작
        self._start_workers()
        
        # 스케줄러 스레드 시작
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        # 헬스체크 스레드 시작
        self.health_check_thread = threading.Thread(target=self._health_check_loop)
        self.health_check_thread.daemon = True
        self.health_check_thread.start()
        
        time.sleep(0.5)
        logger.info("Pipeline Job Manager started successfully")
        
        # 메인 루프
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Job Manager 중지"""
        logger.info("Stopping Pipeline Job Manager...")
        self.running = False
        self.shutdown_event.set()
        
        # 워커 프로세스 종료
        self._stop_workers()
        
        # 스레드 종료 대기
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        if self.health_check_thread and self.health_check_thread.is_alive():
            self.health_check_thread.join(timeout=5)
        
        logger.info("Pipeline Job Manager stopped")
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러 - Ctrl+C 등의 신호 처리"""
        signal_name = "SIGINT" if signum == signal.SIGINT else f"Signal {signum}"
        logger.warning(f"🛑 {signal_name} received - initiating graceful shutdown")
        
        # 현재 실행 중인 모든 job들을 cancelled 상태로 변경
        self._cancel_running_jobs()
        
        # 정상 종료 프로세스 시작
        self.stop()
        sys.exit(0)
    
    def _cancel_running_jobs(self):
        """현재 실행 중인 모든 job들을 cancelled 상태로 변경"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 실행 중인 모든 job step들을 찾아서 cancelled로 변경
                running_steps = conn.execute('''
                    SELECT job_id, step_id, step_name FROM pipeline_job_steps 
                    WHERE status = 'running'
                ''').fetchall()
                
                if running_steps:
                    logger.warning(f"📋 Found {len(running_steps)} running job steps to cancel")
                    for step in running_steps:
                        job_id = step['job_id'] 
                        step_id = step['step_id']
                        step_name = step['step_name']
                        logger.warning(f"   🔄 Cancelling: {job_id}/{step_name}")
                    
                    # 모든 running 상태를 cancelled로 변경
                    conn.execute('''
                        UPDATE pipeline_job_steps 
                        SET status = 'stopped', 
                            completed_at = datetime('now'),
                            error_message = 'Process stopped by user (Ctrl+C)',
                            updated_at = datetime('now')
                        WHERE status = 'running'
                    ''')
                    conn.commit()
                    logger.info(f"✅ Successfully cancelled {len(running_steps)} running jobs")
                else:
                    logger.info("ℹ️ No running jobs found to cancel")
                    
        except Exception as e:
            logger.error(f"❌ Error while cancelling running jobs: {e}")
    
    def _start_workers(self):
        """워커 프로세스들 시작"""
        for i in range(self.max_workers):
            worker_id = f"worker_{i+1}"
            self._start_single_worker(worker_id)
    
    def _start_single_worker(self, worker_id: str):
        """단일 워커 스레드 시작"""
        if worker_id in self.workers:
            logger.warning(f"Worker {worker_id} already running")
            return
        
        def worker_thread():
            logger.info(f"Worker thread {worker_id} starting - PID: {os.getpid()}, TID: {threading.get_ident()}")
            # ToolManager를 워커에 전달
            worker = PipelineJobWorker(worker_id=worker_id, tool_manager=self.tool_manager, db_path=self.db_path)
            worker._job_lock = self.job_lock  # 스레드 간 공유 락 전달
            logger.info(f"[{worker_id}] Lock assigned - ID: {id(self.job_lock)} - Type: {type(self.job_lock)}")
            
            # shutdown event 전달
            worker._shutdown_event = self.shutdown_event
            
            try:
                shared_state.register_worker(worker_id)
                worker.start_worker()
                    
            except Exception as e:
                logger.error(f"Worker {worker_id} failed: {e}")
        
        thread = threading.Thread(target=worker_thread, name=worker_id)
        thread.daemon = True
        thread.start()
        self.workers[worker_id] = thread
        
        logger.info(f"Started worker thread: {worker_id} (TID: {thread.ident})")
    
    def _stop_workers(self):
        """모든 워커 스레드 중지"""
        for worker_id, thread in self.workers.items():
            if thread.is_alive():
                logger.info(f"Stopping worker thread: {worker_id}")
                # 스레드는 shutdown_event로 graceful shutdown
                thread.join(timeout=10)
                
                if thread.is_alive():
                    logger.warning(f"Worker thread {worker_id} still alive after timeout")
        
        self.workers.clear()
    
    def _scheduler_loop(self):
        """스케줄러 루프 - Job 우선순위 관리 및 시스템 모니터링"""
        logger.info("Scheduler started - monitoring job queue and system resources")
        
        while self.running:
            try:
                # Job Queue 모니터링
                self._monitor_job_queue()
                
                # 시스템 리소스 체크
                self._check_system_resources()
                
                time.sleep(30)  # 30초마다 실행
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)
    
    def _health_check_loop(self):
        """워커 헬스체크 루프"""
        logger.info("Health check started")
        
        while self.running:
            try:
                # 죽은 워커 감지 및 재시작
                for worker_id, thread in list(self.workers.items()):
                    if not thread.is_alive():
                        logger.warning(f"Worker thread {worker_id} died, restarting...")
                        self.workers.pop(worker_id)
                        self._start_single_worker(worker_id)

                # 리소스 사용량 정리 (향후 구현)

                time.sleep(60)  # 1분마다 실행
                
            except Exception as e:
                logger.error(f"Health check error: {e}")
                time.sleep(120)
    
    def cancel_pipeline_job(self, job_id: str) -> bool:
        """파이프라인 Job 취소"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            # Job 상태 확인 (pipeline_job_steps에서 조회)
            job = conn.execute('''
                SELECT 
                    CASE 
                        WHEN SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0 THEN 'failed'
                        WHEN SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) > 0 THEN 'running'
                        WHEN COUNT(*) = SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) THEN 'completed'
                        ELSE 'pending'
                    END as status
                FROM pipeline_job_steps WHERE job_id = ?
            ''', (job_id,)).fetchone()
            
            if not job:
                logger.warning(f"Job {job_id} not found")
                return False
            
            if job['status'] in ['completed', 'failed', 'stopped']:
                logger.warning(f"Job {job_id} already in final state: {job['status']}")
                return False
            
            # pipeline_jobs 테이블이 제거되어 pipeline_job_steps만 업데이트
            # 모든 스텝을 stopped로 변경
            conn.execute('''
                UPDATE pipeline_job_steps 
                SET status = 'stopped', updated_at = ?
                WHERE job_id = ? AND status IN ('pending', 'running')
            ''', (datetime.now(self.kst).isoformat(), job_id))
            
            conn.execute('''
                UPDATE job_queue 
                SET status = 'stopped'
                WHERE job_id = ? AND status IN ('queued', 'running')
            ''', (job_id,))
            
            # 취소 이벤트 로그
            conn.execute('''
                INSERT INTO job_events (job_id, event_type, message, severity)
                VALUES (?, 'job_cancelled', 'Pipeline job cancelled by user', 'warning')
            ''', (job_id,))
            
            conn.commit()
            logger.info(f"Cancelled pipeline job: {job_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
        finally:
            conn.close()
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Job 상태 조회"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            # pipeline_jobs 테이블이 제거되어 pipeline_job_steps에서 정보 가져오기
            job = conn.execute('''
                SELECT 
                    pjs.job_id,
                    pjs.workbench_id,
                    vw.name as workbench_name,
                    COUNT(*) as total_steps,
                    SUM(CASE WHEN pjs.status = 'completed' THEN 1 ELSE 0 END) as completed_steps,
                    SUM(CASE WHEN pjs.status = 'failed' THEN 1 ELSE 0 END) as failed_steps,
                    SUM(CASE WHEN pjs.status = 'running' THEN 1 ELSE 0 END) as running_steps,
                    MIN(pjs.created_at) as created_at,
                    MAX(pjs.updated_at) as updated_at,
                    CASE 
                        WHEN SUM(CASE WHEN pjs.status = 'failed' THEN 1 ELSE 0 END) > 0 THEN 'failed'
                        WHEN SUM(CASE WHEN pjs.status = 'running' THEN 1 ELSE 0 END) > 0 THEN 'running'
                        WHEN COUNT(*) = SUM(CASE WHEN pjs.status = 'completed' THEN 1 ELSE 0 END) THEN 'completed'
                        ELSE 'pending'
                    END as status
                FROM pipeline_job_steps pjs
                LEFT JOIN vizr_workbench vw ON pjs.workbench_id = vw.id
                WHERE pjs.job_id = ?
                GROUP BY pjs.job_id, pjs.workbench_id, vw.name
            ''', (job_id,)).fetchone()
            
            if not job:
                return None
            
            # 스텝 상태 조회
            steps = conn.execute('''
                SELECT step_id, step_name, tool_name, status, 
                       started_at, completed_at, duration_seconds, error_message
                FROM pipeline_job_steps 
                WHERE job_id = ?
                ORDER BY step_order
            ''', (job_id,)).fetchall()
            
            # 진행률 계산
            total_steps = len(steps)
            completed_steps = sum(1 for step in steps if step['status'] == 'completed')
            progress_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
            
            # 현재 실행 중인 스텝 찾기
            current_step = None
            for step in steps:
                if step['status'] == 'running':
                    current_step = step['step_name']
                    break
            
            # 전체 실행 시간 계산
            started_at = min([s['started_at'] for s in steps if s['started_at']], default=None)
            completed_at = max([s['completed_at'] for s in steps if s['completed_at']], default=None)
            
            # 오류 메시지 수집
            error_messages = [s['error_message'] for s in steps if s['error_message']]
            error_message = '; '.join(error_messages) if error_messages else None
            
            return {
                'job_id': job['job_id'],
                'workbench_id': job['workbench_id'],
                'workbench_name': job['workbench_name'] if job['workbench_name'] else f"Workbench {job['workbench_id']}",
                'status': job['status'],
                'total_steps': total_steps,
                'completed_steps': completed_steps,
                'failed_steps': job['failed_steps'],
                'progress_percentage': round(progress_percentage, 1),
                'current_step': current_step,
                'started_at': started_at,
                'completed_at': completed_at,
                'estimated_duration': None,  # pipeline_jobs 제거로 사용 불가
                'actual_duration': None,     # pipeline_jobs 제거로 사용 불가
                'error_message': error_message,
                'created_at': job['created_at'],
                'updated_at': job['updated_at'],
                'steps': [dict(step) for step in steps]
            }
            
        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            return None
        finally:
            conn.close()
    
    def list_active_jobs(self) -> List[Dict[str, Any]]:
        """활성 Job 목록 조회"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            jobs = conn.execute('''
                SELECT * FROM job_dashboard 
                WHERE status IN ('pending', 'running')
                ORDER BY created_at DESC
            ''').fetchall()
            
            return [dict(job) for job in jobs]
            
        except Exception as e:
            logger.error(f"Failed to list active jobs: {e}")
            return []
        finally:
            conn.close()
    
    def get_system_status(self) -> Dict[str, Any]:
        """시스템 전체 상태 조회"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            # Job 통계 (pipeline_job_steps에서 집계)
            job_stats = conn.execute('''
                SELECT 
                    CASE 
                        WHEN SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0 THEN 'failed'
                        WHEN SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) > 0 THEN 'running'
                        WHEN COUNT(*) = SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) THEN 'completed'
                        ELSE 'pending'
                    END as status,
                    COUNT(DISTINCT job_id) as count
                FROM pipeline_job_steps 
                WHERE created_at >= datetime('now', '-1 day')
                GROUP BY job_id
            ''').fetchall()
            
            # 워커 상태
            worker_status = {}
            for worker_id, thread in self.workers.items():
                worker_status[worker_id] = {
                    'alive': thread.is_alive(),
                    'thread_id': thread.ident if thread.is_alive() else None
                }
            
            # 큐 상태
            queue_stats = conn.execute('''
                SELECT 
                    status,
                    COUNT(*) as count
                FROM job_queue
                GROUP BY status
            ''').fetchall()
            
            # 시스템 리소스
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'manager_status': 'running' if self.running else 'stopped',
                'workers': worker_status,
                'job_stats': {stat['status']: stat['count'] for stat in job_stats},
                'queue_stats': {stat['status']: stat['count'] for stat in queue_stats},
                'system_resources': {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_used_gb': round(memory.used / (1024**3), 2),
                    'memory_total_gb': round(memory.total / (1024**3), 2),
                    'disk_percent': disk.percent,
                    'disk_used_gb': round(disk.used / (1024**3), 2),
                    'disk_total_gb': round(disk.total / (1024**3), 2)
                },
                'timestamp': datetime.now(self.kst).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {'error': str(e)}
        finally:
            conn.close()
    
    
    def _monitor_job_queue(self):
        """Job Queue 모니터링 (우선순위 제거됨)"""
        conn = sqlite3.connect(self.db_path)
        
        try:
            # 큐에 쌓인 작업 수 모니터링
            result = conn.execute('SELECT COUNT(*) as queue_count FROM job_queue').fetchone()
            queue_count = result[0] if result else 0
            
            if queue_count > 10:
                logger.warning(f"Job queue is getting large: {queue_count} jobs pending")
            
        except Exception as e:
            logger.error(f"Error monitoring job queue: {e}")
        finally:
            conn.close()
    
    def _check_system_resources(self):
        """시스템 리소스 체크 및 경고"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # 임계치 초과 시 경고
            if cpu_percent > 90:
                logger.warning(f"High CPU usage: {cpu_percent}%")
            
            if memory.percent > 85:
                logger.warning(f"High memory usage: {memory.percent}%")
            
            if disk.percent > 90:
                logger.warning(f"Low disk space: {disk.percent}% used")
                
        except Exception as e:
            logger.error(f"Error checking system resources: {e}")


# CLI 인터페이스
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Pipeline Job Manager')
    parser.add_argument('--workers', type=int, default=2, help='Number of worker processes')
    parser.add_argument('--db', default='vizr.db', help='Database path')
    parser.add_argument('--command', choices=['start', 'status', 'stop'], default='start')
    
    args = parser.parse_args()
    
    if args.command == 'start':
        manager = PipelineJobManager(max_workers=args.workers)
        manager.start()
    
    elif args.command == 'status':
        manager = PipelineJobManager(max_workers=1)
        status = manager.get_system_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    
    elif args.command == 'stop':
        # 실제로는 PID 파일을 사용해서 실행 중인 매니저를 중지해야 함
        print("Stop command not implemented - use Ctrl+C or kill command")


if __name__ == '__main__':
    main()
