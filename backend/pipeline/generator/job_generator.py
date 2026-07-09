#!/usr/bin/env python3
"""
Pipeline Job Generator - Modularized Version
DB에서 워크벤치 설정을 읽어 JSON 작업지시서를 생성하고 Job Queue에 등록
"""

import json
import sqlite3
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

# SQLite Threading 설정 - Thread-safe 모드 활성화
sqlite3.threadsafety = 3

from config.backend_settings import BackendConfig as Config
from .models import PipeLineStep, PipelineJobDefinition
from .database import load_workbench_data, register_job_to_database
from .step_creators import (
    create_download_step, 
    create_qc_step, 
    create_clean_step, 
    create_alignment_step, 
    create_count_step, 
    create_deg_step,
    create_gsea_step
)

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class PipelineJobGenerator:
    """파이프라인 작업 생성기 - 간소화된 버전"""
    
    def __init__(self):
        self.db_path = Config.DATABASE_FILE
        self.kst = timezone(timedelta(hours=9))  # 한국 시간대
        self.current_step_counter = 1  # 스텝 ID 카운터
        
        # Step type별 처리 함수 등록 테이블
        self.step_handlers = {
            'download': self._create_download_step_wrapper,
            'qc': self._create_qc_step_wrapper,
            'clean': self._create_clean_step_wrapper,  # 모듈화된 clean (리스트 반환)
            'alignment': self._create_alignment_step_wrapper,
            'count': self._create_count_step_wrapper,
            'deg': self._create_deg_step_wrapper
        }
    
    def create_pipeline_job(self, workbench_id: int) -> str:
        """파이프라인 Job 생성 및 DB 등록"""
        try:
            logger.info(f"[🔍DEBUG-PIPELINE] Starting pipeline job creation for workbench_id: {workbench_id}")
            logger.info(f"[🔍DEBUG-PIPELINE] Generator instance: {self}")
            logger.info(f"[🔍DEBUG-PIPELINE] DB path: {self.db_path}")
            
            # Job 정의 생성
            logger.info(f"[🔍DEBUG-PIPELINE] About to call generate_pipeline_from_workbench({workbench_id})")
            job_definition = self.generate_pipeline_from_workbench(workbench_id)
            logger.info(f"[🔍DEBUG-PIPELINE] Job definition generated: {type(job_definition)}")
            job_id = job_definition.job_id
            logger.info(f"[🔍DEBUG-PIPELINE] Job definition generated successfully with job_id: {job_id}")
            self.current_step_counter = 1  # 다음 호출을 위해 카운터 초기화
            
            # DB에 Job 등록
            register_job_to_database(job_definition)
            
            logger.info(f"[🔍DEBUG-PIPELINE] === PIPELINE JOB CREATION SUCCESS ===")
            return job_id
            
        except Exception as e:
            logger.error(f"[🔍DEBUG-PIPELINE] === PIPELINE JOB CREATION FAILED ===")
            logger.error(f"[🔍DEBUG-PIPELINE] Exception type: {type(e)}")
            logger.error(f"[🔍DEBUG-PIPELINE] Exception message: {str(e)}")
            logger.error(f"[🔍DEBUG-PIPELINE] Failed to create pipeline job for workbench {workbench_id}: {e}")
            import traceback
            logger.error(f"[🔍DEBUG-PIPELINE] Traceback: {traceback.format_exc()}")
            raise e
        
    def generate_pipeline_from_workbench(self, workbench_id: int) -> PipelineJobDefinition:
        """워크벤치 ID로부터 파이프라인 Job 생성"""
        
        # 데이터베이스에서 워크벤치 관련 데이터 로드
        workbench, pipeline_config, samples = load_workbench_data(workbench_id)
        
        # 작업지시서 생성
        logger.info(f"Creating job definition for workbench: {workbench_id}")
        job_definition = self._create_job_definition(
            workbench=workbench,
            pipeline_config=pipeline_config,
            samples=samples
        )

        logger.info(f"Job definition created successfully with {len(job_definition.steps)} steps")
        return job_definition
    
    def _create_job_definition(self, workbench: sqlite3.Row, pipeline_config: sqlite3.Row, samples: List[sqlite3.Row]) -> PipelineJobDefinition:
        """작업지시서 JSON 생성"""
        
        job_definition = PipelineJobDefinition(workbench, pipeline_config, samples)
        
        # pipeline_steps 파싱
        pipeline_steps = json.loads(pipeline_config['pipeline_steps'])

        # pipeline_steps 길이 만큼 for 루프를 돌며 스텝 생성
        deg_tool_for_gsea = None
        gsea_databases_for_gsea = None
        gsea_enabled_for_gsea = True
        for i, step in enumerate(pipeline_steps):
            if (step.get('parameters') or {}).get('disabled'):
                logger.info(f"Skipping disabled pipeline step: {step.get('step')} ({step.get('tool')})")
                continue
            # 스텝 타입에 따라 적절한 핸들러 호출
            handler = self.step_handlers.get(step['step'], None)
            if not handler:
                raise ValueError(f"No handler defined for step: {step['step']}")
            
            # 핸들러 호출
            try:
                step_definition = handler(job_definition, step['step'])
                job_definition.steps.extend(step_definition)
                if step.get('step') == 'deg' and step.get('tool'):
                    deg_tool_for_gsea = step.get('tool')
                    step_parameters = step.get('parameters') or {}
                    gsea_enabled_for_gsea = bool(step_parameters.get('gsea_enabled', True))
                    configured_gsea_databases = step_parameters.get('gsea_databases')
                    if isinstance(configured_gsea_databases, list):
                        gsea_databases_for_gsea = configured_gsea_databases
                
                # 생성된 스텝들의 설정 정보 로깅
                for step_obj in step_definition:
                    logger.info("📋 [STEP] Final step configuration:")
                    logger.info(f"   ├─ Step ID: {step_obj.step_id}")
                    logger.info(f"   ├─ Step: {step_obj.step}")
                    logger.info(f"   ├─ Name: {step_obj.name}")
                    logger.info(f"   ├─ Tool: {step_obj.tool}")
                    logger.info(f"   ├─ Input dir: {step_obj.input_dir}")
                    logger.info(f"   ├─ Input files count: {len(step_obj.input_files) if step_obj.input_files else 0}")
                    if step_obj.input_files:
                        for i, input_file in enumerate(step_obj.input_files, 1):
                            logger.info(f"   │  {i}. {input_file}")
                    logger.info(f"   ├─ Output dir: {step_obj.output_dir}")
                    logger.info(f"   └─ Parameters: {json.dumps(step_obj.parameters, ensure_ascii=False) if step_obj.parameters else '{}'}")

            except Exception as e:
                logger.error(f"Error creating step {step.get('step', 'unknown')}: {e}")
                raise e

        logger.info(
            f"[GSEA-AUTO] DEG tool detected for automatic GSEA step generation: {deg_tool_for_gsea if deg_tool_for_gsea else 'none'} (enabled={gsea_enabled_for_gsea}, databases={gsea_databases_for_gsea if gsea_databases_for_gsea is not None else 'legacy-default'})"
        )
        if deg_tool_for_gsea and gsea_enabled_for_gsea:
            gsea_steps = create_gsea_step(
                job_definition,
                deg_tool_for_gsea,
                self.current_step_counter,
                gsea_databases_for_gsea,
            )
            logger.info(
                f"[GSEA-AUTO] Appending {len(gsea_steps)} automatic GSEA step(s) after DEG for workbench {job_definition.workbench['id']}"
            )
            for gsea_step in gsea_steps:
                logger.info(
                    f"[GSEA-AUTO]   step_id={gsea_step.step_id}, step={gsea_step.step}, tool={gsea_step.tool}, order={gsea_step.order}, parameters={json.dumps(gsea_step.parameters or {}, ensure_ascii=False)}"
                )
            self.current_step_counter += len(gsea_steps)
            job_definition.steps.extend(gsea_steps)
        elif not deg_tool_for_gsea:
            logger.info(
                f"[GSEA-AUTO] No DEG step detected for workbench {job_definition.workbench['id']}; automatic GSEA step will not be added"
            )
        else:
            logger.info(
                f"[GSEA-AUTO] GSEA disabled in DEG parameters for workbench {job_definition.workbench['id']}; automatic GSEA step will not be added"
            )

        return job_definition
    
    # Wrapper methods for step creators - 기존 인터페이스 호환성 유지
    def _create_download_step_wrapper(self, job_definition: PipelineJobDefinition, step_name: str) -> List[PipeLineStep]:
        """Download 스텝 생성 래퍼"""
        steps = create_download_step(job_definition, step_name, self.current_step_counter)
        self.current_step_counter += len(steps)
        return steps
    
    def _create_qc_step_wrapper(self, job_definition: PipelineJobDefinition, step_name: str) -> List[PipeLineStep]:
        """QC 스텝 생성 래퍼"""
        steps = create_qc_step(job_definition, step_name, self.current_step_counter)
        self.current_step_counter += len(steps)
        return steps
    
    def _create_clean_step_wrapper(self, job_definition: PipelineJobDefinition, step_name: str) -> List[PipeLineStep]:
        """Clean 스텝 생성 래퍼"""
        steps = create_clean_step(job_definition, step_name, self.current_step_counter)
        self.current_step_counter += len(steps)
        return steps
    
    def _create_alignment_step_wrapper(self, job_definition: PipelineJobDefinition, step_name: str) -> List[PipeLineStep]:
        """Alignment 스텝 생성 래퍼"""
        steps = create_alignment_step(job_definition, step_name, self.current_step_counter)
        self.current_step_counter += len(steps)
        return steps
    
    def _create_count_step_wrapper(self, job_definition: PipelineJobDefinition, step_name: str) -> List[PipeLineStep]:
        """Count 스텝 생성 래퍼"""
        steps = create_count_step(job_definition, step_name, self.current_step_counter)
        self.current_step_counter += len(steps)
        return steps
    
    def _create_deg_step_wrapper(self, job_definition: PipelineJobDefinition, step_name: str) -> List[PipeLineStep]:
        """DEG 스텝 생성 래퍼"""
        steps = create_deg_step(job_definition, step_name, self.current_step_counter)
        self.current_step_counter += len(steps)
        return steps


# 사용 예제
if __name__ == '__main__':
    generator = PipelineJobGenerator()
    
    try:
        # 워크벤치 1번의 파이프라인 Job 생성
        job_id = generator.create_pipeline_job(workbench_id=1)
        print(f"Created pipeline job: {job_id}")
        
        # 생성된 Job 정의 확인
        job_definition = generator.generate_pipeline_from_workbench(workbench_id=1)
        print(f"Job definition created with {len(job_definition.steps)} steps")
        
    except Exception as e:
        print(f"Error: {e}")
