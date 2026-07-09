"""
HISAT2 alignment functionality for VizR pipeline
HISAT2 정렬 관련 함수들
"""

import json
import os
import sqlite3
import logging
from typing import Dict, List, Any
from datetime import datetime
import subprocess
import time
import multiprocessing as mp
from multiprocessing import TimeoutError as MPTimeoutError

from backend.utils import database
from backend.utils.files import ensure_decompressed_files
from backend.blueprints.workbench_utils import get_workbench_schema
from config.backend_settings import BackendConfig as Config
from config.shared_config import SharedConfig
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.process_wrapper import ProcessWrapper
from backend.pipeline.utils.process_runner import ProcessPoolRunner

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def _get_optional_int(parameters: Dict[str, Any], *keys: str):
    for key in keys:
        value = parameters.get(key)
        if value in (None, ''):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            logger.warning(f"⚠️ [HISAT2] Ignoring invalid integer parameter {key}={value}")
    return None


def cleanup_named_pipes(pid, process_logger):
    """
    HISAT2 실행 전 기존 Named Pipe 정리 - mkfifo 충돌 방지
    
    Args:
        pid: 현재 프로세스 PID
        process_logger: 로거 인스턴스
    """
    pipe_patterns = [
        f"/tmp/{pid}.inpipe1",
        f"/tmp/{pid}.inpipe2", 
        f"/tmp/{pid}.outpipe1",
        f"/tmp/{pid}.outpipe2"
    ]
    
    cleaned_count = 0
    for pipe_path in pipe_patterns:
        if os.path.exists(pipe_path):
            try:
                os.unlink(pipe_path)
                cleaned_count += 1
                process_logger.debug(f"🧹 [HISAT2-{pid}] Cleaned existing Named Pipe: {pipe_path}")
            except OSError as e:
                process_logger.warning(f"⚠️ [HISAT2-{pid}] Failed to clean Named Pipe {pipe_path}: {e}")
    
    if cleaned_count > 0:
        process_logger.info(f"🧹 [HISAT2-{pid}] Cleaned {cleaned_count} existing Named Pipes to prevent mkfifo conflicts")


def parse_hisat2_output(stdout: str, sample_name: str) -> Dict[str, Any]:
    """
    HISAT2 stdout에서 결과 정보 파싱

    Expected format:
    "21917767 reads; of these:
      21917767 (100.00%) were unpaired; of these:
        20695547 (94.42%) aligned exactly 1 time
        1067220 (4.87%) aligned >1 times
      94.42% overall alignment rate"

    Args:
        stdout: HISAT2 명령어 실행 결과
        sample_name: 샘플 이름

    Returns:
        Dict: 파싱된 HISAT2 통계 정보
    """
    # 기본 결과 구조
    result = {
        "sample_name": sample_name,
        "total_reads": 0,
        "aligned_exactly_once": 0,
        "aligned_more_than_once": 0,
        "overall_alignment_rate": 0.0,
        "parsing_successful": False
    }

    try:
        # stdout 입력 검증
        if not stdout or not stdout.strip():
            logger.warning(f"⚠️ [HISAT2-PARSER] Empty or null stdout for sample {sample_name}")
            return result

        logger.info(f"📄 [HISAT2-PARSER] Raw stdout length: {len(stdout)} characters")
        logger.info(f"📄 [HISAT2-PARSER] Raw stdout preview (first 200 chars): {repr(stdout[:200])}")

        # stdout를 줄별로 분할하여 검색
        lines = stdout.strip().split('\n')
        logger.info(f"📝 [HISAT2-PARSER] Analyzing {len(lines)} lines of output")

        import re

        # HISAT2 출력 파싱 로직 구현
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # "21911889 reads; of these:" - 전체 리드 수
            total_reads_match = re.search(r'^(\d+)\s+reads;\s+of\s+these:', line)
            if total_reads_match:
                result["total_reads"] = int(total_reads_match.group(1))
                logger.info(f"📊 [HISAT2-PARSER] Found total reads: {result['total_reads']:,}")
                continue

            # "20891623 (95.34%) aligned exactly 1 time" - 정확히 1번 정렬된 리드
            aligned_once_match = re.search(r'(\d+)\s+\([\d.]+%\)\s+aligned\s+exactly\s+1\s+time', line)
            if aligned_once_match:
                result["aligned_exactly_once"] = int(aligned_once_match.group(1))
                logger.info(f"📊 [HISAT2-PARSER] Found aligned exactly once: {result['aligned_exactly_once']:,}")
                continue

            # "454639 (2.07%) aligned >1 times" - 여러번 정렬된 리드
            aligned_multiple_match = re.search(r'(\d+)\s+\([\d.]+%\)\s+aligned\s+>1\s+times', line)
            if aligned_multiple_match:
                result["aligned_more_than_once"] = int(aligned_multiple_match.group(1))
                logger.info(f"📊 [HISAT2-PARSER] Found aligned >1 times: {result['aligned_more_than_once']:,}")
                continue

            # "97.42% overall alignment rate" - 전체 정렬률
            overall_rate_match = re.search(r'([\d.]+)%\s+overall\s+alignment\s+rate', line)
            if overall_rate_match:
                result["overall_alignment_rate"] = float(overall_rate_match.group(1))
                logger.info(f"📊 [HISAT2-PARSER] Found overall alignment rate: {result['overall_alignment_rate']:.2f}%")
                continue

        # 파싱 성공 여부 확인
        if result["total_reads"] > 0:
            result["parsing_successful"] = True
            logger.info(f"✅ [HISAT2-PARSER] Successfully parsed HISAT2 output for {sample_name}")
            logger.info(f"📊 [HISAT2-PARSER] Parsed summary: total={result['total_reads']:,}, "
                      f"aligned_once={result['aligned_exactly_once']:,}, "
                      f"aligned_multiple={result['aligned_more_than_once']:,}, "
                      f"rate={result['overall_alignment_rate']:.2f}%")
        else:
            result["parsing_successful"] = False
            logger.warning(f"⚠️ [HISAT2-PARSER] No valid statistics found in HISAT2 output for {sample_name}")

        if not result["parsing_successful"]:
            logger.error(f"❌ [HISAT2-PARSER] Failed to parse HISAT2 output for {sample_name}")
            logger.info(f"📝 [HISAT2-PARSER] Complete stdout for debugging:")
            for i, line in enumerate(lines[:10], 1):  # 처음 10줄만 상세 로그
                logger.info(f"   Line {i:2d}: {repr(line)}")
            if len(lines) > 10:
                logger.info(f"   ... and {len(lines) - 10} more lines")

    except Exception as e:
        logger.error(f"❌ [HISAT2-PARSER] Error parsing HISAT2 output for {sample_name}: {e}")
        result["parsing_successful"] = False

    return result


# This function is replaced by the more comprehensive version at line 1035


def cleanup_sam_bam_intermediate_files(*file_paths):
    """SAM/BAM 중간 파일들 정리"""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"🗑️ [HISAT2-CLEANUP] Removed intermediate file: {os.path.basename(file_path)}")
            except Exception as e:
                logger.warning(f"⚠️ [HISAT2-CLEANUP] Failed to remove {file_path}: {e}")
        else:
            logger.debug(f"🔍 [HISAT2-CLEANUP] File not found or None: {file_path}")


def execute_hisat2(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, Any]:
    """HISAT2 실행 - job_step에서 직접 정보 추출"""
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

        logger.info(f"🎯 [HISAT2] Starting HISAT2 alignment process")
        logger.info(f"📋 [HISAT2] Job Configuration:")
        logger.info(f"   ├─ workbench_id: {workbench_id}")
        logger.info(f"   ├─ user: {username}")
        logger.info(f"   └─ step_id: {step_id}")

        # 출력 디렉토리 설정
        output_dir = os.path.join(workbench_schema["quanti"]["alignment"])
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"📁 [HISAT2] Created output directory: {output_dir}")

        # Reference 세트 선택 (기본값: TAIR10)
        reference_set = parameters.get('reference_set', 'TAIR10')
        species = parameters.get('species', 'arabidopsis')

        logger.info(f"🧬 [HISAT2] Reference configuration:")
        logger.info(f"   ├─ Species: {species}")
        logger.info(f"   └─ Reference set: {reference_set}")

        # Reference 세트 디렉토리 경로
        reference_dir = f"{SharedConfig.VIZR_PATH}/users/{username}/resource/{species}/reference/{reference_set}"
        metadata_file = os.path.join(reference_dir, "metadata.json")

        # metadata.json 읽기
        if not os.path.exists(metadata_file):
            error_msg = f"Reference metadata not found: {metadata_file}"
            logger.error(f"❌ [HISAT2] {error_msg}")
            raise FileNotFoundError(error_msg)

        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        logger.info(f"📋 [HISAT2] Loaded metadata: {metadata.get('name', 'Unknown')} v{metadata.get('version', 'Unknown')}")

        # Genomic DNA Reference 파일 경로 (HISAT2는 genome alignment)
        genomic_filename = metadata['files']['genomic']
        reference_fasta = os.path.join(reference_dir, genomic_filename)

        logger.info(f"📄 [HISAT2] Reference file: {genomic_filename}")

        # Reference 파일 존재 확인
        if not os.path.exists(reference_fasta):
            error_msg = f"Reference file not found: {reference_fasta}"
            logger.error(f"❌ [HISAT2] {error_msg}")
            raise FileNotFoundError(error_msg)

        # HISAT2 index 경로 (indexes/hisat2/ 디렉토리 사용)
        index_dir = os.path.join(reference_dir, metadata['indexes']['hisat2'])
        os.makedirs(index_dir, exist_ok=True)

        # Index 파일 베이스네임 (genome_index)
        reference_index = os.path.join(index_dir, "genome_index")

        logger.info(f"📂 [HISAT2] Index directory: {index_dir}")
        logger.info(f"🔍 [HISAT2] Index basename: genome_index")
        
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
                logger.info(f"📊 [HISAT2] Retrieved samples from vizr_pipeline_samples (layout: {layout})")
                
                try:
                    samples_data = json.loads(samples_json)
                    logger.info(f"✅ [HISAT2] {len(samples_data)} samples")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ [HISAT2] Failed to parse samples JSON: {e}")
                    raise
            else:
                logger.warning(f"⚠️  [HISAT2] No samples found for workbench_id: {workbench_id}")
                layout = 'pe'  # 기본값

        logger.info(f"🔍 [HISAT2-DEBUG] Layout 정보: {layout}")
        
        # 이전 단계 확인 (clean_tools에서 어떤 clean tool들이 실행되었는지 확인)
        clean_tools = parameters.get('clean_tools', [])
        
        # 입력 파일 경로 결정
        if 'prinseq' in clean_tools:
            # Case 3: download -> trimmomatic -> prinseq -> hisat2
            input_dir = os.path.join(workbench_schema["quanti"]["clean"], "prinseq")
            logger.info(f"📂 [HISAT2] Input from PRINSEQ: {input_dir}")
        elif 'trimmomatic' in clean_tools:
            # Case 2: download -> trimmomatic -> hisat2
            input_dir = os.path.join(workbench_schema["quanti"]["clean"], "trim")
            logger.info(f"📂 [HISAT2] Input from Trimmomatic: {input_dir}")
        else:
            # Case 1: download -> hisat2
            input_dir = workbench_schema["quanti"]["raw"]
            logger.info(f"📂 [HISAT2] Input from raw files: {input_dir}")

        logger.info(f"⚙️ [HISAT2] Configuration analysis:")
        logger.info(f"   ├─ Clean tools: {clean_tools}")
        logger.info(f"   ├─ Input directory: {input_dir}")
        logger.info(f"   └─ Layout: {layout}")
        
        # 각 샘플에 대한 파일 경로 구성
        for sample_info in samples_data:
            sample_name = sample_info['sampleName']
            group_name = sample_info['groupName']
            
            files = {}
            
            if 'prinseq' in clean_tools:
                # PRINSEQ 후: good 디렉토리에서 파일 찾기 (PRINSEQ outputs uncompressed .fastq)
                sample_input_dir = os.path.join(input_dir, group_name, sample_name, "good")
                if layout == 'pe':
                    files['R1'] = os.path.join(sample_input_dir, f"{sample_name}_good_1.fastq")
                    files['R2'] = os.path.join(sample_input_dir, f"{sample_name}_good_2.fastq")
                else:
                    files['SE'] = os.path.join(sample_input_dir, f"{sample_name}_good.fastq")
                    
            elif 'trimmomatic' in clean_tools:
                # Trimmomatic 후: 파일 찾기 (Trimmomatic outputs uncompressed .fastq)
                sample_input_dir = os.path.join(input_dir, group_name, sample_name)
                if layout == 'pe':
                    files['R1'] = os.path.join(sample_input_dir, f"{sample_name}_1_paired.fastq")
                    files['R2'] = os.path.join(sample_input_dir, f"{sample_name}_2_paired.fastq")
                else:
                    files['SE'] = os.path.join(sample_input_dir, f"{sample_name}_trimmed.fastq")
                    
            else:
                # Raw 파일 직접 사용
                if 'file1' in sample_info and sample_info['file1']:
                    # Remove .gz extension if present (files are decompressed by download step)
                    file1_name = sample_info['file1']
                    if file1_name.endswith('.gz'):
                        file1_name = file1_name[:-3]

                    file1_path = os.path.join(input_dir, file1_name)
                    if layout == 'pe':
                        files['R1'] = file1_path
                    else:
                        files['SE'] = file1_path

                if 'file2' in sample_info and sample_info['file2']:
                    # Remove .gz extension if present (files are decompressed by download step)
                    file2_name = sample_info['file2']
                    if file2_name.endswith('.gz'):
                        file2_name = file2_name[:-3]

                    file2_path = os.path.join(input_dir, file2_name)
                    files['R2'] = file2_path

            # 출력 파일 경로 설정
            sample_output_dir = os.path.join(output_dir, group_name, sample_name)
            os.makedirs(sample_output_dir, exist_ok=True)
            
            sam_file = os.path.join(sample_output_dir, f"{sample_name}.sam")
            bam_file = os.path.join(sample_output_dir, f"{sample_name}.bam")
            sorted_bam_file = os.path.join(sample_output_dir, f"{sample_name}_sorted.bam")

            sample_info_dict = {
                'sample_name': sample_name,
                'condition': group_name,
                'files': files,
                'output_dir': sample_output_dir,
                'sam_file': sam_file,
                'bam_file': bam_file,
                'sorted_bam_file': sorted_bam_file,
                'reference_index': reference_index,
                'reference_fasta': reference_fasta,  # Index 빌드용
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
            logger.info(f"   │   └─ Output SAM: {os.path.basename(sam_file)}")

        # 멀티프로세싱으로 HISAT2 실행
        logger.info(f"🚀 [HISAT2] Starting multi-processing alignment for {len(sample_info_list)} samples")
        results = execute_hisat2_multi(sample_info_list, parameters, worker_id, workbench_id)
        
        return results
        
    except Exception as e:
        logger.error(f"💥 [HISAT2] Exception in _execute_hisat2: {str(e)}")
        return {
            'success': False,
            'stdout': '',
            'stderr': f"HISAT2 execution exception: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }

def execute_hisat2_multi(sample_info_list: List[Dict], parameters: Dict, worker_id: str = "hisat2_multi", workbench_id: int = None) -> Dict[str, Any]:

    # 0개 샘플 방지
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
    logger.info(f"🚀 [HISAT2-MULTI-POOL] Starting Pool-based HISAT2 alignment")
    logger.info(f"📊 [HISAT2-MULTI-POOL] Configuration:")
    logger.info(f"   ├─ Total samples: {len(sample_info_list)}")
    logger.info(f"   └─ Processing mode: multiprocessing.Pool")
    
    # ✅ SharedState에서 해당 워커의 Event 가져오기
    try:
        worker_stop_event = shared_state.get_worker_event(worker_id)
        logger.info(f"📡 [HISAT2-MULTI-POOL] Using SharedState Event for worker: {worker_id}")
    except ValueError as e:
        logger.error(f"❌ [HISAT2-MULTI-POOL] Worker not registered: {e}")
        return {
            'success': False,
            'stdout': '',
            'stderr': f'Worker {worker_id} not registered in SharedState',
            'processed_samples': [],
            'output_files': [],
            'timestamp': datetime.now().isoformat(),
            'execution_time': time.time() - start_time
        }
    
    # 프로세스 간 공유 Lock 생성 (Manager를 통한 진정한 프로세스 간 공유)
    import multiprocessing as mp
    manager = mp.Manager()
    shared_db_lock = manager.Lock()
    logger.info(f"🔒 [HISAT2-MULTI] Created shared DB lock for multiprocessing (lock_id={id(shared_db_lock)})")

    # 작업 인수 준비 - ProcessPoolRunner가 stop_event를 자동 주입하므로 제외
    work_args = []
    for i, sample_info in enumerate(sample_info_list):
        worker_id_sample = f"hisat2_sample_{i}_{sample_info['sample_name']}"
        # stop_event는 ProcessPoolRunner가 자동으로 주입하므로 제외
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
        send_hisat2_progress_update(workbench_id, initial_progress)
        # 초기화 시점에는 shared_db_lock이 아직 생성되지 않음
        _save_hisat2_progress_to_db(workbench_id, completed_samples, total_samples, shared_db_lock)

    with ProcessPoolRunner(max_workers=4, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
        try:
            logger.info(f"🔄 [HISAT2-MULTI-POOL] Processing {len(work_args)} samples...")
            
            for i, result in enumerate(runner.map_unordered(run_single_hisat2, work_args)):
                # ✅ 단일 체크 - 워커가 실제로 중단되었는지만 확인
                if result.get('stopped_by_user', False):
                    logger.warning(f"⏹️ [HISAT2-MULTI-POOL] Sample processing stopped by user")
                    runner.stop()  # 남은 작업들 중단
                    # Reset worker event for next execution
                    shared_state.reset_worker(worker_id)
                    break
                
                # 결과 수집
                sample_results.append(result)

                if result['success']:
                    output_files.extend(result.get('output_files', []))
                    logger.info(f"✅ [HISAT2-MULTI-POOL] Completed sample {i+1}/{len(work_args)}: {result['sample_name']}")
                else:
                    failed_samples.append(result['sample_name'])
                    logger.error(f"❌ [HISAT2-MULTI-POOL] Failed sample {i+1}/{len(work_args)}: {result['sample_name']}")

                # 진행률 업데이트 (샘플 완료시마다)
                if workbench_id:
                    completed_samples = i + 1
                    progress_percent = (completed_samples / total_samples * 100) if total_samples > 0 else 0.0

                    progress_data = {
                        "completed_samples": completed_samples,
                        "total_samples": total_samples,
                        "progress_percent": progress_percent,
                        "current_sample": result.get('sample_name', 'unknown')
                    }

                    # 실시간 진행률 전송
                    send_hisat2_progress_update(workbench_id, progress_data)

                    # DB에 진행률 저장 (샘플 완료시마다 저장)
                    _save_hisat2_progress_to_db(workbench_id, completed_samples, total_samples, shared_db_lock)

                    logger.info(f"📊 [HISAT2-MULTI] Progress: {completed_samples}/{total_samples} ({progress_percent:.1f}%)")
                    
        except Exception as e:
            logger.error(f"💥 [HISAT2-MULTI-POOL] Exception during processing: {e}")
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
    
    logger.info(f"🎯 [HISAT2] Multi-sample alignment completed")
    logger.info(f"   ├─ Total samples: {len(sample_info_list)}")
    logger.info(f"   ├─ Successful: {success_count}")
    logger.info(f"   ├─ Failed: {len(failed_samples)}")
    logger.info(f"   ├─ Output files: {len(output_files)}")
    logger.info(f"   └─ Execution time: {execution_time:.1f}s")
    
    return {
        'success': len(failed_samples) == 0,
        'stdout': '\n'.join([r.get('stdout', '') for r in sample_results]),
        'stderr': '\n'.join([r.get('stderr', '') for r in sample_results if r.get('stderr')]),
        'processed_samples': [r['sample_name'] for r in sample_results if r['success']],
        'failed_samples': failed_samples,
        'output_files': output_files,
        'sample_results': sample_results,  # 상세 결과
        'timestamp': datetime.now().isoformat(),
        'execution_time': execution_time
    }

def run_single_hisat2(sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "hisat2_worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """Process individual HISAT2 sample (PE/SE auto-detection)"""
    
    if stop_event and stop_event.is_set():
        return { 'success': False, 'stopped_by_user': True }
    
    # ProcessWrapper 생성
    wrapper = ProcessWrapper(worker_id)
    
    # Unified logging system
    from backend.utils.logger import setup_module_logger
    process_logger = setup_module_logger(__name__, 'INFO')
    start_time = time.time()
    
    # Log input parameters at function start
    process_logger.info(f"🎯 [HISAT2-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
    process_logger.info(f"🎯 [HISAT2-{os.getpid()}] ║                HISAT2 Function Started - Input Debug            ║")
    process_logger.info(f"🎯 [HISAT2-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
    process_logger.info(f"")
    process_logger.info(f"📋 [HISAT2-{os.getpid()}] INPUT PARAMETERS DEBUG:")
    
    process_logger.info(f"🔍 [HISAT2-{os.getpid()}] sample_info contents:")
    for key, value in sample_info.items():
        if isinstance(value, dict):
            process_logger.info(f"   ├─ {key}: {{")
            for sub_key, sub_value in value.items():
                process_logger.info(f"   │     {sub_key}: {sub_value}")
            process_logger.info(f"   │   }}")
        else:
            process_logger.info(f"   ├─ {key}: {value}")
    
    process_logger.info(f"🔍 [HISAT2-{os.getpid()}] parameters contents:")
    for key, value in parameters.items():
        process_logger.info(f"   ├─ {key}: {value}")
    
    try:
        sample_name = sample_info['sample_name']
        condition = sample_info['condition']
        files = sample_info['files']
        output_dir = sample_info['output_dir']
        sam_file = sample_info['sam_file']
        bam_file = sample_info['bam_file']
        sorted_bam_file = sample_info['sorted_bam_file']
        reference_index = sample_info['reference_index']
        layout = sample_info['layout']
        
        process_logger.info(f"🔧 [HISAT2-{os.getpid()}] Sample configuration:")
        process_logger.info(f"   ├─ Sample: {sample_name}")
        process_logger.info(f"   ├─ Condition: {condition}")
        process_logger.info(f"   ├─ Layout: {layout}")
        process_logger.info(f"   ├─ Reference: {os.path.basename(reference_index)}")
        process_logger.info(f"   └─ Output SAM: {os.path.basename(sam_file)}")

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
        process_logger.info(f"📁 [HISAT2-{os.getpid()}] Input file validation:")
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

        # HISAT2 Index 확인 및 자동 생성
        reference_fasta = sample_info.get('reference_fasta')
        index_check_file = f"{reference_index}.1.ht2"

        if not os.path.exists(index_check_file):
            process_logger.warning(f"⚠️ [HISAT2-{os.getpid()}] Index not found: {index_check_file}")
            process_logger.info(f"🔨 [HISAT2-{os.getpid()}] Building HISAT2 index...")
            process_logger.info(f"   ├─ Reference FASTA: {reference_fasta}")
            process_logger.info(f"   └─ Index basename: {reference_index}")

            if not reference_fasta or not os.path.exists(reference_fasta):
                error_msg = f"Reference FASTA not found for index building: {reference_fasta}"
                process_logger.error(f"❌ [HISAT2-{os.getpid()}] {error_msg}")
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

            # HISAT2 index build command
            build_cmd = ['hisat2-build', reference_fasta, reference_index]
            process_logger.info(f"🚀 [HISAT2-{os.getpid()}] Running hisat2-build...")

            build_result = wrapper.run_command(build_cmd, cwd=os.path.dirname(reference_index), stop_event=stop_event)

            if build_result['stopped_by_user']:
                process_logger.info(f"⏹️ [HISAT2-{os.getpid()}] Index building stopped by user")
                return {
                    'success': False,
                    'sample_name': sample_name,
                    'condition': condition,
                    'returncode': -1,
                    'stdout': '',
                    'stderr': 'Index building stopped by user',
                    'output_files': [],
                    'execution_time': time.time() - start_time,
                    'error_message': 'Index building stopped by user',
                    'pid': os.getpid(),
                    'stopped_by_user': True
                }

            if build_result['returncode'] != 0:
                error_msg = f"HISAT2 index build failed with return code {build_result['returncode']}"
                process_logger.error(f"❌ [HISAT2-{os.getpid()}] {error_msg}")
                process_logger.error(f"   └─ STDERR: {build_result['stderr'][:500]}...")
                return {
                    'success': False,
                    'sample_name': sample_name,
                    'condition': condition,
                    'returncode': build_result['returncode'],
                    'stdout': build_result['stdout'],
                    'stderr': build_result['stderr'],
                    'output_files': [],
                    'execution_time': time.time() - start_time,
                    'error_message': error_msg,
                    'pid': os.getpid()
                }

            process_logger.info(f"✅ [HISAT2-{os.getpid()}] Index built successfully!")
        else:
            process_logger.info(f"✅ [HISAT2-{os.getpid()}] Using existing index: {os.path.basename(reference_index)}")

        # HISAT2 command generation
        threads = parameters.get('threads', 4)
        hisat2_cmd = ['hisat2', '-p', str(threads), '-x', reference_index]
        max_intronlen = _get_optional_int(parameters, 'max_intronlen', 'hisat2_max_intronlen')
        if max_intronlen is not None:
            hisat2_cmd.extend(['--max-intronlen', str(max_intronlen)])
            process_logger.info(f"⚙️  [HISAT2-{os.getpid()}] max intron length: {max_intronlen}")
        
        # Detect file format and add appropriate option
        input_file_sample = None
        if layout == 'pe' and 'R1' in files and 'R2' in files:
            input_file_sample = files['R1']
        elif layout == 'se' and 'SE' in files:
            input_file_sample = files['SE']
        
        if input_file_sample and (input_file_sample.endswith('.fasta') or input_file_sample.endswith('.fa') or 
                                    input_file_sample.endswith('.fasta.gz') or input_file_sample.endswith('.fa.gz')):
            hisat2_cmd.append('-f')  # FASTA input format
            process_logger.info(f"📄 [HISAT2-{os.getpid()}] FASTA format detected, added -f option")
        else:
            process_logger.info(f"📄 [HISAT2-{os.getpid()}] FASTQ format assumed (default)")
        
        # Add input files based on layout
        if layout == 'pe' and 'R1' in files and 'R2' in files:
            hisat2_cmd.extend(['-1', files['R1'], '-2', files['R2']])
            process_logger.info(f"🔧 [HISAT2-{os.getpid()}] PE mode: R1={os.path.basename(files['R1'])}, R2={os.path.basename(files['R2'])}")
        elif layout == 'se' and 'SE' in files:
            hisat2_cmd.extend(['-U', files['SE']])
            process_logger.info(f"🔧 [HISAT2-{os.getpid()}] SE mode: SE={os.path.basename(files['SE'])}")
        else:
            error_msg = f"Invalid file configuration for layout {layout}: {files}"
            process_logger.error(f"❌ [HISAT2-{os.getpid()}] {error_msg}")
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
        
        # Add output SAM file
        hisat2_cmd.extend(['-S', sam_file])
        hisat2_cmd.append('--dta')
        
        # HISAT2 임시 디렉토리 설정 시도 (--temp-directory는 지원하지 않을 수 있음)
        # hisat2_cmd.extend(['--temp-directory', output_dir])  # 이 옵션이 동작하지 않음
        
        # mkfifo Named Pipe 충돌 방지 - HISAT2 실행 전 기존 Named Pipe 정리
        current_pid = os.getpid()
        # cleanup_named_pipes(current_pid, process_logger)
        
        process_logger.info(f"🚀 [HISAT2-{os.getpid()}] Running HISAT2 alignment...")
        process_logger.info(f"   └─ Command: {' '.join(hisat2_cmd)}")
        
        # Execute HISAT2
        result = wrapper.run_command(hisat2_cmd, cwd=output_dir, stop_event=stop_event)
        
        # Stop 신호 체크
        if result['stopped_by_user']:
            process_logger.info(f"⏹️ [HISAT2-{os.getpid()}] HISAT2 alignment stopped by user")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': '',
                'stderr': 'HISAT2 alignment stopped by user',
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': 'HISAT2 alignment stopped by user',
                'pid': os.getpid(),
                'stopped_by_user': True
            }
        
        hisat2_result = result
        
        process_logger.info(f"⏱️  [HISAT2-{os.getpid()}] HISAT2 completed with return code: {hisat2_result['returncode']}")
        
        if hisat2_result['returncode'] != 0:
            process_logger.error(f"❌ [HISAT2-{os.getpid()}] HISAT2 failed!")
            process_logger.error(f"   ├─ Return code: {hisat2_result['returncode']}")
            process_logger.error(f"   ├─ STDERR: {hisat2_result['stderr'][:500]}...")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': hisat2_result['returncode'],
                'stdout': hisat2_result['stdout'],
                'stderr': hisat2_result['stderr'],
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': f"HISAT2 failed with return code {hisat2_result['returncode']}",
                'pid': os.getpid()
            }
        
        # HISAT2 성공 - stdout 또는 stderr에서 통계 정보 파싱 및 DB 저장
        process_logger.info(f"📊 [HISAT2-{os.getpid()}] Parsing HISAT2 alignment statistics...")

        hisat2_parsed_result = None
        output_to_parse = None
        output_source = "none"

        # stdout 우선 확인
        if hisat2_result.get('stdout'):
            output_to_parse = hisat2_result['stdout']
            output_source = "stdout"
            process_logger.info(f"📄 [HISAT2-{os.getpid()}] Found output in stdout ({len(hisat2_result['stdout'])} chars)")
        # stdout이 비어있으면 stderr 확인
        elif hisat2_result.get('stderr'):
            output_to_parse = hisat2_result['stderr']
            output_source = "stderr"
            process_logger.info(f"📄 [HISAT2-{os.getpid()}] Found output in stderr ({len(hisat2_result['stderr'])} chars)")
        else:
            process_logger.warning(f"⚠️ [HISAT2-{os.getpid()}] Sample {sample_name} succeeded but has empty stdout and stderr")

        if output_to_parse:
            process_logger.info(f"🔍 [HISAT2-{os.getpid()}] Parsing HISAT2 output from {output_source}...")
            # HISAT2 출력 파싱
            hisat2_parsed_result = parse_hisat2_output(output_to_parse, sample_name)

            if hisat2_parsed_result and hisat2_parsed_result.get('parsing_successful', False):
                process_logger.info(f"✅ [HISAT2-{os.getpid()}] Successfully parsed HISAT2 statistics from {output_source}")
                process_logger.info(f"📊 [HISAT2-{os.getpid()}] Alignment summary: "
                                  f"total={hisat2_parsed_result.get('total_reads', 0):,}, "
                                  f"aligned_once={hisat2_parsed_result.get('aligned_exactly_once', 0):,}, "
                                  f"aligned_multiple={hisat2_parsed_result.get('aligned_more_than_once', 0):,}, "
                                  f"rate={hisat2_parsed_result.get('overall_alignment_rate', 0):.2f}%")

                # DB에 결과 저장
                if workbench_id:
                    _save_hisat2_result_to_db(workbench_id, sample_name, hisat2_parsed_result, shared_db_lock)
            else:
                process_logger.warning(f"⚠️ [HISAT2-{os.getpid()}] Failed to parse HISAT2 statistics from {output_source}")
        else:
            process_logger.warning(f"⚠️ [HISAT2-{os.getpid()}] No output available for HISAT2 statistics parsing")

        # Convert SAM to BAM
        process_logger.info(f"🔄 [HISAT2-{os.getpid()}] Converting SAM to BAM...")
        samtools_view_cmd = ['samtools', 'view', '-bS', sam_file, '-o', bam_file]
        
        result = wrapper.run_command(samtools_view_cmd, cwd=output_dir, stop_event=stop_event)
        
        # Stop 신호 체크
        if result['stopped_by_user']:
            process_logger.info(f"⏹️ [HISAT2-{os.getpid()}] SAM to BAM conversion stopped by user")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': hisat2_result['stdout'],
                'stderr': hisat2_result['stderr'] + '\nSAM to BAM conversion stopped by user',
                'output_files': [sam_file] if os.path.exists(sam_file) else [],
                'execution_time': time.time() - start_time,
                'error_message': 'SAM to BAM conversion stopped by user',
                'pid': os.getpid(),
                'stopped_by_user': True
            }
        
        # 결과를 딕셔너리 형식으로 변환
        samtools_result = {
            'returncode': result['return_code'],
            'stdout': result['stdout'], 
            'stderr': result['stderr']
        }
        
        if samtools_result['returncode'] != 0:
            process_logger.error(f"❌ [HISAT2-{os.getpid()}] SAM to BAM conversion failed!")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': samtools_result['returncode'],
                'stdout': hisat2_result['stdout'] + samtools_result['stdout'],
                'stderr': hisat2_result['stderr'] + samtools_result['stderr'],
                'output_files': [sam_file] if os.path.exists(sam_file) else [],
                'execution_time': time.time() - start_time,
                'error_message': f"SAM to BAM conversion failed",
                'pid': os.getpid()
            }
        
        # Sort BAM file
        process_logger.info(f"📊 [HISAT2-{os.getpid()}] Sorting BAM file...")
        samtools_sort_cmd = ['samtools', 'sort', bam_file, '-o', sorted_bam_file]
        
        result = wrapper.run_command(samtools_sort_cmd, cwd=output_dir, stop_event=stop_event)
        
        # Stop 신호 체크
        if result['stopped_by_user']:
            process_logger.info(f"⏹️ [HISAT2-{os.getpid()}] BAM sorting stopped by user")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': hisat2_result['stdout'] + samtools_result['stdout'],
                'stderr': hisat2_result['stderr'] + samtools_result['stderr'] + '\nBAM sorting stopped by user',
                'output_files': [sam_file, bam_file] if os.path.exists(bam_file) else [sam_file] if os.path.exists(sam_file) else [],
                'execution_time': time.time() - start_time,
                'error_message': 'BAM sorting stopped by user',
                'pid': os.getpid(),
                'stopped_by_user': True
            }
        
        # 결과를 딕셔너리 형식으로 변환
        sort_result = {
            'returncode': result['return_code'],
            'stdout': result['stdout'], 
            'stderr': result['stderr']
        }
        
        if sort_result['returncode'] != 0:
            process_logger.error(f"❌ [HISAT2-{os.getpid()}] BAM sorting failed!")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': sort_result['returncode'],
                'stdout': hisat2_result['stdout'] + samtools_result['stdout'] + sort_result['stdout'],
                'stderr': hisat2_result['stderr'] + samtools_result['stderr'] + sort_result['stderr'],
                'output_files': [sam_file, bam_file] if os.path.exists(bam_file) else [sam_file] if os.path.exists(sam_file) else [],
                'execution_time': time.time() - start_time,
                'error_message': f"BAM sorting failed",
                'pid': os.getpid()
            }
        
        # Index sorted BAM file
        process_logger.info(f"📇 [HISAT2-{os.getpid()}] Indexing sorted BAM file...")
        samtools_index_cmd = ['samtools', 'index', sorted_bam_file]
        
        result = wrapper.run_command(samtools_index_cmd, cwd=output_dir, stop_event=stop_event)
        
        # Stop 신호 체크
        if result['stopped_by_user']:
            process_logger.info(f"⏹️ [HISAT2-{os.getpid()}] BAM indexing stopped by user")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': hisat2_result['stdout'] + samtools_result['stdout'] + sort_result['stdout'],
                'stderr': hisat2_result['stderr'] + samtools_result['stderr'] + sort_result['stderr'] + '\nBAM indexing stopped by user',
                'output_files': [sorted_bam_file] if os.path.exists(sorted_bam_file) else [],
                'execution_time': time.time() - start_time,
                'error_message': 'BAM indexing stopped by user',
                'pid': os.getpid(),
                'stopped_by_user': True
            }
        
        # 결과를 딕셔너리 형식으로 변환
        index_result = {
            'returncode': result['return_code'],
            'stdout': result['stdout'], 
            'stderr': result['stderr']
        }
        
        if index_result['returncode'] != 0:
            process_logger.warning(f"⚠️  [HISAT2-{os.getpid()}] BAM indexing failed (not critical)")
        
        # Clean up intermediate files
        if os.path.exists(sam_file):
            os.remove(sam_file)
            process_logger.info(f"🧹 [HISAT2-{os.getpid()}] Removed intermediate SAM file")
        
        if os.path.exists(bam_file) and os.path.exists(sorted_bam_file):
            os.remove(bam_file)
            process_logger.info(f"🧹 [HISAT2-{os.getpid()}] Removed unsorted BAM file")
        
        # Final output files
        output_files = []
        if os.path.exists(sorted_bam_file):
            output_files.append(sorted_bam_file)
            file_size = os.path.getsize(sorted_bam_file)
            process_logger.info(f"✅ [HISAT2-{os.getpid()}] Generated sorted BAM: {os.path.basename(sorted_bam_file)} ({file_size:,} bytes)")
            
        bai_file = sorted_bam_file + '.bai'
        if os.path.exists(bai_file):
            output_files.append(bai_file)
            process_logger.info(f"✅ [HISAT2-{os.getpid()}] Generated BAM index: {os.path.basename(bai_file)}")
        
        execution_time = time.time() - start_time
        process_logger.info(f"🎉 [HISAT2-{os.getpid()}] Sample completed successfully!")
        process_logger.info(f"   ├─ Execution time: {execution_time:.1f}s")
        process_logger.info(f"   └─ Output files: {len(output_files)}")
        
        # 최종 반환 데이터 구성
        final_result = {
            'success': True,
            'sample_name': sample_name,
            'condition': condition,
            'returncode': 0,
            'stdout': hisat2_result['stdout'] + samtools_result['stdout'] + sort_result['stdout'],
            'stderr': hisat2_result['stderr'] + samtools_result['stderr'] + sort_result['stderr'],
            'output_files': output_files,
            'execution_time': execution_time,
            'pid': os.getpid()
        }

        # 파싱된 HISAT2 통계 정보 추가
        if hisat2_parsed_result and hisat2_parsed_result.get('parsing_successful', False):
            final_result.update({
                'total_reads': hisat2_parsed_result.get('total_reads', 0),
                'aligned_exactly_once': hisat2_parsed_result.get('aligned_exactly_once', 0),
                'aligned_more_than_once': hisat2_parsed_result.get('aligned_more_than_once', 0),
                'overall_alignment_rate': hisat2_parsed_result.get('overall_alignment_rate', 0.0),
                'parsing_successful': True
            })
        else:
            final_result.update({
                'total_reads': 0,
                'aligned_exactly_once': 0,
                'aligned_more_than_once': 0,
                'overall_alignment_rate': 0.0,
                'parsing_successful': False
            })

        return final_result
        
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"Exception in run_single_hisat2: {str(e)}"
        process_logger.error(f"💥 [HISAT2-{os.getpid()}] {error_msg}")
        
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


def send_hisat2_progress_update(workbench_id: int, progress_data: dict) -> bool:
    """
    HISAT2 진행률 직접 전송

    Args:
        workbench_id: 워크벤치 ID
        progress_data: 진행률 데이터 (completed_samples, total_samples, progress_percent, current_sample)

    Returns:
        전송 성공 여부
    """
    try:
        from backend.pipeline.utils.redis_broker import get_redis_broker
        redis_broker = get_redis_broker()

        if not redis_broker.is_available():
            logger.debug(f"📡 [HISAT2-PROGRESS] Redis not available, skipping progress update")
            return False

        success = redis_broker.publish_progress(
            workbench_id=workbench_id,
            task_type='hisat2',
            progress_data=progress_data
        )

        if success:
            logger.debug(f"📡 [HISAT2-PROGRESS] Successfully sent progress update: {progress_data}")
        else:
            logger.warning(f"📡 [HISAT2-PROGRESS] Failed to send progress update")

        return success

    except Exception as e:
        logger.error(f"❌ [HISAT2-PROGRESS] Error sending progress update: {e}")
        return False


def _save_hisat2_progress_to_db(workbench_id: int, completed_samples: int, total_samples: int, shared_db_lock=None) -> bool:
    """
    HISAT2 진행률 정보를 DB에 저장

    Args:
        workbench_id: 워크벤치 ID
        completed_samples: 완료된 샘플 수
        total_samples: 전체 샘플 수
        shared_db_lock: 멀티프로세스 간 공유 DB 락 (선택적)

    Returns:
        저장 성공 여부
    """
    import multiprocessing as mp
    current_process = mp.current_process()
    pid = current_process.pid

    logger.info(f"📊 [HISAT2-PROGRESS-DB] Updating progress (PID={pid}): {completed_samples}/{total_samples}")

    try:
        # 진행률 계산
        if total_samples > 0:
            progress_percent = (completed_samples / total_samples) * 100
        else:
            progress_percent = 0.0

        # 현재 시간 설정
        import time
        current_time = time.time()

        # Lock 사용 여부 확인 및 처리
        if shared_db_lock is not None:
            logger.info(f"🔒 [HISAT2-PROGRESS-DB] Using shared_db_lock for DB operations (PID={pid})")
            with shared_db_lock:
                # 기존 progress_detail 가져오기
                existing_data = {}
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    result = cursor.execute('''
                        SELECT progress_detail FROM pipeline_job_steps
                        WHERE workbench_id = ? AND tool_name = 'hisat2'
                    ''', (workbench_id,)).fetchone()

                    if result and result[0]:
                        try:
                            existing_data = json.loads(result[0])
                            logger.debug(f"📄 [HISAT2-PROGRESS-DB] Loaded existing progress_detail (PID={pid})")
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.warning(f"⚠️ [HISAT2-PROGRESS-DB] Failed to parse existing progress_detail, initializing new (PID={pid}): {e}")
                            existing_data = {"summary": {}, "results": {}}
                    else:
                        logger.info(f"ℹ️ [HISAT2-PROGRESS-DB] No existing progress_detail found, initializing new structure (PID={pid})")
                        existing_data = {"summary": {}, "results": {}}

                # 기존 구조 확인 및 보정
                if "results" not in existing_data:
                    existing_data["results"] = {}
                if "summary" not in existing_data:
                    existing_data["summary"] = {}

                # Summary 정보 업데이트
                existing_data["summary"] = {
                    "completed_files": completed_samples,
                    "total_files": total_samples,
                    "progress_percent": round(progress_percent, 2),
                    "last_updated": current_time
                }

                logger.info(f"📈 [HISAT2-PROGRESS-DB] Updated summary (PID={pid}): {completed_samples}/{total_samples} ({progress_percent:.1f}%)")

                # JSON 직렬화
                json_str = json.dumps(existing_data)
                logger.info(f"📄 [HISAT2-PROGRESS-DB] JSON content being saved (PID={pid}): {json_str}")

                # DB 업데이트 (같은 lock 블록 내에서 처리)
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE pipeline_job_steps
                        SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE workbench_id = ? AND tool_name = 'hisat2'
                    ''', (json_str, workbench_id))

                    rows_affected = cursor.rowcount
                    logger.info(f"📊 [HISAT2-PROGRESS-DB] Database update affected {rows_affected} row(s) (PID={pid})")

                    if rows_affected == 0:
                        logger.warning(f"⚠️ [HISAT2-PROGRESS-DB] No rows were updated - pipeline step may not exist for workbench {workbench_id} (PID={pid})")
                        return False

                    conn.commit()
                    logger.info(f"✅ [HISAT2-PROGRESS-DB] Database transaction committed successfully (PID={pid})")
        else:
            logger.error(f"❌ [HISAT2-PROGRESS-DB] No shared_db_lock provided - this should not happen in multiprocessing! (PID={pid})")
            return False

        return True

    except Exception as e:
        logger.error(f"❌ [HISAT2-PROGRESS-DB] Database update failed (PID={pid}): {e}")
        return False


def _save_hisat2_result_to_db(workbench_id: int, sample_name: str, result_data: Dict[str, Any], shared_db_lock=None) -> bool:
    """
    개별 샘플의 HISAT2 결과를 DB에 저장

    Args:
        workbench_id: 워크벤치 ID
        sample_name: 샘플 이름
        result_data: 파싱된 결과 데이터
        shared_db_lock: 멀티프로세스 간 공유 DB 락 (선택적)

    Returns:
        저장 성공 여부
    """
    logger.info(f"💾 [HISAT2-RESULT-DB] Starting to save sample result: {sample_name} for workbench {workbench_id}")

    try:
        # 입력 데이터 검증
        if not result_data or not isinstance(result_data, dict):
            logger.warning(f"⚠️ [HISAT2-RESULT-DB] Invalid result_data for sample {sample_name}: {result_data}")
            return False

        # 파싱 성공 여부 확인
        parsing_successful = result_data.get('parsing_successful', False)
        logger.info(f"📊 [HISAT2-RESULT-DB] Sample {sample_name} parsing status: {'SUCCESS' if parsing_successful else 'FAILED'}")

        if parsing_successful:
            logger.info(f"📈 [HISAT2-RESULT-DB] Sample {sample_name} results: "
                       f"Total={result_data.get('total_reads', 0):,}, "
                       f"Aligned_once={result_data.get('aligned_exactly_once', 0):,}, "
                       f"Aligned_multiple={result_data.get('aligned_more_than_once', 0):,}, "
                       f"Rate={result_data.get('overall_alignment_rate', 0):.2f}%")

        # 프로세스 정보 수집
        import multiprocessing as mp
        current_process = mp.current_process()
        process_info = f"PID={current_process.pid}, Name={current_process.name}"

        # Lock 진입 시도 로그
        logger.info(f"🔒 [HISAT2-DB-LOCK-ENTER] PID={current_process.pid} ATTEMPTING lock acquisition - {process_info}, Sample: {sample_name}, Workbench: {workbench_id}")

        # 전달받은 shared_db_lock 사용
        logger.info(f"🔍 [HISAT2-DB-LOCK-DEBUG] Using passed shared_db_lock: {shared_db_lock}")
        logger.info(f"🔍 [HISAT2-DB-LOCK-DEBUG] shared_db_lock type: {type(shared_db_lock)}")

        if shared_db_lock is not None:
            # 전달받은 Lock 사용
            with shared_db_lock:
                logger.info(f"✅ [HISAT2-DB-LOCK-ACQUIRED] PID={current_process.pid} ENTERED critical section WITH SHARED LOCK - {process_info}, Sample: {sample_name}")
                result = _execute_hisat2_db_operations_impl(current_process, process_info, sample_name, workbench_id, result_data)
                logger.info(f"🔓 [HISAT2-DB-LOCK-EXIT] PID={current_process.pid} LEAVING critical section - {process_info}, Sample: {sample_name}")
        else:
            logger.error(f"❌ [HISAT2-DB-LOCK] No shared_db_lock provided - this should not happen!")
            return False

        if result:
            logger.info(f"🎉 [HISAT2-RESULT-DB] Successfully saved sample result for {sample_name}")

        return result

    except Exception as e:
        logger.error(f"❌ [HISAT2-RESULT-DB] Critical error saving sample result for {sample_name}: {e}")
        logger.error(f"❌ [HISAT2-RESULT-DB] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [HISAT2-RESULT-DB] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")
        return False


def _execute_hisat2_db_operations_impl(current_process, process_info: str, sample_name: str, workbench_id: int, result_data: Dict[str, Any]) -> bool:
    """실제 HISAT2 데이터베이스 작업을 수행하는 구현 함수"""
    try:
        # 기존 progress_detail 가져오기
        logger.info(f"🔍 [HISAT2-RESULT-DB] Retrieving existing progress_detail from DB...")
        existing_data = {}

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            result = cursor.execute('''
                SELECT progress_detail FROM pipeline_job_steps
                WHERE workbench_id = ? AND tool_name = 'hisat2'
            ''', (workbench_id,)).fetchone()

            if result and result[0]:
                try:
                    existing_data = json.loads(result[0])
                    logger.info(f"✅ [HISAT2-RESULT-DB] Successfully loaded existing progress_detail: {len(existing_data.get('results', {}))} existing results")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ [HISAT2-RESULT-DB] Failed to parse existing progress_detail, initializing new: {e}")
                    existing_data = {"summary": {}, "results": {}}
            else:
                logger.info(f"ℹ️ [HISAT2-RESULT-DB] No existing progress_detail found, initializing new structure")
                existing_data = {"summary": {}, "results": {}}

        # 기존 구조 확인 및 보정
        if "results" not in existing_data:
            existing_data["results"] = {}
            logger.info(f"🔧 [HISAT2-RESULT-DB] Added missing 'results' section to progress_detail")

        if "summary" not in existing_data:
            existing_data["summary"] = {}
            logger.info(f"🔧 [HISAT2-RESULT-DB] Added missing 'summary' section to progress_detail")

        # results 섹션에 샘플 결과 추가
        previous_result = existing_data["results"].get(sample_name)
        existing_data["results"][sample_name] = result_data

        if previous_result:
            logger.info(f"🔄 [HISAT2-RESULT-DB] Updated existing result for sample {sample_name}")
        else:
            logger.info(f"➕ [HISAT2-RESULT-DB] Added new result for sample {sample_name}")

        # 현재 총 결과 수 확인
        total_results = len(existing_data["results"])

        # 디버깅: 각 샘플의 parsing_successful 상태 확인
        logger.info(f"🔍 [HISAT2-RESULT-DB] Debugging - analyzing {total_results} results:")
        for sample_key, sample_result in existing_data["results"].items():
            parsing_status = sample_result.get('parsing_successful', False)
            logger.info(f"   ├─ {sample_key}: parsing_successful = {parsing_status}")

        successful_results = sum(1 for r in existing_data["results"].values() if r.get('parsing_successful', False))

        logger.info(f"📊 [HISAT2-RESULT-DB] Current results summary: {successful_results}/{total_results} samples with successful parsing")

        # Summary 섹션 업데이트 (results와 동시에 업데이트하여 데이터 일관성 보장)
        import time
        current_time = time.time()

        # 기존 summary에서 total_files 정보 유지, 없으면 현재 결과 수를 기본값으로 사용
        existing_summary = existing_data.get("summary", {})
        total_files = existing_summary.get("total_files", total_results)

        # 진행률 계산
        if total_files > 0:
            progress_percent = (successful_results / total_files) * 100
        else:
            progress_percent = 0.0

        # Summary 데이터 업데이트
        updated_summary = {
            "completed_files": successful_results,
            "total_files": total_files,
            "progress_percent": round(progress_percent, 2),
            "last_updated": current_time
        }

        existing_data["summary"] = updated_summary

        logger.info(f"📈 [HISAT2-RESULT-DB] Updated summary: {successful_results}/{total_files} ({progress_percent:.1f}%)")

        # JSON 직렬화 테스트
        try:
            json_str = json.dumps(existing_data)
            json_size = len(json_str)
            logger.info(f"📦 [HISAT2-RESULT-DB] JSON serialization successful: {json_size} characters")
            logger.info(f"📄 [HISAT2-RESULT-DB] JSON content: {json_str}")
        except (TypeError, ValueError) as e:
            logger.error(f"❌ [HISAT2-RESULT-DB] JSON serialization failed: {e}")
            return False

        # UPDATE 직전 상태 로그 출력
        logger.debug(f"💾 [HISAT2-DB-UPDATE-BEFORE] PID={current_process.pid} About to update hisat2 step, Sample: {sample_name}, Total results: {total_results}, Successful: {successful_results}")

        # DB 업데이트 실행
        logger.info(f"💾 [HISAT2-RESULT-DB] Updating pipeline_job_steps table...")

        with database.get_db_connection() as conn:
            cursor = conn.cursor()

            # 업데이트 실행
            cursor.execute('''
                UPDATE pipeline_job_steps
                SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workbench_id = ? AND tool_name = 'hisat2'
            ''', (json_str, workbench_id))

            # 업데이트된 행 수 확인
            rows_affected = cursor.rowcount
            logger.info(f"📊 [HISAT2-RESULT-DB] Database update affected {rows_affected} row(s)")

            if rows_affected == 0:
                logger.warning(f"⚠️ [HISAT2-RESULT-DB] No rows were updated - pipeline step may not exist for workbench {workbench_id}")
                return False

            conn.commit()
            logger.info(f"✅ [HISAT2-RESULT-DB] Database transaction committed successfully")

        logger.debug(f"💾 [HISAT2-DB-UPDATE-AFTER] PID={current_process.pid} Successfully updated hisat2 step, Sample: {sample_name}")

        # Lock 해제 직전 로그 (공유 Lock 사용)
        logger.debug(f"🔓 [HISAT2-DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, Sample: {sample_name}, Operation: SUCCESS")

        return True

    except Exception as e:
        logger.error(f"❌ [HISAT2-DB-OPERATIONS] Critical error in DB operations for {sample_name}: {e}")
        logger.error(f"❌ [HISAT2-DB-OPERATIONS] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [HISAT2-DB-OPERATIONS] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")
        return False



def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 hisat2 tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering hisat2 tool...")
    
    metadata = {
        'name': 'hisat2',
        'description': 'HISAT2 alignment functionality',
        'version': '1.0.0',
        'supported_formats': ['.fastq', '.fastq.gz', '.fq', '.fq.gz'],
        'requirements': ['hisat2', 'samtools'],
        'parameters': {
            'hisat2_threads': 8,
            'hisat2_trim5': 0,
            'hisat2_trim3': 0,
            'hisat2_min_intronlen': 20,
            'hisat2_max_intronlen': 500000,
            'hisat2_dta': True
        }
    }
    
    return coordinator.register_tool('hisat2', execute_hisat2, metadata)
