"""
edgeR 차등발현분석 모듈

Trinity의 run_DE_analysis.pl 스크립트를 사용한 edgeR 기반 차등발현분석을 수행합니다.
"""

import json
import sqlite3
import subprocess
import os
import time
from typing import Dict
import logging
from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema

# ✅ ProcessWrapper import 추가
from backend.pipeline.utils.process_wrapper import ProcessWrapper

# DEA 분석 함수 import
from backend.pipeline.utils.de_analysis import run_dea

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def cleanup_edger_temp_files(*file_paths):
    """EdgeR 임시 파일들 정리"""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                if os.path.isdir(file_path):
                    import shutil
                    shutil.rmtree(file_path)
                    logger.info(f"🗑️ [EDGER-CLEANUP] Removed temp directory: {os.path.basename(file_path)}")
                else:
                    os.remove(file_path)
                    logger.info(f"🗑️ [EDGER-CLEANUP] Removed temp file: {os.path.basename(file_path)}")
            except Exception as e:
                logger.warning(f"⚠️ [EDGER-CLEANUP] Failed to remove {file_path}: {e}")


def _count_replicates_per_group(samples_file: str) -> Dict[str, int]:
    """samples.txt 파일에서 각 그룹별 replicate 개수 계산
    
    Args:
        samples_file: samples.txt 파일 경로
        
    Returns:
        Dict[str, int]: 그룹명 -> replicate 개수 매핑
    """
    group_counts = {}
    
    try:
        with open(samples_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):  # 주석 제외
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        group_name = parts[0]
                        if group_name in group_counts:
                            group_counts[group_name] += 1
                        else:
                            group_counts[group_name] = 1
        
        logger.info(f"📊 [REPLICATE-COUNT] Parsed {samples_file}:")
        for group, count in group_counts.items():
            logger.info(f"   ├─ {group}: {count} samples")
            
    except Exception as e:
        logger.error(f"❌ [REPLICATE-COUNT] Failed to parse samples file: {e}")
        logger.error(f"   └─ File: {samples_file}")
        
    return group_counts


def _create_samples_file(samples_dir: str, workbench_id: int) -> str:
    """Trinity DEG 분석을 위한 samples.txt 파일 생성
    
    Args:
        samples_dir: samples 디렉토리 경로
        workbench_id: 워크벤치 ID
        
    Returns:
        생성된 samples.txt 파일의 전체 경로
        
    Format:
        group_name<tab>sample_name
        예: C13	C13-1-Rep1
    """
    try:
        logger.info(f"📝 [DEG-SAMPLES] Creating samples file")
        logger.info(f"   ├─ Samples directory: {samples_dir}")
        logger.info(f"   └─ Workbench ID: {workbench_id}")
        
        # samples.txt 파일 경로
        samples_file = os.path.join(samples_dir, "samples.txt")
        
        # vizr_pipeline_samples 테이블에서 데이터 조회
        with database.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT samples, layout 
                FROM vizr_pipeline_samples 
                WHERE workbench_id = ?
            """, (workbench_id,))
            pipeline_samples_result = cursor.fetchone()
            
            if not pipeline_samples_result:
                raise ValueError(f"No samples data found for workbench_id: {workbench_id}")
            
            samples_json = pipeline_samples_result['samples']
            layout = pipeline_samples_result['layout']
            
            logger.info(f"📊 [DEG-SAMPLES] Retrieved samples from vizr_pipeline_samples (layout: {layout})")
            
            try:
                # JSON 파싱
                samples_data = json.loads(samples_json)
                logger.info(f"✅ [DEG-SAMPLES] Parsed {len(samples_data)} samples from JSON")
                
                # samples.txt 파일 생성
                os.makedirs(samples_dir, exist_ok=True)
                
                with open(samples_file, 'w') as f:
                    for sample in samples_data:
                        group_name = sample.get('groupName', '')
                        sample_name = sample.get('sampleName', '')
                        
                        if not group_name or not sample_name:
                            logger.warning(f"⚠️ [DEG-SAMPLES] Missing group or sample name: {sample}")
                            continue
                        
                        # Trinity format: group_name<tab>sample_name
                        f.write(f"{group_name}\t{sample_name}\n")
                        logger.debug(f"   ├─ Added: {group_name} -> {sample_name}")
                
                logger.info(f"✅ [DEG-SAMPLES] Created samples file: {samples_file}")
                return samples_file
                
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse samples JSON: {e}")
                
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ [DEG-SAMPLES] Failed to create samples file!")
        logger.error(f"   ├─ Error: {error_msg}")
        logger.error(f"   └─ Samples directory: {samples_dir}")
        raise


def execute_edger(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    """edgeR을 이용한 차등발현분석 (Trinity run_DE_analysis.pl 사용)
    
    Args:
        job_step: 작업 단계 정보 (SQLite Row 객체)
        
    Returns:
        Dict[str, str]: 실행 결과
    """
    try:
        start_time = time.time()
        
        # 기본 정보 추출
        step_id = job_step['step_id']
        job_id = job_step['job_id'] 
        workbench_id = job_step['workbench_id']
        
        logger.info(f"🧬 [EDGER] Starting edgeR differential expression analysis")
        logger.info(f"   ├─ Step ID: {step_id}")
        logger.info(f"   ├─ Job ID: {job_id}")
        logger.info(f"   ├─ Workbench ID: {workbench_id}")
        logger.info(f"   └─ Worker ID: {worker_id}")
        
        # ✅ ProcessWrapper 생성 및 cleanup 함수 등록
        wrapper = ProcessWrapper(worker_id)
        
        # 파라미터 파싱
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        logger.info(f"📊 [EDGER] Analysis parameters: {parameters}")
        
        # 워크벤치 스키마 조회
        with database.get_db_connection() as db_connection:
            cursor = db_connection.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()
        
        if not workbench:
            raise ValueError(f"Workbench {workbench_id} not found")
            
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        
        # 호스트 경로로 변환 (VizR 컨테이너 경로 → 호스트 경로)
        # SharedConfig의 HOST_VIZR_PATH를 사용하여 정확한 호스트 경로 변환
        from config.shared_config import SharedConfig
        host_workbench_root = workbench_schema["base"].replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        
        logger.info(f"🐳 [EDGER] Docker path mapping DEBUG:")
        logger.info(f"   ├─ Container path: {workbench_schema['base']}")
        logger.info(f"   ├─ Host VIZR_PATH from config.json: {SharedConfig.HOST_VIZR_PATH}")
        logger.info(f"   ├─ Host workbench path calculated: {host_workbench_root}")
        logger.info(f"   └─ Docker mount command will be: -v {host_workbench_root}:/data")
        
        # 1. 디렉토리 설정
        base_dir = workbench_schema["deg"]
        edger_dir = os.path.join(base_dir, "edgeR")
        os.makedirs(edger_dir, exist_ok=True)
        
        logger.info(f"📁 [EDGER] Directory setup:")
        logger.info(f"   ├─ Base directory: {base_dir}")
        logger.info(f"   └─ edgeR output: {edger_dir}")
        
        # ✅ EdgeR 임시 파일들 정리를 위한 cleanup 등록
        temp_files = [
            os.path.join(edger_dir, "tmp"),
            os.path.join(edger_dir, "Rplots.pdf"),
            os.path.join(edger_dir, ".Rhistory"),
            os.path.join(base_dir, "Rplots.pdf")
        ]
        
        wrapper.register_cleanup(cleanup_edger_temp_files, *temp_files)
        logger.info(f"🗑️ [EDGER] Registered cleanup for {len(temp_files)} temp files/directories")
        
        # 2. 입력 파일 경로 설정
        counts_matrix_file = os.path.join(workbench_schema["quanti"]["counts"], "genes.counts.matrix")
        
        # 3. samples.txt 파일 생성
        samples_dir = workbench_schema["quanti"]["samples"]
        samples_file = _create_samples_file(samples_dir, workbench_id)
        
        logger.info(f"📋 [EDGER] Input files:")
        logger.info(f"   ├─ Counts matrix: {counts_matrix_file}")
        logger.info(f"   └─ Samples file: {samples_file}")
        
        # 4. 입력 파일 존재 확인
        if not os.path.exists(counts_matrix_file):
            raise FileNotFoundError(f"Counts matrix file not found: {counts_matrix_file}")
        if not os.path.exists(samples_file):
            raise FileNotFoundError(f"Samples file not found: {samples_file}")
        
        # 5. Replicate 개수 확인 및 dispersion 파라미터 결정
        group_replicates = _count_replicates_per_group(samples_file)
        min_replicates = min(group_replicates.values()) if group_replicates else 0
        
        logger.info(f"📊 [EDGER] Replicate analysis:")
        for group, count in group_replicates.items():
            logger.info(f"   ├─ {group}: {count} replicates")
        logger.info(f"   └─ Minimum replicates per group: {min_replicates}")
        
        # dispersion 파라미터 결정
        dispersion_param = ""
        if min_replicates < 2:
            if min_replicates == 1:
                dispersion_value = "0.1"  # 보수적인 값 (각 그룹에 1개씩)
            else:
                dispersion_value = "0.4"  # 더 보수적인 값 (일부 그룹에 샘플 없음)
            dispersion_param = f" --dispersion {dispersion_value}"
            logger.info(f"⚠️  [EDGER] Insufficient replicates detected, adding dispersion parameter: {dispersion_value}")
        else:
            logger.info(f"✅ [EDGER] Sufficient replicates found, no dispersion parameter needed")
        
        # 6. Docker 명령어 구성 - run_DE_analysis.pl 사용 (상대 경로)
        logger.info(f"🐳 [EDGER] Preparing Trinity run_DE_analysis.pl command...")
        
        # 워크벤치 루트 디렉토리를 Docker에 마운트
        # Docker-in-Docker를 위해 실제 호스트 경로 사용
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_workbench_root}:/data",  # 호스트 실제 경로를 /data로 마운트
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            "cd /data && /usr/local/bin/Analysis/DifferentialExpression/run_DE_analysis.pl "
            "--matrix quanti/counts/genes.counts.matrix "
            "--method edgeR "
            "--samples_file quanti/samples/samples.txt "
            f"--output deg/edgeR{dispersion_param}"
        ]
        
        logger.info(f"🚀 [EDGER] Running Trinity edgeR analysis...")
        logger.info(f"   └─ Command: {' '.join(docker_cmd)}")
        
        # ✅ ProcessWrapper로 Trinity Docker 실행
        logger.info(f"🔧 [EDGER] Starting ProcessWrapper execution...")
        
        # ProcessWrapper로 프로세스 실행 (Stop 신호 체크 통합)
        # cwd 파라미터 제거 - Docker 볼륨 마운트로 경로 해결됨
        result = wrapper.run_command(docker_cmd)
        
        if result['stopped_by_user']:
            logger.info(f"🛑 [EDGER] EdgeR analysis stopped by user signal")
            return {
                'success': False,
                'error': 'EdgeR analysis stopped by user signal',
                'method': 'edgeR',
                'stopped_by_user': True,
                'execution_time': time.time() - start_time
            }
        
        execution_time = time.time() - start_time
        logger.info(f"⏱️  [EDGER] Trinity execution completed in {execution_time:.2f} seconds")
        logger.info(f"   ├─ Success: {result.get('success', False)}")
        logger.info(f"   └─ Execution time: {execution_time:.2f}s")
        
        # 7. 실행 결과 확인
        if not result.get('success', False):
            logger.error(f"❌ [EDGER] Trinity edgeR analysis failed!")
            logger.error(f"   ├─ Success: {result.get('success', False)}")
            logger.error(f"   ├─ STDOUT: {result.get('stdout', 'None')[:500]}...")
            logger.error(f"   └─ STDERR: {result.get('stderr', 'None')[:500]}...")
            
            return {
                'success': False,
                'error': f"Trinity edgeR failed: {result.get('stderr', 'Unknown error')}",
                'stdout': result.get('stdout', ''),
                'stderr': result.get('stderr', ''),
                'method': 'edgeR',
                'execution_time': execution_time
            }
        
        # 8. 출력 파일 확인
        expected_output_files = [
            "edgeR.DE_results",
            "edgeR.DE_results.MA_n_Volcano_plots.pdf",
            "edgeR.count_matrix.RData"
        ]
        
        output_files = []
        missing_files = []
        
        for filename in expected_output_files:
            output_path = os.path.join(edger_dir, filename)
            if os.path.exists(output_path):
                output_files.append(output_path)
                file_size = os.path.getsize(output_path)
                logger.info(f"✅ [EDGER] Generated: {filename} ({file_size:,} bytes)")
            else:
                missing_files.append(filename)
                logger.warning(f"⚠️ [EDGER] Missing: {filename}")
        
        # 9. 결과 요약
        logger.info(f"")
        logger.info(f"")
        logger.info(f"📊 [EDGER] ╔══════════════════════════════════════════════════════════════════╗")
        logger.info(f"📊 [EDGER] ║                    EDGER ANALYSIS SUMMARY                        ║")
        logger.info(f"📊 [EDGER] ╚══════════════════════════════════════════════════════════════════╝")
        logger.info(f"✅ [EDGER] edgeR analysis completed successfully!")
        logger.info(f"   ├─ Generated files: {len(output_files)}")
        logger.info(f"   ├─ Missing files: {len(missing_files)}")
        logger.info(f"   ├─ Output directory: {edger_dir}")
        logger.info(f"   ├─ Counts matrix: {counts_matrix_file}")
        logger.info(f"   ├─ Samples file: {samples_file}")
        logger.info(f"   └─ Execution time: {execution_time:.2f}s")

        # 10. DEA 후속 분석은 ExpressionMatrix 탭에서 on-demand로 실행됨
        # run_dea() 호출 제거 - API에서 사용자 요청 시 실행

        return {
            'success': True,
            'method': 'edgeR',
            'output_directory': edger_dir,
            'output_files': output_files,
            'missing_files': missing_files,
            'counts_matrix': counts_matrix_file,
            'samples_file': samples_file,
            'execution_time': execution_time,
            'stdout': result.get('stdout', ''),
            'stderr': result.get('stderr', '')
        }
        
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"❌ [EDGER] edgeR analysis failed!")
        logger.error(f"   ├─ Error: {error_msg}")
        logger.error(f"   └─ Execution time: {execution_time:.2f}s")
        
        return {
            'success': False,
            'error': error_msg,
            'method': 'edgeR',
            'execution_time': execution_time
        }


def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 edger tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering edger tool...")
    
    metadata = {
        'name': 'edger',
        'description': 'EdgeR differential expression analysis for Trinity',
        'version': '1.0.0',
        'supported_formats': ['.matrix', '.txt'],
        'requirements': ['Trinity', 'edgeR', 'R'],
        'parameters': {
            'padj_threshold': 0.05,
            'lfc_threshold': 1.0,
            'min_rowsum_counts': 2,
            'dispersion': 0.1
        }
    }
    
    return coordinator.register_tool('edger', execute_edger, metadata)

