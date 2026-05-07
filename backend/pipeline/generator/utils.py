#!/usr/bin/env python3
"""
Pipeline Job Generator Utilities
"""

import json
import os
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def generate_comparisons(sample_groups: Dict) -> List[Dict]:
    """샘플 그룹으로부터 비교 조합 생성"""
    groups = list(sample_groups.keys())
    comparisons = []
    
    # 모든 그룹 간 조합 생성
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            comparisons.append({
                "name": f"{groups[j]}_vs_{groups[i]}",
                "condition1": groups[j],
                "condition2": groups[i]
            })
    
    return comparisons


def parse_samples_data(samples_raw: sqlite3.Row, workbench_id: int) -> List[Dict]:
    """샘플 데이터 파싱 및 구조화"""
    samples = []
    if samples_raw and samples_raw['samples']:
        try:
            samples_json = json.loads(samples_raw['samples'])
            if isinstance(samples_json, list):
                for sample_data in samples_json:
                    # 각 샘플의 파일 경로들을 콤마로 연결
                    file_paths = []
                    if 'files' in sample_data and isinstance(sample_data['files'], list):
                        file_paths = [f['path'] if isinstance(f, dict) and 'path' in f else str(f) for f in sample_data['files']]
                    elif 'file1' in sample_data:
                        file_paths.append(sample_data['file1'])
                        if 'file2' in sample_data and sample_data['file2']:
                            file_paths.append(sample_data['file2'])
                    
                    # 샘플 정보를 딕셔너리 형태로 구성
                    sample_dict = {
                        'id': sample_data.get('id', sample_data.get('sampleName', '')),
                        'workbench_id': workbench_id,
                        'layout': samples_raw['layout'],
                        'samples': samples_raw['samples'],  # 원본 JSON 유지
                        'created_at': samples_raw['created_at'],
                        'file_paths': ','.join(file_paths) if file_paths else None,
                        'sample_name': sample_data.get('sampleName', sample_data.get('id', '')),
                        'condition': sample_data.get('condition', ''),
                        'replicate': sample_data.get('replicate', '')
                    }
                    samples.append(sample_dict)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.error(f"Failed to parse samples JSON for workbench {workbench_id}: {e}")
            samples = []
    
    return samples


def log_detailed_json(data: Any, title: str, logger_func=logger.info):
    """JSON 데이터를 상세하게 로깅"""
    logger_func(f"🔍 {title}")
    try:
        data_json = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        logger_func("─" * 80)
        for line_num, line in enumerate(data_json.split('\n'), 1):
            logger_func(f"{line_num:3d} │ {line}")
        logger_func("─" * 80)
    except Exception as e:
        logger.warning(f"⚠️ Failed to format JSON for {title}: {e}")
        logger_func(f"Raw data: {data}")


def extract_input_files_from_samples(samples: List[Dict], input_dir: str) -> List[str]:
    """샘플 데이터에서 입력 파일 목록 추출"""
    input_files = []
    
    try:
        # samples[0]['samples']에서 JSON 파싱하여 file1, file2 추출
        if len(samples) > 0 and 'samples' in samples[0]:
            samples_json = samples[0]['samples']
            logger.info(f"📊 [DEBUG] Parsing samples JSON for input files")
            
            # JSON 문자열 파싱
            samples_data = json.loads(samples_json)
            logger.info(f"📊 [DEBUG] Parsed {len(samples_data)} samples from JSON")
            
            # 각 샘플의 file1, file2를 추출하여 input_files에 추가
            for sample_info in samples_data:
                logger.info(f"📊 [DEBUG] Processing sample_info: {sample_info}")
                
                if 'file1' in sample_info and sample_info['file1']:
                    file1_path = os.path.join(input_dir, sample_info['file1'])
                    input_files.append(file1_path)
                    logger.info(f"📁 Added file1: {sample_info['file1']}")
                
                if 'file2' in sample_info and sample_info['file2']:
                    file2_path = os.path.join(input_dir, sample_info['file2'])
                    input_files.append(file2_path)
                    logger.info(f"📁 Added file2: {sample_info['file2']}")
        else:
            logger.warning("📊 [DEBUG] No samples data found or samples list is empty")
                
        logger.info(f"✅ Total input files extracted: {len(input_files)}")
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse samples JSON: {e}")
        input_files = []
    except Exception as e:
        logger.error(f"❌ Error processing samples for input files: {e}")
        input_files = []
    
    return input_files