"""
Server file copy functionality for VizR pipeline
서버 파일 복사 관련 함수들
"""

import json
import os
import shutil
import sqlite3
import threading
import logging
import time
import multiprocessing as mp
from typing import Dict, List, Any, Optional

# Process wrapper 및 ProcessPoolRunner 추가
from backend.pipeline.utils.process_wrapper import ProcessWrapper
from backend.pipeline.utils.process_runner import ProcessPoolRunner
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.redis_broker import get_redis_broker

from ..utils import (
    get_workbench_id_from_step,
    format_size,
    verify_copied_files,
    log_download_info,
    ensure_output_directory,
    create_download_result_template
)
from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.utils.files import decompress_single_file

# 통합 로깅 시스템 사용
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__)


def get_user_name_from_workbench(workbench_id: int) -> Optional[str]:
    """워크벤치 ID로부터 사용자명 추출"""
    try:
        with database.get_db_connection() as conn:
            result = conn.execute('''
                SELECT u.username
                FROM vizr_workbench w
                LEFT JOIN users u ON w.user_id = u.id
                WHERE w.id = ?
            ''', (workbench_id,)).fetchone()

            if result:
                username = result['username']
                logger.info(f"🔍 [USER-LOOKUP] Workbench {workbench_id} belongs to user: {username}")
                return username
            else:
                logger.warning(f"⚠️ [USER-LOOKUP] No user found for workbench {workbench_id}")
                return None

    except Exception as e:
        logger.error(f"❌ [USER-LOOKUP] Error getting user for workbench {workbench_id}: {str(e)}")
        return None


def execute_server_copy(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    """서버 경로에서 파일 복사 - 코디네이터"""
    logger.info("📁 🚚 SERVER COPY OPERATION - COORDINATOR 🚚")
    
    try:
        # 매개변수 추출
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        server_file_paths = parameters.get('serverFilePaths', '')
        
        # 워크벤치 정보 가져오기
        workbench_id = get_workbench_id_from_step(job_step)
        
        with database.get_db_connection() as db_connection:
            cursor = db_connection.cursor()
            cursor.execute("""
                SELECT * FROM vizr_workbench 
                WHERE id = ?
            """, (workbench_id,))
            workbench = cursor.fetchone()
            
        if not workbench:
            raise ValueError(f"Workbench {workbench_id} not found")
            
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        output_dir = workbench_schema["quanti"]["raw"]
        
        logger.info(f"[SERVER_COPY] Configuration:")
        logger.info(f"   🏷️  workbench_id: {workbench_id}")
        logger.info(f"   📂 output_dir: {output_dir}")
        logger.info(f"   📄 server_file_paths: {server_file_paths}")
        
        # 서버 파일 경로들을 줄바꿈으로 분리
        if not server_file_paths:
            logger.error("❌ [SERVER_COPY] No server file paths provided")
            results = create_download_result_template()
            results['stderr'] = 'No server file paths provided'
            results['success'] = False
            return results
        
        source_files = [path.strip() for path in server_file_paths.split('\n') if path.strip()]
        logger.info(f"[SERVER_COPY] Parsed {len(source_files)} source files")
        
        # 출력 디렉토리 생성
        ensure_output_directory(output_dir)
        
        # 파일별 sample_info 생성
        sample_info_list = []
        for source_file in source_files:
            target_basename = os.path.basename(source_file)
            target_file = os.path.join(output_dir, target_basename)
            
            sample_info = {
                'source_file': source_file,
                'target_dir': output_dir,
                'target_file': target_file
            }
            sample_info_list.append(sample_info)
        
        logger.info(f"🎯 [SERVER_COPY] Prepared {len(sample_info_list)} sample_info entries for processing")

        # Progress detail 초기화 - Job Generator가 생성한 download step에 저장
        _initialize_progress_detail(workbench_id, source_files, worker_id)

        # execute_server_copy_multi 호출 (workbench_id 전달)
        result = execute_server_copy_multi(sample_info_list, parameters, worker_id, workbench_id)
        
        # 결과 검증이 필요한 경우
        if result.get('success', False) and result.get('copied_files'):
            try:
                verify_copied_files(result['copied_files'], output_dir)
                result['stdout'] += "File integrity verification passed\n"
                logger.info(f"✅ [SERVER_COPY] File integrity verification passed")
            except Exception as verify_error:
                logger.warning(f"⚠️ [SERVER_COPY] File verification failed: {verify_error}")
                # 검증 실패해도 복사는 성공으로 유지
        
        return result
        
    except Exception as e:
        error_msg = f"Server copy coordinator failed: {str(e)}"
        logger.error(f"❌ [SERVER_COPY] {error_msg}")
        
        # 기본 결과 템플릿 반환
        results = create_download_result_template()
        results['stderr'] = error_msg
        results['success'] = False
        return results


def execute_server_copy_multi(sample_info_list: List[Dict], parameters: Dict, worker_id: str = "worker", workbench_id: int = None) -> Dict[str, str]:
    """ProcessPoolRunner를 사용한 병렬 서버 파일 복사"""
    logger.info(f"🚀 [SERVER-MULTI] Starting parallel server copy (worker: {worker_id}, workbench: {workbench_id})")
    logger.info(f"   📊 Total files to process: {len(sample_info_list)}")

    # SharedState에서 worker event 가져오기
    try:
        worker_stop_event = shared_state.get_worker_event(worker_id)
    except ValueError:
        worker_stop_event = None

    if not worker_stop_event:
        logger.warning(f"⚠️ [SERVER-MULTI] No stop event found for worker {worker_id}")
    
    # 결과 템플릿 초기화
    results = create_download_result_template()
    
    try:
        # 워커 수 결정 (파일 수와 4 중 작은 값)
        max_workers = min(4, len(sample_info_list))
        logger.info(f"🔧 [SERVER-MULTI] Using {max_workers} workers for {len(sample_info_list)} files")

        # 프로세스 간 공유 Lock 생성 (Manager를 통한 진정한 프로세스 간 공유)
        manager = mp.Manager()
        shared_db_lock = manager.Lock()
        logger.info(f"🔒 [SERVER-MULTI] Created shared DB lock for multiprocessing (lock_id={id(shared_db_lock)})")

        # 작업 인수 준비 (workbench_id와 worker_id 추가)
        work_args = [(sample_info, parameters, worker_id, workbench_id) for sample_info in sample_info_list]
        logger.info(f"🚀 [SERVER-MULTI-POOL] Starting ProcessPoolRunner with {len(work_args)} samples...")

        # ProcessPoolRunner로 병렬 처리 (Event 기반 stop 신호 + 공유 DB Lock)
        with ProcessPoolRunner(max_workers=max_workers, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
            # 각 파일 복사 작업을 병렬로 실행
            sample_results = list(runner.map_unordered(run_single_server_copy, work_args))
            
            logger.info(f"🎯 [SERVER-MULTI-POOL] ProcessPoolRunner completed, processing {len(sample_results)} results...")
            
            # 결과 처리
            total_size = 0
            copied_count = 0
            failed_count = 0
            stopped_by_user = False
            
            for result in sample_results:
                if result.get('stopped_by_user', False):
                    logger.warning(f"🛑 [SERVER-MULTI] Sample processing stopped by user")
                    runner.stop()
                    # Reset worker event for next execution
                    shared_state.reset_worker(worker_id)
                    stopped_by_user = True
                    break
                
                if result.get('success', False):
                    results['copied_files'].append(result['source_file'])
                    total_size += result.get('copied_size', 0)
                    copied_count += 1
                    logger.info(f"   ✅ Successfully copied: {result['source_file']} ({format_size(result.get('copied_size', 0))})")
                    results['stdout'] += f"Copied: {result['source_file']} ({format_size(result.get('copied_size', 0))})\\n"
                else:
                    failed_count += 1
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"   ❌ Failed to copy: {result['source_file']} - {error_msg}")
                    results['stderr'] += f"Failed: {result['source_file']} - {error_msg}\\n"
            
            # 사용자 중단 처리
            if stopped_by_user:
                logger.warning(f"🛑 [SERVER-MULTI] Multi-sample processing stopped by user")
                results['stderr'] = 'Server copy stopped by user signal'
                results['success'] = False
                return results
        
        # 결과 요약
        logger.info(f"🎉 [SERVER-MULTI] Multi-sample processing completed!")
        logger.info(f"   📊 Total files processed: {len(sample_info_list)}")
        logger.info(f"   ✅ Successfully copied: {copied_count}")
        logger.info(f"   ❌ Failed copies: {failed_count}")
        logger.info(f"   💾 Total data size: {format_size(total_size)}")
        
        # 성공 여부 결정
        if copied_count > 0 and failed_count == 0:
            results['success'] = True
            summary = f"Server copy completed: {copied_count} files, {format_size(total_size)} total"
            logger.info(summary)
            results['stdout'] += f"\\n{summary}\\n"
        elif copied_count > 0 and failed_count > 0:
            results['success'] = False  # 일부 실패
            summary = f"Server copy partially completed: {copied_count} success, {failed_count} failed"
            logger.warning(summary)
            results['stdout'] += f"\\n{summary}\\n"
        else:
            results['success'] = False  # 전체 실패
            error_msg = f"All server copy operations failed: {failed_count} files"
            logger.error(error_msg)
            results['stderr'] += error_msg
        
        return results
        
    except Exception as e:
        error_msg = f"Multi-sample server copy failed: {str(e)}"
        logger.error(f"❌ [SERVER-MULTI] {error_msg}")
        results['stderr'] = error_msg
        results['success'] = False
        return results


def run_single_server_copy(sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """단일 파일 서버 복사 실행 - ProcessPoolRunner용 (청크 단위 복사 및 Redis 진행률)"""

    # 통합 로깅 시스템으로 멀티프로세싱 환경에서도 간단하게 설정
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')  # DEBUG 레벨 직접 지정

    logger.info(f"[POOL] worker initialized (pid={mp.current_process().pid})")

    # Stop event 수신 확인 로깅
    if stop_event:
        logger.info(f"🔍 [SERVER-SINGLE-INIT] Stop event received - Initial state: {'SET' if stop_event.is_set() else 'NOT SET'} (id={id(stop_event)})")
    else:
        logger.warning(f"⚠️  [SERVER-SINGLE-INIT] No stop event received - User cancellation not available")

    # ✅ 워커 함수 초기에 stop event 체크 (FastQC 패턴)
    if stop_event and stop_event.is_set():
        logger.warning(f"🛑 [SERVER-SINGLE] Stop signal detected before starting file copy")
        return {
            'success': False,
            'error': 'File copy stopped by user before starting',
            'source_file': sample_info.get('source_file', 'unknown'),
            'copied_size': 0,
            'stopped_by_user': True
        }

    logger.info(f"📄 [SERVER-SINGLE] Starting single file copy (worker: {worker_id}, workbench: {workbench_id})")
    logger.info(f"🔍 [DEBUG] Redis broker available: {get_redis_broker().is_available()}")

    try:
        # sample_info 구조: {'source_file': path, 'target_dir': path, 'target_file': path}
        source_file = sample_info['source_file']
        target_dir = sample_info['target_dir']
        target_file = sample_info['target_file']
        file_name = os.path.basename(source_file)

        logger.info(f"   📥 FROM: {source_file}")
        logger.info(f"   📤 TO:   {target_file}")

        # 파일 존재 확인
        if not os.path.exists(source_file):
            error_msg = f"Source file does not exist: {source_file}"
            logger.error(f"   ❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'source_file': source_file,
                'copied_size': 0,
                'stopped_by_user': False
            }

        # 파일 크기 확인
        file_size = os.path.getsize(source_file)
        logger.info(f"   📊 File size: {file_size:,} bytes ({format_size(file_size)})")

        # 타겟 디렉토리 생성
        os.makedirs(target_dir, exist_ok=True)

        # Redis broker 초기화
        redis_broker = get_redis_broker()

        # 청크 단위 파일 복사 (진행률 추적)
        chunk_size = 1024 * 1024  # 1MB chunks
        copied_bytes = 0
        last_progress_percent = -1
        chunk_count = 0

        try:
            with open(source_file, 'rb') as src, open(target_file, 'wb') as dst:
                while (chunk := src.read(chunk_size)):
                    chunk_count += 1

                    # ✅ stop_event로 중단 신호 확인
                    if stop_event and stop_event.is_set():
                        logger.warning(f"🛑 [COPY-STOP-DETECTED] Stop signal detected at chunk {chunk_count}")
                        logger.warning(f"🛑 [SERVER-SINGLE] File copy stopped by user: {source_file}")
                        logger.info(f"   📊 Processed {chunk_count} chunks ({copied_bytes:,} bytes) before stopping")
                        # 부분적으로 복사된 파일 삭제
                        if os.path.exists(target_file):
                            os.remove(target_file)
                            logger.info(f"   🗑️  Removed partial file: {os.path.basename(target_file)}")
                        return {
                            'success': False,
                            'error': 'File copy stopped by user',
                            'source_file': source_file,
                            'copied_size': 0,
                            'stopped_by_user': True
                        }

                    # 청크 쓰기
                    dst.write(chunk)
                    copied_bytes += len(chunk)

                    # 진행률 계산 및 Redis 전송
                    if file_size > 0:
                        progress_percent = int((copied_bytes / file_size) * 100)
                        # 진행률이 변경되었을 때만 전송 (성능 최적화)
                        if progress_percent != last_progress_percent:
                            last_progress_percent = progress_percent
                            logger.debug(f"🔍 [DEBUG] Progress changed! File: {file_name}, {progress_percent}%, workbench_id: {workbench_id}, redis_available: {redis_broker.is_available()}")

                            # Redis로 진행률 전송
                            if workbench_id and redis_broker.is_available():
                                progress_data = {
                                    'worker_id': worker_id,
                                    'srr_run': file_name,  # NCBI와 동일한 필드명 사용
                                    'file_name': file_name,
                                    'progress_percent': progress_percent,
                                    'copied_bytes': copied_bytes,
                                    'total_bytes': file_size,
                                    'timestamp': time.time()
                                }

                                # NCBI와 동일한 task_type 사용하여 프론트엔드 수정 최소화
                                redis_broker.publish_progress(
                                    workbench_id=workbench_id,
                                    task_type='data_download',  # 모든 데이터 다운로드 작업에 통일된 타입 사용
                                    progress_data=progress_data
                                )
                                logger.debug(f"📡 [REDIS-PUBLISH] Server copy progress sent - File: {file_name}, Progress: {progress_percent}%, Workbench: {workbench_id}")

                                # 데이터베이스에 진행상황 저장 (10% 단위로)
                                if progress_percent % 10 == 0:
                                    try:
                                        _save_progress_to_db(
                                            workbench_id=workbench_id,
                                            worker_id=worker_id,
                                            file_name=file_name,
                                            progress_data=progress_data,
                                            status='running',
                                            shared_db_lock=shared_db_lock
                                        )
                                    except Exception as db_error:
                                        logger.warning(f"⚠️ [DB-SAVE] Failed to save progress to database: {db_error}")

                            else:
                                if not workbench_id:
                                    logger.warning(f"⚠️ [REDIS-PUBLISH] No workbench_id provided for progress update")
                                if not redis_broker.is_available():
                                    logger.warning(f"⚠️ [REDIS-PUBLISH] Redis not available for progress update")

                                # 진행률 로그 (10% 단위로만)
                                if progress_percent % 10 == 0:
                                    logger.info(f"   📊 [SERVER-SINGLE] {file_name}: {progress_percent}% ({format_size(copied_bytes)}/{format_size(file_size)})")

            # 파일 속성 복사 (timestamps, permissions)
            shutil.copystat(source_file, target_file)

        except Exception as copy_error:
            error_msg = f"Error during file copy: {str(copy_error)}"
            logger.error(f"   ❌ {error_msg}")
            # 부분적으로 복사된 파일 삭제
            if os.path.exists(target_file):
                os.remove(target_file)
            return {
                'success': False,
                'error': error_msg,
                'source_file': source_file,
                'copied_size': copied_bytes,
                'stopped_by_user': False
            }

        # 복사된 파일 검증
        if os.path.exists(target_file):
            copied_size = os.path.getsize(target_file)
            if copied_size != file_size:
                error_msg = f"File size mismatch! Source: {file_size}, Target: {copied_size}"
                logger.error(f"   ❌ {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'source_file': source_file,
                    'copied_size': copied_size,
                    'stopped_by_user': False
                }
        else:
            error_msg = f"Target file does not exist after copy: {target_file}"
            logger.error(f"   ❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'source_file': source_file,
                'copied_size': 0,
                'stopped_by_user': False
            }

        # 🔓 압축 파일이면 압축 해제
        final_file = target_file
        final_size = file_size

        if target_file.endswith('.gz'):
            logger.info(f"📦 [SERVER-SINGLE] Decompressing gzip file: {os.path.basename(target_file)}")

            # Stop event 상태 확인 및 로깅
            if stop_event:
                logger.info(f"🔍 [SERVER-SINGLE-STOP] Passing stop_event to decompress - Current state: {'SET' if stop_event.is_set() else 'NOT SET'} (id={id(stop_event)})")
            else:
                logger.warning(f"⚠️  [SERVER-SINGLE-STOP] No stop_event available for decompression - User cannot cancel during decompression")

            try:
                # ✅ stop_event 전달하여 압축 해제 중에도 중단 가능
                # ✅ remove_original=False: 압축 파일 보존 (post-process에서 압축 해제된 파일만 삭제)
                decompressed_file = decompress_single_file(target_file, logger, remove_original=False, stop_event=stop_event)
                final_file = decompressed_file
                final_size = os.path.getsize(decompressed_file)
                logger.info(f"   ✅ Decompressed to: {os.path.basename(decompressed_file)} ({format_size(final_size)})")
                logger.info(f"   💾 Preserved compressed file: {os.path.basename(target_file)}")

                # Redis로 압축 해제 완료 알림
                if workbench_id and redis_broker.is_available():
                    decompression_data = {
                        'worker_id': worker_id,
                        'srr_run': file_name,
                        'file_name': os.path.basename(decompressed_file),
                        'progress_percent': 100,
                        'copied_bytes': final_size,
                        'total_bytes': final_size,
                        'status': 'decompressed',
                        'timestamp': time.time()
                    }
                    redis_broker.publish_progress(
                        workbench_id=workbench_id,
                        task_type='data_download',
                        progress_data=decompression_data
                    )
                    logger.debug(f"📡 [REDIS-PUBLISH] Decompression completion sent - File: {file_name}")

            except Exception as decompress_error:
                # ✅ 사용자 중단 여부 확인
                if "stopped by user" in str(decompress_error).lower():
                    logger.warning(f"🛑 [SERVER-SINGLE] Decompression stopped by user: {os.path.basename(target_file)}")
                    # 압축 파일도 삭제
                    if os.path.exists(target_file):
                        os.remove(target_file)
                    return {
                        'success': False,
                        'error': 'Decompression stopped by user',
                        'source_file': source_file,
                        'copied_size': 0,
                        'stopped_by_user': True
                    }

                logger.warning(f"⚠️ [SERVER-SINGLE] Decompression failed: {decompress_error}")
                logger.warning(f"   Keeping compressed file: {os.path.basename(target_file)}")
                # 압축 해제 실패 시 압축 파일 그대로 사용

        logger.info(f"🎉 [SERVER-SINGLE] File copy completed successfully: {source_file} ({format_size(final_size)})")

        # 복사 완료 알림 및 DB 저장 (압축 해제 이후)
        if workbench_id and redis_broker.is_available():
            completion_data = {
                'worker_id': worker_id,
                'srr_run': file_name,
                'file_name': os.path.basename(final_file),
                'progress_percent': 100,
                'copied_bytes': final_size,
                'total_bytes': final_size,
                'status': 'completed',
                'timestamp': time.time()
            }
            redis_broker.publish_progress(
                workbench_id=workbench_id,
                task_type='data_download',
                progress_data=completion_data
            )
            logger.debug(f"📡 [REDIS-PUBLISH] Server copy completion sent - File: {file_name}, Workbench: {workbench_id}")

            # 데이터베이스에 완료 상태 저장
            try:
                _save_progress_to_db(
                    workbench_id=workbench_id,
                    worker_id=worker_id,
                    file_name=os.path.basename(final_file),
                    progress_data=completion_data,
                    status='completed',
                    shared_db_lock=shared_db_lock
                )
            except Exception as db_error:
                logger.warning(f"⚠️ [DB-SAVE] Failed to save completion to database: {db_error}")

        else:
            if not workbench_id:
                logger.warning(f"⚠️ [REDIS-PUBLISH] No workbench_id for completion notification")
            if not redis_broker.is_available():
                logger.warning(f"⚠️ [REDIS-PUBLISH] Redis not available for completion notification")

        return {
            'success': True,
            'source_file': source_file,
            'target_file': final_file,
            'copied_size': final_size,
            'stopped_by_user': False
        }

    except Exception as e:
        error_msg = f"Single file copy failed: {str(e)}"
        logger.error(f"❌ [SERVER-SINGLE] {error_msg}")
        return {
            'success': False,
            'error': error_msg,
            'source_file': sample_info.get('source_file', 'unknown'),
            'copied_size': 0,
            'stopped_by_user': False
        }


def _initialize_progress_detail(workbench_id: int, input_files: List[str], worker_id: str):
    """
    파일 스캔 완료 후 progress_detail 초기값 생성
    Job Generator가 생성한 download step에 모든 파일의 초기 상태를 설정

    Args:
        workbench_id: 워크벤치 ID
        input_files: 다운로드할 파일 경로 리스트
        worker_id: 워커 ID
    """
    # 프로세스 정보 수집
    current_process = mp.current_process()
    process_info = f"PID={current_process.pid}, Name={current_process.name}"

    # 진행상황 초기화 시작 (메인 프로세스에서 실행, Lock 불필요)
    logger.info(f"🔧 [INIT-PROGRESS] Starting progress detail initialization - {process_info}, Files: {len(input_files)}, Workbench: {workbench_id}")

    try:
        # Job Generator가 생성한 download step 찾기
        existing_step = database.execute_query(
            """
            SELECT id, progress_detail, job_id, step_id
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'download'
                """,
                (workbench_id,)
        )

        if not existing_step:
            logger.warning(f"⚠️ [INIT-PROGRESS] No download step found for workbench {workbench_id}. Job Generator may not have created it yet.")
            logger.info(f"🔚 [INIT-PROGRESS] Progress initialization aborted - no step found")
            return

        step_record = existing_step[0]

        # 파일별 초기 정보 수집
        total_size = 0
        files_detail = {}

        for file_path in input_files:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            total_size += file_size

            files_detail[file_name] = {
                "status": "pending",
                "progress": 0,
                "file_size": file_size,
                "downloaded_size": 0,
                "timestamp": time.time()
            }

        # 초기 progress_detail 구조 생성
        progress_detail = {
            "summary": {
                "total_files": len(input_files),
                "downloading_files": 0,
                "completed_files": 0,
                "pending_files": len(input_files),
                "last_updated": time.time(),
                "total_size": total_size,
                "downloaded_size": 0
            },
            "files": files_detail
        }

        # JSON 문자열로 변환
        progress_json = json.dumps(progress_detail)

        # Job Generator가 생성한 download step 레코드 업데이트
        database.execute_update(
        """
            UPDATE pipeline_job_steps
            SET progress_detail = ?,
                status = 'pending',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (progress_json, step_record['id'])
        )

        logger.info(f"✅ [INIT-PROGRESS] Progress detail initialized for workbench {workbench_id}")
        logger.info(f"   📊 Total files: {len(input_files)}, Total size: {format_size(total_size)}")
        logger.info(f"🏁 [INIT-PROGRESS] Progress initialization completed successfully")

    except Exception as e:
        logger.error(f"❌ [INIT-PROGRESS] Failed to initialize progress detail for workbench {workbench_id}: {e}")
        logger.info(f"🔚 [INIT-PROGRESS] Progress initialization failed, but copy operation will continue")
        # 초기화 실패해도 복사 작업은 계속 진행


def _update_summary_stats(progress_json_data: Dict[str, Any]):
    """
    파일별 진행상황을 기반으로 summary 통계 자동 계산

    Args:
        progress_json_data: progress_detail JSON 데이터 (수정됨)
    """
    all_files = progress_json_data.get('files', {})

    # 🔧 상태 일관성 보장: 100% 완료된 파일의 status를 자동으로 completed로 수정
    for file_name, file_data in all_files.items():
        if file_data.get('progress', 0) == 100 and file_data.get('status') != 'completed':
            file_data['status'] = 'completed'

    # 파일 상태별 개수 계산 (상태 일관성 보정 후)
    total_files = len(all_files)
    completed_files = sum(1 for f in all_files.values() if f.get('status') == 'completed')
    downloading_files = sum(1 for f in all_files.values() if f.get('status') == 'downloading')
    pending_files = sum(1 for f in all_files.values() if f.get('status') == 'pending')

    # 크기별 통계 계산
    total_size = sum(f.get('file_size', 0) for f in all_files.values())
    downloaded_size = sum(f.get('downloaded_size', 0) for f in all_files.values())

    # Summary 업데이트
    logger.debug(f"📊 [SUMMARY-UPDATE] Calculated stats: total={total_files}, completed={completed_files}, downloading={downloading_files}, pending={pending_files}")
    progress_json_data['summary'] = {
        "total_files": total_files,
        "downloading_files": downloading_files,
        "completed_files": completed_files,
        "pending_files": pending_files,
        "last_updated": time.time(),
        "total_size": total_size,
        "downloaded_size": downloaded_size
    }


def _save_progress_to_db(workbench_id: int, worker_id: str, file_name: str, progress_data: Dict[str, Any], status: str, shared_db_lock=None):
    """
    Job Generator가 생성한 download step 레코드의 progress_detail을 업데이트
    워크벤치당 하나의 download 레코드에 모든 파일들의 진행상황이 포함됨

    Args:
        workbench_id: 워크벤치 ID
        worker_id: 워커 ID
        file_name: 파일명
        progress_data: 진행상황 데이터 (Redis 포맷)
        status: 전체 step의 status ('pending', 'running', 'completed' 등)
        shared_db_lock: 멀티프로세스 간 공유 DB 락 (필수)
    """
    # 프로세스 정보 수집
    current_process = mp.current_process()
    process_info = f"PID={current_process.pid}, Name={current_process.name}"
    progress_percent = progress_data.get('progress_percent', 0)

    # Lock 진입 시도 로그
    logger.debug(f"🔒 [DB-LOCK-ENTER] PID={current_process.pid} ATTEMPTING lock acquisition - {process_info}, File: {file_name}, Progress: {progress_percent}%, Workbench: {workbench_id}")

    # 전달받은 shared_db_lock 사용 (ProcessPoolRunner에서 자동 주입됨)
    if shared_db_lock is not None:
        # 전달받은 Lock 사용
        with shared_db_lock:
            logger.debug(f"✅ [DB-LOCK-ACQUIRED] PID={current_process.pid} ENTERED critical section WITH SHARED LOCK - {process_info}, File: {file_name}, Progress: {progress_percent}%")
            _execute_database_operations_impl(current_process, process_info, file_name, progress_percent, workbench_id, progress_data, status)
    else:
        logger.error(f"❌ [DB-LOCK] No shared_db_lock provided - this should not happen!")
        return


def _execute_database_operations_impl(current_process, process_info: str, file_name: str, progress_percent: int, workbench_id: int, progress_data: Dict[str, Any], status: str):
    """실제 데이터베이스 작업을 수행하는 구현 함수

    Args:
        current_process: 현재 프로세스 객체
        process_info: 프로세스 정보 문자열
        file_name: 파일명
        progress_percent: 진행률 퍼센트
        workbench_id: 워크벤치 ID
        progress_data: 진행상황 데이터
        status: 전체 step의 status ('pending', 'running', 'completed' 등)
    """
    try:
        # Job Generator가 생성한 download step 찾기 (step_name="download"로 검색)
        existing_step = database.execute_query(
            """
            SELECT id, progress_detail, job_id, step_id
            FROM pipeline_job_steps
            WHERE workbench_id = ? AND step_name = 'download'
            """,
            (workbench_id,)
        )

        # SELECT 결과 로그 출력
        if existing_step:
            step_record = existing_step[0]

        if not existing_step:
            logger.warning(f"⚠️ [DB-SAVE] No download step found for workbench {workbench_id}. Job Generator may not have created it yet.")
            return

        step_record = existing_step[0]

        # 기존 진행상황 파싱 또는 초기화
        if step_record.get('progress_detail'):
            try:
                progress_json_data = json.loads(step_record['progress_detail'])
            except (json.JSONDecodeError, TypeError):
                progress_json_data = {'files': {}}
        else:
            progress_json_data = {'files': {}}

        # 현재 파일의 진행상황 업데이트
        progress_json_data['files'][file_name] = {
            'progress': progress_data.get('progress_percent', 0),
            'file_size': progress_data.get('total_bytes', 0),
            'downloaded_size': progress_data.get('copied_bytes', 0),
            'status': progress_data.get('status', 'downloading'),
            'timestamp': progress_data.get('timestamp', time.time())
        }

        # Summary 통계 자동 계산 및 업데이트
        _update_summary_stats(progress_json_data)

        # JSON 문자열로 변환
        progress_json = json.dumps(progress_json_data)

        # UPDATE 직전 상태 로그 출력
        logger.debug(f"💾 [DB-UPDATE-BEFORE] PID={current_process.pid} About to update step id={step_record['id']}, File: {file_name}, Status: {status}")

        # 기존 레코드 업데이트 (Job Generator가 생성한 레코드)
        database.execute_update(
            """
            UPDATE pipeline_job_steps
            SET progress_detail = ?,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (progress_json, status, step_record['id'])
        )

        logger.debug(f"💾 [DB-UPDATE-AFTER] PID={current_process.pid} Successfully updated step id={step_record['id']}, File: {file_name}")

        logger.debug(f"💾 [DB-SAVE] Progress updated in download step record - File: {file_name}, Progress: {progress_data.get('progress_percent', 0)}%, Status: {status}")

        # Lock 해제 직전 로그 (공유 Lock 사용)
        logger.debug(f"🔓 [DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, File: {file_name}, Progress: {progress_percent}%, Operation: SUCCESS")

    except Exception as e:
        logger.error(f"❌ [DB-SAVE] Failed to save progress for {file_name}: {e}")
        # Lock 해제 직전 로그 (에러 상황, 공유 Lock 사용)
        logger.debug(f"🔓 [DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, File: {file_name}, Progress: {progress_percent}%, Operation: ERROR")
        raise


def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 server tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering server tool...")
    
    metadata = {
        'name': 'server',
        'description': 'Server file copy functionality',
        'version': '1.0.0',
        'supported_formats': ['.fastq', '.fastq.gz', '.fq', '.fq.gz'],
        'parameters': {
            'dataInputMethod': 'server'
        }
    }
    
    return coordinator.register_tool('server', execute_server_copy, metadata)