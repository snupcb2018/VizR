# backend/pipeline/tools/alignment/__init__.py
"""Alignment tools module - RNA-Seq read alignment functionality
🚀 Plugins System Integration - No circular imports"""

# plugins 폴더의 도구들을 import (필요시)
try:
    from .plugins.hisat2 import execute_hisat2
except ImportError:
    # 플러그인이 아직 구현되지 않은 경우 건너뛰기
    pass

__all__ = []  # 플러그인 시스템에서 coordinator를 직접 로드하므로 비워둠