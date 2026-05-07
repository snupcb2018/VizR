"""
Differential Expression Analysis 유틸리티 모듈

Trinity의 analyze_diff_expr.pl 스크립트를 사용하여 차등발현 분석 결과의 후속 분석을 수행합니다.
run_DE_analysis.pl의 출력을 입력으로 받아 클러스터링, 히트맵 등을 생성합니다.
"""

import os
import time
import shutil
import glob
from typing import Dict
import logging

from backend.pipeline.utils.process_wrapper import ProcessWrapper
from config.shared_config import SharedConfig

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def run_dea(
    workbench_root: str,
    output_dir: str,
    tmm_matrix_file: str,
    samples_file: str,
    workbench_id: int,
    worker_id: str = "worker",
    max_genes: int = 30000,
    p_value: float = 0.01,
    fold_change: float = 2.0
) -> Dict[str, str]:
    """
    Trinity analyze_diff_expr.pl을 사용한 차등발현 분석 후속 처리

    run_DE_analysis.pl 실행 후 추가 분석 수행 (클러스터링, 히트맵 등)

    Args:
        workbench_root: 워크벤치 루트 디렉토리 경로
        output_dir: 출력 디렉토리 경로 (deg/edgeR)
        tmm_matrix_file: TMM normalized matrix 파일 절대 경로 (genes.TMM.matrix)
        samples_file: samples.txt 파일 절대 경로
        workbench_id: 워크벤치 ID
        worker_id: 워커 ID (프로세스 관리용)
        max_genes: 클러스터링에 사용할 최대 유전자 수 (기본값: 30000)
        p_value: p-value cutoff (기본값: 0.01)
        fold_change: fold change cutoff in log2 scale (기본값: 2.0)

    Returns:
        Dict[str, str]: 결과 정보
        {
            'success': True/False,
            'dea_output_dir': '/path/to/dea_output',
            'docker_output': 'analyze_diff_expr.pl command output...',
            'output_files': [list of generated files]
        }
    """
    logger.info(f"🔬 [DEA] Starting differential expression follow-up analysis...")
    logger.info(f"   ├─ Workbench root: {workbench_root}")
    logger.info(f"   ├─ Input TMM matrix: {tmm_matrix_file}")
    logger.info(f"   ├─ Samples file: {samples_file}")
    logger.info(f"   ├─ Output directory: {output_dir}")
    logger.info(f"   ├─ Workbench ID: {workbench_id}")
    logger.info(f"   ├─ Max genes: {max_genes}")
    logger.info(f"   ├─ P-value cutoff: {p_value}")
    logger.info(f"   └─ Fold change cutoff (log2): {fold_change}")

    try:
        # 1. 입력 파일 검증
        if not os.path.exists(tmm_matrix_file):
            raise FileNotFoundError(f"TMM matrix file not found: {tmm_matrix_file}")

        if not os.path.exists(samples_file):
            raise FileNotFoundError(f"Samples file not found: {samples_file}")

        # 2. DEA 출력 디렉토리 설정 (deg/edgeR - 현재 디렉토리에 바로 생성)
        dea_output_dir = output_dir
        logger.info(f"📁 [DEA] DEA output directory: {dea_output_dir}")

        # 3. 절대 경로를 workbench root 기준 상대 경로로 변환
        matrix_relative_path = os.path.relpath(tmm_matrix_file, workbench_root)
        samples_relative_path = os.path.relpath(samples_file, workbench_root)
        output_relative_path = os.path.relpath(output_dir, workbench_root)

        logger.info(f"🔄 [DEA] Path conversion to relative paths:")
        logger.info(f"   ├─ TMM matrix: {matrix_relative_path}")
        logger.info(f"   ├─ Samples: {samples_relative_path}")
        logger.info(f"   └─ Output: {output_relative_path}")

        # 4. 호스트 경로로 변환 (VizR 컨테이너 경로 → 호스트 경로)
        host_workbench_root = workbench_root.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        logger.info(f"🔄 [DEA] Workbench root path conversion:")
        logger.info(f"   ├─ Container: {workbench_root}")
        logger.info(f"   └─ Host: {host_workbench_root}")

        # 5. Docker 명령어 구성 - analyze_diff_expr.pl 사용
        logger.info(f"🐳 [DEA] Preparing Trinity analyze_diff_expr.pl command...")

        # analyze_diff_expr.pl 명령어 구성
        analyze_command = (
            f"cd /data/{output_relative_path} && "
            f"/usr/local/bin/Analysis/DifferentialExpression/analyze_diff_expr.pl "
            f"--max_genes_clust {max_genes} "
            f"--matrix /data/{matrix_relative_path} "
            f"--samples /data/{samples_relative_path} "
            f"-P {p_value} "
            f"-C {fold_change}"
        )

        # Docker 명령어
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_workbench_root}:/data",  # workbench root를 /data로 마운트
            "-w", "/data",  # working directory를 workbench root로 설정
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            analyze_command
        ]

        logger.info(f"🚀 [DEA] Running Trinity analyze_diff_expr.pl for DE follow-up analysis...")
        logger.info(f"   └─ Command: {' '.join(docker_cmd)}")

        # 6. Trinity Docker 실행 with ProcessWrapper
        start_time = time.time()

        # ProcessWrapper 사용
        wrapper = ProcessWrapper(worker_id)

        logger.info(f"🚀 [DEA] Starting ProcessWrapper execution...")
        # ProcessWrapper로 프로세스 실행
        result = wrapper.run_command(docker_cmd, cwd=output_dir)

        if result['stopped_by_user']:
            logger.info(f"🛑 [DEA] DE analysis stopped by user signal")
            return {
                'success': False,
                'error': 'DE analysis stopped by user signal',
                'stopped_by_user': True
            }

        execution_time = time.time() - start_time
        logger.info(f"⏱️  [DEA] Trinity analyze_diff_expr.pl execution completed in {execution_time:.2f} seconds")
        logger.info(f"   ├─ Success: {result.get('success', False)}")
        logger.info(f"   └─ Execution time: {execution_time:.2f}s")

        # 5. 실행 결과 확인
        if not result.get('success', False):
            logger.error(f"❌ [DEA] Trinity analyze_diff_expr.pl failed!")
            logger.error(f"   ├─ STDOUT: {result.get('stdout', 'None')[:500]}...")
            logger.error(f"   └─ STDERR: {result.get('stderr', 'None')[:500]}...")

            return {
                'success': False,
                'error': f"Trinity analyze_diff_expr.pl failed: {result.get('stderr', 'Unknown error')}",
                'stdout': result.get('stdout', ''),
                'stderr': result.get('stderr', ''),
                'execution_time': execution_time
            }

        # 7. 생성된 출력 파일들 확인 (deg/edgeR 디렉토리)
        output_files = []

        # DEA 관련 파일 패턴 (analyze_diff_expr.pl이 생성하는 파일들)
        dea_patterns = [
            "*.gene_clusters.*",           # 클러스터 파일들
            "*diffExpr.*.matrix",          # 차등발현 매트릭스
            "*diffExpr.*.heatmap.*",       # 히트맵 파일들
            "*diffExpr.*.clusters_fixed_*", # 클러스터 고정 파일들
            "*.log2.*",                    # log2 변환 파일들
            "*.subset",                    # subset 파일들
            "*.R",                         # R 스크립트 파일들
        ]

        # 패턴 매칭으로 모든 DEA 관련 파일 찾기
        all_dea_files = set()
        for pattern in dea_patterns:
            matched_files = glob.glob(os.path.join(dea_output_dir, pattern))
            all_dea_files.update(matched_files)

        logger.info(f"🔍 [DEA] Found {len(all_dea_files)} DEA-related files")

        # 8. 생성된 파일 정보 수집
        for dea_file in all_dea_files:
            if os.path.isfile(dea_file):
                filename = os.path.basename(dea_file)
                file_size = os.path.getsize(dea_file)
                output_files.append(dea_file)
                logger.info(f"✅ [DEA] Generated: {filename} ({file_size:,} bytes)")

        logger.info(f"✅ [DEA] DE follow-up analysis completed successfully!")
        logger.info(f"   ├─ Generated files: {len(output_files)}")
        logger.info(f"   ├─ Output directory: {dea_output_dir}")
        logger.info(f"   └─ Execution time: {execution_time:.2f}s")
        logger.info(f"📂 [DEA] All DEA results organized in: {dea_output_dir}")

        # 결과에 대한 요약 로그
        if result.get('stdout'):
            logger.info(f"📊 [DEA] Analysis output summary:")
            # stdout의 마지막 몇 줄 출력 (보통 요약 정보 포함)
            stdout_lines = result['stdout'].strip().split('\n')
            for line in stdout_lines[-10:]:  # 마지막 10줄
                if line.strip():
                    logger.info(f"   │ {line}")

        return {
            'success': True,
            'dea_output_dir': dea_output_dir,
            'samples_file': samples_file,
            'docker_output': result.get('stdout', ''),
            'execution_time': execution_time,
            'output_files': output_files
        }

    except Exception as e:
        logger.error(f"❌ [DEA] DE follow-up analysis failed: {str(e)}")
        logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'execution_time': time.time() - start_time if 'start_time' in locals() else 0
        }
