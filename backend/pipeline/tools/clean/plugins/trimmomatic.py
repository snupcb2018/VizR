"""
Trimmomatic functionality for VizR pipeline
Trimmomatic 품질 조정 관련 함수들
"""

import json
import os
import sqlite3
import logging
import subprocess
import time
import multiprocessing as mp
from typing import Dict, List, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

from backend.utils import database
from backend.utils.files import ensure_decompressed_files
from ....utils.process_wrapper import ProcessWrapper
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.process_runner import ProcessPoolRunner
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'DEBUG')


def parse_trimmomatic_output(stdout: str, sample_name: str) -> Dict[str, Any]:
    """
    Trimmomatic stdout에서 결과 정보 파싱

    SE와 PE 모드의 두 가지 출력 형식을 모두 지원:
    - SE: "Input Reads: 21917767 Surviving: 21824112 (99.57%) Dropped: 93655 (0.43%)"
    - PE: "Input Read Pairs: 35918854 Both Surviving: 34874225 (97.09%) Forward Only Surviving: 745686 (2.08%) Reverse Only Surviving: 221834 (0.62%) Dropped: 77109 (0.21%)"

    Args:
        stdout: Trimmomatic 명령어 실행 결과
        sample_name: 샘플 이름

    Returns:
        dict: 파싱된 결과 정보
    """
    logger.debug(f"🔍 [TRIMMOMATIC-PARSER] Starting output parsing for sample: {sample_name}")

    result = {
        "sample_name": sample_name,
        "input_reads": 0,
        "surviving_reads": 0,
        "survival_rate": 0.0,
        "dropped_reads": 0,
        "drop_rate": 0.0,
        "parsing_successful": False
    }

    try:
        # stdout 입력 검증
        if not stdout or not stdout.strip():
            logger.warning(f"⚠️ [TRIMMOMATIC-PARSER] Empty or null stdout for sample {sample_name}")
            return result

        logger.debug(f"📄 [TRIMMOMATIC-PARSER] Raw stdout length: {len(stdout)} characters")
        logger.debug(f"📄 [TRIMMOMATIC-PARSER] Raw stdout preview (first 200 chars): {repr(stdout[:200])}")

        # stdout를 줄별로 분할하여 검색
        lines = stdout.strip().split('\n')
        logger.debug(f"📝 [TRIMMOMATIC-PARSER] Analyzing {len(lines)} lines of output")

        import re
        target_line_found = False

        for line_idx, line in enumerate(lines):
            # 중요한 라인만 로그 출력
            if any(keyword in line for keyword in ["Input Read", "Surviving:", "Dropped:", "TrimmomaticSE:", "TrimmomaticPE:"]):
                logger.debug(f"📄 [TRIMMOMATIC-PARSER] Line {line_idx + 1}: {line}")

            # PE 모드 파싱: "Input Read Pairs: ... Both Surviving: ... Dropped: ..."
            if "Input Read Pairs:" in line and "Both Surviving:" in line and "Dropped:" in line:
                target_line_found = True
                logger.debug(f"🎯 [TRIMMOMATIC-PARSER] Found PE format line at line {line_idx + 1}")
                logger.debug(f"🔍 [TRIMMOMATIC-PARSER] Starting PE regex parsing...")

                # Input Read Pairs: 숫자 (PE는 pair 단위이므로 *2)
                input_pattern = r'Input Read Pairs:\s*(\d+)'
                input_match = re.search(input_pattern, line)
                if input_match:
                    pairs = int(input_match.group(1))
                    result["input_reads"] = pairs * 2  # PE는 R1+R2이므로 2배
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Parsed input_read_pairs: {pairs} → input_reads: {result['input_reads']}")
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-PARSER] Failed to match input_read_pairs pattern")

                # Both Surviving: 숫자 (퍼센트%)
                both_surviving_pattern = r'Both Surviving:\s*(\d+)\s*\(([0-9.]+)%\)'
                both_surviving_match = re.search(both_surviving_pattern, line)

                # Forward Only Surviving: 숫자 (퍼센트%)
                forward_pattern = r'Forward Only Surviving:\s*(\d+)\s*\(([0-9.]+)%\)'
                forward_match = re.search(forward_pattern, line)

                # Reverse Only Surviving: 숫자 (퍼센트%)
                reverse_pattern = r'Reverse Only Surviving:\s*(\d+)\s*\(([0-9.]+)%\)'
                reverse_match = re.search(reverse_pattern, line)

                both_surviving = 0
                forward_only = 0
                reverse_only = 0

                if both_surviving_match:
                    both_surviving = int(both_surviving_match.group(1))
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Both Surviving: {both_surviving}")

                if forward_match:
                    forward_only = int(forward_match.group(1))
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Forward Only: {forward_only}")

                if reverse_match:
                    reverse_only = int(reverse_match.group(1))
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Reverse Only: {reverse_only}")

                # PE의 surviving_reads = (both_surviving * 2) + forward_only + reverse_only
                result["surviving_reads"] = (both_surviving * 2) + forward_only + reverse_only
                logger.debug(f"📊 [TRIMMOMATIC-PARSER] Total surviving_reads: {result['surviving_reads']}")

                # Dropped 파싱은 drop_rate를 얻기 위한 것이며, dropped_reads는 계산으로 구함
                dropped_pattern = r'Dropped:\s*(\d+)\s*\(([0-9.]+)%\)'
                dropped_match = re.search(dropped_pattern, line)
                if dropped_match:
                    # drop_rate는 Trimmomatic 출력에서 가져오되, dropped_reads는 계산
                    result["drop_rate"] = float(dropped_match.group(2))
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Parsed drop_rate from output: {result['drop_rate']}%")
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-PARSER] Failed to match dropped pattern")

                # dropped_reads는 input - surviving으로 계산 (더 정확함)
                if result["input_reads"] > 0:
                    result["dropped_reads"] = result["input_reads"] - result["surviving_reads"]
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Calculated dropped_reads: {result['dropped_reads']} = input({result['input_reads']}) - surviving({result['surviving_reads']})")

                    # drop_rate를 파싱하지 못한 경우 계산
                    if result["drop_rate"] == 0.0 and result["input_reads"] > 0:
                        result["drop_rate"] = (result["dropped_reads"] / result["input_reads"]) * 100
                        logger.debug(f"📊 [TRIMMOMATIC-PARSER] Calculated drop_rate: {result['drop_rate']:.2f}%")

                # survival_rate 계산
                if result["input_reads"] > 0:
                    result["survival_rate"] = (result["surviving_reads"] / result["input_reads"]) * 100
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Calculated survival_rate: {result['survival_rate']:.2f}%")

                break

            # SE 모드 파싱: "Input Reads: ... Surviving: ... Dropped: ..."
            elif "Input Reads:" in line and "Surviving:" in line and "Dropped:" in line:
                target_line_found = True
                logger.debug(f"🎯 [TRIMMOMATIC-PARSER] Found SE format line at line {line_idx + 1}")
                logger.debug(f"🔍 [TRIMMOMATIC-PARSER] Starting SE regex parsing...")

                # Input Reads: 숫자
                input_pattern = r'Input Reads:\s*(\d+)'
                input_match = re.search(input_pattern, line)
                if input_match:
                    result["input_reads"] = int(input_match.group(1))
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Parsed input_reads: {result['input_reads']}")
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-PARSER] Failed to match input_reads pattern")

                # Surviving: 숫자 (퍼센트%)
                surviving_pattern = r'Surviving:\s*(\d+)\s*\(([0-9.]+)%\)'
                surviving_match = re.search(surviving_pattern, line)
                if surviving_match:
                    result["surviving_reads"] = int(surviving_match.group(1))
                    result["survival_rate"] = float(surviving_match.group(2))
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Parsed surviving_reads: {result['surviving_reads']} ({result['survival_rate']}%)")
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-PARSER] Failed to match surviving pattern")

                # Dropped 파싱은 drop_rate를 얻기 위한 것이며, dropped_reads는 계산으로 구함
                dropped_pattern = r'Dropped:\s*(\d+)\s*\(([0-9.]+)%\)'
                dropped_match = re.search(dropped_pattern, line)
                if dropped_match:
                    # drop_rate는 Trimmomatic 출력에서 가져오되, dropped_reads는 계산
                    result["drop_rate"] = float(dropped_match.group(2))
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Parsed drop_rate from output: {result['drop_rate']}%")
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-PARSER] Failed to match dropped pattern")

                # dropped_reads는 input - surviving으로 계산 (더 정확함)
                if result["input_reads"] > 0:
                    result["dropped_reads"] = result["input_reads"] - result["surviving_reads"]
                    logger.debug(f"📊 [TRIMMOMATIC-PARSER] Calculated dropped_reads: {result['dropped_reads']} = input({result['input_reads']}) - surviving({result['surviving_reads']})")

                    # drop_rate를 파싱하지 못한 경우 계산
                    if result["drop_rate"] == 0.0 and result["input_reads"] > 0:
                        result["drop_rate"] = (result["dropped_reads"] / result["input_reads"]) * 100
                        logger.debug(f"📊 [TRIMMOMATIC-PARSER] Calculated drop_rate: {result['drop_rate']:.2f}%")

                break

        # 파싱 결과 검증
        logger.info(f"🔍 [TRIMMOMATIC-PARSER] ⭐ VALIDATION STARTING for {sample_name}")
        logger.info(f"   ├─ target_line_found: {target_line_found}")
        logger.info(f"   ├─ input_reads: {result['input_reads']}")
        logger.info(f"   ├─ surviving_reads: {result['surviving_reads']}")
        logger.info(f"   └─ dropped_reads: {result['dropped_reads']}")

        if target_line_found:
            logger.info(f"✅ [TRIMMOMATIC-PARSER] ⭐ Target line was found, proceeding to validation...")

            # 기본 값 검증
            input_valid = result["input_reads"] > 0
            surviving_valid = result["surviving_reads"] >= 0
            dropped_valid = result["dropped_reads"] >= 0

            logger.info(f"🔍 [TRIMMOMATIC-PARSER] ⭐ Basic value validation:")
            logger.info(f"   ├─ input_reads > 0: {input_valid} (value: {result['input_reads']})")
            logger.info(f"   ├─ surviving_reads >= 0: {surviving_valid} (value: {result['surviving_reads']})")
            logger.info(f"   └─ dropped_reads >= 0: {dropped_valid} (value: {result['dropped_reads']})")

            if input_valid and surviving_valid and dropped_valid:
                logger.info(f"✅ [TRIMMOMATIC-PARSER] ⭐ Basic validation PASSED")

                # 데이터 일관성 검증
                calculated_total = result["surviving_reads"] + result["dropped_reads"]
                difference = calculated_total - result["input_reads"]

                logger.info(f"🔍 [TRIMMOMATIC-PARSER] ⭐ Data consistency check:")
                logger.info(f"   ├─ surviving + dropped = {calculated_total}")
                logger.info(f"   ├─ input = {result['input_reads']}")
                logger.info(f"   ├─ difference = {difference}")
                logger.info(f"   └─ match = {calculated_total == result['input_reads']}")

                if calculated_total == result["input_reads"]:
                    result["parsing_successful"] = True
                    logger.info(f"✅ [TRIMMOMATIC-PARSER] ⭐ Data consistency check PASSED")
                    logger.info(f"✅ [TRIMMOMATIC-PARSER] Successfully parsed and validated results for {sample_name}")
                    logger.info(f"📊 [TRIMMOMATIC-PARSER] Final results: Input={result['input_reads']}, "
                              f"Surviving={result['surviving_reads']} ({result['survival_rate']:.2f}%), "
                              f"Dropped={result['dropped_reads']} ({result['drop_rate']:.2f}%)")
                else:
                    result["parsing_successful"] = False
                    logger.error(f"❌ [TRIMMOMATIC-PARSER] ⭐ Data consistency check FAILED for {sample_name}")
                    logger.error(f"   ├─ REASON: surviving + dropped != input")
                    logger.error(f"   ├─ surviving({result['surviving_reads']}) + dropped({result['dropped_reads']}) = {calculated_total}")
                    logger.error(f"   ├─ input = {result['input_reads']}")
                    logger.error(f"   └─ difference = {difference}")
            else:
                result["parsing_successful"] = False
                logger.error(f"❌ [TRIMMOMATIC-PARSER] ⭐ Basic validation FAILED for {sample_name}")
                logger.error(f"   ├─ REASON: Invalid parsed values detected")
                logger.error(f"   ├─ input_reads ({result['input_reads']}) > 0: {input_valid}")
                logger.error(f"   ├─ surviving_reads ({result['surviving_reads']}) >= 0: {surviving_valid}")
                logger.error(f"   └─ dropped_reads ({result['dropped_reads']}) >= 0: {dropped_valid}")
        else:
            result["parsing_successful"] = False
            logger.error(f"❌ [TRIMMOMATIC-PARSER] ⭐ Target line NOT FOUND for {sample_name}")
            logger.error(f"   └─ REASON: Could not find 'Input Read Pairs:' or 'Input Reads:' line with statistics")
            logger.info(f"📝 [TRIMMOMATIC-PARSER] Searched for patterns: SE format OR PE format")

            # 부분적으로 일치하는 라인들 검색
            partial_matches = []
            for line_idx, line in enumerate(lines):
                if any(keyword in line for keyword in ["Input Read", "Surviving:", "Dropped:"]):
                    partial_matches.append(f"Line {line_idx + 1}: {line}")

            if partial_matches:
                logger.info(f"📝 [TRIMMOMATIC-PARSER] Found partial matches:")
                for match in partial_matches[:5]:  # 최대 5개만 로그
                    logger.info(f"   {match}")
            else:
                logger.warning(f"⚠️ [TRIMMOMATIC-PARSER] No partial matches found either")

        if not result["parsing_successful"]:
            logger.error(f"❌ [TRIMMOMATIC-PARSER] Failed to parse Trimmomatic output for {sample_name}")
            logger.info(f"📝 [TRIMMOMATIC-PARSER] Complete stdout for debugging:")
            for i, line in enumerate(lines[:10], 1):  # 처음 10줄만 상세 로그
                logger.info(f"   Line {i:2d}: {repr(line)}")
            if len(lines) > 10:
                logger.info(f"   ... and {len(lines) - 10} more lines")

    except Exception as e:
        logger.error(f"❌ [TRIMMOMATIC-PARSER] Exception while parsing output for {sample_name}: {e}")
        logger.error(f"❌ [TRIMMOMATIC-PARSER] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [TRIMMOMATIC-PARSER] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")

    logger.info(f"🏁 [TRIMMOMATIC-PARSER] Parsing completed for {sample_name}: {'SUCCESS' if result['parsing_successful'] else 'FAILED'}")
    return result


def send_trimmomatic_progress_update(workbench_id: int, progress_data: dict) -> bool:
    """
    Trimmomatic 진행률 직접 전송

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
            logger.debug(f"📡 [TRIMMOMATIC-PROGRESS] Redis not available, skipping progress update")
            return False

        success = redis_broker.publish_progress(
            workbench_id=workbench_id,
            task_type='trimmomatic',
            progress_data=progress_data
        )

        if success:
            logger.debug(f"📡 [TRIMMOMATIC-PROGRESS] Successfully sent progress update: {progress_data}")
        else:
            logger.warning(f"📡 [TRIMMOMATIC-PROGRESS] Failed to send progress update - Redis available: {redis_broker.is_available()}, Progress data: {progress_data}")

        return success
    except Exception as e:
        logger.error(f"❌ [TRIMMOMATIC-PROGRESS] Error sending progress update: {e}")
        return False


def _save_trimmomatic_progress_to_db(workbench_id: int, completed_files: int, total_files: int, shared_db_lock=None) -> bool:
    """
    Trimmomatic 진행률을 DB에 저장 (summary만 안전하게 업데이트)

    Args:
        workbench_id: 워크벤치 ID
        completed_files: 완료된 파일 수
        total_files: 전체 파일 수
        shared_db_lock: 멀티프로세스 간 공유 DB 락 (선택적)

    Returns:
        저장 성공 여부
    """
    logger.info(f"💾 [TRIMMOMATIC-PROGRESS-DB] Starting to save progress: workbench={workbench_id}, completed={completed_files}/{total_files}")

    try:
        # 진행률 계산 및 검증
        if total_files <= 0:
            logger.warning(f"⚠️ [TRIMMOMATIC-PROGRESS-DB] Invalid total_files: {total_files}")
            progress_percent = 0
        else:
            progress_percent = (completed_files / total_files * 100)
            progress_percent = min(100.0, max(0.0, progress_percent))  # 0-100 범위로 제한

        logger.info(f"📊 [TRIMMOMATIC-PROGRESS-DB] Calculated progress: {progress_percent:.2f}% ({completed_files}/{total_files})")

        # 기존 progress_detail 가져오기
        logger.info(f"🔍 [TRIMMOMATIC-PROGRESS-DB] Retrieving existing progress_detail from DB...")
        existing_data = {}

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            result = cursor.execute('''
                SELECT progress_detail FROM pipeline_job_steps
                WHERE workbench_id = ? AND tool_name = 'trimmomatic'
            ''', (workbench_id,)).fetchone()

            if result and result[0]:
                try:
                    existing_data = json.loads(result[0])
                    existing_results_count = len(existing_data.get("results", {}))
                    logger.info(f"✅ [TRIMMOMATIC-PROGRESS-DB] Successfully loaded existing progress_detail: {existing_results_count} existing results")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ [TRIMMOMATIC-PROGRESS-DB] Failed to parse existing progress_detail, initializing new: {e}")
                    existing_data = {}
            else:
                logger.info(f"ℹ️ [TRIMMOMATIC-PROGRESS-DB] No existing progress_detail found, initializing new structure")

        # 기존 results 보존
        existing_results = existing_data.get("results", {})
        logger.info(f"🔧 [TRIMMOMATIC-PROGRESS-DB] Preserving {len(existing_results)} existing sample results")

        # summary 데이터 생성
        current_time = time.time()
        summary_data = {
            "completed_files": completed_files,
            "total_files": total_files,
            "progress_percent": round(progress_percent, 2),
            "last_updated": current_time
        }

        logger.info(f"📈 [TRIMMOMATIC-PROGRESS-DB] New summary data: {summary_data}")

        # ⚠️ 중요: 기존 데이터 구조를 유지하고 summary만 업데이트 (results는 절대 건드리지 않음!)
        # 기존 results가 있으면 그대로 유지, 없으면 빈 객체로 초기화
        if "results" not in existing_data:
            existing_data["results"] = {}
            logger.info(f"🔧 [TRIMMOMATIC-PROGRESS-DB] Initialized empty results section")

        # Summary만 업데이트
        existing_data["summary"] = summary_data
        progress_data = existing_data

        # 디버깅: 최종 results 개수 확인
        final_results_count = len(progress_data.get("results", {}))
        logger.info(f"🔍 [TRIMMOMATIC-PROGRESS-DB] Final data structure: {final_results_count} results preserved (NEVER overwritten)")

        # 결과 손실 방지를 위한 추가 검증
        if final_results_count < len(existing_results):
            logger.error(f"❌ [TRIMMOMATIC-PROGRESS-DB] CRITICAL ERROR: Results count decreased from {len(existing_results)} to {final_results_count}!")
            logger.error(f"❌ [TRIMMOMATIC-PROGRESS-DB] This indicates data loss - operation aborted")
            return False

        # JSON 직렬화 테스트
        try:
            json_str = json.dumps(progress_data)
            json_size = len(json_str)
            logger.info(f"📦 [TRIMMOMATIC-PROGRESS-DB] JSON serialization successful: {json_size} characters")
        except (TypeError, ValueError) as e:
            logger.error(f"❌ [TRIMMOMATIC-PROGRESS-DB] JSON serialization failed: {e}")
            return False

        # DB 업데이트 실행 (shared_db_lock으로 보호)
        current_process = mp.current_process()
        if shared_db_lock is not None:
            logger.info(f"🔒 [TRIMMOMATIC-PROGRESS-DB-LOCK-ENTER] PID={current_process.pid} ATTEMPTING lock acquisition for progress update")

            with shared_db_lock:
                logger.info(f"✅ [TRIMMOMATIC-PROGRESS-DB-LOCK-ACQUIRED] PID={current_process.pid} ENTERED critical section for progress update")
                success = _execute_progress_db_update(workbench_id, json_str, current_process.pid)
                logger.info(f"🔓 [TRIMMOMATIC-PROGRESS-DB-LOCK-EXIT] PID={current_process.pid} LEAVING critical section for progress update")
                return success
        else:
            logger.warning(f"⚠️ [TRIMMOMATIC-PROGRESS-DB] No shared_db_lock provided - proceeding without lock protection")
            return _execute_progress_db_update(workbench_id, json_str, current_process.pid)

    except Exception as e:
        logger.error(f"❌ [TRIMMOMATIC-PROGRESS-DB] Critical error saving progress to DB: {e}")
        logger.error(f"❌ [TRIMMOMATIC-PROGRESS-DB] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [TRIMMOMATIC-PROGRESS-DB] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")
        return False


def _save_trimmomatic_result_to_db(workbench_id: int, sample_name: str, result_data: Dict[str, Any], shared_db_lock=None) -> bool:
    """
    개별 샘플의 Trimmomatic 결과를 DB에 저장

    Args:
        workbench_id: 워크벤치 ID
        sample_name: 샘플 이름
        result_data: 파싱된 결과 데이터

    Returns:
        저장 성공 여부
    """
    logger.info(f"💾 [TRIMMOMATIC-RESULT-DB] ⭐ CALLED: Starting to save sample result: {sample_name} for workbench {workbench_id}")
    logger.info(f"🔍 [TRIMMOMATIC-RESULT-DB] ⭐ result_data keys: {result_data.keys() if result_data else 'None'}")
    logger.info(f"🔍 [TRIMMOMATIC-RESULT-DB] ⭐ result_data type: {type(result_data)}")

    try:
        # 입력 데이터 검증
        if not result_data or not isinstance(result_data, dict):
            logger.warning(f"⚠️ [TRIMMOMATIC-RESULT-DB] Invalid result_data for sample {sample_name}: {result_data}")
            return False

        # 파싱 성공 여부 확인
        parsing_successful = result_data.get('parsing_successful', False)
        logger.info(f"📊 [TRIMMOMATIC-RESULT-DB] ⭐ Sample {sample_name} parsing status: {'SUCCESS' if parsing_successful else 'FAILED'}")

        if parsing_successful:
            logger.info(f"📈 [TRIMMOMATIC-RESULT-DB] Sample {sample_name} results: "
                       f"Input={result_data.get('input_reads', 0)}, "
                       f"Surviving={result_data.get('surviving_reads', 0)} ({result_data.get('survival_rate', 0):.1f}%), "
                       f"Dropped={result_data.get('dropped_reads', 0)} ({result_data.get('drop_rate', 0):.1f}%)")

        # 프로세스 정보 수집 (server.py와 동일한 패턴)
        current_process = __import__('multiprocessing').current_process()
        process_info = f"PID={current_process.pid}, Name={current_process.name}"

        # Lock 진입 시도 로그
        logger.debug(f"🔒 [TRIMMOMATIC-DB-LOCK-ENTER] PID={current_process.pid} ATTEMPTING lock acquisition - {process_info}, Sample: {sample_name}, Workbench: {workbench_id}")

        # 전달받은 shared_db_lock 사용 (ProcessPoolRunner에서 자동 주입됨)
        logger.debug(f"🔍 [TRIMMOMATIC-DB-LOCK-DEBUG] Using passed shared_db_lock: {shared_db_lock}")
        logger.debug(f"🔍 [TRIMMOMATIC-DB-LOCK-DEBUG] shared_db_lock type: {type(shared_db_lock)}")

        if shared_db_lock is not None:
            # 전달받은 Lock 사용
            with shared_db_lock:
                logger.info(f"✅ [TRIMMOMATIC-DB-LOCK-ACQUIRED] ⭐ PID={current_process.pid} ENTERED critical section, Sample: {sample_name}")
                result = _execute_trimmomatic_db_operations_impl(current_process, process_info, sample_name, workbench_id, result_data)
                logger.info(f"🔓 [TRIMMOMATIC-DB-LOCK-EXIT] ⭐ PID={current_process.pid} LEAVING critical section, Result: {result}, Sample: {sample_name}")
        else:
            logger.error(f"❌ [TRIMMOMATIC-DB-LOCK] No shared_db_lock provided - this should not happen!")
            return False

        if result:
            logger.info(f"🎉 [TRIMMOMATIC-RESULT-DB] ⭐ Successfully saved sample result for {sample_name}")
        else:
            logger.error(f"❌ [TRIMMOMATIC-RESULT-DB] ⭐ FAILED to save sample result for {sample_name}")

        return result

    except Exception as e:
        logger.error(f"❌ [TRIMMOMATIC-RESULT-DB] Critical error saving sample result for {sample_name}: {e}")
        logger.error(f"❌ [TRIMMOMATIC-RESULT-DB] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [TRIMMOMATIC-RESULT-DB] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")
        return False


def _execute_progress_db_update(workbench_id: int, json_str: str, pid: int) -> bool:
    """진행률 DB 업데이트를 실행하는 헬퍼 함수"""
    try:
        logger.info(f"💾 [TRIMMOMATIC-PROGRESS-DB] Updating pipeline_job_steps table... (PID={pid})")

        with database.get_db_connection() as conn:
            cursor = conn.cursor()

            # 업데이트 실행
            cursor.execute('''
                UPDATE pipeline_job_steps
                SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workbench_id = ? AND tool_name = 'trimmomatic'
            ''', (json_str, workbench_id))

            # 업데이트된 행 수 확인
            rows_affected = cursor.rowcount
            logger.info(f"📊 [TRIMMOMATIC-PROGRESS-DB] Database update affected {rows_affected} row(s) (PID={pid})")

            if rows_affected == 0:
                logger.warning(f"⚠️ [TRIMMOMATIC-PROGRESS-DB] No rows were updated - pipeline step may not exist for workbench {workbench_id} (PID={pid})")
                return False

            conn.commit()
            logger.info(f"✅ [TRIMMOMATIC-PROGRESS-DB] Database transaction committed successfully (PID={pid})")

        return True

    except Exception as e:
        logger.error(f"❌ [TRIMMOMATIC-PROGRESS-DB] Database update failed (PID={pid}): {e}")
        return False


def _execute_trimmomatic_db_operations_impl(current_process, process_info: str, sample_name: str, workbench_id: int, result_data: Dict[str, Any]) -> bool:
    """실제 Trimmomatic 데이터베이스 작업을 수행하는 구현 함수"""
    try:
        # 기존 progress_detail 가져오기
        logger.info(f"🔍 [TRIMMOMATIC-RESULT-DB] ⭐ Retrieving existing progress_detail from DB...")
        existing_data = {}

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            result = cursor.execute('''
                SELECT progress_detail FROM pipeline_job_steps
                WHERE workbench_id = ? AND tool_name = 'trimmomatic'
            ''', (workbench_id,)).fetchone()

            if result and result[0]:
                try:
                    existing_data = json.loads(result[0])
                    logger.info(f"✅ [TRIMMOMATIC-RESULT-DB] ⭐ Successfully loaded existing progress_detail: {len(existing_data.get('results', {}))} existing results")
                    logger.info(f"🔍 [TRIMMOMATIC-RESULT-DB] ⭐ Existing data keys: {existing_data.keys()}")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ [TRIMMOMATIC-RESULT-DB] Failed to parse existing progress_detail, initializing new: {e}")
                    existing_data = {"summary": {}, "results": {}}
            else:
                logger.info(f"ℹ️ [TRIMMOMATIC-RESULT-DB] ⭐ No existing progress_detail found, initializing new structure")
                existing_data = {"summary": {}, "results": {}}

        # 기존 구조 확인 및 보정
        if "results" not in existing_data:
            existing_data["results"] = {}
            logger.info(f"🔧 [TRIMMOMATIC-RESULT-DB] ⭐ Added missing 'results' section to progress_detail")

        if "summary" not in existing_data:
            existing_data["summary"] = {}
            logger.info(f"🔧 [TRIMMOMATIC-RESULT-DB] ⭐ Added missing 'summary' section to progress_detail")

        # results 섹션에 샘플 결과 추가
        logger.info(f"📝 [TRIMMOMATIC-RESULT-DB] ⭐ BEFORE adding - existing_data['results'] has {len(existing_data['results'])} samples")
        logger.info(f"📝 [TRIMMOMATIC-RESULT-DB] ⭐ Adding sample '{sample_name}' to results...")
        logger.info(f"📝 [TRIMMOMATIC-RESULT-DB] ⭐ result_data to add: parsing_successful={result_data.get('parsing_successful', False)}")

        previous_result = existing_data["results"].get(sample_name)
        existing_data["results"][sample_name] = result_data

        logger.info(f"📝 [TRIMMOMATIC-RESULT-DB] ⭐ AFTER adding - existing_data['results'] has {len(existing_data['results'])} samples")
        logger.info(f"📝 [TRIMMOMATIC-RESULT-DB] ⭐ Sample names in results: {list(existing_data['results'].keys())}")

        if previous_result:
            logger.info(f"🔄 [TRIMMOMATIC-RESULT-DB] Updated existing result for sample {sample_name}")
        else:
            logger.info(f"➕ [TRIMMOMATIC-RESULT-DB] ⭐ Added NEW result for sample {sample_name}")

        # 현재 총 결과 수 확인
        total_results = len(existing_data["results"])

        # 디버깅: 각 샘플의 parsing_successful 상태 확인
        logger.info(f"🔍 [TRIMMOMATIC-RESULT-DB] ⭐ Debugging - analyzing {total_results} results:")
        for sample_key, sample_result in existing_data["results"].items():
            parsing_status = sample_result.get('parsing_successful', False)
            logger.info(f"   ├─ {sample_key}: parsing_successful = {parsing_status}")

        successful_results = sum(1 for r in existing_data["results"].values() if r.get('parsing_successful', False))

        logger.info(f"📊 [TRIMMOMATIC-RESULT-DB] ⭐ Current results summary: {successful_results}/{total_results} samples with successful parsing")

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

        logger.info(f"📈 [TRIMMOMATIC-RESULT-DB] Updated summary: {successful_results}/{total_files} ({progress_percent:.1f}%)")

        # JSON 직렬화 테스트
        try:
            json_str = json.dumps(existing_data)
            json_size = len(json_str)
            logger.info(f"📦 [TRIMMOMATIC-RESULT-DB] JSON serialization successful: {json_size} characters")
        except (TypeError, ValueError) as e:
            logger.error(f"❌ [TRIMMOMATIC-RESULT-DB] JSON serialization failed: {e}")
            return False

        # UPDATE 직전 상태 로그 출력
        logger.info(f"💾 [TRIMMOMATIC-DB-UPDATE-BEFORE] ⭐ PID={current_process.pid} About to update trimmomatic step")
        logger.info(f"   ├─ Sample: {sample_name}")
        logger.info(f"   ├─ Total results to save: {total_results}")
        logger.info(f"   ├─ Successful results: {successful_results}")
        logger.info(f"   └─ JSON size: {len(json_str)} characters")

        # DB 업데이트 실행
        logger.info(f"💾 [TRIMMOMATIC-RESULT-DB] ⭐ Updating pipeline_job_steps table...")

        with database.get_db_connection() as conn:
            cursor = conn.cursor()

            # 업데이트 실행
            cursor.execute('''
                UPDATE pipeline_job_steps
                SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workbench_id = ? AND tool_name = 'trimmomatic'
            ''', (json_str, workbench_id))

            # 업데이트된 행 수 확인
            rows_affected = cursor.rowcount
            logger.info(f"📊 [TRIMMOMATIC-RESULT-DB] ⭐ Database update affected {rows_affected} row(s)")

            if rows_affected == 0:
                logger.warning(f"⚠️ [TRIMMOMATIC-RESULT-DB] No rows were updated - pipeline step may not exist for workbench {workbench_id}")
                return False

            conn.commit()
            logger.info(f"✅ [TRIMMOMATIC-RESULT-DB] ⭐ Database transaction committed successfully")

        logger.info(f"💾 [TRIMMOMATIC-DB-UPDATE-AFTER] ⭐ PID={current_process.pid} Successfully updated trimmomatic step, Sample: {sample_name}")

        # Lock 해제 직전 로그 (공유 Lock 사용)
        logger.debug(f"🔓 [TRIMMOMATIC-DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, Sample: {sample_name}, Operation: SUCCESS")

        return True

    except Exception as e:
        logger.error(f"❌ [TRIMMOMATIC-RESULT-DB] Failed to save sample result for {sample_name}: {e}")
        # Lock 해제 직전 로그 (에러 상황, 공유 Lock 사용)
        logger.debug(f"🔓 [TRIMMOMATIC-DB-LOCK-LEAVE] PID={current_process.pid} EXITING critical section - {process_info}, Sample: {sample_name}, Operation: ERROR")
        return False


def execute_trimmomatic(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    """Trimmomatic 실행 - job_step에서 직접 정보 추출"""
    try:
        # job_step에서 직접 정보 추출 (step_details 개념 제거)
        step_id = job_step['step_id'] 
        job_id = job_step['job_id']
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        workbench_id = job_step['workbench_id']

        logger.info(f"✂️ [TRIMMOMATIC] Starting Trimmomatic process")
        logger.debug(f"📋 [TRIMMOMATIC] Job Configuration:")
        logger.debug(f"   └─ workbench_id: {workbench_id}")
        logger.debug(f"   └─ step_id: {step_id}")

        # 입력 파일 결정 (job_step에서 직접 가져오기)
        input_dir = job_step['input_dir']
        input_files = json.loads(job_step['input_files'])
        output_dir = job_step['output_dir']

        # Note: input_files is used for filtering samples, not for direct file access
        # Actual file path resolution (compressed/uncompressed) happens in _find_file function later

        logger.debug(f"📂 [TRIMMOMATIC] Input Configuration:")
        logger.debug(f"   ├─ input_dir: {input_dir}")
        logger.debug(f"   ├─ input_files: {json.dumps(input_files, indent=4)}")
        logger.debug(f"   └─ output_dir: {output_dir}")

        logger.info(f"📊 [TRIMMOMATIC] Processing {len(input_files)} input file entries")

        # 출력 디렉터리 생성
        trimmomatic_output_dir = output_dir
        os.makedirs(trimmomatic_output_dir, exist_ok=True)
        logger.debug(f"📂 [TRIMMOMATIC] Output directory: {trimmomatic_output_dir}")

        # 데이터베이스에서 샘플 정보 조회 - backend.utils.database 사용
        with database.get_db_connection() as db_connection:
            db_connection.row_factory = sqlite3.Row
            cursor = db_connection.cursor()

            # ─────────────────────────────────────────────────────────────────
            # DB의 samples 테이블을 이용한 SE/PE 구성
            # ─────────────────────────────────────────────────────────────────
            logger.debug(f"🔍 [TRIMMOMATIC] Building file groups from 'samples' table...")

            # vizr_pipeline_samples 테이블에서 samples를 뽑아 json.load를 하여 rows에 할당한다.
            cursor.execute("""
                SELECT samples, layout
                FROM vizr_pipeline_samples
                WHERE workbench_id = ?
            """, (workbench_id,))
            pipeline_samples_result = cursor.fetchone()

            if pipeline_samples_result:
                samples_json = pipeline_samples_result['samples']
                layout = pipeline_samples_result['layout']
                logger.debug(f"📊 [TRIMMOMATIC] Retrieved samples from vizr_pipeline_samples (layout: {layout})")

                try:
                    # JSON 파싱하여 rows에 할당
                    samples_data = json.loads(samples_json)
                    rows = []
                    for sample in samples_data:
                        # vizr_pipeline_samples의 구조를 samples 테이블 구조로 변환
                        row = (
                            sample.get('sampleName', ''),     # sample_name
                            sample.get('groupName', ''),      # group_name
                            layout,             # layout
                            sample.get('file1', ''),          # file1_path
                            sample.get('file2', '')           # file2_path
                        )
                        rows.append(row)
                    logger.debug(f"✅ [TRIMMOMATIC] Converted {len(rows)} samples from vizr_pipeline_samples to rows format")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ [TRIMMOMATIC] Failed to parse samples JSON from vizr_pipeline_samples: {e}")
                    rows = []
            else:
                logger.warning(f"⚠️ [TRIMMOMATIC] No samples found in vizr_pipeline_samples, using samples table data")
                # rows는 이미 위에서 samples 테이블로부터 설정됨

            
        # SE/PE 자동 감지 및 샘플 구성
        sample_info_list = []

        file_groups = {}

        def _normalize_basename(name: str) -> str:
            return name.replace('.gz', '') if name else name

        selected_basenames = None
        if input_files:
            selected_basenames = set()
            for f in input_files:
                base = os.path.basename(f)
                selected_basenames.add(base)
                selected_basenames.add(_normalize_basename(base))

        def _abs_or_join(base_dir: str, p: str) -> str:
            if not p:
                return ''
            return p if os.path.isabs(p) else os.path.join(base_dir, p)

        for r in rows:
            s_name, g_name, s_layout, f1, f2 = r  # file1=R1, file2=R2
            if not f1:
                logger.warning(f"   └─ Skipping sample '{s_name}': file1_path is empty")
                continue

            # Smart file detection: check for both uncompressed and compressed files
            # Trimmomatic supports .gz files natively, so use whichever exists
            def _find_file(base_dir: str, filename: str) -> str:
                """
                Find file in either uncompressed or compressed form
                Returns the actual file path that exists, or empty string if not found
                """
                if not filename:
                    return ''

                # Check for uncompressed file first
                uncompressed_name = filename.replace('.gz', '') if filename.endswith('.gz') else filename
                uncompressed_path = _abs_or_join(base_dir, uncompressed_name)

                # Check for compressed file
                compressed_name = filename if filename.endswith('.gz') else filename + '.gz'
                compressed_path = _abs_or_join(base_dir, compressed_name)

                if os.path.exists(uncompressed_path):
                    # Prefer uncompressed file if available
                    logger.debug(f"   Found uncompressed: {os.path.basename(uncompressed_path)}")
                    return uncompressed_path
                elif os.path.exists(compressed_path):
                    # Use compressed file (Trimmomatic supports .gz natively)
                    logger.debug(f"   Found compressed: {os.path.basename(compressed_path)}")
                    return compressed_path
                else:
                    return ''

            # Find actual file paths
            f1_path = _find_file(input_dir, f1)
            f2_path = _find_file(input_dir, f2) if f2 else ''

            # Check if files were found
            f1_ok = bool(f1_path)
            f2_ok = bool(f2_path) if f2 else True  # SE면 True 취급

            # input_files 필터링 (실제 찾은 파일명으로)
            if selected_basenames is not None:
                f1_base = os.path.basename(f1_path) if f1_path else os.path.basename(f1)
                f2_base = os.path.basename(f2_path) if f2_path else (os.path.basename(f2) if f2 else None)
                f1_norm = _normalize_basename(f1_base)
                f2_norm = _normalize_basename(f2_base) if f2_base else None
                in_selected = (
                    (f1_norm in selected_basenames) or
                    (f2_norm in selected_basenames if f2_norm else False)
                )
                if not in_selected:
                    logger.debug(f"   └─ Skipping (filtered by input_files): sample='{s_name}'")
                    continue

            if s_layout and s_layout.lower() == 'pe':
                if not f2:
                    logger.warning(f"   └─ [PE] sample '{s_name}' has no file2_path; skipping")
                    continue
                if not f1_ok or not f2_ok:
                    logger.warning(f"   └─ [PE] Missing files for sample '{s_name}': "
                                f"R1={'OK' if f1_ok else 'MISSING'}, R2={'OK' if f2_ok else 'MISSING'}")
                    continue

                file_groups[s_name] = {'R1': f1_path, 'R2': f2_path}
                logger.debug(f"   ├─ {s_name} [PE]\n"
                            f"   │   ├─ R1: {f1_path}\n"
                            f"   │   └─ R2: {f2_path}")
            else:
                # SE로 처리
                if not f1_ok:
                    logger.warning(f"   └─ [SE] Missing file for sample '{s_name}': {f1_path}")
                    continue
                file_groups[s_name] = {'SE': f1_path}
                logger.debug(f"   ├─ {s_name} [SE]: {f1_path}")

        # 결과 요약 로그(기존 포맷 유지)
        logger.debug(f"📊 [TRIMMOMATIC] File grouping results:")
        for sample_name, files in file_groups.items():
            if 'SE' in files:
                logger.debug(f"   ├─ {sample_name} [SE]: {files['SE']}")
            elif 'R1' in files and 'R2' in files:
                logger.debug(f"   ├─ {sample_name} [PE]:")
                logger.debug(f"   │   ├─ R1: {files['R1']}")
                logger.debug(f"   │   └─ R2: {files['R2']}")
            else:
                logger.warning(f"   ├─ {sample_name} [INCOMPLETE]: {json.dumps(files, indent=6)}")
        # ─────────────────────────────────────────────────────────────────
        
        # 샘플 정보 구성
        logger.debug(f"🛠️  [TRIMMOMATIC] Building sample configuration...")
        for sample_name, files in file_groups.items():
            # 데이터베이스에서 condition(group_name) 찾기
            condition = 'unknown'
            for row in rows:
                s_name, g_name, s_layout, f1, f2 = row
                if s_name == sample_name:
                    condition = g_name
                    break

            sample_info = {
                'sample_name': sample_name,
                'condition': condition,
                'files': files,
                'output_base_dir': trimmomatic_output_dir
            }
            sample_info_list.append(sample_info)

            logger.debug(f"   ├─ Sample: {sample_name}")
            logger.debug(f"   │   ├─ Condition: {condition}")
            logger.debug(f"   │   ├─ File type: {'PE' if ('R1' in files and 'R2' in files) else 'SE'}")
            logger.debug(f"   │   └─ Output dir: {os.path.join(trimmomatic_output_dir, condition, sample_name)}")

        logger.info(f"✅ [TRIMMOMATIC] Configuration completed:")
        logger.info(f"   ├─ Total samples: {len(sample_info_list)}")
        logger.info(f"   ├─ SE samples: {sum(1 for s in sample_info_list if 'SE' in s['files'])}")
        logger.info(f"   └─ PE samples: {sum(1 for s in sample_info_list if 'R1' in s['files'] and 'R2' in s['files'])}")

        # Trimmomatic 파라미터 로그
        logger.debug(f"⚙️  [TRIMMOMATIC] Parameters:")
        trimmomatic_params = {k: v for k, v in parameters.items() if k.startswith('trimmomatic_')}
        if trimmomatic_params:
            for key, value in trimmomatic_params.items():
                logger.debug(f"   ├─ {key}: {value}")
        else:
            logger.debug(f"   └─ Using default parameters")
        
        # 멀티프로세싱으로 실행
        result = execute_trimmomatic_multi(sample_info_list, parameters, workbench_id, worker_id)
        return result

    except Exception as e:
        logger.error(f"❌ [TRIMMOMATIC] Error: {str(e)}")
        return {"status": "FAILED", "message": str(e)}


def execute_trimmomatic_multi(sample_info_list: List[Dict], parameters: Dict, workbench_id: int, worker_id: str = "worker") -> Dict[str, str]:
    """
    Trimmomatic SE/PE 통합 처리 (멀티프로세싱)
    멀티프로세싱 오케스트레이션
    """
    logger.info(f"✂️ [TRIMMOMATIC-MULTI] Starting multi-processing Trimmomatic")

    # 입력 샘플 정보 상세 로그
    logger.debug(f"📊 [TRIMMOMATIC-MULTI] Sample information summary:")
    logger.debug(f"   ├─ Total samples: {len(sample_info_list)}")

    se_count = sum(1 for s in sample_info_list if 'SE' in s.get('files', {}))
    pe_count = sum(1 for s in sample_info_list if 'R1' in s.get('files', {}) and 'R2' in s.get('files', {}))

    logger.debug(f"   ├─ SE samples: {se_count}")
    logger.debug(f"   ├─ PE samples: {pe_count}")
    logger.debug(f"   └─ Worker ID: {worker_id}")

    # 결과 딕셔너리 초기화
    results = {
        'success': True,
        'total_samples': len(sample_info_list),
        'successful_samples': 0,
        'failed_samples': 0,
        'stdout': '',
        'stderr': '',
        'sample_results': []
    }

    if not sample_info_list:
        logger.warning(f"⚠️ [TRIMMOMATIC-MULTI] No samples to process")
        return results

    try:
        # ✅ SharedState에서 해당 워커의 Event 가져오기
        worker_stop_event = shared_state.get_worker_event(worker_id)

        # 🔍 Event 상태 로깅
        is_set_before = worker_stop_event.is_set() if worker_stop_event else None
        logger.info(f"🔍 [TRIMMOMATIC-MULTI-DEBUG] Worker stop event status BEFORE pool creation:")
        logger.info(f"   ├─ Worker ID: {worker_id}")
        logger.info(f"   ├─ Event object: {worker_stop_event}")
        logger.info(f"   ├─ Event is_set: {is_set_before}")
        logger.info(f"   └─ Workbench ID: {workbench_id}")

        # 이미 set되어 있다면 명시적으로 clear
        if worker_stop_event and is_set_before:
            logger.warning(f"⚠️ [TRIMMOMATIC-MULTI-DEBUG] Worker stop event is already SET! Clearing it now...")
            worker_stop_event.clear()
            logger.info(f"✅ [TRIMMOMATIC-MULTI-DEBUG] Event cleared. New status: {worker_stop_event.is_set()}")

        # 멀티프로세싱 작업 인수 준비
        work_args = []
        for sample_info in sample_info_list:
            work_args.append((workbench_id, sample_info, parameters, f"{worker_id}_sub"))

        logger.debug(f"🚀 [TRIMMOMATIC-MULTI-POOL] Starting ProcessPoolRunner with {len(work_args)} samples...")

        # 초기 진행률 전송
        total_samples = len(work_args)
        completed_files = 0

        initial_progress = {
            "completed_files": completed_files,
            "total_files": total_samples,
            "progress_percent": 0.0
        }
        send_trimmomatic_progress_update(workbench_id, initial_progress)
        # 초기화 시점에는 shared_db_lock이 아직 생성되지 않음
        _save_trimmomatic_progress_to_db(workbench_id, completed_files, total_samples, None)

        # 프로세스 간 공유 Lock 생성 (Manager를 통한 진정한 프로세스 간 공유)
        import multiprocessing as mp
        manager = mp.Manager()
        shared_db_lock = manager.Lock()
        logger.debug(f"🔒 [TRIMMOMATIC-MULTI-POOL] Created shared DB lock for multiprocessing (lock_id={id(shared_db_lock)})")

        # ProcessPoolRunner로 병렬 처리 (Event 기반 stop 신호 + 공유 DB Lock)
        with ProcessPoolRunner(max_workers=4, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
            for i, result in enumerate(runner.map_unordered(run_single_trimmomatic, work_args)):

                # ✅ 단일 체크 - 워커가 실제로 중단되었는지만 확인
                if result.get('stopped_by_user', False):
                    logger.warning(f"⏹️ [TRIMMOMATIC-MULTI-POOL] Sample processing stopped by user")
                    runner.stop()  # 남은 작업들 중단
                    # Reset worker event for next execution
                    shared_state.reset_worker(worker_id)
                    break

                # 결과 처리
                sample_name = result.get('sample_name', 'unknown')
                success = result.get('success', False)

                if success:
                    results['successful_samples'] += 1
                    logger.debug(f"✅ [TRIMMOMATIC-MULTI-POOL] Sample {i+1}/{len(work_args)} completed: {sample_name}")
                else:
                    results['failed_samples'] += 1
                    logger.error(f"❌ [TRIMMOMATIC-MULTI-POOL] Sample {i+1}/{len(work_args)} failed: {sample_name}")

                # 샘플 결과 저장
                results['sample_results'].append(result)

                # stdout/stderr 누적
                if result.get('stdout'):
                    results['stdout'] += f"[{sample_name}] {result['stdout']}\n"
                if result.get('stderr'):
                    results['stderr'] += f"[{sample_name}] {result['stderr']}\n"

                # 진행률 업데이트 (성공/실패 관계없이 완료된 것으로 카운트)
                completed_files = results['successful_samples'] + results['failed_samples']
                progress_percent = (completed_files / total_samples * 100) if total_samples > 0 else 0

                progress_data = {
                    "completed_files": completed_files,
                    "total_files": total_samples,
                    "progress_percent": round(progress_percent, 2),
                    "current_sample": sample_name
                }

                # 실시간 진행률 전송
                send_trimmomatic_progress_update(workbench_id, progress_data)

                # DB에 진행률 저장 (수정된 안전한 버전 - results는 절대 덮어쓰지 않음)
                _save_trimmomatic_progress_to_db(workbench_id, completed_files, total_samples, shared_db_lock)

                logger.debug(f"📊 [TRIMMOMATIC-MULTI-POOL] Progress: {completed_files}/{total_samples} ({progress_percent:.1f}%)")

        # 전체 성공/실패 판단
        results['success'] = (results['failed_samples'] == 0)

        # 최종 진행률 전송
        final_progress = {
            "completed_files": results['successful_samples'] + results['failed_samples'],
            "total_files": total_samples,
            "progress_percent": 100.0
        }
        send_trimmomatic_progress_update(workbench_id, final_progress)
        # Note: _save_trimmomatic_progress_to_db는 완료 후에는 호출하지 않음 (job_worker에서 이미 step을 completed로 업데이트)

        logger.info(f"🏁 [TRIMMOMATIC-MULTI-POOL] Multi-processing completed")
        logger.info(f"   ├─ Total processed: {results['successful_samples'] + results['failed_samples']}")
        logger.info(f"   ├─ Successful: {results['successful_samples']}")
        logger.info(f"   └─ Failed: {results['failed_samples']}")

        if results['success']:
            logger.info(f"🎉 [TRIMMOMATIC-MULTI-POOL] All samples processed successfully!")
        else:
            logger.error(f"💥 [TRIMMOMATIC-MULTI-POOL] Some samples failed to process")
            
    except Exception as e:
        logger.error(f"💥 [TRIMMOMATIC-MULTI-POOL] Critical multi-processing error occurred:")
        logger.error(f"   ├─ Error type: {type(e).__name__}")
        logger.error(f"   ├─ Error message: {str(e)}")
        logger.error(f"   └─ This is a fatal error in the orchestration layer")
        results['success'] = False
        results['stderr'] += f"Critical multi-processing error: {str(e)}\n"
    
    # 🔄 Event 기반 시스템에서는 별도 상태 설정 불필요
    logger.info(f"🔄 [TRIMMOMATIC-MULTI] Worker {worker_id} processing completed")
    
    return results

def run_single_trimmomatic(workbench_id, sample_info: Dict[str, Any], parameters: Dict, worker_id: str = "worker", stop_event=None, shared_db_lock=None) -> Dict[str, Any]:
    """개별 Trimmomatic 샘플 처리 (SE/PE 자동 감지, 멀티프로세싱용 독립 함수)"""
    
    if stop_event and stop_event.is_set():
        return { 'success': False, 'stopped_by_user': True }
    
    # 로깅 설정 (각 프로세스에서 별도 로거 사용)
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(f"trimmomatic_worker_{os.getpid()}", 'INFO')
    start_time = time.time()
    
    try:
        sample_name = sample_info['sample_name']
        condition = sample_info['condition']
        files = sample_info['files']
        output_base_dir = sample_info['output_base_dir']
        
        logger.info(f"✂️ [TRIMMOMATIC-{os.getpid()}] Starting sample processing")
        logger.debug(f"📋 [TRIMMOMATIC-{os.getpid()}] Sample details:")
        logger.debug(f"   ├─ Sample name: {sample_name}")
        logger.debug(f"   ├─ Condition: {condition}")
        logger.debug(f"   ├─ Process PID: {os.getpid()}")
        logger.debug(f"   └─ Output base: {output_base_dir}")

        # Ensure input files are decompressed (auto-decompress .gz if needed)
        try:
            files = ensure_decompressed_files(files, logger)
        except FileNotFoundError as e:
            logger.error(f"   ❌ Input file preparation failed: {e}")
            return {
                'success': False,
                'sample_name': sample_name,
                'condition': condition,
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'output_files': [],
                'execution_time': time.time() - start_time,
                'error_message': str(e),
                'pid': os.getpid()
            }

        # 입력 파일 정보 로그
        file_type = 'PE' if ('R1' in files and 'R2' in files) else 'SE'
        logger.debug(f"📁 [TRIMMOMATIC-{os.getpid()}] Input files ({file_type}):")
        if file_type == 'SE':
            input_file = files['SE']
            file_size = os.path.getsize(input_file) if os.path.exists(input_file) else 0
            logger.debug(f"   └─ SE: {os.path.basename(input_file)} ({file_size:,} bytes)")
        else:
            input_r1 = files['R1']
            input_r2 = files['R2']
            r1_size = os.path.getsize(input_r1) if os.path.exists(input_r1) else 0
            r2_size = os.path.getsize(input_r2) if os.path.exists(input_r2) else 0
            logger.debug(f"   ├─ R1: {os.path.basename(input_r1)} ({r1_size:,} bytes)")
            logger.debug(f"   └─ R2: {os.path.basename(input_r2)} ({r2_size:,} bytes)")

        # condition 정보 추출 및 디렉토리 구조화: trimmomatic/{condition}/{sample}/
        sample_output_dir = os.path.join(output_base_dir, condition, sample_name)

        logger.debug(f"📂 [TRIMMOMATIC-{os.getpid()}] Output structure:")
        logger.debug(f"   └─ Sample dir: {sample_output_dir}")

        # 출력 디렉토리 생성
        os.makedirs(sample_output_dir, exist_ok=True)
        logger.debug(f"📁 [TRIMMOMATIC-{os.getpid()}] Created output directories")
        
        # Trimmomatic 파라미터 처리
        trimmomatic_params = {
            'trimmomatic_threads': 4,
            'trimmomatic_leading': 3,
            'trimmomatic_trailing': 3,
            'trimmomatic_slidingwindow_size': 4,
            'trimmomatic_slidingwindow_quality': 15,
            'trimmomatic_minlen': 36
        }
        
        # 어댑터 파일명 결정 (DB에서 버전명 가져와서 파일명으로 변환)
        adapter_version = 'TruSeq3'  # 기본 버전
        try:
            with database.get_db_connection() as db_connection:
                cursor = db_connection.cursor()

                if workbench_id:
                    cursor.execute("SELECT trimmomatic_adapter FROM pipeline_configurations WHERE workbench_id = ? ORDER BY created_at DESC LIMIT 1", (workbench_id,))
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-{os.getpid()}] No workbench_id found in sample_info")
                    cursor = None

                if cursor:
                    result = cursor.fetchone()
                    if result and result[0]:
                        adapter_version = result[0]
                        logger.debug(f"🔧 [TRIMMOMATIC-{os.getpid()}] Loaded adapter version from DB: {adapter_version}")
                db_connection.close()
        except Exception as e:
            logger.warning(f"⚠️ [TRIMMOMATIC-{os.getpid()}] Failed to load adapter from DB, using default: {e}")

        # 버전명과 파일 타입(SE/PE)을 조합하여 실제 어댑터 파일명 생성
        if adapter_version == 'none':
            # 어댑터 없음 - ILLUMINACLIP 단계 생략
            adapter_filename = None
            logger.info(f"ℹ️ [TRIMMOMATIC-{os.getpid()}] No adapter selected - skipping ILLUMINACLIP step")
        else:
            # 버전명 → 파일명 매핑 (SE/PE에 따라 다른 파일 선택)
            adapter_map = {
                'TruSeq3': {
                    'SE': 'TruSeq3-SE.fa',
                    'PE': 'TruSeq3-PE-2.fa'
                },
                'TruSeq2': {
                    'SE': 'TruSeq2-SE.fa',
                    'PE': 'TruSeq2-PE.fa'
                },
                'NexteraPE': {
                    'SE': 'NexteraPE-PE.fa',  # NexteraPE는 SE용이 없으므로 PE 파일 사용
                    'PE': 'NexteraPE-PE.fa'
                }
            }

            if adapter_version in adapter_map:
                adapter_filename = adapter_map[adapter_version][file_type]
                logger.debug(f"🔧 [TRIMMOMATIC-{os.getpid()}] Mapped adapter: {adapter_version} + {file_type} → {adapter_filename}")
            else:
                # 알 수 없는 버전명 - 기본값 사용
                adapter_filename = 'TruSeq3-PE-2.fa' if file_type == 'PE' else 'TruSeq3-SE.fa'
                logger.warning(f"⚠️ [TRIMMOMATIC-{os.getpid()}] Unknown adapter version '{adapter_version}', using default: {adapter_filename}")

        # 어댑터 파일 전체 경로 생성 (adapter_filename이 None이 아닐 때만)
        if adapter_filename:
            from config.shared_config import SharedConfig
            adapter_base_dir = os.path.join(SharedConfig.VIZR_PATH, "tools", "trimmomatic", "Trimmomatic-0.36", "adapters")
            adapter_full_path = os.path.join(adapter_base_dir, adapter_filename)

            # 어댑터 디렉토리가 없으면 /vizr/resource에서 복사
            if not os.path.exists(adapter_base_dir):
                source_adapter_dir = "/vizr/resource/tools/trimmomatic/Trimmomatic-0.36/adapters"
                if os.path.exists(source_adapter_dir):
                    logger.info(f"📋 [TRIMMOMATIC-{os.getpid()}] Adapter directory not found in {adapter_base_dir}")
                    logger.info(f"📋 [TRIMMOMATIC-{os.getpid()}] Copying adapter files from {source_adapter_dir}")
                    try:
                        import shutil
                        os.makedirs(adapter_base_dir, exist_ok=True)
                        # 디렉토리 전체 복사
                        for item in os.listdir(source_adapter_dir):
                            source_item = os.path.join(source_adapter_dir, item)
                            dest_item = os.path.join(adapter_base_dir, item)
                            if os.path.isfile(source_item):
                                shutil.copy2(source_item, dest_item)
                                logger.debug(f"  ✅ Copied: {item}")
                        logger.info(f"✅ [TRIMMOMATIC-{os.getpid()}] Successfully copied adapter files")
                    except Exception as e:
                        logger.error(f"❌ [TRIMMOMATIC-{os.getpid()}] Failed to copy adapter files: {e}")
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-{os.getpid()}] Source adapter directory not found: {source_adapter_dir}")

            # 어댑터 파일 존재 확인
            if not os.path.exists(adapter_full_path):
                logger.warning(f"⚠️ [TRIMMOMATIC-{os.getpid()}] Adapter file not found: {adapter_full_path}")

            trimmomatic_params['trimmomatic_adapter_file'] = adapter_full_path
            logger.debug(f"🔧 [TRIMMOMATIC-{os.getpid()}] Adapter file path: {adapter_full_path}")
        else:
            trimmomatic_params['trimmomatic_adapter_file'] = None
            logger.debug(f"🔧 [TRIMMOMATIC-{os.getpid()}] No adapter file will be used")

        logger.debug(f"⚙️ [TRIMMOMATIC-{os.getpid()}] Parameters:")
        for key, value in trimmomatic_params.items():
            logger.debug(f"   ├─ {key}: {value}")
        
        # 출력 파일명 생성
        output_files = []
        
        if file_type == 'SE':
            # Single-End 모드
            input_file = files['SE']
            output_file = os.path.join(sample_output_dir, f"{sample_name}_trimmed.fastq")
            output_files.append(output_file)

            # Trimmomatic SE 명령어 구성
            cmd = [
                'trimmomatic', 'SE',
                '-threads', str(trimmomatic_params['trimmomatic_threads']),
                input_file,
                output_file
            ]

            # ILLUMINACLIP은 어댑터 파일이 있을 때만 추가
            if trimmomatic_params['trimmomatic_adapter_file']:
                cmd.append(f"ILLUMINACLIP:{trimmomatic_params['trimmomatic_adapter_file']}:2:30:10")

            # 나머지 파라미터 추가
            cmd.extend([
                f"LEADING:{trimmomatic_params['trimmomatic_leading']}",
                f"TRAILING:{trimmomatic_params['trimmomatic_trailing']}",
                f"SLIDINGWINDOW:{trimmomatic_params['trimmomatic_slidingwindow_size']}:{trimmomatic_params['trimmomatic_slidingwindow_quality']}",
                f"MINLEN:{trimmomatic_params['trimmomatic_minlen']}"
            ])
            
        else:
            # Paired-End 모드
            input_r1 = files['R1']
            input_r2 = files['R2']
            output_r1_paired = os.path.join(sample_output_dir, f"{sample_name}_1_paired.fastq")
            output_r1_unpaired = os.path.join(sample_output_dir, f"{sample_name}_1_unpaired.fastq")
            output_r2_paired = os.path.join(sample_output_dir, f"{sample_name}_2_paired.fastq")
            output_r2_unpaired = os.path.join(sample_output_dir, f"{sample_name}_2_unpaired.fastq")

            output_files.extend([output_r1_paired, output_r1_unpaired, output_r2_paired, output_r2_unpaired])

            # Trimmomatic PE 명령어 구성
            cmd = [
                'trimmomatic', 'PE',
                '-threads', str(trimmomatic_params['trimmomatic_threads']),
                input_r1, input_r2,
                output_r1_paired, output_r1_unpaired,
                output_r2_paired, output_r2_unpaired
            ]

            # ILLUMINACLIP은 어댑터 파일이 있을 때만 추가
            if trimmomatic_params['trimmomatic_adapter_file']:
                cmd.append(f"ILLUMINACLIP:{trimmomatic_params['trimmomatic_adapter_file']}:2:30:10")

            # 나머지 파라미터 추가
            cmd.extend([
                f"LEADING:{trimmomatic_params['trimmomatic_leading']}",
                f"TRAILING:{trimmomatic_params['trimmomatic_trailing']}",
                f"SLIDINGWINDOW:{trimmomatic_params['trimmomatic_slidingwindow_size']}:{trimmomatic_params['trimmomatic_slidingwindow_quality']}",
                f"MINLEN:{trimmomatic_params['trimmomatic_minlen']}"
            ])
        
        logger.debug(f"🔧 [TRIMMOMATIC-{os.getpid()}] Command:")
        logger.debug(f"   └─ {' '.join(cmd)}")

        logger.debug(f"📤 [TRIMMOMATIC-{os.getpid()}] Expected output files:")
        for i, output_file in enumerate(output_files):
            logger.debug(f"   [{i+1}] {output_file}")

        # Docker 실행 (ProcessWrapper 사용)
        logger.debug(f"🚀 [TRIMMOMATIC-{os.getpid()}] Executing Trimmomatic...")
        
        wrapper = ProcessWrapper(worker_id)
        result = wrapper.run_command(cmd, stop_event=stop_event, cwd=sample_output_dir)
        
        execution_time = time.time() - start_time
        logger.debug(f"⏱️ [TRIMMOMATIC-{os.getpid()}] Execution completed in {execution_time:.2f}s")
        logger.debug(f"📊 [TRIMMOMATIC-{os.getpid()}] Return code: {result['returncode']}")

        # stdout/stderr 로깅 (길이 제한)
        if result['stdout']:
            stdout_lines = result['stdout'].strip().split('\n')
            logger.debug(f"📝 [TRIMMOMATIC-{os.getpid()}] STDOUT ({len(stdout_lines)} lines):")
            for i, line in enumerate(stdout_lines[:5]):  # 처음 5줄만 로그
                logger.debug(f"   [{i+1}] {line}")
            if len(stdout_lines) > 5:
                logger.debug(f"   ... and {len(stdout_lines) - 5} more lines")

        if result['stderr']:
            stderr_lines = result['stderr'].strip().split('\n')
            logger.debug(f"⚠️ [TRIMMOMATIC-{os.getpid()}] STDERR ({len(stderr_lines)} lines):")
            for i, line in enumerate(stderr_lines[:5]):  # 처음 5줄만 로그
                logger.debug(f"   [{i+1}] {line}")
            if len(stderr_lines) > 5:
                logger.debug(f"   ... and {len(stderr_lines) - 5} more lines")

        # 출력 파일 확인
        actual_output_files = []
        for output_file in output_files:
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                actual_output_files.append(output_file)
                logger.debug(f"✅ [TRIMMOMATIC-{os.getpid()}] Output: {os.path.basename(output_file)} ({file_size:,} bytes)")
            else:
                logger.warning(f"❌ [TRIMMOMATIC-{os.getpid()}] Missing: {os.path.basename(output_file)}")
        
        # 성공/실패 판단
        success = (result['returncode'] == 0 and len(actual_output_files) > 0)

        # Trimmomatic 결과 파싱 및 저장
        logger.debug(f"🔍 [TRIMMOMATIC-{os.getpid()}] Starting result parsing and DB storage for {sample_name}")

        trimmomatic_result = None
        parsing_attempted = False
        db_save_attempted = False
        db_save_successful = False

        if success:
            # Trimmomatic은 출력을 stdout 또는 stderr로 보낼 수 있으므로 둘 다 확인
            output_to_parse = None
            output_source = None

            if result['stdout']:
                output_to_parse = result['stdout']
                output_source = "stdout"
                logger.debug(f"📄 [TRIMMOMATIC-{os.getpid()}] Found output in stdout ({len(result['stdout'])} chars)")
            elif result['stderr']:
                output_to_parse = result['stderr']
                output_source = "stderr"
                logger.debug(f"📄 [TRIMMOMATIC-{os.getpid()}] Found output in stderr ({len(result['stderr'])} chars)")
            else:
                logger.warning(f"⚠️ [TRIMMOMATIC-{os.getpid()}] Sample {sample_name} succeeded but has empty stdout and stderr")

            if output_to_parse:
                parsing_attempted = True
                logger.debug(f"📄 [TRIMMOMATIC-{os.getpid()}] Attempting to parse {output_source} for {sample_name}")
                logger.debug(f"📋 [TRIMMOMATIC-{os.getpid()}] Output sample: {output_to_parse[:200]}...")

                trimmomatic_result = parse_trimmomatic_output(output_to_parse, sample_name)

                if trimmomatic_result and trimmomatic_result.get('parsing_successful', False):
                    logger.debug(f"✅ [TRIMMOMATIC-{os.getpid()}] Successfully parsed Trimmomatic output for {sample_name}")
                    logger.debug(f"📊 [TRIMMOMATIC-{os.getpid()}] Parsed values: "
                              f"input={trimmomatic_result.get('input_reads', 0)}, "
                              f"surviving={trimmomatic_result.get('surviving_reads', 0)}, "
                              f"dropped={trimmomatic_result.get('dropped_reads', 0)}")

                    # DB에 개별 샘플 결과 저장
                    db_save_attempted = True
                    logger.debug(f"💾 [TRIMMOMATIC-{os.getpid()}] Attempting to save parsed results to DB...")

                    db_save_successful = _save_trimmomatic_result_to_db(workbench_id, sample_name, trimmomatic_result, shared_db_lock)

                    if db_save_successful:
                        logger.debug(f"✅ [TRIMMOMATIC-{os.getpid()}] Successfully saved results to DB for {sample_name}")
                    else:
                        logger.error(f"❌ [TRIMMOMATIC-{os.getpid()}] Failed to save results to DB for {sample_name}")
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-{os.getpid()}] Failed to parse Trimmomatic output for {sample_name}")
                    if trimmomatic_result:
                        logger.debug(f"📋 [TRIMMOMATIC-{os.getpid()}] Parser result: {trimmomatic_result}")
        elif not success:
            logger.debug(f"ℹ️ [TRIMMOMATIC-{os.getpid()}] Skipping result parsing for failed sample {sample_name}")

        # 결과 로깅
        if success:
            logger.info(f"🎉 [TRIMMOMATIC-{os.getpid()}] Sample {sample_name} completed successfully")
            logger.debug(f"   ├─ Input files: {len(files)}")
            logger.debug(f"   ├─ Output files: {len(actual_output_files)}")
            logger.debug(f"   ├─ Execution time: {execution_time:.2f}s")
            logger.debug(f"   ├─ Parsing attempted: {'YES' if parsing_attempted else 'NO'}")
            logger.debug(f"   ├─ Parsing successful: {'YES' if trimmomatic_result and trimmomatic_result.get('parsing_successful') else 'NO'}")
            logger.debug(f"   ├─ DB save attempted: {'YES' if db_save_attempted else 'NO'}")
            logger.debug(f"   └─ DB save successful: {'YES' if db_save_successful else 'NO'}")

            if trimmomatic_result and trimmomatic_result.get('parsing_successful', False):
                logger.debug(f"📈 [TRIMMOMATIC-{os.getpid()}] Final results: Input={trimmomatic_result['input_reads']}, "
                          f"Surviving={trimmomatic_result['surviving_reads']} ({trimmomatic_result['survival_rate']:.1f}%), "
                          f"Dropped={trimmomatic_result['dropped_reads']} ({trimmomatic_result['drop_rate']:.1f}%)")
        else:
            logger.error(f"💥 [TRIMMOMATIC-{os.getpid()}] Sample {sample_name} failed")
            logger.error(f"   ├─ Return code: {result['returncode']}")
            logger.error(f"   ├─ Output files: {len(actual_output_files)}/{len(output_files)}")
            logger.error(f"   ├─ Parsing attempted: {'YES' if parsing_attempted else 'NO'}")
            logger.error(f"   └─ Reason: {'Command execution failed' if result['returncode'] != 0 else 'No output files generated'}")

        return {
            'success': success,
            'sample_name': sample_name,
            'condition': condition,
            'file_type': file_type,
            'returncode': result['returncode'],
            'stdout': result['stdout'],
            'stderr': result['stderr'],
            'output_files': actual_output_files,
            'execution_time': execution_time,
            'error_message': result['stderr'] if not success else None,
            'pid': os.getpid(),
            'trimmomatic_result': trimmomatic_result  # 파싱된 결과 추가
        }
        
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"Exception in run_single_trimmomatic: {str(e)}"
        logger.error(f"💥 [TRIMMOMATIC-{os.getpid()}] {error_msg}")
        
        return {
            'success': False,
            'sample_name': sample_info.get('sample_name', 'unknown'),
            'condition': sample_info.get('condition', 'unknown'),
            'file_type': 'unknown',
            'returncode': -1,
            'stdout': '',
            'stderr': error_msg,
            'output_files': [],
            'execution_time': execution_time,
            'error_message': error_msg,
            'pid': os.getpid()
        }


def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 trimmomatic tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering trimmomatic tool...")
    
    metadata = {
        'name': 'trimmomatic',
        'description': 'Trimmomatic sequence cleaning functionality',
        'version': '1.0.0',
        'supported_formats': ['.fastq', '.fastq.gz', '.fq', '.fq.gz'],
        'requirements': ['trimmomatic'],
        'parameters': {
            'trimmomatic_threads': 4,
            'trimmomatic_leading': 3,
            'trimmomatic_trailing': 3,
            'trimmomatic_slidingwindow_size': 4,
            'trimmomatic_slidingwindow_quality': 15,
            'trimmomatic_minlen': 36,
            'trimmomatic_adapter_file': 'TruSeq3-PE-2.fa'
        }
    }
    
    return coordinator.register_tool('trimmomatic', execute_trimmomatic, metadata)
