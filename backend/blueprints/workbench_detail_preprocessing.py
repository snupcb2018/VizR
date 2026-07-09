"""
VizR Workbench Preprocessing Detail Blueprint
워크벤치 전처리(Trimmomatic, PRINSEQ) 관련 엔드포인트
"""
from flask import Blueprint, request, jsonify, session, current_app
import logging
import json

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
workbench_detail_preprocessing_bp = Blueprint('workbench_detail_preprocessing', __name__, url_prefix='/api/workbenches')

# Import database stuff and config settings
from backend.utils.database import get_db_connection_simple as get_db_connection
from backend.utils.auth import require_auth, get_current_user_id
from backend.blueprints.workbench_share import check_workbench_access


@workbench_detail_preprocessing_bp.route('/<int:workbench_id>/trimmomatic-progress', methods=['GET'])
@require_auth
def get_trimmomatic_progress(workbench_id):
    """
    Trimmomatic 진행률 조회 API

    Response:
    {
        "workbench_id": 1,
        "status": "running",
        "progress_data": {
            "completed_files": 3,
            "total_files": 10,
            "progress_percent": 30.0
        },
        "last_updated": "2024-01-15T10:30:00Z"
    }
    """
    logger.debug(f"[TRIMMOMATIC-PROGRESS] Fetching progress for workbench {workbench_id}")

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        user_id = get_current_user_id()
        has_access, permission = check_workbench_access(workbench_id, user_id)

        if not has_access:
            logger.warning(f"⚠️ [TRIMMOMATIC-PROGRESS] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Workbench not found or access denied'}), 404

        logger.debug(f"✅ [TRIMMOMATIC-PROGRESS] User {user_id} has {permission} access to workbench {workbench_id}")

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            if not workbench:
                logger.warning(f"⚠️ [TRIMMOMATIC-PROGRESS] Workbench {workbench_id} not found")
                return jsonify({'error': 'Workbench not found'}), 404

            logger.debug(f"[TRIMMOMATIC-PROGRESS] Workbench found: {workbench['name']}")

            # 먼저 모든 파이프라인 작업 확인
            all_steps = conn.execute('''
                SELECT step_name, tool_name, status, updated_at,
                       LENGTH(progress_detail) as detail_length,
                       SUBSTR(progress_detail, 1, 100) as detail_preview
                FROM pipeline_job_steps
                WHERE workbench_id = ?
                ORDER BY updated_at DESC
            ''', (workbench_id,)).fetchall()

            logger.debug(f"[TRIMMOMATIC-PROGRESS] Total pipeline steps for workbench {workbench_id}: {len(all_steps)}")
            for step in all_steps:
                logger.debug(f"  - Step: {step['step_name']}/{step['tool_name']}, Status: {step['status']}, "
                           f"Detail length: {step['detail_length']}, Updated: {step['updated_at']}")
                if step['detail_preview']:
                    logger.debug(f"    Preview: {step['detail_preview'][:100]}")

            # Trimmomatic step 조회 (step_name이 clean이고 tool_name이 trimmomatic인 경우)
            trimmomatic_step = conn.execute('''
                SELECT progress_detail, status, updated_at
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'clean' AND tool_name = 'trimmomatic'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            # Trimmomatic 진행률 처리
            progress_data = None
            status = 'not_started'
            last_updated = None

            if trimmomatic_step:
                logger.debug(f"[TRIMMOMATIC-PROGRESS] Trimmomatic step found")
                logger.debug(f"  - Status: {trimmomatic_step['status']}")
                logger.debug(f"  - Updated at: {trimmomatic_step['updated_at']}")
                logger.debug(f"  - progress_detail is None: {trimmomatic_step['progress_detail'] is None}")
                if trimmomatic_step['progress_detail']:
                    logger.debug(f"  - progress_detail length: {len(trimmomatic_step['progress_detail'])} chars")
                    logger.debug(f"  - progress_detail first 200 chars: {trimmomatic_step['progress_detail'][:200]}")

                status = trimmomatic_step['status']
                last_updated = trimmomatic_step['updated_at']

                if trimmomatic_step['progress_detail']:
                    try:
                        progress_data = json.loads(trimmomatic_step['progress_detail'])
                        logger.debug(f"[TRIMMOMATIC-PROGRESS] Parsed JSON keys: {list(progress_data.keys())}")

                        # 새로운 구조에서 summary 정보 추출
                        if 'summary' in progress_data:
                            summary_data = progress_data['summary']
                            logger.debug(f"  - Found 'summary' key with data: {summary_data}")
                            completed = summary_data.get('completed_files', 0)
                            total = summary_data.get('total_files', 0)
                            # progress_data를 summary_data로 설정 (frontend 호환성)
                            progress_data = summary_data
                        else:
                            # 기존 구조 호환성 유지
                            logger.debug(f"  - Using old structure (no 'summary' key)")
                            completed = progress_data.get('completed_files', 0)
                            total = progress_data.get('total_files', 0)

                        logger.debug(f"  - Completed/Total: {completed}/{total}")

                        # 진행률에 따른 상태 업데이트
                        if total > 0 and completed == total:
                            status = 'completed'
                            logger.info(f"✅ [TRIMMOMATIC-PROGRESS] Workbench {workbench_id} completed: {completed}/{total} files")
                        elif completed > 0:
                            status = 'running'

                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(f"❌ [TRIMMOMATIC-PROGRESS] Failed to parse progress_detail: {e}")
                        logger.error(f"  - Raw progress_detail: {trimmomatic_step['progress_detail'][:500]}")
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-PROGRESS] progress_detail is None or empty")
            else:
                logger.warning(f"⚠️ [TRIMMOMATIC-PROGRESS] No Trimmomatic step found for workbench {workbench_id}")

            logger.debug(f"[TRIMMOMATIC-PROGRESS] Final status: {status}, progress_data: {progress_data is not None}")

            return jsonify({
                'workbench_id': workbench_id,
                'status': status,
                'progress_data': progress_data,
                'last_updated': last_updated
            }), 200

    except Exception as e:
        logger.error(f"Failed to get Trimmomatic progress for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@workbench_detail_preprocessing_bp.route('/<int:workbench_id>/prinseq-progress', methods=['GET'])
@require_auth
def get_prinseq_progress(workbench_id):
    """
    PRINSEQ 진행률 조회 API

    Response:
    {
        "workbench_id": 1,
        "status": "running",
        "progress_data": {
            "completed_files": 5,
            "total_files": 10,
            "progress_percent": 50.0
        },
        "last_updated": "2024-01-15T10:35:00Z"
    }
    """
    logger.info(f"🔍 [PRINSEQ-PROGRESS] Fetching progress for workbench {workbench_id}")

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        user_id = get_current_user_id()
        has_access, permission = check_workbench_access(workbench_id, user_id)

        if not has_access:
            logger.warning(f"⚠️ [PRINSEQ-PROGRESS] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Workbench not found or access denied'}), 404

        logger.info(f"✅ [PRINSEQ-PROGRESS] User {user_id} has {permission} access to workbench {workbench_id}")

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            if not workbench:
                logger.warning(f"⚠️ [PRINSEQ-PROGRESS] Workbench {workbench_id} not found")
                return jsonify({'error': 'Workbench not found'}), 404

            logger.info(f"✅ [PRINSEQ-PROGRESS] Workbench found: {workbench['name']}")

            # PRINSEQ step 조회 (step_name이 clean이고 tool_name이 prinseq인 경우)
            prinseq_step = conn.execute('''
                SELECT progress_detail, status, updated_at
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'clean' AND tool_name = 'prinseq'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            # PRINSEQ 진행률 처리
            progress_data = None
            status = 'not_started'
            last_updated = None

            if prinseq_step:
                logger.info(f"✅ [PRINSEQ-PROGRESS] PRINSEQ step found")
                logger.info(f"  - Status: {prinseq_step['status']}")
                logger.info(f"  - Updated at: {prinseq_step['updated_at']}")
                logger.info(f"  - progress_detail is None: {prinseq_step['progress_detail'] is None}")
                if prinseq_step['progress_detail']:
                    logger.info(f"  - progress_detail length: {len(prinseq_step['progress_detail'])} chars")
                    logger.info(f"  - progress_detail first 200 chars: {prinseq_step['progress_detail'][:200]}")

                status = prinseq_step['status']
                last_updated = prinseq_step['updated_at']

                if prinseq_step['progress_detail']:
                    try:
                        progress_data = json.loads(prinseq_step['progress_detail'])
                        logger.info(f"🔍 [PRINSEQ-PROGRESS] Parsed JSON keys: {list(progress_data.keys())}")

                        # 새로운 구조에서 summary 정보 추출
                        if 'summary' in progress_data:
                            summary_data = progress_data['summary']
                            logger.info(f"  - Found 'summary' key with data: {summary_data}")
                            completed = summary_data.get('completed_files', 0)
                            total = summary_data.get('total_files', 0)
                            # progress_data를 summary_data로 설정 (frontend 호환성)
                            progress_data = summary_data
                        else:
                            # 기존 구조 호환성 유지
                            logger.info(f"  - Using old structure (no 'summary' key)")
                            completed = progress_data.get('completed_files', 0)
                            total = progress_data.get('total_files', 0)

                        logger.info(f"  - Completed/Total: {completed}/{total}")

                        # 진행률에 따른 상태 업데이트
                        if total > 0 and completed == total:
                            status = 'completed'
                        elif completed > 0:
                            status = 'running'

                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(f"❌ [PRINSEQ-PROGRESS] Failed to parse progress_detail: {e}")
                        logger.error(f"  - Raw progress_detail: {prinseq_step['progress_detail'][:500]}")
                else:
                    logger.warning(f"⚠️ [PRINSEQ-PROGRESS] progress_detail is None or empty")
            else:
                logger.warning(f"⚠️ [PRINSEQ-PROGRESS] No PRINSEQ step found for workbench {workbench_id}")

            logger.info(f"📊 [PRINSEQ-PROGRESS] Final status: {status}, progress_data: {progress_data is not None}")

            return jsonify({
                'workbench_id': workbench_id,
                'status': status,
                'progress_data': progress_data,
                'last_updated': last_updated
            }), 200

    except Exception as e:
        logger.error(f"Failed to get PRINSEQ progress for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@workbench_detail_preprocessing_bp.route('/<int:workbench_id>/trimmomatic-results', methods=['GET'])
@require_auth
def get_trimmomatic_results(workbench_id):
    """
    Trimmomatic 결과 조회 API

    Response:
    {
        "workbench_id": 1,
        "samples": [
            {
                "sample_name": "SRR001",
                "input_reads": 1000000,
                "surviving_reads": 950000,
                "survival_rate": 95.0,
                "adapter_removed": 45000
            }
        ],
        "total_count": 1,
        "summary": {
            "total_input_reads": 1000000,
            "total_surviving_reads": 950000,
            "average_survival_rate": 95.0,
            "total_removed": 45000
        }
    }
    """
    logger.info(f"📊 [TRIMMOMATIC-RESULTS] Fetching Trimmomatic results for workbench {workbench_id}")

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        user_id = get_current_user_id()
        has_access, permission = check_workbench_access(workbench_id, user_id)

        if not has_access:
            logger.warning(f"⚠️ [TRIMMOMATIC-RESULTS] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Workbench not found or access denied'}), 404

        logger.info(f"✅ [TRIMMOMATIC-RESULTS] User {user_id} has {permission} access to workbench {workbench_id}")

        # Get Trimmomatic results from progress_detail
        with get_db_connection() as conn:
            # Trimmomatic step의 progress_detail에서 results 조회
            trimmomatic_step = conn.execute('''
                SELECT progress_detail, status, updated_at
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'clean' AND tool_name = 'trimmomatic'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            # 디버깅: Step 존재 여부 확인
            if not trimmomatic_step:
                logger.warning(f"⚠️ [TRIMMOMATIC-RESULTS] No Trimmomatic step found for workbench {workbench_id}")
                return jsonify({
                    'workbench_id': workbench_id,
                    'samples': [],
                    'total_count': 0,
                    'summary': {
                        'total_input_reads': 0,
                        'total_surviving_reads': 0,
                        'average_survival_rate': 0.0,
                        'total_removed': 0
                    }
                }), 200

            # 디버깅: progress_detail 내용 확인
            logger.info(f"🔍 [TRIMMOMATIC-RESULTS] Step status: {trimmomatic_step['status']}")
            logger.info(f"🔍 [TRIMMOMATIC-RESULTS] progress_detail exists: {trimmomatic_step['progress_detail'] is not None}")
            if trimmomatic_step['progress_detail']:
                logger.info(f"🔍 [TRIMMOMATIC-RESULTS] progress_detail length: {len(trimmomatic_step['progress_detail'])} chars")
                logger.info(f"🔍 [TRIMMOMATIC-RESULTS] progress_detail preview (first 200 chars): {trimmomatic_step['progress_detail'][:200]}")

            if not trimmomatic_step['progress_detail']:
                logger.warning(f"⚠️ [TRIMMOMATIC-RESULTS] progress_detail is empty for workbench {workbench_id}")
                return jsonify({
                    'workbench_id': workbench_id,
                    'samples': [],
                    'total_count': 0,
                    'summary': {
                        'total_input_reads': 0,
                        'total_surviving_reads': 0,
                        'average_survival_rate': 0.0,
                        'total_removed': 0
                    }
                }), 200

            try:
                progress_data = json.loads(trimmomatic_step['progress_detail'])
                logger.info(f"🔍 [TRIMMOMATIC-RESULTS] progress_data keys: {list(progress_data.keys())}")

                results_data = progress_data.get('results', {})
                logger.info(f"🔍 [TRIMMOMATIC-RESULTS] results_data type: {type(results_data)}, length: {len(results_data)}")

                if not results_data:
                    logger.warning(f"⚠️ [TRIMMOMATIC-RESULTS] results section is empty for workbench {workbench_id}")
                    logger.info(f"📋 [TRIMMOMATIC-RESULTS] Full progress_data structure: {json.dumps(progress_data, indent=2)[:500]}...")
                else:
                    logger.info(f"📋 [TRIMMOMATIC-RESULTS] Sample names in results: {list(results_data.keys())}")

                # 샘플별 결과 정리
                samples = []
                total_input_reads = 0
                total_surviving_reads = 0
                total_removed = 0

                for sample_name, result in results_data.items():
                    if result.get('parsing_successful', False):
                        sample_result = {
                            'sample_name': sample_name,
                            'input_reads': result.get('input_reads', 0),
                            'surviving_reads': result.get('surviving_reads', 0),
                            'survival_rate': result.get('survival_rate', 0.0),
                            'adapter_removed': result.get('dropped_reads', 0)  # dropped_reads를 adapter_removed로 매핑
                        }
                        samples.append(sample_result)

                        # 전체 통계 누적
                        total_input_reads += sample_result['input_reads']
                        total_surviving_reads += sample_result['surviving_reads']
                        total_removed += sample_result['adapter_removed']

                # vizr_pipeline_samples 테이블의 samples JSON에서 샘플 순서 가져오기
                sample_order = {}
                sample_order_query = conn.execute('''
                    SELECT samples
                    FROM vizr_pipeline_samples
                    WHERE workbench_id = ?
                    LIMIT 1
                ''', (workbench_id,)).fetchone()

                if sample_order_query and sample_order_query['samples']:
                    try:
                        samples_json = json.loads(sample_order_query['samples'])
                        # JSON 배열 내 sampleName 순서대로 인덱스 부여
                        for index, sample_info in enumerate(samples_json):
                            if 'sampleName' in sample_info:
                                sample_order[sample_info['sampleName']] = index

                        logger.info(f"📋 [TRIMMOMATIC-RESULTS] Sample order from JSON: {sample_order}")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"⚠️ [TRIMMOMATIC-RESULTS] Failed to parse samples JSON: {e}")
                        sample_order = {}
                else:
                    logger.warning(f"⚠️ [TRIMMOMATIC-RESULTS] No samples JSON found for workbench {workbench_id}")
                    sample_order = {}

                # 샘플 순서에 따라 정렬
                def get_sample_order(sample):
                    sample_name = sample['sample_name']
                    return sample_order.get(sample_name, 999)  # DB에 없는 샘플은 맨 뒤로

                samples.sort(key=get_sample_order)
                logger.info(f"📊 [TRIMMOMATIC-RESULTS] Samples sorted by database order: {[s['sample_name'] for s in samples]}")

                # 평균 생존율 계산
                average_survival_rate = (total_surviving_reads / total_input_reads * 100) if total_input_reads > 0 else 0.0

                # 최종 결과 구성
                results = {
                    'workbench_id': workbench_id,
                    'samples': samples,
                    'total_count': len(samples),
                    'summary': {
                        'total_input_reads': total_input_reads,
                        'total_surviving_reads': total_surviving_reads,
                        'average_survival_rate': round(average_survival_rate, 2),
                        'total_removed': total_removed
                    }
                }

                logger.info(f"✅ [TRIMMOMATIC-RESULTS] Successfully prepared results for workbench {workbench_id}: {len(samples)} samples")

                return jsonify(results), 200

            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse Trimmomatic progress_detail for workbench {workbench_id}: {e}")
                return jsonify({'error': 'Failed to parse Trimmomatic results'}), 500

    except Exception as e:
        logger.error(f"Failed to get Trimmomatic results for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@workbench_detail_preprocessing_bp.route('/<int:workbench_id>/prinseq-results', methods=['GET'])
@require_auth
def get_prinseq_results(workbench_id):
    """
    PRINSEQ 결과 조회 API

    Response:
    {
        "workbench_id": 1,
        "samples": [
            {
                "sample_name": "SRR001",
                "input_sequences": 21917767,
                "good_sequences": 21054717,
                "bad_sequences": 863050,
                "good_rate": 96.06,
                "bad_rate": 3.94
            }
        ],
        "total_count": 1,
        "summary": {
            "total_input_sequences": 21917767,
            "total_good_sequences": 21054717,
            "total_bad_sequences": 863050,
            "average_good_rate": 96.06,
            "average_bad_rate": 3.94
        }
    }
    """
    logger.info(f"📊 [PRINSEQ-RESULTS] Fetching PRINSEQ results for workbench {workbench_id}")

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        user_id = get_current_user_id()
        has_access, permission = check_workbench_access(workbench_id, user_id)

        if not has_access:
            logger.warning(f"⚠️ [PRINSEQ-RESULTS] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Workbench not found or access denied'}), 404

        logger.info(f"✅ [PRINSEQ-RESULTS] User {user_id} has {permission} access to workbench {workbench_id}")

        # Get PRINSEQ results from progress_detail
        with get_db_connection() as conn:
            # PRINSEQ step의 progress_detail에서 results 조회
            prinseq_step = conn.execute('''
                SELECT progress_detail, status, updated_at
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'clean' AND tool_name = 'prinseq'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            # 디버깅: Step 존재 여부 확인
            if not prinseq_step:
                logger.warning(f"⚠️ [PRINSEQ-RESULTS] No PRINSEQ step found for workbench {workbench_id}")
                return jsonify({
                    'workbench_id': workbench_id,
                    'samples': [],
                    'total_count': 0,
                    'summary': {
                        'total_input_sequences': 0,
                        'total_good_sequences': 0,
                        'total_bad_sequences': 0,
                        'average_good_rate': 0.0,
                        'average_bad_rate': 0.0
                    }
                }), 200

            # 디버깅: progress_detail 내용 확인
            logger.info(f"🔍 [PRINSEQ-RESULTS] Step status: {prinseq_step['status']}")
            logger.info(f"🔍 [PRINSEQ-RESULTS] progress_detail exists: {prinseq_step['progress_detail'] is not None}")
            if prinseq_step['progress_detail']:
                logger.info(f"🔍 [PRINSEQ-RESULTS] progress_detail length: {len(prinseq_step['progress_detail'])} chars")
                logger.info(f"🔍 [PRINSEQ-RESULTS] progress_detail preview (first 200 chars): {prinseq_step['progress_detail'][:200]}")

            if not prinseq_step['progress_detail']:
                logger.warning(f"⚠️ [PRINSEQ-RESULTS] progress_detail is empty for workbench {workbench_id}")
                return jsonify({
                    'workbench_id': workbench_id,
                    'samples': [],
                    'total_count': 0,
                    'summary': {
                        'total_input_sequences': 0,
                        'total_good_sequences': 0,
                        'total_bad_sequences': 0,
                        'average_good_rate': 0.0,
                        'average_bad_rate': 0.0
                    }
                }), 200

            try:
                progress_data = json.loads(prinseq_step['progress_detail'])
                logger.info(f"🔍 [PRINSEQ-RESULTS] progress_data keys: {list(progress_data.keys())}")

                results_data = progress_data.get('results', {})
                logger.info(f"🔍 [PRINSEQ-RESULTS] results_data type: {type(results_data)}, length: {len(results_data)}")

                if not results_data:
                    logger.warning(f"⚠️ [PRINSEQ-RESULTS] results section is empty for workbench {workbench_id}")
                    logger.info(f"📋 [PRINSEQ-RESULTS] Full progress_data structure: {json.dumps(progress_data, indent=2)[:500]}...")
                else:
                    logger.info(f"📋 [PRINSEQ-RESULTS] Sample names in results: {list(results_data.keys())}")

                # 샘플별 결과 정리
                samples = []
                total_input_sequences = 0
                total_good_sequences = 0
                total_bad_sequences = 0

                for sample_name, result in results_data.items():
                    if result.get('parsing_successful', False):
                        sample_result = {
                            'sample_name': sample_name,
                            'input_sequences': result.get('input_sequences', 0),
                            'good_sequences': result.get('good_sequences', 0),
                            'bad_sequences': result.get('bad_sequences', 0),
                            'good_rate': result.get('good_rate', 0.0),
                            'bad_rate': result.get('bad_rate', 0.0),
                            'min_len_filtered': result.get('min_len_filtered'),
                            'min_qual_mean_filtered': result.get('min_qual_mean_filtered'),
                            'parsing_successful': result.get('parsing_successful', False)
                        }
                        samples.append(sample_result)

                        # 전체 통계 누적
                        total_input_sequences += sample_result['input_sequences']
                        total_good_sequences += sample_result['good_sequences']
                        total_bad_sequences += sample_result['bad_sequences']

                # vizr_pipeline_samples 테이블의 samples JSON에서 샘플 순서 가져오기
                sample_order = {}
                sample_order_query = conn.execute('''
                    SELECT samples
                    FROM vizr_pipeline_samples
                    WHERE workbench_id = ?
                    LIMIT 1
                ''', (workbench_id,)).fetchone()

                if sample_order_query and sample_order_query['samples']:
                    try:
                        samples_json = json.loads(sample_order_query['samples'])
                        # JSON 배열 내 sampleName 순서대로 인덱스 부여
                        for index, sample_info in enumerate(samples_json):
                            if 'sampleName' in sample_info:
                                sample_order[sample_info['sampleName']] = index

                        logger.info(f"📋 [PRINSEQ-RESULTS] Sample order from JSON: {sample_order}")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"⚠️ [PRINSEQ-RESULTS] Failed to parse samples JSON: {e}")
                        sample_order = {}
                else:
                    logger.warning(f"⚠️ [PRINSEQ-RESULTS] No samples JSON found for workbench {workbench_id}")
                    sample_order = {}

                # 샘플 순서에 따라 정렬
                def get_sample_order(sample):
                    sample_name = sample['sample_name']
                    return sample_order.get(sample_name, 999)  # DB에 없는 샘플은 맨 뒤로

                samples.sort(key=get_sample_order)
                logger.info(f"📊 [PRINSEQ-RESULTS] Samples sorted by database order: {[s['sample_name'] for s in samples]}")

                # 평균 비율 계산
                average_good_rate = (total_good_sequences / total_input_sequences * 100) if total_input_sequences > 0 else 0.0
                average_bad_rate = (total_bad_sequences / total_input_sequences * 100) if total_input_sequences > 0 else 0.0

                # 최종 결과 구성
                results = {
                    'workbench_id': workbench_id,
                    'samples': samples,
                    'total_count': len(samples),
                    'summary': {
                        'total_input_sequences': total_input_sequences,
                        'total_good_sequences': total_good_sequences,
                        'total_bad_sequences': total_bad_sequences,
                        'average_good_rate': round(average_good_rate, 2),
                        'average_bad_rate': round(average_bad_rate, 2)
                    }
                }

                logger.info(f"✅ [PRINSEQ-RESULTS] Successfully prepared results for workbench {workbench_id}: {len(samples)} samples")

                return jsonify(results), 200

            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse PRINSEQ progress_detail for workbench {workbench_id}: {e}")
                return jsonify({'error': 'Failed to parse PRINSEQ results'}), 500

    except Exception as e:
        logger.error(f"Failed to get PRINSEQ results for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500
