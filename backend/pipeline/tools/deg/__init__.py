"""
DEG (Differential Expression Gene) 분석 모듈

이 모듈은 차등발현유전자 분석을 위한 다양한 도구들을 제공합니다:
- edgeR: Trinity 기반 edgeR 분석
- DESeq2: R 스크립트 기반 DESeq2 분석
🚀 Plugins System Integration - No circular imports
"""

# plugins 폴더의 도구들을 import (필요시)
try:
    from .plugins.deseq2 import execute_deseq2
    from .plugins.edger import execute_edger
except ImportError:
    # 플러그인이 아직 구현되지 않은 경우 건너뛰기
    pass

__all__ = []  # 플러그인 시스템에서 coordinator를 직접 로드하므로 비워둠