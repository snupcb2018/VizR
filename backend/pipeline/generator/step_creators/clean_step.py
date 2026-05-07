#!/usr/bin/env python3
"""
Clean Step Creators (Trimmomatic, PRINSEQ)
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


def create_clean_step(job_definition: PipelineJobDefinition, step_name: str, step_counter: int) -> List[PipeLineStep]:
    """Clean 스텝 생성 (모듈화) - clean_tools에 따라 개별 step들 생성"""
    
    logger.info("🧬 ═══════════════════════════════════════════════════════════════════════")
    logger.info("🧬 🧹 CLEAN STEP CREATION - FUNCTION ENTRY 🧹")
    logger.info("🧬 ═══════════════════════════════════════════════════════════════════════")
    logger.info(f"🎯 Creating Clean step for: {step_name}")
    logger.info(f"📋 Function: create_clean_step()")
    logger.info(f"🔢 Current step counter: {step_counter}")

    # job_definition에서 step_name에 해당하는 스텝을 찾기
    logger.info("🔍 [CLEAN_STEP] Searching for step configuration...")
    
    # pipeline_steps 타입 확인 및 파싱
    pipeline_steps = job_definition.pipeline_config['pipeline_steps']
    logger.info(f"📊 [DEBUG] pipeline_steps type: {type(pipeline_steps)}")
    
    # pipeline_steps가 문자열인 경우 JSON 파싱
    if isinstance(pipeline_steps, str):
        try:
            pipeline_steps = json.loads(pipeline_steps)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse pipeline_steps JSON: {e}")
            raise ValueError(f"Invalid pipeline_steps JSON: {e}")
    
    step_data = next((s for s in pipeline_steps if s['step'] == step_name), None)
    if not step_data:
        logger.error(f"❌ [CLEAN_STEP] Step configuration for {step_name} not found in pipeline steps")
        raise ValueError(f"Step configuration for {step_name} not found in pipeline steps")
    
    logger.info("✅ [CLEAN_STEP] Step configuration found:")
    try:
        logger.info(f"   ├─ Step: {step_data.get('step')}")
        logger.info(f"   ├─ Tool: {step_data.get('tool')}")
        logger.info(f"   ├─ Description: {step_data.get('description')}")
        logger.info(f"   └─ Parameters: {step_data.get('parameters', {})}")
        parameter = step_data.get('parameters', {})
    except (KeyError, AttributeError) as e:
        logger.warning(f"   ├─ Error accessing step_data fields: {e}")
        logger.info(f"   └─ Step data type: {type(step_data)}")
        parameter = {}
    
    # clean_tools 파라미터 확인
    clean_tools = step_data.get('parameters', {}).get('clean_tools', ['trimmomatic', 'prinseq'])
    if isinstance(clean_tools, str):
        clean_tools = [clean_tools]
    
    logger.info(f"[CLEAN_STEP] Creating modular clean steps for tools: {clean_tools}")
    
    generated_steps = []
    current_counter = step_counter
    
    # 1. Trimmomatic step 생성 (선택된 경우)
    if 'trimmomatic' in clean_tools:
        logger.info(f"[CLEAN_STEP] Creating Trimmomatic step")
        
        trimmomatic_steps = create_trimmomatic_step(job_definition, step_name, current_counter)
        generated_steps.extend(trimmomatic_steps)
        current_counter += len(trimmomatic_steps)
        logger.info(f"✅ [CLEAN_STEP] Created Trimmomatic step: {trimmomatic_steps[0].step_id}")
    
    # 2. PRINSEQ step 생성 (선택된 경우)
    if 'prinseq' in clean_tools:
        logger.info(f"[CLEAN_STEP] Creating PRINSEQ step")
        
        prinseq_steps = create_prinseq_step(job_definition, step_name, current_counter)
        generated_steps.extend(prinseq_steps)
        current_counter += len(prinseq_steps)
        logger.info(f"✅ [CLEAN_STEP] Created PRINSEQ step: {prinseq_steps[0].step_id}")
    
    logger.info(f"[CLEAN_STEP] Generated {len(generated_steps)} modular clean steps")
    return generated_steps


def create_trimmomatic_step(job_definition: PipelineJobDefinition, step_name: str, step_counter: int) -> List[PipeLineStep]:
    """Trimmomatic 스텝 생성 - 표준 구조"""
    samples = job_definition.samples
    workbench = job_definition.workbench
    workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
    
    # workbench_schema 구조 디버깅
    logger.info(f"📊 [DEBUG] workbench_schema type: {type(workbench_schema)}")
    logger.info(f"📊 [DEBUG] workbench_schema content: {workbench_schema}")
    if isinstance(workbench_schema, dict):
        logger.info(f"📊 [DEBUG] workbench_schema keys: {list(workbench_schema.keys())}")
        if 'quanti' in workbench_schema:
            logger.info(f"📊 [DEBUG] quanti structure: {workbench_schema['quanti']}")
    
    pipeline_steps = job_definition.pipeline_config['pipeline_steps']
    logger.info(f"📊 [DEBUG] pipeline_steps type: {type(pipeline_steps)}")
    
    # pipeline_steps가 문자열인 경우 JSON 파싱
    if isinstance(pipeline_steps, str):
        try:
            logger.info("🔧 [DEBUG] pipeline_steps is string, attempting JSON parse...")
            pipeline_steps = json.loads(pipeline_steps)
            logger.info(f"✅ [DEBUG] Successfully parsed pipeline_steps for Trimmomatic")
        except json.JSONDecodeError as e:
            logger.error(f"❌ [DEBUG] Failed to parse pipeline_steps JSON: {e}")
            raise ValueError(f"Invalid JSON in pipeline_steps: {e}")

    step_data = next((s for s in pipeline_steps if s['step'] == step_name), None)
    if not step_data:
        logger.error(f"❌ [TRIMMOMATIC_STEP] Step configuration for {step_name} not found in pipeline steps")
        raise ValueError(f"Step configuration for {step_name} not found in pipeline steps")
    
    logger.info("✅ [TRIMMOMATIC_STEP] Step configuration found:")
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
    step_id = "clean_trimmomatic"
    logger.info(f"   └─ Generated step_id: {step_id}")

    new_step = PipeLineStep(
        step_id=step_id,
        step="clean",
        name=f"Sequence cleaning with Trimmomatic",
        tool="trimmomatic",
        order=step_counter,
        status='pending',
        parameters=parameter
    )

    # input_dir 설정 - raw data 디렉토리에서 입력 받음
    new_step.input_dir = workbench_schema["quanti"]["raw"]
    logger.info(f"📊 [DEBUG] Set input_dir: {new_step.input_dir}")

    # output_dir 설정 - clean 결과 저장 디렉토리
    clean_dir = workbench_schema["quanti"]["clean"]
    if isinstance(clean_dir, dict) and "trim" in clean_dir:
        new_step.output_dir = clean_dir["trim"]
    else:
        # clean이 문자열인 경우 trim 서브디렉토리 생성
        new_step.output_dir = os.path.join(clean_dir, "trim")
    logger.info(f"📊 [DEBUG] Set output_dir: {new_step.output_dir}")

    # samples에서 file1, file2 추출 및 input_files 설정
    new_step.input_files = extract_input_files_from_samples(samples, new_step.input_dir)
    logger.info(f"✅ Total input files for Trimmomatic: {len(new_step.input_files)}")

    return [new_step]  # List로 반환


def create_prinseq_step(job_definition: PipelineJobDefinition, step_name: str, step_counter: int) -> List[PipeLineStep]:
    """PRINSEQ 스텝 생성 - 표준 구조"""
    
    logger.info("🧬 ═══════════════════════════════════════════════════════════════════════")
    logger.info("🧬 🧹 PRINSEQ STEP CREATION - FUNCTION ENTRY 🧹")
    logger.info("🧬 ═══════════════════════════════════════════════════════════════════════")
    logger.info(f"🎯 Creating PRINSEQ step for: {step_name}")
    logger.info(f"📋 Function: create_prinseq_step()")
    logger.info(f"🔢 Current step counter: {step_counter}")
    
    samples = job_definition.samples
    workbench = job_definition.workbench
    workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
    
    # workbench_schema 구조 디버깅
    logger.info(f"📊 [DEBUG] PRINSEQ workbench_schema type: {type(workbench_schema)}")
    logger.info(f"📊 [DEBUG] PRINSEQ workbench_schema content: {workbench_schema}")
    if isinstance(workbench_schema, dict):
        logger.info(f"📊 [DEBUG] PRINSEQ workbench_schema keys: {list(workbench_schema.keys())}")
        if 'quanti' in workbench_schema:
            logger.info(f"📊 [DEBUG] PRINSEQ quanti structure: {workbench_schema['quanti']}")
    
    pipeline_steps = job_definition.pipeline_config['pipeline_steps']
    
    try:
        workbench_name = workbench['name'] if 'name' in workbench.keys() else 'Unknown'
    except (KeyError, AttributeError):
        workbench_name = 'Unknown'
    logger.info(f"📊 Retrieved workbench data: {workbench_name}")
    logger.info(f"🏗️ Workbench schema generated for PRINSEQ step")
    logger.info(f"📊 [DEBUG] pipeline_steps type: {type(pipeline_steps)}")
    
    # pipeline_steps가 문자열인 경우 JSON 파싱
    if isinstance(pipeline_steps, str):
        try:
            logger.info("🔧 [DEBUG] pipeline_steps is string, attempting JSON parse...")
            pipeline_steps = json.loads(pipeline_steps)
            logger.info(f"✅ [DEBUG] Successfully parsed pipeline_steps for PRINSEQ")
        except json.JSONDecodeError as e:
            logger.error(f"❌ [DEBUG] Failed to parse pipeline_steps JSON: {e}")
            raise ValueError(f"Invalid JSON in pipeline_steps: {e}")

    step_data = next((s for s in pipeline_steps if s['step'] == step_name), None)
    if not step_data:
        logger.error(f"❌ [PRINSEQ_STEP] Step configuration for {step_name} not found in pipeline steps")
        raise ValueError(f"Step configuration for {step_name} not found in pipeline steps")
    
    logger.info("✅ [PRINSEQ_STEP] Step configuration found:")
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
    step_id = "clean_prinseq"
    logger.info(f"   └─ Generated step_id: {step_id}")

    new_step = PipeLineStep(
        step_id=step_id,
        step="clean",
        name=f"Sequence cleaning with PRINSEQ",
        tool="prinseq",
        order=step_counter,
        status='pending',
        parameters=parameter
    )

    # parameter 정보로부터 앞전의 단계가 trimmomatic 단계였는지 확인한다. is_after_download 할당.
    clean_tools = parameter.get('clean_tools', [])
    is_after_download = 'trimmomatic' not in clean_tools
    
    logger.info(f"⚙️ [PRINSEQ_STEP] Configuration analysis:")
    logger.info(f"   ├─ Clean tools: {clean_tools}")
    logger.info(f"   ├─ Is after download: {is_after_download}")
    logger.info(f"   └─ Execution mode: {'Download → PRINSEQ' if is_after_download else 'Download → Trimmomatic → PRINSEQ'}")

    logger.info("✅ [PRINSEQ_STEP] PRINSEQ step creation completed:")
    logger.info(f"   ├─ Step ID: {new_step.step_id}")
    logger.info(f"   ├─ Step: {new_step.step}")
    logger.info(f"   ├─ Name: {new_step.name}")
    logger.info(f"   ├─ Tool: {new_step.tool}")
    logger.info(f"   ├─ Input dir: {new_step.input_dir}")
    logger.info(f"   ├─ Input files count: {len(new_step.input_files) if new_step.input_files else 0}")
    logger.info(f"   ├─ Output dir: {new_step.output_dir}")
    logger.info(f"   └─ Parameters: {new_step.parameters}")
    logger.info("🧬 ═══════════════════════════════════════════════════════════════════════")
    
    return [new_step]  # List로 반환