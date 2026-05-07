#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VizR 통합 로깅 시스템
모든 백엔드 모듈의 로깅을 통합 관리하는 유틸리티
"""

import os
import logging
import time
from typing import Optional, Dict, Any
from pathlib import Path



def get_log_file_path() -> str:
    """
    로그 파일 경로를 가져옵니다.
    권한 문제를 피하기 위해 현재 작업 디렉토리 기준을 사용합니다.

    Returns:
        로그 파일의 절대 경로
    """
    # 현재 작업 디렉토리 기준으로 log/vizr.log 사용 (권한 문제 해결)
    return os.path.join(os.getcwd(), "log", "vizr.log")


def get_log_level() -> str:
    """
    백엔드 설정에서 로그 레벨을 가져옵니다.

    Returns:
        로그 레벨 문자열
    """
    try:
        from config.backend_settings import BackendConfig
        return BackendConfig.LOG_LEVEL
    except ImportError:
        return "DEBUG"  # 기본값을 DEBUG로 변경하여 모든 로그가 기록되도록 함


def create_console_handler() -> logging.StreamHandler:
    """
    표준 콘솔 핸들러를 생성합니다.

    Returns:
        설정된 콘솔 핸들러
    """
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # 로컬 타임존 사용 (기본값이 gmtime일 경우를 대비)
    formatter.converter = time.localtime
    handler.setFormatter(formatter)
    return handler


def create_file_handler(log_file_path: str) -> Optional[logging.FileHandler]:
    """
    파일 핸들러를 생성합니다.

    Args:
        log_file_path: 로그 파일 경로

    Returns:
        설정된 파일 핸들러 또는 None (실패 시)
    """
    try:
        # 로그 디렉토리 생성
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

        # UTF-8 인코딩 명시적 지정으로 한글 깨짐 방지
        handler = logging.FileHandler(log_file_path, encoding='utf-8')
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s - %(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        # 로컬 타임존 사용 (기본값이 gmtime일 경우를 대비)
        formatter.converter = time.localtime
        handler.setFormatter(formatter)
        return handler
    except Exception as e:
        # 파일 핸들러 생성 실패해도 계속 진행
        print(f"Warning: Failed to create file handler: {e}")
        return None


def setup_basic_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    기본 로거 핸들러를 설정합니다.

    Args:
        name: 로거 이름
        level: 로그 레벨 (None이면 설정에서 가져옴)

    Returns:
        설정된 로거
    """
    logger = logging.getLogger(name)

    # 중복 핸들러 방지를 위한 핸들러 정리
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    # 로그 레벨 설정
    if level is None:
        level = get_log_level()
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 콘솔 핸들러 생성
    console_handler = create_console_handler()
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)

    # 파일 핸들러 생성
    log_file_path = get_log_file_path()
    file_handler = create_file_handler(log_file_path)
    if file_handler:
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)

    return logger

def change_log_level(level: str, logger_name: Optional[str] = None) -> None:
    """
    로그 레벨을 변경합니다.

    Args:
        level: 새로운 로그 레벨 ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        logger_name: 특정 로거 이름 (사용하지 않음, 호환성 유지용)
    """
    try:
        log_level = getattr(logging, level.upper())
    except AttributeError:
        print(f"Warning: Invalid log level '{level}', using INFO")
        log_level = logging.INFO

    # 루트 로거의 레벨 변경
    logging.getLogger().setLevel(log_level)


def setup_module_logger(module_name: str, level: Optional[str] = None) -> logging.Logger:
    """
    모듈용 로거를 설정합니다. (선택된 코드 패턴 기반)

    이 함수는 기존 모듈들이 사용하던 로깅 설정 패턴을
    통합된 방식으로 대체합니다.

    Args:
        module_name: 모듈 이름 (__name__ 사용 권장)
        level: 로그 레벨 (None이면 설정에서 가져옴)

    Returns:
        설정된 로거

    Usage:
        # 기존 코드를 대체:
        # logger = logging.getLogger(__name__)
        # logger.handlers.clear()
        # ... 복잡한 핸들러 설정 ...

        # 새로운 방식:
        from backend.utils.logger import setup_module_logger
        logger = setup_module_logger(__name__, 'DEBUG')  # 레벨 직접 지정 가능
    """
    return setup_basic_logger(module_name, level)


# 편의 함수
def get_logger(name: str) -> logging.Logger:
    """
    로거를 가져오는 편의 함수

    Args:
        name: 로거 이름 (보통 __name__)

    Returns:
        설정된 로거
    """
    return setup_module_logger(name)