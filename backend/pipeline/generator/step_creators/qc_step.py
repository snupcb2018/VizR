#!/usr/bin/env python3
"""
QC Step Creator
"""

import json
import os
import logging
from typing import List
from ..models import PipeLineStep, PipelineJobDefinition
from ..utils import extract_input_files_from_samples
from ....blueprints.workbench_utils import get_workbench_schema

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def create_qc_step(job_definition: PipelineJobDefinition, step_name: str, step_counter: int) -> List[PipeLineStep]:
    """QC 스텝 생성 (FastQC) (Callback Handler) - 표준 구조"""
    
    logger.info("🧬 ═══════════════════════════════════════════════════════════════════════")
    logger.info("🧬 📊 QC STEP CREATION - FUNCTION ENTRY 📊")
    logger.info("🧬 ═══════════════════════════════════════════════════════════════════════")
    logger.info(f"🎯 Creating QC step for: {step_name}")
    logger.info(f"📋 Function: create_qc_step()")
    logger.info(f"🔢 Current step counter: {step_counter}")

    samples = job_definition.samples
    workbench = job_definition.workbench
    workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
    
    try:
        workbench_name = workbench['name'] if 'name' in workbench.keys() else 'Unknown'
    except (KeyError, AttributeError):
        workbench_name = 'Unknown'
    logger.info(f"📊 Retrieved workbench data: {workbench_name}")
    logger.info(f"🏗️ Workbench schema generated for QC step")
    
    # job_definition에서 step_name에 해당하는 스텝을 찾기
    logger.info("🔍 [QC_STEP] Searching for step configuration...")
    
    # pipeline_steps 타입 확인 및 파싱
    pipeline_steps = job_definition.pipeline_config['pipeline_steps']
    logger.info(f"📊 [DEBUG] pipeline_steps type: {type(pipeline_steps)}")
    
    # pipeline_steps가 문자열인 경우 JSON 파싱
    if isinstance(pipeline_steps, str):
        try:
            logger.info("🔧 [DEBUG] pipeline_steps is string, attempting JSON parse...")
            pipeline_steps = json.loads(pipeline_steps)
            logger.info(f"✅ [DEBUG] Successfully parsed pipeline_steps for QC")
        except json.JSONDecodeError as e:
            logger.error(f"❌ [DEBUG] Failed to parse pipeline_steps JSON: {e}")
            raise ValueError(f"Invalid JSON in pipeline_steps: {e}")
    
    step_data = next((s for s in pipeline_steps if s['step'] == step_name), None)
    if not step_data:
        logger.error(f"❌ [QC_STEP] Step configuration for {step_name} not found in pipeline steps")
        raise ValueError(f"Step configuration for {step_name} not found in pipeline steps")
    
    logger.info("✅ [QC_STEP] Step configuration found:")
    try:
        logger.info(f"   ├─ Step: {step_data.get('step')}")
        logger.info(f"   ├─ Tool: {step_data.get('tool')}")
        logger.info(f"   └─ Description: {step_data.get('description')}")
        parameter = step_data.get('parameters', {})
    except (KeyError, AttributeError) as e:
        logger.warning(f"   ├─ Error accessing step_data fields: {e}")
        logger.info(f"   └─ Step data type: {type(step_data)}")
        parameter = {}

    # new_step 생성
    step = step_data.get('step', 'qc')
    tool = step_data.get('tool', 'fastqc')
    step_id = f"{step}_{tool}"
    logger.info(f"   └─ Generated step_id: {step_id}")

    new_step = PipeLineStep(
        step_id=step_id,
        step=step,
        name=f"Quality Control ({tool.upper()})",
        tool=tool,
        order=step_counter,
        status='pending',
        parameters=parameter
    )
    
    logger.info(f"✅ Created QC step: {new_step.step_id}")

    # input_dir 설정 - raw data 디렉토리에서 입력 받음
    new_step.input_dir = workbench_schema["quanti"]["raw"]
    logger.info(f"🔧 Set QC input_dir: {new_step.input_dir}")

    # output_dir 설정 - QC 결과 저장 디렉토리
    new_step.output_dir = workbench_schema["quanti"]["qc"]
    logger.info(f"🔧 Set QC output_dir: {new_step.output_dir}")

    # samples에서 file1, file2 추출 및 input_files 설정
    new_step.input_files = extract_input_files_from_samples(samples, new_step.input_dir)
    logger.info(f"✅ Total input files for QC: {len(new_step.input_files)}")

    return [new_step]  # List로 반환