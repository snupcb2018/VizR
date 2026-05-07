"""
VizR 백엔드 전용 설정 모듈
Flask 애플리케이션 및 백엔드 서비스를 위한 설정
"""
import os
from pathlib import Path
from .shared_config import SharedConfig


class BackendConfig:
    """백엔드 설정 클래스"""
    
    # 공통 설정 상속
    VIZR_DIR = SharedConfig.VIZR_PATH
    LOG_LEVEL = SharedConfig.LOG_LEVEL
    ENVIRONMENT = SharedConfig.ENVIRONMENT
    
    # Flask 기본 설정
    SECRET_KEY = os.getenv('SECRET_KEY', 'vizr-secret-key-change-in-production')
    DEBUG = ENVIRONMENT == 'development'
    
    # 파일 업로드 설정
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024 * 1024  # 10GB max file size

    # 데이터베이스 설정 - 절대 경로 사용 (멀티프로세싱 환경 호환성)
    DATABASE_FILE = os.getenv('DATABASE_FILE', str(Path(SharedConfig.VIZR_PATH) / 'vizr.db'))
    DATABASE_SCHEMA_FILE = str(Path(__file__).parent / 'database_schema.sql')
    
    # 로깅 설정 - VIZR_PATH/log 디렉토리에 배치
    LOG_FILE = os.getenv('LOG_FILE', str(Path(SharedConfig.VIZR_PATH) / 'log' / 'vizr.log'))
    
    # CORS 설정
    CORS_SUPPORTS_CREDENTIALS = True
    
    # 파이프라인 설정
    PIPELINE_MAX_WORKERS = SharedConfig.PIPELINE_MAX_WORKERS
    PIPELINE_TIMEOUT = SharedConfig.PIPELINE_TIMEOUT
    
    # Redis 설정 (선택적)
    USE_REDIS = os.getenv('USE_REDIS', 'false').lower() == 'true'
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    
    @staticmethod
    def init_app(app):
        """Flask 애플리케이션 초기화"""
        # 필요한 디렉토리들 생성 (사용자별 workbench는 워크벤치 생성 시 자동 생성됨)
        directories = [
            Path(BackendConfig.VIZR_DIR) / 'users',  # 사용자 디렉토리
            Path(BackendConfig.DATABASE_FILE).parent,
            Path(BackendConfig.LOG_FILE).parent
        ]

        for directory in directories:
            os.makedirs(directory, exist_ok=True)

        print(f"✅ 백엔드 설정 초기화 완료:")
        print(f"   루트 경로: {BackendConfig.VIZR_DIR}")
        print(f"   사용자 디렉토리: {Path(BackendConfig.VIZR_DIR) / 'users'}")
        print(f"   데이터베이스: {BackendConfig.DATABASE_FILE}")
        print(f"   로그: {BackendConfig.LOG_FILE}")


class DevelopmentConfig(BackendConfig):
    """개발 환경 설정"""
    DEBUG = True


class ProductionConfig(BackendConfig):
    """프로덕션 환경 설정"""
    DEBUG = False
    SECRET_KEY = os.getenv('SECRET_KEY')
    
    @classmethod
    def init_app(cls, app):
        BackendConfig.init_app(app)
        
        # 프로덕션 전용 초기화
        if not cls.SECRET_KEY:
            raise ValueError("SECRET_KEY must be set in production")


class TestingConfig(BackendConfig):
    """테스트 환경 설정"""
    TESTING = True
    DATABASE_FILE = ':memory:'  # 메모리 내 데이터베이스 사용


# 설정 매핑
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}