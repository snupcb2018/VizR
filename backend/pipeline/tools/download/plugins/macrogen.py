"""
Macrogen download functionality for VizR pipeline
Macrogen NGS 보고서에서 fastq 파일 다운로드
"""

import json
import os
import sqlite3
import hashlib
import time
import multiprocessing as mp
from typing import Dict, List, Any

from backend.pipeline.utils.process_runner import ProcessPoolRunner
from backend.pipeline.utils.shared_state import shared_state
from backend.pipeline.utils.redis_broker import get_redis_broker

from ..utils import (
    get_workbench_id_from_step,
    format_size,
    ensure_output_directory,
    create_download_result_template
)
from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


# ============================================================================
# 병렬 처리 - Multi download coordinator
# ============================================================================

def execute_macrogen_download_multi(file_info_list: List[Dict], parameters: Dict, worker_id: str = "worker", workbench_id: int = None) -> Dict:
    """ProcessPoolRunner를 사용한 병렬 Macrogen 다운로드"""
    logger.info(f"🚀 [MACROGEN-MULTI] Starting parallel Macrogen download (worker: {worker_id})")
    logger.info(f"   📊 Total files to process: {len(file_info_list)}")

    try:
        worker_stop_event = shared_state.get_worker_event(worker_id)
    except ValueError:
        worker_stop_event = None

    if not worker_stop_event:
        logger.warning(f"⚠️ [MACROGEN-MULTI] No stop event found for worker {worker_id}")

    results = create_download_result_template()

    try:
        max_workers = min(8, len(file_info_list))
        logger.info(f"🔧 [MACROGEN-MULTI] Using {max_workers} workers for {len(file_info_list)} files")

        manager = mp.Manager()
        shared_db_lock = manager.Lock()

        work_args = [(file_info, parameters, worker_id, workbench_id) for file_info in file_info_list]

        with ProcessPoolRunner(max_workers=max_workers, external_stop_event=worker_stop_event, shared_db_lock=shared_db_lock) as runner:
            file_results = list(runner.map_unordered(run_single_macrogen_download, work_args))

            downloaded_count = 0
            failed_count = 0
            stopped_by_user = False

            for result in file_results:
                if result.get('stopped_by_user', False):
                    logger.warning(f"🛑 [MACROGEN-MULTI] Download stopped by user")
                    runner.stop()
                    shared_state.reset_worker(worker_id)
                    stopped_by_user = True
                    break

                if result.get('success', False):
                    results['copied_files'].extend(result.get('files', []))
                    downloaded_count += 1
                    fname = result.get('filename', 'unknown')
                    logger.info(f"   ✅ Downloaded: {fname}")
                    results['stdout'] += f"Downloaded: {fname}\n"
                else:
                    failed_count += 1
                    fname = result.get('filename', 'unknown')
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"   ❌ Failed: {fname} - {error_msg}")
                    results['stderr'] += f"Failed: {fname} - {error_msg}\n"

            if stopped_by_user:
                results['stderr'] = 'Macrogen download stopped by user signal'
                results['success'] = False
                return results

        logger.info(f"🎉 [MACROGEN-MULTI] Completed: {downloaded_count} success, {failed_count} failed")

        if downloaded_count > 0 and failed_count == 0:
            results['success'] = True
            summary = f"Macrogen download completed: {downloaded_count} files"
            results['stdout'] += f"\n{summary}\n"
        elif downloaded_count > 0 and failed_count > 0:
            results['success'] = False
            summary = f"Macrogen download partially completed: {downloaded_count} success, {failed_count} failed"
            results['stdout'] += f"\n{summary}\n"
        else:
            results['success'] = False
            results['stderr'] += f"All Macrogen download operations failed: {failed_count} files"

        return results

    except Exception as e:
        error_msg = f"Multi-file Macrogen download failed: {str(e)}"
        logger.error(f"❌ [MACROGEN-MULTI] {error_msg}")
        results['stderr'] = error_msg
        results['success'] = False
        return results


# ============================================================================
# 단일 파일 다운로드 - ProcessPoolRunner worker
# ============================================================================

def run_single_macrogen_download(file_info: Dict, parameters: Dict, worker_id: str = "worker", workbench_id: int = None, stop_event=None, shared_db_lock=None) -> Dict:
    """단일 Macrogen fastq 파일 다운로드 - ProcessPoolRunner용"""
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')

    logger.info(f"[POOL] Macrogen worker initialized (pid={mp.current_process().pid})")

    filename = file_info.get('name', 'unknown')
    url = file_info.get('url', '')
    expected_md5 = file_info.get('md5', '')
    size_bytes = file_info.get('size_bytes', 0)
    output_dir = file_info.get('output_dir', '')

    try:
        import requests

        active_shared_state = shared_state

        logger.info(f"🚀 [{filename}] STARTING download [{worker_id}]")
        logger.info(f"   🔗 URL: {url}")
        logger.info(f"   📂 TO: {output_dir}")

        redis_broker = get_redis_broker()

        os.makedirs(output_dir, exist_ok=True)
        dest_path = os.path.join(output_dir, filename)

        # 이미 완료된 파일 확인 (MD5 검증)
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            if expected_md5:
                existing_md5 = _compute_md5(dest_path)
                if existing_md5 == expected_md5:
                    logger.info(f"✅ [{filename}] Already downloaded and MD5 verified, skipping")
                    existing_size = os.path.getsize(dest_path)
                    if workbench_id:
                        completion_data = {
                            'srr_run': filename,
                            'filename': filename,
                            'status': 'completed',
                            'progress_percent': 100.0,
                            'downloaded_size': existing_size,
                            'total_size': size_bytes or existing_size,
                            'total_bytes': size_bytes or existing_size,
                            'file_size': size_bytes or existing_size,
                            'worker_id': worker_id
                        }
                        if redis_broker.is_available():
                            redis_broker.publish_progress(
                                workbench_id=workbench_id,
                                task_type='data_download',
                                progress_data=completion_data
                            )
                        if shared_db_lock is not None:
                            _save_macrogen_progress_to_db(
                                workbench_id=workbench_id,
                                filename=filename,
                                progress_data=completion_data,
                                shared_db_lock=shared_db_lock
                            )
                    return {
                        'success': True,
                        'filename': filename,
                        'files': [dest_path],
                        'downloaded_size': existing_size,
                        'stopped_by_user': False
                    }
                else:
                    logger.warning(f"⚠️ [{filename}] MD5 mismatch, re-downloading")
            else:
                logger.info(f"✅ [{filename}] Already exists, skipping (no MD5 to verify)")
                existing_size = os.path.getsize(dest_path)
                if workbench_id:
                    completion_data = {
                        'srr_run': filename,
                        'filename': filename,
                        'status': 'completed',
                        'progress_percent': 100.0,
                        'downloaded_size': existing_size,
                        'total_size': size_bytes or existing_size,
                        'total_bytes': size_bytes or existing_size,
                        'file_size': size_bytes or existing_size,
                        'worker_id': worker_id
                    }
                    if redis_broker.is_available():
                        redis_broker.publish_progress(
                            workbench_id=workbench_id,
                            task_type='data_download',
                            progress_data=completion_data
                        )
                    if shared_db_lock is not None:
                        _save_macrogen_progress_to_db(
                            workbench_id=workbench_id,
                            filename=filename,
                            progress_data=completion_data,
                            shared_db_lock=shared_db_lock
                        )
                return {
                    'success': True,
                    'filename': filename,
                    'files': [dest_path],
                    'downloaded_size': existing_size,
                    'stopped_by_user': False
                }

        # HTTP 스트리밍 다운로드
        try:
            response = requests.get(url, timeout=600, stream=True)
            response.raise_for_status()
        except requests.RequestException as e:
            error_msg = f"HTTP download failed: {str(e)}"
            logger.error(f"❌ [{filename}] {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'filename': filename,
                'files': [],
                'downloaded_size': 0,
                'stopped_by_user': False
            }

        # 청크 단위 다운로드 + 진행상황 발행
        downloaded_bytes = 0
        chunk_size = 1024 * 1024  # 1MB
        md5_hash = hashlib.md5()
        last_publish_pct = -1

        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                # Stop 신호 확인
                if active_shared_state.is_worker_stopped(worker_id):
                    logger.info(f"🛑 [{filename}] Stop signal detected")
                    return {
                        'success': False,
                        'error': 'Download stopped by user',
                        'filename': filename,
                        'files': [],
                        'downloaded_size': downloaded_bytes,
                        'stopped_by_user': True
                    }

                if not chunk:
                    continue

                f.write(chunk)
                md5_hash.update(chunk)
                downloaded_bytes += len(chunk)

                # 진행상황 계산 및 Redis 발행 (5% 단위)
                if size_bytes > 0:
                    pct = int(downloaded_bytes / size_bytes * 100)
                    if pct >= last_publish_pct + 5 and workbench_id:
                        last_publish_pct = pct
                        progress_data = {
                            'srr_run': filename,  # keep data_download payload compatible with frontend consumers
                            'filename': filename,
                            'status': 'downloading',
                            'progress_percent': float(pct),
                            'downloaded_size': downloaded_bytes,
                            'total_size': size_bytes,
                            'total_bytes': size_bytes,
                            'file_size': size_bytes,
                            'worker_id': worker_id
                        }
                        if redis_broker.is_available():
                            redis_broker.publish_progress(
                                workbench_id=workbench_id,
                                task_type='data_download',
                                progress_data=progress_data
                            )
                        # DB 저장
                        if shared_db_lock is not None:
                            _save_macrogen_progress_to_db(
                                workbench_id=workbench_id,
                                filename=filename,
                                progress_data=progress_data,
                                shared_db_lock=shared_db_lock
                            )

        # MD5 검증
        actual_md5 = md5_hash.hexdigest()
        if expected_md5 and actual_md5 != expected_md5:
            error_msg = f"MD5 mismatch: expected {expected_md5}, got {actual_md5}"
            logger.error(f"❌ [{filename}] {error_msg}")
            # 손상된 파일 삭제
            try:
                os.remove(dest_path)
            except OSError:
                pass
            return {
                'success': False,
                'error': error_msg,
                'filename': filename,
                'files': [],
                'downloaded_size': downloaded_bytes,
                'stopped_by_user': False
            }

        final_size = os.path.getsize(dest_path)
        logger.info(f"✅ [{filename}] COMPLETED - {format_size(final_size)} [{worker_id}]")

        # 완료 이벤트 Redis 발행
        if workbench_id:
            completion_data = {
                'srr_run': filename,  # keep data_download payload compatible with frontend consumers
                'filename': filename,
                'status': 'completed',
                'progress_percent': 100.0,
                'downloaded_size': final_size,
                'total_size': size_bytes,
                'total_bytes': size_bytes,
                'file_size': size_bytes,
                'worker_id': worker_id
            }
            if redis_broker.is_available():
                redis_broker.publish_progress(
                    workbench_id=workbench_id,
                    task_type='data_download',
                    progress_data=completion_data
                )
            if shared_db_lock is not None:
                _save_macrogen_progress_to_db(
                    workbench_id=workbench_id,
                    filename=filename,
                    progress_data=completion_data,
                    shared_db_lock=shared_db_lock
                )

        return {
            'success': True,
            'filename': filename,
            'files': [dest_path],
            'downloaded_size': final_size,
            'stopped_by_user': False
        }

    except Exception as e:
        error_msg = f"Single file download failed: {str(e)}"
        logger.error(f"❌ [{filename}] {error_msg}")
        return {
            'success': False,
            'error': error_msg,
            'filename': filename,
            'files': [],
            'downloaded_size': 0,
            'stopped_by_user': False
        }


# ============================================================================
# 메인 실행 함수 - coordinator 진입점
# ============================================================================

def execute_macrogen_download(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict:
    """Macrogen 다운로드 - 코디네이터"""
    logger.info("🔽 🚚 MACROGEN DOWNLOAD OPERATION - COORDINATOR 🚚")

    try:
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        report_url = parameters.get('report_url', '')
        macrogen_files = parameters.get('macrogen_files', [])

        logger.info(f"🔗 [MACROGEN-DOWNLOAD] Report URL: {report_url}")
        logger.info(f"📋 [MACROGEN-DOWNLOAD] Files: {len(macrogen_files)}")

        if not macrogen_files:
            results = create_download_result_template()
            results['stderr'] = 'No files provided for Macrogen download'
            results['success'] = False
            return results

        # 워크벤치 정보 가져오기
        workbench_id = get_workbench_id_from_step(job_step)

        with database.get_db_connection() as db_connection:
            cursor = db_connection.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            raise ValueError(f"Workbench {workbench_id} not found")

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        output_dir = workbench_schema["quanti"]["raw"]

        logger.info(f"[MACROGEN_DOWNLOAD] Configuration:")
        logger.info(f"   🏷️  workbench_id: {workbench_id}")
        logger.info(f"   📂 output_dir: {output_dir}")
        logger.info(f"   📋 files: {len(macrogen_files)}")

        ensure_output_directory(output_dir)

        # 이미 존재하는 파일 확인 (MD5 검증 포함)
        files_to_download = []
        for file_info in macrogen_files:
            fname = file_info.get('name', '')
            dest_path = os.path.join(output_dir, fname)
            expected_md5 = file_info.get('md5', '')

            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                if expected_md5:
                    existing_md5 = _compute_md5(dest_path)
                    if existing_md5 == expected_md5:
                        logger.info(f"✅ [MACROGEN_DOWNLOAD] Already exists (MD5 ok): {fname}")
                        continue
                else:
                    logger.info(f"✅ [MACROGEN_DOWNLOAD] Already exists: {fname}")
                    continue

            file_info_with_dir = dict(file_info)
            file_info_with_dir['output_dir'] = output_dir
            files_to_download.append(file_info_with_dir)

        skipped_count = len(macrogen_files) - len(files_to_download)
        logger.info(f"📥 [MACROGEN_DOWNLOAD] {len(files_to_download)} files to download (skipped {skipped_count})")

        # Progress detail 초기화 (skip 파일은 completed로 반영)
        _initialize_macrogen_progress_detail(
            workbench_id=workbench_id,
            macrogen_files=macrogen_files,
            files_to_download=files_to_download,
            output_dir=output_dir
        )

        if not files_to_download:
            logger.info(f"✅ [MACROGEN_DOWNLOAD] All {len(macrogen_files)} files already exist, skipping")
            results = create_download_result_template()
            results['success'] = True
            results['stdout'] = f"Download step skipped: {len(macrogen_files)} files already exist in raw directory\n"
            return results

        # 병렬 다운로드 실행
        result = execute_macrogen_download_multi(files_to_download, parameters, worker_id, workbench_id)

        if result.get('success', False):
            result['stdout'] += f"Macrogen report: {report_url}\n"
            logger.info(f"✅ [MACROGEN_DOWNLOAD] Download completed")

        return result

    except Exception as e:
        error_msg = f"Macrogen download coordinator failed: {str(e)}"
        logger.error(f"❌ [MACROGEN_DOWNLOAD] {error_msg}")
        results = create_download_result_template()
        results['stderr'] = error_msg
        results['success'] = False
        return results


# ============================================================================
# 헬퍼 함수들
# ============================================================================

def _compute_md5(filepath: str) -> str:
    """파일의 MD5 해시 계산"""
    md5_hash = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def _initialize_macrogen_progress_detail(workbench_id: int, macrogen_files: List[Dict], files_to_download: List[Dict], output_dir: str):
    """progress_detail 초기값 생성"""
    try:
        existing_step = database.execute_query(
            """
            SELECT id, progress_detail
            FROM pipeline_job_steps
            WHERE workbench_id = ? AND step_name = 'download'
            ORDER BY id DESC
            LIMIT 1
            """,
            (workbench_id,)
        )

        if not existing_step:
            logger.warning(f"⚠️ [INIT-MACROGEN-PROGRESS] No download step found for workbench {workbench_id}")
            return

        step_record = existing_step[0]

        to_download_names = {f.get('name', '') for f in files_to_download}
        files_detail = {}
        total_size = 0
        downloaded_size = 0

        for file_info in macrogen_files:
            fname = file_info.get('name', 'unknown')
            expected_size = file_info.get('size_bytes', 0)
            dest_path = os.path.join(output_dir, fname)

            # 재실행에서 skip되는 파일은 completed로 표시해 pending으로 덮어쓰기 방지
            if fname and fname not in to_download_names:
                actual_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else expected_size
                file_size = expected_size or actual_size
                files_detail[fname] = {
                    'status': 'completed',
                    'progress': 100,
                    'file_size': file_size,
                    'downloaded_size': actual_size or file_size,
                    'timestamp': time.time()
                }
                total_size += file_size
                downloaded_size += actual_size or file_size
            else:
                files_detail[fname] = {
                    'status': 'pending',
                    'progress': 0,
                    'file_size': expected_size,
                    'downloaded_size': 0,
                    'timestamp': time.time()
                }
                total_size += expected_size

        completed_files = sum(1 for f in files_detail.values() if f.get('status') == 'completed')
        pending_files = sum(1 for f in files_detail.values() if f.get('status') == 'pending')
        progress_percent = (downloaded_size / total_size * 100.0) if total_size > 0 else (100.0 if completed_files else 0.0)
        progress_detail = {
            'summary': {
                'total_files': len(macrogen_files),
                'downloading_files': 0,
                'completed_files': completed_files,
                'pending_files': pending_files,
                'progress_percent': progress_percent,
                'total_size': total_size,
                'downloaded_size': downloaded_size,
                'last_updated': time.time()
            },
            'files': files_detail
        }

        database.execute_update(
            """
            UPDATE pipeline_job_steps
            SET progress_detail = ?, status = 'pending', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(progress_detail), step_record['id'])
        )

        logger.info(f"✅ [INIT-MACROGEN-PROGRESS] Progress detail initialized for workbench {workbench_id}: {len(macrogen_files)} files")

    except Exception as e:
        logger.error(f"❌ [INIT-MACROGEN-PROGRESS] Failed: {e}")


def _save_macrogen_progress_to_db(workbench_id: int, filename: str, progress_data: Dict, shared_db_lock):
    """DB의 progress_detail 업데이트"""
    if shared_db_lock is None:
        return

    with shared_db_lock:
        try:
            existing_step = database.execute_query(
                """
                SELECT id, progress_detail
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'download'
                ORDER BY id DESC
                LIMIT 1
                """,
                (workbench_id,)
            )

            if not existing_step:
                return

            step_record = existing_step[0]

            if step_record.get('progress_detail'):
                try:
                    progress_json_data = json.loads(step_record['progress_detail'])
                except (json.JSONDecodeError, TypeError):
                    progress_json_data = {'summary': {}, 'files': {}}
            else:
                progress_json_data = {'summary': {}, 'files': {}}

            status = progress_data.get('status', 'downloading')
            pct = progress_data.get('progress_percent', 0)
            dl_size = progress_data.get('downloaded_size', 0)
            total_size = progress_data.get('total_size', 0)

            progress_json_data.setdefault('files', {})[filename] = {
                'status': status,
                'progress': pct,
                'file_size': total_size,
                'downloaded_size': dl_size,
                'timestamp': time.time()
            }

            # summary 재계산
            all_files = progress_json_data.get('files', {})
            total_files = len(all_files)
            completed = sum(1 for f in all_files.values()
                            if f.get('status') == 'completed' or f.get('progress') == 100)
            downloading = sum(1 for f in all_files.values()
                              if f.get('status') == 'downloading' and f.get('progress', 0) < 100)
            pending = sum(1 for f in all_files.values() if f.get('status') == 'pending')
            total_size = sum(int(f.get('file_size') or 0) for f in all_files.values())
            downloaded_size = sum(int(f.get('downloaded_size') or 0) for f in all_files.values())
            progress_percent = (downloaded_size / total_size * 100.0) if total_size > 0 else (
                (completed / total_files * 100.0) if total_files > 0 else 0.0
            )

            progress_json_data['summary'] = {
                'total_files': total_files,
                'downloading_files': downloading,
                'completed_files': completed,
                'pending_files': pending,
                'progress_percent': progress_percent,
                'total_size': total_size,
                'downloaded_size': downloaded_size,
                'last_updated': time.time()
            }

            database.execute_update(
                """
                UPDATE pipeline_job_steps
                SET progress_detail = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(progress_json_data), step_record['id'])
            )

        except Exception as e:
            logger.error(f"❌ [DB-SAVE-MACROGEN] Failed to save progress: {e}")


# ============================================================================
# 플러그인 등록
# ============================================================================

def REGISTER_TOOL(coordinator):
    """🔌 자동 tool 등록 함수 - 코디네이터에 macrogen tool 등록"""
    logger.info(f"🔌 [TOOL-REG] Registering macrogen tool...")

    metadata = {
        'name': 'macrogen',
        'description': 'Macrogen NGS report fastq download functionality',
        'version': '1.0.0',
        'supported_formats': ['.fastq.gz', '.fq.gz'],
        'requirements': ['requests'],
        'parameters': {
            'dataInputMethod': 'macrogen',
            'report_url': 'string',
            'macrogen_files': 'array'
        }
    }

    return coordinator.register_tool('macrogen', execute_macrogen_download, metadata)
