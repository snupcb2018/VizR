"""
VizR 공통 설정 모듈
백엔드/프론트엔드 모두에서 사용하는 공통 설정
"""
import json
import os
from pathlib import Path


def load_user_config():
    """config.json 파일을 로드합니다."""
    config_file = Path(__file__).parent.parent / 'config.json'
    
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"⚠️ config.json 로드 실패: {e}")
    
    # 기본 설정 반환
    return {
        'vizr_path': './',
        'environment': 'development',
        'log_level': 'INFO',
        'ports': {
            'backend': 5001,
            'frontend': 5173
        }
    }


def ensure_directory_exists(path):
    """디렉토리가 존재하지 않으면 생성합니다."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"❌ 디렉토리 생성 실패 {path}: {e}")
        return False


class SharedConfig:
    """백엔드/프론트엔드 공통 설정 클래스"""
    
    # 사용자 설정 로드
    _user_config = load_user_config()
    
    # vizr_path에서 workbench 경로 계산
    _vizr_path = _user_config.get('vizr_path', './')
    
    # Docker 컨테이너 내에서는 고정 경로 사용 (컨테이너 내부용)
    VIZR_PATH = os.getenv('VIZR_PATH', '/vizr')

    # 호스트 실제 경로 (Docker-in-Docker용)
    # 우선순위: 환경변수 > config.json > 기본값
    HOST_VIZR_PATH = os.getenv('HOST_VIZR_PATH', _vizr_path)
    
    # 환경 설정
    ENVIRONMENT = _user_config.get('environment', 'development')
    
    # 포트 설정
    BACKEND_PORT = _user_config.get('ports', {}).get('backend', 5001)
    FRONTEND_PORT = _user_config.get('ports', {}).get('frontend', 5173)
    
    # 로깅 설정
    LOG_LEVEL = _user_config.get('log_level', 'INFO')
    
    # 파이프라인 설정
    PIPELINE_MAX_WORKERS = _user_config.get('pipeline', {}).get('max_workers', 2)
    PIPELINE_TIMEOUT = _user_config.get('pipeline', {}).get('timeout', 3600)

    # Docker 이미지 설정
    TRINITY_IMAGE = _user_config.get('docker', {}).get('trinity_image', 'hjung200x/trinity-mfuzz:latest')

    # UI 설정
    UI_THEME = _user_config.get('ui', {}).get('theme', 'light')
    UI_LANGUAGE = _user_config.get('ui', {}).get('language', 'ko')
    
    @classmethod
    def init_directories(cls):
        """필요한 디렉토리들을 생성합니다."""
        directories = [
            cls.VIZR_PATH,
            str(Path(cls.VIZR_PATH) / 'users'),
            str(Path(cls.VIZR_PATH) / '.tmp'),
            str(Path(cls.VIZR_PATH) / 'logs')
        ]

        success = True
        for directory in directories:
            if not ensure_directory_exists(directory):
                success = False

        return success
    
    @classmethod
    def get_config_dict(cls):
        """설정을 딕셔너리 형태로 반환합니다."""
        return {
            'vizr_path': cls.VIZR_PATH,
            'host_vizr_path': cls.HOST_VIZR_PATH,
            'environment': cls.ENVIRONMENT,
            'backend_port': cls.BACKEND_PORT,
            'frontend_port': cls.FRONTEND_PORT,
            'log_level': cls.LOG_LEVEL,
            'pipeline_max_workers': cls.PIPELINE_MAX_WORKERS,
            'pipeline_timeout': cls.PIPELINE_TIMEOUT,
            'ui_theme': cls.UI_THEME,
            'ui_language': cls.UI_LANGUAGE
        }


# 설정 유효성 검사
def validate_config():
    """설정 유효성을 검사합니다."""
    config = SharedConfig()

    # VIZR_PATH 존재 검사
    if not Path(config.VIZR_PATH).exists():
        print(f"⚠️ VIZR 경로가 존재하지 않습니다: {config.VIZR_PATH}")
        return False

    # 포트 범위 검사
    if not (1024 <= config.BACKEND_PORT <= 65535) or not (1024 <= config.FRONTEND_PORT <= 65535):
        print("⚠️ 포트 번호는 1024-65535 범위여야 합니다.")
        return False

    return True


# 초기화 실행
if __name__ == "__main__":
    print("🔧 VizR 공통 설정 초기화...")
    
    if SharedConfig.init_directories():
        print("✅ 필요한 디렉토리 생성 완료")
    else:
        print("❌ 디렉토리 생성 중 오류 발생")
    
    if validate_config():
        print("✅ 설정 유효성 검사 통과")
    else:
        print("❌ 설정 유효성 검사 실패")
    
    print("\n📋 현재 설정:")
    for key, value in SharedConfig.get_config_dict().items():
        print(f"  {key}: {value}")
