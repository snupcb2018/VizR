#!/usr/bin/env python3
"""
Alignment Step Creator (HISAT2)
"""

import json
import logging
from typing import List
from ..models import PipeLineStep, PipelineJobDefinition
from backend.utils.database import get_db_connection

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def create_alignment_step(job_definition: PipelineJobDefinition, step_name: str, step_counter: int) -> List[PipeLineStep]:
    """Alignment 스텝 생성 (HISAT2) - 표준 구조"""
    
    logger.info("🎯 ═══════════════════════════════════════════════════════════════════════")
    logger.info("🎯 🧬 ALIGNMENT STEP CREATION - FUNCTION ENTRY 🧬")
    logger.info("🎯 ═══════════════════════════════════════════════════════════════════════")
    logger.info(f"🎯 Creating alignment step for: {step_name}")
    logger.info(f"📋 Function: create_alignment_step()")
    logger.info(f"🔢 Current step counter: {step_counter}")
    
    samples = job_definition.samples
    workbench = job_definition.workbench
    
    pipeline_steps = job_definition.pipeline_config['pipeline_steps']
    
    try:
        workbench_name = workbench['name'] if 'name' in workbench.keys() else 'Unknown'
    except (KeyError, AttributeError):
        workbench_name = 'Unknown'
    logger.info(f"📊 Retrieved workbench data: {workbench_name}")
    logger.info(f"🏗️ Workbench schema generated for HISAT2 alignment step")
    logger.info(f"📊 [DEBUG] pipeline_steps type: {type(pipeline_steps)}")
    
    # pipeline_steps가 문자열인 경우 JSON 파싱
    if isinstance(pipeline_steps, str):
        try:
            logger.info("🔧 [DEBUG] pipeline_steps is string, attempting JSON parse...")
            pipeline_steps = json.loads(pipeline_steps)
            logger.info(f"✅ [DEBUG] Successfully parsed pipeline_steps for HISAT2")
        except json.JSONDecodeError as e:
            logger.error(f"❌ [DEBUG] Failed to parse pipeline_steps JSON: {e}")
            raise ValueError(f"Invalid JSON in pipeline_steps: {e}")

    step_data = next((s for s in pipeline_steps if s['step'] == step_name), None)
    if not step_data:
        logger.error(f"❌ [ALIGNMENT_STEP] Step configuration for {step_name} not found in pipeline steps")
        raise ValueError(f"Step configuration for {step_name} not found in pipeline steps")
    
    logger.info("✅ [ALIGNMENT_STEP] Step configuration found:")
    try:
        logger.info(f"   ├─ Step: {step_data.get('step')}")
        logger.info(f"   ├─ Tool: {step_data.get('tool')}")
        logger.info(f"   └─ Description: {step_data.get('description')}")
        parameters = step_data.get('parameters', {})
        tool_name = step_data.get('tool', 'hisat2')  # 기본값은 hisat2
    except (KeyError, AttributeError) as e:
        logger.warning(f"   ├─ Error accessing step_data fields: {e}")
        logger.info(f"   └─ Step data type: {type(step_data)}")
        parameters = {}
        tool_name = 'hisat2'  # 기본값

    # clean_tools 정보를 DB에서 실제 실행된 clean step에서 가져오기
    logger.info("🔍 [ALIGNMENT_STEP] Looking for clean step configuration from DB...")
    workbench_id = workbench['id']

    clean_tools = []
    try:
        with get_db_connection() as conn:
            # 실행 완료된 clean step을 DB에서 조회 (최신 것 하나만)
            clean_step_row = conn.execute('''
                SELECT parameters FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'clean' AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if clean_step_row and clean_step_row['parameters']:
                # parameters JSON 파싱
                params = json.loads(clean_step_row['parameters'])
                clean_tools = params.get('clean_tools', [])
                logger.info(f"✅ [ALIGNMENT_STEP] Found clean_tools from DB: {clean_tools}")
            else:
                logger.info("ℹ️ [ALIGNMENT_STEP] No completed clean step found in DB")

                # Fallback: 현재 파이프라인 설정에서 찾기
                clean_step_config = next((s for s in pipeline_steps if s['step'] == 'clean'), None)
                if clean_step_config:
                    clean_tools = clean_step_config.get('parameters', {}).get('clean_tools', [])
                    logger.info(f"✅ [ALIGNMENT_STEP] Found clean_tools from pipeline config (fallback): {clean_tools}")
                else:
                    logger.info("ℹ️ [ALIGNMENT_STEP] No clean step in pipeline config either, using empty clean_tools")

    except Exception as e:
        logger.error(f"❌ [ALIGNMENT_STEP] Failed to query clean step from DB: {e}")
        logger.info("⚠️ [ALIGNMENT_STEP] Falling back to pipeline config...")

        # Exception fallback
        clean_step_config = next((s for s in pipeline_steps if s['step'] == 'clean'), None)
        if clean_step_config:
            clean_tools = clean_step_config.get('parameters', {}).get('clean_tools', [])
            logger.info(f"✅ [ALIGNMENT_STEP] Found clean_tools from pipeline config (exception fallback): {clean_tools}")

    parameters['clean_tools'] = clean_tools

    # new_step 생성
    step_id = f"alignment_{tool_name}"
    logger.info(f"   └─ Generated step_id: {step_id}")

    new_step = PipeLineStep(
        step_id=step_id,
        step="alignment",
        name=f"Read alignment with {tool_name.upper()}",
        tool=tool_name,
        order=step_counter,
        status='pending',
        parameters=parameters
    )

    logger.info(f"✅ [ALIGNMENT_STEP] Created {tool_name.upper()} step:")
    logger.info(f"   ├─ Step ID: {new_step.step_id}")
    logger.info(f"   ├─ Tool: {new_step.tool}")
    logger.info(f"   ├─ Order: {new_step.order}")
    logger.info(f"   └─ Parameters: {new_step.parameters}")

    return [new_step]