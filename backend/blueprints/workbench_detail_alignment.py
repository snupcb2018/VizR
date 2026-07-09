"""
VizR Workbench Alignment Detail Blueprint
워크벤치 정렬(HISAT2) 관련 엔드포인트
"""
from flask import Blueprint, request, jsonify, session, current_app
import logging
import json

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
workbench_detail_alignment_bp = Blueprint('workbench_detail_alignment', __name__, url_prefix='/api/workbenches')

# Import database stuff and config settings
from backend.utils.database import get_db_connection_simple as get_db_connection
from backend.utils.auth import require_auth, get_current_user_id
from backend.blueprints.workbench_share import check_workbench_access


@workbench_detail_alignment_bp.route('/<int:workbench_id>/alignment-progress', methods=['GET'])
@require_auth
def get_alignment_progress(workbench_id):
    """
    Alignment 진행률 조회 API (HISAT2)

    Response:
    {
        "workbench_id": 1,
        "status": "running",
        "progress_data": {
            "completed_files": 2,
            "total_files": 5,
            "progress_percent": 40.0,
            "current_sample": "DC1"
        },
        "last_updated": "2024-01-15T10:35:00Z"
    }
    """
    logger.info(f"🔍 [ALIGNMENT-PROGRESS-API] Starting alignment progress query for workbench {workbench_id}")
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        user_id = get_current_user_id()
        has_access, permission = check_workbench_access(workbench_id, user_id)

        if not has_access:
            logger.warning(f"⚠️ [ALIGNMENT-PROGRESS-API] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Workbench not found or access denied'}), 404

        logger.info(f"✅ [ALIGNMENT-PROGRESS-API] User {user_id} has {permission} access to workbench {workbench_id}")

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            if not workbench:
                logger.warning(f"⚠️ [ALIGNMENT-PROGRESS-API] Workbench {workbench_id} not found")
                return jsonify({'error': 'Workbench not found'}), 404

            logger.info(f"✅ [ALIGNMENT-PROGRESS-API] Workbench found: {workbench['name']}")

            # HISAT2 step 조회 (step_name이 alignment이고 tool_name이 hisat2인 경우)
            logger.info(f"🔍 [ALIGNMENT-PROGRESS-API] Querying HISAT2 step for workbench {workbench_id}")
            hisat2_step = conn.execute('''
                SELECT progress_detail, status, updated_at, tool_name
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'alignment'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if hisat2_step:
                logger.info(f"📊 [ALIGNMENT-PROGRESS-API] Found alignment step: tool={hisat2_step['tool_name']}, status={hisat2_step['status']}, updated_at={hisat2_step['updated_at']}")
            else:
                logger.info(f"ℹ️ [ALIGNMENT-PROGRESS-API] No alignment step found for workbench {workbench_id}")

            # HISAT2 진행률 처리
            progress_data = None
            status = 'not_started'
            last_updated = None

            if hisat2_step:
                status = hisat2_step['status']
                last_updated = hisat2_step['updated_at']

                if hisat2_step['progress_detail']:
                    try:
                        logger.info(f"📄 [ALIGNMENT-PROGRESS-API] Parsing progress_detail JSON for workbench {workbench_id}")
                        progress_data = json.loads(hisat2_step['progress_detail'])

                        # HISAT2 진행률 구조에서 정보 추출
                        completed = progress_data.get('summary', {}).get('completed_files', 0)
                        total = progress_data.get('summary', {}).get('total_files', 0)
                        progress_percent = progress_data.get('summary', {}).get('progress_percent', 0.0)

                        logger.info(f"📈 [ALIGNMENT-PROGRESS-API] Progress extracted: {completed}/{total} samples ({progress_percent:.1f}%)")

                        # 진행률에 따른 상태 업데이트
                        if total > 0 and completed == total:
                            status = 'completed'
                            logger.info(f"✅ [ALIGNMENT-PROGRESS-API] Alignment completed for workbench {workbench_id}")
                        elif completed > 0:
                            status = 'running'
                            logger.info(f"🔄 [ALIGNMENT-PROGRESS-API] Alignment running for workbench {workbench_id}")

                        # 프론트엔드 호환성을 위한 progress_data 구성
                        progress_data = {
                            'completed_files': completed,
                            'total_files': total,
                            'progress_percent': progress_percent,
                            'current_sample': progress_data.get('current_sample'),
                            'tool_name': hisat2_step['tool_name']
                        }

                        logger.info(f"📊 [ALIGNMENT-PROGRESS-API] Final progress_data prepared: {progress_data}")

                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"❌ [ALIGNMENT-PROGRESS-API] Failed to parse HISAT2 progress_detail for workbench {workbench_id}: {e}")

            logger.info(f"📊 [ALIGNMENT-PROGRESS-API] Final response for workbench {workbench_id}: Status({status}), Data({progress_data})")

            return jsonify({
                'workbench_id': workbench_id,
                'status': status,
                'progress_data': progress_data,
                'last_updated': last_updated
            }), 200

    except Exception as e:
        logger.error(f"Failed to get alignment progress for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@workbench_detail_alignment_bp.route('/<int:workbench_id>/alignment-results', methods=['GET'])
@require_auth
def get_alignment_results(workbench_id):
    """
    Alignment 결과 조회 API

    Response:
    {
        "workbench_id": 1,
        "samples": [
            {
                "sample_name": "DC1",
                "total_reads": 1000000,
                "mapped_reads": 950000,
                "unmapped_reads": 50000,
                "mapping_rate": 95.0,
                "multi_mapped_reads": 45000,
                "multi_mapping_rate": 4.5,
                "parsing_successful": true
            }
        ],
        "total_count": 1,
        "summary": {
            "total_reads": 1000000,
            "total_mapped_reads": 950000,
            "total_unmapped_reads": 50000,
            "average_mapping_rate": 95.0,
            "overall_mapping_rate": 95.0
        }
    }
    """
    logger.info(f"📊 [ALIGNMENT-RESULTS] Fetching alignment results for workbench {workbench_id}")

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        user_id = get_current_user_id()
        has_access, permission = check_workbench_access(workbench_id, user_id)

        if not has_access:
            logger.warning(f"⚠️ [ALIGNMENT-RESULTS] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Workbench not found or access denied'}), 404

        logger.info(f"✅ [ALIGNMENT-RESULTS] User {user_id} has {permission} access to workbench {workbench_id}")

        # Get alignment results from progress_detail
        with get_db_connection() as conn:
            # Alignment step의 progress_detail에서 results 조회
            alignment_step = conn.execute('''
                SELECT progress_detail, status, updated_at, tool_name
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'alignment'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if not alignment_step or not alignment_step['progress_detail']:
                logger.warning(f"No alignment results found for workbench {workbench_id}")
                return jsonify({
                    'workbench_id': workbench_id,
                    'samples': [],
                    'total_count': 0,
                    'summary': {
                        'total_reads': 0,
                        'total_mapped_reads': 0,
                        'total_unmapped_reads': 0,
                        'average_mapping_rate': 0.0,
                        'overall_mapping_rate': 0.0
                    }
                }), 200

            try:
                progress_data = json.loads(alignment_step['progress_detail'])
                results_data = progress_data.get('results', {})

                # 샘플별 결과 정리
                samples = []
                total_reads = 0
                total_mapped_reads = 0
                total_unmapped_reads = 0

                for sample_name, result in results_data.items():
                    logger.info(f"🔍 [ALIGNMENT-RESULTS] Processing sample: {sample_name}")
                    logger.info(f"📄 [ALIGNMENT-RESULTS] Raw result data: {result}")

                    if result.get('parsing_successful', False):
                        # 공통 데이터
                        sample_total_reads = result.get('total_reads', 0)

                        # Bowtie2 vs HISAT2 형식 구분
                        if 'aligned_reads' in result:
                            # Bowtie2/RSEM 형식
                            logger.info(f"📊 [ALIGNMENT-RESULTS] Detected Bowtie2/RSEM format for {sample_name}")
                            mapping_rate = result.get('alignment_rate', 0.0)
                            # 표시 지표 일관성: mapping_rate 기반으로 mapped/unmapped 계산
                            mapped_reads = int(round(sample_total_reads * (mapping_rate / 100.0))) if sample_total_reads > 0 else 0
                            unmapped_reads = max(0, sample_total_reads - mapped_reads)
                            # Bowtie2/RSEM은 multi-mapping 정보를 제공하지 않음
                            multi_mapped_reads = 0
                            multi_mapping_rate = 0.0
                        else:
                            # HISAT2 형식
                            logger.info(f"📊 [ALIGNMENT-RESULTS] Detected HISAT2 format for {sample_name}")
                            # 매핑율
                            mapping_rate = result.get('overall_alignment_rate', 0.0)
                            # 표시 지표 일관성: mapping_rate 기반으로 mapped/unmapped 계산
                            mapped_reads = int(round(sample_total_reads * (mapping_rate / 100.0))) if sample_total_reads > 0 else 0
                            unmapped_reads = max(0, sample_total_reads - mapped_reads)

                            # HISAT2의 multi-mapped는 보조 지표로 별도 유지
                            aligned_multiple = result.get('aligned_more_than_once', 0)
                            multi_mapped_reads = aligned_multiple
                            multi_mapping_rate = (aligned_multiple / sample_total_reads * 100) if sample_total_reads > 0 else 0.0

                        sample_result = {
                            'sample_name': sample_name,
                            'total_reads': sample_total_reads,
                            'mapped_reads': mapped_reads,
                            'unmapped_reads': unmapped_reads,
                            'mapping_rate': mapping_rate,
                            'multi_mapped_reads': multi_mapped_reads,
                            'multi_mapping_rate': multi_mapping_rate,
                            'parsing_successful': result.get('parsing_successful', False)
                        }

                        logger.info(f"📊 [ALIGNMENT-RESULTS] Converted sample result: {sample_result}")
                        samples.append(sample_result)

                        # 전체 통계 누적
                        total_reads += sample_result['total_reads']
                        total_mapped_reads += sample_result['mapped_reads']
                        total_unmapped_reads += sample_result['unmapped_reads']

                        logger.info(f"📈 [ALIGNMENT-RESULTS] Running totals: total={total_reads}, mapped={total_mapped_reads}, unmapped={total_unmapped_reads}")
                    else:
                        logger.warning(f"⚠️ [ALIGNMENT-RESULTS] Sample {sample_name} failed parsing, skipping")

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

                        logger.info(f"📋 [ALIGNMENT-RESULTS] Sample order from JSON: {sample_order}")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"⚠️ [ALIGNMENT-RESULTS] Failed to parse samples JSON: {e}")
                        sample_order = {}
                else:
                    logger.warning(f"⚠️ [ALIGNMENT-RESULTS] No samples JSON found for workbench {workbench_id}")
                    sample_order = {}

                # 샘플 순서에 따라 정렬
                def get_sample_order(sample):
                    sample_name = sample['sample_name']
                    return sample_order.get(sample_name, 999)  # DB에 없는 샘플은 맨 뒤로

                samples.sort(key=get_sample_order)
                logger.info(f"📊 [ALIGNMENT-RESULTS] Samples sorted by database order: {[s['sample_name'] for s in samples]}")

                # 평균 매핑율 계산
                average_mapping_rate = (total_mapped_reads / total_reads * 100) if total_reads > 0 else 0.0
                overall_mapping_rate = average_mapping_rate  # 동일한 값

                # 최종 결과 구성
                results = {
                    'workbench_id': workbench_id,
                    'samples': samples,
                    'total_count': len(samples),
                    'summary': {
                        'total_reads': total_reads,
                        'total_mapped_reads': total_mapped_reads,
                        'total_unmapped_reads': total_unmapped_reads,
                        'average_mapping_rate': round(average_mapping_rate, 2),
                        'overall_mapping_rate': round(overall_mapping_rate, 2)
                    }
                }

                logger.info(f"✅ [ALIGNMENT-RESULTS] Successfully prepared results for workbench {workbench_id}: {len(samples)} samples")

                return jsonify(results), 200

            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse alignment progress_detail for workbench {workbench_id}: {e}")
                return jsonify({'error': 'Failed to parse alignment results'}), 500

    except Exception as e:
        logger.error(f"Failed to get alignment results for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500
