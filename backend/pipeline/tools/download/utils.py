"""
Common utilities for download operations
다운로드 작업에서 공통으로 사용되는 유틸리티 함수들
"""

import os
import sqlite3
import logging
from typing import List

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def get_workbench_id_from_step(job_step: sqlite3.Row) -> int:
    """스텝에서 워크벤치 ID 추출"""
    workbench_id = job_step['workbench_id']
    if workbench_id:
        return workbench_id
    else:
        raise ValueError("Workbench ID not found in job step")


def format_size(bytes_size: int) -> str:
    """파일 크기 포맷팅"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


def verify_copied_files(copied_files: List[str], target_path: str):
    """복사된 파일들의 무결성 검증"""
    for filename in copied_files:
        # 절대 경로인 경우와 파일명만인 경우 모두 처리
        if os.path.isabs(filename):
            file_path = os.path.join(target_path, os.path.basename(filename))
        else:
            file_path = os.path.join(target_path, filename)
            
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Copied file missing: {filename}")
    logger.info(f"✅ File integrity verification passed for {len(copied_files)} files")


def log_download_info(job_step: sqlite3.Row, download_type: str):
    """다운로드 작업 기본 정보 로깅"""
    workbench_id = get_workbench_id_from_step(job_step)
    input_dir = job_step['input_dir']
    output_dir = job_step['output_dir']
    
    logger.info(f"[{download_type.upper()}_DOWNLOAD] Standard structure:")
    logger.info(f"   🏷️  workbench_id: {workbench_id}")
    logger.info(f"   📋 job_step keys: {list(job_step.keys()) if job_step else 'None'}")
    logger.info(f"   📂 input_dir: {input_dir}")
    logger.info(f"   📂 output_dir: {output_dir}")
    
    return workbench_id, input_dir, output_dir


def ensure_output_directory(output_dir: str) -> str:
    """출력 디렉토리 생성 및 확인"""
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"[DOWNLOAD] Created/verified output directory: {output_dir}")
    return output_dir


def create_download_result_template() -> dict:
    """다운로드 결과 템플릿 생성"""
    return {
        'stdout': '', 
        'stderr': '', 
        'copied_files': [],
        'success': False
    }