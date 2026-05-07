"""
PRINSEQ functionality for VizR pipeline
PRINSEQ 품질 조정 관련 함수들
"""

import json
import os
import sqlite3
import subprocess
import tempfile
import shutil
import time
import logging
from typing import Dict, List, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.utils.files import cleanup_temp_files, ensure_decompressed_files
# Process wrapper 추가
from backend.pipeline.utils.process_wrapper import ProcessWrapper, cleanup_temp_directory
# SharedState Events 추가
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.process_runner import ProcessPoolRunner

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def parse_prinseq_output(stdout: str, sample_name: str) -> Dict[str, Any]:
    """
    PRINSEQ stdout에서 결과 정보 파싱

    SE와 PE 모드의 두 가지 출력 형식을 모두 지원:
    - SE: "Input sequences: 21,917,767
           Good sequences: 21,054,717 (96.06%)
           Bad sequences: 863,050 (3.94%)"
    - PE: "Input sequences (file 1): 27,029,963
           Input sequences (file 2): 27,029,963
           Good sequences (pairs): 26,972,900
           Bad sequences (pairs): 57,063"

    Args:
        stdout: PRINSEQ 명령어 실행 결과
        sample_name: 샘플 이름

    Returns:
        dict: 파싱된 결과 정보
    """
    logger.info(f"🔍 [PRINSEQ-PARSER] Starting output parsing for sample: {sample_name}")

    result = {
        "sample_name": sample_name,
        "input_sequences": 0,
        "good_sequences": 0,
        "good_rate": 0.0,
        "bad_sequences": 0,
        "bad_rate": 0.0,
        "min_len_filtered": 0,
        "min_qual_mean_filtered": 0,
        "parsing_successful": False
    }

    try:
        # stdout 입력 검증
        if not stdout or not stdout.strip():
            logger.warning(f"⚠️ [PRINSEQ-PARSER] Empty or null stdout for sample {sample_name}")
            return result

        logger.info(f"📄 [PRINSEQ-PARSER] Raw stdout length: {len(stdout)} characters")
        logger.info(f"📄 [PRINSEQ-PARSER] Raw stdout preview (first 200 chars): {repr(stdout[:200])}")

        # stdout를 줄별로 분할하여 검색
        lines = stdout.strip().split('\n')
        logger.info(f"📝 [PRINSEQ-PARSER] Analyzing {len(lines)} lines of output")

        import re

        # PE/SE 모드 감지
        is_pe_mode = False
        input_file1 = 0
        input_file2 = 0

        # 각 패턴별로 검색
        input_sequences_found = False
        good_sequences_found = False
        bad_sequences_found = False
        min_len_filtered_found = False
        min_qual_mean_filtered_found = False

        for line_idx, line in enumerate(lines):
            # 중요한 라인만 로그 출력
            if any(keyword in line for keyword in ["Input sequences", "Good sequences", "Bad sequences", "min_len:", "min_qual_mean:"]):
                logger.info(f"📄 [PRINSEQ-PARSER] Line {line_idx + 1}: {line}")

            # PE 모드 감지: "Input sequences (file 1):" 패턴
            if "Input sequences (file 1):" in line:
                is_pe_mode = True
                input_pattern = r'Input sequences \(file 1\):\s*([\d,]+)'
                input_match = re.search(input_pattern, line)
                if input_match:
                    input_str = input_match.group(1).replace(',', '')
                    input_file1 = int(input_str)
                    logger.info(f"📊 [PRINSEQ-PARSER] PE Mode - Parsed input_file1: {input_file1}")

            # PE 모드: "Input sequences (file 2):" 패턴
            if "Input sequences (file 2):" in line:
                input_pattern = r'Input sequences \(file 2\):\s*([\d,]+)'
                input_match = re.search(input_pattern, line)
                if input_match:
                    input_str = input_match.group(1).replace(',', '')
                    input_file2 = int(input_str)
                    result["input_sequences"] = input_file1 + input_file2  # PE는 file1 + file2
                    input_sequences_found = True
                    logger.info(f"📊 [PRINSEQ-PARSER] PE Mode - Parsed input_file2: {input_file2}")
                    logger.info(f"📊 [PRINSEQ-PARSER] PE Mode - Total input_sequences: {result['input_sequences']}")

            # SE 모드: "Input sequences: 21,917,767" 패턴
            if "Input sequences:" in line and not is_pe_mode and not input_sequences_found:
                input_pattern = r'Input sequences:\s*([\d,]+)'
                input_match = re.search(input_pattern, line)
                if input_match:
                    input_str = input_match.group(1).replace(',', '')
                    result["input_sequences"] = int(input_str)
                    input_sequences_found = True
                    logger.info(f"📊 [PRINSEQ-PARSER] SE Mode - Parsed input_sequences: {result['input_sequences']}")

            # PE 모드: "Good sequences (pairs): 26,972,900" 패턴
            if "Good sequences (pairs):" in line and not good_sequences_found:
                good_pattern = r'Good sequences \(pairs\):\s*([\d,]+)'
                good_match = re.search(good_pattern, line)
                if good_match:
                    good_str = good_match.group(1).replace(',', '')
                    pairs = int(good_str)
                    result["good_sequences"] = pairs * 2  # PE는 pairs * 2
                    # PE 모드에서는 퍼센트가 없으므로 계산
                    if result["input_sequences"] > 0:
                        result["good_rate"] = (result["good_sequences"] / result["input_sequences"]) * 100
                    good_sequences_found = True
                    logger.info(f"📊 [PRINSEQ-PARSER] PE Mode - Parsed good_pairs: {pairs} → good_sequences: {result['good_sequences']} ({result['good_rate']:.2f}%)")

            # SE 모드: "Good sequences: 21,054,717 (96.06%)" 패턴
            if "Good sequences:" in line and not is_pe_mode and not good_sequences_found:
                good_pattern = r'Good sequences:\s*([\d,]+)\s*\(([0-9.]+)%\)'
                good_match = re.search(good_pattern, line)
                if good_match:
                    good_str = good_match.group(1).replace(',', '')
                    result["good_sequences"] = int(good_str)
                    result["good_rate"] = float(good_match.group(2))
                    good_sequences_found = True
                    logger.info(f"📊 [PRINSEQ-PARSER] SE Mode - Parsed good_sequences: {result['good_sequences']} ({result['good_rate']}%)")

            # PE 모드: "Bad sequences (pairs): 57,063" 패턴
            if "Bad sequences (pairs):" in line and not bad_sequences_found:
                bad_pattern = r'Bad sequences \(pairs\):\s*([\d,]+)'
                bad_match = re.search(bad_pattern, line)
                if bad_match:
                    bad_str = bad_match.group(1).replace(',', '')
                    pairs = int(bad_str)
                    result["bad_sequences"] = pairs * 2  # PE는 pairs * 2
                    # PE 모드에서는 퍼센트가 없으므로 계산
                    if result["input_sequences"] > 0:
                        result["bad_rate"] = (result["bad_sequences"] / result["input_sequences"]) * 100
                    bad_sequences_found = True
                    logger.info(f"📊 [PRINSEQ-PARSER] PE Mode - Parsed bad_pairs: {pairs} → bad_sequences: {result['bad_sequences']} ({result['bad_rate']:.2f}%)")

            # SE 모드: "Bad sequences: 863,050 (3.94%)" 패턴
            if "Bad sequences:" in line and not is_pe_mode and not bad_sequences_found:
                bad_pattern = r'Bad sequences:\s*([\d,]+)\s*\(([0-9.]+)%\)'
                bad_match = re.search(bad_pattern, line)
                if bad_match:
                    bad_str = bad_match.group(1).replace(',', '')
                    result["bad_sequences"] = int(bad_str)
                    result["bad_rate"] = float(bad_match.group(2))
                    bad_sequences_found = True
                    logger.info(f"📊 [PRINSEQ-PARSER] SE Mode - Parsed bad_sequences: {result['bad_sequences']} ({result['bad_rate']}%)")

            # "min_len: 862972" 패턴 찾기
            if "min_len:" in line and not min_len_filtered_found:
                min_len_pattern = r'min_len:\s*([\d,]+)'
                min_len_match = re.search(min_len_pattern, line)
                if min_len_match:
                    min_len_str = min_len_match.group(1).replace(',', '')
                    result["min_len_filtered"] = int(min_len_str)
                    min_len_filtered_found = True
                    logger.info(f"📊 [PRINSEQ-PARSER] Parsed min_len_filtered: {result['min_len_filtered']}")

            # "min_qual_mean: 78" 패턴 찾기
            if "min_qual_mean:" in line and not min_qual_mean_filtered_found:
                min_qual_pattern = r'min_qual_mean:\s*([\d,]+)'
                min_qual_match = re.search(min_qual_pattern, line)
                if min_qual_match:
                    min_qual_str = min_qual_match.group(1).replace(',', '')
                    result["min_qual_mean_filtered"] = int(min_qual_str)
                    min_qual_mean_filtered_found = True
                    logger.info(f"📊 [PRINSEQ-PARSER] Parsed min_qual_mean_filtered: {result['min_qual_mean_filtered']}")

        # PE 모드에서 Bad sequences (pairs) 라인이 없는 경우 자동 계산
        # PRINSEQ PE 모드에서는 "Bad sequences (pairs)" 라인을 생략하고 개별 필터 통계만 출력하는 경우가 있음
        if is_pe_mode and result["bad_sequences"] == 0:
            if result["input_sequences"] > 0 and result["good_sequences"] > 0:
                result["bad_sequences"] = result["input_sequences"] - result["good_sequences"]
                if result["input_sequences"] > 0:
                    result["bad_rate"] = (result["bad_sequences"] / result["input_sequences"]) * 100
                logger.info(f"🔧 [PRINSEQ-PARSER] PE Mode - Auto-calculated bad_sequences: {result['bad_sequences']} ({result['bad_rate']:.2f}%)")
                logger.info(f"💡 [PRINSEQ-PARSER] Calculation: Input({result['input_sequences']}) - Good({result['good_sequences']}) = Bad({result['bad_sequences']})")

        # 모든 필수 값이 파싱되었는지 확인
        logger.info(f"🔍 [PRINSEQ-PARSER] Validation check - Mode: {'PE' if is_pe_mode else 'SE'}, input: {result['input_sequences']}, good: {result['good_sequences']}, bad: {result['bad_sequences']}")

        if (result["input_sequences"] > 0 and
            result["good_sequences"] >= 0 and
            result["bad_sequences"] >= 0):

            # 데이터 일관성 검증
            calculated_total = result["good_sequences"] + result["bad_sequences"]
            if calculated_total == result["input_sequences"]:
                result["parsing_successful"] = True
                logger.info(f"✅ [PRINSEQ-PARSER] Successfully parsed and validated results for {sample_name} ({'PE' if is_pe_mode else 'SE'} mode)")
                logger.info(f"📊 [PRINSEQ-PARSER] Final results: Input={result['input_sequences']}, "
                          f"Good={result['good_sequences']} ({result['good_rate']:.2f}%), "
                          f"Bad={result['bad_sequences']} ({result['bad_rate']:.2f}%)")
            else:
                logger.warning(f"⚠️ [PRINSEQ-PARSER] Data inconsistency detected for {sample_name}: "
                             f"good({result['good_sequences']}) + bad({result['bad_sequences']}) = {calculated_total} "
                             f"!= input({result['input_sequences']})")
                result["parsing_successful"] = False
        else:
            logger.warning(f"⚠️ [PRINSEQ-PARSER] Invalid parsed values for {sample_name}: "
                         f"input={result['input_sequences']}, good={result['good_sequences']}, bad={result['bad_sequences']}")

        if not result["parsing_successful"]:
            logger.error(f"❌ [PRINSEQ-PARSER] Failed to parse PRINSEQ output for {sample_name}")
            logger.info(f"📝 [PRINSEQ-PARSER] Complete stdout for debugging:")
            for i, line in enumerate(lines[:10], 1):  # 처음 10줄만 상세 로그
                logger.info(f"   Line {i:2d}: {repr(line)}")
            if len(lines) > 10:
                logger.info(f"   ... and {len(lines) - 10} more lines")

    except Exception as e:
        logger.error(f"❌ [PRINSEQ-PARSER] Exception while parsing output for {sample_name}: {e}")
        logger.error(f"❌ [PRINSEQ-PARSER] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [PRINSEQ-PARSER] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")

    logger.info(f"🏁 [PRINSEQ-PARSER] Parsing completed for {sample_name}: {'SUCCESS' if result['parsing_successful'] else 'FAILED'}")
    return result


def send_prinseq_progress_update(workbench_id: int, progress_data: dict) -> bool:
    """
    PRINSEQ 진행률 직접 전송

    Args:
        workbench_id: 워크벤치 ID
        progress_data: 진행률 데이터 (completed_files, total_files, progress_percent)

    Returns:
        전송 성공 여부
    """
    try:
        from backend.pipeline.utils.redis_broker import get_redis_broker
        redis_broker = get_redis_broker()

        if not redis_broker.is_available():
            logger.debug(f"📡 [PRINSEQ-PROGRESS] Redis not available, skipping progress update")
            return False

        success = redis_broker.publish_progress(
            workbench_id=workbench_id,
            task_type='prinseq',
            progress_data=progress_data
        )

        if success:
            logger.debug(f"📡 [PRINSEQ-PROGRESS] Successfully sent progress update: {progress_data}")
        else:
            logger.warning(f"📡 [PRINSEQ-PROGRESS] Failed to send progress update")

        return success
    except Exception as e:
        logger.error(f"❌ [PRINSEQ-PROGRESS] Error sending progress update: {e}")
        return False


def _save_prinseq_progress_to_db(workbench_id: int, completed_files: int, total_files: int, shared_db_lock=None) -> bool:
    """
    PRINSEQ 진행률을 DB에 저장

    Args:
        workbench_id: 워크벤치 ID
        completed_files: 완료된 파일 수
        total_files: 전체 파일 수
        shared_db_lock: 멀티프로세스 간 공유 DB 락 (선택적)

    Returns:
        저장 성공 여부
    """
    logger.info(f"💾 [PRINSEQ-PROGRESS-DB] Starting to save progress: workbench={workbench_id}, completed={completed_files}/{total_files}")

    try:
        # 진행률 계산 및 검증
        if total_files <= 0:
            logger.warning(f"⚠️ [PRINSEQ-PROGRESS-DB] Invalid total_files: {total_files}")
            progress_percent = 0
        else:
            progress_percent = (completed_files / total_files * 100)
            progress_percent = min(100.0, max(0.0, progress_percent))  # 0-100 범위로 제한

        logger.info(f"📊 [PRINSEQ-PROGRESS-DB] Calculated progress: {progress_percent:.2f}% ({completed_files}/{total_files})")

        # 기존 데이터 로드하여 results 섹션 보존
        import time
        current_time = time.time()

        # 기존 progress_detail 가져오기
        existing_data = {}
        try:
            with database.get_db_connection() as conn:
                cursor = conn.cursor()
                result = cursor.execute('''
                    SELECT progress_detail FROM pipeline_job_steps
                    WHERE workbench_id = ? AND tool_name = 'prinseq'
                ''', (workbench_id,)).fetchone()

                if result and result[0]:
                    try:
                        existing_data = json.loads(result[0])
                        logger.info(f"✅ [PRINSEQ-PROGRESS-DB] Loaded existing data with {len(existing_data.get('results', {}))} results")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"⚠️ [PRINSEQ-PROGRESS-DB] Failed to parse existing data, initializing new: {e}")
                        existing_data = {"results": {}}
                else:
                    logger.info(f"ℹ️ [PRINSEQ-PROGRESS-DB] No existing data found, initializing new structure")
                    existing_data = {"results": {}}
        except Exception as e:
            logger.warning(f"⚠️ [PRINSEQ-PROGRESS-DB] Error loading existing data, initializing new: {e}")
            existing_data = {"results": {}}

        # 실제 성공한 샘플 수를 DB에서 계산
        actual_results = existing_data.get("results", {})
        actual_successful_results = sum(1 for r in actual_results.values() if r.get('parsing_successful', False))

        # 진행률 재계산 (실제 성공한 샘플 기준)
        if total_files > 0:
            actual_progress_percent = (actual_successful_results / total_files * 100)
            actual_progress_percent = min(100.0, max(0.0, actual_progress_percent))
        else:
            actual_progress_percent = 0.0

        logger.info(f"📊 [PRINSEQ-PROGRESS-DB] Actual successful samples: {actual_successful_results}/{total_files} ({actual_progress_percent:.2f}%)")

        # 기존 results 보존하고 summary만 업데이트 (실제 성공 샘플 수 기준)
        progress_data = {
            "results": actual_results,
            "summary": {
                "completed_files": actual_successful_results,
                "total_files": total_files,
                "progress_percent": round(actual_progress_percent, 2),
                "last_updated": current_time
            },
            "completed_files": actual_successful_results,
            "total_files": total_files,
            "progress_percent": round(actual_progress_percent, 2),
            "last_updated": current_time
        }

        logger.info(f"📈 [PRINSEQ-PROGRESS-DB] Progress data with {len(progress_data['results'])} preserved results")

        # JSON 직렬화 테스트
        try:
            json_str = json.dumps(progress_data)
            json_size = len(json_str)
            logger.info(f"📦 [PRINSEQ-PROGRESS-DB] JSON serialization successful: {json_size} characters")
        except (TypeError, ValueError) as e:
            logger.error(f"❌ [PRINSEQ-PROGRESS-DB] JSON serialization failed: {e}")
            return False

        # DB 업데이트 실행 (shared_db_lock으로 보호)
        import multiprocessing as mp
        current_process = mp.current_process()
        if shared_db_lock is not None:
            logger.info(f"🔒 [PRINSEQ-PROGRESS-DB-LOCK-ENTER] PID={current_process.pid} ATTEMPTING lock acquisition for progress update")

            with shared_db_lock:
                logger.info(f"✅ [PRINSEQ-PROGRESS-DB-LOCK-ACQUIRED] PID={current_process.pid} ENTERED critical section for progress update")
                success = _execute_prinseq_progress_db_update(workbench_id, json_str, current_process.pid)
                logger.info(f"🔓 [PRINSEQ-PROGRESS-DB-LOCK-EXIT] PID={current_process.pid} LEAVING critical section for progress update")
                return success
        else:
            logger.warning(f"⚠️ [PRINSEQ-PROGRESS-DB] No shared_db_lock provided - proceeding without lock protection")
            return _execute_prinseq_progress_db_update(workbench_id, json_str, current_process.pid)

    except Exception as e:
        logger.error(f"❌ [PRINSEQ-PROGRESS-DB] Critical error saving progress to DB: {e}")
        logger.error(f"❌ [PRINSEQ-PROGRESS-DB] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [PRINSEQ-PROGRESS-DB] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")
        return False


def _execute_prinseq_progress_db_update(workbench_id: int, json_str: str, pid: int) -> bool:
    """진행률 DB 업데이트를 실행하는 헬퍼 함수"""
    try:
        logger.info(f"💾 [PRINSEQ-PROGRESS-DB] Updating pipeline_job_steps table... (PID={pid})")

        with database.get_db_connection() as conn:
            cursor = conn.cursor()

            # 업데이트 실행
            cursor.execute('''
                UPDATE pipeline_job_steps
                SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workbench_id = ? AND tool_name = 'prinseq'
            ''', (json_str, workbench_id))

            # 업데이트된 행 수 확인
            rows_affected = cursor.rowcount
            logger.info(f"📊 [PRINSEQ-PROGRESS-DB] Database update affected {rows_affected} row(s) (PID={pid})")

            if rows_affected == 0:
                logger.warning(f"⚠️ [PRINSEQ-PROGRESS-DB] No rows were updated - pipeline step may not exist for workbench {workbench_id} (PID={pid})")
                return False

            conn.commit()
            logger.info(f"✅ [PRINSEQ-PROGRESS-DB] Database transaction committed successfully (PID={pid})")

        return True

    except Exception as e:
        logger.error(f"❌ [PRINSEQ-PROGRESS-DB] Database update failed (PID={pid}): {e}")
        return False


def _save_prinseq_result_to_db(workbench_id: int, sample_name: str, result_data: Dict[str, Any], shared_db_lock=None) -> bool:
    """
    개별 샘플의 PRINSEQ 결과를 DB에 저장

    Args:
        workbench_id: 워크벤치 ID
        sample_name: 샘플 이름
        result_data: 파싱된 결과 데이터
        shared_db_lock: 멀티프로세스 간 공유 DB 락 (선택적)

    Returns:
        저장 성공 여부
    """
    logger.info(f"💾 [PRINSEQ-RESULT-DB] Starting to save sample result: {sample_name} for workbench {workbench_id}")

    try:
        # 입력 데이터 검증
        if not result_data or not isinstance(result_data, dict):
            logger.warning(f"⚠️ [PRINSEQ-RESULT-DB] Invalid result_data for sample {sample_name}: {result_data}")
            return False

        # 파싱 성공 여부 확인
        parsing_successful = result_data.get('parsing_successful', False)
        logger.info(f"📊 [PRINSEQ-RESULT-DB] Sample {sample_name} parsing status: {'SUCCESS' if parsing_successful else 'FAILED'}")

        if parsing_successful:
            logger.info(f"📈 [PRINSEQ-RESULT-DB] Sample {sample_name} results: "
                       f"Input={result_data.get('input_sequences', 0)}, "
                       f"Good={result_data.get('good_sequences', 0)} ({result_data.get('good_rate', 0):.1f}%), "
                       f"Bad={result_data.get('bad_sequences', 0)} ({result_data.get('bad_rate', 0):.1f}%)")

        # 프로세스 정보 수집
        import multiprocessing as mp
        current_process = mp.current_process()
        process_info = f"PID={current_process.pid}, Name={current_process.name}"

        # Lock 진입 시도 로그
        logger.info(f"🔒 [PRINSEQ-DB-LOCK-ENTER] PID={current_process.pid} ATTEMPTING lock acquisition - {process_info}, Sample: {sample_name}, Workbench: {workbench_id}")

        # 전달받은 shared_db_lock 사용
        logger.info(f"🔍 [PRINSEQ-DB-LOCK-DEBUG] Using passed shared_db_lock: {shared_db_lock}")
        logger.info(f"🔍 [PRINSEQ-DB-LOCK-DEBUG] shared_db_lock type: {type(shared_db_lock)}")

        if shared_db_lock is not None:
            # 전달받은 Lock 사용
            with shared_db_lock:
                logger.info(f"✅ [PRINSEQ-DB-LOCK-ACQUIRED] PID={current_process.pid} ENTERED critical section WITH SHARED LOCK - {process_info}, Sample: {sample_name}")
                result = _execute_prinseq_db_operations_impl(current_process, process_info, sample_name, workbench_id, result_data)
                logger.info(f"🔓 [PRINSEQ-DB-LOCK-EXIT] PID={current_process.pid} LEAVING critical section - {process_info}, Sample: {sample_name}")
        else:
            logger.error(f"❌ [PRINSEQ-DB-LOCK] No shared_db_lock provided - this should not happen!")
            return False

        if result:
            logger.info(f"🎉 [PRINSEQ-RESULT-DB] Successfully saved sample result for {sample_name}")

        return result

    except Exception as e:
        logger.error(f"❌ [PRINSEQ-RESULT-DB] Critical error saving sample result for {sample_name}: {e}")
        logger.error(f"❌ [PRINSEQ-RESULT-DB] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [PRINSEQ-RESULT-DB] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")
        return False


def _execute_prinseq_db_operations_impl(current_process, process_info: str, sample_name: str, workbench_id: int, result_data: Dict[str, Any]) -> bool:
    """실제 PRINSEQ 데이터베이스 작업을 수행하는 구현 함수"""
    try:
        # 기존 progress_detail 가져오기
        logger.info(f"🔍 [PRINSEQ-RESULT-DB] Retrieving existing progress_detail from DB...")
        existing_data = {}

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            result = cursor.execute('''
                SELECT progress_detail FROM pipeline_job_steps
                WHERE workbench_id = ? AND tool_name = 'prinseq'
            ''', (workbench_id,)).fetchone()

            if result and result[0]:
                try:
                    existing_data = json.loads(result[0])
                    logger.info(f"✅ [PRINSEQ-RESULT-DB] Successfully loaded existing progress_detail: {len(existing_data.get('results', {}))} existing results")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ [PRINSEQ-RESULT-DB] Failed to parse existing progress_detail, initializing new: {e}")
                    existing_data = {"summary": {}, "results": {}}
            else:
                logger.info(f"ℹ️ [PRINSEQ-RESULT-DB] No existing progress_detail found, initializing new structure")
                existing_data = {"summary": {}, "results": {}}

        # 기존 구조 확인 및 보정
        if "results" not in existing_data:
            existing_data["results"] = {}
            logger.info(f"🔧 [PRINSEQ-RESULT-DB] Added missing 'results' section to progress_detail")

        if "summary" not in existing_data:
            existing_data["summary"] = {}
            logger.info(f"🔧 [PRINSEQ-RESULT-DB] Added missing 'summary' section to progress_detail")

        # results 섹션에 샘플 결과 추가
        previous_result = existing_data["results"].get(sample_name)
        existing_data["results"][sample_name] = result_data

        if previous_result:
            logger.info(f"🔄 [PRINSEQ-RESULT-DB] Updated existing result for sample {sample_name}")
        else:
            logger.info(f"➕ [PRINSEQ-RESULT-DB] Added new result for sample {sample_name}")

        # 현재 총 결과 수 확인
        total_results = len(existing_data["results"])

        # 디버깅: 각 샘플의 parsing_successful 상태 확인
        logger.info(f"🔍 [PRINSEQ-RESULT-DB] Debugging - analyzing {total_results} results:")
        for sample_key, sample_result in existing_data["results"].items():
            parsing_status = sample_result.get('parsing_successful', False)
            logger.info(f"   ├─ {sample_key}: parsing_successful = {parsing_status}")

        successful_results = sum(1 for r in existing_data["results"].values() if r.get('parsing_successful', False))

        logger.info(f"📊 [PRINSEQ-RESULT-DB] Current results summary: {successful_results}/{total_results} samples with successful parsing")

        # Summary 섹션 업데이트 (results와 동시에 업데이트하여 데이터 일관성 보장)
        import time
        current_time = time.time()

        # 기존 summary에서 total_files 정보 유지, 없으면 현재 결과 수를 기본값으로 사용
        existing_summary = existing_data.get("summary", {})
        total_files = existing_summary.get("total_files", total_results)

        # 진행률 계산
        if total_files > 0:
            progress_percent = (successful_results / total_files) * 100
        else:
            progress_percent = 0.0

        # Summary 데이터 업데이트
        updated_summary = {
            "completed_files": successful_results,
            "total_files": total_files,
            "progress_percent": round(progress_percent, 2),
            "last_updated": current_time
        }

        existing_data["summary"] = updated_summary

        logger.info(f"📈 [PRINSEQ-RESULT-DB] Updated summary: {successful_results}/{total_files} ({progress_percent:.1f}%)")

        # JSON 직렬화 테스트
        try:
            json_str = json.dumps(existing_data)
            json_size = len(json_str)
            logger.info(f"📦 [PRINSEQ-RESULT-DB] JSON serialization successful: {json_size} characters")
        except (TypeError, ValueError) as e:
            logger.error(f"❌ [PRINSEQ-RESULT-DB] JSON serialization failed: {e}")
            return False

        # UPDATE 직전 상태 로그 출력
        logger.debug(f"💾 [PRINSEQ-DB-UPDATE-BEFORE] PID={current_process.pid} About to update prinseq step, Sample: {sample_name}, Total results: {total_results}, Successful: {successful_results}")

        # DB 업데이트 실행
        logger.info(f"💾 [PRINSEQ-RESULT-DB] Updating pipeline_job_steps table...")

        with database.get_db_connection() as conn:
            cursor = conn.cursor()

            # 업데이트 실행
            cursor.execute('''
                UPDATE pipeline_job_steps
                SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workbench_id = ? AND tool_name = 'prinseq'
            ''', (json_str, workbench_id))

            # 업데이트된 행 수 확인
            rows_affected = cursor.rowcount
            logger.info(f"📊 [PRINSEQ-RESULT-DB] Database update affected {rows_affected} row(s)")

            if rows_affected == 0:
                logger.warning(f"⚠️ [PRINSEQ-RESULT-DB] No rows were updated - pipeline step may not exist for workbench {workbench_id}")
                return False

            conn.commit()
            logger.info(f"✅ [PRINSEQ-RESULT-DB] Database transaction committed successfully")

        logger.debug(f"💾 [PRINSEQ-DB-UPDATE-AFTER] PID={current_process.pid} Successfully updated prinseq step, Sample: {sample_name}")

        # Lock 해제 직전 로그 (공유 Lock 사용)
        logger.debug(f"🔓 [PRINSEQ-DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, Sample: {sample_name}, Operation: SUCCESS")

        return True

    except Exception as e:
        logger.error(f"❌ [PRINSEQ-RESULT-DB] Failed to save sample result for {sample_name}: {e}")
        # Lock 해제 직전 로그 (에러 상황, 공유 Lock 사용)
        logger.debug(f"🔓 [PRINSEQ-DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, Sample: {sample_name}, Operation: ERROR")
        return False


def execute_prinseq(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    """
    PRINSEQ 실행 - job_step에서 직접 정보 추출
    """
    # job_step에서 직접 정보 추출 (step_details 개념 제거)
    step_id = job_step['step_id']
    job_id = job_step['job_id']
    parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
    workbench_id = job_step['workbench_id']

    # workbench 정보 조회
    with database.get_db_connection() as db_connection:
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT * FROM vizr_workbench 
            WHERE id = ?
        """, (workbench_id,))
        workbench = cursor.fetchone()
        
    if not workbench:
        raise ValueError(f"Workbench {workbench_id} not found")
        
    workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])

    logger.info(f"🧹 [PRINSEQ] Starting PRINSEQ process")
    logger.info(f"📋 [PRINSEQ] Job Configuration:")
    logger.info(f"   └─ workbench_id: {workbench_id}")
    logger.info(f"   └─ step_id: {step_id}")
    
    # 입력 파일 결정 (job_step에서 직접 가져오기)
    output_dir = os.path.join(workbench_schema["quanti"]["clean"], "prinseq")

    # PRINSEQ 출력 디렉토리 구조 생성: prinseq/{group_name}/{sample}/good|bad
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"📁 [PRINSEQ] Created output directory: {output_dir}")
    
    # samples_data에서 직접 sample_info_list 구성  
    sample_info_list = []
    
    # workbench_id에서 샘플 정보와 layout 정보 조회
    workbench_id = job_step['workbench_id']
    with database.get_db_connection() as db_connection:
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT samples, layout 
            FROM vizr_pipeline_samples 
            WHERE workbench_id = ?
        """, (workbench_id,))
        pipeline_samples_result = cursor.fetchone()
        
        if pipeline_samples_result:
            samples_json = pipeline_samples_result['samples']
            layout = pipeline_samples_result['layout']
            logger.info(f"📊 [PRINSEQ] Retrieved samples from vizr_pipeline_samples (layout: {layout})")
            
            try:
                # JSON 파싱하여 rows에 할당
                samples_data = json.loads(samples_json)
                logger.info(f"✅ [PRINSEQ] {len(samples_data)} samples")
            except json.JSONDecodeError as e:
                logger.error(f"❌ [PRINSEQ] Failed to parse samples JSON from vizr_pipeline_samples: {e}")
        else:
            logger.warning(f"⚠️  [PRINSEQ] No samples found in vizr_pipeline_samples for workbench_id: {workbench_id}")
            layout = 'pe'  # 기본값
    
    logger.info(f"🔍 [PRINSEQ-DEBUG] Layout 정보: {layout}")
    
    # samples_data로 직접 sample_info_list 구성
    logger.info(f"🛠️  [PRINSEQ] Building sample configuration from DB samples...")
    
    # parameters 정보로부터 앞전의 단계가 trimmomatic 단계였는지 확인한다. is_after_download 할당.
    clean_tools = parameters.get('clean_tools', ['prinseq'])
    is_after_download = 'trimmomatic' not in clean_tools

    logger.info(f"⚙️ [PRINSEQ] Configuration analysis:")
    logger.info(f"   ├─ Clean tools: {clean_tools}")
    logger.info(f"   ├─ Is after download: {is_after_download}")
    logger.info(f"   └─ Execution mode: {'Download → PRINSEQ' if is_after_download else 'Download → Trimmomatic → PRINSEQ'}")
    
    if is_after_download:
        # Download 후 바로 실행되는 경우: pipeline_job_generator.py 1022라인 로직 적용
        logger.info(f"📊 [PRINSEQ] Processing {len(samples_data)} samples from job definition")
        
        input_dir = workbench_schema["quanti"]["raw"]

        # 각 샘플의 file1, file2를 추출하여 파일 경로 구성
        for sample_info in samples_data:
            sample_name = sample_info['sampleName']
            group_name = sample_info['groupName']
            
            files = {}

            if 'file1' in sample_info and sample_info['file1']:
                file1_name = sample_info['file1']

                # Check for uncompressed file first, then compressed file
                # PRINSEQ can read .gz files natively, so we use whichever is available
                uncompressed_name = file1_name.replace('.gz', '') if file1_name.endswith('.gz') else file1_name
                uncompressed_path = os.path.join(input_dir, uncompressed_name)
                compressed_path = os.path.join(input_dir, file1_name if file1_name.endswith('.gz') else file1_name + '.gz')

                if os.path.exists(uncompressed_path):
                    # Prefer uncompressed file if available
                    file1_path = uncompressed_path
                    logger.debug(f"📁 Added file1 (uncompressed): {uncompressed_name}")
                elif os.path.exists(compressed_path):
                    # Use compressed file (PRINSEQ supports .gz natively)
                    file1_path = compressed_path
                    logger.debug(f"📁 Added file1 (compressed): {os.path.basename(compressed_path)}")
                else:
                    # File not found in either format
                    raise FileNotFoundError(
                        f"Input file not found: {uncompressed_name} or {os.path.basename(compressed_path)} "
                        f"in directory: {input_dir}"
                    )

                if layout == 'pe':
                    files['R1'] = file1_path
                else:  # SE
                    files['SE'] = file1_path

            if 'file2' in sample_info and sample_info['file2']:
                file2_name = sample_info['file2']

                # Check for uncompressed file first, then compressed file
                uncompressed_name = file2_name.replace('.gz', '') if file2_name.endswith('.gz') else file2_name
                uncompressed_path = os.path.join(input_dir, uncompressed_name)
                compressed_path = os.path.join(input_dir, file2_name if file2_name.endswith('.gz') else file2_name + '.gz')

                if os.path.exists(uncompressed_path):
                    # Prefer uncompressed file if available
                    file2_path = uncompressed_path
                    logger.debug(f"📁 Added file2 (uncompressed): {uncompressed_name}")
                elif os.path.exists(compressed_path):
                    # Use compressed file (PRINSEQ supports .gz natively)
                    file2_path = compressed_path
                    logger.debug(f"📁 Added file2 (compressed): {os.path.basename(compressed_path)}")
                else:
                    # File not found in either format
                    raise FileNotFoundError(
                        f"Input file not found: {uncompressed_name} or {os.path.basename(compressed_path)} "
                        f"in directory: {input_dir}"
                    )

                files['R2'] = file2_path
            
            sample_info_dict = {
                'sample_name': sample_name,
                'group_name': group_name,
                'files': files,
                'output_base_dir': output_dir
            }
            sample_info_list.append(sample_info_dict)
            
            file_type = 'PE' if 'R2' in files else 'SE'
            logger.info(f"   ├─ Sample: {sample_name}")
            logger.info(f"   │   ├─ Condition: {group_name}")
            logger.info(f"   │   ├─ File type: {file_type}")
            if file_type == 'PE':
                logger.info(f"   │       ├─ R1: {os.path.basename(files['R1'])}")
                logger.info(f"   │       └─ R2: {os.path.basename(files['R2'])}")
            else:
                logger.info(f"   │       └─ SE: {os.path.basename(files['SE'])}")

    else:
        input_dir = os.path.join(workbench_schema["quanti"]["clean"], "trim")
        for sample in samples_data:
            sample_name = sample['sampleName']
            group_name = sample['groupName']
            
            # 파일 경로 구성 (처리된 파일명으로 변환)
            if layout == 'pe':
                # PE: {group_name}/{sample_name}/{sample_name}_1_paired.fastq, {sample_name}_2_paired.fastq
                files = {
                    'R1': os.path.join(input_dir, f"{group_name}", f"{sample_name}", f"{sample_name}_1_paired.fastq"),
                    'R2': os.path.join(input_dir, f"{group_name}", f"{sample_name}", f"{sample_name}_2_paired.fastq")
                }
                file_type = 'PE'
            else:  # SE
                # SE: {group_name}/{sample_name}/{sample_name}_trimmed.fastq
                files = {
                    'SE': os.path.join(input_dir, f"{group_name}", f"{sample_name}", f"{sample_name}_trimmed.fastq")
                }
                file_type = 'SE'
            
            sample_info = {
                'sample_name': sample_name,
                'group_name': group_name,
                'files': files,
                'output_base_dir': output_dir
            }
            sample_info_list.append(sample_info)
            
            logger.info(f"   ├─ Sample: {sample_name}")
            logger.info(f"   │   ├─ Condition: {group_name}")
            logger.info(f"   │   ├─ File type: {file_type}")
            logger.info(f"   │   └─ Output dir: {os.path.join(output_dir, group_name, sample_name)}")
            if file_type == 'PE':
                logger.info(f"   │       ├─ R1: {files['R1']}")
                logger.info(f"   │       └─ R2: {files['R2']}")
            else:
                logger.info(f"   │       └─ SE: {files['SE']}")
    
    logger.info(f"✅ [PRINSEQ] Configuration completed:")
    logger.info(f"   ├─ Total samples: {len(sample_info_list)}")
    logger.info(f"   ├─ SE samples: {sum(1 for s in sample_info_list if 'SE' in s['files'])}")
    logger.info(f"   └─ PE samples: {sum(1 for s in sample_info_list if 'R1' in s['files'] and 'R2' in s['files'])}")
    
    # PRINSEQ 파라미터 로그
    logger.info(f"⚙️  [PRINSEQ] Parameters:")
    prinseq_params = {k: v for k, v in parameters.items() if k.startswith('prinseq_')}
    if prinseq_params:
        for key, value in prinseq_params.items():
            logger.info(f"   ├─ {key}: {value}")
    else:
        logger.info(f"   └─ Using default parameters")
    logger.info(f"   └─ concurrent_jobs: {parameters.get('concurrent_jobs', 2)}")
    
    # ✅ execute_prinseq_multi() 호출 (worker_id와 workbench_id 전달)
    logger.info(f"🚀 [PRINSEQ] Initiating multi-processing execution...")
    return execute_prinseq_multi(sample_info_list, parameters, workbench_id, worker_id)

def execute_prinseq_multi(sample_info_list: List[Dict], parameters: Dict, workbench_id: int, worker_id: str = "worker") -> Dict[str, str]:
    """
    PRINSEQ SE/PE 통합 처리 (멀티프로세싱)
    SharedState Event 기반 stop 신호 처리
    실시간 진행률 전송 및 DB 저장
    """
    import time

    logger.info(f"🚀 [PRINSEQ-MULTI] Starting multi-processing execution")
    logger.info(f"📊 [PRINSEQ-MULTI] Configuration:")
    logger.info(f"   ├─ Samples: {len(sample_info_list)}")
    logger.info(f"   ├─ Worker ID: {worker_id}")
    logger.info(f"   ├─ Workbench ID: {workbench_id}")
    logger.info(f"   └─ Concurrent jobs: {parameters.get('concurrent_jobs', 4)}")

    start_time = time.time()
    concurrent_jobs = min(parameters.get('concurrent_jobs', 4), len(sample_info_list))
    
    # SharedState에서 해당 워커의 Event 가져오기
    try:
        worker_stop_event = shared_state.get_worker_event(worker_id)
        logger.info(f"✅ [PRINSEQ-MULTI] SharedState Event retrieved for worker: {worker_id}")
    except Exception as e:
        logger.error(f"❌ [PRINSEQ-MULTI] Failed to get worker event: {e}")
        return {
            'success': False,
            'message': f'Failed to get worker event: {str(e)}',
            'processed_samples': 0,
            'failed_samples': 0,
            'execution_time': 0,
            'stopped_by_user': False
        }
    
    # ProcessPoolRunner로 멀티프로세싱 실행
    work_args = [(sample_info, parameters, worker_id, workbench_id) for sample_info in sample_info_list]
    
    processed_samples = 0
    failed_samples = 0
    results = []
    
    logger.info(f"🎯 [PRINSEQ-MULTI] Starting parallel processing with {concurrent_jobs} workers...")

    # 초기 진행률 전송
    total_samples = len(sample_info_list)
    completed_files = 0

    initial_progress = {
        "completed_files": completed_files,
        "total_files": total_samples,
        "progress_percent": 0.0
    }
    send_prinseq_progress_update(workbench_id, initial_progress)
    # 초기화 시점에는 shared_db_lock이 아직 생성되지 않음
    _save_prinseq_progress_to_db(workbench_id, completed_files, total_samples, None)

    # 프로세스 간 공유 Lock 생성 (Manager를 통한 진정한 프로세스 간 공유)
    import multiprocessing as mp
    manager = mp.Manager()
    shared_db_lock = manager.Lock()
    logger.info(f"🔒 [PRINSEQ-MULTI] Created shared DB lock for multiprocessing (lock_id={id(shared_db_lock)})")

    with ProcessPoolRunner(max_workers=concurrent_jobs, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
        try:
            for i, result in enumerate(runner.map_unordered(run_single_prinseq, work_args)):
                if result.get('stopped_by_user', False):
                    logger.warning(f"🛑 [PRINSEQ-MULTI] Sample processing stopped by user")
                    runner.stop()
                    # Reset worker event for next execution
                    shared_state.reset_worker(worker_id)
                    break

                # 결과 처리 - returncode와 output_files 둘 다 확인
                sample_name = result.get('sample_name', f'sample_{i+1}')
                returncode = result.get('returncode', -1)
                output_files = result.get('output_files', [])
                missing_files = result.get('missing_files', [])

                # 성공 조건: returncode == 0 AND output_files가 있음 AND missing_files가 없음
                is_success = (returncode == 0) and (len(output_files) > 0) and (len(missing_files) == 0)

                if is_success:
                    processed_samples += 1
                    logger.info(f"✅ [PRINSEQ-MULTI] [{i+1}/{len(sample_info_list)}] SUCCESS: {sample_name}")
                    logger.info(f"   └─ Generated {len(output_files)} output files")
                else:
                    failed_samples += 1
                    logger.warning(f"❌ [PRINSEQ-MULTI] [{i+1}/{len(sample_info_list)}] FAILED: {sample_name}")
                    if returncode != 0:
                        logger.warning(f"   ├─ Return code: {returncode}")
                    if len(output_files) == 0:
                        logger.warning(f"   ├─ No output files generated")
                    if len(missing_files) > 0:
                        logger.warning(f"   ├─ Missing {len(missing_files)} expected files")
                    logger.warning(f"   └─ Error: {result.get('stderr', 'Unknown error')[:200]}...")

                results.append(result)

                # 진행률 업데이트 (성공/실패 관계없이 완료된 것으로 카운트)
                completed_files = processed_samples + failed_samples
                progress_percent = (completed_files / total_samples * 100) if total_samples > 0 else 0

                progress_data = {
                    "completed_files": completed_files,
                    "total_files": total_samples,
                    "progress_percent": round(progress_percent, 2),
                    "current_sample": sample_name
                }

                # 실시간 진행률 전송
                send_prinseq_progress_update(workbench_id, progress_data)

                # DB에 진행률 저장 (샘플 완료시마다 저장)
                _save_prinseq_progress_to_db(workbench_id, completed_files, total_samples, shared_db_lock)

                logger.info(f"📊 [PRINSEQ-MULTI] Progress: {completed_files}/{total_samples} ({progress_percent:.1f}%)")

        except Exception as e:
            logger.error(f"💥 [PRINSEQ-MULTI] ProcessPoolRunner execution failed: {e}")
            return {
                'success': False,
                'message': f'Multi-processing execution failed: {str(e)}',
                'processed_samples': processed_samples,
                'failed_samples': failed_samples,
                'execution_time': time.time() - start_time,
                'stopped_by_user': False
            }
    
    execution_time = time.time() - start_time

    # 최종 진행률 전송
    final_progress = {
        "completed_files": processed_samples + failed_samples,
        "total_files": total_samples,
        "progress_percent": 100.0
    }
    send_prinseq_progress_update(workbench_id, final_progress)
    # Note: _save_prinseq_progress_to_db는 완료 후에는 호출하지 않음 (job_worker에서 이미 step을 completed로 업데이트)

    # 전체 결과 정리
    total_samples = len(sample_info_list)
    success_rate = (processed_samples / total_samples * 100) if total_samples > 0 else 0

    logger.info(f"🏁 [PRINSEQ-MULTI] Multi-processing execution completed!")
    logger.info(f"📊 [PRINSEQ-MULTI] Final statistics:")
    logger.info(f"   ├─ Total samples: {total_samples}")
    logger.info(f"   ├─ Successful: {processed_samples}")
    logger.info(f"   ├─ Failed: {failed_samples}")
    logger.info(f"   ├─ Success rate: {success_rate:.1f}%")
    logger.info(f"   └─ Total time: {execution_time:.2f}s")

    # User stop 체크
    user_stopped = any(result.get('stopped_by_user', False) for result in results)
    overall_success = failed_samples == 0 and not user_stopped
    
    return {
        'success': overall_success,
        'message': f'PRINSEQ processing completed: {processed_samples}/{total_samples} samples successful',
        'processed_samples': processed_samples,
        'failed_samples': failed_samples,
        'execution_time': execution_time,
        'stopped_by_user': user_stopped,
        'results': results
    }

def run_single_prinseq(sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """Process individual PRINSEQ sample (SE/PE auto-detection, gunzip decompression)"""

    if stop_event and stop_event.is_set():
        return { 'success': False, 'stopped_by_user': True }
    import subprocess
    import os
    import logging
    import time
    import tempfile
    import shutil
    import concurrent.futures
    import gzip
    import signal
    import atexit
    
    
    # Unified logging system
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')
    start_time = time.time()
    
    # ✅ Worker ID와 함께 입력 파라미터 로깅
    logger.info(f"🚀 [PRINSEQ-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
    logger.info(f"🚀 [PRINSEQ-{os.getpid()}] ║                PRINSEQ Function Started - Input Debug           ║")
    logger.info(f"🚀 [PRINSEQ-{os.getpid()}] ║                    Worker ID: {worker_id:<30} ║")
    logger.info(f"🚀 [PRINSEQ-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
    logger.info(f"")
    logger.info(f"📋 [PRINSEQ-{os.getpid()}] INPUT PARAMETERS DEBUG:")
    logger.info(f"")
    logger.info(f"🔍 [PRINSEQ-{os.getpid()}] sample_info contents:")
    for key, value in sample_info.items():
        if isinstance(value, dict):
            logger.info(f"   ├─ {key}: {{")
            for sub_key, sub_value in value.items():
                logger.info(f"   │     {sub_key}: {sub_value}")
            logger.info(f"   │   }}")
        else:
            logger.info(f"   ├─ {key}: {value}")
    
    logger.info(f"")
    logger.info(f"🔍 [PRINSEQ-{os.getpid()}] parameters contents:")
    for key, value in parameters.items():
        logger.info(f"   ├─ {key}: {value}")
    
    logger.info(f"")
    logger.info(f"💡 [PRINSEQ-{os.getpid()}] Raw JSON representations:")
    logger.info(f"   ├─ sample_info: {sample_info}")
    logger.info(f"   └─ parameters: {parameters}")
    logger.info(f"")
    
    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix=f"prinseq_{os.getpid()}_")
    decompressed_files = {}
    
    # ✅ ProcessWrapper 생성 및 cleanup 함수 등록 (Stop 신호 처리용)
    wrapper = ProcessWrapper(worker_id)
    wrapper.register_cleanup(cleanup_temp_directory, temp_dir)
    
    try:
        sample_name = sample_info['sample_name']
        group_name = sample_info['group_name']
        files = sample_info['files']
        output_base_dir = sample_info['output_base_dir']
        
        logger.info(f"🎬 [PRINSEQ-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
        logger.info(f"🎬 [PRINSEQ-{os.getpid()}] ║                    PRINSEQ Sample Processing Started             ║")
        logger.info(f"🎬 [PRINSEQ-{os.getpid()}] ║                (Using gunzip decompression method)               ║")
        logger.info(f"🎬 [PRINSEQ-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
        logger.info(f"")
        logger.info(f"📋 [PRINSEQ-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"📋 [PRINSEQ-{os.getpid()}] STEP 0: Initial setup and environment preparation")
        logger.info(f"📋 [PRINSEQ-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"🔧 [PRINSEQ-{os.getpid()}] Sample information:")
        logger.info(f"   ├─ Group name: {group_name}")
        logger.info(f"   ├─ Sample name: {sample_name}")
        logger.info(f"   ├─ Process PID: {os.getpid()}")
        logger.info(f"   ├─ Output base path: {output_base_dir}")
        logger.info(f"   └─ Temporary work directory: {temp_dir}")
        logger.info(f"")
        logger.info(f"🗂️  [PRINSEQ-{os.getpid()}] Temporary directory status:")
        logger.info(f"   ├─ Path: {temp_dir}")
        logger.info(f"   ├─ Exists: {os.path.exists(temp_dir)}")
        logger.info(f"   └─ Permission: {'Writable' if os.access(temp_dir, os.W_OK) else 'Not writable'}")

        # Ensure input files are decompressed (auto-decompress .gz if needed)
        try:
            files = ensure_decompressed_files(files, logger)
        except FileNotFoundError as e:
            logger.error(f"   ❌ Input file preparation failed: {e}")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': group_name,
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': str(e),
                'pid': os.getpid()
            }

        # Log input file information
        file_type = 'PE' if ('R1' in files and 'R2' in files) else 'SE'
        logger.info(f"📁 [PRINSEQ-{os.getpid()}] Input files ({file_type}):")
        if file_type == 'SE':
            input_file = files['SE']
            file_size = os.path.getsize(input_file) if os.path.exists(input_file) else 0
            logger.info(f"   └─ SE: {os.path.basename(input_file)} ({file_size:,} bytes)")
        else:
            input_r1 = files['R1']
            input_r2 = files['R2']
            r1_size = os.path.getsize(input_r1) if os.path.exists(input_r1) else 0
            r2_size = os.path.getsize(input_r2) if os.path.exists(input_r2) else 0
            logger.info(f"   ├─ R1: {os.path.basename(input_r1)} ({r1_size:,} bytes)")
            logger.info(f"   └─ R2: {os.path.basename(input_r2)} ({r2_size:,} bytes)")
        
        # Extract group_name info and structure directories: prinseq/{group_name}/{sample}/good|bad
        sample_output_dir = os.path.join(output_base_dir, group_name, sample_name)
        good_dir = os.path.join(sample_output_dir, 'good')
        bad_dir = os.path.join(sample_output_dir, 'bad')
        
        logger.info(f"📂 [PRINSEQ-{os.getpid()}] Output structure:")
        logger.info(f"   ├─ Sample dir: {sample_output_dir}")
        logger.info(f"   ├─ Good dir: {good_dir}")
        logger.info(f"   └─ Bad dir: {bad_dir}")
        
        # Create output directories
        os.makedirs(good_dir, exist_ok=True)
        os.makedirs(bad_dir, exist_ok=True)
        logger.info(f"✅ [PRINSEQ-{os.getpid()}] Created output directories")
        
        # Configure PRINSEQ parameters
        min_len = parameters.get('prinseq_min_len', 50)
        min_qual_mean = parameters.get('prinseq_min_qual_mean', 20)
        trim_qual_left = parameters.get('prinseq_trim_qual_left', 20)
        trim_qual_right = parameters.get('prinseq_trim_qual_right', 20)
        ns_max_p = parameters.get('prinseq_ns_max_p', 10)
        
        logger.info(f"⚙️  [PRINSEQ-{os.getpid()}] PRINSEQ parameters:")
        logger.info(f"   ├─ min_len: {min_len}")
        logger.info(f"   ├─ min_qual_mean: {min_qual_mean}")
        logger.info(f"   ├─ trim_qual_left: {trim_qual_left}")
        logger.info(f"   ├─ trim_qual_right: {trim_qual_right}")
        logger.info(f"   └─ ns_max_p: {ns_max_p}%")
        
        # Output filename prefix
        out_good_prefix = os.path.join(good_dir, sample_name + '_good')
        out_bad_prefix = os.path.join(bad_dir, sample_name + '_bad')
        
        output_files = []
        
        # Determine SE/PE and configure PRINSEQ (no decompression needed)
        if 'SE' in files:
            # Single-End processing
            input_file = files['SE']
            logger.info(f"🔧 [PRINSEQ-SE-{os.getpid()}] Configuring Single-End processing")

            # Determine file format based on extension
            if input_file.endswith('.fasta') or input_file.endswith('.fa'):
                file_format_option = '-fasta'
                output_extension = '.fasta'
            else:
                file_format_option = '-fastq'
                output_extension = '.fastq'

            logger.info(f"📄 [PRINSEQ-SE-{os.getpid()}] File format detection:")
            logger.info(f"   ├─ Input file: {os.path.basename(input_file)}")
            logger.info(f"   ├─ Format option: {file_format_option}")
            logger.info(f"   └─ Output extension: {output_extension}")

            prinseq_cmd = [
                'prinseq-lite.pl',
                file_format_option, input_file,
                '-out_good', out_good_prefix,
                '-out_bad', out_bad_prefix,
                '-min_len', str(min_len),
                '-ns_max_p', str(ns_max_p)
            ]

            # FASTQ 파일인 경우에만 품질 점수 관련 파라미터 추가
            if file_format_option == '-fastq':
                prinseq_cmd.extend([
                    '-min_qual_mean', str(min_qual_mean),
                    '-trim_qual_left', str(trim_qual_left),
                    '-trim_qual_right', str(trim_qual_right)
                ])
                logger.info(f"📊 [PRINSEQ-SE-{os.getpid()}] FASTQ quality parameters applied:")
                logger.info(f"   ├─ min_qual_mean: {min_qual_mean}")
                logger.info(f"   ├─ trim_qual_left: {trim_qual_left}")
                logger.info(f"   └─ trim_qual_right: {trim_qual_right}")
            else:
                logger.info(f"📊 [PRINSEQ-SE-{os.getpid()}] FASTA format: Quality parameters skipped")

            # Expected output files (without compression)
            expected_good = out_good_prefix + output_extension
            expected_bad = out_bad_prefix + output_extension
            output_files.extend([expected_good, expected_bad])

            logger.info(f"📄 [PRINSEQ-SE-{os.getpid()}] Expected output files:")
            logger.info(f"   ├─ Good: {os.path.basename(expected_good)}")
            logger.info(f"   └─ Bad: {os.path.basename(expected_bad)}")
            
        elif 'R1' in files and 'R2' in files:
            # Paired-End processing
            input_r1 = files['R1']
            input_r2 = files['R2']
            logger.info(f"🔧 [PRINSEQ-PE-{os.getpid()}] Configuring Paired-End processing")

            # Determine file format based on extension (use R1 for detection)
            if input_r1.endswith('.fasta') or input_r1.endswith('.fa'):
                file_format_option = '-fasta'
                file_format_option2 = '-fasta2'
                output_extension = '.fasta'
            else:
                file_format_option = '-fastq'
                file_format_option2 = '-fastq2'
                output_extension = '.fastq'

            logger.info(f"📄 [PRINSEQ-PE-{os.getpid()}] File format detection:")
            logger.info(f"   ├─ Input R1: {os.path.basename(input_r1)}")
            logger.info(f"   ├─ Input R2: {os.path.basename(input_r2)}")
            logger.info(f"   ├─ Format options: {file_format_option}, {file_format_option2}")
            logger.info(f"   └─ Output extension: {output_extension}")

            prinseq_cmd = [
                'prinseq-lite.pl',
                file_format_option, input_r1,
                file_format_option2, input_r2,
                '-out_good', out_good_prefix,
                '-out_bad', out_bad_prefix,
                '-min_len', str(min_len),
                '-ns_max_p', str(ns_max_p)
            ]

            # FASTQ 파일인 경우에만 품질 점수 관련 파라미터 추가
            if file_format_option == '-fastq':
                prinseq_cmd.extend([
                    '-min_qual_mean', str(min_qual_mean),
                    '-trim_qual_left', str(trim_qual_left),
                    '-trim_qual_right', str(trim_qual_right)
                ])
                logger.info(f"📊 [PRINSEQ-PE-{os.getpid()}] FASTQ quality parameters applied:")
                logger.info(f"   ├─ min_qual_mean: {min_qual_mean}")
                logger.info(f"   ├─ trim_qual_left: {trim_qual_left}")
                logger.info(f"   └─ trim_qual_right: {trim_qual_right}")
            else:
                logger.info(f"📊 [PRINSEQ-PE-{os.getpid()}] FASTA format: Quality parameters skipped")

            # Expected output files (without compression)
            expected_good_1 = out_good_prefix + '_1' + output_extension
            expected_good_2 = out_good_prefix + '_2' + output_extension
            expected_bad_1 = out_bad_prefix + '_1' + output_extension
            expected_bad_2 = out_bad_prefix + '_2' + output_extension
            output_files.extend([expected_good_1, expected_good_2, expected_bad_1, expected_bad_2])

            logger.info(f"📄 [PRINSEQ-PE-{os.getpid()}] Expected output files:")
            logger.info(f"   ├─ Good R1: {os.path.basename(expected_good_1)}")
            logger.info(f"   ├─ Good R2: {os.path.basename(expected_good_2)}")
            logger.info(f"   ├─ Bad R1: {os.path.basename(expected_bad_1)}")
            logger.info(f"   └─ Bad R2: {os.path.basename(expected_bad_2)}")
            
        else:
            error_msg = f"Invalid file structure for sample {sample_name}: {files}"
            logger.error(f"❌ [PRINSEQ-{os.getpid()}] Configuration error:")
            logger.error(f"   ├─ Sample: {sample_name}")
            logger.error(f"   ├─ Files provided: {list(files.keys())}")
            logger.error(f"   └─ Error: {error_msg}")
            return {
                'sample_name': sample_name,
                'returncode': -1,
                'stdout': '',
                'stderr': error_msg,
                'output_files': [],
                'exception': error_msg
            }
        
        # PRINSEQ 명령 실행
        logger.info(f"")
        logger.info(f"🧪 [PRINSEQ-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"🧪 [PRINSEQ-{os.getpid()}] STEP 2: PRINSEQ 품질 필터링 실행")
        logger.info(f"🧪 [PRINSEQ-{os.getpid()}] ═══════════════════════════════════════")
        cmd_str = ' '.join(prinseq_cmd)
        logger.info(f"🚀 [PRINSEQ-{os.getpid()}] 실행 명령어:")
        logger.info(f"   └─ {cmd_str}")
        logger.info(f"")
        logger.info(f"⏰ [PRINSEQ-{os.getpid()}] PRINSEQ 프로세스 시작...")
        
        exec_start_time = time.time()
        
        # PRINSEQ 프로세스 실행 (ProcessWrapper 사용)
        result = wrapper.run_command(prinseq_cmd, stop_event=stop_event)
        
        # Stop 신호로 인한 중단 체크
        if result['stopped_by_user']:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'PRINSEQ stopped by user signal',
                'output_files': [],
                'clean_files': []
            }
        exec_time = time.time() - exec_start_time
        
        logger.info(f"⏱️ [PRINSEQ-{os.getpid()}] PRINSEQ 실행 완료!")
        logger.info(f"📊 [PRINSEQ-{os.getpid()}] 실행 결과:")
        logger.info(f"   ├─ 반환 코드: {result['returncode']} {'(성공)' if result['success'] else '(실패)'}")
        logger.info(f"   ├─ 실행 시간: {exec_time:.2f}초")
        logger.info(f"   ├─ 표준 출력 길이: {len(result['stdout']):,} 문자")
        logger.info(f"   └─ 표준 에러 길이: {len(result['stderr']):,} 문자")
        
        # stdout 요약 출력 (PRINSEQ 통계 정보)
        if result['stdout'] and result['success']:
            logger.info(f"📈 [PRINSEQ-{os.getpid()}] PRINSEQ 통계 요약:")
            stdout_lines = result['stdout'].strip().split('\n')
            for line in stdout_lines[-10:]:  # 마지막 10줄만 출력 (통계 정보)
                if line.strip():
                    logger.info(f"   │ {line.strip()}")
        
        # 결과 파일 검증
        logger.info(f"")
        logger.info(f"📋 [PRINSEQ-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"📋 [PRINSEQ-{os.getpid()}] STEP 3: 출력 파일 검증")
        logger.info(f"📋 [PRINSEQ-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"🔍 [PRINSEQ-{os.getpid()}] 예상 출력 파일 {len(output_files)}개 검증 중...")
        
        actual_output_files = []
        missing_files = []
        total_output_size = 0
        
        for i, expected_file in enumerate(output_files, 1):
            logger.info(f"📄 [PRINSEQ-{os.getpid()}] [{i}/{len(output_files)}] 검증: {os.path.basename(expected_file)}")
            if os.path.exists(expected_file):
                file_size = os.path.getsize(expected_file)
                actual_output_files.append(expected_file)
                total_output_size += file_size
                logger.info(f"   ✅ 발견: {file_size:,} bytes")
            else:
                missing_files.append(expected_file)
                logger.warning(f"   ❌ 누락: 파일이 생성되지 않음")
        
        logger.info(f"📊 [PRINSEQ-{os.getpid()}] 파일 검증 결과:")
        logger.info(f"   ├─ 생성된 파일: {len(actual_output_files)}/{len(output_files)}")
        logger.info(f"   ├─ 누락된 파일: {len(missing_files)}")
        logger.info(f"   └─ 총 출력 크기: {total_output_size:,} bytes")
        
        # PRINSEQ 결과 파싱 및 저장
        logger.info(f"🔍 [PRINSEQ-{os.getpid()}] Starting result parsing and DB storage for {sample_name}")

        prinseq_result = None
        parsing_attempted = False
        db_save_attempted = False
        db_save_successful = False

        # 성공한 경우에만 파싱 시도
        success = (result['returncode'] == 0 and len(actual_output_files) > 0)

        if success:
            # PRINSEQ는 출력을 stdout으로 보내므로 stdout 확인
            output_to_parse = None
            output_source = None

            if result['stdout']:
                output_to_parse = result['stdout']
                output_source = "stdout"
                logger.info(f"📄 [PRINSEQ-{os.getpid()}] Found output in stdout ({len(result['stdout'])} chars)")
            elif result['stderr']:
                output_to_parse = result['stderr']
                output_source = "stderr"
                logger.info(f"📄 [PRINSEQ-{os.getpid()}] Found output in stderr ({len(result['stderr'])} chars)")
            else:
                logger.warning(f"⚠️ [PRINSEQ-{os.getpid()}] Sample {sample_name} succeeded but has empty stdout and stderr")

            if output_to_parse:
                parsing_attempted = True
                logger.info(f"📄 [PRINSEQ-{os.getpid()}] Attempting to parse {output_source} for {sample_name}")
                logger.info(f"📋 [PRINSEQ-{os.getpid()}] Output:\n{output_to_parse}")

                prinseq_result = parse_prinseq_output(output_to_parse, sample_name)

                if prinseq_result and prinseq_result.get('parsing_successful', False):
                    logger.info(f"✅ [PRINSEQ-{os.getpid()}] Successfully parsed PRINSEQ output for {sample_name}")
                    logger.info(f"📊 [PRINSEQ-{os.getpid()}] Parsed values: "
                              f"input={prinseq_result.get('input_sequences', 0)}, "
                              f"good={prinseq_result.get('good_sequences', 0)}, "
                              f"bad={prinseq_result.get('bad_sequences', 0)}")

                    # DB에 개별 샘플 결과 저장
                    db_save_attempted = True
                    logger.info(f"💾 [PRINSEQ-{os.getpid()}] Attempting to save parsed results to DB...")

                    # 함수 인자로 받은 workbench_id 사용
                    if not workbench_id:
                        logger.error(f"❌ [PRINSEQ-{os.getpid()}] No workbench_id provided for {sample_name}")
                        db_save_successful = False
                    else:
                        db_save_successful = _save_prinseq_result_to_db(workbench_id, sample_name, prinseq_result, shared_db_lock)

                    if db_save_successful:
                        logger.info(f"✅ [PRINSEQ-{os.getpid()}] Successfully saved results to DB for {sample_name}")
                    else:
                        logger.error(f"❌ [PRINSEQ-{os.getpid()}] Failed to save results to DB for {sample_name}")
                else:
                    logger.warning(f"⚠️ [PRINSEQ-{os.getpid()}] Failed to parse PRINSEQ output for {sample_name}")
                    if prinseq_result:
                        logger.info(f"📋 [PRINSEQ-{os.getpid()}] Parser result: {prinseq_result}")
        elif not success:
            logger.info(f"ℹ️ [PRINSEQ-{os.getpid()}] Skipping result parsing for failed sample {sample_name}")

        # 최종 결과 처리
        if success:
            total_time = time.time() - start_time
            logger.info(f"")
            logger.info(f"🏆 [PRINSEQ-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
            logger.info(f"🏆 [PRINSEQ-{os.getpid()}] ║                     처리 완료 - 성공!                         ║")
            logger.info(f"🏆 [PRINSEQ-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
            logger.info(f"🎯 [PRINSEQ-{os.getpid()}] 처리 결과 요약:")
            logger.info(f"   ├─ 그룹명: {group_name}")
            logger.info(f"   ├─ 샘플명: {sample_name}")
            logger.info(f"   ├─ 파일 타입: {file_type}")
            logger.info(f"   ├─ 생성된 파일: {len(actual_output_files)}/{len(output_files)} 개")
            logger.info(f"   ├─ 총 처리 시간: {total_time:.2f}초")
            logger.info(f"   ├─ PRINSEQ 실행 시간: {exec_time:.2f}초")
            logger.info(f"   ├─ 총 출력 크기: {total_output_size:,} bytes")
            logger.info(f"   ├─ 파싱 시도: {'YES' if parsing_attempted else 'NO'}")
            logger.info(f"   ├─ 파싱 성공: {'YES' if prinseq_result and prinseq_result.get('parsing_successful') else 'NO'}")
            logger.info(f"   ├─ DB 저장 시도: {'YES' if db_save_attempted else 'NO'}")
            logger.info(f"   ├─ DB 저장 성공: {'YES' if db_save_successful else 'NO'}")
            logger.info(f"   └─ 출력 디렉토리: {sample_output_dir}")

            if prinseq_result and prinseq_result.get('parsing_successful', False):
                logger.info(f"📈 [PRINSEQ-{os.getpid()}] Final results: Input={prinseq_result['input_sequences']}, "
                          f"Good={prinseq_result['good_sequences']} ({prinseq_result['good_rate']:.1f}%), "
                          f"Bad={prinseq_result['bad_sequences']} ({prinseq_result['bad_rate']:.1f}%)")

            if missing_files:
                logger.warning(f"")
                logger.warning(f"⚠️  [PRINSEQ-{os.getpid()}] 일부 예상 파일이 생성되지 않았습니다:")
                for missing in missing_files:
                    logger.warning(f"     └─ {os.path.basename(missing)}")
            else:
                logger.info(f"✨ [PRINSEQ-{os.getpid()}] 모든 예상 파일이 성공적으로 생성되었습니다!")

        else:
            logger.error(f"")
            logger.error(f"💥 [PRINSEQ-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
            logger.error(f"💥 [PRINSEQ-{os.getpid()}] ║                     처리 실패!                               ║")
            logger.error(f"💥 [PRINSEQ-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
            logger.error(f"❌ [PRINSEQ-{os.getpid()}] 실패 정보:")
            logger.error(f"   ├─ 샘플명: {sample_name}")
            logger.error(f"   ├─ 반환 코드: {result['returncode']}")
            logger.error(f"   ├─ 실행 시간: {exec_time:.2f}초")
            logger.error(f"   └─ 에러 상세 내용 확인 필요")
            
            # stderr가 있으면 일부 출력
            if result['stderr']:
                stderr_preview = result['stderr'][:500] + "..." if len(result['stderr']) > 500 else result['stderr']
                logger.error(f"")
                logger.error(f"📄 [PRINSEQ-{os.getpid()}] 에러 메시지 미리보기:")
                for line in stderr_preview.split('\n')[:10]:  # 최대 10줄까지
                    if line.strip():
                        logger.error(f"   │ {line.strip()}")
            
            # 생성된 파일이 있다면 표시
            if actual_output_files:
                logger.info(f"")
                logger.info(f"📋 [PRINSEQ-{os.getpid()}] 부분적으로 생성된 파일:")
                for file_path in actual_output_files:
                    file_size = os.path.getsize(file_path)
                    logger.info(f"   └─ {os.path.basename(file_path)} ({file_size:,} bytes)")
        
        return {
            'sample_name': sample_name,
            'condition': group_name,
            'returncode': result['returncode'],
            'stdout': result['stdout'],
            'stderr': result['stderr'],
            'output_files': actual_output_files,
            'expected_files': output_files,
            'missing_files': missing_files,
            'execution_time': exec_time,
            'total_time': time.time() - start_time,
            'pid': os.getpid(),
            'prinseq_result': prinseq_result,
            'parsing_successful': prinseq_result.get('parsing_successful', False) if prinseq_result else False,
            'db_save_successful': db_save_successful
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"💥 [PRINSEQ-{os.getpid()}] Critical exception occurred:")
        logger.error(f"   ├─ Sample: {sample_info.get('sample_name', 'unknown')}")
        logger.error(f"   ├─ Exception type: {type(e).__name__}")
        logger.error(f"   ├─ Exception message: {str(e)}")
        logger.error(f"   ├─ Processing time before error: {total_time:.2f}s")
        logger.error(f"   └─ PID: {os.getpid()}")
        
        # 스택 트레이스 일부 포함
        import traceback
        tb_lines = traceback.format_exc().split('\n')
        logger.error(f"   Stack trace (last 3 lines):")
        for line in tb_lines[-4:-1]:  # 마지막 몇 줄만 표시
            if line.strip():
                logger.error(f"     {line.strip()}")
        
        return {
            'sample_name': sample_info.get('sample_name', 'unknown'),
            'condition': sample_info.get('group_name', 'unknown'),
            'returncode': -1,
            'stdout': '',
            'stderr': str(e),
            'output_files': [],
            'expected_files': [],
            'missing_files': [],
            'execution_time': 0,
            'total_time': total_time,
            'pid': os.getpid(),
            'exception': str(e),
            'prinseq_result': None,
            'parsing_successful': False,
            'db_save_successful': False
        }
    
    finally:
        # 정리 작업 시작
        total_final_time = time.time() - start_time
        logger.info(f"")
        logger.info(f"🧹 [PRINSEQ-{os.getpid()}] ═══════════════════════════════════════")
        logger.info(f"🧹 [PRINSEQ-{os.getpid()}] STEP 4: 정리 작업 시작")
        logger.info(f"🧹 [PRINSEQ-{os.getpid()}] ═══════════════════════════════════════")
        
        # 압축 해제된 입력 파일들 정리
        if decompressed_files:
            logger.info(f"🗑️  [PRINSEQ-{os.getpid()}] 임시 입력 파일 정리 중...")
            cleanup_count = 0
            cleanup_size = 0
            
            for key, temp_file in decompressed_files.items():
                try:
                    if os.path.exists(temp_file):
                        file_size = os.path.getsize(temp_file)
                        os.remove(temp_file)
                        cleanup_count += 1
                        cleanup_size += file_size
                        logger.info(f"   ✅ [{key}] 삭제: {os.path.basename(temp_file)} ({file_size:,} bytes)")
                    else:
                        logger.warning(f"   ⚠️  [{key}] 파일 없음: {os.path.basename(temp_file)}")
                except Exception as cleanup_error:
                    logger.error(f"   ❌ [{key}] 삭제 실패: {os.path.basename(temp_file)}")
                    logger.error(f"       에러: {cleanup_error}")
            
            logger.info(f"📊 [PRINSEQ-{os.getpid()}] 임시 파일 정리 완료:")
            logger.info(f"   ├─ 삭제된 파일: {cleanup_count}개")
            logger.info(f"   └─ 절약된 공간: {cleanup_size:,} bytes")
        else:
            logger.info(f"📋 [PRINSEQ-{os.getpid()}] 정리할 임시 파일 없음")
        
        # 임시 디렉토리 삭제
        logger.info(f"🗂️  [PRINSEQ-{os.getpid()}] 임시 디렉토리 정리 중...")
        try:
            if os.path.exists(temp_dir):
                # 디렉토리 내용 확인
                remaining_files = []
                try:
                    remaining_files = os.listdir(temp_dir)
                except:
                    pass
                
                if remaining_files:
                    logger.warning(f"⚠️  [PRINSEQ-{os.getpid()}] 임시 디렉토리에 남은 파일: {len(remaining_files)}개")
                    for file in remaining_files[:5]:  # 최대 5개까지만 표시
                        logger.warning(f"     └─ {file}")
                    if len(remaining_files) > 5:
                        logger.warning(f"     └─ ... 외 {len(remaining_files)-5}개")
                
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"   ✅ 임시 디렉토리 삭제 완료: {temp_dir}")
            else:
                logger.info(f"   📋 임시 디렉토리 이미 없음: {temp_dir}")
                
        except Exception as cleanup_error:
            logger.error(f"   ❌ 임시 디렉토리 삭제 실패: {temp_dir}")
            logger.error(f"       에러: {cleanup_error}")
        
        # 최종 요약
        logger.info(f"")
        logger.info(f"🏁 [PRINSEQ-{os.getpid()}] ╔══════════════════════════════════════════════════════════════════╗")
        logger.info(f"🏁 [PRINSEQ-{os.getpid()}] ║                     전체 작업 완료                            ║")
        logger.info(f"🏁 [PRINSEQ-{os.getpid()}] ╚══════════════════════════════════════════════════════════════════╝")
        logger.info(f"📊 [PRINSEQ-{os.getpid()}] 최종 통계:")
        logger.info(f"   ├─ 총 소요 시간: {total_final_time:.2f}초")
        logger.info(f"   ├─ 프로세스 PID: {os.getpid()}")
        logger.info(f"   └─ 정리 작업: 완료")


def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 prinseq tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering prinseq tool...")
    
    metadata = {
        'name': 'prinseq',
        'description': 'PRINSEQ sequence filtering functionality',
        'version': '1.0.0',
        'supported_formats': ['.fastq', '.fastq.gz', '.fq', '.fq.gz'],
        'requirements': ['prinseq-lite.pl'],
        'parameters': {
            'prinseq_min_len': 20,
            'prinseq_max_len': 500,
            'prinseq_min_qual_mean': 20,
            'prinseq_max_ns': 5,
            'prinseq_trim_left': 0,
            'prinseq_trim_right': 0
        }
    }
    
    return coordinator.register_tool('prinseq', execute_prinseq, metadata)

