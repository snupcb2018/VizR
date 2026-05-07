"""
Quality Control tools module
품질 관리 도구 모듈 - FastQC 등 QC 도구들을 지원하는 통합 인터페이스
"""

from .plugins.fastqc import execute_fastqc

# 외부에서 사용할 메인 함수들
__all__ = [
    'execute_fastqc'  # FastQC 실행 함수
]