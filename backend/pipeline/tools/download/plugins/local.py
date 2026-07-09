"""
Local file copy functionality for VizR pipeline
로컬 파일 복사 관련 함수들
"""

import json
import os
import shutil
import sqlite3
import logging
import time
import threading
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
from backend.utils.files import decompress_single_file, is_gzip_file
from config.shared_config import SharedConfig

logger = logging.getLogger(__name__)

# TODO: Implement proper shared lock mechanism via ProcessPoolRunner
# _db_lock removed - was not working due to multiprocessing isolation


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


def execute_local_copy(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    """로컬 임시 파일 복사 - 코디네이터"""
    logger.info("🔍 [LOCAL_COPY] Starting local copy operation...")
    
    try:
        # 매개변수 추출
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        
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
        
        logger.info(f"[LOCAL_COPY] Configuration:")
        logger.info(f"   🏷️  workbench_id: {workbench_id}")
        logger.info(f"   📂 output_dir: {output_dir}")

        # 사용자 정보 가져오기
        user_name = get_user_name_from_workbench(workbench_id)
        if not user_name:
            raise Exception(f"Unable to get user name for workbench {workbench_id}")
        
        # 실제 업로드 파일 위치 - Dynamic File Discovery
        upload_dir = os.path.join(SharedConfig.VIZR_PATH, "users", user_name, "tmp")
        logger.info(f"📁 [LOCAL_COPY] Scanning upload directory: {upload_dir}")
        logger.info(f"   User tmp folder: {upload_dir}")
        
        # 업로드된 파일 목록 동적 스캔
        input_files = []
        if os.path.exists(upload_dir):
            for file_name in os.listdir(upload_dir):
                if file_name.endswith(('.fastq', '.fastq.gz', '.fq', '.fq.gz')):
                    full_path = os.path.join(upload_dir, file_name)
                    if os.path.isfile(full_path):
                        input_files.append(full_path)
                        file_size = os.path.getsize(full_path)
                        logger.info(f"   ✅ Found: {file_name} ({format_size(file_size)})")
        else:
            logger.warning(f"⚠️ [LOCAL_COPY] Upload directory does not exist: {upload_dir}")

        # tmp가 비어있으면 raw 폴더 확인 (이미 파일이 있을 수 있음)
        if not input_files:
            logger.info(f"📁 [LOCAL_COPY] No files in tmp directory, checking raw directory: {output_dir}")

            if os.path.exists(output_dir):
                raw_files = []
                for file_name in os.listdir(output_dir):
                    if file_name.endswith(('.fastq', '.fastq.gz', '.fq', '.fq.gz')):
                        full_path = os.path.join(output_dir, file_name)
                        if os.path.isfile(full_path):
                            raw_files.append(full_path)
                            file_size = os.path.getsize(full_path)
                            logger.info(f"   ✅ Found in raw: {file_name} ({format_size(file_size)})")

                if raw_files:
                    logger.info(f"✅ [LOCAL_COPY] Found {len(raw_files)} files already in raw directory, skipping download")

                    # 성공 결과 반환
                    results = create_download_result_template()
                    results['success'] = True
                    results['copied_files'] = raw_files
                    results['stdout'] = f"Download step skipped: {len(raw_files)} files already exist in raw directory\n"

                    for raw_file in raw_files:
                        file_size = os.path.getsize(raw_file)
                        results['stdout'] += f"Existing: {os.path.basename(raw_file)} ({format_size(file_size)})\n"

                    return results

            # tmp도 비어있고 raw도 비어있으면 에러
            raise Exception(f"No FASTQ files found in upload directory ({upload_dir}) or raw directory ({output_dir})")
        
        logger.info(f"📁 [LOCAL_COPY] Found {len(input_files)} files for processing")
        
        # Progress detail 초기화 - Job Generator가 생성한 download step에 저장
        _initialize_progress_detail(workbench_id, input_files, worker_id)

        # 출력 디렉토리 생성
        ensure_output_directory(output_dir)
        
        # 파일별 sample_info 생성
        sample_info_list = []
        for source_file in input_files:
            source_basename = os.path.basename(source_file)

            # 타임스탬프 prefix 제거 (형식: YYYYMMDD_HHMMSS_mmm_원본파일명)
            # 예: 20251020_194054_701_RH50-rep1_2.fastq.gz -> RH50-rep1_2.fastq.gz
            parts = source_basename.split('_', 3)  # 최대 3번 split (타임스탬프 3부분 제거)
            if len(parts) == 4:
                target_basename = parts[3]  # 원본 파일명만 추출
                logger.info(f"   🔧 Removing timestamp prefix: {source_basename} -> {target_basename}")
            else:
                # 타임스탬프가 없는 경우 (예외 상황) 그대로 사용
                target_basename = source_basename
                logger.warning(f"   ⚠️ No timestamp prefix found, using original name: {source_basename}")

            target_file = os.path.join(output_dir, target_basename)

            sample_info = {
                'source_file': source_file,
                'target_dir': output_dir,
                'target_file': target_file
            }
            sample_info_list.append(sample_info)
        
        logger.info(f"🎯 [LOCAL_COPY] Prepared {len(sample_info_list)} sample_info entries for processing")
        
        # execute_local_copy_multi 호출 (workbench_id 전달)
        result = execute_local_copy_multi(sample_info_list, parameters, worker_id, workbench_id)
        
        # 결과 검증이 필요한 경우
        if result.get('success', False) and result.get('copied_files'):
            try:
                verify_copied_files(result['copied_files'], output_dir)
                result['stdout'] += "File integrity verification passed\n"
                logger.info(f"✅ [LOCAL_COPY] File integrity verification passed")
            except Exception as verify_error:
                logger.warning(f"⚠️ [LOCAL_COPY] File verification failed: {verify_error}")
                # 검증 실패해도 복사는 성공으로 유지

        # 🧹 Move 완료 후 tmp 디렉토리 정리
        if result.get('success', False):
            try:
                if os.path.exists(upload_dir):
                    # tmp 폴더 내 모든 파일 삭제
                    for file_name in os.listdir(upload_dir):
                        file_path = os.path.join(upload_dir, file_name)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            logger.debug(f"🗑️ [CLEANUP] Removed tmp file: {file_name}")

                    # tmp 폴더가 비었으면 폴더도 삭제
                    if not os.listdir(upload_dir):
                        os.rmdir(upload_dir)
                        logger.info(f"🧹 [CLEANUP] Removed empty tmp directory: {upload_dir}")
                    else:
                        logger.info(f"🧹 [CLEANUP] Cleaned tmp files in: {upload_dir}")

                    result['stdout'] += f"Cleaned up temporary upload directory\n"
            except Exception as cleanup_error:
                logger.warning(f"⚠️ [CLEANUP] Failed to clean tmp directory: {cleanup_error}")
                # 정리 실패해도 move 성공 상태는 유지

        return result
        
    except Exception as e:
        error_msg = f"Local copy coordinator failed: {str(e)}"
        logger.error(f"❌ [LOCAL_COPY] {error_msg}")
        
        # 기본 결과 템플릿 반환
        results = create_download_result_template()
        results['stderr'] = error_msg
        results['success'] = False
        return results


def execute_local_copy_multi(sample_info_list: List[Dict], parameters: Dict, worker_id: str = "worker", workbench_id: int = None) -> Dict[str, str]:
    """ProcessPoolRunner를 사용한 병렬 로컬 파일 복사"""
    logger.info(f"🚀 [LOCAL-MULTI] Starting parallel local copy (worker: {worker_id}, workbench: {workbench_id})")
    logger.info(f"   📊 Total files to process: {len(sample_info_list)}")
    
    # SharedState에서 worker event 가져오기
    try:
        worker_stop_event = shared_state.get_worker_event(worker_id)
    except ValueError:
        worker_stop_event = None
    
    if not worker_stop_event:
        logger.warning(f"⚠️ [LOCAL-MULTI] No stop event found for worker {worker_id}")
    
    # 결과 템플릿 초기화
    results = create_download_result_template()
    
    try:
        # 워커 수 결정 (파일 수와 4 중 작은 값)
        max_workers = min(4, len(sample_info_list))
        logger.info(f"🔧 [LOCAL-MULTI] Using {max_workers} workers for {len(sample_info_list)} files")

        # 프로세스 간 공유 Lock 생성 (Manager를 통한 진정한 프로세스 간 공유)
        manager = mp.Manager()
        shared_db_lock = manager.Lock()
        logger.info(f"🔒 [LOCAL-MULTI] Created shared DB lock for multiprocessing (lock_id={id(shared_db_lock)})")

        # 작업 인수 준비 (workbench_id와 worker_id 추가)
        work_args = [(sample_info, parameters, worker_id, workbench_id) for sample_info in sample_info_list]
        logger.info(f"🚀 [LOCAL-MULTI-POOL] Starting ProcessPoolRunner with {len(work_args)} samples...")

        # ProcessPoolRunner로 병렬 처리 (Event 기반 stop 신호 + 공유 DB Lock)
        with ProcessPoolRunner(max_workers=max_workers, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
            # 각 파일 복사 작업을 병렬로 실행
            sample_results = list(runner.map_unordered(run_single_local_copy, work_args))
            
            logger.info(f"🎯 [LOCAL-MULTI-POOL] ProcessPoolRunner completed, processing {len(sample_results)} results...")
            
            # 결과 처리
            total_size = 0
            copied_count = 0
            failed_count = 0
            stopped_by_user = False
            
            for result in sample_results:
                if result.get('stopped_by_user', False):
                    logger.warning(f"🛑 [LOCAL-MULTI] Sample processing stopped by user")
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
                logger.warning(f"🛑 [LOCAL-MULTI] Multi-sample processing stopped by user")
                results['stderr'] = 'Local copy stopped by user signal'
                results['success'] = False
                return results
        
        # 결과 요약
        logger.info(f"🎉 [LOCAL-MULTI] Multi-sample processing completed!")
        logger.info(f"   📊 Total files processed: {len(sample_info_list)}")
        logger.info(f"   ✅ Successfully copied: {copied_count}")
        logger.info(f"   ❌ Failed copies: {failed_count}")
        logger.info(f"   💾 Total data size: {format_size(total_size)}")
        
        # 성공 여부 결정
        if copied_count > 0 and failed_count == 0:
            results['success'] = True
            summary = f"Local copy completed: {copied_count} files, {format_size(total_size)} total"
            logger.info(summary)
            results['stdout'] += f"\\n{summary}\\n"
        elif copied_count > 0 and failed_count > 0:
            results['success'] = False  # 일부 실패
            summary = f"Local copy partially completed: {copied_count} success, {failed_count} failed"
            logger.warning(summary)
            results['stdout'] += f"\\n{summary}\\n"
        else:
            results['success'] = False  # 전체 실패
            error_msg = f"All local copy operations failed: {failed_count} files"
            logger.error(error_msg)
            results['stderr'] += error_msg
        
        return results
        
    except Exception as e:
        error_msg = f"Multi-sample local copy failed: {str(e)}"
        logger.error(f"❌ [LOCAL-MULTI] {error_msg}")
        results['stderr'] = error_msg
        results['success'] = False
        return results


def move_with_progress(source_file: str, target_file: str, file_name: str, file_size: int,
                       worker_id: str, workbench_id: int, redis_broker, shared_db_lock, logger) -> tuple:
    """
    파일 시스템을 감지하여 최적의 이동 전략 선택
    - 같은 파일시스템: 빠른 rename (즉시 완료)
    - 다른 파일시스템: chunk 기반 copy+delete (progress 추적)

    Returns:
        tuple: (success: bool, transferred_bytes: int, error_msg: str or None)
    """

    # 1️⃣ 파일 시스템 경계 감지
    source_stat = os.stat(source_file)
    target_dir = os.path.dirname(target_file)
    target_dir_stat = os.stat(target_dir)

    same_filesystem = (source_stat.st_dev == target_dir_stat.st_dev)

    # 2️⃣ 같은 파일시스템: 빠른 rename
    if same_filesystem:
        logger.info(f"📌 [MOVE] Same filesystem detected - using fast rename")
        try:
            shutil.move(source_file, target_file)

            # Redis progress: 즉시 100% 완료
            if workbench_id and redis_broker.is_available():
                progress_data = {
                    'worker_id': worker_id,
                    'srr_run': file_name,
                    'file_name': file_name,
                    'progress_percent': 100,
                    'copied_bytes': file_size,
                    'total_bytes': file_size,
                    'timestamp': time.time()
                }
                redis_broker.publish_progress(
                    workbench_id=workbench_id,
                    task_type='data_download',
                    progress_data=progress_data
                )
                logger.debug(f"📡 [REDIS-PUBLISH] Fast move completed - File: {file_name}")

            return (True, file_size, None)

        except Exception as move_error:
            error_msg = f"Fast move failed: {str(move_error)}"
            logger.error(f"   ❌ {error_msg}")
            return (False, 0, error_msg)

    # 3️⃣ 다른 파일시스템: chunk 기반 copy+delete
    logger.info(f"📌 [MOVE] Cross-filesystem detected - using chunked copy+delete")
    chunk_size = 1024 * 1024  # 1MB
    copied_bytes = 0
    last_progress_percent = -1

    try:
        with open(source_file, 'rb') as src, open(target_file, 'wb') as dst:
            while True:
                # SharedState에서 중단 신호 확인
                if shared_state.is_worker_stopped(worker_id):
                    logger.warning(f"🛑 [MOVE] File move stopped by user: {source_file}")
                    # 부분적으로 복사된 파일 삭제
                    if os.path.exists(target_file):
                        os.remove(target_file)
                    return (False, 0, "File move stopped by user")

                # 청크 읽기
                chunk = src.read(chunk_size)
                if not chunk:
                    break

                # 청크 쓰기
                dst.write(chunk)
                copied_bytes += len(chunk)

                # 진행률 계산 및 Redis 전송
                if file_size > 0:
                    progress_percent = int((copied_bytes / file_size) * 100)
                    if progress_percent != last_progress_percent:
                        last_progress_percent = progress_percent
                        logger.debug(f"🔍 [DEBUG] Progress changed! File: {file_name}, {progress_percent}%")

                        # Redis로 진행률 전송
                        if workbench_id and redis_broker.is_available():
                            progress_data = {
                                'worker_id': worker_id,
                                'srr_run': file_name,
                                'file_name': file_name,
                                'progress_percent': progress_percent,
                                'copied_bytes': copied_bytes,
                                'total_bytes': file_size,
                                'timestamp': time.time()
                            }
                            redis_broker.publish_progress(
                                workbench_id=workbench_id,
                                task_type='data_download',
                                progress_data=progress_data
                            )
                            logger.debug(f"📡 [REDIS-PUBLISH] Move progress sent - File: {file_name}, Progress: {progress_percent}%")

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
                                    logger.warning(f"⚠️ [DB-SAVE] Failed to save progress: {db_error}")
                        else:
                            # 진행률 로그 (10% 단위로만)
                            if progress_percent % 10 == 0:
                                logger.info(f"   📊 [MOVE] {file_name}: {progress_percent}% ({format_size(copied_bytes)}/{format_size(file_size)})")

        # 4️⃣ Copy 성공 후 원본 삭제
        os.remove(source_file)
        logger.info(f"✅ [MOVE] Cross-filesystem move completed: {file_name}")

        return (True, copied_bytes, None)

    except Exception as move_error:
        error_msg = f"Cross-filesystem move failed: {str(move_error)}"
        logger.error(f"   ❌ {error_msg}")
        # 부분적으로 복사된 파일 삭제
        if os.path.exists(target_file):
            os.remove(target_file)
        return (False, copied_bytes, error_msg)


def run_single_local_copy(sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """단일 파일 로컬 복사 실행 - ProcessPoolRunner용 (move with progress 사용)"""

    # 통합 로깅 시스템으로 멀티프로세싱 환경에서도 간단하게 설정
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')

    logger.info(f"[POOL] worker initialized (pid={mp.current_process().pid})")

    logger.info(f"📄 [LOCAL-SINGLE] Starting single file move (worker: {worker_id}, workbench: {workbench_id})")
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

        # 🔍 파일 중복 검사: 같은 이름과 크기를 가진 파일이 이미 존재하면 복사 건너뛰기
        if os.path.exists(target_file):
            existing_size = os.path.getsize(target_file)
            if existing_size == file_size:
                logger.info(f"⏭️ [LOCAL-SINGLE] File already exists with same size, skipping copy: {os.path.basename(target_file)}")
                logger.info(f"   📊 File size: {format_size(file_size)}")

                # 원본 파일 삭제 (이미 복사되어 있으므로)
                try:
                    os.remove(source_file)
                    logger.info(f"   🗑️ Removed source file: {source_file}")
                except Exception as remove_error:
                    logger.warning(f"   ⚠️ Failed to remove source file: {remove_error}")

                # Redis broker 초기화 및 완료 알림
                redis_broker = get_redis_broker()
                if workbench_id and redis_broker.is_available():
                    completion_data = {
                        'worker_id': worker_id,
                        'srr_run': file_name,
                        'file_name': os.path.basename(target_file),
                        'progress_percent': 100,
                        'copied_bytes': file_size,
                        'total_bytes': file_size,
                        'status': 'skipped',
                        'timestamp': time.time()
                    }
                    redis_broker.publish_progress(
                        workbench_id=workbench_id,
                        task_type='data_download',
                        progress_data=completion_data
                    )
                    logger.debug(f"📡 [REDIS-PUBLISH] File skip notification sent - File: {file_name}")

                return {
                    'success': True,
                    'source_file': source_file,
                    'target_file': target_file,
                    'copied_size': file_size,
                    'stopped_by_user': False,
                    'skipped': True
                }
            else:
                logger.warning(f"⚠️ [LOCAL-SINGLE] File exists with different size, will overwrite:")
                logger.warning(f"   Existing: {format_size(existing_size)}, New: {format_size(file_size)}")

        # Redis broker 초기화
        redis_broker = get_redis_broker()

        # move_with_progress 호출
        success, transferred_bytes, error_msg = move_with_progress(
            source_file=source_file,
            target_file=target_file,
            file_name=file_name,
            file_size=file_size,
            worker_id=worker_id,
            workbench_id=workbench_id,
            redis_broker=redis_broker,
            shared_db_lock=shared_db_lock,
            logger=logger
        )

        if not success:
            return {
                'success': False,
                'error': error_msg,
                'source_file': source_file,
                'copied_size': transferred_bytes,
                'stopped_by_user': 'stopped by user' in error_msg.lower() if error_msg else False
            }

        # 이동된 파일 검증
        if os.path.exists(target_file):
            moved_size = os.path.getsize(target_file)
            if moved_size != file_size:
                error_msg = f"File size mismatch! Source: {file_size}, Target: {moved_size}"
                logger.error(f"   ❌ {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'source_file': source_file,
                    'copied_size': moved_size,
                    'stopped_by_user': False
                }
        else:
            error_msg = f"Target file does not exist after move: {target_file}"
            logger.error(f"   ❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'source_file': source_file,
                'copied_size': 0,
                'stopped_by_user': False
            }

        # 🔓 파일 내용 기반 압축 여부 확인 후 압축 해제
        final_file = target_file
        final_size = file_size

        # Magic bytes 검사로 실제 gzip 파일인지 확인 (확장자가 아닌 파일 내용 검사)
        if is_gzip_file(target_file):
            logger.info(f"📦 [LOCAL-SINGLE] Detected gzip file (magic bytes check): {os.path.basename(target_file)}")
            try:
                # ✅ remove_original=False: 압축 파일 보존 (post-process에서 압축 해제된 파일만 삭제)
                decompressed_file = decompress_single_file(target_file, logger, remove_original=False)
                final_file = decompressed_file
                final_size = os.path.getsize(decompressed_file)
                logger.info(f"   ✅ Decompressed to: {os.path.basename(decompressed_file)} ({format_size(final_size)})")
                logger.info(f"   💾 Preserved compressed file: {os.path.basename(target_file)}")

                # Redis로 압축 해제 완료 알림 (키는 원본 .gz 파일명 유지)
                if workbench_id and redis_broker.is_available():
                    decompression_data = {
                        'worker_id': worker_id,
                        'srr_run': file_name,  # 원본 .gz 파일명을 키로 사용
                        'file_name': os.path.basename(decompressed_file),  # 실제 파일명은 .fastq
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
                logger.warning(f"⚠️ [LOCAL-SINGLE] Decompression failed: {decompress_error}")
                logger.warning(f"   Keeping compressed file: {os.path.basename(target_file)}")
                # 압축 해제 실패 시 압축 파일 그대로 사용
        else:
            logger.info(f"📄 [LOCAL-SINGLE] Non-compressed file detected, keeping as-is: {os.path.basename(target_file)}")

        logger.info(f"🎉 [LOCAL-SINGLE] File move completed successfully: {source_file} ({format_size(final_size)})")

        # 이동 완료 알림 및 DB 저장 (압축 해제 이후)
        # ✅ 키는 항상 원본 업로드 파일명(file_name)을 사용하여 중복 방지
        if workbench_id and redis_broker.is_available():
            completion_data = {
                'worker_id': worker_id,
                'srr_run': file_name,  # 원본 파일명을 키로 사용
                'file_name': os.path.basename(final_file),  # 실제 파일명 (.fastq 또는 .gz)
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
            logger.debug(f"📡 [REDIS-PUBLISH] Local move completion sent - File: {file_name}, Workbench: {workbench_id}")

            # 데이터베이스에 완료 상태 저장 (키는 원본 파일명 사용)
            try:
                _save_progress_to_db(
                    workbench_id=workbench_id,
                    worker_id=worker_id,
                    file_name=file_name,  # 원본 파일명을 키로 사용
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
        logger.error(f"❌ [LOCAL-SINGLE] {error_msg}")
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
    logger.info(f"📊 [SUMMARY-UPDATE] Calculated stats: total={total_files}, completed={completed_files}, downloading={downloading_files}, pending={pending_files}")
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
    """🔌 자동 tool 등록 함수 - 코디네이터에 local tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering local tool...")
    
    metadata = {
        'name': 'local',
        'description': 'Local file copy functionality',
        'version': '1.0.0',
        'supported_formats': ['.fastq', '.fastq.gz', '.fq', '.fq.gz'],
        'parameters': {
            'dataInputMethod': 'local'
        }
    }
    
    return coordinator.register_tool('local', execute_local_copy, metadata)