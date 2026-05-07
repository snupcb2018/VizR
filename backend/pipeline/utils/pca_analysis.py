"""
PCA (Principal Component Analysis) 분석 유틸리티 모듈

Trinity의 PtR 스크립트를 사용하여 RNA-seq 데이터의 PCA 분석을 수행합니다.
"""

import json
import sqlite3
import subprocess
import os
import time
from typing import Dict
import logging
from pathlib import Path

from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.pipeline.utils.process_wrapper import ProcessWrapper
from config.shared_config import SharedConfig

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def _create_samples_file(samples_dir: str, workbench_id: int) -> str:
    """PCA 분석을 위한 samples.txt 파일 생성

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
        logger.info(f"📝 [PCA-SAMPLES] Creating samples file for PCA analysis")
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

            logger.info(f"📊 [PCA-SAMPLES] Retrieved samples from vizr_pipeline_samples (layout: {layout})")

            try:
                # JSON 파싱
                samples_data = json.loads(samples_json)
                logger.info(f"✅ [PCA-SAMPLES] Parsed {len(samples_data)} samples from JSON")

                # samples.txt 파일 생성
                os.makedirs(samples_dir, exist_ok=True)

                with open(samples_file, 'w') as f:
                    for sample in samples_data:
                        group_name = sample.get('groupName', '')
                        sample_name = sample.get('sampleName', '')

                        if not group_name or not sample_name:
                            logger.warning(f"⚠️ [PCA-SAMPLES] Missing group or sample name: {sample}")
                            continue

                        # Trinity format: group_name<tab>sample_name
                        f.write(f"{group_name}\t{sample_name}\n")
                        logger.debug(f"   ├─ Added: {group_name} -> {sample_name}")

                logger.info(f"✅ [PCA-SAMPLES] Created samples file: {samples_file}")
                return samples_file

            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse samples JSON: {e}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ [PCA-SAMPLES] Failed to create samples file!")
        logger.error(f"   ├─ Error: {error_msg}")
        logger.error(f"   └─ Samples directory: {samples_dir}")
        raise


def run_pca(counts_dir: str, count_matrix_file: str, workbench_id: int, worker_id: str = "worker") -> Dict[str, str]:
    """
    Trinity PtR 스크립트를 사용한 PCA 분석

    Args:
        counts_dir: 출력 디렉토리 경로
        count_matrix_file: count 매트릭스 파일 경로 (genes.counts.matrix)
        workbench_id: 워크벤치 ID
        worker_id: 워커 ID (프로세스 관리용)

    Returns:
        Dict[str, str]: 결과 정보
        {
            'success': True/False,
            'pca_output_dir': '/path/to/pca_output',
            'samples_file': '/path/to/samples.txt',
            'docker_output': 'PtR command output...',
            'output_files': [list of generated files]
        }
    """
    logger.info(f"🔬 [PCA] Starting PCA analysis...")
    logger.info(f"   ├─ Input count matrix: {count_matrix_file}")
    logger.info(f"   ├─ Output directory: {counts_dir}")
    logger.info(f"   └─ Workbench ID: {workbench_id}")

    try:
        # 1. 입력 파일 검증
        if not os.path.exists(count_matrix_file):
            raise FileNotFoundError(f"Count matrix file not found: {count_matrix_file}")

        # 2. samples 디렉토리 및 samples.txt 파일 생성
        samples_dir = os.path.join(counts_dir, "samples")
        samples_file = _create_samples_file(samples_dir, workbench_id)

        # 3. PCA 출력 디렉토리 설정
        pca_output_dir = os.path.join(counts_dir, "pca_results")
        os.makedirs(pca_output_dir, exist_ok=True)
        logger.info(f"📁 [PCA] Created PCA output directory: {pca_output_dir}")

        # 4. Docker 명령어 구성 - PtR 사용
        logger.info(f"🐳 [PCA] Preparing Trinity PtR command...")

        # 파일명 (docker 컨테이너 내에서 사용할 경로)
        matrix_filename = os.path.basename(count_matrix_file)

        # 호스트 경로로 변환 (VizR 컨테이너 경로 → 호스트 경로)
        host_counts_dir = counts_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        logger.info(f"🔄 [PCA] Path conversion: container→host")
        logger.info(f"   ├─ Container: {counts_dir}")
        logger.info(f"   └─ Host: {host_counts_dir}")

        # PtR 명령어 구성
        ptr_command = (
            f"cd /data && "
            f"/usr/local/bin/Analysis/DifferentialExpression/PtR "
            f"--matrix {matrix_filename} "
            f"--samples samples/samples.txt "
            f"--log2 "
            f"--min_rowSums 10 "
            f"--compare_replicates "
            f"--CPM "
            f"--sample_cor_matrix "
            f"--center_rows "
            f"--prin_comp 2"
        )

        # Docker 명령어
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_counts_dir}:/data",  # counts 디렉토리를 /data로 마운트
            "-w", "/data",  # working directory 설정
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            ptr_command
        ]

        logger.info(f"🚀 [PCA] Running Trinity PtR for PCA analysis...")
        logger.info(f"   └─ Command: {' '.join(docker_cmd)}")

        # 5. Trinity Docker 실행 with ProcessWrapper
        start_time = time.time()

        # ProcessWrapper 사용
        wrapper = ProcessWrapper(worker_id)

        logger.info(f"🚀 [PCA] Starting ProcessWrapper execution...")
        # ProcessWrapper로 프로세스 실행
        result = wrapper.run_command(docker_cmd, cwd=counts_dir)

        if result['stopped_by_user']:
            logger.info(f"🛑 [PCA] PCA analysis stopped by user signal")
            return {
                'success': False,
                'error': 'PCA analysis stopped by user signal',
                'stopped_by_user': True
            }

        execution_time = time.time() - start_time
        logger.info(f"⏱️  [PCA] Trinity PtR execution completed in {execution_time:.2f} seconds")
        logger.info(f"   ├─ Success: {result.get('success', False)}")
        logger.info(f"   └─ Execution time: {execution_time:.2f}s")

        # 6. 실행 결과 확인
        if not result.get('success', False):
            logger.error(f"❌ [PCA] Trinity PtR failed!")
            logger.error(f"   ├─ STDOUT: {result.get('stdout', 'None')[:500]}...")
            logger.error(f"   └─ STDERR: {result.get('stderr', 'None')[:500]}...")

            return {
                'success': False,
                'error': f"Trinity PtR failed: {result.get('stderr', 'Unknown error')}",
                'stdout': result.get('stdout', ''),
                'stderr': result.get('stderr', ''),
                'execution_time': execution_time
            }

        # 7. 생성된 출력 파일들 확인 및 이동
        output_files = []
        expected_outputs = [
            "genes.counts.matrix.minRow10.CPM.log2.centered.prcomp.principal_components",  # PC 좌표
            "genes.counts.matrix.minRow10.CPM.log2.centered.prcomp.pdf",  # PCA plot
            "genes.counts.matrix.minRow10.CPM.log2.sample_cor_matrix.pdf",  # 상관관계 매트릭스 히트맵
            "genes.counts.matrix.minRow10.CPM.log2.sample_cor.dat",  # 상관관계 데이터
            "genes.counts.matrix.minRow10.CPM.log2.centered.prcomp.loadings",  # PC loadings
            "genes.counts.matrix.minRow10.rep_compare.pdf"  # Replicate comparison plot
        ]

        # PCA 관련 파일 패턴 추가 (실제 생성되는 파일들 기준)
        import glob
        pca_patterns = [
            "*.PCA.prcomp.*",           # PCA가 포함된 prcomp 파일들
            "*.prcomp.*",               # prcomp 파일들
            "*sample_cor*",             # 샘플 상관관계 파일들
            "*rep_compare*",            # Replicate 비교 파일들
            "*.CPM.log2.centered.*",    # CPM log2 centered 파일들
            "genes.counts.matrix.R"     # R 스크립트 파일
        ]

        # 패턴 매칭으로 모든 PCA 관련 파일 찾기
        all_pca_files = set()
        for pattern in pca_patterns:
            matched_files = glob.glob(os.path.join(counts_dir, pattern))
            all_pca_files.update(matched_files)

        logger.info(f"🔍 [PCA] Found {len(all_pca_files)} PCA-related files to move")

        # 8. PCA 결과 파일들을 pca_results 디렉토리로 이동
        import shutil
        moved_files = []

        for src_file in all_pca_files:
            if os.path.isfile(src_file):
                filename = os.path.basename(src_file)
                dest_file = os.path.join(pca_output_dir, filename)

                try:
                    # 파일 이동
                    shutil.move(src_file, dest_file)
                    file_size = os.path.getsize(dest_file)
                    moved_files.append(dest_file)
                    output_files.append(dest_file)
                    logger.info(f"✅ [PCA] Moved: {filename} ({file_size:,} bytes)")
                except Exception as e:
                    logger.warning(f"⚠️ [PCA] Failed to move {filename}: {e}")
                    # 이동 실패 시 원본 경로를 output_files에 추가
                    if os.path.exists(src_file):
                        output_files.append(src_file)

        # samples 디렉토리도 pca_results로 이동
        if os.path.exists(samples_dir):
            dest_samples_dir = os.path.join(pca_output_dir, "samples")
            try:
                if os.path.exists(dest_samples_dir):
                    shutil.rmtree(dest_samples_dir)  # 기존 디렉토리 제거
                shutil.move(samples_dir, dest_samples_dir)
                logger.info(f"✅ [PCA] Moved samples directory to {dest_samples_dir}")
                # samples_file 경로 업데이트
                samples_file = os.path.join(dest_samples_dir, "samples.txt")
            except Exception as e:
                logger.warning(f"⚠️ [PCA] Failed to move samples directory: {e}")

        logger.info(f"✅ [PCA] PCA analysis completed successfully!")
        logger.info(f"   ├─ Moved {len(moved_files)} files to: {pca_output_dir}")
        logger.info(f"   ├─ Total output files: {len(output_files)}")
        logger.info(f"   ├─ Execution time: {execution_time:.2f}s")
        logger.info(f"   └─ Samples file: {samples_file}")
        logger.info(f"📂 [PCA] All PCA results organized in: {pca_output_dir}")

        # 결과에 대한 요약 로그
        if result.get('stdout'):
            logger.info(f"📊 [PCA] Analysis output summary:")
            # stdout의 마지막 몇 줄 출력 (보통 요약 정보 포함)
            stdout_lines = result['stdout'].strip().split('\n')
            for line in stdout_lines[-10:]:  # 마지막 10줄
                if line.strip():
                    logger.info(f"   │ {line}")

        return {
            'success': True,
            'pca_output_dir': pca_output_dir,
            'samples_file': samples_file,
            'docker_output': result.get('stdout', ''),
            'execution_time': execution_time,
            'output_files': output_files
        }

    except subprocess.TimeoutExpired:
        logger.error(f"❌ [PCA] Trinity PtR analysis timed out after 10 minutes")
        return {
            'success': False,
            'error': 'Trinity PtR analysis timed out after 10 minutes',
            'execution_time': 600
        }

    except Exception as e:
        logger.error(f"❌ [PCA] PCA analysis failed: {str(e)}")
        logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'execution_time': time.time() - start_time if 'start_time' in locals() else 0
        }