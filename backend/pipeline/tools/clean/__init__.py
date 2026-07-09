"""
Clean tools module
클린 도구 모듈 - Trimmomatic, PRINSEQ 등 전처리 도구들을 지원하는 통합 인터페이스
🚀 Plugins System Integration - No circular imports
"""

# plugins 폴더의 도구들을 import (필요시)
try:
    from .plugins.trimmomatic import execute_trimmomatic, execute_trimmomatic_multi
    from .plugins.prinseq import execute_prinseq, execute_prinseq_multi
except ImportError:
    # 플러그인이 아직 구현되지 않은 경우 건너뛰기
    pass

__all__ = []  # 플러그인 시스템에서 coordinator를 직접 로드하므로 비워둠