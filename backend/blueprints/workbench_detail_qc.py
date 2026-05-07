"""
VizR Workbench QC Detail Blueprint
워크벤치 Quality Control 관련 엔드포인트
"""
from flask import Blueprint, request, jsonify, session, current_app
import logging
import json

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
workbench_detail_qc_bp = Blueprint('workbench_detail_qc', __name__, url_prefix='/api/workbenches')

# Import database stuff and config settings
from backend.utils.database import get_db_connection_simple as get_db_connection
from backend.utils.auth import require_auth, get_current_user_id
from backend.blueprints.workbench_share import check_workbench_access


@workbench_detail_qc_bp.route('/<int:workbench_id>/qc-progress', methods=['GET'])
@require_auth
def get_qc_progress(workbench_id):
    """워크벤치의 QC 진행상황 조회"""
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        user_id = get_current_user_id()
        has_access, permission = check_workbench_access(workbench_id, user_id)

        if not has_access:
            logger.warning(f"⚠️ [QC-PROGRESS] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Workbench not found or access denied'}), 404

        logger.info(f"✅ [QC-PROGRESS] User {user_id} has {permission} access to workbench {workbench_id}")

        with get_db_connection() as conn:

            # QC step의 progress_detail 조회
            qc_step = conn.execute('''
                SELECT progress_detail, status, updated_at
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'qc'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if not qc_step:
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': 'not_started',
                    'progress_data': None,
                    'last_updated': None
                }), 200

            if not qc_step['progress_detail']:
                # QC step은 있지만 진행률이 없는 경우 DB status 그대로 반환
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': qc_step['status'],  # DB status 그대로 반환 (pending/running)
                    'progress_data': None,
                    'last_updated': qc_step['updated_at']
                }), 200

            # progress_detail JSON 파싱
            try:
                progress_data = json.loads(qc_step['progress_detail'])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse QC progress_detail for workbench {workbench_id}: {e}")
                progress_data = None

            # 상태 결정 (completed_files == total_files이면 completed)
            status = qc_step['status']
            logger.info(f"🔄 [QC-API-DEBUG] Initial DB status: '{status}'")

            if progress_data:
                completed = progress_data.get('completed_files', 0)
                total = progress_data.get('total_files', 0)
                logger.info(f"📈 [QC-API-DEBUG] Progress: {completed}/{total} files completed")

                if total > 0 and completed == total:
                    status = 'completed'
                    logger.info(f"✅ [QC-API-DEBUG] All files completed - status: '{status}'")
                elif completed > 0:
                    status = 'running'
                    logger.info(f"🔄 [QC-API-DEBUG] Files in progress - status: '{status}'")
                else:
                    logger.info(f"⏳ [QC-API-DEBUG] No files completed yet - keeping DB status: '{status}'")

            logger.info(f"🎯 [QC-API-DEBUG] Final API response - status: '{status}', progress_data: {progress_data}")

            return jsonify({
                'workbench_id': workbench_id,
                'status': status,
                'progress_data': progress_data,
                'last_updated': qc_step['updated_at']
            }), 200

    except Exception as e:
        logger.error(f"Failed to get QC progress for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@workbench_detail_qc_bp.route('/<int:workbench_id>/qc/results', methods=['GET'])
@require_auth
def get_qc_results(workbench_id):
    """
    Get FastQC analysis results for a workbench

    Returns parsed FastQC data transformed into chart-ready format
    """
    from backend.utils.fastqc_parser import get_all_qc_results

    logger.info(f"📊 [QC-RESULTS] Fetching QC results for workbench {workbench_id}")

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        user_id = get_current_user_id()
        has_access, permission = check_workbench_access(workbench_id, user_id)

        if not has_access:
            logger.warning(f"⚠️ [QC-RESULTS] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Workbench not found or access denied'}), 404

        logger.info(f"✅ [QC-RESULTS] User {user_id} has {permission} access to workbench {workbench_id}")

        # Get all QC results using the parser module
        results = get_all_qc_results(workbench_id)

        logger.info(f"✅ [QC-RESULTS] Successfully fetched {results['total_count']} samples for workbench {workbench_id}")

        return jsonify(results), 200

    except Exception as e:
        logger.error(f"Failed to get QC results for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500
