#!/usr/bin/env python3
"""
Download Step Creator
"""

import json
import logging
from typing import List
from ..models import PipeLineStep, PipelineJobDefinition

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def create_download_step(job_definition: PipelineJobDefinition, step_name: str, step_counter: int) -> List[PipeLineStep]:
    """데이터 다운로드/복사 스텝 생성 (Callback Handler)"""
    logger.info(f"🔍 [DOWNLOAD_STEP] Starting _create_download_step for step: {step_name}")
    
    workbench = job_definition.workbench
    logger.info(f"🔍 [DOWNLOAD_STEP] Workbench data type: {type(workbench)}")
    
    # pipeline_steps 파싱 전 타입 확인
    raw_pipeline_steps = job_definition.pipeline_config['pipeline_steps']
    logger.info(f"🔍 [DOWNLOAD_STEP] Raw pipeline_steps type: {type(raw_pipeline_steps)}")
    logger.info(f"🔍 [DOWNLOAD_STEP] Raw pipeline_steps content: {raw_pipeline_steps[:200]}...")
    
    try:
        pipeline_steps = json.loads(raw_pipeline_steps)
        logger.info(f"🔍 [DOWNLOAD_STEP] Parsed pipeline_steps type: {type(pipeline_steps)}")
        logger.info(f"🔍 [DOWNLOAD_STEP] Parsed pipeline_steps length: {len(pipeline_steps)}")
        
        # 각 스텝의 구조 확인
        for i, step in enumerate(pipeline_steps):
            logger.info(f"🔍 [DOWNLOAD_STEP] Step {i}: type={type(step)}, content={step}")
    except Exception as e:
        logger.error(f"❌ [DOWNLOAD_STEP] Error parsing pipeline_steps: {e}")
        raise

    step_data = next((s for s in pipeline_steps if s['step'] == step_name), None)
    logger.info(f"🔍 [DOWNLOAD_STEP] step_data content: {json.dumps(step_data, ensure_ascii=False, indent=2) if step_data else 'None'}")
    
    if not step_data:
        logger.error(f"❌ [DOWNLOAD_STEP] Step configuration for {step_name} not found in pipeline steps")
        raise ValueError(f"Step configuration for {step_name} not found in pipeline steps")

    parameter = step_data.get('parameters', {})
    
    logger.info("🔽 " + "=" * 80)
    logger.info("📥 [DOWNLOAD_STEP] Creating download step")
    logger.info(f"   ├─ Workbench ID: {workbench['id']}")
    logger.info(f"   ├─ Workbench Name: {workbench['name']}")
    logger.info(f"   └─ Step Name: {step_name}")

    # PipeLineStep 인스턴스 생성
    logger.info("🔧 [DOWNLOAD_STEP] Creating PipeLineStep instance...")
    step = step_data.get('step', 'unknown')
    tool = step_data.get('tool', 'unknown')
    step_id = f"{step}_{tool}"
    logger.info(f"   └─ Generated step_id: {step_id}")

    new_step = PipeLineStep(
        step_id = step_id,
        step = step,
        name = step_data.get('description', f"Step {step_counter}"),
        tool = tool,
        order = step_counter,
        status = 'pending',
        parameters = parameter
    )
    
    return [new_step]  # List로 반환