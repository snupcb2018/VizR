#!/usr/bin/env python3
"""
DEG Step Creator (DESeq2/edgeR)
"""

import json
import logging
from typing import List
from ..models import PipeLineStep, PipelineJobDefinition

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def create_deg_step(job_definition: PipelineJobDefinition, step_name: str, step_counter: int) -> List[PipeLineStep]:
    """DEG 스텝 생성 (DESeq2/edgeR) - 표준 구조"""
    logger.info("🎯 ═══════════════════════════════════════════════════════════════════════")
    logger.info("🎯 🧬 DEG STEP CREATION - FUNCTION ENTRY 🧬")
    logger.info("🎯 ═══════════════════════════════════════════════════════════════════════")
    logger.info(f"🎯 Creating DEG step for: {step_name}")
    logger.info(f"📋 Function: create_deg_step()")
    logger.info(f"🔢 Current step counter: {step_counter}")
    
    samples = job_definition.samples
    workbench = job_definition.workbench
    
    pipeline_steps = job_definition.pipeline_config['pipeline_steps']
    
    try:
        workbench_name = workbench['name'] if 'name' in workbench.keys() else 'Unknown'
    except (KeyError, AttributeError):
        workbench_name = 'Unknown'
    logger.info(f"📊 Retrieved workbench data: {workbench_name}")
    logger.info(f"🏗️ Workbench schema generated for DEG step")
    logger.info(f"📊 [DEBUG] pipeline_steps type: {type(pipeline_steps)}")
    
    # pipeline_steps가 문자열인 경우 JSON 파싱
    if isinstance(pipeline_steps, str):
        try:
            logger.info("🔧 [DEBUG] pipeline_steps is string, attempting JSON parse...")
            pipeline_steps = json.loads(pipeline_steps)
            logger.info(f"✅ [DEBUG] Successfully parsed pipeline_steps for DEG")
        except json.JSONDecodeError as e:
            logger.error(f"❌ [DEBUG] Failed to parse pipeline_steps JSON: {e}")
            raise ValueError(f"Invalid JSON in pipeline_steps: {e}")

    step_data = next((s for s in pipeline_steps if s['step'] == step_name), None)
    if not step_data:
        logger.error(f"❌ [DEG_STEP] Step configuration for {step_name} not found in pipeline steps")
        raise ValueError(f"Step configuration for {step_name} not found in pipeline steps")
    
    logger.info("✅ [DEG_STEP] Step configuration found:")
    try:
        logger.info(f"   ├─ Step: {step_data.get('step')}")
        logger.info(f"   ├─ Tool: {step_data.get('tool')}")
        logger.info(f"   └─ Description: {step_data.get('description')}")
        parameters = step_data.get('parameters', {})
        tool_name = step_data.get('tool', 'deseq2')  # 기본값은 deseq2
    except (KeyError, AttributeError) as e:
        logger.warning(f"   ├─ Error accessing step_data fields: {e}")
        logger.info(f"   └─ Step data type: {type(step_data)}")
        parameters = {}
        tool_name = 'deseq2'  # 기본값
    
    # new_step 생성
    step_id = f"deg_{tool_name}"
    logger.info(f"   └─ Generated step_id: {step_id}")

    new_step = PipeLineStep(
        step_id=step_id,
        step="deg",
        name=f"Differential expression analysis with {tool_name.upper()}",
        tool=tool_name,
        order=step_counter,
        status='pending',
        parameters=parameters
    )

    logger.info(f"✅ [DEG_STEP] Created {tool_name.upper()} step:")
    logger.info(f"   ├─ Step ID: {new_step.step_id}")
    logger.info(f"   ├─ Tool: {new_step.tool}")
    logger.info(f"   ├─ Order: {new_step.order}")
    logger.info(f"   └─ Parameters: {new_step.parameters}")

    return [new_step]