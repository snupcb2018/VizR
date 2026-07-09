#!/usr/bin/env python3
"""
Pipeline Database Operations
"""

import json
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from ...utils.database import get_db_connection
from ...blueprints.workbench_utils import get_workbench_schema
from .models import PipelineJobDefinition
from .utils import parse_samples_data

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def load_workbench_data(workbench_id: int) -> tuple:
    """워크벤치 관련 데이터 로드"""
    logger.info(f"Generating job from workbench {workbench_id}")
    
    with get_db_connection() as conn:
        # 워크벤치 기본 정보 조회 (사용자 정보 포함)
        logger.info(f"Fetching workbench data for ID: {workbench_id}")
        workbench = conn.execute('''
            SELECT w.*, u.username 
            FROM vizr_workbench w 
            JOIN users u ON w.user_id = u.id 
            WHERE w.id = ?
        ''', (workbench_id,)).fetchone()
        
        if not workbench:
            raise ValueError(f"Workbench {workbench_id} not found")
        
        # 파이프라인 설정 조회
        pipeline_config = conn.execute('''
            SELECT * FROM vizr_pipeline_configurations 
            WHERE workbench_id = ? 
            ORDER BY created_at DESC LIMIT 1
        ''', (workbench_id,)).fetchone()
        
        if not pipeline_config:
            raise ValueError(f"No pipeline configuration found for workbench {workbench_id}")
        
        # Pipeline configuration 로깅
        logger.info("🔍 [PIPELINE-CONFIG] Pipeline configuration loaded")
        logger.info(f"   ├─ Workbench ID: {workbench_id}")
        logger.info(f"   └─ Config ID: {pipeline_config['id']}")
        
        # 샘플 및 파일 매핑 조회 (JSON에서 파싱)
        samples_raw = conn.execute('''
            SELECT * FROM vizr_pipeline_samples 
            WHERE workbench_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (workbench_id,)).fetchone()
        
        # JSON 데이터를 파싱하여 샘플 목록 생성
        samples = parse_samples_data(samples_raw, workbench_id) if samples_raw else []

        # Samples 정보 로깅
        logger.info(f"🔍 [SAMPLES] Sample data loaded: {len(samples)} samples")
        
        return workbench, pipeline_config, samples


def register_job_to_database(job_definition: PipelineJobDefinition) -> str:
    """파이프라인 작업을 데이터베이스에 등록"""
    job_id = job_definition.job_id

    logger.info(f"[🔍DEBUG-PIPELINE] === DATABASE REGISTRATION START ===")
    with get_db_connection() as conn:
        logger.info(f"[🔍DEBUG-PIPELINE] DB connection established: {conn}")

        # Workbench 존재 여부 확인
        workbench_exists = conn.execute('''
            SELECT COUNT(*) FROM vizr_workbench WHERE id = ?
        ''', (job_definition.workbench['id'],)).fetchone()[0]

        logger.info(f"[🔍WORKBENCH] Workbench exists check: ✅ (count: {workbench_exists})")

        if workbench_exists == 0:
            logger.error(f"[🔍WORKBENCH] ❌ Workbench ID {job_definition.workbench['id']} not found!")
            raise ValueError(f"Workbench ID {job_definition.workbench['id']} does not exist in database")

        workbench_id = job_definition.workbench['id']

        # 1. 기존 job_queue에서 해당 워크벤치의 모든 작업 삭제
        logger.info(f"🗑️ [CLEANUP] Deleting existing job_queue for workbench {workbench_id}")
        deleted_queue = conn.execute('''
            DELETE FROM job_queue WHERE workbench_id = ?
        ''', (workbench_id,))
        logger.info(f"   └─ Deleted {deleted_queue.rowcount} jobs from job_queue")

        # 2. 기존 step들의 should_run 플래그를 모두 0으로 초기화
        logger.info(f"🔄 [RESET] Resetting should_run flags for workbench {workbench_id}")
        conn.execute('''
            UPDATE pipeline_job_steps
            SET should_run = 0
            WHERE workbench_id = ?
        ''', (workbench_id,))
        conn.commit()

        # 3. 새 파이프라인에 없는 같은 종류(step_name)의 기존 step 삭제
        logger.info(f"🗑️ [CLEANUP-OLD-STEPS] Removing old steps not in new pipeline")

        # 3-1. 새 파이프라인의 step_id 목록 생성
        new_step_ids = {step.step_id for step in job_definition.steps}
        logger.info(f"   ├─ New step_ids: {new_step_ids}")

        # 3-2. 새 파이프라인의 step_name 목록 생성 (중복 제거)
        new_step_names = {step.step for step in job_definition.steps}

        # 3-3. 각 step_name별로 기존 step 중에서 새 파이프라인에 없는 것들 삭제
        deleted_count = 0
        for step_name in new_step_names:
            # 같은 step_name을 가진 기존 step들 조회
            existing_steps = conn.execute('''
                SELECT step_id FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = ?
            ''', (workbench_id, step_name)).fetchall()

            # 새 파이프라인에 없는 기존 step 삭제
            for existing in existing_steps:
                if existing['step_id'] not in new_step_ids:
                    conn.execute('''
                        DELETE FROM pipeline_job_steps
                        WHERE workbench_id = ? AND step_id = ?
                    ''', (workbench_id, existing['step_id']))
                    deleted_count += 1
                    logger.info(f"   ├─ 🗑️ Deleted old step: {existing['step_id']} (same step_name: {step_name})")

        if deleted_count > 0:
            conn.commit()
            logger.info(f"   └─ ✅ Deleted {deleted_count} old step(s)")
        else:
            logger.info(f"   └─ ℹ️ No old steps to delete")

        # 4. 각 스텝을 UPSERT (기존 step이면 UPDATE, 없으면 INSERT)
        logger.info(f"[🔍DB-STEPS] === UPSERTING {len(job_definition.steps)} STEPS ===")
        for i, step in enumerate(job_definition.steps, 1):
            logger.info(f"[🔍DB-STEPS] Step {i}/{len(job_definition.steps)}: {step.step_id}")
            logger.info(f"[🔍DB-STEPS]   ├─ Name: {step.name}")
            logger.info(f"[🔍DB-STEPS]   ├─ Tool: {step.tool}")
            logger.info(f"[🔍DB-STEPS]   ├─ Order: {step.order}")

            # 기존 step 확인
            existing = conn.execute('''
                SELECT id FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_id = ?
            ''', (workbench_id, step.step_id)).fetchone()

            if existing:
                # UPDATE (기존 step 업데이트 + should_run=1 마킹)
                logger.info(f"[🔍DB-STEPS]   ├─ Action: UPDATE (existing step)")
                conn.execute('''
                    UPDATE pipeline_job_steps
                    SET job_id = ?, step_name = ?, tool_name = ?, step_order = ?,
                        status = 'pending', should_run = 1,
                        input_files = ?, parameters = ?, input_dir = ?, output_dir = ?, output_files = ?
                    WHERE workbench_id = ? AND step_id = ?
                ''', (
                    job_id,
                    step.step,
                    step.tool,
                    step.order,
                    json.dumps(step.input_files),
                    json.dumps(step.parameters),
                    step.input_dir,
                    step.output_dir,
                    json.dumps(step.output_files),
                    workbench_id,
                    step.step_id
                ))
                logger.info(f"[🔍DB-STEPS]   └─ ✅ Step {step.step_id} updated (should_run=1)")
            else:
                # INSERT (새 step 추가 + should_run=1 마킹)
                logger.info(f"[🔍DB-STEPS]   ├─ Action: INSERT (new step)")
                conn.execute('''
                    INSERT INTO pipeline_job_steps
                    (job_id, step_id, step_name, tool_name, step_order, status, should_run,
                     input_files, parameters, input_dir, output_dir, output_files, workbench_id)
                    VALUES (?, ?, ?, ?, ?, 'pending', 1, ?, ?, ?, ?, ?, ?)
                ''', (
                    job_id,
                    step.step_id,
                    step.step,
                    step.tool,
                    step.order,
                    json.dumps(step.input_files),
                    json.dumps(step.parameters),
                    step.input_dir,
                    step.output_dir,
                    json.dumps(step.output_files),
                    workbench_id
                ))
                logger.info(f"[🔍DB-STEPS]   └─ ✅ Step {step.step_id} inserted (should_run=1)")

        conn.commit()

        # 5. should_run=1인 첫 번째 step만 job_queue에 enqueue
        registered_steps = conn.execute('''
            SELECT step_id, step_name, tool_name, step_order, status, should_run
            FROM pipeline_job_steps
            WHERE workbench_id = ? AND job_id = ?
            ORDER BY step_order ASC
        ''', (workbench_id, job_id)).fetchall()
        logger.info(f"[GSEA-AUTO][DB] Registered {len(registered_steps)} step(s) for job {job_id}")
        for step_row in registered_steps:
            logger.info(
                f"[GSEA-AUTO][DB]   step_id={step_row['step_id']}, step_name={step_row['step_name']}, tool={step_row['tool_name']}, order={step_row['step_order']}, status={step_row['status']}, should_run={step_row['should_run']}"
            )

        first_marked_step = conn.execute('''
            SELECT step_id FROM pipeline_job_steps
            WHERE workbench_id = ? AND should_run = 1 AND status = 'pending'
            ORDER BY step_order ASC
            LIMIT 1
        ''', (workbench_id,)).fetchone()

        if first_marked_step:
            logger.info(f"🚀 [JOB_QUEUE] Enqueueing first marked step: {first_marked_step['step_id']}")

            conn.execute('''
                INSERT INTO job_queue
                (job_id, step_id, status, workbench_id, queued_at)
                VALUES (?, ?, 'pending', ?, ?)
            ''', (
                job_id,
                first_marked_step['step_id'],
                workbench_id,
                datetime.now(timezone.utc).isoformat()
            ))

            conn.commit()

            logger.info(f"✅ [JOB_QUEUE] First marked step {first_marked_step['step_id']} enqueued successfully")
        else:
            logger.warning(f"⚠️ [JOB_QUEUE] No steps marked with should_run=1 to enqueue for job {job_id}")

    logger.info(f"[🔍DEBUG-PIPELINE] === DATABASE REGISTRATION SUCCESS ===")
    logger.info(f"[🔍DEBUG-PIPELINE] Pipeline job created: {job_id} for workbench {job_definition.workbench['id']}")
    logger.info(f"[🔍DEBUG-PIPELINE] Total steps inserted: {len(job_definition.steps)}")
    logger.info(f"[🔍DEBUG-PIPELINE] Using simplified structure: pipeline_job_steps only")

    return job_id
