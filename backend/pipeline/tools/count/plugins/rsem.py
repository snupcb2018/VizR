"""
RSEM 정량화 모듈
Bowtie/Bowtie2 alignment 단계에서 이미 quantification이 완료되었으므로
Count 단계에서는 결과 파일 확인만 수행
"""
import json
import os
import sqlite3
import logging
from typing import Dict
from datetime import datetime

from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def execute_rsem(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    """
    RSEM Count 실행 - alignment 단계에서 이미 quantification 완료
    결과 파일 확인만 수행
    """
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

        logger.info(f"🎯 [RSEM-COUNT] Starting RSEM count verification")
        logger.info(f"📋 [RSEM-COUNT] Job Configuration:")
        logger.info(f"   ├─ workbench_id: {workbench_id}")
        logger.info(f"   └─ step_id: {step_id}")

        # RSEM 결과 디렉토리 (alignment 단계에서 생성됨)
        alignment_dir = workbench_schema["quanti"]["alignment"]
        logger.info(f"📁 [RSEM-COUNT] Alignment directory: {alignment_dir}")

        # samples_data 구성
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
                logger.info(f"📊 [RSEM-COUNT] Retrieved samples from vizr_pipeline_samples (layout: {layout})")

                try:
                    samples_data = json.loads(samples_json)
                    logger.info(f"✅ [RSEM-COUNT] {len(samples_data)} samples")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ [RSEM-COUNT] Failed to parse samples JSON: {e}")
                    raise
            else:
                logger.warning(f"⚠️  [RSEM-COUNT] No samples found for workbench_id: {workbench_id}")
                samples_data = []

        logger.info(f"📊 [RSEM-COUNT] Total samples: {len(samples_data)}")

        # 각 샘플의 RSEM 결과 파일 확인
        missing_files = []
        found_files = []

        for sample_data in samples_data:
            sample_name = sample_data['sampleName']
            group_name = sample_data['groupName']

            # RSEM 출력 파일 경로
            sample_alignment_dir = os.path.join(alignment_dir, group_name, sample_name)

            # RSEM 결과 파일들
            expected_files = [
                os.path.join(sample_alignment_dir, "RSEM.genes.results"),
                os.path.join(sample_alignment_dir, "RSEM.isoforms.results")
            ]

            for result_file in expected_files:
                if os.path.exists(result_file):
                    file_size = os.path.getsize(result_file)
                    found_files.append(result_file)
                    logger.info(f"✅ [RSEM-COUNT] Found: {os.path.basename(result_file)} ({file_size:,} bytes)")
                else:
                    missing_files.append(result_file)
                    logger.error(f"❌ [RSEM-COUNT] Missing: {result_file}")

        # RSEM 매트릭스 파일 확인 (alignment 단계에서 생성됨)
        counts_dir = workbench_schema["quanti"]["counts"]
        matrix_files = [
            os.path.join(counts_dir, "genes.TPM.matrix"),
            os.path.join(counts_dir, "genes.counts.matrix"),
            os.path.join(counts_dir, "genes.TMM.EXPR.matrix")
        ]

        for matrix_file in matrix_files:
            if os.path.exists(matrix_file):
                file_size = os.path.getsize(matrix_file)
                found_files.append(matrix_file)
                logger.info(f"✅ [RSEM-COUNT] Matrix found: {os.path.basename(matrix_file)} ({file_size:,} bytes)")
            else:
                logger.warning(f"⚠️  [RSEM-COUNT] Matrix not found (optional): {os.path.basename(matrix_file)}")

        # 결과 판정
        if missing_files:
            error_msg = f"Missing RSEM result files: {missing_files}"
            logger.error(f"❌ [RSEM-COUNT] {error_msg}")
            return {
                'success': False,
                'stdout': f'Found {len(found_files)} files',
                'stderr': error_msg,
                'timestamp': datetime.now().isoformat()
            }

        logger.info(f"🎉 [RSEM-COUNT] ✅ All RSEM results verified successfully!")
        logger.info(f"📊 [RSEM-COUNT] Total files verified: {len(found_files)}")
        logger.info(f"📋 [RSEM-COUNT] Note: Quantification was completed during alignment step")

        return {
            'success': True,
            'stdout': f'RSEM quantification verified: {len(found_files)} files found',
            'stderr': '',
            'timestamp': datetime.now().isoformat(),
            'verified_files': len(found_files),
            'total_samples': len(samples_data)
        }

    except Exception as e:
        logger.error(f"[RSEM-COUNT] RSEM count verification failed: {e}")
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'timestamp': datetime.now().isoformat()
        }


def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 rsem tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering rsem tool...")

    metadata = {
        'name': 'rsem',
        'description': 'RSEM quantification results verification (quantification completed during alignment)',
        'version': '1.0.0',
        'supported_formats': ['.results'],
        'requirements': ['rsem'],
        'parameters': {}
    }

    return coordinator.register_tool('rsem', execute_rsem, metadata)
