#!/usr/bin/env python3
"""
Workbench Utility Functions
워크벤치 디렉토리 구조 생성 및 관리
"""

import os
import logging
from pathlib import Path
from typing import Dict, List

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

def create_workbench_directory_structure(workbench_path: str, workbench_name: str) -> Dict[str, str]:
    """
    표준 워크벤치 디렉토리 구조 생성
    
    Args:
        workbench_path: 워크벤치 기본 경로 (예: /vizr/workbench)
        workbench_name: 워크벤치 이름 (예: test_workbench)
        
    Returns:
        생성된 디렉토리 경로들의 딕셔너리
    """
    base_path = Path(workbench_path) / workbench_name
    
    # 표준 디렉토리 구조 정의
    directories = {
        'base': str(base_path),
        'deg': str(base_path / 'deg'),
        'log': str(base_path / 'log'),
        'report': str(base_path / 'report'),
        'visual': str(base_path / 'visual'),
        'work': str(base_path / 'work'),
        
        # quanti 하위 구조
        'quanti': str(base_path / 'quanti'),
        'quanti_counts': str(base_path / 'quanti' / 'counts'),
        'quanti_clean': str(base_path / 'quanti' / 'clean'),
        'quanti_qc': str(base_path / 'quanti' / 'qc'),
        'quanti_raw': str(base_path / 'quanti' / 'raw'),
        'quanti_samples': str(base_path / 'quanti' / 'samples'),
        
        # 추가 하위 구조
        'quanti_clean_prinseq': str(base_path / 'quanti' / 'clean' / 'prinseq'),
        'quanti_clean_trim': str(base_path / 'quanti' / 'clean' / 'trim'),
        'quanti_alignment': str(base_path / 'quanti' / 'alignment'),
        'quanti_abundance': str(base_path / 'quanti' / 'abundance')
    }
    
    logger.info(f"Creating workbench directory structure: {workbench_name}")
    
    # 디렉토리 생성
    created_dirs = []
    for dir_name, dir_path in directories.items():
        try:
            os.makedirs(dir_path, exist_ok=True)
            created_dirs.append(dir_name)
            logger.debug(f"Created directory: {dir_path}")
        except Exception as e:
            logger.error(f"Failed to create directory {dir_path}: {e}")
            raise
    
    # samples.txt 파일 생성 (기본 템플릿)
    samples_file = Path(directories['quanti_samples']) / 'samples.txt'
    if not samples_file.exists():
        with open(samples_file, 'w') as f:
            f.write("# Sample format: condition_name\tsample_name\tfile1_name\t[file2_name]\n")
            f.write("# Example for paired-end:\n")
            f.write("# control\tctrl_rep1\tctrl_rep1_R1.fastq.gz\tctrl_rep1_R2.fastq.gz\n")
            f.write("# treatment\ttreat_rep1\ttreat_rep1_R1.fastq.gz\ttreat_rep1_R2.fastq.gz\n")
    
    logger.info(f"Successfully created {len(created_dirs)} directories for workbench '{workbench_name}'")
    
    return directories

def get_workbench_structure_info(workbench_path: str, workbench_name: str) -> Dict[str, any]:
    """
    워크벤치 디렉토리 구조 정보 조회
    
    Args:
        workbench_path: 워크벤치 기본 경로
        workbench_name: 워크벤치 이름
        
    Returns:
        디렉토리 구조 정보
    """
    base_path = Path(workbench_path) / workbench_name
    
    if not base_path.exists():
        return {'exists': False, 'message': 'Workbench not found'}
    
    structure_info = {
        'exists': True,
        'base_path': str(base_path),
        'directories': {},
        'file_counts': {},
        'total_size': 0
    }
    
    # 각 디렉토리 정보 수집
    standard_dirs = ['deg', 'log', 'report', 'visual', 'work', 'quanti']
    quanti_subdirs = ['counts', 'clean', 'qc', 'raw', 'samples', 'alignment', 'abundance']
    
    for dir_name in standard_dirs:
        dir_path = base_path / dir_name
        if dir_path.exists():
            file_count = len(list(dir_path.rglob('*'))) if dir_path.is_dir() else 0
            structure_info['directories'][dir_name] = {
                'exists': True,
                'path': str(dir_path),
                'file_count': file_count
            }
        else:
            structure_info['directories'][dir_name] = {'exists': False}
    
    # quanti 하위 디렉토리 정보
    if (base_path / 'quanti').exists():
        structure_info['directories']['quanti']['subdirs'] = {}
        for subdir_name in quanti_subdirs:
            subdir_path = base_path / 'quanti' / subdir_name
            if subdir_path.exists():
                file_count = len(list(subdir_path.rglob('*'))) if subdir_path.is_dir() else 0
                structure_info['directories']['quanti']['subdirs'][subdir_name] = {
                    'exists': True,
                    'path': str(subdir_path),
                    'file_count': file_count
                }
            else:
                structure_info['directories']['quanti']['subdirs'][subdir_name] = {'exists': False}
    
    return structure_info

def validate_workbench_structure(workbench_path: str, workbench_name: str) -> Dict[str, any]:
    """
    워크벤치 구조 유효성 검사
    
    Args:
        workbench_path: 워크벤치 기본 경로
        workbench_name: 워크벤치 이름
        
    Returns:
        유효성 검사 결과
    """
    required_dirs = [
        'quanti/raw',      # 원본 데이터
        'quanti/samples',  # 샘플 정보
        'quanti/qc',       # QC 결과
        'quanti/clean',    # 정제된 데이터
        'log'              # 로그
    ]
    
    base_path = Path(workbench_path) / workbench_name
    validation_result = {
        'valid': True,
        'missing_dirs': [],
        'warnings': [],
        'recommendations': []
    }
    
    # 필수 디렉토리 확인
    for dir_path in required_dirs:
        full_path = base_path / dir_path
        if not full_path.exists():
            validation_result['missing_dirs'].append(dir_path)
            validation_result['valid'] = False
    
    # samples.txt 파일 확인
    samples_file = base_path / 'quanti' / 'samples' / 'samples.txt'
    if not samples_file.exists():
        validation_result['warnings'].append('samples.txt file not found')
        validation_result['recommendations'].append('Create samples.txt file in quanti/samples/')
    
    # 원본 데이터 확인
    raw_dir = base_path / 'quanti' / 'raw'
    if raw_dir.exists():
        raw_files = list(raw_dir.glob('*.fastq*')) + list(raw_dir.glob('*.fq*'))
        if not raw_files:
            validation_result['warnings'].append('No FASTQ files found in quanti/raw/')
            validation_result['recommendations'].append('Upload raw FASTQ files to quanti/raw/')
    
    return validation_result
