"""
FastQC quality control functionality for VizR pipeline
FastQC 품질 관리 관련 함수들
"""

import json
import os
import sqlite3
import logging
import subprocess
import time
from typing import Dict, List, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.utils.files import ensure_decompressed_files
from backend.pipeline.utils.process_wrapper import ProcessWrapper, cleanup_temp_directory
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.process_runner import ProcessPoolRunner
from backend.pipeline.utils.redis_broker import get_redis_broker
from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'INFO')


def send_qc_progress_update(workbench_id: int, progress_data: dict) -> bool:
    """
    QC 진행률 직접 전송

    Args:
        workbench_id: 워크벤치 ID
        progress_data: 진행률 데이터 (completed_files, total_files, progress_percent)

    Returns:
        전송 성공 여부
    """
    try:
        redis_broker = get_redis_broker()

        if not redis_broker.is_available():
            logger.debug(f"📡 [QC-PROGRESS] Redis not available, skipping progress update")
            return False

        # Redis로 진행률 전송
        success = redis_broker.publish_progress(
            workbench_id=workbench_id,
            task_type='qc',  # QC 작업 타입
            progress_data=progress_data
        )

        if success:
            logger.debug(f"📡 [QC-PROGRESS] Progress sent - Workbench: {workbench_id}, "
                        f"Progress: {progress_data.get('completed_files', 0)}/{progress_data.get('total_files', 0)} "
                        f"({progress_data.get('progress_percent', 0):.1f}%)")
        else:
            logger.debug(f"📡 [QC-PROGRESS] No subscribers for workbench {workbench_id}")

        return success

    except Exception as e:
        logger.error(f"❌ [QC-PROGRESS] Failed to send progress update: {e}")
        return False


def _save_qc_progress_to_db(workbench_id: int, completed_files: int, total_files: int) -> bool:
    """
    QC 진행상황을 pipeline_job_steps.progress_detail에 저장

    Args:
        workbench_id: 워크벤치 ID
        completed_files: 완료된 파일 수
        total_files: 전체 파일 수

    Returns:
        저장 성공 여부
    """
    try:
        progress_data = {
            'completed_files': completed_files,
            'total_files': total_files,
            'progress_percent': (completed_files / total_files * 100) if total_files > 0 else 0,
            'last_updated': time.time()
        }

        with database.get_db_connection() as conn:
            cursor = conn.cursor()

            # pipeline_job_steps 테이블에 진행률 업데이트
            cursor.execute("""
                UPDATE pipeline_job_steps
                SET progress_detail = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE workbench_id = ?
                AND step_name = 'qc'
            """, (
                json.dumps(progress_data),
                workbench_id
            ))

            conn.commit()

            if cursor.rowcount > 0:
                logger.debug(f"💾 [QC-DB] Progress saved to DB - Workbench: {workbench_id}, "
                            f"Progress: {completed_files}/{total_files} ({progress_data['progress_percent']:.1f}%)")
                return True
            else:
                logger.warning(f"⚠️ [QC-DB] No matching QC step found for workbench {workbench_id}")
                return False

    except Exception as e:
        logger.error(f"❌ [QC-DB] Failed to save progress to DB: {e}")
        return False


def execute_fastqc(job_step: sqlite3.Row, worker_id: str = "worker", stop_event=None) -> Dict[str, str]:
    """
    FastQC 실행 - job_step에서 직접 정보 추출
    """
    # job_step에서 직접 정보 추출 (step_details 개념 제거)
    step_id = job_step['step_id']
    job_id = job_step['job_id']
    parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
    workbench_id = job_step['workbench_id']

    # workbench 정보 조회
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

    logger.info(f"🧪 [FASTQC] Starting FastQC process")
    logger.debug(f"📋 [FASTQC] Job Configuration:")
    logger.debug(f"   └─ workbench_id: {workbench_id}")
    logger.debug(f"   └─ step_id: {step_id}")

    # 출력 디렉토리 설정
    output_dir = os.path.join(workbench_schema["quanti"]["qc"], "fastqc")
    os.makedirs(output_dir, exist_ok=True)
    logger.debug(f"📁 [FASTQC] Created output directory: {output_dir}")
    
    # samples_data에서 직접 sample_info_list 구성  
    sample_info_list = []
    
    # workbench_id에서 샘플 정보와 layout 정보 조회
    workbench_id = job_step['workbench_id']
    with database.get_db_connection() as db_connection:
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT samples, layout 
            FROM vizr_pipeline_samples 
            WHERE workbench_id = ?
        """, (workbench_id,))
        pipeline_samples_result = cursor.fetchone()
        
        if pipeline_samples_result:
            samples_json = pipeline_samples_result['samples']
            layout = pipeline_samples_result['layout']
            logger.info(f"📊 [FASTQC] Retrieved {len(json.loads(samples_json))} samples (layout: {layout})")

            try:
                # JSON 파싱하여 rows에 할당
                samples_data = json.loads(samples_json)
            except json.JSONDecodeError as e:
                logger.error(f"❌ [FASTQC] Failed to parse samples JSON from vizr_pipeline_samples: {e}")
        else:
            logger.warning(f"⚠️  [FASTQC] No samples found in vizr_pipeline_samples for workbench_id: {workbench_id}")
            layout = 'pe'  # 기본값

    logger.debug(f"🔍 [FASTQC] Layout: {layout}")

    # samples_data로 직접 sample_info_list 구성
    logger.debug(f"🛠️  [FASTQC] Building sample configuration...")
    
    # 입력 파일은 항상 raw 디렉토리에서 가져오기 (FastQC는 첫 번째 단계)
    input_dir = workbench_schema["quanti"]["raw"]
    
    # 각 샘플의 file1, file2를 추출하여 파일 경로 구성
    for sample_info in samples_data:
        sample_name = sample_info['sampleName']
        group_name = sample_info['groupName']

        files = {}

        if 'file1' in sample_info and sample_info['file1']:
            file1_name = sample_info['file1']

            # Check for uncompressed file first, then compressed file
            # FastQC can read .gz files natively, so we use whichever is available
            uncompressed_name = file1_name.replace('.gz', '') if file1_name.endswith('.gz') else file1_name
            uncompressed_path = os.path.join(input_dir, uncompressed_name)
            compressed_path = os.path.join(input_dir, file1_name if file1_name.endswith('.gz') else file1_name + '.gz')

            if os.path.exists(uncompressed_path):
                # Prefer uncompressed file if available
                file1_path = uncompressed_path
                logger.debug(f"📁 Added file1 (uncompressed): {uncompressed_name}")
            elif os.path.exists(compressed_path):
                # Use compressed file (FastQC supports .gz natively)
                file1_path = compressed_path
                logger.debug(f"📁 Added file1 (compressed): {os.path.basename(compressed_path)}")
            else:
                # File not found in either format
                raise FileNotFoundError(
                    f"Input file not found: {uncompressed_name} or {os.path.basename(compressed_path)} "
                    f"in directory: {input_dir}"
                )

            if layout == 'pe':
                files['R1'] = file1_path
            else:  # SE
                files['SE'] = file1_path

        if 'file2' in sample_info and sample_info['file2']:
            file2_name = sample_info['file2']

            # Check for uncompressed file first, then compressed file
            # FastQC can read .gz files natively, so we use whichever is available
            uncompressed_name = file2_name.replace('.gz', '') if file2_name.endswith('.gz') else file2_name
            uncompressed_path = os.path.join(input_dir, uncompressed_name)
            compressed_path = os.path.join(input_dir, file2_name if file2_name.endswith('.gz') else file2_name + '.gz')

            if os.path.exists(uncompressed_path):
                # Prefer uncompressed file if available
                file2_path = uncompressed_path
                logger.debug(f"📁 Added file2 (uncompressed): {uncompressed_name}")
            elif os.path.exists(compressed_path):
                # Use compressed file (FastQC supports .gz natively)
                file2_path = compressed_path
                logger.debug(f"📁 Added file2 (compressed): {os.path.basename(compressed_path)}")
            else:
                # File not found in either format
                raise FileNotFoundError(
                    f"Input file not found: {uncompressed_name} or {os.path.basename(compressed_path)} "
                    f"in directory: {input_dir}"
                )

            files['R2'] = file2_path
        
        sample_info_dict = {
            'sample_name': sample_name,
            'group_name': group_name,
            'files': files,
            'output_base_dir': output_dir
        }
        sample_info_list.append(sample_info_dict)
        
        file_type = 'PE' if 'R2' in files else 'SE'
        logger.debug(f"   ├─ Sample: {sample_name} ({file_type})")
        logger.debug(f"   │   ├─ Condition: {group_name}")
        if file_type == 'PE':
            logger.debug(f"   │   ├─ R1: {os.path.basename(files['R1'])}")
            logger.debug(f"   │   └─ R2: {os.path.basename(files['R2'])}")
        else:
            logger.debug(f"   │   └─ SE: {os.path.basename(files['SE'])}")

    logger.info(f"✅ [FASTQC] Configuration completed: {len(sample_info_list)} samples ({sum(1 for s in sample_info_list if 'R1' in s['files'] and 'R2' in s['files'])} PE, {sum(1 for s in sample_info_list if 'SE' in s['files'])} SE)")

    # FastQC 파라미터 로그
    logger.debug(f"⚙️  [FASTQC] Parameters:")
    fastqc_params = {k: v for k, v in parameters.items() if k.startswith('fastqc_')}
    if fastqc_params:
        for key, value in fastqc_params.items():
            logger.debug(f"   ├─ {key}: {value}")
    else:
        logger.debug(f"   └─ Using default parameters")
    logger.debug(f"   └─ concurrent_jobs: {parameters.get('concurrent_jobs', 2)}")

    # ✅ execute_fastqc_multi() 호출 (worker_id와 workbench_id 전달)
    logger.info(f"🚀 [FASTQC] Starting parallel processing...")
    return execute_fastqc_multi(sample_info_list, parameters, worker_id, workbench_id)

def execute_fastqc_multi(sample_info_list: List[Dict], parameters: Dict, worker_id: str = "worker", workbench_id: int = None) -> Dict[str, str]:
    """
    FastQC SE/PE 통합 처리 (멀티프로세싱)
    SharedState Event 기반 stop 신호 처리
    실시간 진행률 전송 및 DB 저장
    """
    import time

    logger.debug(f"🚀 [FASTQC-MULTI] Starting multi-processing execution")
    logger.debug(f"📊 [FASTQC-MULTI] Configuration:")
    logger.debug(f"   ├─ Samples: {len(sample_info_list)}")
    logger.debug(f"   ├─ Worker ID: {worker_id}")
    logger.debug(f"   ├─ Workbench ID: {workbench_id}")
    logger.debug(f"   └─ Concurrent jobs: {parameters.get('concurrent_jobs', 3)}")
    
    start_time = time.time()
    concurrent_jobs = min(parameters.get('concurrent_jobs', 3), len(sample_info_list))
    
    # SharedState에서 해당 워커의 Event 가져오기
    try:
        worker_stop_event = shared_state.get_worker_event(worker_id)
        logger.info(f"✅ [FASTQC-MULTI] SharedState Event retrieved for worker: {worker_id}")
    except Exception as e:
        logger.error(f"❌ [FASTQC-MULTI] Failed to get worker event: {e}")
        return {
            'success': False,
            'message': f'Failed to get worker event: {str(e)}',
            'processed_samples': 0,
            'failed_samples': 0,
            'execution_time': 0,
            'stopped_by_user': False
        }
    
    # ProcessPoolRunner로 멀티프로세싱 실행
    work_args = [(sample_info, parameters, worker_id, workbench_id) for sample_info in sample_info_list]

    processed_samples = 0
    failed_samples = 0
    results = []
    total_samples = len(sample_info_list)

    # Calculate total files (file1 + file2 for each sample)
    total_files = 0
    for sample_info in sample_info_list:
        files = sample_info.get('files', {})
        if 'R1' in files or 'SE' in files:
            total_files += 1
        if 'R2' in files:
            total_files += 1

    logger.info(f"🎯 [FASTQC-MULTI] Starting parallel processing with {concurrent_jobs} workers...")
    logger.info(f"📊 [FASTQC-MULTI] Total samples: {total_samples}, Total files: {total_files}")

    # 시작 시 초기 진행률 전송 (0%)
    if workbench_id:
        initial_progress = {
            'completed_files': 0,
            'total_files': total_files,
            'progress_percent': 0.0
        }
        send_qc_progress_update(workbench_id, initial_progress)
        _save_qc_progress_to_db(workbench_id, 0, total_files)

    with ProcessPoolRunner(max_workers=concurrent_jobs, external_stop_event=worker_stop_event) as runner:
        try:
            for i, result in enumerate(runner.map_unordered(run_single_fastqc, work_args)):
                if result.get('stopped_by_user', False):
                    logger.warning(f"🛑 [FASTQC-MULTI] Sample processing stopped by user")
                    runner.stop()
                    # Reset worker event for next execution
                    shared_state.reset_worker(worker_id)
                    break

                # 결과 처리
                sample_name = result.get('sample_name', f'sample_{i+1}')
                if result.get('returncode', 0) == 0:
                    processed_samples += 1
                    logger.info(f"✅ [FASTQC-MULTI] [{i+1}/{len(sample_info_list)}] SUCCESS: {sample_name}")
                else:
                    failed_samples += 1
                    logger.warning(f"❌ [FASTQC-MULTI] [{i+1}/{len(sample_info_list)}] FAILED: {sample_name}")
                    logger.warning(f"   └─ Error: {result.get('stderr', 'Unknown error')[:200]}...")

                results.append(result)

                # 진행률 업데이트 (성공/실패 모두 완료로 카운트)
                # Calculate completed files based on the current sample's file count
                completed_file_count = 0
                for idx in range(i + 1):
                    sample = sample_info_list[idx]
                    files = sample.get('files', {})
                    if 'R1' in files or 'SE' in files:
                        completed_file_count += 1
                    if 'R2' in files:
                        completed_file_count += 1

                progress_percent = (completed_file_count / total_files * 100) if total_files > 0 else 0

                if workbench_id:
                    progress_data = {
                        'completed_files': completed_file_count,
                        'total_files': total_files,
                        'progress_percent': progress_percent
                    }

                    # Redis로 실시간 진행률 전송
                    send_qc_progress_update(workbench_id, progress_data)

                    # DB에 진행률 저장
                    _save_qc_progress_to_db(workbench_id, completed_file_count, total_files)

                logger.info(f"📊 [FASTQC-MULTI] Progress: {completed_file_count}/{total_files} files ({progress_percent:.1f}%)")
            
        except Exception as e:
            logger.error(f"💥 [FASTQC-MULTI] ProcessPoolRunner execution failed: {e}")
            return {
                'success': False,
                'message': f'Multi-processing execution failed: {str(e)}',
                'processed_samples': processed_samples,
                'failed_samples': failed_samples,
                'execution_time': time.time() - start_time,
                'stopped_by_user': False
            }
    
    execution_time = time.time() - start_time

    # 전체 결과 정리
    total_samples = len(sample_info_list)
    success_rate = (processed_samples / total_samples * 100) if total_samples > 0 else 0

    logger.info(f"🏁 [FASTQC-MULTI] Multi-processing execution completed!")
    logger.info(f"📊 [FASTQC-MULTI] Final statistics:")
    logger.info(f"   ├─ Total samples: {total_samples}")
    logger.info(f"   ├─ Successful: {processed_samples}")
    logger.info(f"   ├─ Failed: {failed_samples}")
    logger.info(f"   ├─ Success rate: {success_rate:.1f}%")
    logger.info(f"   └─ Total time: {execution_time:.2f}s")

    # 완료 시 최종 진행률 전송 (100% 또는 중단된 상태)
    if workbench_id:
        # Calculate final completed file count
        final_completed_file_count = 0
        for idx in range(len(results)):
            sample = sample_info_list[idx]
            files = sample.get('files', {})
            if 'R1' in files or 'SE' in files:
                final_completed_file_count += 1
            if 'R2' in files:
                final_completed_file_count += 1

        final_progress = {
            'completed_files': final_completed_file_count,
            'total_files': total_files,
            'progress_percent': (final_completed_file_count / total_files * 100) if total_files > 0 else 0
        }
        send_qc_progress_update(workbench_id, final_progress)
        # Note: _save_qc_progress_to_db는 완료 후에는 호출하지 않음 (job_worker에서 이미 step을 completed로 업데이트)
    
    # User stop 체크
    user_stopped = any(result.get('stopped_by_user', False) for result in results)
    overall_success = failed_samples == 0 and not user_stopped
    
    return {
        'success': overall_success,
        'message': f'FastQC processing completed: {processed_samples}/{total_samples} samples successful',
        'processed_samples': processed_samples,
        'failed_samples': failed_samples,
        'execution_time': execution_time,
        'stopped_by_user': user_stopped,
        'results': results
    }

def run_single_fastqc(sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """Process individual FastQC sample (SE/PE auto-detection)"""
    
    if stop_event and stop_event.is_set():
        return { 'success': False, 'stopped_by_user': True }
    
    import subprocess
    import os
    import logging
    import time
    import tempfile
    import shutil
    
    # Unified logging system
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')

    start_time = time.time()
    
    # ✅ Worker ID와 함께 입력 파라미터 로깅
    logger.info(f"🚀 [FASTQC-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
    logger.info(f"🚀 [FASTQC-{os.getpid()}] ║                FASTQC Function Started - Input Debug           ║")
    logger.info(f"🚀 [FASTQC-{os.getpid()}] ║                    Worker ID: {worker_id:<30} ║")
    logger.info(f"🚀 [FASTQC-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
    logger.info(f"")
    logger.info(f"📋 [FASTQC-{os.getpid()}] INPUT PARAMETERS DEBUG:")
    logger.info(f"")
    logger.info(f"🔍 [FASTQC-{os.getpid()}] sample_info contents:")
    for key, value in sample_info.items():
        if isinstance(value, dict):
            logger.info(f"   ├─ {key}: {{")
            for sub_key, sub_value in value.items():
                logger.info(f"   │     {sub_key}: {sub_value}")
            logger.info(f"   │   }}")
        else:
            logger.info(f"   ├─ {key}: {value}")
    
    logger.info(f"")
    logger.info(f"🔍 [FASTQC-{os.getpid()}] parameters contents:")
    for key, value in parameters.items():
        logger.info(f"   ├─ {key}: {value}")
    
    logger.info(f"")
    logger.info(f"💡 [FASTQC-{os.getpid()}] Raw JSON representations:")
    logger.info(f"   ├─ sample_info: {sample_info}")
    logger.info(f"   └─ parameters: {parameters}")
    logger.info(f"")
    
    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix=f"fastqc_{os.getpid()}_")
    
    # ✅ ProcessWrapper 생성 및 cleanup 함수 등록 (Stop 신호 처리용)
    wrapper = ProcessWrapper(worker_id)
    wrapper.register_cleanup(cleanup_temp_directory, temp_dir)
    
    try:
        sample_name = sample_info['sample_name']
        group_name = sample_info['group_name']
        files = sample_info['files']
        output_base_dir = sample_info['output_base_dir']
        
        logger.info(f"🎬 [FASTQC-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
        logger.info(f"🎬 [FASTQC-{os.getpid()}] ║                    FASTQC Sample Processing Started             ║")
        logger.info(f"🎬 [FASTQC-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
        logger.info(f"")
        logger.info(f"📋 [FASTQC-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"📋 [FASTQC-{os.getpid()}] STEP 1: Initial setup and environment preparation")
        logger.info(f"📋 [FASTQC-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"🔧 [FASTQC-{os.getpid()}] Sample information:")
        logger.info(f"   ├─ Group name: {group_name}")
        logger.info(f"   ├─ Sample name: {sample_name}")
        logger.info(f"   ├─ Process PID: {os.getpid()}")
        logger.info(f"   ├─ Output base path: {output_base_dir}")
        logger.info(f"   └─ Temporary work directory: {temp_dir}")
        logger.info(f"")
        logger.info(f"🗂️  [FASTQC-{os.getpid()}] Temporary directory status:")
        logger.info(f"   ├─ Path: {temp_dir}")
        logger.info(f"   ├─ Exists: {os.path.exists(temp_dir)}")
        logger.info(f"   └─ Permission: {'Writable' if os.access(temp_dir, os.W_OK) else 'Not writable'}")

        # Ensure input files are decompressed (auto-decompress .gz if needed)
        try:
            files = ensure_decompressed_files(files, logger)
        except FileNotFoundError as e:
            logger.error(f"   ❌ Input file preparation failed: {e}")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': group_name,
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': str(e),
                'pid': os.getpid()
            }

        # Log input file information
        file_type = 'PE' if ('R1' in files and 'R2' in files) else 'SE'
        logger.info(f"📁 [FASTQC-{os.getpid()}] Input files ({file_type}):")
        if file_type == 'SE':
            input_file = files['SE']
            file_size = os.path.getsize(input_file) if os.path.exists(input_file) else 0
            logger.info(f"   └─ SE: {os.path.basename(input_file)} ({file_size:,} bytes)")
        else:
            input_r1 = files['R1']
            input_r2 = files['R2']
            r1_size = os.path.getsize(input_r1) if os.path.exists(input_r1) else 0
            r2_size = os.path.getsize(input_r2) if os.path.exists(input_r2) else 0
            logger.info(f"   ├─ R1: {os.path.basename(input_r1)} ({r1_size:,} bytes)")
            logger.info(f"   └─ R2: {os.path.basename(input_r2)} ({r2_size:,} bytes)")
        
        # Extract group_name info and structure directories: fastqc/{group_name}/{sample}/
        sample_output_dir = os.path.join(output_base_dir, group_name, sample_name)
        
        logger.info(f"📂 [FASTQC-{os.getpid()}] Output structure:")
        logger.info(f"   └─ Sample dir: {sample_output_dir}")
        
        # Create output directories
        os.makedirs(sample_output_dir, exist_ok=True)
        logger.info(f"✅ [FASTQC-{os.getpid()}] Created output directories")
        
        # Configure FastQC parameters
        threads = parameters.get('fastqc_threads', parameters.get('threads', 2))
        extract = parameters.get('fastqc_extract', True)
        quiet = parameters.get('fastqc_quiet', False)
        
        logger.info(f"⚙️  [FASTQC-{os.getpid()}] FastQC parameters:")
        logger.info(f"   ├─ threads: {threads}")
        logger.info(f"   ├─ extract: {extract}")
        logger.info(f"   └─ quiet: {quiet}")
        
        # Build FastQC command
        fastqc_cmd = ['fastqc']
        
        # Add options
        if threads > 1:
            fastqc_cmd.extend(['--threads', str(threads)])
        if extract:
            fastqc_cmd.append('--extract')
        if quiet:
            fastqc_cmd.append('--quiet')
        
        # Add output directory
        fastqc_cmd.extend(['--outdir', sample_output_dir])
        
        # Add input files
        input_files = []
        if file_type == 'SE':
            input_files.append(files['SE'])
        else:  # PE
            input_files.extend([files['R1'], files['R2']])
        
        fastqc_cmd.extend(input_files)
        
        # FastQC 명령 실행
        logger.info(f"")
        logger.info(f"🧪 [FASTQC-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"🧪 [FASTQC-{os.getpid()}] STEP 2: FastQC 품질 분석 실행")
        logger.info(f"🧪 [FASTQC-{os.getpid()}] ═══════════════════════════════════════")
        cmd_str = ' '.join(fastqc_cmd)
        logger.info(f"🚀 [FASTQC-{os.getpid()}] 실행 명령어:")
        logger.info(f"   └─ {cmd_str}")
        logger.info(f"")
        logger.info(f"⏰ [FASTQC-{os.getpid()}] FastQC 프로세스 시작...")
        
        exec_start_time = time.time()
        
        # FastQC 프로세스 실행 (ProcessWrapper 사용)
        result = wrapper.run_command(fastqc_cmd, stop_event=stop_event)
        
        # Stop 신호로 인한 중단 체크
        if result['stopped_by_user']:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'FastQC stopped by user signal',
                'output_files': [],
                'stopped_by_user': True
            }
        exec_time = time.time() - exec_start_time
        
        logger.info(f"⏱️ [FASTQC-{os.getpid()}] FastQC 실행 완료!")
        logger.info(f"📊 [FASTQC-{os.getpid()}] 실행 결과:")
        logger.info(f"   ├─ 반환 코드: {result['returncode']} {'(성공)' if result['success'] else '(실패)'}")
        logger.info(f"   ├─ 실행 시간: {exec_time:.2f}초")
        logger.info(f"   ├─ 표준 출력 길이: {len(result['stdout']):,} 문자")
        logger.info(f"   └─ 표준 에러 길이: {len(result['stderr']):,} 문자")
        
        # stdout 요약 출력 (FastQC 결과 정보)
        if result['stdout'] and result['success']:
            logger.info(f"📈 [FASTQC-{os.getpid()}] FastQC 결과 요약:")
            stdout_lines = result['stdout'].strip().split('\n')
            for line in stdout_lines[-5:]:  # 마지막 5줄만 출력
                if line.strip():
                    logger.info(f"   │ {line.strip()}")
        
        # 결과 파일 검증
        logger.info(f"")
        logger.info(f"📋 [FASTQC-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"📋 [FASTQC-{os.getpid()}] STEP 3: 출력 파일 검증")
        logger.info(f"📋 [FASTQC-{os.getpid()}] ═══════════════════════════════════════")
        
        # 예상 출력 파일 목록 생성
        expected_files = []
        for input_file in input_files:
            base_name = os.path.basename(input_file)
            # Remove extensions
            if base_name.endswith('.fastq.gz'):
                base_name = base_name[:-9]
            elif base_name.endswith('.fq.gz'):
                base_name = base_name[:-6]
            elif base_name.endswith('.fastq'):
                base_name = base_name[:-6]
            elif base_name.endswith('.fq'):
                base_name = base_name[:-3]
            
            expected_files.extend([
                os.path.join(sample_output_dir, f"{base_name}_fastqc.html"),
                os.path.join(sample_output_dir, f"{base_name}_fastqc.zip")
            ])
        
        logger.info(f"🔍 [FASTQC-{os.getpid()}] 예상 출력 파일 {len(expected_files)}개 검증 중...")
        
        actual_output_files = []
        missing_files = []
        total_output_size = 0
        
        for i, expected_file in enumerate(expected_files, 1):
            logger.info(f"📄 [FASTQC-{os.getpid()}] [{i}/{len(expected_files)}] 검증: {os.path.basename(expected_file)}")
            if os.path.exists(expected_file):
                file_size = os.path.getsize(expected_file)
                actual_output_files.append(expected_file)
                total_output_size += file_size
                logger.info(f"   ✅ 발견: {file_size:,} bytes")
            else:
                missing_files.append(expected_file)
                logger.warning(f"   ❌ 누락: 파일이 생성되지 않음")
        
        logger.info(f"📊 [FASTQC-{os.getpid()}] 파일 검증 결과:")
        logger.info(f"   ├─ 생성된 파일: {len(actual_output_files)}/{len(expected_files)}")
        logger.info(f"   ├─ 누락된 파일: {len(missing_files)}")
        logger.info(f"   └─ 총 출력 크기: {total_output_size:,} bytes")
        
        # 최종 결과 처리
        if result['success']:
            total_time = time.time() - start_time
            logger.info(f"")
            logger.info(f"🏆 [FASTQC-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
            logger.info(f"🏆 [FASTQC-{os.getpid()}] ║                     처리 완료 - 성공!                         ║")
            logger.info(f"🏆 [FASTQC-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
            logger.info(f"🎯 [FASTQC-{os.getpid()}] 처리 결과 요약:")
            logger.info(f"   ├─ 그룹명: {group_name}")
            logger.info(f"   ├─ 샘플명: {sample_name}")
            logger.info(f"   ├─ 파일 타입: {file_type}")
            logger.info(f"   ├─ 생성된 파일: {len(actual_output_files)}/{len(expected_files)} 개")
            logger.info(f"   ├─ 총 처리 시간: {total_time:.2f}초")
            logger.info(f"   ├─ FastQC 실행 시간: {exec_time:.2f}초")
            logger.info(f"   ├─ 총 출력 크기: {total_output_size:,} bytes")
            logger.info(f"   └─ 출력 디렉토리: {sample_output_dir}")

            # AI 분석 자동 실행 (FastQC 성공 시)
            try:
                # Check if QC AI analysis is enabled for this user
                qc_analysis_enabled = False
                try:
                    from backend.utils.database import get_user_by_workbench_id
                    from backend.blueprints.settings import UserSettings

                    user_info = get_user_by_workbench_id(workbench_id)
                    if user_info:
                        user_id = user_info['id']
                        ai_settings = UserSettings.get_values(user_id, [
                            'ai.analysis_enabled',
                            'ai.features_enabled'
                        ])

                        analysis_enabled = ai_settings.get('ai.analysis_enabled', False)
                        features_enabled = ai_settings.get('ai.features_enabled', {})
                        qc_analysis_enabled = analysis_enabled and features_enabled.get('qc_analysis', False)

                        logger.info(f"🤖 [AI-QC-{os.getpid()}] User {user_id} AI settings: analysis_enabled={analysis_enabled}, qc_analysis={features_enabled.get('qc_analysis', False)}")
                    else:
                        logger.warning(f"🤖 [AI-QC-{os.getpid()}] No user found for workbench {workbench_id}")
                except Exception as e:
                    logger.error(f"🤖 [AI-QC-{os.getpid()}] Failed to check AI settings: {e}")

                if qc_analysis_enabled:
                    logger.info(f"")
                    logger.info(f"🤖 [AI-QC-{os.getpid()}] ═══════════════════════════════════════")
                    logger.info(f"🤖 [AI-QC-{os.getpid()}] AI 분석 시작")
                    logger.info(f"🤖 [AI-QC-{os.getpid()}] ═══════════════════════════════════════")

                    from backend.utils.ai.qc_ai_analyzer import perform_post_fastqc_ai_analysis

                    ai_analysis_result = perform_post_fastqc_ai_analysis(
                        sample_info=sample_info,
                        fastqc_result_path=sample_output_dir,
                        workbench_id=workbench_id,
                        experiment_type=parameters.get('experiment_type', 'RNA-seq')
                    )
                else:
                    logger.info(f"🤖 [AI-QC-{os.getpid()}] QC AI analysis disabled - skipping")
                    ai_analysis_result = {'status': 'skipped', 'reason': 'QC analysis disabled in user settings'}

                if ai_analysis_result['status'] == 'success':
                    logger.info(f"✅ [AI-QC-{os.getpid()}] AI 분석 완료!")
                    logger.info(f"   ├─ 분석 파일: {os.path.basename(ai_analysis_result.get('ai_file_path', ''))}")
                    logger.info(f"   └─ 처리 시간: {ai_analysis_result.get('analysis', {}).get('processing_time', 0):.2f}초")
                elif ai_analysis_result['status'] == 'skipped':
                    logger.info(f"⏭️ [AI-QC-{os.getpid()}] AI 분석 스킵됨")
                    logger.info(f"   └─ 사유: {ai_analysis_result.get('reason', 'QC analysis disabled')}")

                    # AI 분석이 스킵된 경우에도 상태 정보를 파일로 저장
                    try:
                        # FastQC가 생성한 각 _fastqc 디렉토리에 상태 파일 저장
                        for input_file in input_files:
                            base_name = os.path.basename(input_file)
                            # Remove extensions
                            if base_name.endswith('.fastq.gz'):
                                base_name = base_name[:-9]
                            elif base_name.endswith('.fq.gz'):
                                base_name = base_name[:-6]
                            elif base_name.endswith('.fastq'):
                                base_name = base_name[:-6]
                            elif base_name.endswith('.fq'):
                                base_name = base_name[:-3]

                            fastqc_dir = os.path.join(sample_output_dir, f"{base_name}_fastqc")
                            ai_status_file = os.path.join(fastqc_dir, 'ai_analysis.json')

                            # FastQC 디렉토리가 존재하면 상태 파일 저장
                            if os.path.exists(fastqc_dir):
                                status_data = {
                                    'ai_analysis_status': 'skipped',
                                    'ai_analysis_reason': ai_analysis_result.get('reason', 'QC analysis disabled in user settings'),
                                    'ai_analysis': None  # No actual analysis data
                                }
                                with open(ai_status_file, 'w', encoding='utf-8') as f:
                                    json.dump(status_data, f, indent=2, ensure_ascii=False)
                                logger.debug(f"📄 [AI-QC-{os.getpid()}] AI 상태 파일 저장: {ai_status_file}")
                    except Exception as status_error:
                        logger.warning(f"⚠️ [AI-QC-{os.getpid()}] AI 상태 파일 저장 실패: {status_error}")
                else:
                    logger.warning(f"⚠️ [AI-QC-{os.getpid()}] AI 분석 실패: {ai_analysis_result.get('error', 'Unknown error')}")
                    logger.warning(f"   └─ FastQC는 정상 완료됨")

            except Exception as ai_error:
                logger.warning(f"⚠️ [AI-QC-{os.getpid()}] AI 분석 중 예외 발생: {ai_error}")
                logger.warning(f"   └─ FastQC 결과는 유효함")
            
            if missing_files:
                logger.warning(f"")
                logger.warning(f"⚠️  [FASTQC-{os.getpid()}] 일부 예상 파일이 생성되지 않았습니다:")
                for missing in missing_files:
                    logger.warning(f"     └─ {os.path.basename(missing)}")
            else:
                logger.info(f"✨ [FASTQC-{os.getpid()}] 모든 예상 파일이 성공적으로 생성되었습니다!")
        else:
            logger.error(f"")
            logger.error(f"💥 [FASTQC-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
            logger.error(f"💥 [FASTQC-{os.getpid()}] ║                     처리 실패!                               ║")
            logger.error(f"💥 [FASTQC-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
            logger.error(f"❌ [FASTQC-{os.getpid()}] 실패 정보:")
            logger.error(f"   ├─ 샘플명: {sample_name}")
            logger.error(f"   ├─ 반환 코드: {result['returncode']}")
            logger.error(f"   ├─ 실행 시간: {exec_time:.2f}초")
            logger.error(f"   └─ 에러 상세 내용 확인 필요")
            
            # stderr가 있으면 일부 출력
            if result['stderr']:
                stderr_preview = result['stderr'][:500] + "..." if len(result['stderr']) > 500 else result['stderr']
                logger.error(f"")
                logger.error(f"📄 [FASTQC-{os.getpid()}] 에러 메시지 미리보기:")
                for line in stderr_preview.split('\n')[:10]:  # 최대 10줄까지
                    if line.strip():
                        logger.error(f"   │ {line.strip()}")
        
        return {
            'sample_name': sample_name,
            'condition': group_name,
            'returncode': result['returncode'],
            'stdout': result['stdout'],
            'stderr': result['stderr'],
            'output_files': actual_output_files,
            'expected_files': expected_files,
            'missing_files': missing_files,
            'execution_time': exec_time,
            'total_time': time.time() - start_time,
            'pid': os.getpid(),
            'ai_analysis_status': ai_analysis_result.get('status', 'unknown') if 'ai_analysis_result' in locals() else 'unknown',
            'ai_analysis_reason': ai_analysis_result.get('reason', '') if 'ai_analysis_result' in locals() else ''
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"💥 [FASTQC-{os.getpid()}] Critical exception occurred:")
        logger.error(f"   ├─ Sample: {sample_info.get('sample_name', 'unknown')}")
        logger.error(f"   ├─ Exception type: {type(e).__name__}")
        logger.error(f"   ├─ Exception message: {str(e)}")
        logger.error(f"   ├─ Processing time before error: {total_time:.2f}s")
        logger.error(f"   └─ PID: {os.getpid()}")
        
        # 스택 트레이스 일부 포함
        import traceback
        tb_lines = traceback.format_exc().split('\n')
        logger.error(f"   Stack trace (last 3 lines):")
        for line in tb_lines[-4:-1]:  # 마지막 몇 줄만 표시
            if line.strip():
                logger.error(f"     {line.strip()}")
        
        return {
            'sample_name': sample_info.get('sample_name', 'unknown'),
            'condition': sample_info.get('group_name', 'unknown'),
            'returncode': -1,
            'stdout': '',
            'stderr': str(e),
            'output_files': [],
            'expected_files': [],
            'missing_files': [],
            'execution_time': 0,
            'total_time': total_time,
            'pid': os.getpid(),
            'exception': str(e)
        }
    
    finally:
        # 정리 작업 시작
        total_final_time = time.time() - start_time
        logger.info(f"")
        logger.info(f"🧹 [FASTQC-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"🧹 [FASTQC-{os.getpid()}] STEP 4: 정리 작업 시작")
        logger.info(f"🧹 [FASTQC-{os.getpid()}] ═══════════════════════════════════════")
        
        # 임시 디렉토리 삭제
        logger.info(f"🗂️  [FASTQC-{os.getpid()}] 임시 디렉토리 정리 중...")
        try:
            if os.path.exists(temp_dir):
                # 디렉토리 내용 확인
                remaining_files = []
                try:
                    remaining_files = os.listdir(temp_dir)
                except:
                    pass
                
                if remaining_files:
                    logger.warning(f"⚠️  [FASTQC-{os.getpid()}] 임시 디렉토리에 남은 파일: {len(remaining_files)}개")
                    for file in remaining_files[:5]:  # 최대 5개까지만 표시
                        logger.warning(f"     └─ {file}")
                    if len(remaining_files) > 5:
                        logger.warning(f"     └─ ... 외 {len(remaining_files)-5}개")
                
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"   ✅ 임시 디렉토리 삭제 완료: {temp_dir}")
            else:
                logger.info(f"   📋 임시 디렉토리 이미 없음: {temp_dir}")
                
        except Exception as cleanup_error:
            logger.error(f"   ❌ 임시 디렉토리 삭제 실패: {temp_dir}")
            logger.error(f"       에러: {cleanup_error}")
        
        # 최종 요약
        logger.info(f"")
        logger.info(f"🏁 [FASTQC-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
        logger.info(f"🏁 [FASTQC-{os.getpid()}] ║                     전체 작업 완료                            ║")
        logger.info(f"🏁 [FASTQC-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
        logger.info(f"📊 [FASTQC-{os.getpid()}] 최종 통계:")
        logger.info(f"   ├─ 총 소요 시간: {total_final_time:.2f}초")
        logger.info(f"   ├─ 프로세스 PID: {os.getpid()}")
        logger.info(f"   └─ 정리 작업: 완료")


def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 fastqc tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering fastqc tool...")
    
    metadata = {
        'name': 'fastqc',
        'description': 'FastQC quality control analysis',
        'version': '1.0.0',
        'supported_formats': ['.fastq', '.fastq.gz', '.fq', '.fq.gz'],
        'requirements': ['fastqc'],
        'parameters': {
            'fastqc_threads': 2,
            'fastqc_extract': True,
            'fastqc_quiet': False
        }
    }
    
    return coordinator.register_tool('fastqc', execute_fastqc, metadata)
