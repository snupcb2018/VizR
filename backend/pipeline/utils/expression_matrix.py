"""
Expression Matrix 처리 유틸리티 모듈

StringTie 후처리를 위한 발현량 매트릭스 생성 및 정규화 기능
- PrepDE: Count matrix 생성
- TPM: Transcripts Per Million matrix 생성
- TMM: Trimmed Mean of M-values normalization
"""

import json
import sqlite3
import subprocess
import os
import time
from typing import Dict, List, Any, Tuple
import logging
from pathlib import Path
import pandas as pd
import csv
import re
from collections import defaultdict
from math import ceil

from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.pipeline.utils.process_wrapper import ProcessWrapper
from config.shared_config import SharedConfig

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


# ============================================================================
# RSEM Matrix Integration Functions
# ============================================================================

def collect_rsem_samples(alignment_dir: str, sample_info_list: List[Dict]) -> List[Tuple[str, str]]:
    """
    Bowtie+RSEM 출력 디렉토리에서 RSEM.genes.results 파일들을 수집

    Args:
        alignment_dir: alignment 디렉토리 경로 (/path/to/alignment/bowtie or bowtie2)
        sample_info_list: 샘플 정보 리스트

    Returns:
        List[Tuple[str, str]]: [(sample_name, rsem_file_path), ...]
    """
    samples = []
    alignment_path = Path(alignment_dir)

    for sample_info in sample_info_list:
        sample_name = sample_info["sample_name"]
        group_name = sample_info.get("group_name") or sample_info.get("condition")

        # RSEM 파일 경로: alignment/bowtie/{group_name}/{sample_name}/RSEM.genes.results
        rsem_filename = "RSEM.genes.results"
        rsem_path = alignment_path / group_name / sample_name / rsem_filename

        if rsem_path.exists():
            samples.append((sample_name, str(rsem_path)))
            logger.info(f"   ✅ Found RSEM file: {sample_name}")
        else:
            logger.warning(f"⚠️ [RSEM-COLLECT] RSEM file not found: {rsem_path}")

    return samples


def run_rsem_matrix_integration(
    alignment_dir: str,
    sample_info_list: List[Dict],
    workbench_id: int,
    worker_id: str = "rsem_matrix"
) -> Dict[str, Any]:
    """
    RSEM 결과를 매트릭스로 통합

    Trinity의 abundance_estimates_to_matrix.pl 스크립트 사용

    Args:
        alignment_dir: Bowtie+RSEM 출력 디렉토리 경로 (/path/to/alignment/bowtie)
        sample_info_list: 샘플 정보 리스트
        workbench_id: 워크벤치 ID
        worker_id: 워커 ID (로깅용)

    Returns:
        Dict[str, Any]: 결과 정보
        {
            'success': True/False,
            'matrix_file': 'path/to/genes.counts.matrix',
            'tpm_file': 'path/to/genes.TPM.not_cross_norm',
            'tmm_file': 'path/to/genes.TMM.EXPR.matrix',
            'processed_samples': int
        }
    """
    logger.info(f"🔬 [RSEM-MATRIX] Starting RSEM matrix integration...")
    logger.info(f"   ├─ Alignment directory: {alignment_dir}")
    logger.info(f"   ├─ Sample count: {len(sample_info_list)}")
    logger.info(f"   └─ Workbench ID: {workbench_id}")

    try:
        # 1. RSEM 파일 수집
        logger.info(f"📁 [RSEM-MATRIX] Collecting RSEM.genes.results files...")
        samples = collect_rsem_samples(alignment_dir, sample_info_list)

        if not samples:
            logger.error(f"❌ [RSEM-MATRIX] No RSEM.genes.results files found")
            raise RuntimeError("No RSEM.genes.results files found for matrix integration")

        logger.info(f"✅ [RSEM-MATRIX] Found {len(samples)} RSEM files:")
        for i, (sample_name, rsem_path) in enumerate(samples, 1):
            logger.info(f"   {i}. {sample_name}: {rsem_path}")

        # 2. quant_files.list 생성 (Trinity 입력용)
        logger.info(f"📝 [RSEM-MATRIX] Creating quant_files.list for Trinity...")
        quant_files_list = os.path.join(alignment_dir, "quant_files.list")

        with open(quant_files_list, 'w') as f:
            for sample_name, rsem_path in samples:
                # Trinity expects: path/to/RSEM.isoforms.results (--name_sample_by_basedir 옵션 사용)
                # RSEM.genes.results와 RSEM.isoforms.results 모두 같은 디렉토리에 있음
                isoforms_path = rsem_path.replace("RSEM.genes.results", "RSEM.isoforms.results")

                # Docker 컨테이너 내부 경로로 변환: alignment_dir 기준 상대 경로
                # /vizr/users/.../alignment/RH50/RH50-rep1/RSEM.isoforms.results
                # -> /alignment/RH50/RH50-rep1/RSEM.isoforms.results
                relative_path = os.path.relpath(isoforms_path, alignment_dir)
                container_path = f"/alignment/{relative_path}"

                # --name_sample_by_basedir 옵션: 경로만 작성 (샘플명은 디렉토리명에서 자동 추출)
                f.write(f"{container_path}\n")

        logger.info(f"   └─ Created: {quant_files_list}")

        # 3. 출력 디렉토리 설정 (counts 디렉토리 생성)
        # alignment/bowtie → counts로 변경

        # workbench 정보 조회
        with database.get_db_connection() as conn:
            workbench = conn.execute("""
                SELECT name, user_id FROM vizr_workbench
                WHERE id = ?
            """, (workbench_id,)).fetchone()

        if not workbench:
            raise ValueError(f"Workbench {workbench_id} not found")

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        counts_dir = workbench_schema["quanti"]["counts"]
        os.makedirs(counts_dir, exist_ok=True)

        logger.info(f"📂 [RSEM-MATRIX] Output directory: {counts_dir}")

        # 4. Trinity Docker 명령어 구성
        logger.info(f"🐳 [RSEM-MATRIX] Preparing Trinity abundance_estimates_to_matrix.pl command...")

        # 호스트 경로로 변환
        host_alignment_dir = alignment_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        host_counts_dir = counts_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)

        logger.info(f"🔄 [RSEM-MATRIX] Path conversion: container→host")
        logger.info(f"   ├─ Alignment: {alignment_dir} → {host_alignment_dir}")
        logger.info(f"   └─ Counts: {counts_dir} → {host_counts_dir}")

        # Docker 명령어
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_alignment_dir}:/alignment",  # RSEM 파일들이 있는 디렉토리
            "-v", f"{host_counts_dir}:/output",         # 출력 디렉토리
            "-w", "/output",                            # 작업 디렉토리
            SharedConfig.TRINITY_IMAGE,
            "/usr/local/bin/util/abundance_estimates_to_matrix.pl",
            "--est_method", "RSEM",
            "--quant_files", "/alignment/quant_files.list",
            "--gene_trans_map", "none",
            "--name_sample_by_basedir"
        ]

        logger.info(f"🚀 [RSEM-MATRIX] Running Trinity abundance_estimates_to_matrix.pl...")
        logger.info(f"   └─ Command: {' '.join(docker_cmd)}")

        # 5. Trinity Docker 실행 with ProcessWrapper
        start_time = time.time()

        wrapper = ProcessWrapper(worker_id)
        logger.info(f"🚀 [RSEM-MATRIX] Starting ProcessWrapper execution...")

        result = wrapper.run_command(docker_cmd, cwd=counts_dir)

        if result['stopped_by_user']:
            logger.info(f"🛑 [RSEM-MATRIX] RSEM matrix integration stopped by user signal")
            return {
                'success': False,
                'error': 'RSEM matrix integration stopped by user signal',
                'stopped_by_user': True
            }

        execution_time = time.time() - start_time
        logger.info(f"⏱️  [RSEM-MATRIX] Trinity execution completed in {execution_time:.2f} seconds")

        # 6. 실행 결과 확인
        if not result.get('success', False):
            logger.error(f"❌ [RSEM-MATRIX] Trinity abundance_estimates_to_matrix.pl failed!")
            logger.error(f"   ├─ STDOUT: {result.get('stdout', 'None')[:500]}...")
            logger.error(f"   └─ STDERR: {result.get('stderr', 'None')[:500]}...")

            return {
                'success': False,
                'error': f"Trinity abundance_estimates_to_matrix.pl failed: {result.get('stderr', 'Unknown error')}",
                'stdout': result.get('stdout', ''),
                'stderr': result.get('stderr', ''),
                'execution_time': execution_time
            }

        # 7. 출력 파일 검증
        logger.info(f"🔍 [RSEM-MATRIX] Verifying output files...")

        expected_files = {
            'matrix_file': os.path.join(counts_dir, "RSEM.gene.counts.matrix"),
            'tpm_file': os.path.join(counts_dir, "RSEM.gene.TPM.not_cross_norm"),
            'tmm_file': os.path.join(counts_dir, "RSEM.gene.TMM.EXPR.matrix")
        }

        # 실제로 생성된 파일명 확인 (Trinity는 prefix를 다르게 생성할 수 있음)
        created_files = [f for f in os.listdir(counts_dir) if f.endswith('.matrix') or 'TPM' in f or 'TMM' in f]
        logger.info(f"   └─ Created files: {created_files}")

        # RSEM은 아이소폼 레벨 매트릭스만 생성: RSEM.isoform.counts.matrix
        isoform_matrix_file = os.path.join(counts_dir, "RSEM.isoform.counts.matrix")
        standard_matrix_file = os.path.join(counts_dir, "genes.counts.matrix")

        if not os.path.exists(isoform_matrix_file):
            logger.error(f"❌ [RSEM-MATRIX] RSEM.isoform.counts.matrix not found in: {created_files}")
            raise FileNotFoundError(f"RSEM isoform matrix file not generated")

        # RSEM 아이소폼 매트릭스를 genes.counts.matrix로 복사 (DEG 분석 호환성)
        import shutil
        shutil.copy2(isoform_matrix_file, standard_matrix_file)
        logger.info(f"📋 [RSEM-MATRIX] Copied RSEM.isoform.counts.matrix to genes.counts.matrix")

        # 첫 줄에 gene_id 헤더 추가 (백엔드 호환성)
        with open(standard_matrix_file, 'r') as f:
            lines = f.readlines()

        if lines and not lines[0].strip().startswith('gene_id'):
            # 첫 줄 앞에 'gene_id' 추가
            lines[0] = 'gene_id' + lines[0]

            with open(standard_matrix_file, 'w') as f:
                f.writelines(lines)

            logger.info(f"   ├─ Added 'gene_id' header to first column")

        # 8. 결과 파일 정보 출력
        file_size = os.path.getsize(standard_matrix_file)
        logger.info(f"📊 [RSEM-MATRIX] Matrix file information:")
        logger.info(f"   ├─ File path: {standard_matrix_file}")
        logger.info(f"   └─ File size: {file_size:,} bytes")

        # 행 수 확인
        try:
            with open(standard_matrix_file, 'r') as f:
                line_count = sum(1 for line in f)
            logger.info(f"   ├─ Line count: {line_count:,} (including header)")

            # 첫 번째 행 확인 (헤더)
            with open(standard_matrix_file, 'r') as f:
                first_line = f.readline().strip()
            logger.info(f"   └─ Header: {first_line[:100]}...")

        except Exception as e:
            logger.warning(f"   └─ Could not analyze file: {str(e)}")

        # 9. 유전자 레벨 TMM 정규화 수행
        logger.info(f"🔬 [RSEM-MATRIX] Running TMM normalization on genes.counts.matrix...")

        # run_TMM_scale_matrix.pl은 stdout으로 결과를 출력하므로 파일로 리다이렉트
        tmm_output_file = os.path.join(counts_dir, "genes.TMM.matrix")

        tmm_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_counts_dir}:/output",
            "-w", "/output",
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            f"/usr/local/bin/util/support_scripts/run_TMM_scale_matrix.pl --matrix genes.counts.matrix > genes.TMM.matrix"
        ]

        logger.info(f"   └─ Command: docker run ... run_TMM_scale_matrix.pl --matrix genes.counts.matrix > genes.TMM.matrix")

        try:
            tmm_start = time.time()
            tmm_wrapper = ProcessWrapper(worker_id)
            tmm_result = tmm_wrapper.run_command(tmm_cmd, cwd=counts_dir)
            tmm_execution_time = time.time() - tmm_start

            if tmm_result.get('success'):
                logger.info(f"✅ [RSEM-MATRIX] TMM normalization completed in {tmm_execution_time:.2f}s")

                # genes.TMM.matrix 파일 확인 및 헤더 수정
                if os.path.exists(tmm_output_file):
                    # 첫 줄에 gene_id 헤더 추가 (백엔드 호환성)
                    with open(tmm_output_file, 'r') as f:
                        lines = f.readlines()

                    if lines and not lines[0].strip().startswith('gene_id'):
                        # 첫 줄 앞에 'gene_id' 추가
                        lines[0] = 'gene_id' + lines[0]

                        with open(tmm_output_file, 'w') as f:
                            f.writelines(lines)

                        logger.info(f"   ├─ Added 'gene_id' header to first column")

                    file_size = os.path.getsize(tmm_output_file)
                    logger.info(f"   └─ Created: genes.TMM.matrix ({file_size:,} bytes)")
                else:
                    logger.warning(f"⚠️ [RSEM-MATRIX] TMM matrix file not found: {tmm_output_file}")
            else:
                logger.error(f"❌ [RSEM-MATRIX] TMM normalization failed")
                logger.error(f"   └─ Error: {tmm_result.get('stderr', '')}")
        except Exception as e:
            logger.error(f"❌ [RSEM-MATRIX] Exception during TMM normalization: {str(e)}")

        # 10. 유전자 레벨 TPM 매트릭스 생성
        logger.info(f"📊 [RSEM-MATRIX] Generating TPM matrix from RSEM.genes.results...")

        try:
            import pandas as pd

            tpm_data = {}
            gene_order = None

            # 각 샘플의 RSEM.genes.results에서 TPM 추출
            # samples는 [(sample_name, rsem_file_path), ...] 형식
            for sample_name, rsem_file in samples:
                if not os.path.exists(rsem_file):
                    logger.warning(f"⚠️ [RSEM-MATRIX] RSEM.genes.results not found: {rsem_file}")
                    continue

                # gene_id와 TPM 컬럼만 읽기
                df = pd.read_csv(rsem_file, sep='\t', usecols=['gene_id', 'TPM'])

                if gene_order is None:
                    gene_order = df['gene_id'].tolist()

                tpm_data[sample_name] = df.set_index('gene_id')['TPM']
                logger.info(f"   ├─ Extracted TPM from {sample_name}: {len(df)} genes")

            if tpm_data:
                # TPM 데이터프레임 생성
                tpm_df = pd.DataFrame(tpm_data)
                tpm_df.index.name = 'gene_id'

                # genes.TPM.matrix로 저장
                tpm_output_file = os.path.join(counts_dir, "genes.TPM.matrix")
                tpm_df.to_csv(tpm_output_file, sep='\t')

                file_size = os.path.getsize(tpm_output_file)
                logger.info(f"✅ [RSEM-MATRIX] TPM matrix created successfully")
                logger.info(f"   ├─ Genes: {len(tpm_df)}")
                logger.info(f"   ├─ Samples: {len(tpm_df.columns)}")
                logger.info(f"   └─ File: genes.TPM.matrix ({file_size:,} bytes)")
            else:
                logger.warning(f"⚠️ [RSEM-MATRIX] No TPM data extracted from samples")

        except Exception as e:
            logger.error(f"❌ [RSEM-MATRIX] Exception during TPM matrix generation: {str(e)}")
            logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")

        logger.info(f"✅ [RSEM-MATRIX] RSEM matrix integration completed successfully!")
        logger.info(f"   ├─ Processed samples: {len(samples)}")
        logger.info(f"   ├─ Execution time: {execution_time:.2f}s")
        logger.info(f"   └─ Output: genes.counts.matrix, genes.TMM.matrix, genes.TPM.matrix")

        return {
            'success': True,
            'matrix_file': standard_matrix_file,
            'processed_samples': len(samples),
            'execution_time': execution_time,
            'file_size': file_size
        }

    except Exception as e:
        logger.error(f"❌ [RSEM-MATRIX] RSEM matrix integration failed: {str(e)}")
        logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'processed_samples': 0
        }


# ============================================================================
# PrepDE Count Matrix Generation Functions
# ============================================================================

def collect_gtf_samples(counts_dir: str, sample_info_list: List[Dict]) -> List[Tuple[str, str]]:
    """
    StringTie 출력 디렉토리에서 GTF 파일들을 수집

    Args:
        counts_dir: counts 디렉토리 경로 (/path/to/counts)
        sample_info_list: 샘플 정보 리스트

    Returns:
        List[Tuple[str, str]]: [(sample_name, gtf_file_path), ...]
    """
    samples = []
    counts_path = Path(counts_dir)

    for sample_info in sample_info_list:
        sample_name = sample_info["sample_name"]
        group_name = sample_info["group_name"]

        # GTF 파일 경로: counts/group/sample/{sample_name}_sorted.bam.gtf
        gtf_filename = f"{sample_name}_sorted.bam.gtf"
        gtf_path = counts_path / group_name / sample_name / gtf_filename

        if gtf_path.exists():
            samples.append((sample_name, str(gtf_path)))
        else:
            logger.warning(f"⚠️ [PREPDE] GTF file not found: {gtf_path}")

    # vizr_pipeline_samples 순서를 유지하기 위해 정렬하지 않음
    return samples


def parse_gene_info(gtf_line: str, ctg: str, tid: str) -> str:
    """GTF 라인에서 gene ID 추출 (gene_id만 반환, gene_name 제외)"""
    RE_GENE_ID = re.compile('gene_id "([^"]+)"')

    r = RE_GENE_ID.search(gtf_line)

    if r:
        return r.group(1).split("gene:")[-1]
    return tid


def get_coverage(gtf_line: str) -> float:
    """GTF 라인에서 coverage 값 추출"""
    RE_COVERAGE = re.compile('cov "([\-\+\d\.]+)"')
    r = RE_COVERAGE.search(gtf_line)
    if r:
        v = float(r.group(1))
        return max(v, 0.0)  # 음수면 0으로
    return 0.0


def process_gtf_file(gtf_path: str, sample_name: str, read_length: int = 75) -> Tuple[Dict, Dict]:
    """
    개별 GTF 파일을 처리하여 transcript와 gene count 계산

    Args:
        gtf_path: GTF 파일 경로
        sample_name: 샘플명
        read_length: 평균 read length

    Returns:
        Tuple[Dict, Dict]: (transcript_counts, gene_ids_mapping)
    """
    RE_TRANSCRIPT_ID = re.compile('transcript_id "([^"]+)"')

    transcript_counts = defaultdict(lambda: 0)
    gene_ids = {}

    with open(gtf_path, 'r') as f:
        transcript_len = 0
        t_id = None
        g_id = None
        coverage = 0.0

        for line_num, line in enumerate(f, 1):
            if line.startswith('#'):
                # StringTie -e 옵션 확인
                if line_num == 1 and '-e' not in line:
                    raise ValueError(f"GTF file {gtf_path} was not generated with -e option!")
                continue

            parts = line.strip().split('\t')
            if len(parts) < 9:
                continue

            if parts[2] == "transcript":
                # 이전 transcript 처리 완료
                if t_id and transcript_len > 0:
                    count = int(ceil(coverage * transcript_len / read_length))
                    transcript_counts[t_id] = count

                # 새 transcript 시작
                t_id = RE_TRANSCRIPT_ID.search(parts[8]).group(1)
                g_id = parse_gene_info(parts[8], parts[0], t_id)
                coverage = get_coverage(parts[8])
                transcript_len = 0
                gene_ids[t_id] = g_id

            elif parts[2] == "exon":
                # exon 길이 누적
                transcript_len += int(parts[4]) - int(parts[3]) + 1

        # 마지막 transcript 처리
        if t_id and transcript_len > 0:
            count = int(ceil(coverage * transcript_len / read_length))
            transcript_counts[t_id] = count

    return dict(transcript_counts), gene_ids


def run_prepde_analysis(counts_dir: str, sample_info_list: List[Dict], read_length: int = 75) -> Dict[str, str]:
    """
    StringTie 결과로부터 gene/transcript count 매트릭스 생성

    Args:
        counts_dir: StringTie 출력 디렉토리 경로
        sample_info_list: 샘플 정보 리스트
        read_length: 평균 read length (default: 75)

    Returns:
        Dict[str, str]: 결과 정보
        {
            'gene_matrix_file': 'path/to/gene_count_matrix.csv',
            'transcript_matrix_file': 'path/to/transcript_count_matrix.csv',
            'success': True,
            'processed_samples': 2
        }
    """
    logger.info(f"🔬 [PREPDE] Starting PrepDE analysis...")
    logger.info(f"   ├─ Counts directory: {counts_dir}")
    logger.info(f"   ├─ Sample count: {len(sample_info_list)}")
    logger.info(f"   └─ Read length: {read_length}")

    try:
        # 1. GTF 파일 수집
        logger.info(f"📁 [PREPDE] Collecting GTF files from StringTie output...")
        samples = collect_gtf_samples(counts_dir, sample_info_list)

        if not samples:
            logger.error(f"❌ [PREPDE] No GTF files found for PrepDE analysis")
            raise RuntimeError("No GTF files found for PrepDE analysis")

        logger.info(f"✅ [PREPDE] Found {len(samples)} GTF files:")
        for i, (sample_name, gtf_path) in enumerate(samples, 1):
            logger.info(f"   {i}. {sample_name}: {gtf_path}")

        # 2. 각 샘플 처리
        logger.info(f"🧬 [PREPDE] Processing GTF files for transcript/gene counts...")
        all_transcript_counts = defaultdict(lambda: defaultdict(lambda: 0))  # t_id -> sample -> count
        all_gene_ids = {}  # t_id -> g_id
        processed_samples = 0

        for sample_name, gtf_path in samples:
            logger.info(f"   🔄 Processing sample: {sample_name}")
            transcript_counts, gene_ids = process_gtf_file(gtf_path, sample_name, read_length)
            processed_samples += 1

            logger.info(f"      ├─ Transcripts found: {len(transcript_counts)}")
            logger.info(f"      └─ Genes mapped: {len(gene_ids)}")

            # transcript counts 저장
            for t_id, count in transcript_counts.items():
                all_transcript_counts[t_id][sample_name] = count

            # gene IDs 매핑 저장
            all_gene_ids.update(gene_ids)

        # 3. Gene counts 계산 (transcript counts 합산)
        logger.info(f"🔗 [PREPDE] Aggregating transcript counts into gene counts...")
        gene_counts = defaultdict(lambda: defaultdict(lambda: 0))  # g_id -> sample -> count

        for t_id, sample_counts in all_transcript_counts.items():
            g_id = all_gene_ids.get(t_id, t_id)  # gene ID가 없으면 transcript ID 사용
            for sample_name, count in sample_counts.items():
                gene_counts[g_id][sample_name] += count

        logger.info(f"   ├─ Total transcripts: {len(all_transcript_counts)}")
        logger.info(f"   └─ Unique genes: {len(gene_counts)}")

        # 4. 출력 파일 경로
        gene_matrix_file = os.path.join(counts_dir, "gene_count_matrix.csv")
        transcript_matrix_file = os.path.join(counts_dir, "transcript_count_matrix.csv")

        logger.info(f"📝 [PREPDE] Generating count matrices...")
        logger.info(f"   ├─ Transcript matrix: {transcript_matrix_file}")
        logger.info(f"   └─ Gene matrix: {gene_matrix_file}")

        # 5. Transcript count 매트릭스 생성
        logger.info(f"📊 [PREPDE] Writing transcript count matrix...")
        sample_names = [name for name, _ in samples]
        with open(transcript_matrix_file, 'w', newline='') as csvfile:
            fieldnames = ["transcript_id"] + sample_names
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            transcript_count = 0
            for t_id in sorted(all_transcript_counts.keys()):
                row = {"transcript_id": t_id}
                for sample_name in sample_names:
                    row[sample_name] = all_transcript_counts[t_id].get(sample_name, 0)
                writer.writerow(row)
                transcript_count += 1

        logger.info(f"   └─ Written {transcript_count} transcripts")

        # 6. Gene count 매트릭스 생성
        logger.info(f"📊 [PREPDE] Writing gene count matrix...")
        with open(gene_matrix_file, 'w', newline='') as csvfile:
            fieldnames = ["gene_id"] + sample_names
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            gene_count = 0
            for g_id in sorted(gene_counts.keys()):
                row = {"gene_id": g_id}
                for sample_name in sample_names:
                    row[sample_name] = gene_counts[g_id].get(sample_name, 0)
                writer.writerow(row)
                gene_count += 1

        logger.info(f"   └─ Written {gene_count} genes")

        # 7. Trinity DESeq2/EdgeR 호환을 위해 genes.counts.matrix 파일 생성
        # gene_count_matrix.csv를 TAB 구분자로 변환하여 genes.counts.matrix로 저장
        trinity_matrix_file = os.path.join(counts_dir, "genes.counts.matrix")
        logger.info(f"🔄 [PREPDE] Creating Trinity-compatible matrix file...")
        logger.info(f"   └─ Target: {trinity_matrix_file}")

        with open(gene_matrix_file, 'r') as csv_in, open(trinity_matrix_file, 'w') as tsv_out:
            reader = csv.reader(csv_in)
            for row in reader:
                tsv_out.write('\t'.join(row) + '\n')

        logger.info(f"✅ [PREPDE] Trinity-compatible matrix created")
        logger.info(f"   ├─ Format: TSV (tab-separated)")
        logger.info(f"   └─ Compatible with: Trinity DESeq2/EdgeR")

        logger.info(f"✅ [PREPDE] PrepDE analysis completed successfully!")
        logger.info(f"   ├─ Processed samples: {processed_samples}")
        logger.info(f"   ├─ Total transcripts: {len(all_transcript_counts)}")
        logger.info(f"   └─ Unique genes: {len(gene_counts)}")

        return {
            'gene_matrix_file': gene_matrix_file,
            'transcript_matrix_file': transcript_matrix_file,
            'trinity_matrix_file': trinity_matrix_file,
            'success': True,
            'processed_samples': len(samples)
        }

    except Exception as e:
        logger.error(f"❌ [PREPDE] PrepDE analysis failed: {str(e)}")
        logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'processed_samples': 0
        }


# ============================================================================
# TPM Matrix Generation Functions
# ============================================================================

def find_gene_abund_paths(counts_dir: str, sample_info_list: list) -> dict:
    """
    counts_dir: '/.../quanti/counts'
    sample_info_list: [sample_info dict, ...]
    return: {sample_name: Path(.../gene_abund.tab), ...}
    """
    counts_path = Path(counts_dir)
    mapping = {}

    for sample_info in sample_info_list:
        group = sample_info["group_name"]
        sample = sample_info["sample_name"]
        tab_path = counts_path / group / sample / "gene_abund.tab"
        mapping[sample] = tab_path
        if not tab_path.exists():
            print(f"[경고] 파일 없음: {tab_path}")

    return mapping


def load_tpm_table(sample_name: str, tab_path: Path, value_col: str = "TPM") -> pd.DataFrame:
    """
    gene_abund.tab에서 Gene ID와 TPM 컬럼만 읽어 샘플 단일 시리즈 형태로 반환
    - 같은 유전자가 중복되면 합산
    """
    df = pd.read_csv(tab_path, sep="\t")

    required = {"Gene ID", value_col}
    if not required.issubset(df.columns):
        raise ValueError(f"{tab_path}에 필수 컬럼 {required} 없음. 실제 컬럼: {list(df.columns)}")

    # gene: 접두어 제거
    df["Gene ID"] = df["Gene ID"].astype(str).str.replace(r"^gene:", "", regex=True)

    # 유전자별 합산 후 샘플명으로 컬럼명 지정
    sr = df.groupby("Gene ID", as_index=True)[value_col].sum().to_frame()
    sr.columns = [sample_name]
    sr.index.name = "GeneID"  # 인덱스 이름을 "GeneID"로 설정 (공백 제거)
    return sr


def build_tpm_matrix(counts_dir: str, sample_info_list: list, output: str = "genes.TPM.matrix") -> pd.DataFrame:
    """
    sample_info_list로 각 샘플의 gene_abund.tab를 찾아 TPM 매트릭스 생성
    - 없거나 형식이 맞지 않는 샘플은 건너뜀
    - 최종 파일: genes.TPM.matrix (탭 구분)
    """
    paths = find_gene_abund_paths(counts_dir, sample_info_list)

    dfs = []
    for sample, tab_path in paths.items():
        if not tab_path.exists():
            print(f"[SKIP] {sample}: 파일 없음")
            continue
        try:
            df = load_tpm_table(sample, tab_path, value_col="TPM")
            dfs.append(df)
        except Exception as e:
            print(f"[SKIP] {sample}: {e}")

    if not dfs:
        raise RuntimeError("처리 가능한 샘플이 없습니다.")

    # 유전자 기준 외부 결합, 결측치는 0으로
    matrix = pd.concat(dfs, axis=1, join="outer").fillna(0).reset_index()

    # 저장
    matrix.to_csv(output, sep="\t", index=False)
    print(f"[DONE] {output} 생성 완료 (샘플 수: {matrix.shape[1]-1}, 유전자 수: {matrix.shape[0]})")
    return matrix


# ============================================================================
# TMM Normalization Functions
# ============================================================================

def run_tmm_normalization(counts_dir: str, tpm_matrix_file: str) -> Dict[str, str]:
    """
    Trinity run_TMM_scale_matrix.pl 스크립트를 사용한 TMM 정규화
    기존 TPM 매트릭스에 TMM 정규화만 적용

    Args:
        counts_dir: 출력 디렉토리 경로
        tpm_matrix_file: TPM 매트릭스 파일 경로 (genes.TPM.matrix)

    Returns:
        Dict[str, str]: 결과 정보
        {
            'tmm_matrix_file': '/path/to/genes.TMM.matrix',
            'success': True,
            'docker_output': 'Trinity command output...'
        }
    """
    import inspect
    logger.info(f"🔧 [{inspect.currentframe().f_code.co_name}:{inspect.currentframe().f_lineno}] Starting TMM normalization...")
    logger.info(f"   ├─ Input TPM matrix: {tpm_matrix_file}")
    logger.info(f"   └─ Output directory: {counts_dir}")

    logger.info(
        "[TMM-NORM] marker=RUN_TMM_NORMALIZATION_CODE_V2026_03_13_01 input_matrix=%s output_dir=%s",
        tpm_matrix_file,
        counts_dir
    )
    try:
        # 1. 입력 파일 검증
        if not os.path.exists(tpm_matrix_file):
            raise FileNotFoundError(f"TPM matrix file not found: {tpm_matrix_file}")

        # 2. 출력 파일 경로 설정
        tmm_matrix_file = os.path.join(counts_dir, "genes.TMM.matrix")

        # 3. Docker 명령어 구성 - run_TMM_scale_matrix.pl 사용
        logger.info(f"🐳 [TMM-NORM] Preparing Trinity run_TMM_scale_matrix.pl command...")

        # TPM 매트릭스 파일명 (docker 컨테이너 내에서 사용할 경로)
        tpm_filename = os.path.basename(tpm_matrix_file)

        # 호스트 경로로 변환 (VizR 컨테이너 경로 → 호스트 경로)
        # SharedConfig의 HOST_VIZR_PATH를 사용하여 정확한 호스트 경로 변환
        host_counts_dir = counts_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        logger.info(f"🔄 [TMM-NORM] Path conversion: container→host")
        logger.info(f"🔄 [TMM-NORM] {SharedConfig.VIZR_PATH} → {SharedConfig.HOST_VIZR_PATH}")
        logger.info(f"🔄 [TMM-NORM] {counts_dir} → {host_counts_dir}")

        # Docker 명령어: run_TMM_scale_matrix.pl --matrix input > output
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_counts_dir}:/data",  # 호스트 경로를 /data로 마운트
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            f"/usr/local/bin/util/support_scripts/run_TMM_scale_matrix.pl --matrix /data/{tpm_filename} > /data/genes.TMM.matrix"
        ]

        logger.info(f"🚀 [TMM-NORM] Running Trinity TMM scale matrix...")
        logger.info(f"   └─ Command: {' '.join(docker_cmd)}")

        # 4. Trinity Docker 실행 with ProcessWrapper
        start_time = time.time()

        # ProcessWrapper 사용 (TMM normalization은 parent worker에서 실행)
        wrapper = ProcessWrapper("worker")  # TMM은 parent worker에서 실행

        logger.info(f"🚀 [TMM-NORM] Starting ProcessWrapper execution...")
        # ProcessWrapper로 프로세스 실행 (Stop 신호 체크 통합)
        result = wrapper.run_command(docker_cmd, cwd=counts_dir)

        if result['stopped_by_user']:
            logger.info(f"🛑 [TMM-NORM] TMM normalization stopped by user signal")
            return {
                'success': False,
                'error': 'TMM normalization stopped by user signal',
                'stopped_by_user': True
            }

        execution_time = time.time() - start_time
        logger.info(f"⏱️  [TMM-NORM] Trinity execution completed in {execution_time:.2f} seconds")
        logger.info(f"   ├─ Success: {result.get('success', False)}")
        logger.info(f"   └─ Execution time: {execution_time:.2f}s")

        # 5. 실행 결과 확인
        if not result.get('success', False):
            logger.error(f"❌ [TMM-NORM] Trinity TMM scale matrix failed!")
            logger.error(f"   ├─ Success: {result.get('success', False)}")
            logger.error(f"   ├─ STDOUT: {result.get('stdout', 'None')[:500]}...")
            logger.error(f"   └─ STDERR: {result.get('stderr', 'None')[:500]}...")

            return {
                'success': False,
                'error': f"Trinity run_TMM_scale_matrix.pl failed: {result.get('stderr', 'Unknown error')}",
                'stdout': result.get('stdout', ''),
                'stderr': result.get('stderr', ''),
                'execution_time': execution_time
            }

        # 6. 출력 파일 검증
        if not os.path.exists(tmm_matrix_file):
            logger.error(f"❌ [TMM-NORM] Expected output file not generated: {tmm_matrix_file}")

            # 디렉토리 내 생성된 파일들 확인
            created_files = [f for f in os.listdir(counts_dir) if f.endswith('.matrix')]
            logger.error(f"   └─ Files in directory: {created_files}")

            raise FileNotFoundError(f"TMM normalized matrix file not generated: {tmm_matrix_file}")

        # 7. 결과 파일 정보 확인
        file_size = os.path.getsize(tmm_matrix_file)
        logger.info(f"📊 [TMM-NORM] TMM matrix file information:")
        logger.info(f"   ├─ File path: {tmm_matrix_file}")
        logger.info(f"   ├─ File size: {file_size:,} bytes")

        # 행 수 확인
        try:
            with open(tmm_matrix_file, 'r') as f:
                line_count = sum(1 for line in f)
            logger.info(f"   ├─ Line count: {line_count:,} (including header)")

            # 첫 번째 행 확인 (헤더)
            with open(tmm_matrix_file, 'r') as f:
                first_line = f.readline().strip()
            logger.info(f"   └─ Header: {first_line[:100]}...")

        except Exception as e:
            logger.warning(f"   └─ Could not analyze file: {str(e)}")

        logger.info(f"✅ [TMM-NORM] TMM normalization completed successfully!")
        logger.info(f"   ├─ Script: run_TMM_scale_matrix.pl")
        logger.info(f"   ├─ Execution time: {execution_time:.2f}s")
        logger.info(f"   └─ Output: {os.path.basename(tmm_matrix_file)}")

        return {
            'tmm_matrix_file': tmm_matrix_file,
            'success': True,
            'docker_output': result.get('stdout', ''),
            'execution_time': execution_time,
            'file_size': file_size
        }

    except subprocess.TimeoutExpired:
        logger.error(f"❌ [TMM-NORM] Trinity TMM normalization timed out after 10 minutes")
        return {
            'success': False,
            'error': 'Trinity TMM normalization timed out after 10 minutes',
            'execution_time': 600
        }

    except Exception as e:
        logger.error(f"❌ [TMM-NORM] TMM normalization failed: {str(e)}")
        logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'execution_time': time.time() - start_time if 'start_time' in locals() else 0
        }


def run_tmm_normalization_from_counts(counts_dir: str, counts_matrix_file: str) -> Dict[str, str]:
    """
    Trinity run_TMM_scale_matrix.pl 스크립트를 사용한 counts 기반 TMM 정규화.
    counts-only matrix import 경로에서 사용한다.

    Args:
        counts_dir: 출력 디렉터리 경로
        counts_matrix_file: counts matrix 파일 경로 (genes.counts.matrix)

    Returns:
        Dict[str, str]: 결과 정보
    """
    logger.info("[TMM-NORM-COUNTS] marker=RUN_TMM_NORMALIZATION_FROM_COUNTS_CODE_V2026_03_13_01 input_matrix=%s output_dir=%s",
                counts_matrix_file, counts_dir)

    try:
        if not os.path.exists(counts_matrix_file):
            raise FileNotFoundError(f"Counts matrix file not found: {counts_matrix_file}")

        tmm_matrix_file = os.path.join(counts_dir, "genes.TMM.matrix")
        host_counts_dir = counts_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        counts_filename = os.path.basename(counts_matrix_file)

        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_counts_dir}:/data",
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            f"/usr/local/bin/util/support_scripts/run_TMM_scale_matrix.pl --matrix /data/{counts_filename} > /data/genes.TMM.matrix"
        ]

        logger.info("[TMM-NORM-COUNTS] Running Trinity TMM scale matrix from counts...")
        logger.info("   └─ Command: %s", " ".join(docker_cmd))

        start_time = time.time()
        wrapper = ProcessWrapper("worker")
        result = wrapper.run_command(docker_cmd, cwd=counts_dir)

        if result.get('stopped_by_user'):
            logger.info("[TMM-NORM-COUNTS] TMM normalization from counts stopped by user signal")
            return {
                'success': False,
                'error': 'TMM normalization from counts stopped by user signal',
                'stopped_by_user': True
            }

        execution_time = time.time() - start_time
        logger.info("[TMM-NORM-COUNTS] Trinity execution completed in %.2f seconds", execution_time)

        if not result.get('success', False):
            return {
                'success': False,
                'error': f"Trinity run_TMM_scale_matrix.pl failed: {result.get('stderr', 'Unknown error')}",
                'stdout': result.get('stdout', ''),
                'stderr': result.get('stderr', ''),
                'execution_time': execution_time
            }

        if not os.path.exists(tmm_matrix_file):
            raise FileNotFoundError(f"TMM normalized matrix file not generated: {tmm_matrix_file}")

        with open(tmm_matrix_file, 'r', encoding='utf-8') as handle:
            lines = handle.readlines()
        if lines and not lines[0].strip().startswith('gene_id'):
            lines[0] = 'gene_id' + lines[0]
            with open(tmm_matrix_file, 'w', encoding='utf-8') as handle:
                handle.writelines(lines)

        file_size = os.path.getsize(tmm_matrix_file)
        logger.info("[TMM-NORM-COUNTS] Counts-based TMM normalization completed successfully")
        logger.info("   ├─ Output: %s", tmm_matrix_file)
        logger.info("   ├─ Execution time: %.2fs", execution_time)
        logger.info("   └─ File size: %s bytes", f"{file_size:,}")

        return {
            'tmm_matrix_file': tmm_matrix_file,
            'success': True,
            'docker_output': result.get('stdout', ''),
            'execution_time': execution_time,
            'file_size': file_size
        }

    except Exception as e:
        logger.error(f"[TMM-NORM-COUNTS] Counts-based TMM normalization failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'execution_time': time.time() - start_time if 'start_time' in locals() else 0
        }


# ============================================================================
# Counts-native TMM Normalization Functions
# ============================================================================

def run_tmm_normalization_from_counts_native(counts_dir: str, counts_matrix_file: str) -> Dict[str, str]:
    """edgeR 기반 counts-native TMM matrix 생성."""
    logger.info(
        "[TMM-NORM-COUNTS] marker=RUN_TMM_NORMALIZATION_FROM_COUNTS_CODE_V2026_03_13_02 input_matrix=%s output_dir=%s",
        counts_matrix_file,
        counts_dir
    )

    try:
        if not os.path.exists(counts_matrix_file):
            raise FileNotFoundError(f"Counts matrix file not found: {counts_matrix_file}")

        tmm_matrix_file = os.path.join(counts_dir, "genes.TMM.matrix")
        host_counts_dir = counts_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        counts_filename = os.path.basename(counts_matrix_file)
        script_filename = "run_tmm_from_counts.native.R"
        script_path = os.path.join(counts_dir, script_filename)

        r_script = """#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(edgeR)
})

args <- commandArgs(trailingOnly = TRUE)
input_file <- NULL
output_file <- NULL
i <- 1
while (i <= length(args)) {
  if (args[i] == "--input") {
    input_file <- args[i + 1]
    i <- i + 2
  } else if (args[i] == "--output") {
    output_file <- args[i + 1]
    i <- i + 2
  } else {
    i <- i + 1
  }
}

if (is.null(input_file) || is.null(output_file)) {
  stop("Usage: Rscript run_tmm_from_counts.native.R --input <genes.counts.matrix> --output <genes.TMM.matrix>")
}

counts_df <- read.table(
  input_file,
  header = TRUE,
  sep = "\\t",
  check.names = FALSE,
  stringsAsFactors = FALSE,
  quote = "",
  comment.char = ""
)

if (ncol(counts_df) < 2) stop("Counts matrix must contain a gene_id column and at least one sample column")
first_col <- colnames(counts_df)[1]
if (!(first_col %in% c("gene_id", "GeneID"))) stop("First column must be gene_id or GeneID")

gene_ids <- as.character(counts_df[[1]])
if (any(is.na(gene_ids)) || any(trimws(gene_ids) == "")) stop("gene_id column contains blank values")
if (any(duplicated(gene_ids))) stop("gene_id column contains duplicate values")

sample_names <- colnames(counts_df)[-1]
if (any(duplicated(sample_names))) stop("Sample column names contain duplicate values")

count_matrix <- as.matrix(counts_df[, -1, drop = FALSE])
storage.mode(count_matrix) <- "numeric"
rownames(count_matrix) <- gene_ids

if (any(is.na(count_matrix))) stop("Counts matrix contains non-numeric or NA values")
if (any(count_matrix < 0)) stop("Counts matrix contains negative values")
if (any(colSums(count_matrix) == 0)) stop("At least one sample column has total count 0")

dge <- DGEList(counts = count_matrix)
dge <- calcNormFactors(dge, method = "TMM")
tmm_matrix <- cpm(dge, normalized.lib.sizes = TRUE, log = FALSE, prior.count = 0)

output_df <- data.frame(gene_id = rownames(tmm_matrix), tmm_matrix, check.names = FALSE)
write.table(output_df, file = output_file, sep = "\\t", quote = FALSE, row.names = FALSE, col.names = TRUE)
"""

        with open(script_path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(r_script)

        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_counts_dir}:/data",
            SharedConfig.TRINITY_IMAGE,
            "Rscript", f"/data/{script_filename}",
            "--input", f"/data/{counts_filename}",
            "--output", "/data/genes.TMM.matrix"
        ]

        logger.info("[TMM-NORM-COUNTS] Running edgeR-based counts TMM normalization...")
        logger.info("   Command: %s", " ".join(docker_cmd))

        start_time = time.time()
        wrapper = ProcessWrapper("worker")
        result = wrapper.run_command(docker_cmd, cwd=counts_dir)

        if result.get('stopped_by_user'):
            logger.info("[TMM-NORM-COUNTS] TMM normalization from counts stopped by user signal")
            return {
                'success': False,
                'error': 'TMM normalization from counts stopped by user signal',
                'stopped_by_user': True
            }

        execution_time = time.time() - start_time
        logger.info("[TMM-NORM-COUNTS] edgeR execution completed in %.2f seconds", execution_time)

        if not result.get('success', False):
            return {
                'success': False,
                'error': f"edgeR counts-based TMM normalization failed: {result.get('stderr', 'Unknown error')}",
                'stdout': result.get('stdout', ''),
                'stderr': result.get('stderr', ''),
                'execution_time': execution_time
            }

        if not os.path.exists(tmm_matrix_file):
            raise FileNotFoundError(f"TMM normalized matrix file not generated: {tmm_matrix_file}")

        file_size = os.path.getsize(tmm_matrix_file)
        if os.path.exists(script_path):
            os.remove(script_path)
        logger.info("[TMM-NORM-COUNTS] Counts-based TMM normalization completed successfully")
        logger.info("   Output: %s", tmm_matrix_file)
        logger.info("   Execution time: %.2fs", execution_time)
        logger.info("   File size: %s bytes", f"{file_size:,}")

        return {
            'tmm_matrix_file': tmm_matrix_file,
            'success': True,
            'docker_output': result.get('stdout', ''),
            'execution_time': execution_time,
            'file_size': file_size
        }

    except Exception as e:
        script_path = locals().get('script_path')
        if script_path and os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass
        logger.error(f"[TMM-NORM-COUNTS] Counts-based TMM normalization failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'execution_time': time.time() - start_time if 'start_time' in locals() else 0
        }


# ============================================================================
# Matrix Sample Order Reordering Functions
# ============================================================================

def reorder_matrix_samples(matrix_file: str, sample_order: List[str]) -> Dict[str, Any]:
    """
    매트릭스 파일의 샘플 컬럼 순서를 vizr_pipeline_samples 순서로 재정렬

    Args:
        matrix_file: 재정렬할 매트릭스 파일 경로 (TSV 형식)
        sample_order: vizr_pipeline_samples에서 가져온 샘플 순서 리스트

    Returns:
        Dict[str, Any]: 결과 정보
        {
            'success': True,
            'reordered_samples': 73,
            'missing_samples': [],
            'extra_samples': []
        }
    """
    logger.info(f"🔄 [REORDER] Reordering matrix samples to match vizr_pipeline_samples order...")
    logger.info(f"   ├─ Matrix file: {matrix_file}")
    logger.info(f"   └─ Expected sample order: {len(sample_order)} samples")

    try:
        # 1. 매트릭스 파일 로드
        df = pd.read_csv(matrix_file, sep='\t', index_col=0)
        original_columns = df.columns.tolist()

        logger.info(f"📖 [REORDER] Original matrix: {df.shape}")
        logger.info(f"   ├─ Genes: {len(df.index)}")
        logger.info(f"   └─ Samples: {len(original_columns)}")

        # 2. 샘플 순서 비교
        missing_samples = [s for s in sample_order if s not in original_columns]
        extra_samples = [s for s in original_columns if s not in sample_order]

        if missing_samples:
            logger.warning(f"⚠️ [REORDER] Missing samples in matrix: {missing_samples}")

        if extra_samples:
            logger.warning(f"⚠️ [REORDER] Extra samples in matrix (not in vizr_pipeline_samples): {extra_samples}")

        # 3. 새로운 컬럼 순서 생성 (sample_order 기준 + extra_samples 추가)
        new_column_order = [s for s in sample_order if s in original_columns]
        new_column_order.extend(extra_samples)

        logger.info(f"🔄 [REORDER] Reordering columns...")
        logger.info(f"   ├─ Original order: {original_columns[:5]}... (showing first 5)")
        logger.info(f"   └─ New order: {new_column_order[:5]}... (showing first 5)")

        # 4. 컬럼 순서 재정렬
        df_reordered = df[new_column_order]

        # 5. 파일 백업 (원본 보존)
        backup_file = matrix_file + ".original"
        if not os.path.exists(backup_file):
            import shutil
            shutil.copy2(matrix_file, backup_file)
            logger.info(f"💾 [REORDER] Original file backed up to: {backup_file}")

        # 6. 재정렬된 매트릭스 저장
        df_reordered.to_csv(matrix_file, sep='\t')

        logger.info(f"✅ [REORDER] Matrix samples reordered successfully!")
        logger.info(f"   ├─ Reordered samples: {len(new_column_order)}")
        logger.info(f"   ├─ Missing samples: {len(missing_samples)}")
        logger.info(f"   └─ Extra samples: {len(extra_samples)}")

        return {
            'success': True,
            'reordered_samples': len(new_column_order),
            'missing_samples': missing_samples,
            'extra_samples': extra_samples,
            'original_order': original_columns,
            'new_order': new_column_order
        }

    except Exception as e:
        logger.error(f"❌ [REORDER] Failed to reorder matrix samples: {str(e)}")
        logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'reordered_samples': 0,
            'missing_samples': [],
            'extra_samples': []
        }


# ============================================================================
# Matrix Preprocessing Functions
# ============================================================================

def run_matrix_preprocess(counts_dir: str, gene_matrix_file: str, tpm_matrix_file: str) -> Dict[str, str]:
    """
    Count 매트릭스와 TPM 매트릭스 후처리
    - CSV → TSV 변환 (edgeR/DESeq2 호환성)
    - Gene ID 정규화 (파이프 이후 제거)
    - 매트릭스 일치성 검증
    - 표준화된 출력 생성

    Args:
        counts_dir: 출력 디렉토리 경로
        gene_matrix_file: PrepDE gene count 매트릭스 파일 경로 (CSV)
        tpm_matrix_file: TPM 매트릭스 파일 경로 (TSV)

    Returns:
        Dict[str, str]: 결과 정보
        {
            'processed_counts_matrix': '/path/to/genes.counts.matrix',
            'validation_passed': True,
            'trimmed_genes': 1234,
            'original_genes': 1234,
            'success': True
        }
    """
    logger.info(f"🔧 [MATRIX-PREP] Starting matrix preprocessing...")
    logger.info(f"   ├─ Input counts (CSV): {gene_matrix_file}")
    logger.info(f"   ├─ Input TPM (TSV): {tpm_matrix_file}")
    logger.info(f"   └─ Output directory: {counts_dir}")

    try:
        # 1. Count 매트릭스 로드 (CSV 형식)
        logger.info(f"📖 [MATRIX-PREP] Loading count matrix...")
        if not os.path.exists(gene_matrix_file):
            raise FileNotFoundError(f"Gene count matrix file not found: {gene_matrix_file}")

        counts_df = pd.read_csv(gene_matrix_file, index_col=0)
        original_gene_count = len(counts_df.index)
        logger.info(f"   ├─ Loaded counts matrix: {counts_df.shape}")
        logger.info(f"   └─ Original genes: {original_gene_count}")

        # 2. TPM 매트릭스 로드 (TSV 형식)
        logger.info(f"📖 [MATRIX-PREP] Loading TPM matrix...")
        if not os.path.exists(tpm_matrix_file):
            raise FileNotFoundError(f"TPM matrix file not found: {tpm_matrix_file}")

        tpm_df = pd.read_csv(tpm_matrix_file, sep="\t", index_col=0)
        logger.info(f"   ├─ Loaded TPM matrix: {tpm_df.shape}")
        logger.info(f"   └─ TPM genes: {len(tpm_df.index)}")

        # 3. Gene ID 정규화 (파이프 이후 제거)
        logger.info(f"✂️ [MATRIX-PREP] Trimming gene IDs (removing suffix after '|')...")
        original_gene_ids = list(counts_df.index)
        trimmed_gene_ids = []
        trimmed_count = 0

        for gene_id in original_gene_ids:
            if "|" in str(gene_id):
                trimmed_id = str(gene_id).split("|")[0]
                trimmed_gene_ids.append(trimmed_id)
                trimmed_count += 1
            else:
                trimmed_gene_ids.append(str(gene_id))

        # Gene ID 업데이트
        counts_df.index = trimmed_gene_ids
        logger.info(f"   ├─ Trimmed gene IDs: {trimmed_count}/{original_gene_count}")
        logger.info(f"   └─ Final gene count: {len(counts_df.index)}")

        # 4. 매트릭스 일치성 검증
        logger.info(f"🔍 [MATRIX-PREP] Validating matrix consistency...")

        # TPM 매트릭스의 gene ID를 counts 매트릭스에서 찾을 수 있는지 확인
        try:
            counts_subset = counts_df.loc[tpm_df.index]
            counts_validation = counts_subset.shape[0] == len(tpm_df.index)
        except KeyError:
            counts_validation = False

        # Counts 매트릭스의 gene ID를 TPM 매트릭스에서 찾을 수 있는지 확인
        try:
            tpm_subset = tpm_df.loc[counts_df.index]
            tpm_validation = tpm_subset.shape[0] == len(counts_df.index)
        except KeyError:
            tpm_validation = False

        logger.info(f"   ├─ Counts matrix validation: {'✅ OK' if counts_validation else '❌ FAIL'}")
        logger.info(f"   └─ TPM matrix validation: {'✅ OK' if tpm_validation else '❌ FAIL'}")

        validation_passed = counts_validation and tpm_validation

        if not validation_passed:
            logger.warning(f"⚠️ [MATRIX-PREP] Matrix validation failed, but continuing...")
            logger.warning(f"   ├─ This may indicate gene ID mismatch between matrices")
            logger.warning(f"   └─ Check reference genome and annotation consistency")

        # 5. TSV 형식으로 저장
        output_file = os.path.join(counts_dir, "genes.counts.matrix")
        logger.info(f"💾 [MATRIX-PREP] Saving processed count matrix...")
        logger.info(f"   └─ Output file: {output_file}")

        counts_df.to_csv(output_file, sep="\t")

        logger.info(f"✅ [MATRIX-PREP] Matrix preprocessing completed successfully!")
        logger.info(f"   ├─ Original genes: {original_gene_count}")
        logger.info(f"   ├─ Trimmed gene IDs: {trimmed_count}")
        logger.info(f"   ├─ Final genes: {len(counts_df.index)}")
        logger.info(f"   ├─ Validation passed: {'Yes' if validation_passed else 'No'}")
        logger.info(f"   └─ Output: genes.counts.matrix (TSV format)")

        return {
            'processed_counts_matrix': output_file,
            'validation_passed': validation_passed,
            'trimmed_genes': trimmed_count,
            'original_genes': original_gene_count,
            'final_genes': len(counts_df.index),
            'success': True
        }

    except Exception as e:
        logger.error(f"❌ [MATRIX-PREP] Matrix preprocessing failed: {str(e)}")
        logger.error(f"   └─ Error details: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'trimmed_genes': 0,
            'original_genes': 0,
            'final_genes': 0,
            'validation_passed': False
        }
