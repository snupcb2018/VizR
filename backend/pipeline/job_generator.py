#!/usr/bin/env python3
"""
Pipeline Job Generator - Entry Point
새로운 모듈화된 구조로 리다이렉트
"""

# 새로운 모듈화된 구조에서 import
from .generator import PipelineJobGenerator

# 하위 호환성을 위한 기존 클래스들 re-export
from .generator.models import PipeLineStep, PipelineJobDefinition

# 기존 함수들도 여전히 사용 가능하도록 유지
__all__ = ['PipelineJobGenerator', 'PipeLineStep', 'PipelineJobDefinition']