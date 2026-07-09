#!/usr/bin/env python3
"""
Process Wrapper for Pipeline Tools
모든 파이프라인 도구들의 통일된 프로세스 실행 및 정리 시스템

✅ Shared Memory 기반으로 worker_instance 의존성 제거
"""

import os
import sys
import time
import shutil
import subprocess
import threading
import logging
import signal
import platform
import multiprocessing as mp
from typing import List, Callable, Any, Optional, Dict
from pathlib import Path

from backend.pipeline.utils.shared_state import shared_state

# SharedState import 제거됨 - ProcessPoolExecutor가 프로세스 관리를 담당

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def file_copy_worker(source_file: str, target_file: str, progress_callback: Optional[Callable] = None) -> int:
    """
    파일 복사 워커 함수 - 별도 프로세스에서 실행됨
    
    Args:
        source_file: 원본 파일 경로
        target_file: 대상 파일 경로  
        progress_callback: 진행률 콜백 함수 (옵션)
        
    Returns:
        0: 성공, 1: 실패
    """
    try:
        # 대상 디렉토리가 없으면 생성
        target_dir = os.path.dirname(target_file)
        if target_dir and not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
        
        # 파일 크기 확인 (진행률 추적용)
        source_size = os.path.getsize(source_file)
        
        # 파일 복사 실행
        with open(source_file, 'rb') as src, open(target_file, 'wb') as dst:
            copied = 0
            chunk_size = 1024 * 1024  # 1MB chunks
            
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                    
                dst.write(chunk)
                copied += len(chunk)
                
                # 진행률 콜백 (옵션)
                if progress_callback and source_size > 0:
                    progress = (copied / source_size) * 100
                    progress_callback(progress)
        
        # 파일 속성 복사 (timestamps, permissions)
        shutil.copystat(source_file, target_file)
        
        return 0  # 성공
        
    except Exception as e:
        print(f"File copy failed: {e}", file=sys.stderr)
        return 1  # 실패


class ProcessWrapper:
    """
    통일된 프로세스 실행 및 정리 시스템
    ✅ 단순화된 버전 - ProcessPoolExecutor가 프로세스 종료를 담당
    """
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.current_process = None
        self.cleanup_functions: List[Callable] = []

        # 자식 프로세스에서 한 번만 설정
        from backend.utils.logger import setup_module_logger
        logger = setup_module_logger(__name__, 'INFO')
        logger.info(f"[ProcessWrapper] worker initialized (pid={mp.current_process().pid})")

        
        logger.debug(f"🔧 [PROCESS-WRAPPER] Initialized for worker {worker_id}")
    
    def run_command(self, cmd: List[str], stop_event=None, progress_callback=None, **kwargs) -> dict:
        """
        명령 실행 및 완료 대기 (progress_callback 지원)
        
        Args:
            cmd: 실행할 명령어 리스트
            stop_event: 중단 신호 이벤트
            progress_callback: 실시간 진행상황 콜백 함수
            **kwargs: subprocess.Popen에 전달할 추가 인수들
            
        Returns:
            실행 결과 딕셔너리
        """
        # progress_callback이 있으면 run_command_with_callback 사용
        if progress_callback:
            return self.run_command_with_callback(
                cmd=cmd,
                stop_event=stop_event, 
                output_callback=progress_callback,
                **kwargs
            )
        else:
            # 프로세스 시작
            process = self._start_process(cmd, **kwargs)
            
            # 완료 대기 및 결과 반환
            return self._wait_for_process(process, stop_event=stop_event)
    
    def run_command_with_callback(self, cmd: List[str], stop_event=None, output_callback=None, **kwargs) -> dict:
        """
        명령 실행 및 완료 대기 (실시간 출력 콜백 포함)
        
        Args:
            cmd: 실행할 명령어 리스트
            stop_event: 중단 신호 이벤트
            output_callback: 실시간 출력 라인 처리 함수
            **kwargs: subprocess.Popen에 전달할 추가 인수들
            
        Returns:
            실행 결과 딕셔너리
        """
        # 프로세스 시작
        process = self._start_process(cmd, **kwargs)
        
        # 실시간 출력 처리 및 완료 대기
        return self._wait_for_process_with_callback(process, stop_event=stop_event, output_callback=output_callback)
    
    def _start_process(self, cmd: List[str], **kwargs) -> subprocess.Popen:
        """프로세스 그룹으로 시작"""
        # 기본 설정
        default_kwargs = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True
        }
        
        # 플랫폼별 프로세스 그룹 설정
        if platform.system() == 'Windows':
            # Windows: 새 프로세스 그룹 생성
            default_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            logger.debug(f"🪟 [PROCESS-WRAPPER] Windows: Creating new process group")
        else:
            # POSIX (Linux/macOS): 새 세션 생성
            default_kwargs['preexec_fn'] = os.setsid
            logger.debug(f"🐧 [PROCESS-WRAPPER] POSIX: Creating new session/process group")
        
        default_kwargs.update(kwargs)
        
        logger.info(f"🚀 [PROCESS-WRAPPER] Running command: {' '.join(cmd)}")
        
        # 프로세스 시작
        self.current_process = subprocess.Popen(cmd, **default_kwargs)
        
        logger.debug(f"📝 [PROCESS-WRAPPER] Started process PID {self.current_process.pid}")
        
        return self.current_process
    
    def _wait_for_process_with_callback(self, process: subprocess.Popen, check_interval: float = 0.1, stop_event=None, output_callback=None) -> dict:
        """
        프로세스 완료 대기 (실시간 출력 처리 포함)
        
        Args:
            process: 대기할 프로세스
            check_interval: Stop 신호 체크 간격 (초)
            output_callback: 출력 라인 처리 함수
            
        Returns:
            실행 결과 딕셔너리
        """
        logger.info(f"⏳ [PROCESS-WRAPPER] Waiting for process with real-time output monitoring...")
        
        # 출력 버퍼 수집
        stdout_lines = []
        stderr_lines = []
        
        # 통합된 스트림 읽기 함수
        def read_stream(stream, stream_name, output_lines):
            """stdout과 stderr를 동일한 로직으로 처리하는 통합 함수"""
            
            buffer = ""
            try:
                while True:
                    # Stop Event 체크 (스레드 레벨에서)
                    if stop_event and stop_event.is_set():
                        logger.info(f"🛑 [PROCESS-WRAPPER] Stop signal detected in {stream_name} reader for worker {self.worker_id}")
                        break
                        
                    # 프로세스가 종료되었는지 먼저 체크
                    if process.poll() is not None:
                        # 프로세스 종료됨 - 버퍼에 남은 내용 처리 후 종료
                        if buffer.strip():
                            line = buffer.strip()
                            
                            # 🔍 DEBUG: ProcessWrapper에서 라인 읽기 확인
                            try:
                                logger.info(f"🔍 [{stream_name}] PROCESS_END: '{line}'")
                            except:
                                pass
                            
                            output_lines.append(line)
                            if output_callback:
                                try:
                                    output_callback(line)
                                except Exception as e:
                                    logger.warning(f"⚠️ [PROCESS-WRAPPER] {stream_name} callback error: {e}")
                        break
                    
                    # 한 글자씩 읽되, 블로킹 방지를 위해 타임아웃 적용
                    try:
                        char = stream.read(1)
                        logger.debug(f"🔍 [{stream_name}] CHAR: '{char}'")
                        if not char:  # EOF or no data
                            time.sleep(0.01)  # 10ms 대기
                    except Exception as read_error:
                        # 읽기 오류 시 잠시 대기 후 재시도
                        logger.warning(f"{stream_name} read error: {read_error}")
                        time.sleep(0.01)
                        continue
                    
                    buffer += char

                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.rstrip('\r')
                        logger.info(f"[PROCESS-WRAPPER] {stream_name} LINE: {line}")
                        output_lines.append(line)
                        if output_callback:
                            try:
                                output_callback(line)
                            except Exception as e:
                                logger.warning(f"[PROCESS-WRAPPER] {stream_name} callback error: {e}")

            except Exception as e:
                logger.warning(f"⚠️ [PROCESS-WRAPPER] {stream_name} reading error: {e}")
        
        # 각 스트림별 래퍼 함수
        def read_stdout():
            read_stream(process.stdout, "STDOUT", stdout_lines)
        
        def read_stderr():
            read_stream(process.stderr, "STDERR", stderr_lines)
        
        # 출력 읽기 스레드 시작
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        
        stdout_thread.start()
        stderr_thread.start()
        
        # Stop 신호 체크하며 프로세스 완료 대기
        while process.poll() is None:
            # Stop 신호 체크
            try:
                if stop_event and stop_event.is_set():
                    logger.warning(f"🛑 [PROCESS-WRAPPER] Stop signal detected for worker {self.worker_id}")
                    logger.warning(f"🛑 [PROCESS-WRAPPER] Initiating process group termination...")
                    
                    # 프로세스 그룹 전체 강제 종료
                    self.terminate_process_group(process)
                    
                    # 출력 스레드 완료 대기 (짧은 시간)
                    stdout_thread.join(timeout=2)
                    stderr_thread.join(timeout=2)
                    
                    # SharedState에서 중단된 프로세스 제거
                    shared_state.remove_current_process(self.worker_id, process.pid)
                    logger.debug(f"🗑️ [PROCESS-WRAPPER] Removed terminated process PID {process.pid} for worker {self.worker_id}")
                    
                    return {
                        'success': False,
                        'return_code': -1,
                        'returncode': -1,
                        'stdout': '\n'.join(stdout_lines),
                        'stderr': '\n'.join(stderr_lines),
                        'stopped_by_user': True
                    }
                    
            except Exception as e:
                logger.warning(f"⚠️ [PROCESS-WRAPPER] Error checking stop signal: {e}")
            
            time.sleep(check_interval)
        
        # 프로세스 정상 완료 - 출력 스레드 완료 대기
        logger.info(f"📊 [PROCESS-WRAPPER] Process finished, waiting for output threads...")
        
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        
        returncode = process.returncode
        
        if returncode == 0:
            logger.info(f"✅ [PROCESS-WRAPPER] Process completed successfully with return code: {returncode}")
        else:
            logger.warning(f"⚠️ [PROCESS-WRAPPER] Process completed with error return code: {returncode}")
        
        # SharedState에서 완료된 프로세스 제거
        shared_state.remove_current_process(self.worker_id, process.pid)
        logger.debug(f"🗑️ [PROCESS-WRAPPER] Removed completed process PID {process.pid} for worker {self.worker_id}")
        
        return {
            'success': returncode == 0,
            'return_code': returncode,
            'returncode': returncode,
            'stdout': '\n'.join(stdout_lines),
            'stderr': '\n'.join(stderr_lines),
            'stopped_by_user': False
        }
    
    def terminate_process_group(self, process: subprocess.Popen):
        """프로세스 그룹 전체 강제 종료"""
        if not process or process.poll() is not None:
            logger.debug(f"🔍 [PROCESS-WRAPPER] Process already terminated or None")
            return
            
        try:
            pid = process.pid
            logger.warning(f"🛑 [PROCESS-WRAPPER] Terminating process group for PID {pid}")
            
            if platform.system() == 'Windows':
                # Windows: 프로세스 트리 전체 종료
                logger.debug(f"🪟 [PROCESS-WRAPPER] Windows: Using taskkill /T /F")
                result = subprocess.run(
                    ['taskkill', '/T', '/F', '/PID', str(pid)], 
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    logger.info(f"✅ [PROCESS-WRAPPER] Windows process tree terminated successfully")
                else:
                    logger.warning(f"⚠️ [PROCESS-WRAPPER] taskkill failed: {result.stderr}")
                    
            else:
                # POSIX: 프로세스 그룹 점진적 종료
                logger.debug(f"🐧 [PROCESS-WRAPPER] POSIX: Using SIGTERM -> SIGKILL")
                
                try:
                    pgid = os.getpgid(pid)
                    logger.debug(f"📝 [PROCESS-WRAPPER] Process group ID: {pgid}")
                    
                    # 1. SIGTERM으로 정중한 종료 시도
                    os.killpg(pgid, signal.SIGTERM)
                    logger.debug(f"📤 [PROCESS-WRAPPER] Sent SIGTERM to process group {pgid}")
                    
                    # 2. 1초 대기
                    time.sleep(1)
                    
                    # 3. 아직 살아있으면 SIGKILL로 강제 종료
                    if process.poll() is None:
                        logger.warning(f"⚡ [PROCESS-WRAPPER] Process still running, sending SIGKILL")
                        os.killpg(pgid, signal.SIGKILL)
                        logger.info(f"💀 [PROCESS-WRAPPER] Sent SIGKILL to process group {pgid}")
                    else:
                        logger.info(f"✅ [PROCESS-WRAPPER] Process terminated gracefully with SIGTERM")
                        
                except ProcessLookupError:
                    logger.info(f"ℹ️ [PROCESS-WRAPPER] Process group already terminated")
                    
        except (OSError, subprocess.TimeoutExpired, ProcessLookupError) as e:
            logger.error(f"❌ [PROCESS-WRAPPER] Process group termination failed: {type(e).__name__}: {e}")
            
            # 최후 수단: 개별 프로세스 강제 종료
            try:
                process.kill()
                logger.warning(f"🔨 [PROCESS-WRAPPER] Fallback: killed individual process")
            except:
                pass
        
        except Exception as e:
            logger.error(f"💥 [PROCESS-WRAPPER] Unexpected error in process termination: {e}")
    
    def run_file_copy(self, source_file: str, target_file: str) -> dict:
        """
        shutil.copy2() 대체 - 별도 프로세스로 파일 복사 실행 및 완료 대기
        
        Args:
            source_file: 원본 파일 경로
            target_file: 대상 파일 경로
            
        Returns:
            실행 결과 딕셔너리
        """
        logger.info(f"🚀 [PROCESS-WRAPPER] Starting file copy: {source_file} -> {target_file}")
        
        # file_copy_worker 함수를 별도 프로세스로 실행
        copy_cmd = [
            sys.executable, "-c",
            f"from backend.pipeline.utils.process_wrapper import file_copy_worker; "
            f"import sys; "
            f"sys.exit(file_copy_worker('{source_file}', '{target_file}'))"
        ]
        
        # 파일 복사도 프로세스 그룹으로 시작
        copy_kwargs = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True
        }
        
        # 플랫폼별 프로세스 그룹 설정
        if platform.system() == 'Windows':
            copy_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            copy_kwargs['preexec_fn'] = os.setsid
        
        self.current_process = subprocess.Popen(copy_cmd, **copy_kwargs)
        
        # ✅ Shared Memory에 현재 프로세스 등록
        shared_state.set_current_process(self.worker_id, self.current_process.pid)
        
        logger.debug(f"📝 [PROCESS-WRAPPER] Registered file copy PID {self.current_process.pid} for worker {self.worker_id}")
        
        # 완료 대기 및 결과 반환
        return self._wait_for_process(self.current_process)
    
    def _wait_for_process(self, process: subprocess.Popen, check_interval: float = 0.5, stop_event=None) -> dict:
        """
        프로세스 완료 대기 (Stop 신호 체크 포함, 실시간 출력 읽기로 데드락 방지)

        Args:
            process: 대기할 프로세스
            check_interval: Stop 신호 체크 간격 (초)

        Returns:
            실행 결과 딕셔너리
        """
        logger.info(f"⏳ [PROCESS-WRAPPER] Waiting for process completion with stop signal monitoring...")

        # 출력 버퍼 수집 (데드락 방지를 위해 실시간으로 읽음)
        stdout_lines = []
        stderr_lines = []

        # 스트림 읽기 함수
        def read_stream(stream, output_lines):
            """stdout/stderr를 실시간으로 읽어서 버퍼 데드락 방지"""
            try:
                for line in iter(stream.readline, ''):
                    if line:
                        output_lines.append(line.rstrip('\n'))
                    else:
                        break
            except Exception as e:
                logger.debug(f"[PROCESS-WRAPPER] Stream reading completed or error: {e}")

        # 출력 읽기 스레드 시작
        stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines), daemon=True)
        stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines), daemon=True)

        stdout_thread.start()
        stderr_thread.start()

        # Stop 신호 체크하며 프로세스 완료 대기
        while process.poll() is None:
            # ✅ Stop 신호 체크 - SharedState를 통해 실시간 모니터링
            try:
               if stop_event and stop_event.is_set():
                    logger.warning(f"🛑 [PROCESS-WRAPPER] Stop signal detected for worker {self.worker_id}")
                    logger.warning(f"🛑 [PROCESS-WRAPPER] Initiating process group termination...")

                    # 프로세스 그룹 전체 강제 종료
                    self.terminate_process_group(process)

                    # 출력 스레드 완료 대기
                    stdout_thread.join(timeout=2)
                    stderr_thread.join(timeout=2)

                    # ✅ Shared Memory에서 중단된 프로세스 제거
                    shared_state.remove_current_process(self.worker_id, process.pid)
                    logger.debug(f"🗑️ [PROCESS-WRAPPER] Removed terminated process PID {process.pid} for worker {self.worker_id}")

                    return {
                        'success': False,
                        'return_code': -1,
                        'returncode': -1,
                        'stdout': '\n'.join(stdout_lines),
                        'stderr': '\n'.join(stderr_lines),
                        'stopped_by_user': True
                    }

            except Exception as e:
                logger.warning(f"⚠️ [PROCESS-WRAPPER] Error checking stop signal: {e}")
                # Stop 신호 체크 실패해도 프로세스는 계속 진행

            time.sleep(check_interval)

        # 프로세스 정상 완료 - 출력 스레드 완료 대기
        logger.info(f"📊 [PROCESS-WRAPPER] Process finished, waiting for output threads...")

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        returncode = process.returncode

        if returncode == 0:
            logger.info(f"✅ [PROCESS-WRAPPER] Process completed successfully with return code: {returncode}")
        else:
            logger.warning(f"⚠️ [PROCESS-WRAPPER] Process completed with error return code: {returncode}")

        # ✅ Shared Memory에서 완료된 프로세스 제거
        shared_state.remove_current_process(self.worker_id, process.pid)
        logger.debug(f"🗑️ [PROCESS-WRAPPER] Removed completed process PID {process.pid} for worker {self.worker_id}")

        return {
            'success': returncode == 0,
            'return_code': returncode,  # 새로운 키 이름
            'returncode': returncode,   # 기존 호환성을 위해 유지
            'stdout': '\n'.join(stdout_lines),
            'stderr': '\n'.join(stderr_lines),
            'stopped_by_user': False
        }
    
    def wait_for_completion(self, process: subprocess.Popen, check_interval: float = 0.1) -> dict:
        """
        호환성을 위한 구 버전 메서드
        향후 제거 예정 - run_command()를 직접 사용하세요
        """
        logger.warning("⚠️ [PROCESS-WRAPPER] wait_for_completion()은 deprecated입니다. run_command()를 직접 사용하세요.")
        return self._wait_for_process(process, check_interval)
    
    def register_cleanup(self, func: Callable, *args, **kwargs):
        """
        정리 함수 등록
        
        Args:
            func: 정리 함수
            *args, **kwargs: 함수에 전달할 인수들
        """
        def wrapper():
            try:
                logger.info(f"🧹 [PROCESS-WRAPPER] Running cleanup function: {func.__name__}")
                func(*args, **kwargs)
            except Exception as e:
                logger.error(f"❌ [PROCESS-WRAPPER] Cleanup function {func.__name__} failed: {e}")
        
        self.cleanup_functions.append(wrapper)
        
        # TODO: Shared State를 통한 정리 함수 등록은 향후 구현 예정
        # 현재는 로컬 cleanup_functions 리스트만 사용
        
        logger.debug(f"📝 [PROCESS-WRAPPER] Registered cleanup function: {func.__name__}")
    
    def cleanup(self):
        """등록된 모든 정리 함수들 실행"""
        if not self.cleanup_functions:
            return

        logger.info(f"🧹 [PROCESS-WRAPPER] Running {len(self.cleanup_functions)} cleanup functions...")

        for cleanup_func in self.cleanup_functions:
            cleanup_func()

        # 실행 후 정리
        self.cleanup_functions.clear()
        logger.info(f"✅ [PROCESS-WRAPPER] All cleanup functions completed")

    def __enter__(self):
        """컨텍스트 매니저 진입 (with 문 지원)"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료 - 자동 정리"""
        self.cleanup()
        return False

    def __del__(self):
        """소멸자 - 자동 정리"""
        try:
            self.cleanup()
        except Exception as e:
            # 소멸자에서 예외 발생 시 조용히 무시 (로깅도 안전하지 않을 수 있음)
            pass

    # _graceful_terminate와 _flush_process_buffers 메서드 제거됨
    # ProcessPoolExecutor가 모든 프로세스 종료를 처리하므로 불필요


# 공통 정리 함수들
def cleanup_temp_directory(temp_dir: str):
    """임시 디렉토리 정리"""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"🧹 Cleaned up temp directory: {temp_dir}")


def cleanup_temp_file(temp_file: str):
    """임시 파일 정리"""
    if os.path.exists(temp_file):
        os.remove(temp_file)
        logger.info(f"🧹 Cleaned up temp file: {temp_file}")


def cleanup_temp_files(file_patterns: List[str]):
    """임시 파일들 정리 (패턴 매칭)"""
    import glob
    
    for pattern in file_patterns:
        for file_path in glob.glob(pattern):
            try:
                os.remove(file_path)
                logger.info(f"🧹 Cleaned up temp file: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to clean up {file_path}: {e}")
