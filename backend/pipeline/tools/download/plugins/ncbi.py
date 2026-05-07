"""
NCBI download functionality for VizR pipeline
NCBI 다운로드 관련 함수들
"""

import json
import os
import sqlite3
import subprocess
import logging
import time
import threading
import re
import multiprocessing as mp
from typing import Dict, List, Any

# Process wrapper 및 ProcessPoolRunner 추가
from backend.pipeline.utils.process_wrapper import ProcessWrapper
from backend.pipeline.utils.process_runner import ProcessPoolRunner
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.redis_broker import get_redis_broker

from ..utils import (
    get_workbench_id_from_step,
    format_size,
    log_download_info,
    ensure_output_directory,
    create_download_result_template
)
from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.utils.files import compress_gzip_files

logger = logging.getLogger(__name__)

# TODO: Implement proper shared lock mechanism via ProcessPoolRunner
# _db_lock removed - threading.Lock() was not working due to multiprocessing isolation

def execute_ncbi_download_multi(sample_info_list: List[Dict], parameters: Dict, worker_id: str = "worker", workbench_id: int = None) -> Dict[str, str]:
    """ProcessPoolRunner를 사용한 병렬 NCBI 다운로드"""
    logger.info(f"🚀 [NCBI-MULTI] Starting parallel NCBI download (worker: {worker_id})")
    logger.info(f"   📊 Total SRR runs to process: {len(sample_info_list)}")
    
    # SharedState에서 worker event 가져오기
    try:
        worker_stop_event = shared_state.get_worker_event(worker_id)
    except ValueError:
        worker_stop_event = None
    
    if not worker_stop_event:
        logger.warning(f"⚠️ [NCBI-MULTI] No stop event found for worker {worker_id}")
    
    # 결과 템플릿 초기화
    results = create_download_result_template()
    
    try:
        # 워커 수 결정 (SRR 수와 8 중 작은 값)
        max_workers = min(8, len(sample_info_list))
        logger.info(f"🔧 [NCBI-MULTI] Using {max_workers} workers for {len(sample_info_list)} SRR runs")

        # 프로세스 간 공유 Lock 생성 (Manager를 통한 진정한 프로세스 간 공유)
        manager = mp.Manager()
        shared_db_lock = manager.Lock()
        logger.info(f"🔒 [NCBI-MULTI] Created shared DB lock for multiprocessing (lock_id={id(shared_db_lock)})")

        # 작업 인수 준비 (workbench_id 포함) - SharedState는 전역 import로 접근
        work_args = [(sample_info, parameters, worker_id, workbench_id) for sample_info in sample_info_list]
        logger.info(f"🚀 [NCBI-MULTI-POOL] Starting ProcessPoolRunner with {len(work_args)} samples...")

        # ProcessPoolRunner로 병렬 처리 (Event 기반 stop 신호 + 공유 DB Lock)
        with ProcessPoolRunner(max_workers=max_workers, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
            # 각 SRR 다운로드 작업을 병렬로 실행
            sample_results = list(runner.map_unordered(run_single_ncbi_download, work_args))
            
            logger.info(f"🎯 [NCBI-MULTI-POOL] ProcessPoolRunner completed, processing {len(sample_results)} results...")
            
            # 결과 처리
            total_size = 0
            downloaded_count = 0
            failed_count = 0
            stopped_by_user = False
            
            for result in sample_results:
                if result.get('stopped_by_user', False):
                    logger.warning(f"🛑 [NCBI-MULTI] Sample processing stopped by user")
                    runner.stop()
                    # Reset worker event for next execution
                    shared_state.reset_worker(worker_id)
                    stopped_by_user = True
                    break
                
                if result.get('success', False):
                    results['copied_files'].extend(result.get('files', []))
                    total_size += result.get('downloaded_size', 0)
                    downloaded_count += 1
                    srr_run = result.get('srr_run', 'unknown')
                    files = result.get('files', [])
                    logger.info(f"   ✅ Successfully downloaded: {srr_run} ({len(files)} files)")
                    results['stdout'] += f"Downloaded: {srr_run} ({len(files)} files)\\n"
                else:
                    failed_count += 1
                    srr_run = result.get('srr_run', 'unknown')
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"   ❌ Failed to download: {srr_run} - {error_msg}")
                    results['stderr'] += f"Failed: {srr_run} - {error_msg}\\n"
            
            # 사용자 중단 처리
            if stopped_by_user:
                logger.warning(f"🛑 [NCBI-MULTI] Multi-sample processing stopped by user")
                results['stderr'] = 'NCBI download stopped by user signal'
                results['success'] = False
                return results
        
        # 결과 요약
        logger.info(f"🎉 [NCBI-MULTI] Multi-sample processing completed!")
        logger.info(f"   📊 Total SRR runs processed: {len(sample_info_list)}")
        logger.info(f"   ✅ Successfully downloaded: {downloaded_count}")
        logger.info(f"   ❌ Failed downloads: {failed_count}")
        logger.info(f"   💾 Total downloaded files: {len(results['copied_files'])}")
        
        # 성공 여부 결정
        if downloaded_count > 0 and failed_count == 0:
            results['success'] = True
            summary = f"NCBI download completed: {downloaded_count} SRR runs, {len(results['copied_files'])} files total"
            logger.info(summary)
            results['stdout'] += f"\\n{summary}\\n"
        elif downloaded_count > 0 and failed_count > 0:
            results['success'] = False  # 일부 실패
            summary = f"NCBI download partially completed: {downloaded_count} success, {failed_count} failed"
            logger.warning(summary)
            results['stdout'] += f"\\n{summary}\\n"
        else:
            results['success'] = False  # 전체 실패
            error_msg = f"All NCBI download operations failed: {failed_count} SRR runs"
            logger.error(error_msg)
            results['stderr'] += error_msg
        
        return results
        
    except Exception as e:
        error_msg = f"Multi-sample NCBI download failed: {str(e)}"
        logger.error(f"❌ [NCBI-MULTI] {error_msg}")
        results['stderr'] = error_msg
        results['success'] = False
        return results


def run_single_ncbi_download(sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """단일 SRR Run 다운로드 실행 - ProcessPoolRunner용"""

    # 통합 로깅 시스템으로 멀티프로세싱 환경에서도 간단하게 설정
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')

    logger.info(f"[POOL] worker initialized (pid={mp.current_process().pid})")

    try:
        # 전역 SharedState 사용 (pickle 직렬화 문제 해결)
        active_shared_state = shared_state
        
        # sample_info 구조: {'srr_run': str, 'output_dir': str}
        srr_run = sample_info['srr_run']
        output_dir = sample_info['output_dir']

        # SRR 파일 크기 정보 추출
        srr_sizes = parameters.get('SRR_Sizes', {}) if parameters else {}
        logger.debug(f"📏 [NCBI-SINGLE] SRR sizes for callback: {srr_sizes}")
        
        # 🖨️ Print문으로 다운로드 시작 출력
        logger.info(f"🚀 [{srr_run}] STARTING download [{worker_id}]")
        
        logger.info(f"   🧬 SRR Run: {srr_run}")
        logger.info(f"   📤 TO: {output_dir}")
        
        # 출력 디렉토리 생성
        os.makedirs(output_dir, exist_ok=True)
        
        # 워크벤치별 임시 디렉토리 설정
        temp_dir = os.path.join(output_dir, '.tmp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # fasterq-dump 명령어 구성
        cmd = [
            'fasterq-dump',
            '--split-3',  # PE 파일을 _1.fastq, _2.fastq로 분리
            '--outdir', output_dir,
            '--temp', temp_dir,  # 워크벤치별 임시 디렉토리 지정
            '--progress',  # 진행상황 표시
            '--force',
            srr_run
        ]
        
        logger.info(f"   🔧 Running command: {' '.join(cmd)}")
        
        # 작업 시작 시간 기록
        set_global_start_time(worker_id)
        
        # 통일된 progress_callback 함수 생성 (workbench_id 전달)
        logger.info(f"🔍 [DEBUG-CHILD] Creating progress_callback for SRR: {srr_run}, workbench_id: {workbench_id}")

        callback = progress_callback(worker_id, srr_run, workbench_id, srr_sizes, shared_db_lock)

        logger.info(f"🔍 [DEBUG-CHILD] progress_callback created: {callback is not None}")
        
        # ProcessWrapper로 fasterq-dump 실행 (progress_callback 포함)
        wrapper = ProcessWrapper(worker_id)
        
        logger.info(f"🔍 [DEBUG-CHILD] About to execute fasterq-dump with callback: {callback is not None}")

        result = wrapper.run_command(
            cmd,
            stop_event=stop_event,
            progress_callback=callback
        )
        
        # fasterq-dump 실행 결과 분석
        logger.info(f"🔍 [DEBUG-CHILD] fasterq-dump execution completed. Return code: {result.get('returncode', 'unknown')}")
            
        stdout_lines = len(result.get('stdout', '').split('\n')) if result.get('stdout') else 0
        stderr_lines = len(result.get('stderr', '').split('\n')) if result.get('stderr') else 0
        
        logger.info(f"🔍 [DEBUG-CHILD] fasterq-dump stdout lines: {stdout_lines}, stderr lines: {stderr_lines}")
            
        # stdout/stderr 샘플 출력
        stdout_sample = result.get('stdout', '')[:200] if result.get('stdout') else 'None'
        stderr_sample = result.get('stderr', '')[:200] if result.get('stderr') else 'None'
        
        logger.info(f"🔍 [DEBUG-CHILD] stdout sample: {stdout_sample}...")
        logger.info(f"🔍 [DEBUG-CHILD] stderr sample: {stderr_sample}...")

        # stop_event 체크
        if result.get('stopped_by_user', False):
            logger.info(f"🛑 [NCBI-SINGLE] SRR download stopped by user: {srr_run}")
            
            # 중단 시에도 시작 시간 정리
            clear_global_start_time(worker_id)
            
            return {
                'success': False,
                'error': 'SRR download stopped by user',
                'srr_run': srr_run,
                'files': [],
                'downloaded_size': 0,
                'stopped_by_user': True
            }
        
        # fasterq-dump 결과 확인
        if result['returncode'] != 0:
            error_msg = result['stderr'].strip() if result['stderr'] else f"Command failed with return code {result['returncode']}"
            logger.error(f"   ❌ fasterq-dump failed: {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'srr_run': srr_run,
                'files': [],
                'downloaded_size': 0,
                'stopped_by_user': False
            }
        
        # 다운로드된 파일들 확인
        fastq_files = []
        for suffix in ['_1.fastq', '_2.fastq', '.fastq']:
            potential_file = os.path.join(output_dir, f"{srr_run}{suffix}")
            if os.path.exists(potential_file):
                fastq_files.append(potential_file)
        
        if not fastq_files:
            error_msg = f"No FASTQ files found after download: {srr_run}"
            logger.error(f"   ❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'srr_run': srr_run,
                'files': [],
                'downloaded_size': 0,
                'stopped_by_user': False
            }
        
        # 📦 다운로드 완료 후 압축
        logger.info(f"📦 [NCBI-COMPRESS] Compressing downloaded FASTQ files: {srr_run}")

        try:
            # compress_gzip_files 함수 호출하여 압축
            compressed_files = compress_gzip_files(fastq_files, logger, remove_original=True)

            if compressed_files:
                final_files = compressed_files
                logger.info(f"   ✅ Compressed {len(compressed_files)} files successfully")
            else:
                # 압축 실패 시 원본 파일 유지
                logger.warning(f"   ⚠️ Compression failed, keeping original files")
                final_files = fastq_files
        except Exception as compress_error:
            logger.error(f"   ❌ Compression error: {compress_error}, keeping original files")
            final_files = fastq_files

        # 최종 파일 크기 계산 (압축 후)
        total_size = 0
        for final_file in final_files:
            if os.path.exists(final_file):
                file_size = os.path.getsize(final_file)
                total_size += file_size

        logger.info(f"🎉 [NCBI-SINGLE] SRR download completed successfully: {srr_run} ({len(final_files)} files, {format_size(total_size)})")
        
        # ✅ 다운로드 완료 시 Redis publish
        if workbench_id:
            completion_data = {
                'srr_run': srr_run,
                'status': 'completed',
                'progress_percent': 100.0,
                'worker_id': worker_id,
                'files': final_files,
                'downloaded_size': total_size,
                'total_files': len(final_files)
            }
            
            # 🖨️ Print문으로 완료 상태 출력
            size_mb = total_size / (1024 * 1024) if total_size > 0 else 0
            logger.info(f"✅ [{srr_run}] COMPLETED - {len(final_files)} files, {size_mb:.1f}MB [{worker_id}]")
            
            # Redis로 완료 이벤트 발행
            redis_broker = get_redis_broker()
            if redis_broker.is_available():
                redis_broker.publish_progress(
                    workbench_id=workbench_id,
                    task_type='data_download',
                    progress_data=completion_data
                )
                logger.info(f"📡 [REDIS-PUBLISH] Completion event published - SRR: {srr_run}")

                # 데이터베이스에 완료 상태 저장
                try:
                    _save_progress_to_db(
                        workbench_id=workbench_id,
                        worker_id=worker_id,
                        srr_run=srr_run,
                        progress_data=completion_data,
                        srr_sizes=srr_sizes,
                        shared_db_lock=shared_db_lock
                    )
                except Exception as db_error:
                    logger.warning(f"⚠️ [DB-SAVE] Failed to save completion to database: {db_error}")
            else:
                logger.warning(f"⚠️ [REDIS-PUBLISH] Redis not available for completion event")
        
        # 성공 시 시작 시간 정리
        clear_global_start_time(worker_id)
        
        return {
            'success': True,
            'srr_run': srr_run,
            'files': final_files,
            'downloaded_size': total_size,
            'stopped_by_user': False
        }
        
    except Exception as e:
        error_msg = f"Single SRR download failed: {str(e)}"
        logger.error(f"❌ [NCBI-SINGLE] {error_msg}")
        
        # 실패 시에도 시작 시간 정리
        clear_global_start_time(worker_id)
        
        return {
            'success': False,
            'error': error_msg,
            'srr_run': sample_info.get('srr_run', 'unknown'),
            'files': [],
            'downloaded_size': 0,
            'stopped_by_user': False
        }


def execute_ncbi_download(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    """NCBI 다운로드 - 코디네이터"""
    logger.info("🔽 🚚 NCBI DOWNLOAD OPERATION - COORDINATOR 🚚")
    
    try:
        # 매개변수 추출
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        bioproject_id = parameters.get('bioprojectId', '')
        srr_runs = parameters.get('SRR_Runs', [])
        srr_sizes = parameters.get('SRR_Sizes', {})  # ✅ SRR 파일 크기 정보 추출

        logger.info(f"🧬 [NCBI-DOWNLOAD] BioProject: {bioproject_id}")
        logger.info(f"📋 [NCBI-DOWNLOAD] SRR runs: {srr_runs}")
        logger.info(f"📏 [NCBI-DOWNLOAD] SRR sizes (bytes): {srr_sizes}")

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
        
        logger.info(f"[NCBI_DOWNLOAD] Configuration:")
        logger.info(f"   🏷️  workbench_id: {workbench_id}")
        logger.info(f"   📋 bioproject_id: {bioproject_id}")
        logger.info(f"   📂 output_dir: {output_dir}")
        logger.info(f"   🧬 srr_runs: {srr_runs} ({len(srr_runs)} runs)")
        
        # SRR Runs 확인
        if not srr_runs:
            logger.error("❌ [NCBI_DOWNLOAD] No SRR runs provided")
            results = create_download_result_template()
            results['stderr'] = 'No SRR runs provided for download'
            results['success'] = False
            return results
        
        # 출력 디렉토리 생성
        ensure_output_directory(output_dir)

        # raw 디렉토리에 이미 다운로드된 파일이 있는지 확인
        existing_files = {}
        if os.path.exists(output_dir):
            logger.info(f"📁 [NCBI_DOWNLOAD] Checking for existing files in raw directory: {output_dir}")

            for file_name in os.listdir(output_dir):
                if file_name.endswith(('.fastq', '.fastq.gz', '.fq', '.fq.gz')):
                    full_path = os.path.join(output_dir, file_name)
                    if os.path.isfile(full_path):
                        # SRR ID 추출 (파일명에서 SRR로 시작하는 부분)
                        # 예: SRR12345_1.fastq.gz -> SRR12345
                        match = re.match(r'(SRR\d+)', file_name)
                        if match:
                            srr_id = match.group(1)
                            if srr_id not in existing_files:
                                existing_files[srr_id] = []
                            existing_files[srr_id].append(full_path)
                            file_size = os.path.getsize(full_path)
                            logger.info(f"   ✅ Found in raw: {file_name} ({format_size(file_size)})")

        # 이미 존재하는 파일은 다운로드 목록에서 제외
        files_to_download = [srr for srr in srr_runs if srr not in existing_files]

        # 모든 파일이 이미 존재하는 경우
        if not files_to_download:
            logger.info(f"✅ [NCBI_DOWNLOAD] All {len(srr_runs)} SRR files already exist in raw directory, skipping download")

            # 성공 결과 반환
            results = create_download_result_template()
            results['success'] = True
            all_existing = []
            for srr_id, files in existing_files.items():
                all_existing.extend(files)
            results['downloaded_files'] = all_existing
            results['stdout'] = f"Download step skipped: {len(srr_runs)} SRR runs already exist in raw directory\n"

            for srr_id in srr_runs:
                if srr_id in existing_files:
                    for file_path in existing_files[srr_id]:
                        file_size = os.path.getsize(file_path)
                        results['stdout'] += f"Existing: {os.path.basename(file_path)} ({format_size(file_size)})\n"

            return results

        # 일부 파일만 존재하는 경우 로그 출력
        if existing_files:
            logger.info(f"📦 [NCBI_DOWNLOAD] {len(existing_files)} SRR files already exist, downloading remaining {len(files_to_download)} files")

        # 다운로드가 필요한 SRR만 sample_info 생성
        sample_info_list = []
        for srr_run in files_to_download:
            sample_info = {
                'srr_run': srr_run,
                'output_dir': output_dir
            }
            sample_info_list.append(sample_info)
        
        logger.info(f"🎯 [NCBI_DOWNLOAD] Prepared {len(sample_info_list)} sample_info entries for processing")
        
        # Progress detail 초기화 - Job Generator가 생성한 download step에 저장
        _initialize_ncbi_progress_detail(workbench_id, srr_runs, worker_id, srr_sizes)
        
        # execute_ncbi_download_multi 호출 (workbench_id 전달)
        result = execute_ncbi_download_multi(sample_info_list, parameters, worker_id, workbench_id)
        
        # 결과에 BioProject ID 정보 추가
        if result.get('success', False):
            result['stdout'] += f"BioProject: {bioproject_id}\\n"
            logger.info(f"✅ [NCBI_DOWNLOAD] BioProject {bioproject_id} download completed")
        
        return result
        
    except Exception as e:
        error_msg = f"NCBI download coordinator failed: {str(e)}"
        logger.error(f"❌ [NCBI_DOWNLOAD] {error_msg}")
        
        # 기본 결과 템플릿 반환
        results = create_download_result_template()
        results['stderr'] = error_msg
        results['success'] = False
        return results


def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 ncbi tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering ncbi tool...")
    
    metadata = {
        'name': 'ncbi',
        'description': 'NCBI SRA download functionality',
        'version': '1.0.0',
        'supported_formats': ['.fastq'],
        'requirements': ['fasterq-dump'],
        'parameters': {
            'dataInputMethod': 'ncbi',
            'bioprojectId': 'string',
            'SRR_Runs': 'array'
        }
    }
    
    return coordinator.register_tool('ncbi', execute_ncbi_download, metadata)


# ============================================================================
# Progress Callback Functions for SSE Support
# ============================================================================

class StopRequested(Exception):
    """워커 중단 요청 예외"""
    pass


def progress_callback(worker_id: str, srr_run: str, workbench_id: int = None, srr_sizes: Dict[str, int] = None, shared_db_lock=None):
    """
    NCBI 다운로드용 progress_callback 함수 (Redis Pub/Sub 전용)
    fasterq-dump 출력을 파싱하여 Redis로 실시간 진행상황 발행

    Args:
        worker_id: 워커 식별자
        srr_run: SRR 실행 ID
        workbench_id: 워크벤치 ID (Redis publish용)
        srr_sizes: SRR 크기 정보 (선택적)
        shared_db_lock: 멀티프로세스 간 공유 DB 락 (선택적)

    Returns:
        실제 콜백 함수
    """
    # Redis 브로커 초기화
    redis_broker = get_redis_broker()
    active_shared_state = shared_state

    logger.info(f"📡 [REDIS-CALLBACK] Creating callback for SRR: {srr_run}, workbench: {workbench_id}")

    # 클로저 변수들 선언
    line = ""
    in_progress_mode = False
    current_percentage = ""

    # 🔒 중복 저장 방지를 위한 진행률 추적 (프로세스별 독립)
    last_saved_progress = {}
    
    def callback(char: str):
        """fasterq-dump 출력을 파싱하여 SharedState에 전송"""
        nonlocal line, in_progress_mode, current_percentage, last_saved_progress
        
        try:
            # 1. Stop Event 체크 (최우선)
            if active_shared_state.is_worker_stopped(worker_id):
                logger.info(f"🛑 [NCBI-PROGRESS] Stop signal detected for worker {worker_id}")
                
                # Redis로 중단 상태 발행
                if workbench_id and redis_broker.is_available():
                    cancel_data = {
                        'srr_run': srr_run,
                        'status': 'cancelled',
                        'progress_percent': 0.0,
                        'message': 'NCBI download cancelled by user'
                    }
                    redis_broker.publish_progress(
                        workbench_id=workbench_id,
                        task_type='data_download',
                        progress_data=cancel_data
                    )

                    # 데이터베이스에 중단 상태 저장
                    try:
                        _save_progress_to_db(
                            workbench_id=workbench_id,
                            worker_id=worker_id,
                            srr_run=srr_run,
                            progress_data=cancel_data,
                            srr_sizes=srr_sizes,
                            shared_db_lock=shared_db_lock
                        )
                    except Exception as db_error:
                        logger.warning(f"⚠️ [DB-SAVE] Failed to save cancellation to database: {db_error}")

                # 상위 루프 중단을 위한 예외 발생
                raise StopRequested("NCBI download stopped by user")
            
            # 2. 문자를 line에 추가
            line += char
            
            # 3. "join   :|" 패턴 감지 - 진행률 모드 시작
            if "join   :|" in line and not in_progress_mode:
                logger.info(f"🎯 [{srr_run}] Progress mode started - detected 'join   :|'")
                in_progress_mode = True
                line = ""  # 패턴 이후부터 새로 수집
                current_percentage = ""
                return
            
            # 4. 진행률 모드에서 백스페이스 처리
            if in_progress_mode:
                # 백스페이스 문자 감지 (\b 또는 \x08)
                if char == '\b' or ord(char) == 8:
                    # 현재까지 수집한 percentage 파싱
                    if current_percentage:
                        # percentage에서 숫자만 추출
                        import re
                        match = re.search(r'(\d+\.?\d*)%', current_percentage)
                        if match:
                            progress_value = float(match.group(1))
                            
                            # 진행상황 데이터 생성
                            progress_data = {
                                'srr_run': srr_run,
                                'status': 'downloading',
                                'progress_percent': progress_value,
                                'message': f'Joining reads: {progress_value:.2f}%',
                                'worker_id': worker_id
                            }
                            
                            logger.debug(f"📊 [{srr_run}] Progress: {progress_value:.2f}%")
                            
                            # Redis로 진행률 발행
                            if workbench_id and redis_broker.is_available():
                                redis_broker.publish_progress(
                                    workbench_id=workbench_id,
                                    task_type='data_download',
                                    progress_data=progress_data
                                )

                                # 🔒 데이터베이스에 진행상황 저장 (10% 단위 + 중복 방지)
                                current_progress_int = int(progress_value)
                                # 중복 저장 방지: 이미 저장한 진행률인지 확인
                                if last_saved_progress.get(srr_run) != current_progress_int:
                                    last_saved_progress[srr_run] = current_progress_int
                                    logger.debug(f"🔒 [{srr_run}] DB save triggered: {current_progress_int}% (first time)")

                                    try:
                                        _save_progress_to_db(
                                            workbench_id=workbench_id,
                                            worker_id=worker_id,
                                            srr_run=srr_run,
                                            progress_data=progress_data,
                                            srr_sizes=srr_sizes,
                                            shared_db_lock=shared_db_lock
                                        )
                                    except Exception as db_error:
                                        logger.warning(f"⚠️ [DB-SAVE] Failed to save progress to database: {db_error}")
                                else:
                                    logger.debug(f"🔒 [{srr_run}] DB save skipped: {current_progress_int}% (already saved)")

                            elif not redis_broker.is_available():
                                logger.warning(f"⚠️ [REDIS-PUBLISH] Redis not available for progress update")
                    
                    # 백스페이스 후 line 초기화 (다음 percentage 준비)
                    line = ""
                    current_percentage = ""
                    return
                
                # 백스페이스가 아니면 percentage 문자열 수집
                if char not in ['\n', '\r']:
                    current_percentage += char
            
            # 5. 진행률 100% 도달 또는 완료 감지
            if in_progress_mode and ("100%" in current_percentage or "done" in line.lower()):
                logger.info(f"✅ [{srr_run}] Join completed - 100%")
                in_progress_mode = False
                line = ""
                current_percentage = ""



                
        except StopRequested:
            # 중단 예외는 상위로 전파
            raise
        except Exception as e:
            logger.warning(f"⚠️ [NCBI-PROGRESS] Progress parsing error: {e}")
    
    # 🔍 DEBUG: callback 함수 반환 확인
    logger.info(f"🔍 [DEBUG] Returning callback function for SRR: {srr_run}")
    return callback


def get_sra_total_spots(srr_run: str) -> int:
    """
    SRA 메타데이터에서 총 스팟 수 추정
    NCBI E-utilities를 사용하여 SRA 데이터베이스 조회
    
    Args:
        srr_run: SRR 실행 ID (예: "SRR12494476")
        
    Returns:
        총 스팟 수 (실패 시 기본값 1,000,000)
    """
    
    try:
        # esearch를 사용한 SRA ID 조회
        esearch_cmd = [
            'esearch', 
            '-db', 'sra', 
            '-query', srr_run
        ]
        
        logger.debug(f"🔍 [SRA-META] Querying metadata for {srr_run}...")
        
        esearch_process = subprocess.run(
            esearch_cmd, 
            capture_output=True, 
            text=True,
            timeout=30  # 30초 타임아웃
        )
        
        if esearch_process.returncode != 0:
            logger.warning(f"⚠️ [SRA-META] esearch failed for {srr_run}: {esearch_process.stderr}")
            return 1000000  # 기본값
        
        # efetch를 사용한 runinfo 조회  
        efetch_cmd = [
            'efetch', 
            '-format', 'runinfo'
        ]
        
        efetch_process = subprocess.run(
            efetch_cmd,
            input=esearch_process.stdout,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if efetch_process.returncode != 0:
            logger.warning(f"⚠️ [SRA-META] efetch failed for {srr_run}: {efetch_process.stderr}")
            return 1000000  # 기본값
        
        # runinfo CSV 파싱
        runinfo_text = efetch_process.stdout.strip()
        if not runinfo_text:
            logger.warning(f"⚠️ [SRA-META] Empty runinfo for {srr_run}")
            return 1000000
        
        lines = runinfo_text.split('\n')
        if len(lines) < 2:  # 헤더 + 최소 1개 데이터 라인
            logger.warning(f"⚠️ [SRA-META] Invalid runinfo format for {srr_run}")
            return 1000000
        
        # CSV 헤더와 데이터 파싱
        header = [col.strip() for col in lines[0].split(',')]
        data = [col.strip() for col in lines[1].split(',')]
        
        if len(header) != len(data):
            logger.warning(f"⚠️ [SRA-META] Header/data mismatch for {srr_run}")
            return 1000000
        
        # spots 컬럼 찾기
        for i, column_name in enumerate(header):
            if column_name.lower() == 'spots':
                try:
                    total_spots = int(data[i])
                    logger.info(f"✅ [SRA-META] Found {total_spots:,} spots for {srr_run}")
                    return total_spots
                except (ValueError, IndexError) as e:
                    logger.warning(f"⚠️ [SRA-META] Invalid spots value for {srr_run}: {e}")
                    break
        
        # spots 컬럼을 찾지 못한 경우
        logger.warning(f"⚠️ [SRA-META] No 'spots' column found for {srr_run}")
        return 1000000  # 기본값
        
    except subprocess.TimeoutExpired:
        logger.warning(f"⏱️ [SRA-META] Timeout querying metadata for {srr_run}")
        return 1000000
    except Exception as e:
        logger.warning(f"❌ [SRA-META] Metadata query failed for {srr_run}: {e}")
        return 1000000


# 전역 시작 시간 저장소
_global_start_times = {}


def set_global_start_time(worker_id: str):
    """작업 시작 시간 기록"""
    global _global_start_times
    _global_start_times[worker_id] = time.time()


def get_global_start_time(worker_id: str) -> float:
    """작업 시작 시간 조회"""
    global _global_start_times
    return _global_start_times.get(worker_id, time.time())


def clear_global_start_time(worker_id: str):
    """작업 완료 후 시작 시간 정리"""
    global _global_start_times
    if worker_id in _global_start_times:
        del _global_start_times[worker_id]


def calculate_eta(current: int, total: int, worker_id: str) -> int:
    """
    ETA 계산 (초 단위)
    
    Args:
        current: 현재 처리된 양
        total: 전체 처리해야 할 양  
        worker_id: 워커 식별자 (시작 시간 조회용)
        
    Returns:
        예상 남은 시간 (초)
    """
    
    try:
        # 작업 시작 시간 가져오기
        start_time = get_global_start_time(worker_id)
        
        # 경과 시간 계산
        elapsed = time.time() - start_time
        
        # 유효성 검사
        if current <= 0 or elapsed <= 0:
            return 0
        
        # 초당 처리율 계산
        rate = current / elapsed
        
        # 남은 작업량 계산
        remaining = total - current
        
        # ETA 계산
        eta = remaining / rate if rate > 0 else 0
        
        # 0보다 큰 값만 반환
        return max(0, int(eta))
        
    except Exception as e:
        logger.warning(f"⚠️ [NCBI-ETA] ETA calculation error: {e}")
        return 0


def _initialize_ncbi_progress_detail(workbench_id: int, srr_runs: List[str], worker_id: str, srr_sizes: Dict[str, int] = None):
    """
    SRR 런 목록 확정 후 progress_detail 초기값 생성
    Job Generator가 생성한 download step에 모든 SRR 런의 초기 상태를 설정

    Args:
        workbench_id: 워크벤치 ID
        srr_runs: SRR 런 목록
        worker_id: 워커 ID
        srr_sizes: SRR 파일 크기 정보 (bytes)
    """
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
            logger.warning(f"⚠️ [INIT-NCBI-PROGRESS] No download step found for workbench {workbench_id}. Job Generator may not have created it yet.")
            return
        
        step_record = existing_step[0]
        
        # SRR별 초기 정보 수집 (실제 파일 크기 사용)
        files_detail = {}
        total_size = 0  # 전체 크기 계산용

        for srr_run in srr_runs:
            file_size = srr_sizes.get(srr_run, 0) if srr_sizes else 0
            total_size += file_size

            files_detail[srr_run] = {
                "status": "pending",
                "progress": 0,
                "file_size": file_size,  # ✅ 실제 SRR 크기 사용
                "downloaded_size": 0,
                "timestamp": time.time()
            }

            logger.debug(f"📏 [INIT-PROGRESS] {srr_run}: {file_size} bytes")
        
        # 초기 progress_detail 구조 생성 (크기 필드 제외 - NCBI 특성상 의미없음)
        progress_detail = {
            "summary": {
                "total_files": len(srr_runs),
                "downloading_files": 0,
                "completed_files": 0,
                "pending_files": len(srr_runs),
                "last_updated": time.time()
                # total_size, downloaded_size 제거: NCBI 특성상 의미없음
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
        
        logger.info(f"✅ [INIT-NCBI-PROGRESS] Progress detail initialized for workbench {workbench_id}")
        logger.info(f"   📊 Total SRR runs: {len(srr_runs)}")
        
    except Exception as e:
        logger.error(f"❌ [INIT-NCBI-PROGRESS] Failed to initialize progress detail for workbench {workbench_id}: {e}")
        # 초기화 실패해도 다운로드 작업은 계속 진행


def _update_ncbi_summary_stats(progress_json_data: Dict[str, Any]):
    """
    SRR별 진행상황을 기반으로 summary 통계 자동 계산
    
    Args:
        progress_json_data: progress_detail JSON 데이터 (수정됨)
    """
    all_files = progress_json_data.get('files', {})
    
    # 파일 상태별 개수 계산 (100% 완료된 파일도 완료로 처리)
    total_files = len(all_files)
    completed_files = sum(1 for f in all_files.values() 
                         if f.get('status') == 'completed' or f.get('progress') == 100)
    downloading_files = sum(1 for f in all_files.values() 
                           if f.get('status') == 'downloading' and f.get('progress', 0) < 100)
    pending_files = sum(1 for f in all_files.values() if f.get('status') == 'pending')
    
    # Summary 업데이트 (파일 개수 기반 통계만 포함)
    progress_json_data['summary'] = {
        "total_files": total_files,
        "downloading_files": downloading_files,
        "completed_files": completed_files,
        "pending_files": pending_files,
        "last_updated": time.time()
        # total_size, downloaded_size 제거: NCBI 특성상 의미없음
    }


def _save_progress_to_db(workbench_id: int, worker_id: str, srr_run: str, progress_data: Dict[str, Any], srr_sizes: Dict[str, int] = None, shared_db_lock=None):
    """
    Job Generator가 생성한 download step 레코드의 progress_detail을 업데이트
    워크벤치당 하나의 download 레코드에 모든 파일들의 진행상황이 포함됨

    Args:
        workbench_id: 워크벤치 ID
        worker_id: 워커 ID
        srr_run: SRR run 명 (파일명으로 사용)
        progress_data: 진행상황 데이터 (Redis 포맷)
        srr_sizes: SRR 크기 정보 (선택적)
        shared_db_lock: 멀티프로세스 간 공유 DB 락 (필수)
    """
    # 프로세스 정보 수집
    current_process = mp.current_process()
    process_info = f"PID={current_process.pid}, Name={current_process.name}"
    progress_percent = progress_data.get('progress_percent', 0)

    # Lock 진입 시도 로그
    logger.debug(f"🔒 [DB-LOCK-ENTER] PID={current_process.pid} ATTEMPTING lock acquisition - {process_info}, SRR: {srr_run}, Progress: {progress_percent}%, Workbench: {workbench_id}")

    # 전달받은 shared_db_lock 사용 (ProcessPoolRunner에서 자동 주입됨)
    if shared_db_lock is not None:
        # 전달받은 Lock 사용
        with shared_db_lock:
            logger.debug(f"✅ [DB-LOCK-ACQUIRED] PID={current_process.pid} ENTERED critical section WITH SHARED LOCK - {process_info}, SRR: {srr_run}, Progress: {progress_percent}%")
            _execute_ncbi_database_operations_impl(current_process, process_info, srr_run, progress_percent, workbench_id, progress_data, srr_sizes)
    else:
        logger.error(f"❌ [DB-LOCK] No shared_db_lock provided - this should not happen!")
        return


def _execute_ncbi_database_operations_impl(current_process, process_info: str, srr_run: str, progress_percent: int, workbench_id: int, progress_data: Dict[str, Any], srr_sizes: Dict[str, int] = None):
    """실제 데이터베이스 작업을 수행하는 구현 함수"""
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

        # 현재 SRR run의 진행상황 업데이트 (실제 파일 크기 사용)
        file_size = srr_sizes.get(srr_run, 0) if srr_sizes else 0
        downloaded_size = int(file_size * (progress_percent / 100)) if file_size > 0 else 0

        logger.debug(f"📏 [DB-SAVE] File size info for {srr_run}: {file_size} bytes, Downloaded: {downloaded_size} bytes ({progress_percent}%)")

        progress_json_data['files'][srr_run] = {
            'progress': progress_percent,
            'file_size': file_size,
            'downloaded_size': downloaded_size,  # file_size 기반 정확한 계산
            'status': progress_data.get('status', 'downloading'),
            'timestamp': time.time()
        }

        # Summary 통계 자동 계산 및 업데이트
        _update_ncbi_summary_stats(progress_json_data)

        # JSON 문자열로 변환
        progress_json = json.dumps(progress_json_data)

        # 전체 다운로드 상태 계산 (모든 파일이 완료되었는지 확인)
        all_files = progress_json_data['files']
        total_files = len(all_files)
        completed_files = sum(1 for f in all_files.values() if f.get('status') == 'completed')
        download_status = 'completed' if completed_files == total_files and total_files > 0 else 'running'

        # UPDATE 직전 상태 로그 출력
        logger.debug(f"💾 [DB-UPDATE-BEFORE] PID={current_process.pid} About to update step id={step_record['id']}, SRR: {srr_run}, Status: {download_status}, Total files: {total_files}, Completed: {completed_files}")

        # 기존 레코드 업데이트 (Job Generator가 생성한 레코드)
        database.execute_update(
            """
            UPDATE pipeline_job_steps
            SET progress_detail = ?,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (progress_json, download_status, step_record['id'])
        )

        logger.debug(f"💾 [DB-UPDATE-AFTER] PID={current_process.pid} Successfully updated step id={step_record['id']}, SRR: {srr_run}")

        logger.info(f"💾 [DB-SAVE] Progress updated in download step record - SRR: {srr_run}, Progress: {progress_percent}%, Total files: {total_files}, Completed: {completed_files}")

        # Lock 해제 직전 로그 (공유 Lock 사용)
        logger.debug(f"🔓 [DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, SRR: {srr_run}, Progress: {progress_percent}%, Operation: SUCCESS")

    except Exception as e:
        logger.error(f"❌ [DB-SAVE] Failed to save progress for {srr_run}: {e}")
        # Lock 해제 직전 로그 (에러 상황, 공유 Lock 사용)
        logger.debug(f"🔓 [DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, SRR: {srr_run}, Progress: {progress_percent}%, Operation: ERROR")
        raise


