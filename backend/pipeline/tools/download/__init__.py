"""
Download tools module
다운로드 도구 모듈 - 다양한 다운로드 방식을 지원하는 통합 인터페이스
🚀 Plugins System Integration - No circular imports
"""

# plugins 폴더의 도구들을 import
from .plugins.local import execute_local_copy
from .plugins.server import execute_server_copy
from .plugins.ncbi import execute_ncbi_download

# 외부에서 사용할 함수들 (coordinator 제외)
__all__ = [
    'execute_local_copy',       # 개별 로컬 복사 함수
    'execute_server_copy',      # 개별 서버 복사 함수
    'execute_ncbi_download'     # 개별 NCBI 다운로드 함수
]