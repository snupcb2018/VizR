"""
Bowtie/Bowtie2 alignment functionality for VizR pipeline
Trinity의 align_and_estimate_abundance.pl을 사용한 Alignment + Quantification 통합 처리
"""

import json
import os
import sqlite3
import logging
from typing import Dict, List, Any
from datetime import datetime
import time
import multiprocessing as mp

from backend.utils import database
from backend.utils.files import ensure_decompressed_files
from backend.blueprints.workbench_utils import get_workbench_schema
from config.backend_settings import BackendConfig as Config
from config.shared_config import SharedConfig
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.process_wrapper import ProcessWrapper
from backend.pipeline.utils.process_runner import ProcessPoolRunner
from backend.pipeline.utils.expression_matrix import run_rsem_matrix_integration

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def parse_rsem_cnt_file(cnt_file_path: str, sample_name: str) -> Dict[str, Any]:
    """
    RSEM.cnt 파일에서 alignment 통계 파싱 (RSEM v1.3.1)

    RSEM.cnt 파일 형식 (2번째 줄):
        n_assigned n_aligned n_total_fragments

    Args:
        cnt_file_path: RSEM.cnt 파일 경로
        sample_name: 샘플 이름

    Returns:
        Dict: 파싱된 RSEM 통계 정보
    """
    result = {
        "sample_name": sample_name,
        "total_reads": 0,
        "aligned_reads": 0,
        "alignment_rate": 0.0,
        "unalignable_reads": 0,
        "parsing_successful": False
    }

    try:
        if not os.path.exists(cnt_file_path):
            logger.warning(f"⚠️ [RSEM-CNT] File not found: {cnt_file_path}")
            return result

        logger.info(f"📄 [RSEM-CNT] Parsing RSEM.cnt file for {sample_name}")
        logger.info(f"📂 [RSEM-CNT] File path: {cnt_file_path}")

        with open(cnt_file_path, 'r') as f:
            lines = f.readlines()

            if len(lines) < 2:
                logger.warning(f"⚠️ [RSEM-CNT] Insufficient lines in file (expected ≥2, got {len(lines)})")
                return result

            # 2번째 줄 파싱 (index 1)
            # 형식: n_assigned n_aligned n_total_fragments
            second_line = lines[1].strip().split()

            if len(second_line) < 3:
                logger.warning(f"⚠️ [RSEM-CNT] Invalid format in line 2: {lines[1]}")
                return result

            n_assigned = int(second_line[0])   # 할당된 fragment 수
            n_aligned = int(second_line[1])    # 정렬된 fragment 수
            n_total = int(second_line[2])      # 총 fragment 수

            logger.info(f"📊 [RSEM-CNT] Raw values from file:")
            logger.info(f"   ├─ Assigned fragments: {n_assigned:,}")
            logger.info(f"   ├─ Aligned fragments: {n_aligned:,}")
            logger.info(f"   └─ Total fragments: {n_total:,}")

            # Fragment 수를 Read 수로 변환 (Paired-end는 ×2)
            # Alignment rate는 fragment 기준으로 계산
            result["total_reads"] = n_total * 2      # Fragment → Reads (PE)
            result["aligned_reads"] = n_aligned * 2
            result["unalignable_reads"] = (n_total - n_aligned) * 2

            if n_total > 0:
                result["alignment_rate"] = (n_aligned / n_total) * 100

            result["parsing_successful"] = True

            logger.info(f"✅ [RSEM-CNT] Successfully parsed RSEM.cnt for {sample_name}")
            logger.info(f"📊 [RSEM-CNT] Alignment summary:")
            logger.info(f"   ├─ Total reads: {result['total_reads']:,}")
            logger.info(f"   ├─ Aligned reads: {result['aligned_reads']:,}")
            logger.info(f"   ├─ Unalignable reads: {result['unalignable_reads']:,}")
            logger.info(f"   └─ Alignment rate: {result['alignment_rate']:.2f}%")

    except Exception as e:
        logger.error(f"❌ [RSEM-CNT] Error parsing {cnt_file_path}: {e}")
        import traceback
        logger.error(f"   └─ Traceback: {traceback.format_exc()}")
        result["parsing_successful"] = False

    return result


def execute_bowtie(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, Any]:
    """Bowtie/Bowtie2 실행 - job_step에서 직접 정보 추출"""
    try:
        # job_step에서 직접 정보 추출
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

        # Username 조회 (사용자별 resource 경로 구성용)
        with database.get_db_connection() as db_connection:
            cursor = db_connection.cursor()
            cursor.execute("""
                SELECT username FROM users
                WHERE id = ?
            """, (workbench['user_id'],))
            user_result = cursor.fetchone()

        if not user_result:
            raise ValueError(f"User {workbench['user_id']} not found")

        username = user_result['username']

        logger.info(f"🎯 [BOWTIE] Starting Bowtie alignment + quantification process")
        logger.info(f"📋 [BOWTIE] Job Configuration:")
        logger.info(f"   ├─ workbench_id: {workbench_id}")
        logger.info(f"   ├─ user: {username}")
        logger.info(f"   └─ step_id: {step_id}")

        # 출력 디렉토리 설정
        output_dir = os.path.join(workbench_schema["quanti"]["alignment"])
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"📁 [BOWTIE] Created output directory: {output_dir}")

        # Reference 세트 선택 (기본값: TAIR10)
        reference_set = parameters.get('reference_set', 'TAIR10')
        species = parameters.get('species', 'arabidopsis')

        logger.info(f"🧬 [BOWTIE] Reference configuration:")
        logger.info(f"   ├─ Species: {species}")
        logger.info(f"   └─ Reference set: {reference_set}")

        # Reference 세트 디렉토리 경로
        reference_dir = f"{SharedConfig.VIZR_PATH}/users/{username}/resource/{species}/reference/{reference_set}"
        metadata_file = os.path.join(reference_dir, "metadata.json")

        # metadata.json 읽기
        if not os.path.exists(metadata_file):
            error_msg = f"Reference metadata not found: {metadata_file}"
            logger.error(f"❌ [BOWTIE] {error_msg}")
            raise FileNotFoundError(error_msg)

        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        logger.info(f"📋 [BOWTIE] Loaded metadata: {metadata.get('name', 'Unknown')} v{metadata.get('version', 'Unknown')}")

        # cDNA Reference 파일 경로 (Bowtie는 transcript alignment)
        cdna_filename = metadata['files']['cdna']
        reference_file = os.path.join(reference_dir, cdna_filename)

        logger.info(f"📄 [BOWTIE] Reference file: {cdna_filename}")

        # Reference 파일 존재 확인
        if not os.path.exists(reference_file):
            error_msg = f"Reference file not found: {reference_file}"
            logger.error(f"❌ [BOWTIE] {error_msg}")
            raise FileNotFoundError(error_msg)

        # samples_data 구성
        sample_info_list = []

        # workbench_id에서 샘플 정보와 layout 정보 조회
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
                logger.info(f"📊 [BOWTIE] Retrieved samples from vizr_pipeline_samples (layout: {layout})")

                try:
                    samples_data = json.loads(samples_json)
                    logger.info(f"✅ [BOWTIE] {len(samples_data)} samples")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ [BOWTIE] Failed to parse samples JSON: {e}")
                    raise
            else:
                logger.warning(f"⚠️  [BOWTIE] No samples found for workbench_id: {workbench_id}")
                layout = 'pe'  # 기본값

        logger.info(f"🔍 [BOWTIE-DEBUG] Layout 정보: {layout}")

        # 이전 단계 확인 (clean_tools에서 어떤 clean tool들이 실행되었는지 확인)
        clean_tools = parameters.get('clean_tools', [])

        # 입력 파일 경로 결정
        if 'prinseq' in clean_tools:
            input_dir = os.path.join(workbench_schema["quanti"]["clean"], "prinseq")
            logger.info(f"📂 [BOWTIE] Input from PRINSEQ: {input_dir}")
        elif 'trimmomatic' in clean_tools:
            input_dir = os.path.join(workbench_schema["quanti"]["clean"], "trim")
            logger.info(f"📂 [BOWTIE] Input from Trimmomatic: {input_dir}")
        else:
            input_dir = workbench_schema["quanti"]["raw"]
            logger.info(f"📂 [BOWTIE] Input from raw files: {input_dir}")

        logger.info(f"⚙️ [BOWTIE] Configuration analysis:")
        logger.info(f"   ├─ Clean tools: {clean_tools}")
        logger.info(f"   ├─ Input directory: {input_dir}")
        logger.info(f"   └─ Layout: {layout}")

        # 각 샘플에 대한 파일 경로 구성
        for sample_info in samples_data:
            sample_name = sample_info['sampleName']
            group_name = sample_info['groupName']

            files = {}

            if 'prinseq' in clean_tools:
                # PRINSEQ 후: good 디렉토리에서 파일 찾기
                sample_input_dir = os.path.join(input_dir, group_name, sample_name, "good")
                if layout == 'pe':
                    files['R1'] = os.path.join(sample_input_dir, f"{sample_name}_good_1.fastq")
                    files['R2'] = os.path.join(sample_input_dir, f"{sample_name}_good_2.fastq")
                else:
                    files['SE'] = os.path.join(sample_input_dir, f"{sample_name}_good.fastq")

            elif 'trimmomatic' in clean_tools:
                # Trimmomatic 후: 파일 찾기
                sample_input_dir = os.path.join(input_dir, group_name, sample_name)
                if layout == 'pe':
                    files['R1'] = os.path.join(sample_input_dir, f"{sample_name}_1_paired.fastq")
                    files['R2'] = os.path.join(sample_input_dir, f"{sample_name}_2_paired.fastq")
                else:
                    files['SE'] = os.path.join(sample_input_dir, f"{sample_name}_trimmed.fastq")

            else:
                # Raw 파일 직접 사용
                if 'file1' in sample_info and sample_info['file1']:
                    file1_name = sample_info['file1']
                    if file1_name.endswith('.gz'):
                        file1_name = file1_name[:-3]

                    file1_path = os.path.join(input_dir, file1_name)
                    if layout == 'pe':
                        files['R1'] = file1_path
                    else:
                        files['SE'] = file1_path

                if 'file2' in sample_info and sample_info['file2']:
                    file2_name = sample_info['file2']
                    if file2_name.endswith('.gz'):
                        file2_name = file2_name[:-3]

                    file2_path = os.path.join(input_dir, file2_name)
                    files['R2'] = file2_path

            # 출력 디렉토리 설정
            sample_output_dir = os.path.join(output_dir, group_name, sample_name)
            os.makedirs(sample_output_dir, exist_ok=True)

            sample_info_dict = {
                'sample_name': sample_name,
                'condition': group_name,
                'files': files,
                'output_dir': sample_output_dir,
                'reference_file': reference_file,
                'layout': layout
            }
            sample_info_list.append(sample_info_dict)

            file_type = 'PE' if 'R2' in files else 'SE'
            logger.info(f"   ├─ Sample: {sample_name}")
            logger.info(f"   │   ├─ Condition: {group_name}")
            logger.info(f"   │   ├─ File type: {file_type}")
            if file_type == 'PE':
                logger.info(f"   │   ├─ R1: {os.path.basename(files['R1'])}")
                logger.info(f"   │   ├─ R2: {os.path.basename(files['R2'])}")
            else:
                logger.info(f"   │   ├─ SE: {os.path.basename(files['SE'])}")
            logger.info(f"   │   └─ Output dir: {sample_output_dir}")

        # 멀티프로세싱으로 Bowtie 실행
        logger.info(f"🚀 [BOWTIE] Starting multi-processing alignment for {len(sample_info_list)} samples")
        results = execute_bowtie_multi(sample_info_list, parameters, worker_id, workbench_id)

        return results

    except Exception as e:
        logger.error(f"💥 [BOWTIE] Exception in execute_bowtie: {str(e)}")
        return {
            'success': False,
            'stdout': '',
            'stderr': f"Bowtie execution exception: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }


def execute_bowtie_multi(sample_info_list: List[Dict], parameters: Dict, worker_id: str = "bowtie_multi", workbench_id: int = None) -> Dict[str, Any]:
    """Bowtie 병렬 실행"""

    if not sample_info_list:
        return {
            'success': True,
            'stdout': '',
            'stderr': 'No samples to process\n',
            'processed_samples': [],
            'output_files': [],
            'timestamp': datetime.now().isoformat()
        }

    start_time = time.time()
    logger.info(f"🚀 [BOWTIE-MULTI-POOL] Starting Pool-based Bowtie alignment")
    logger.info(f"📊 [BOWTIE-MULTI-POOL] Configuration:")
    logger.info(f"   ├─ Total samples: {len(sample_info_list)}")
    logger.info(f"   └─ Processing mode: multiprocessing.Pool")

    # SharedState에서 해당 워커의 Event 가져오기
    try:
        worker_stop_event = shared_state.get_worker_event(worker_id)
        logger.info(f"📡 [BOWTIE-MULTI-POOL] Using SharedState Event for worker: {worker_id}")
    except ValueError as e:
        logger.error(f"❌ [BOWTIE-MULTI-POOL] Worker not registered: {e}")
        return {
            'success': False,
            'stdout': '',
            'stderr': f'Worker {worker_id} not registered in SharedState',
            'processed_samples': [],
            'output_files': [],
            'timestamp': datetime.now().isoformat(),
            'execution_time': time.time() - start_time
        }

    # 프로세스 간 공유 Lock 생성
    manager = mp.Manager()
    shared_db_lock = manager.Lock()
    logger.info(f"🔒 [BOWTIE-MULTI] Created shared DB lock for multiprocessing")

    # 작업 인수 준비
    work_args = []
    for i, sample_info in enumerate(sample_info_list):
        worker_id_sample = f"bowtie_sample_{i}_{sample_info['sample_name']}"
        work_args.append((sample_info, parameters, worker_id_sample, workbench_id))

    sample_results = []
    failed_samples = []
    output_files = []

    # 초기 진행률 전송
    completed_samples = 0
    total_samples = len(sample_info_list)

    if workbench_id:
        initial_progress = {
            "completed_samples": completed_samples,
            "total_samples": total_samples,
            "progress_percent": 0.0,
            "current_sample": None
        }
        send_bowtie_progress_update(workbench_id, initial_progress)
        _save_bowtie_progress_to_db(workbench_id, completed_samples, total_samples, shared_db_lock)

    with ProcessPoolRunner(max_workers=4, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
        try:
            logger.info(f"🔄 [BOWTIE-MULTI-POOL] Processing {len(work_args)} samples...")

            for i, result in enumerate(runner.map_unordered(run_single_bowtie, work_args)):
                # 사용자 중단 체크
                if result.get('stopped_by_user', False):
                    logger.warning(f"⏹️ [BOWTIE-MULTI-POOL] Sample processing stopped by user")
                    runner.stop()
                    shared_state.reset_worker(worker_id)
                    break

                # 결과 수집
                sample_results.append(result)

                if result['success']:
                    output_files.extend(result.get('output_files', []))
                    logger.info(f"✅ [BOWTIE-MULTI-POOL] Completed sample {i+1}/{len(work_args)}: {result['sample_name']}")
                else:
                    failed_samples.append(result['sample_name'])
                    logger.error(f"❌ [BOWTIE-MULTI-POOL] Failed sample {i+1}/{len(work_args)}: {result['sample_name']}")

                # 진행률 업데이트
                if workbench_id:
                    completed_samples = i + 1
                    progress_percent = (completed_samples / total_samples * 100) if total_samples > 0 else 0.0

                    progress_data = {
                        "completed_samples": completed_samples,
                        "total_samples": total_samples,
                        "progress_percent": progress_percent,
                        "current_sample": result.get('sample_name', 'unknown')
                    }

                    send_bowtie_progress_update(workbench_id, progress_data)
                    _save_bowtie_progress_to_db(workbench_id, completed_samples, total_samples, shared_db_lock)
                    logger.info(f"📊 [BOWTIE-MULTI] Progress: {completed_samples}/{total_samples} ({progress_percent:.1f}%)")

        except Exception as e:
            logger.error(f"💥 [BOWTIE-MULTI-POOL] Exception during processing: {e}")
            return {
                'success': False,
                'stdout': '',
                'stderr': f"Multi-processing exception: {str(e)}",
                'processed_samples': [],
                'output_files': [],
                'failed_samples': failed_samples,
                'timestamp': datetime.now().isoformat(),
                'execution_time': time.time() - start_time
            }

    # 최종 결과 집계
    execution_time = time.time() - start_time
    success_count = len([r for r in sample_results if r['success']])

    logger.info(f"🎯 [BOWTIE] Multi-sample alignment completed")
    logger.info(f"   ├─ Total samples: {len(sample_info_list)}")
    logger.info(f"   ├─ Successful: {success_count}")
    logger.info(f"   ├─ Failed: {len(failed_samples)}")
    logger.info(f"   ├─ Output files: {len(output_files)}")
    logger.info(f"   └─ Execution time: {execution_time:.1f}s")

    # RSEM 매트릭스 통합 (모든 샘플 성공 시에만)
    matrix_integration_result = {}
    if len(failed_samples) == 0 and workbench_id:
        logger.info(f"")
        logger.info(f"🔬 [BOWTIE-MULTI] All samples completed successfully - Starting RSEM matrix integration...")

        try:
            # workbench 정보 조회
            with database.get_db_connection() as conn:
                workbench = conn.execute("""
                    SELECT name, user_id FROM vizr_workbench
                    WHERE id = ?
                """, (workbench_id,)).fetchone()

            if not workbench:
                raise ValueError(f"Workbench {workbench_id} not found")

            workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])

            # alignment 디렉토리 경로
            alignment_dir = workbench_schema["quanti"]["alignment"]

            logger.info(f"📂 [BOWTIE-MULTI] Alignment directory: {alignment_dir}")

            # RSEM 매트릭스 통합 실행
            matrix_result = run_rsem_matrix_integration(
                alignment_dir=alignment_dir,
                sample_info_list=sample_info_list,
                workbench_id=workbench_id,
                worker_id=f"{worker_id}_matrix"
            )

            matrix_integration_result = matrix_result

            if matrix_result.get('success'):
                logger.info(f"✅ [BOWTIE-MULTI] RSEM matrix integration completed successfully!")
                logger.info(f"   ├─ Matrix file: {matrix_result.get('matrix_file')}")
                logger.info(f"   ├─ Processed samples: {matrix_result.get('processed_samples')}")
                logger.info(f"   └─ Execution time: {matrix_result.get('execution_time', 0):.2f}s")
            else:
                logger.error(f"❌ [BOWTIE-MULTI] RSEM matrix integration failed!")
                logger.error(f"   └─ Error: {matrix_result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"❌ [BOWTIE-MULTI] Exception during RSEM matrix integration: {str(e)}")
            logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")
            matrix_integration_result = {
                'success': False,
                'error': str(e)
            }
    elif len(failed_samples) > 0:
        logger.warning(f"⚠️ [BOWTIE-MULTI] Skipping RSEM matrix integration due to failed samples")

    logger.info(f"")

    return {
        'success': len(failed_samples) == 0,
        'stdout': '\n'.join([r.get('stdout', '') for r in sample_results]),
        'stderr': '\n'.join([r.get('stderr', '') for r in sample_results if r.get('stderr')]),
        'processed_samples': [r['sample_name'] for r in sample_results if r['success']],
        'failed_samples': failed_samples,
        'output_files': output_files,
        'sample_results': sample_results,
        'matrix_integration': matrix_integration_result,
        'timestamp': datetime.now().isoformat(),
        'execution_time': execution_time
    }


def run_single_bowtie(sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "bowtie_worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """개별 Bowtie 샘플 처리 (Trinity Docker 사용)"""

    if stop_event and stop_event.is_set():
        return {'success': False, 'stopped_by_user': True}

    # ProcessWrapper 생성
    wrapper = ProcessWrapper(worker_id)

    # Unified logging system
    from backend.utils.logger import setup_module_logger
    process_logger = setup_module_logger(__name__, 'INFO')
    start_time = time.time()

    process_logger.info(f"🎯 [BOWTIE-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
    process_logger.info(f"🎯 [BOWTIE-{os.getpid()}] ║          Bowtie + RSEM Function Started - Input Debug           ║")
    process_logger.info(f"🎯 [BOWTIE-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")

    try:
        sample_name = sample_info['sample_name']
        condition = sample_info['condition']
        files = sample_info['files']
        output_dir = sample_info['output_dir']
        reference_file = sample_info['reference_file']
        layout = sample_info['layout']

        process_logger.info(f"🔧 [BOWTIE-{os.getpid()}] Sample configuration:")
        process_logger.info(f"   ├─ Sample: {sample_name}")
        process_logger.info(f"   ├─ Condition: {condition}")
        process_logger.info(f"   ├─ Layout: {layout}")
        process_logger.info(f"   ├─ Reference: {os.path.basename(reference_file)}")
        process_logger.info(f"   └─ Output dir: {output_dir}")

        # Ensure input files are decompressed (auto-decompress .gz if needed)
        try:
            files = ensure_decompressed_files(files, process_logger)
        except FileNotFoundError as e:
            process_logger.error(f"   ❌ Input file preparation failed: {e}")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': str(e),
                'pid': os.getpid()
            }

        # Input files validation
        process_logger.info(f"📁 [BOWTIE-{os.getpid()}] Input file validation:")
        for file_type, file_path in files.items():
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                process_logger.info(f"   ✅ {file_type}: {os.path.basename(file_path)} ({file_size:,} bytes)")
            else:
                process_logger.error(f"   ❌ {file_type}: {file_path} - File not found!")
                return {
                    'success': False,
                    'sample_name': sample_name,
                    'condition': condition,
                    'returncode': -1,
                    'stdout': '',
                    'stderr': f"Input file not found: {file_path}",
                    'output_files': [],
                    'execution_time': time.time() - start_time,
                    'error_message': f"Input file not found: {file_path}",
                    'pid': os.getpid()
                }

        # Reference file validation
        if not os.path.exists(reference_file):
            process_logger.error(f"❌ [BOWTIE-{os.getpid()}] Reference file not found: {reference_file}")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': '',
                'stderr': f"Reference file not found: {reference_file}",
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': f"Reference file not found: {reference_file}",
                'pid': os.getpid()
            }

        # 경로 변환 (VizR 컨테이너 → 호스트)
        # 입력 파일들의 디렉토리
        if layout == 'pe' and 'R1' in files:
            input_file_dir = os.path.dirname(files['R1'])
        elif layout == 'se' and 'SE' in files:
            input_file_dir = os.path.dirname(files['SE'])
        else:
            error_msg = f"Invalid file configuration for layout {layout}: {files}"
            process_logger.error(f"❌ [BOWTIE-{os.getpid()}] {error_msg}")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': '',
                'stderr': error_msg,
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': error_msg,
                'pid': os.getpid()
            }

        # 경로 변환
        host_input_dir = input_file_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        host_output_dir = output_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        host_reference_dir = os.path.dirname(reference_file).replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)

        process_logger.info(f"🔄 [BOWTIE-{os.getpid()}] Path conversion: container→host")
        process_logger.info(f"   ├─ Input: {input_file_dir} → {host_input_dir}")
        process_logger.info(f"   ├─ Output: {output_dir} → {host_output_dir}")
        process_logger.info(f"   └─ Reference: {os.path.dirname(reference_file)} → {host_reference_dir}")

        # Trinity align_and_estimate_abundance.pl 명령어 구성
        tool_name = parameters.get('tool_name', 'bowtie2')  # bowtie or bowtie2

        # Tool name 유효성 검증
        if tool_name not in ['bowtie', 'bowtie2']:
            process_logger.warning(f"⚠️ [BOWTIE-{os.getpid()}] Invalid tool_name '{tool_name}', defaulting to 'bowtie2'")
            tool_name = 'bowtie2'

        process_logger.info(f"🔧 [BOWTIE-{os.getpid()}] Using alignment tool: {tool_name}")

        threads = parameters.get('threads', 4)

        # 파일명 (Docker 컨테이너 내부 경로)
        reference_filename = os.path.basename(reference_file)

        # Trinity 명령어 구성 (절대 경로 사용)
        trinity_cmd = (
            f"/usr/local/bin/util/align_and_estimate_abundance.pl "
            f"--transcripts /reference/{reference_filename} "
            f"--seqType fq "
        )

        # Layout에 따른 입력 파일 지정
        if layout == 'pe' and 'R1' in files and 'R2' in files:
            r1_filename = os.path.basename(files['R1'])
            r2_filename = os.path.basename(files['R2'])
            trinity_cmd += f"--left /input/{r1_filename} --right /input/{r2_filename} "
            process_logger.info(f"🔧 [BOWTIE-{os.getpid()}] PE mode: R1={r1_filename}, R2={r2_filename}")
        elif layout == 'se' and 'SE' in files:
            se_filename = os.path.basename(files['SE'])
            trinity_cmd += f"--single /input/{se_filename} "
            process_logger.info(f"🔧 [BOWTIE-{os.getpid()}] SE mode: SE={se_filename}")

        trinity_cmd += (
            f"--output_dir /output "
            f"--est_method RSEM "
            f"--aln_method {tool_name} "
            f"--thread_count {threads} "
            f"--prep_reference"  # Index 자동 생성
        )

        # Docker 명령어
        # exec를 사용하여 bash를 perl 프로세스로 대체 (백그라운드 프로세스 파이프 상속 문제 해결)
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_input_dir}:/input",
            "-v", f"{host_output_dir}:/output",
            "-v", f"{host_reference_dir}:/reference",
            "-w", "/output",
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            f"exec {trinity_cmd}"
        ]

        process_logger.info(f"🚀 [BOWTIE-{os.getpid()}] Running Trinity align_and_estimate_abundance.pl...")
        process_logger.info(f"   └─ Command: {' '.join(docker_cmd[:10])}...")

        # Trinity Docker 실행
        result = wrapper.run_command(docker_cmd, cwd=output_dir, stop_event=stop_event)

        # Stop 신호 체크
        if result['stopped_by_user']:
            process_logger.info(f"⏹️ [BOWTIE-{os.getpid()}] Bowtie+RSEM stopped by user")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': '',
                'stderr': 'Bowtie+RSEM stopped by user',
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': 'Bowtie+RSEM stopped by user',
                'pid': os.getpid(),
                'stopped_by_user': True
            }

        trinity_result = result

        process_logger.info(f"⏱️  [BOWTIE-{os.getpid()}] Trinity completed with return code: {trinity_result['returncode']}")

        if trinity_result['returncode'] != 0:
            process_logger.error(f"❌ [BOWTIE-{os.getpid()}] Trinity failed!")
            process_logger.error(f"   ├─ Return code: {trinity_result['returncode']}")
            process_logger.error(f"   ├─ STDERR: {trinity_result['stderr'][:500]}...")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': trinity_result['returncode'],
                'stdout': trinity_result['stdout'],
                'stderr': trinity_result['stderr'],
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': f"Trinity failed with return code {trinity_result['returncode']}",
                'pid': os.getpid()
            }

        # RSEM.cnt 파일에서 결과 파싱
        process_logger.info(f"📊 [BOWTIE-{os.getpid()}] Parsing RSEM statistics from RSEM.cnt file...")

        cnt_file_path = os.path.join(output_dir, "RSEM.stat", "RSEM.cnt")
        rsem_parsed_result = parse_rsem_cnt_file(cnt_file_path, sample_name)

        if rsem_parsed_result and rsem_parsed_result.get('parsing_successful', False):
            process_logger.info(f"✅ [BOWTIE-{os.getpid()}] Successfully parsed RSEM statistics from RSEM.cnt")
            process_logger.info(f"📊 [BOWTIE-{os.getpid()}] Summary: "
                              f"total={rsem_parsed_result.get('total_reads', 0):,}, "
                              f"aligned={rsem_parsed_result.get('aligned_reads', 0):,}, "
                              f"rate={rsem_parsed_result.get('alignment_rate', 0):.2f}%")

            # DB에 결과 저장
            if workbench_id:
                _save_bowtie_result_to_db(workbench_id, sample_name, rsem_parsed_result, shared_db_lock)
        else:
            process_logger.warning(f"⚠️ [BOWTIE-{os.getpid()}] Failed to parse RSEM.cnt file")
            process_logger.warning(f"   └─ Expected file: {cnt_file_path}")

        # 출력 파일 확인
        output_files = []
        expected_outputs = [
            f"{tool_name}.bam",
            "RSEM.genes.results",
            "RSEM.isoforms.results"
        ]

        for filename in expected_outputs:
            file_path = os.path.join(output_dir, filename)
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                output_files.append(file_path)
                process_logger.info(f"✅ [BOWTIE-{os.getpid()}] Generated: {filename} ({file_size:,} bytes)")

        execution_time = time.time() - start_time
        process_logger.info(f"🎉 [BOWTIE-{os.getpid()}] Sample completed successfully!")
        process_logger.info(f"   ├─ Execution time: {execution_time:.1f}s")
        process_logger.info(f"   └─ Output files: {len(output_files)}")

        # 최종 반환 데이터
        final_result = {
            'success': True,
            'sample_name': sample_name,
            'condition': condition,
            'returncode': 0,
            'stdout': trinity_result['stdout'],
            'stderr': trinity_result['stderr'],
            'output_files': output_files,
            'execution_time': execution_time,
            'pid': os.getpid()
        }

        # 파싱된 RSEM 통계 정보 추가
        if rsem_parsed_result and rsem_parsed_result.get('parsing_successful', False):
            final_result.update({
                'total_reads': rsem_parsed_result.get('total_reads', 0),
                'aligned_reads': rsem_parsed_result.get('aligned_reads', 0),
                'alignment_rate': rsem_parsed_result.get('alignment_rate', 0.0),
                'parsing_successful': True
            })
        else:
            final_result.update({
                'total_reads': 0,
                'aligned_reads': 0,
                'alignment_rate': 0.0,
                'parsing_successful': False
            })

        return final_result

    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"Exception in run_single_bowtie: {str(e)}"
        process_logger.error(f"💥 [BOWTIE-{os.getpid()}] {error_msg}")

        return {
            'success': False,
            'sample_name': sample_info.get('sample_name', 'unknown'),
            'condition': sample_info.get('condition', 'unknown'),
            'returncode': -1,
            'stdout': '',
            'stderr': error_msg,
            'output_files': [],
            'execution_time': execution_time,
            'error_message': error_msg,
            'pid': os.getpid()
        }


def send_bowtie_progress_update(workbench_id: int, progress_data: dict) -> bool:
    """Bowtie 진행률 직접 전송"""
    try:
        from backend.pipeline.utils.redis_broker import get_redis_broker
        redis_broker = get_redis_broker()

        if not redis_broker.is_available():
            logger.debug(f"📡 [BOWTIE-PROGRESS] Redis not available, skipping progress update")
            return False

        success = redis_broker.publish_progress(
            workbench_id=workbench_id,
            task_type='bowtie',
            progress_data=progress_data
        )

        if success:
            logger.debug(f"📡 [BOWTIE-PROGRESS] Successfully sent progress update: {progress_data}")
        else:
            logger.warning(f"📡 [BOWTIE-PROGRESS] Failed to send progress update")

        return success

    except Exception as e:
        logger.error(f"❌ [BOWTIE-PROGRESS] Error sending progress update: {e}")
        return False


def _save_bowtie_progress_to_db(workbench_id: int, completed_samples: int, total_samples: int, shared_db_lock=None) -> bool:
    """Bowtie 진행률 정보를 DB에 저장"""
    current_process = mp.current_process()
    pid = current_process.pid

    logger.info(f"📊 [BOWTIE-PROGRESS-DB] Updating progress (PID={pid}): {completed_samples}/{total_samples}")

    try:
        # 진행률 계산
        if total_samples > 0:
            progress_percent = (completed_samples / total_samples) * 100
        else:
            progress_percent = 0.0

        # 현재 시간
        current_time = time.time()

        # Lock 사용
        if shared_db_lock is not None:
            logger.info(f"🔒 [BOWTIE-PROGRESS-DB] Using shared_db_lock (PID={pid})")
            with shared_db_lock:
                # 기존 progress_detail 가져오기
                existing_data = {}
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    result = cursor.execute('''
                        SELECT progress_detail FROM pipeline_job_steps
                        WHERE workbench_id = ? AND (tool_name = 'bowtie' OR tool_name = 'bowtie2')
                    ''', (workbench_id,)).fetchone()

                    if result and result[0]:
                        try:
                            existing_data = json.loads(result[0])
                        except (json.JSONDecodeError, TypeError):
                            existing_data = {"summary": {}, "results": {}}
                    else:
                        existing_data = {"summary": {}, "results": {}}

                # 구조 확인
                if "results" not in existing_data:
                    existing_data["results"] = {}
                if "summary" not in existing_data:
                    existing_data["summary"] = {}

                # Summary 업데이트
                existing_data["summary"] = {
                    "completed_files": completed_samples,
                    "total_files": total_samples,
                    "progress_percent": round(progress_percent, 2),
                    "last_updated": current_time
                }

                logger.info(f"📈 [BOWTIE-PROGRESS-DB] Updated summary (PID={pid}): {completed_samples}/{total_samples} ({progress_percent:.1f}%)")

                # JSON 직렬화
                json_str = json.dumps(existing_data)

                # DB 업데이트
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE pipeline_job_steps
                        SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE workbench_id = ? AND (tool_name = 'bowtie' OR tool_name = 'bowtie2')
                    ''', (json_str, workbench_id))

                    rows_affected = cursor.rowcount
                    logger.info(f"📊 [BOWTIE-PROGRESS-DB] Database update affected {rows_affected} row(s) (PID={pid})")

                    if rows_affected == 0:
                        logger.warning(f"⚠️ [BOWTIE-PROGRESS-DB] No rows updated (PID={pid})")
                        return False

                    conn.commit()
                    logger.info(f"✅ [BOWTIE-PROGRESS-DB] Database transaction committed (PID={pid})")
        else:
            logger.error(f"❌ [BOWTIE-PROGRESS-DB] No shared_db_lock provided (PID={pid})")
            return False

        return True

    except Exception as e:
        logger.error(f"❌ [BOWTIE-PROGRESS-DB] Database update failed (PID={pid}): {e}")
        return False


def _save_bowtie_result_to_db(workbench_id: int, sample_name: str, result_data: Dict[str, Any], shared_db_lock=None) -> bool:
    """개별 샘플의 Bowtie+RSEM 결과를 DB에 저장"""
    logger.info(f"💾 [BOWTIE-RESULT-DB] Starting to save sample result: {sample_name}")

    try:
        if not result_data or not isinstance(result_data, dict):
            logger.warning(f"⚠️ [BOWTIE-RESULT-DB] Invalid result_data for {sample_name}")
            return False

        parsing_successful = result_data.get('parsing_successful', False)
        logger.info(f"📊 [BOWTIE-RESULT-DB] Sample {sample_name} parsing: {'SUCCESS' if parsing_successful else 'FAILED'}")

        if parsing_successful:
            logger.info(f"📈 [BOWTIE-RESULT-DB] {sample_name} results: "
                       f"Total={result_data.get('total_reads', 0):,}, "
                       f"Aligned={result_data.get('aligned_reads', 0):,}, "
                       f"Rate={result_data.get('alignment_rate', 0):.2f}%")

        current_process = mp.current_process()

        if shared_db_lock is not None:
            with shared_db_lock:
                logger.info(f"✅ [BOWTIE-DB-LOCK] PID={current_process.pid} ENTERED critical section")

                # 기존 progress_detail 가져오기
                existing_data = {}
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    result = cursor.execute('''
                        SELECT progress_detail FROM pipeline_job_steps
                        WHERE workbench_id = ? AND (tool_name = 'bowtie' OR tool_name = 'bowtie2')
                    ''', (workbench_id,)).fetchone()

                    if result and result[0]:
                        try:
                            existing_data = json.loads(result[0])
                        except (json.JSONDecodeError, TypeError):
                            existing_data = {"summary": {}, "results": {}}
                    else:
                        existing_data = {"summary": {}, "results": {}}

                # 구조 확인
                if "results" not in existing_data:
                    existing_data["results"] = {}
                if "summary" not in existing_data:
                    existing_data["summary"] = {}

                # results에 샘플 결과 추가
                existing_data["results"][sample_name] = result_data
                logger.info(f"➕ [BOWTIE-RESULT-DB] Added result for {sample_name}")

                # 총 결과 수 확인
                total_results = len(existing_data["results"])
                successful_results = sum(1 for r in existing_data["results"].values() if r.get('parsing_successful', False))

                logger.info(f"📊 [BOWTIE-RESULT-DB] Current summary: {successful_results}/{total_results}")

                # Summary 업데이트
                existing_summary = existing_data.get("summary", {})
                total_files = existing_summary.get("total_files", total_results)

                if total_files > 0:
                    progress_percent = (successful_results / total_files) * 100
                else:
                    progress_percent = 0.0

                existing_data["summary"] = {
                    "completed_files": successful_results,
                    "total_files": total_files,
                    "progress_percent": round(progress_percent, 2),
                    "last_updated": time.time()
                }

                logger.info(f"📈 [BOWTIE-RESULT-DB] Updated summary: {successful_results}/{total_files} ({progress_percent:.1f}%)")

                # JSON 직렬화
                json_str = json.dumps(existing_data)

                # DB 업데이트
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE pipeline_job_steps
                        SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE workbench_id = ? AND (tool_name = 'bowtie' OR tool_name = 'bowtie2')
                    ''', (json_str, workbench_id))

                    rows_affected = cursor.rowcount
                    logger.info(f"📊 [BOWTIE-RESULT-DB] Database update affected {rows_affected} row(s)")

                    if rows_affected == 0:
                        logger.warning(f"⚠️ [BOWTIE-RESULT-DB] No rows updated")
                        return False

                    conn.commit()
                    logger.info(f"✅ [BOWTIE-RESULT-DB] Database transaction committed")

                logger.info(f"🔓 [BOWTIE-DB-LOCK] PID={current_process.pid} LEAVING critical section")
        else:
            logger.error(f"❌ [BOWTIE-DB-LOCK] No shared_db_lock provided!")
            return False

        logger.info(f"🎉 [BOWTIE-RESULT-DB] Successfully saved result for {sample_name}")
        return True

    except Exception as e:
        logger.error(f"❌ [BOWTIE-RESULT-DB] Critical error saving result for {sample_name}: {e}")
        import traceback
        logger.error(f"❌ [BOWTIE-RESULT-DB] Traceback:")
        for line in traceback.format_exc().split('\n'):
            if line.strip():
                logger.error(f"   │ {line}")
        return False


def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 bowtie/bowtie2 tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering bowtie and bowtie2 tools...")

    # Shared metadata for both bowtie and bowtie2
    metadata = {
        'name': 'bowtie',  # Base name
        'description': 'Bowtie/Bowtie2 alignment + RSEM quantification (Trinity)',
        'version': '1.0.0',
        'supported_formats': ['.fastq', '.fastq.gz', '.fq', '.fq.gz'],
        'requirements': ['docker', 'trinity'],
        'parameters': {
            'tool_name': 'bowtie2',  # bowtie or bowtie2
            'threads': 4,
            'est_method': 'RSEM',
            'seqType': 'fq'
        }
    }

    # Register the same function for both 'bowtie' and 'bowtie2'
    # This allows users to select either one, and both use the same implementation
    coordinator.register_tool('bowtie', execute_bowtie, metadata)
    logger.info(f"  ✅ [TOOL-REG] Registered 'bowtie' tool")

    # Register bowtie2 as an alias (same function, different name)
    metadata_bowtie2 = metadata.copy()
    metadata_bowtie2['name'] = 'bowtie2'
    coordinator.register_tool('bowtie2', execute_bowtie, metadata_bowtie2)
    logger.info(f"  ✅ [TOOL-REG] Registered 'bowtie2' tool (same implementation as bowtie)")

    return True  # Both tools registered successfully
