"""
StringTie 정량화 모듈
RNA-seq 데이터의 전사체 정량화를 수행하는 모듈
"""
import gzip
import json
import subprocess
import os
import logging
import time
import sqlite3
from typing import Dict, List, Any, Tuple
from datetime import datetime
from statistics import median

# SharedState Events 추가
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.process_runner import ProcessPoolRunner

from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema
from config.backend_settings import BackendConfig as Config
from config.shared_config import SharedConfig

# ✅ ProcessWrapper import 추가
from backend.pipeline.utils.process_wrapper import ProcessWrapper

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Expression matrix 및 PCA 분석 함수들 import
from backend.pipeline.utils.expression_matrix import (
    run_prepde_analysis,
    build_tpm_matrix,
    run_tmm_normalization,
    reorder_matrix_samples
)
from backend.pipeline.utils.pca_analysis import run_pca


def _normalize_clean_tools(value) -> List[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value] if value else []
    return []


def _get_optional_float(parameters: Dict[str, Any], *keys: str):
    for key in keys:
        value = parameters.get(key)
        if value in (None, ''):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(f"⚠️ [STRINGTIE] Ignoring invalid numeric parameter {key}={value}")
    return None


def _get_optional_int(parameters: Dict[str, Any], *keys: str):
    value = _get_optional_float(parameters, *keys)
    return int(value) if value is not None else None


def _path_variants(path: str) -> List[str]:
    if not path:
        return []

    variants = [path]
    if path.endswith('.gz'):
        variants.append(path[:-3])
    else:
        variants.append(f"{path}.gz")
    return variants


def _first_existing_path(paths: List[str]):
    for path in paths:
        for candidate in _path_variants(path):
            if os.path.exists(candidate):
                return candidate
    return None


def _open_fastq_text(path: str):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, 'r', encoding='utf-8', errors='replace')


def _estimate_fastq_read_length(path: str, max_reads: int = 1000):
    lengths = []
    with _open_fastq_text(path) as handle:
        for _ in range(max_reads):
            header = handle.readline()
            if not header:
                break
            sequence = handle.readline()
            plus = handle.readline()
            quality = handle.readline()
            if not quality:
                break
            sequence = sequence.strip()
            if sequence:
                lengths.append(len(sequence))

    if not lengths:
        return None
    return int(round(median(lengths)))


def _build_read_length_candidate_files(sample_data: Dict[str, Any], layout: str, workbench_schema: Dict[str, Any], clean_tools: List[str]) -> List[str]:
    sample_name = sample_data['sampleName']
    group_name = sample_data['groupName']
    candidates = []

    if 'prinseq' in clean_tools:
        prinseq_dir = os.path.join(workbench_schema["quanti"]["clean"], "prinseq", group_name, sample_name, "good")
        if layout == 'pe':
            candidates.extend([
                os.path.join(prinseq_dir, f"{sample_name}_good_1.fastq"),
                os.path.join(prinseq_dir, f"{sample_name}_good_2.fastq")
            ])
        else:
            candidates.append(os.path.join(prinseq_dir, f"{sample_name}_good.fastq"))

    if 'trimmomatic' in clean_tools:
        trim_dir = os.path.join(workbench_schema["quanti"]["clean"], "trim", group_name, sample_name)
        if layout == 'pe':
            candidates.extend([
                os.path.join(trim_dir, f"{sample_name}_1_paired.fastq"),
                os.path.join(trim_dir, f"{sample_name}_2_paired.fastq")
            ])
        else:
            candidates.append(os.path.join(trim_dir, f"{sample_name}_trimmed.fastq"))

    raw_dir = workbench_schema["quanti"]["raw"]
    if sample_data.get('file1'):
        candidates.append(os.path.join(raw_dir, sample_data['file1']))
    if layout == 'pe' and sample_data.get('file2'):
        candidates.append(os.path.join(raw_dir, sample_data['file2']))

    return candidates


def _resolve_read_length(parameters: Dict[str, Any], sample_info_list: List[Dict]) -> int:
    configured_value = parameters.get('read_length', parameters.get('stringtie_read_length'))

    if configured_value not in (None, '', 'auto'):
        try:
            read_length = int(float(configured_value))
            if read_length > 0:
                logger.info(f"📏 [STRINGTIE] Using configured read_length={read_length}")
                return read_length
        except (TypeError, ValueError):
            logger.warning(f"⚠️ [STRINGTIE] Invalid read_length={configured_value}; attempting auto detection")

    for sample_info in sample_info_list:
        candidate_file = _first_existing_path(sample_info.get('read_length_files', []))
        if not candidate_file:
            continue

        try:
            estimated_length = _estimate_fastq_read_length(candidate_file)
            if estimated_length:
                logger.info(
                    f"📏 [STRINGTIE] Auto-detected read_length={estimated_length} "
                    f"from {os.path.basename(candidate_file)}"
                )
                return estimated_length
        except Exception as exc:
            logger.warning(f"⚠️ [STRINGTIE] Failed to estimate read length from {candidate_file}: {exc}")

    logger.warning("⚠️ [STRINGTIE] Could not auto-detect read length; falling back to 75 for compatibility")
    return 75

def execute_stringtie(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    """StringTie 실행 - job_step에서 직접 정보 추출"""
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

        logger.info(f"🎯 [STRINGTIE] Starting StringTie quantification process")
        logger.info(f"📋 [STRINGTIE] Job Configuration:")
        logger.info(f"   ├─ workbench_id: {workbench_id}")
        logger.info(f"   ├─ user: {username}")
        logger.info(f"   └─ step_id: {step_id}")

        # 출력 디렉토리 설정 (count 디렉토리 사용)
        output_dir = os.path.join(workbench_schema["quanti"]["counts"])
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"📁 [STRINGTIE] Created output directory: {output_dir}")

        # HISAT2 결과 디렉토리 (입력 BAM 파일 위치)
        alignment_dir = os.path.join(workbench_schema["quanti"]["alignment"])
        logger.info(f"📁 [STRINGTIE] Input BAM directory: {alignment_dir}")

        # Reference 세트 선택 (기본값: TAIR10)
        reference_set = parameters.get('reference_set', 'TAIR10')
        species = parameters.get('species', 'arabidopsis')

        logger.info(f"🧬 [STRINGTIE] Reference configuration:")
        logger.info(f"   ├─ Species: {species}")
        logger.info(f"   └─ Reference set: {reference_set}")

        # Reference 세트 디렉토리 경로
        reference_dir = f"{SharedConfig.VIZR_PATH}/users/{username}/resource/{species}/reference/{reference_set}"
        metadata_file = os.path.join(reference_dir, "metadata.json")

        # metadata.json 읽기
        if not os.path.exists(metadata_file):
            error_msg = f"Reference metadata not found: {metadata_file}"
            logger.error(f"❌ [STRINGTIE] {error_msg}")
            raise FileNotFoundError(error_msg)

        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        logger.info(f"📋 [STRINGTIE] Loaded metadata: {metadata.get('name', 'Unknown')} v{metadata.get('version', 'Unknown')}")

        # GTF Annotation 파일 경로
        gtf_filename = metadata['files']['annotation']
        gtf_file = os.path.join(reference_dir, gtf_filename)

        logger.info(f"📄 [STRINGTIE] GTF file: {gtf_filename}")

        # GTF 파일 존재 확인
        if not os.path.exists(gtf_file):
            error_msg = f"GTF file not found: {gtf_file}"
            logger.error(f"❌ [STRINGTIE] {error_msg}")
            raise FileNotFoundError(error_msg)

        # samples_data 구성
        sample_info_list = []
        
        # workbench_id에서 샘플 정보와 layout 정보 조회
        with database.get_db_connection() as db_connection:
            cursor = db_connection.cursor()
            cursor.execute("""
                SELECT samples, layout 
                FROM vizr_pipeline_samples 
                WHERE id = ?
            """, (workbench_id,))
            pipeline_samples_result = cursor.fetchone()
            
            if pipeline_samples_result:
                samples_json = pipeline_samples_result['samples']
                layout = pipeline_samples_result['layout']
                logger.info(f"📊 [STRINGTIE] Retrieved samples from vizr_pipeline_samples (layout: {layout})")
                
                try:
                    samples_data = json.loads(samples_json)
                    logger.info(f"✅ [STRINGTIE] {len(samples_data)} samples")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ [STRINGTIE] Failed to parse samples JSON: {e}")
                    raise
            else:
                logger.warning(f"⚠️  [STRINGTIE] No samples found for workbench_id: {workbench_id}")
                layout = 'pe'  # 기본값

        logger.info(f"📊 [STRINGTIE] Layout: {layout}")
        logger.info(f"📊 [STRINGTIE] Total samples: {len(samples_data)}")
        clean_tools = _normalize_clean_tools(parameters.get('clean_tools', []))
        logger.info(f"⚙️ [STRINGTIE] Clean tools for read length detection: {clean_tools}")

        # ProcessWrapper는 각 run_single_stringtie에서 개별 생성됨

        # 각 샘플에 대한 정보 구성
        for sample_data in samples_data:
            sample_name = sample_data['sampleName']
            group_name = sample_data['groupName']
            
            # HISAT2 출력 파일 경로 (입력으로 사용)
            sample_alignment_dir = os.path.join(alignment_dir, group_name, sample_name)
            sorted_bam_file = os.path.join(sample_alignment_dir, f"{sample_name}_sorted.bam")
            
            # StringTie 출력 파일 경로
            sample_output_dir = os.path.join(output_dir, group_name, sample_name)
            os.makedirs(sample_output_dir, exist_ok=True)
            
            gtf_output_file = os.path.join(sample_output_dir, f"{sample_name}_sorted.bam.gtf")
            abundance_file = os.path.join(sample_output_dir, "gene_abund.tab")

            sample_info_dict = {
                'sample_name': sample_name,
                'group_name': group_name,
                'sorted_bam_file': sorted_bam_file,
                'output_dir': sample_output_dir,
                'gtf_output_file': gtf_output_file,
                'abundance_file': abundance_file,
                'reference_gtf': gtf_file,
                'workbench_schema': workbench_schema,
                'layout': layout,
                'read_length_files': _build_read_length_candidate_files(sample_data, layout, workbench_schema, clean_tools)
            }
            
            sample_info_list.append(sample_info_dict)
            logger.info(f"📊 [STRINGTIE] Sample configured: {sample_name} (group: {group_name})")

        # StringTie 멀티프로세싱 실행 - worker_id와 workbench_id 전달
        results = execute_stringtie_multi(sample_info_list, parameters, worker_id, workbench_id)
        
        logger.info(f"[STRINGTIE] StringTie execution completed")
        return results
        
    except Exception as e:
        logger.error(f"[STRINGTIE] StringTie execution failed: {e}")
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'timestamp': datetime.now().isoformat()
        }

def execute_stringtie_multi(sample_info_list: List[Dict], parameters: Dict, worker_id: str = "worker", workbench_id: int = None) -> Dict[str, str]:
    """
    StringTie 멀티프로세싱 실행
    SharedState Event 기반 stop 신호 처리
    """
    import psutil
    from concurrent.futures import ProcessPoolExecutor
    
    logger.info(f"🚀 [STRINGTIE-MULTI] Starting StringTie multi-processing execution")
    logger.info(f"📊 [STRINGTIE-MULTI] Total samples: {len(sample_info_list)}")
    logger.info(f"⚙️  [STRINGTIE-MULTI] Worker ID: {worker_id}")

    # SharedState에서 해당 워커의 Event 가져오기
    worker_stop_event = shared_state.get_worker_event(worker_id)
    if worker_stop_event is None:
        logger.warning(f"⚠️ [STRINGTIE-MULTI] No stop event found for worker {worker_id}")
        worker_stop_event = shared_state.manager.Event()
    
    start_time = time.time()
    successful_results = []
    failed_results = []
    stopped_by_user = False

    # CPU 코어 수에 따른 동적 워커 수 설정
    cpu_count = psutil.cpu_count(logical=False)
    max_workers = min(len(sample_info_list), max(1, cpu_count - 1))
    logger.info(f"🔧 [STRINGTIE-MULTI] Using {max_workers} concurrent workers (CPU cores: {cpu_count})")

    # 프로세스 간 공유 Lock 생성 (Manager를 통한 진정한 프로세스 간 공유)
    import multiprocessing as mp
    manager = mp.Manager()
    shared_db_lock = manager.Lock()
    logger.info(f"🔒 [STRINGTIE-MULTI] Created shared DB lock for multiprocessing (lock_id={id(shared_db_lock)})")

    # 초기 진행률 전송
    completed_samples = 0
    total_samples = len(sample_info_list)

    if workbench_id:
        # 초기 진행률 Redis 전송
        initial_progress = {
            "completed_files": completed_samples,
            "total_files": total_samples,
            "progress_percent": 0.0
        }
        send_stringtie_progress_update(workbench_id, initial_progress)
        # 초기화 시점에는 shared_db_lock이 아직 생성되지 않음
        _save_stringtie_progress_to_db(workbench_id, completed_samples, total_samples, shared_db_lock)

    # 각 샘플에 worker_id와 workbench_id 추가
    work_args = [(sample_info, parameters, worker_id, workbench_id) for sample_info in sample_info_list]

    try:
        logger.info(f"🎯 [STRINGTIE-MULTI] Creating ProcessPoolRunner with external stop event")

        with ProcessPoolRunner(max_workers=max_workers, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
            logger.info(f"🚀 [STRINGTIE-MULTI] Starting parallel StringTie execution...")
            
            # 병렬 실행 및 결과 수집
            for i, result in enumerate(runner.map_unordered(run_single_stringtie, work_args)):
                sample_name = result.get('sample_name', f'sample_{i+1}')
                
                if result.get('stopped_by_user', False):
                    logger.warning(f"🛑 [STRINGTIE-MULTI] Sample {sample_name} stopped by user")
                    stopped_by_user = True
                    runner.stop()
                    # Reset worker event for next execution
                    shared_state.reset_worker(worker_id)
                    break
                elif result.get('success', False):
                    successful_results.append(result)
                    logger.info(f"✅ [STRINGTIE-MULTI] Sample {sample_name} completed successfully ({len(successful_results)}/{len(sample_info_list)})")
                else:
                    failed_results.append(result)
                    logger.error(f"❌ [STRINGTIE-MULTI] Sample {sample_name} failed: {result.get('stderr', 'Unknown error')}")

                    # 실패한 샘플이 있어도 계속 진행 (선택적 중단)
                    continue

                # 진행률 업데이트 (샘플 완료시마다)
                if workbench_id:
                    completed_samples = i + 1
                    progress_percent = (completed_samples / total_samples * 100) if total_samples > 0 else 0.0

                    # 후처리(prepDE, TPM, TMM)가 남아있으므로 최대 99%까지만 표시
                    # 100%는 모든 후처리 완료 후에만 전송
                    if progress_percent >= 100:
                        progress_percent = 99.0

                    # Redis 실시간 진행률 전송
                    progress_data = {
                        "completed_files": completed_samples,
                        "total_files": total_samples,
                        "progress_percent": round(progress_percent, 2),
                        "current_sample": sample_name
                    }
                    send_stringtie_progress_update(workbench_id, progress_data)

                    # DB에 진행률 저장 (샘플 완료시마다 저장)
                    _save_stringtie_progress_to_db(workbench_id, completed_samples, total_samples, shared_db_lock)

                    logger.info(f"📊 [STRINGTIE-MULTI] Progress: {completed_samples}/{total_samples} ({progress_percent:.1f}%)")

        execution_time = time.time() - start_time

        # ⚠️ 주의: 아직 100% 전송하지 않음 - 후처리(prepDE, TPM, TMM)가 남아있음
        # 후처리 완료 후에 progress_percent=100 전송

        # 결과 요약
        total_samples = len(sample_info_list)
        success_count = len(successful_results)
        failed_count = len(failed_results)
        
        if stopped_by_user:
            logger.info(f"🛑 [STRINGTIE-MULTI] StringTie multi-processing stopped by user")
            logger.info(f"📊 [STRINGTIE-MULTI] Completed before stop: {success_count}/{total_samples} samples")
            
            return {
                'success': False,
                'stdout': f'StringTie processing stopped by user after {success_count}/{total_samples} samples',
                'stderr': 'Processing stopped by user signal',
                'timestamp': datetime.now().isoformat(),
                'execution_time': execution_time,
                'successful_samples': success_count,
                'failed_samples': failed_count,
                'stopped_by_user': True
            }
        
        elif success_count == total_samples:
            logger.info(f"🎉 [STRINGTIE-MULTI] All samples completed successfully!")
            logger.info(f"📊 [STRINGTIE-MULTI] Execution time: {execution_time:.2f} seconds")

            # TPM 매트릭스 생성
            try:
                logger.info(f"📊 [STRINGTIE-MULTI] Building TPM matrix from {total_samples} samples...")

                # workbench 정보 조회하여 schema 가져오기
                with database.get_db_connection() as conn:
                    workbench = conn.execute('SELECT name, user_id FROM vizr_workbench WHERE id = ?', (workbench_id,)).fetchone()

                if workbench:
                    workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
                    counts_dir = workbench_schema["quanti"]["counts"]
                    logger.info(f"📂 [STRINGTIE-MULTI] Counts directory: {counts_dir}")
                    matrix_output = os.path.join(counts_dir, "genes.TPM.matrix")
                    logger.info(f"📄 [STRINGTIE-MULTI] Matrix output path: {matrix_output}")
                else:
                    raise ValueError(f"Workbench {workbench_id} not found")

                # PrepDE 분석 먼저 실행 (gene/transcript count matrix 생성)
                logger.info(f"🔬 [STRINGTIE-MULTI] Running PrepDE analysis for count matrices...")
                read_length = _resolve_read_length(parameters, sample_info_list)
                prepde_result = run_prepde_analysis(
                    counts_dir=counts_dir,
                    sample_info_list=sample_info_list,
                    read_length=read_length
                )

                if prepde_result.get('success', False):
                    logger.info(f"✅ [STRINGTIE-MULTI] PrepDE analysis completed:")
                    logger.info(f"   ├─ Gene matrix: {prepde_result.get('gene_matrix_file', 'N/A')}")
                    logger.info(f"   ├─ Transcript matrix: {prepde_result.get('transcript_matrix_file', 'N/A')}")
                    logger.info(f"   └─ Processed samples: {prepde_result.get('processed_samples', 0)}")
                else:
                    logger.error(f"❌ [STRINGTIE-MULTI] PrepDE analysis failed")

                # TPM 매트릭스 생성 (PrepDE 후에 실행)
                logger.info(f"📊 [STRINGTIE-MULTI] Building TPM matrix...")
                tpm_matrix = build_tpm_matrix(
                    counts_dir=counts_dir,
                    sample_info_list=sample_info_list,
                    output=matrix_output
                )

                logger.info(f"✅ [STRINGTIE-MULTI] TPM matrix created: {matrix_output}")
                logger.info(f"📊 [STRINGTIE-MULTI] Matrix size: {tpm_matrix.shape[0]} genes × {tpm_matrix.shape[1]-1} samples")

                # TMM 정규화 실행 (세 번째 단계)
                logger.info(f"🔧 [STRINGTIE-MULTI] Running TMM normalization...")
                tmm_result = run_tmm_normalization(
                    counts_dir=counts_dir,
                    tpm_matrix_file=matrix_output
                )

                if tmm_result.get('success', False):
                    logger.info(f"✅ [STRINGTIE-MULTI] TMM normalization completed:")
                    logger.info(f"   └─ TMM matrix: {tmm_result.get('tmm_matrix_file', 'N/A')}")

                    # TMM 매트릭스 샘플 순서를 vizr_pipeline_samples 순서로 재정렬
                    logger.info(f"🔄 [STRINGTIE-MULTI] Reordering TMM matrix samples to match vizr_pipeline_samples order...")
                    sample_order = [s['sample_name'] for s in sample_info_list]
                    reorder_result = reorder_matrix_samples(
                        matrix_file=tmm_result.get('tmm_matrix_file'),
                        sample_order=sample_order
                    )

                    if reorder_result.get('success', False):
                        logger.info(f"✅ [STRINGTIE-MULTI] TMM matrix samples reordered:")
                        logger.info(f"   ├─ Reordered samples: {reorder_result.get('reordered_samples', 0)}")
                        logger.info(f"   ├─ Missing samples: {len(reorder_result.get('missing_samples', []))}")
                        logger.info(f"   └─ Extra samples: {len(reorder_result.get('extra_samples', []))}")
                    else:
                        logger.warning(f"⚠️ [STRINGTIE-MULTI] Failed to reorder TMM matrix samples: {reorder_result.get('error', 'Unknown error')}")
                else:
                    logger.error(f"❌ [STRINGTIE-MULTI] TMM normalization failed")

                # PCA 분석 실행 (네 번째 단계)
                logger.info(f"📊 [STRINGTIE-MULTI] Running PCA analysis...")

                # PrepDE로 생성된 genes.counts.matrix 파일 사용
                count_matrix_file = prepde_result.get('trinity_matrix_file', os.path.join(counts_dir, "genes.counts.matrix"))

                pca_result = run_pca(
                    counts_dir=counts_dir,
                    count_matrix_file=count_matrix_file,
                    workbench_id=workbench_id,
                    worker_id=worker_id
                )

                if pca_result.get('success', False):
                    logger.info(f"✅ [STRINGTIE-MULTI] PCA analysis completed:")
                    logger.info(f"   ├─ Output directory: {pca_result.get('pca_output_dir', 'N/A')}")
                    logger.info(f"   ├─ Generated files: {len(pca_result.get('output_files', []))}")
                    logger.info(f"   └─ Samples file: {pca_result.get('samples_file', 'N/A')}")
                else:
                    logger.error(f"❌ [STRINGTIE-MULTI] PCA analysis failed: {pca_result.get('error', 'Unknown error')}")

                # 모든 후처리 완료 - 이제 100% 진행률 전송
                if workbench_id:
                    logger.info(f"🎉 [STRINGTIE-MULTI] All post-processing completed, sending 100% progress")
                    final_progress = {
                        "completed_files": len(successful_results) + len(failed_results),
                        "total_files": len(sample_info_list),
                        "progress_percent": 100.0
                    }
                    send_stringtie_progress_update(workbench_id, final_progress)

            except Exception as e:
                logger.error(f"❌ [STRINGTIE-MULTI] Failed to build TPM matrix: {e}")
                # 매트릭스 생성 실패해도 StringTie는 성공으로 처리
                # 하지만 100% 진행률은 전송
                if workbench_id:
                    logger.warning(f"⚠️ [STRINGTIE-MULTI] Post-processing failed, but sending 100% progress")
                    final_progress = {
                        "completed_files": len(successful_results) + len(failed_results),
                        "total_files": len(sample_info_list),
                        "progress_percent": 100.0
                    }
                    send_stringtie_progress_update(workbench_id, final_progress)

            return {
                'success': True,
                'stdout': f'All {success_count} samples processed successfully',
                'stderr': '',
                'timestamp': datetime.now().isoformat(),
                'execution_time': execution_time,
                'successful_samples': success_count,
                'failed_samples': failed_count,
                'stopped_by_user': False
            }
        
        elif success_count > 0:
            logger.warning(f"⚠️ [STRINGTIE-MULTI] Partial success: {success_count}/{total_samples} samples completed")
            
            return {
                'success': False,  # 부분 성공은 실패로 간주
                'stdout': f'{success_count}/{total_samples} samples completed successfully',
                'stderr': f'{failed_count} samples failed',
                'timestamp': datetime.now().isoformat(),
                'execution_time': execution_time,
                'successful_samples': success_count,
                'failed_samples': failed_count,
                'stopped_by_user': False
            }
        
        else:
            logger.error(f"❌ [STRINGTIE-MULTI] All samples failed!")
            
            return {
                'success': False,
                'stdout': '',
                'stderr': f'All {total_samples} samples failed',
                'timestamp': datetime.now().isoformat(),
                'execution_time': execution_time,
                'successful_samples': 0,
                'failed_samples': failed_count,
                'stopped_by_user': False
            }
            
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"💥 [STRINGTIE-MULTI] StringTie multi-processing failed with exception: {str(e)}")
        
        return {
            'success': False,
            'stdout': '',
            'stderr': f'StringTie multi-processing exception: {str(e)}',
            'timestamp': datetime.now().isoformat(),
            'execution_time': execution_time,
            'successful_samples': len(successful_results),
            'failed_samples': len(failed_results),
            'stopped_by_user': False
        }

def run_single_stringtie(sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """Process individual StringTie sample"""
    
    if stop_event and stop_event.is_set():
        return { 'success': False, 'stopped_by_user': True }
    
    # Logging setup (separate logger for each process)
    process_logger = logging.getLogger(f"stringtie_worker_{os.getpid()}")
    start_time = time.time()
    
    # Log input parameters at function start
    process_logger.info(f"🎯 [STRINGTIE-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
    process_logger.info(f"🎯 [STRINGTIE-{os.getpid()}] ║                STRINGTIE Function Started - Input Debug          ║")
    process_logger.info(f"🎯 [STRINGTIE-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
    process_logger.info(f"")
    process_logger.info(f"📋 [STRINGTIE-{os.getpid()}] INPUT PARAMETERS DEBUG:")
    
    process_logger.info(f"🔍 [STRINGTIE-{os.getpid()}] sample_info contents:")
    for key, value in sample_info.items():
        if isinstance(value, dict):
            process_logger.info(f"   ├─ {key}: {{")
            for sub_key, sub_value in value.items():
                process_logger.info(f"   │     {sub_key}: {sub_value}")
            process_logger.info(f"   │   }}")
        else:
            process_logger.info(f"   ├─ {key}: {value}")
    
    process_logger.info(f"🔍 [STRINGTIE-{os.getpid()}] parameters contents:")
    for key, value in parameters.items():
        process_logger.info(f"   ├─ {key}: {value}")
    
    try:
        # Extract sample information
        sample_name = sample_info['sample_name']
        group_name = sample_info['group_name']
        sorted_bam_file = sample_info['sorted_bam_file']
        output_dir = sample_info['output_dir']
        gtf_output_file = sample_info['gtf_output_file']
        abundance_file = sample_info['abundance_file']
        reference_gtf = sample_info['reference_gtf']
        
        process_logger.info(f"")
        process_logger.info(f"🎯 [STRINGTIE-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
        process_logger.info(f"🎯 [STRINGTIE-{os.getpid()}] ║              STRINGTIE EXECUTION STARTING                       ║")
        process_logger.info(f"🎯 [STRINGTIE-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
        process_logger.info(f"📋 [STRINGTIE-{os.getpid()}] Sample: {sample_name} (Group Name: {group_name})")
        process_logger.info(f"📋 [STRINGTIE-{os.getpid()}] Input BAM: {sorted_bam_file}")
        process_logger.info(f"📋 [STRINGTIE-{os.getpid()}] Reference GTF: {reference_gtf}")
        process_logger.info(f"📋 [STRINGTIE-{os.getpid()}] Output GTF: {gtf_output_file}")
        process_logger.info(f"📋 [STRINGTIE-{os.getpid()}] Abundance file: {abundance_file}")
        
        # Check input file existence
        if not os.path.exists(sorted_bam_file):
            error_msg = f"Input BAM file not found: {sorted_bam_file}"
            process_logger.error(f"❌ [STRINGTIE-{os.getpid()}] {error_msg}")
            return {
                'success': False,
                'sample_name': sample_name,
                'stderr': error_msg,
                'stdout': '',
                'output_files': []
            }
        
        if not os.path.exists(reference_gtf):
            error_msg = f"Reference GTF file not found: {reference_gtf}"
            process_logger.error(f"❌ [STRINGTIE-{os.getpid()}] {error_msg}")
            return {
                'success': False,
                'sample_name': sample_name,
                'stderr': error_msg,
                'stdout': '',
                'output_files': []
            }
        
        # Check input file size
        bam_size = os.path.getsize(sorted_bam_file)
        process_logger.info(f"📁 [STRINGTIE-{os.getpid()}] Input BAM size: {bam_size:,} bytes")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        process_logger.info(f"📁 [STRINGTIE-{os.getpid()}] Created output directory: {output_dir}")
        
        # StringTie command configuration
        # Based on the comment template:
        # stringtie -eB -G gtf_file -A gene_abund.tab -o output.gtf -p 16 input.bam
        
        threads = parameters.get('threads', 16)
        process_logger.info(f"⚙️  [STRINGTIE-{os.getpid()}] Using {threads} threads")
        min_coverage = _get_optional_float(parameters, 'min_coverage', 'stringtie_min_coverage')
        min_transcript_len = _get_optional_int(parameters, 'min_transcript_len', 'stringtie_min_transcript_len')
        
        cmd = [
            'stringtie',
            '-eB',  # Enable reference-guided transcriptome assembly and ballgown table output
            '-G', reference_gtf,  # Reference GTF file
            '-A', abundance_file,  # Gene abundance output file
            '-o', gtf_output_file,  # Output GTF file
            '-p', str(threads),  # Number of threads
            sorted_bam_file  # Input BAM file
        ]
        if min_coverage is not None:
            cmd[-1:-1] = ['-c', str(min_coverage)]
            process_logger.info(f"⚙️  [STRINGTIE-{os.getpid()}] Minimum coverage: {min_coverage}")
        if min_transcript_len is not None:
            cmd[-1:-1] = ['-m', str(min_transcript_len)]
            process_logger.info(f"⚙️  [STRINGTIE-{os.getpid()}] Minimum transcript length: {min_transcript_len}")
        
        process_logger.info(f"")
        process_logger.info(f"🚀 [STRINGTIE-{os.getpid()}] Executing StringTie command:")
        process_logger.info(f"   └─ {' '.join(cmd)}")
        process_logger.info(f"")
        
        # ✅ ProcessWrapper로 StringTie 실행
        process_logger.info(f"🔧 [STRINGTIE-{os.getpid()}] Creating ProcessWrapper with worker_id: {worker_id}")
        wrapper = ProcessWrapper(worker_id)
        
        exec_start_time = time.time()
        process_logger.info(f"🚀 [STRINGTIE-{os.getpid()}] Starting ProcessWrapper execution...")
        
        # ProcessWrapper로 프로세스 실행 (Stop 신호 체크 통합)
        result = wrapper.run_command(cmd, stop_event=stop_event, cwd=output_dir)
        
        if result['stopped_by_user']:
            process_logger.info(f"🛑 [STRINGTIE-{os.getpid()}] StringTie stopped by user signal")
            return {
                'success': False,
                'sample_name': sample_name,
                'stderr': 'StringTie execution stopped by user signal',
                'stdout': '',
                'output_files': [],
                'stopped_by_user': True
            }
        
        execution_time = time.time() - exec_start_time
        total_time = time.time() - start_time
        
        # Log execution results
        process_logger.info(f"")
        process_logger.info(f"📊 [STRINGTIE-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
        process_logger.info(f"📊 [STRINGTIE-{os.getpid()}] ║                    EXECUTION RESULTS                             ║")
        process_logger.info(f"📊 [STRINGTIE-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
        process_logger.info(f"📊 [STRINGTIE-{os.getpid()}] Return code: {result.get('returncode', 'N/A')}")
        process_logger.info(f"📊 [STRINGTIE-{os.getpid()}] Success: {result.get('success', False)}")
        process_logger.info(f"📊 [STRINGTIE-{os.getpid()}] Execution time: {execution_time:.2f}초")
        process_logger.info(f"📊 [STRINGTIE-{os.getpid()}] Total time: {total_time:.2f}초")
        
        # StringTie 성공 - stdout 또는 stderr에서 통계 정보 파싱 및 로그 출력
        process_logger.info(f"📊 [STRINGTIE-{os.getpid()}] Parsing StringTie execution output...")

        output_to_parse = None
        output_source = "none"

        # stdout 우선 확인
        if result.get('stdout'):
            output_to_parse = result['stdout']
            output_source = "stdout"
            process_logger.info(f"📄 [STRINGTIE-{os.getpid()}] Found output in stdout ({len(result['stdout'])} chars)")
        # stdout이 비어있으면 stderr 확인
        elif result.get('stderr'):
            output_to_parse = result['stderr']
            output_source = "stderr"
            process_logger.info(f"📄 [STRINGTIE-{os.getpid()}] Found output in stderr ({len(result['stderr'])} chars)")
        else:
            process_logger.warning(f"⚠️ [STRINGTIE-{os.getpid()}] Sample {sample_name} succeeded but has empty stdout and stderr")

        # 우선순위에 따른 출력 로그
        if output_to_parse:
            process_logger.info(f"📤 [STRINGTIE-{os.getpid()}] {output_source.upper()} (primary output):")
            for line in output_to_parse.strip().split('\n'):
                if line.strip():
                    process_logger.info(f"   │ {line}")

            # 보조 출력도 있으면 기록
            if output_source == "stdout" and result.get('stderr'):
                process_logger.info(f"📥 [STRINGTIE-{os.getpid()}] STDERR (secondary output):")
                for line in result['stderr'].strip().split('\n'):
                    if line.strip():
                        process_logger.info(f"   │ {line}")
            elif output_source == "stderr" and result.get('stdout'):
                process_logger.info(f"📤 [STRINGTIE-{os.getpid()}] STDOUT (secondary output):")
                for line in result['stdout'].strip().split('\n'):
                    if line.strip():
                        process_logger.info(f"   │ {line}")
        
        # Check for output files
        output_files = []
        missing_files = []
        
        expected_outputs = [gtf_output_file, abundance_file]
        for output_file in expected_outputs:
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                output_files.append(output_file)
                process_logger.info(f"✅ [STRINGTIE-{os.getpid()}] Created: {os.path.basename(output_file)} ({file_size:,} bytes)")
            else:
                missing_files.append(output_file)
                process_logger.error(f"❌ [STRINGTIE-{os.getpid()}] Missing: {os.path.basename(output_file)}")
        
        # Determine success
        success = (result.get('success', False) and len(missing_files) == 0)
        
        if success:
            total_output_size = sum(os.path.getsize(f) for f in output_files if os.path.exists(f))
            process_logger.info(f"")
            process_logger.info(f"🎉 [STRINGTIE-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
            process_logger.info(f"🎉 [STRINGTIE-{os.getpid()}] ║                   SUCCESS SUMMARY                                ║")
            process_logger.info(f"🎉 [STRINGTIE-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
            process_logger.info(f"✅ [STRINGTIE-{os.getpid()}] StringTie completed successfully!")
            process_logger.info(f"   ├─ Sample: {sample_name}")
            process_logger.info(f"   ├─ 총 처리 시간: {total_time:.2f}초")
            process_logger.info(f"   ├─ StringTie 실행 시간: {execution_time:.2f}초")
            process_logger.info(f"   ├─ 총 출력 크기: {total_output_size:,} bytes")
            process_logger.info(f"   └─ 출력 디렉토리: {output_dir}")
            
            return {
                'success': True,
                'sample_name': sample_name,
                'stdout': result.get('stdout', ''),
                'stderr': result.get('stderr', ''),
                'output_files': output_files,
                'execution_time': execution_time,
                'total_time': total_time
            }
        else:
            error_msg = f"StringTie failed for {sample_name}"
            if missing_files:
                error_msg += f" - Missing output files: {missing_files}"
            if not result.get('success', False):
                error_msg += f" - ProcessWrapper error: {result.get('stderr', 'Unknown error')}"
                
            process_logger.error(f"❌ [STRINGTIE-{os.getpid()}] {error_msg}")
            
            return {
                'success': False,
                'sample_name': sample_name,
                'stdout': result.get('stdout', ''),
                'stderr': error_msg,
                'output_files': output_files,
                'execution_time': execution_time,
                'total_time': total_time
            }
            
    except Exception as e:
        total_time = time.time() - start_time
        error_msg = f"StringTie processing exception for {sample_info.get('sample_name', 'unknown')}: {str(e)}"
        process_logger.error(f"💥 [STRINGTIE-{os.getpid()}] {error_msg}")
        
        return {
            'success': False,
            'sample_name': sample_info.get('sample_name', 'unknown'),
            'stdout': '',
            'stderr': error_msg,
            'output_files': [],
            'total_time': total_time
        }            

# ============================================================================
# StringTie Cleanup Functions
# ============================================================================

def cleanup_stringtie_temp_files(*file_paths):
    """StringTie 임시 파일들 정리"""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                if os.path.isdir(file_path):
                    import shutil
                    shutil.rmtree(file_path)
                    logger.info(f"🗑️ [STRINGTIE-CLEANUP] Removed temp directory: {os.path.basename(file_path)}")
                else:
                    os.remove(file_path)
                    logger.info(f"🗑️ [STRINGTIE-CLEANUP] Removed temp file: {os.path.basename(file_path)}")
            except Exception as e:
                logger.warning(f"⚠️ [STRINGTIE-CLEANUP] Failed to remove {file_path}: {e}")

# ============================================================================
# Matrix Processing Functions Moved to expression_matrix.py
# ============================================================================
# The following functions have been moved to backend.pipeline.utils.expression_matrix:
# - run_prepde_analysis()
# - build_tpm_matrix()
# - run_tmm_normalization()
# - run_matrix_preprocess()
# - collect_gtf_samples()
# - parse_gene_info()
# - get_coverage()
# - process_gtf_file()
# - find_gene_abund_paths()
# - load_tpm_table()

# All the removed functions have been moved to expression_matrix.py

def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 stringtie tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering stringtie tool...")

    metadata = {
        'name': 'stringtie',
        'description': 'StringTie transcriptome assembly and quantification',
        'version': '1.0.0',
        'supported_formats': ['.bam', '.sam'],
        'requirements': ['stringtie', 'prepDE.py'],
        'parameters': {
            'stringtie_threads': 8,
            'stringtie_min_tpm': 1.0,
            'stringtie_min_coverage': 2.5,
            'stringtie_min_read_per_bp': 1.0,
            'stringtie_min_locus_gap_sep': 50,
            'stringtie_ballgown': True
        }
    }

    return coordinator.register_tool('stringtie', execute_stringtie, metadata)


def send_stringtie_progress_update(workbench_id: int, progress_data: dict) -> bool:
    """
    StringTie 진행률 직접 전송

    Args:
        workbench_id: 워크벤치 ID
        progress_data: 진행률 데이터

    Returns:
        전송 성공 여부
    """
    try:
        from backend.pipeline.utils.redis_broker import get_redis_broker
        redis_broker = get_redis_broker()

        if not redis_broker.is_available():
            logger.debug(f"📡 [STRINGTIE-PROGRESS] Redis not available, skipping progress update")
            return False

        success = redis_broker.publish_progress(
            workbench_id=workbench_id,
            task_type='stringtie',
            progress_data=progress_data
        )

        if success:
            logger.debug(f"📡 [STRINGTIE-PROGRESS] Successfully sent progress update: {progress_data}")
        else:
            logger.warning(f"📡 [STRINGTIE-PROGRESS] Failed to send progress update")

        return success
    except Exception as e:
        logger.error(f"❌ [STRINGTIE-PROGRESS] Error sending progress update: {e}")
        return False


def _save_stringtie_progress_to_db(workbench_id: int, completed_samples: int, total_samples: int, shared_db_lock=None) -> bool:
    """
    StringTie 진행률 정보를 DB에 저장

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

    logger.info(f"📊 [STRINGTIE-PROGRESS-DB] Updating progress (PID={pid}): {completed_samples}/{total_samples}")

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
            logger.info(f"🔒 [STRINGTIE-PROGRESS-DB] Using shared_db_lock for DB operations (PID={pid})")
            with shared_db_lock:
                # 기존 progress_detail 가져오기
                existing_data = {}
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    result = cursor.execute('''
                        SELECT progress_detail FROM pipeline_job_steps
                        WHERE workbench_id = ? AND tool_name = 'stringtie'
                    ''', (workbench_id,)).fetchone()

                    if result and result[0]:
                        try:
                            existing_data = json.loads(result[0])
                            logger.debug(f"📄 [STRINGTIE-PROGRESS-DB] Loaded existing progress_detail (PID={pid})")
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.warning(f"⚠️ [STRINGTIE-PROGRESS-DB] Failed to parse existing progress_detail, initializing new (PID={pid}): {e}")
                            existing_data = {"summary": {}, "results": {}}
                    else:
                        logger.info(f"ℹ️ [STRINGTIE-PROGRESS-DB] No existing progress_detail found, initializing new structure (PID={pid})")
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

                logger.info(f"📈 [STRINGTIE-PROGRESS-DB] Updated summary (PID={pid}): {completed_samples}/{total_samples} ({progress_percent:.1f}%)")

                # JSON 직렬화
                json_str = json.dumps(existing_data)
                logger.info(f"📄 [STRINGTIE-PROGRESS-DB] JSON content being saved (PID={pid}): {json_str}")

                # DB 업데이트 (같은 lock 블록 내에서 처리)
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE pipeline_job_steps
                        SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE workbench_id = ? AND tool_name = 'stringtie'
                    ''', (json_str, workbench_id))

                    rows_affected = cursor.rowcount
                    logger.info(f"📊 [STRINGTIE-PROGRESS-DB] Database update affected {rows_affected} row(s) (PID={pid})")

                    if rows_affected == 0:
                        logger.warning(f"⚠️ [STRINGTIE-PROGRESS-DB] No rows were updated - pipeline step may not exist for workbench {workbench_id} (PID={pid})")
                        return False

                    conn.commit()
                    logger.info(f"✅ [STRINGTIE-PROGRESS-DB] Database transaction committed successfully (PID={pid})")
        else:
            logger.error(f"❌ [STRINGTIE-PROGRESS-DB] No shared_db_lock provided - this should not happen in multiprocessing! (PID={pid})")
            return False

        return True

    except Exception as e:
        logger.error(f"❌ [STRINGTIE-PROGRESS-DB] Database update failed (PID={pid}): {e}")
        return False
