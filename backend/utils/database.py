"""
Database utility functions for VizR
데이터베이스 연결 및 관리 유틸리티
"""

import sqlite3
import os
import logging
from contextlib import contextmanager
from typing import Optional, Any, List, Dict
import threading
from datetime import datetime
import time

from config.backend_settings import BackendConfig as Config


# 로거 설정
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

CONNECTION_TIMEOUT = 30.0
ROW_FACTORY = sqlite3.Row  # dict-like access to rows

# 스레드 로컬 저장소 (연결 풀링용)
_thread_local = threading.local()

def get_database_path() -> str:
    """
    데이터베이스 파일 절대 경로 반환 (멀티프로세싱 환경 호환성)
    설정 파일이 변경된 경우를 대비해 동적으로 확인

    Returns:
        str: 데이터베이스 파일 절대 경로
    """
    try:
        from config.backend_settings import BackendConfig as Config
        db_path = Config.DATABASE_FILE
    except (ImportError, AttributeError):
        db_path = Config.DATABASE_FILE

    # 절대 경로로 변환 (멀티프로세싱 환경에서 필수)
    return os.path.abspath(db_path)

def init_database():
    """Initialize database with schema if it doesn't exist."""

    db_file_path = get_database_path()
    logger.info(f"Database path: {db_file_path}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.debug(f"Database file exists: {os.path.exists(db_file_path)}")

    # 디렉토리 권한 확인
    db_dir = os.path.dirname(os.path.abspath(db_file_path))
    logger.debug(f"Database directory: {db_dir}")
    logger.debug(f"Directory exists: {os.path.exists(db_dir)}")
    if os.path.exists(db_dir):
        logger.debug(f"Directory writable: {os.access(db_dir, os.W_OK)}")

    if not os.path.exists(db_file_path):
        logger.info("Creating new database...")
        schema_file_path = Config.DATABASE_SCHEMA_FILE
        logger.info(f"Schema file path: {schema_file_path}")
        logger.info(f"Schema file exists: {os.path.exists(schema_file_path)}")

        with open(schema_file_path, 'r') as schema_file:
            schema = schema_file.read()

        with get_db_connection() as conn:
            conn.executescript(schema)
            conn.commit()
        logger.info("Database created successfully")
    else:
        logger.info("Database already exists")

    # Admin 계정 생성 (존재하지 않는 경우)
    _create_admin_user_if_not_exists()

def _create_admin_user_if_not_exists():
    """Create admin user if it doesn't exist"""
    from werkzeug.security import generate_password_hash

    try:
        # Check if admin user exists
        query = "SELECT id FROM users WHERE username = ?"
        results = execute_query(query, ('admin',))

        if not results:
            # Create admin user
            password_hash = generate_password_hash('admin')
            insert_query = """
                INSERT INTO users (username, email, password_hash, full_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """
            admin_id = execute_insert(
                insert_query,
                ('admin', 'admin@vizr.local', password_hash, 'Administrator', datetime.now().isoformat())
            )
            logger.info(f"Admin user created successfully with ID: {admin_id}")
        else:
            logger.info("Admin user already exists")

    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")

def create_connection(database_path: Optional[str] = None) -> sqlite3.Connection:
    """
    SQLite 데이터베이스에 연결
    
    Args:
        database_path (str, optional): 데이터베이스 파일 경로. 기본값은 설정 파일의 DATABASE_FILE
        
    Returns:
        sqlite3.Connection: 데이터베이스 연결 객체
        
    Raises:
        sqlite3.Error: 데이터베이스 연결 실패시
    """
    if database_path is None:
        database_path = get_database_path()

    # 절대 경로로 변환 (멀티프로세싱 환경 필수)
    abs_path = os.path.abspath(database_path)

    # 연결 전 상세 정보 로깅 (DEBUG 레벨로 변경)
    logger.debug(f"Attempting to connect to database: {abs_path}")
    logger.debug(f"File exists: {os.path.exists(abs_path)}")

    # 디렉토리 정보
    db_dir = os.path.dirname(abs_path)
    logger.debug(f"Database directory: {db_dir}")
    logger.debug(f"Directory exists: {os.path.exists(db_dir)}")

    # 권한 확인
    if os.path.exists(abs_path):
        logger.debug(f"File readable: {os.access(abs_path, os.R_OK)}")
        logger.debug(f"File writable: {os.access(abs_path, os.W_OK)}")
    elif os.path.exists(db_dir):
        logger.debug(f"Directory writable: {os.access(db_dir, os.W_OK)}")

    try:
        # 데이터베이스 연결 (절대 경로 사용)
        logger.debug(f"Connecting to SQLite database with absolute path: {abs_path}")
        conn = sqlite3.connect(
            abs_path,  # 절대 경로 사용
            timeout=CONNECTION_TIMEOUT,
            check_same_thread=False
        )
        
        # Row factory 설정 (dict-like access)
        conn.row_factory = ROW_FACTORY

        # 멀티프로세싱 환경 최적화 SQLite 설정
        conn.execute("PRAGMA foreign_keys = ON")  # 외래키 제약조건 활성화

        # WAL 모드 설정 및 확인 (멀티프로세싱 환경 필수)
        conn.execute("PRAGMA journal_mode = WAL")
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        if journal_mode != 'wal':
            logger.warning(f"WAL mode not applied. Current mode: {journal_mode}")
        else:
            logger.debug("SQLite WAL mode successfully activated")

        # 멀티프로세싱 동시성 최적화 설정
        conn.execute("PRAGMA synchronous = NORMAL")  # 성능과 안정성 균형
        conn.execute("PRAGMA wal_autocheckpoint = 100")  # WAL 체크포인트 설정 (더 자주 체크포인트)
        conn.execute("PRAGMA wal_synchronous = NORMAL")  # WAL 동기화 설정
        conn.execute("PRAGMA cache_size = 10000")  # 캐시 크기 증가
        conn.execute("PRAGMA temp_store = MEMORY")  # 임시 저장소 메모리 사용
        conn.execute("PRAGMA busy_timeout = 30000")  # 30초 대기 시간 설정

        # 멀티프로세싱 환경에서 파일 잠금 관련 설정
        conn.execute("PRAGMA locking_mode = NORMAL")  # 기본 잠금 모드 사용

        logger.debug(f"데이터베이스 연결 성공 (절대 경로): {abs_path}")
        return conn
        
    except sqlite3.Error as e:
        logger.error(f"SQLite 연결 실패: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Database absolute path was: {abs_path}")
        logger.error(f"Original path was: {database_path}")
        raise
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Database absolute path was: {abs_path}")
        raise sqlite3.Error(f"Database connection failed: {str(e)}")

def get_thread_connection() -> sqlite3.Connection:
    """
    현재 스레드의 데이터베이스 연결 반환 (연결 풀링)
    
    Returns:
        sqlite3.Connection: 현재 스레드의 데이터베이스 연결
    """
    if not hasattr(_thread_local, 'connection') or _thread_local.connection is None:
        _thread_local.connection = create_connection()
    
    return _thread_local.connection

def close_thread_connection():
    """현재 스레드의 데이터베이스 연결 종료"""
    if hasattr(_thread_local, 'connection') and _thread_local.connection is not None:
        try:
            _thread_local.connection.close()
            logger.debug("스레드 데이터베이스 연결 종료")
        except Exception as e:
            logger.warning(f"연결 종료 중 오류: {e}")
        finally:
            _thread_local.connection = None

def get_db_connection_simple(database_path: Optional[str] = None) -> sqlite3.Connection:
    """
    간단한 데이터베이스 연결 함수 (기존 코드 호환용)
    
    Args:
        database_path (str, optional): 데이터베이스 파일 경로
        
    Returns:
        sqlite3.Connection: 데이터베이스 연결 객체
        
    Example:
        conn = get_db_connection_simple()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        results = cursor.fetchall()
        conn.close()
    """
    return create_connection(database_path)

@contextmanager
def get_db_connection(database_path: Optional[str] = None):
    """
    데이터베이스 연결 컨텍스트 매니저

    Args:
        database_path (str, optional): 데이터베이스 파일 경로

    Yields:
        sqlite3.Connection: 데이터베이스 연결 객체

    Example:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            results = cursor.fetchall()
    """
    conn = None
    try:
        conn = create_connection(database_path)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"데이터베이스 작업 중 오류: {e}")
        raise
    finally:
        if conn:
            # WAL 체크포인트 강제 실행 (변경사항을 메인 DB 파일에 즉시 반영)
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception as checkpoint_error:
                logger.debug(f"WAL checkpoint 실패 (무시 가능): {checkpoint_error}")

            conn.close()
            # SQLite 연결 종료 후 약간의 지연 추가 (동시성 문제 완화)
            time.sleep(0.1)

@contextmanager
def get_db_cursor(database_path: Optional[str] = None):
    """
    데이터베이스 커서 컨텍스트 매니저 (자동 커밋)

    Args:
        database_path (str, optional): 데이터베이스 파일 경로

    Yields:
        sqlite3.Cursor: 데이터베이스 커서 객체

    Example:
        with get_db_cursor() as cursor:
            cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", ("John", "john@example.com"))
            user_id = cursor.lastrowid
    """
    conn = None
    try:
        conn = create_connection(database_path)
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"데이터베이스 작업 중 오류: {e}")
        raise
    finally:
        if conn:
            # WAL 체크포인트 강제 실행 (변경사항을 메인 DB 파일에 즉시 반영)
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception as checkpoint_error:
                logger.debug(f"WAL checkpoint 실패 (무시 가능): {checkpoint_error}")

            conn.close()
            # SQLite 연결 종료 후 약간의 지연 추가 (동시성 문제 완화)
            time.sleep(0.1)

def execute_query(query: str, params: tuple = (), database_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    SELECT 쿼리 실행 및 결과 반환
    
    Args:
        query (str): SQL 쿼리
        params (tuple): 쿼리 파라미터
        database_path (str, optional): 데이터베이스 파일 경로
        
    Returns:
        List[Dict[str, Any]]: 쿼리 결과 (딕셔너리 리스트)
        
    Example:
        results = execute_query("SELECT * FROM users WHERE id = ?", (1,))
    """
    with get_db_cursor(database_path) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def execute_insert(query: str, params: tuple = (), database_path: Optional[str] = None) -> int:
    """
    INSERT 쿼리 실행 및 생성된 ID 반환
    
    Args:
        query (str): SQL INSERT 쿼리
        params (tuple): 쿼리 파라미터
        database_path (str, optional): 데이터베이스 파일 경로
        
    Returns:
        int: 생성된 레코드의 ID (lastrowid)
        
    Example:
        user_id = execute_insert("INSERT INTO users (name, email) VALUES (?, ?)", ("John", "john@example.com"))
    """
    with get_db_cursor(database_path) as cursor:
        cursor.execute(query, params)
        return cursor.lastrowid

def execute_update(query: str, params: tuple = (), database_path: Optional[str] = None) -> int:
    """
    UPDATE/DELETE 쿼리 실행 및 영향받은 행 수 반환
    
    Args:
        query (str): SQL UPDATE/DELETE 쿼리
        params (tuple): 쿼리 파라미터
        database_path (str, optional): 데이터베이스 파일 경로
        
    Returns:
        int: 영향받은 행 수 (rowcount)
        
    Example:
        affected_rows = execute_update("UPDATE users SET email = ? WHERE id = ?", ("new@example.com", 1))
    """
    with get_db_cursor(database_path) as cursor:
        cursor.execute(query, params)
        return cursor.rowcount

def execute_many(query: str, params_list: List[tuple], database_path: Optional[str] = None) -> int:
    """
    여러 레코드에 대한 쿼리 일괄 실행
    
    Args:
        query (str): SQL 쿼리
        params_list (List[tuple]): 파라미터 리스트
        database_path (str, optional): 데이터베이스 파일 경로
        
    Returns:
        int: 영향받은 행 수
        
    Example:
        params = [("John", "john@example.com"), ("Jane", "jane@example.com")]
        affected_rows = execute_many("INSERT INTO users (name, email) VALUES (?, ?)", params)
    """
    with get_db_cursor(database_path) as cursor:
        cursor.executemany(query, params_list)
        return cursor.rowcount

def table_exists(table_name: str, database_path: Optional[str] = None) -> bool:
    """
    테이블 존재 여부 확인
    
    Args:
        table_name (str): 테이블 이름
        database_path (str, optional): 데이터베이스 파일 경로
        
    Returns:
        bool: 테이블 존재 여부
    """
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
    results = execute_query(query, (table_name,), database_path)
    return len(results) > 0

def get_table_info(table_name: str, database_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    테이블 구조 정보 반환
    
    Args:
        table_name (str): 테이블 이름
        database_path (str, optional): 데이터베이스 파일 경로
        
    Returns:
        List[Dict[str, Any]]: 테이블 컬럼 정보
    """
    query = f"PRAGMA table_info({table_name})"
    return execute_query(query, (), database_path)

def backup_database(backup_path: Optional[str] = None, database_path: Optional[str] = None) -> str:
    """
    데이터베이스 백업 생성
    
    Args:
        backup_path (str, optional): 백업 파일 경로. 기본값은 자동 생성
        database_path (str, optional): 원본 데이터베이스 파일 경로
        
    Returns:
        str: 생성된 백업 파일 경로
    """
    if database_path is None:
        database_path = get_database_path()
    
    if backup_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{database_path}.backup_{timestamp}"
    
    try:
        with sqlite3.connect(database_path) as source:
            with sqlite3.connect(backup_path) as backup:
                source.backup(backup)
        
        logger.info(f"데이터베이스 백업 완료: {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.error(f"데이터베이스 백업 실패: {e}")
        raise

def get_database_stats(database_path: Optional[str] = None) -> Dict[str, Any]:
    """
    데이터베이스 통계 정보 반환
    
    Args:
        database_path (str, optional): 데이터베이스 파일 경로
        
    Returns:
        Dict[str, Any]: 데이터베이스 통계 정보
    """
    if database_path is None:
        database_path = get_database_path()
    
    stats = {
        'file_size': os.path.getsize(database_path) if os.path.exists(database_path) else 0,
        'tables': {},
        'indexes': [],
        'triggers': []
    }
    
    try:
        # 테이블 목록 및 행 수
        tables = execute_query("SELECT name FROM sqlite_master WHERE type='table'", (), database_path)
        for table in tables:
            table_name = table['name']
            count_result = execute_query(f"SELECT COUNT(*) as count FROM {table_name}", (), database_path)
            stats['tables'][table_name] = count_result[0]['count'] if count_result else 0
        
        # 인덱스 목록
        indexes = execute_query("SELECT name FROM sqlite_master WHERE type='index'", (), database_path)
        stats['indexes'] = [idx['name'] for idx in indexes if idx['name'] is not None]
        
        # 트리거 목록
        triggers = execute_query("SELECT name FROM sqlite_master WHERE type='trigger'", (), database_path)
        stats['triggers'] = [tr['name'] for tr in triggers]
        
    except Exception as e:
        logger.error(f"데이터베이스 통계 수집 실패: {e}")
    
    return stats

# VizR 전용 유틸리티 함수들

def get_vizr_workbench_by_id(workbench_id: int) -> Optional[Dict[str, Any]]:
    """
    ID로 VizR 워크벤치 조회

    Args:
        workbench_id (int): 워크벤치 ID

    Returns:
        Optional[Dict[str, Any]]: 워크벤치 정보 또는 None
    """
    query = "SELECT * FROM vizr_workbench WHERE id = ?"
    results = execute_query(query, (workbench_id,))
    return results[0] if results else None

def get_user_by_workbench_id(workbench_id: int) -> Optional[Dict[str, Any]]:
    """
    워크벤치 ID로 사용자 조회

    Args:
        workbench_id (int): 워크벤치 ID

    Returns:
        Optional[Dict[str, Any]]: 사용자 정보 또는 None
    """
    query = """
        SELECT u.* FROM users u
        JOIN vizr_workbench w ON u.id = w.user_id
        WHERE w.id = ?
    """
    results = execute_query(query, (workbench_id,))
    return results[0] if results else None

def create_vizr_workbench(name: str, description: str, species: str, user_id: int) -> int:
    """
    새로운 VizR 워크벤치 생성
    
    Args:
        name (str): 워크벤치 이름
        description (str): 워크벤치 설명
        species (str): 종 정보
        user_id (int): 사용자 ID
        
    Returns:
        int: 생성된 워크벤치 ID
    """
    query = """
        INSERT INTO vizr_workbench (name, description, species, user_id)
        VALUES (?, ?, ?, ?)
    """
    return execute_insert(query, (name, description, species, user_id))

def update_vizr_workbench_status(workbench_id: int, status: str) -> int:
    """
    VizR 워크벤치 상태 업데이트
    
    Args:
        workbench_id (int): 워크벤치 ID
        status (str): 새로운 상태
        
    Returns:
        int: 영향받은 행 수
    """
    query = "UPDATE vizr_workbench SET status = ? WHERE id = ?"
    return execute_update(query, (status, workbench_id))

def get_vizr_workbenches_by_user(user_id: int) -> List[Dict[str, Any]]:
    """
    사용자의 VizR 워크벤치 목록 조회
    
    Args:
        user_id (int): 사용자 ID
        
    Returns:
        List[Dict[str, Any]]: 워크벤치 목록
    """
    query = """
        SELECT * FROM vizr_workbench 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    """
    return execute_query(query, (user_id,))

# 초기화 함수
def initialize_database():
    """데이터베이스 초기화 및 기본 설정"""
    try:
        # 설정에서 데이터베이스 경로 가져오기
        db_path = get_database_path()
        
        # 데이터베이스 파일 존재 확인
        if not os.path.exists(db_path):
            logger.warning(f"데이터베이스 파일이 존재하지 않습니다: {db_path}")
            return False
        
        # 연결 테스트
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            logger.info(f"SQLite 버전: {version}")
        
        # VizR 테이블 존재 확인
        vizr_tables = ['vizr_workbench', 'vizr_pipeline_configurations', 'vizr_pipeline_samples']
        missing_tables = []
        
        for table in vizr_tables:
            if not table_exists(table):
                missing_tables.append(table)
        
        if missing_tables:
            logger.warning(f"누락된 VizR 테이블: {missing_tables}")
            logger.info("migrate_new_schema.sql을 실행하여 테이블을 생성하세요.")
        else:
            logger.info("모든 VizR 테이블이 존재합니다.")
        
        return True
        
    except Exception as e:
        logger.error(f"데이터베이스 초기화 실패: {e}")
        return False