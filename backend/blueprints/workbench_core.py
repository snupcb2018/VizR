"""
VizR Workbench Core Blueprint
워크벤치 핵심 CRUD 작업 (생성, 조회, 수정, 삭제, 검증, 구조 관리)
"""
from flask import Blueprint, request, jsonify, session, current_app
from datetime import datetime, timezone, timedelta
import logging
import os
import json
import shutil
import pandas as pd

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
workbench_core_bp = Blueprint('workbench_core', __name__, url_prefix='/api/workbenches')

# Import database stuff and config settings
from backend.utils.database import get_db_connection_simple as get_db_connection
from backend.utils.auth import require_auth, get_current_user_id
from config.backend_settings import BackendConfig as Config
from config.shared_config import SharedConfig

# Import utility functions
from backend.blueprints.workbench_utils import (
    get_workbench_name_by_id,
    get_workbench_schema
)
from backend.blueprints.workbench_share import check_workbench_access


def _get_latest_pipeline_steps(conn, workbench_id):
    pipeline_config = conn.execute('''
        SELECT pipeline_steps
        FROM vizr_pipeline_configurations
        WHERE workbench_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    ''', (workbench_id,)).fetchone()
    if not pipeline_config or not pipeline_config['pipeline_steps']:
        return []
    try:
        return json.loads(pipeline_config['pipeline_steps'])
    except (json.JSONDecodeError, TypeError):
        return []


def _extract_reference_set(pipeline_steps):
    for step in pipeline_steps:
        params = step.get('parameters', {}) or {}
        if params.get('reference_set'):
            return params['reference_set']
    return None


def _extract_count_tool(pipeline_steps):
    count_step = next((step for step in pipeline_steps if step.get('step') == 'count'), None)
    return count_step.get('tool') if count_step else None


def _derive_source_mode(pipeline_steps):
    if any(step.get('step') == 'count' and step.get('tool') == 'imported_counts' for step in pipeline_steps):
        return 'existing_workbench'
    if any(step.get('step') == 'count' and step.get('tool') == 'imported_matrix_files' for step in pipeline_steps):
        return 'matrix_files'
    return 'raw'


def _derive_has_tpm_matrix(pipeline_steps):
    for step in pipeline_steps:
        if step.get('step') != 'count':
            continue
        params = step.get('parameters', {}) or {}
        if step.get('tool') == 'imported_matrix_files':
            return bool(params.get('has_tpm_matrix'))
        if step.get('tool') == 'imported_counts':
            source_data = params.get('source_workbench_data', {}) or {}
            if 'has_tpm_matrix' in params:
                return bool(params.get('has_tpm_matrix'))
            if 'has_tpm_matrix' in source_data:
                return bool(source_data.get('has_tpm_matrix'))
            return True
    return True


def _derive_has_gsea_results(conn, workbench_row):
    owner = conn.execute('SELECT username FROM users WHERE id = ?', (workbench_row['user_id'],)).fetchone()
    if not owner or not owner['username']:
        return False

    deg_root = os.path.join(
        SharedConfig.VIZR_PATH,
        "users",
        owner['username'],
        "workbench",
        workbench_row['name'],
        "deg",
    )
    if not os.path.isdir(deg_root):
        return False

    for dirpath, _, filenames in os.walk(deg_root):
        path_with_sep = f"{dirpath}{os.sep}"
        if f"{os.sep}gsea{os.sep}" not in path_with_sep and not dirpath.endswith(f"{os.sep}gsea"):
            continue
        if 'summary.json' in filenames or 'result.json' in filenames or 'status.json' in filenames:
            return True
    return False


def _get_user_temp_file_path(temp_filename: str) -> str:
    username = session.get('username')
    if not username:
        raise ValueError('Authentication required')
    return os.path.join(SharedConfig.VIZR_PATH, "users", username, "tmp", temp_filename)


def _load_and_validate_matrix_file(file_path: str, label: str):
    try:
        df = pd.read_csv(file_path, sep='\t', dtype=str)
    except Exception as exc:
        raise ValueError(f"Failed to parse {label} file: {exc}") from exc

    if df.empty:
        raise ValueError(f"{label} file is empty")

    first_column = df.columns[0]
    if first_column not in ('gene_id', 'GeneID'):
        raise ValueError(f"{label} file must start with a gene_id or GeneID column")

    df = df.rename(columns={first_column: 'gene_id'})
    sample_columns = list(df.columns[1:])
    if not sample_columns:
        raise ValueError(f"{label} file must contain at least one sample column")
    if any(not str(col).strip() for col in sample_columns):
        raise ValueError(f"{label} file contains blank sample column names")
    if len(sample_columns) != len(set(sample_columns)):
        raise ValueError(f"{label} file contains duplicate sample column names")

    gene_ids = df['gene_id'].astype(str)
    if gene_ids.str.strip().eq('').any():
        raise ValueError(f"{label} file contains blank gene_id values")
    if gene_ids.duplicated().any():
        raise ValueError(f"{label} file contains duplicate gene_id values")

    return {
        'dataframe': df,
        'sample_columns': sample_columns,
        'gene_ids': gene_ids.tolist()
    }


@workbench_core_bp.route('/validate-matrix-files', methods=['POST'])
@require_auth
def validate_matrix_files():
    try:
        data = request.get_json() or {}
        counts_temp_file = (data.get('counts_temp_file') or '').strip()
        tpm_temp_file = (data.get('tpm_temp_file') or '').strip()

        errors = []
        warnings = []

        if not counts_temp_file:
            return jsonify({
                'valid': False,
                'errors': ['Counts matrix is required'],
                'warnings': [],
                'sample_columns': [],
                'sample_count': 0,
                'gene_count': 0,
                'has_tpm_matrix': False
            }), 200

        counts_path = _get_user_temp_file_path(counts_temp_file)
        if not os.path.exists(counts_path):
            errors.append('Counts matrix temp file was not found')
            return jsonify({
                'valid': False,
                'errors': errors,
                'warnings': warnings,
                'sample_columns': [],
                'sample_count': 0,
                'gene_count': 0,
                'has_tpm_matrix': False
            }), 200

        counts_info = _load_and_validate_matrix_file(counts_path, 'Counts matrix')

        has_tpm_matrix = False
        if tpm_temp_file:
            tpm_path = _get_user_temp_file_path(tpm_temp_file)
            if not os.path.exists(tpm_path):
                errors.append('TPM matrix temp file was not found')
            else:
                tpm_info = _load_and_validate_matrix_file(tpm_path, 'TPM matrix')
                has_tpm_matrix = True
                if set(tpm_info['sample_columns']) != set(counts_info['sample_columns']):
                    errors.append('Counts and TPM matrices must contain the same sample columns')
                if set(tpm_info['gene_ids']) != set(counts_info['gene_ids']):
                    errors.append('Counts and TPM matrices must contain the same gene_id set')
        else:
            warnings.append('TPM matrix not provided. TPM-based views will be disabled.')

        return jsonify({
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'sample_columns': counts_info['sample_columns'],
            'sample_count': len(counts_info['sample_columns']),
            'gene_count': len(counts_info['gene_ids']),
            'has_tpm_matrix': has_tpm_matrix
        })
    except Exception as e:
        logger.error(f"Matrix validation error: {e}")
        return jsonify({
            'valid': False,
            'errors': [str(e)],
            'warnings': [],
            'sample_columns': [],
            'sample_count': 0,
            'gene_count': 0,
            'has_tpm_matrix': False
        }), 200

@workbench_core_bp.route('/', methods=['GET'])
@require_auth
def get_workbench_list():
    """Get all workbenches for current user."""
    logger.info("🔍 [GET-WORKBENCH-LIST] Function started")
    try:
        user_id = get_current_user_id()
        logger.info(f"👤 [GET-WORKBENCH-LIST] User ID: {user_id}")

        with get_db_connection() as conn:
            logger.info("🔗 [GET-WORKBENCH-LIST] Database connection established")
            # VizR 워크벤치 조회 (파이프라인 상태 포함)
            logger.info("📋 [GET-WORKBENCH-LIST] Executing workbench query")
            workbenches = conn.execute('''
                SELECT vw.id, vw.name, vw.description, vw.species, vw.status, vw.user_id,
                       vw.created_at, vw.updated_at, vw.shared_users,
                       COUNT(DISTINCT vpc.id) as pipeline_configs_count,
                       COUNT(DISTINCT vps.id) as sample_groups_count,
                       -- 파이프라인 작업 상태 조회
                       CASE
                           WHEN pjs_running.workbench_id IS NOT NULL THEN 'running'
                           WHEN pjs_pending.workbench_id IS NOT NULL THEN 'pending'
                           WHEN pjs_completed.workbench_id IS NOT NULL THEN 'completed'
                           WHEN pjs_failed.workbench_id IS NOT NULL THEN 'failed'
                           ELSE vw.status
                       END as actual_status,
                       pjs_summary.total_steps,
                       pjs_summary.completed_steps,
                       pjs_summary.running_steps,
                       pjs_summary.failed_steps
                FROM vizr_workbench vw
                LEFT JOIN vizr_pipeline_configurations vpc ON vw.id = vpc.workbench_id
                LEFT JOIN vizr_pipeline_samples vps ON vw.id = vps.workbench_id
                
                -- 실행 중인 작업이 있는지 확인
                LEFT JOIN (
                    SELECT DISTINCT workbench_id 
                    FROM pipeline_job_steps 
                    WHERE status = 'running'
                ) pjs_running ON vw.id = pjs_running.workbench_id
                
                -- 대기 중인 작업이 있는지 확인
                LEFT JOIN (
                    SELECT DISTINCT workbench_id 
                    FROM pipeline_job_steps 
                    WHERE status = 'pending'
                ) pjs_pending ON vw.id = pjs_pending.workbench_id
                
                -- 완료된 작업만 있는지 확인 (실행중이나 대기중이 아니고 완료된 것이 있을 때)
                LEFT JOIN (
                    SELECT DISTINCT workbench_id 
                    FROM pipeline_job_steps 
                    WHERE workbench_id NOT IN (
                        SELECT DISTINCT workbench_id FROM pipeline_job_steps WHERE status IN ('running', 'pending', 'failed')
                    ) AND workbench_id IN (
                        SELECT DISTINCT workbench_id FROM pipeline_job_steps WHERE status = 'completed'
                    )
                ) pjs_completed ON vw.id = pjs_completed.workbench_id
                
                -- 실패한 작업이 있는지 확인
                LEFT JOIN (
                    SELECT DISTINCT workbench_id 
                    FROM pipeline_job_steps 
                    WHERE status = 'failed'
                ) pjs_failed ON vw.id = pjs_failed.workbench_id
                
                -- 작업 통계
                LEFT JOIN (
                    SELECT 
                        workbench_id,
                        COUNT(*) as total_steps,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_steps,
                        SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running_steps,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_steps
                    FROM pipeline_job_steps 
                    WHERE 1=1
                    GROUP BY workbench_id
                ) pjs_summary ON vw.id = pjs_summary.workbench_id
                
                WHERE vw.user_id = ? OR json_extract(vw.shared_users, '$') LIKE '%' || ? || '%'
                GROUP BY vw.id, pjs_running.workbench_id, pjs_pending.workbench_id,
                         pjs_completed.workbench_id, pjs_failed.workbench_id,
                         pjs_summary.total_steps, pjs_summary.completed_steps,
                         pjs_summary.running_steps, pjs_summary.failed_steps
                ORDER BY vw.created_at DESC
            ''', (user_id, user_id)).fetchall()

            logger.info(f"📊 [GET-WORKBENCH-LIST] Query executed successfully. Found {len(workbenches)} workbenches")

            # 워크벤치 데이터 가공
            workbench_list = []
            logger.info("🔧 [GET-WORKBENCH-LIST] Starting data processing")
            for i, wb in enumerate(workbenches):
                try:
                    workbench_id = wb['id']  # SQLite Row 객체에서 직접 접근
                    logger.info(f"   📋 [GET-WORKBENCH-LIST] Processing workbench {i+1}/{len(workbenches)}: ID={workbench_id}")
                    workbench_data = dict(wb)
                    # actual_status를 status로 사용
                    workbench_data['status'] = workbench_data['actual_status']
                    # 진행률 계산
                    total_steps = workbench_data.get('total_steps') if hasattr(workbench_data, 'get') else workbench_data['total_steps'] if 'total_steps' in workbench_data else None
                    if total_steps:
                        completed_steps = workbench_data.get('completed_steps') if hasattr(workbench_data, 'get') else workbench_data['completed_steps'] if 'completed_steps' in workbench_data else 0
                        workbench_data['progress_percentage'] = (
                            completed_steps / total_steps * 100
                        )
                    else:
                        workbench_data['progress_percentage'] = 0

                    # 권한 정보 추가
                    is_owner = workbench_data['user_id'] == user_id
                    workbench_data['is_owner'] = is_owner
                    workbench_data['permission'] = 'owner' if is_owner else 'shared'

                    # 공유 사용자 목록 파싱
                    shared_users_json = workbench_data.get('shared_users', '[]')
                    try:
                        workbench_data['shared_users'] = json.loads(shared_users_json) if shared_users_json else []
                    except json.JSONDecodeError:
                        workbench_data['shared_users'] = []

                    # 생성자 정보 추가
                    if not is_owner:
                        owner = conn.execute('SELECT username FROM users WHERE id = ?', (workbench_data['user_id'],)).fetchone()
                        workbench_data['created_by'] = owner['username'] if owner else 'Unknown'
                    else:
                        workbench_data['created_by'] = 'You'

                    workbench_list.append(workbench_data)
                    logger.info(f"   ✅ [GET-WORKBENCH-LIST] Successfully processed workbench ID={workbench_id}")
                except Exception as e:
                    logger.error(f"   ❌ [GET-WORKBENCH-LIST] Error processing workbench {i+1}: {e}")
                    logger.error(f"   📋 [GET-WORKBENCH-LIST] Workbench data: {dict(wb) if wb else 'None'}")
                    continue

            logger.info(f"🎉 [GET-WORKBENCH-LIST] Data processing completed. Returning {len(workbench_list)} workbenches")
            return jsonify({
                'workbenches': workbench_list
            })

    except Exception as e:
        logger.error(f"💥 [GET-WORKBENCH-LIST] CRITICAL ERROR: {e}")
        logger.error(f"💥 [GET-WORKBENCH-LIST] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"💥 [GET-WORKBENCH-LIST] Full traceback:")
        for i, line in enumerate(traceback.format_exc().split('\n'), 1):
            if line.strip():
                logger.error(f"   {i:3d} │ {line}")
        return jsonify({'error': 'Failed to fetch workbenches'}), 500

@workbench_core_bp.route('/', methods=['POST'])
@require_auth
def create_workbench():
    """Create a new workbench with complete configuration."""
    logger.info("🏗️ ═══════════════════════════════════════════════════════════════════════")
    logger.info("🏗️ 🚀 WORKBENCH CREATION - FUNCTION ENTRY 🚀")
    logger.info("🏗️ ═══════════════════════════════════════════════════════════════════════")
    logger.info("📥 Receiving workbench creation request...")
    logger.info("🔧 Initializing creation process...")
    
    try:
        data = request.get_json()
        user_id = get_current_user_id()
        data_input_method = data.get('dataInputMethod', 'local')

        if data_input_method == 'matrix_files':
            matrix_file_data = data.get('matrixFileData') or {}
            file_mappings = data.get('fileMappings') or {}
            samples = file_mappings.get('samples') or []
            counts_temp_file = (matrix_file_data.get('counts_temp_file') or '').strip()
            tpm_temp_file = (matrix_file_data.get('tpm_temp_file') or '').strip()
            has_tpm_matrix = bool(matrix_file_data.get('has_tpm_matrix'))

            if not counts_temp_file:
                return jsonify({'error': 'Counts matrix file is required for matrix-file workbenches'}), 400
            if not samples:
                return jsonify({'error': 'At least one mapped sample is required for matrix-file workbenches'}), 400

            counts_path = _get_user_temp_file_path(counts_temp_file)
            if not os.path.exists(counts_path):
                return jsonify({'error': 'Counts matrix temp file was not found'}), 400

            if has_tpm_matrix:
                if not tpm_temp_file:
                    return jsonify({'error': 'TPM matrix file metadata is missing'}), 400
                tpm_path = _get_user_temp_file_path(tpm_temp_file)
                if not os.path.exists(tpm_path):
                    return jsonify({'error': 'TPM matrix temp file was not found'}), 400

            invalid_samples = [
                sample for sample in samples
                if not str(sample.get('groupName', '')).strip()
                or not str(sample.get('sampleName', '')).strip()
                or not str(sample.get('sourceColumnName', '')).strip()
            ]
            if invalid_samples:
                return jsonify({'error': 'Each matrix-file sample must include group, sample, and source column information'}), 400

        workbench_name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        species = data.get('species', '').strip()
        
        # 📋 Raw request data JSON 출력 (초반)
        logger.info("🔍 [WORKBENCH-CREATE] Raw request data received:")
        try:
            data_json = json.dumps(data, indent=2, ensure_ascii=False)
            logger.info("─" * 80)
            for line_num, line in enumerate(data_json.split('\n'), 1):
                logger.info(f"{line_num:3d} │ {line}")
            logger.info("─" * 80)
        except Exception as e:
            logger.warning(f"⚠️ Failed to format JSON: {e}")
            logger.info(f"Raw data: {data}")
        
        # vizr_workbench 테이블에 데이터 삽입
        try:
            workbench_name = data.get('name', '')
            description = data.get('description', '')
            species = data.get('species', '')
            data_input_method = data.get('dataInputMethod', 'local')  # NCBI 데이터 소스 정보
            bioproject_id = data.get('bioprojectId', '') if data_input_method == 'ncbi' else ''

            logger.info(f"📝 Data to insert into vizr_workbench table:")
            logger.info(f"   workbench name: {workbench_name}")
            logger.info(f"   description: {description}")
            logger.info(f"   species: {species}")
            logger.info(f"   user_id: {user_id}")
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO vizr_workbench (name, description, species, user_id)
                    VALUES (?, ?, ?, ?)
                """, (workbench_name, description, species, user_id))
                
                workbench_id = cursor.lastrowid
                conn.commit()
                logger.info(f"✅ Successfully inserted data into vizr_workbench table: ID = {workbench_id}")
                        
        except Exception as e:
            logger.error(f"❌ Failed to insert into vizr_workbench table: {e}")
            return jsonify({'error': f'Failed to insert into vizr_workbench: {str(e)}'}), 500
        
        # vizr_pipeline_configurations 테이블에 파이프라인 설정 삽입
        logger.info(f"📦 [WORKBENCH-PIPELINE] Starting pipeline configuration insertion for workbench_id: {workbench_id}")
        try:
            pipeline_steps = data.get('pipelineSteps', [])
            if pipeline_steps:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO vizr_pipeline_configurations 
                        (workbench_id, pipeline_steps, created_at)
                        VALUES (?, ?, datetime('now'))
                    """, (workbench_id, json.dumps(pipeline_steps)))
                    conn.commit()
                    logger.info(f"✅ Successfully inserted data into vizr_pipeline_configurations table: workbench_id = {workbench_id}")
            else:
                logger.warning("⚠️ pipelineSteps is empty, skipping insert into vizr_pipeline_configurations")
                        
        except Exception as e:
            logger.error(f"❌ Failed to insert into vizr_pipeline_configurations table: {e}")
            return jsonify({'error': f'Failed to insert into vizr_pipeline_configurations: {str(e)}'}), 500

        # vizr_pipeline_samples 테이블에 샘플 정보 삽입
        try:
            file_mappings = data.get('fileMappings', {})
            
            if file_mappings:
                layout = file_mappings.get('layout', 'pe')  # fileMappings 내부의 layout
                samples = file_mappings.get('samples', [])  # fileMappings 내부의 samples 배열
                
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    
                    # layout과 samples를 분리해서 저장 (스키마에 맞게)
                    cursor.execute("""
                        INSERT INTO vizr_pipeline_samples 
                        (workbench_id, layout, samples, created_at)
                        VALUES (?, ?, ?, datetime('now'))
                    """, (workbench_id, layout, json.dumps(samples)))
                    
                    conn.commit()
                    logger.info(f"✅ Successfully inserted data into vizr_pipeline_samples table: {len(samples)} samples, layout = {layout}, workbench_id = {workbench_id}")
            else:
                logger.warning("⚠️ fileMappings is empty, skipping insert into vizr_pipeline_samples")
                        
            # 워크벤치 디렉토리 구조 얻기
            workbench_structure = get_workbench_schema(workbench_name, user_id)
            
            # 실제 디렉토리 생성
            try:
                logger.info(f"📁 Creating workbench directory structure...")
                
                # 기본 디렉토리들 생성
                os.makedirs(workbench_structure["base"], exist_ok=True)
                os.makedirs(workbench_structure["deg"], exist_ok=True)
                os.makedirs(workbench_structure["log"], exist_ok=True)
                os.makedirs(workbench_structure["report"], exist_ok=True)
                os.makedirs(workbench_structure["visual"], exist_ok=True)
                os.makedirs(workbench_structure["ref"], exist_ok=True)
                
                # quanti 하위 디렉토리들 생성
                os.makedirs(workbench_structure["quanti"]["base"], exist_ok=True)
                os.makedirs(workbench_structure["quanti"]["alignment"], exist_ok=True)
                os.makedirs(workbench_structure["quanti"]["counts"], exist_ok=True)
                os.makedirs(workbench_structure["quanti"]["clean"], exist_ok=True)
                os.makedirs(workbench_structure["quanti"]["qc"], exist_ok=True)
                os.makedirs(workbench_structure["quanti"]["raw"], exist_ok=True)
                os.makedirs(workbench_structure["quanti"]["samples"], exist_ok=True)
                
                logger.info(f"✅ Successfully created workbench directory structure at: {workbench_structure['base']}")
                
            except Exception as e:
                logger.error(f"❌ Failed to create workbench directory structure: {e}")
                # 디렉토리 생성 실패해도 워크벤치 생성은 계속 진행 (나중에 생성 가능)

            return jsonify({
                'message': 'Workbench created successfully',
                'workbench_id': workbench_id
            }), 201

        
        except Exception as e:
            logger.error(f"❌ Failed to insert into vizr_pipeline_samples table: {e}")
            return jsonify({'error': f'Failed to insert into vizr_pipeline_samples: {str(e)}'}), 500

    except Exception as e:
        logger.error(f"Workbench creation error: {e}")
        return jsonify({'error': 'Failed to create workbench'}), 500


@workbench_core_bp.route('/import-sources', methods=['GET'])
@require_auth
def get_import_workbench_sources():
    """List completed workbenches that can provide imported count matrices."""
    try:
        user_id = get_current_user_id()
        species_filter = request.args.get('species', '').strip()

        with get_db_connection() as conn:
            workbenches = conn.execute('''
                SELECT w.id, w.name, w.species, w.user_id, w.status, w.created_at, w.updated_at, u.username
                FROM vizr_workbench w
                JOIN users u ON w.user_id = u.id
                WHERE w.status = 'completed'
                  AND (w.user_id = ? OR json_extract(w.shared_users, '$') LIKE '%' || ? || '%')
                ORDER BY w.updated_at DESC, w.created_at DESC
            ''', (user_id, user_id)).fetchall()

            candidate_logs = [
                {
                    'workbench_id': workbench['id'],
                    'workbench_name': workbench['name'],
                    'species': workbench['species'],
                    'status': workbench['status'],
                    'owner_user_id': workbench['user_id'],
                    'owner_username': workbench['username'],
                    'updated_at': workbench['updated_at'],
                }
                for workbench in workbenches
            ]
            logger.info(
                "[IMPORT-SOURCES] request user_id=%s species_filter=%s candidate_count=%s candidates=%s",
                user_id,
                species_filter or 'all',
                len(workbenches),
                json.dumps(candidate_logs, ensure_ascii=False),
            )

            sources = []
            excluded_sources = []
            for workbench in workbenches:
                exclusion = {
                    'workbench_id': workbench['id'],
                    'workbench_name': workbench['name'],
                    'species': workbench['species'],
                    'reason': None,
                }

                if species_filter and workbench['species'] != species_filter:
                    exclusion.update({
                        'reason': 'species_mismatch',
                        'expected_species': species_filter,
                        'actual_species': workbench['species'],
                    })
                    excluded_sources.append(exclusion)
                    continue

                pipeline_steps = _get_latest_pipeline_steps(conn, workbench['id'])
                if not pipeline_steps:
                    exclusion['reason'] = 'missing_pipeline_steps'
                    excluded_sources.append(exclusion)
                    continue

                count_tool = _extract_count_tool(pipeline_steps)
                if not count_tool:
                    exclusion['reason'] = 'missing_count_tool'
                    excluded_sources.append(exclusion)
                    continue

                if count_tool == 'imported_counts':
                    exclusion.update({
                        'reason': 'imported_counts_source_excluded',
                        'count_tool': count_tool,
                    })
                    excluded_sources.append(exclusion)
                    continue

                workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
                counts_matrix = os.path.join(workbench_schema['quanti']['counts'], 'genes.counts.matrix')
                if not os.path.exists(counts_matrix):
                    exclusion.update({
                        'reason': 'missing_counts_matrix',
                        'count_tool': count_tool,
                        'counts_matrix': counts_matrix,
                    })
                    excluded_sources.append(exclusion)
                    continue

                samples_row = conn.execute('''
                    SELECT samples
                    FROM vizr_pipeline_samples
                    WHERE workbench_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', (workbench['id'],)).fetchone()
                if not samples_row or not samples_row['samples']:
                    exclusion.update({
                        'reason': 'missing_pipeline_samples',
                        'count_tool': count_tool,
                        'counts_matrix': counts_matrix,
                    })
                    excluded_sources.append(exclusion)
                    continue

                try:
                    samples = json.loads(samples_row['samples'])
                except (json.JSONDecodeError, TypeError) as parse_error:
                    exclusion.update({
                        'reason': 'invalid_pipeline_samples_json',
                        'count_tool': count_tool,
                        'error': str(parse_error),
                    })
                    excluded_sources.append(exclusion)
                    continue

                sources.append({
                    'workbench_id': workbench['id'],
                    'workbench_name': workbench['name'],
                    'species': workbench['species'],
                    'count_tool': count_tool,
                    'has_tpm_matrix': _derive_has_tpm_matrix(pipeline_steps),
                    'reference_set': _extract_reference_set(pipeline_steps),
                    'samples': [
                        {
                            'sample_name': sample.get('sampleName', ''),
                            'group_name': sample.get('groupName', '')
                        }
                        for sample in samples
                    ]
                })

            included_logs = [
                {
                    'workbench_id': source['workbench_id'],
                    'workbench_name': source['workbench_name'],
                    'species': source['species'],
                    'count_tool': source['count_tool'],
                    'reference_set': source['reference_set'],
                    'has_tpm_matrix': source['has_tpm_matrix'],
                    'sample_count': len(source['samples']),
                }
                for source in sources
            ]
            logger.info(
                "[IMPORT-SOURCES] response included_count=%s included=%s excluded_count=%s excluded=%s",
                len(sources),
                json.dumps(included_logs, ensure_ascii=False),
                len(excluded_sources),
                json.dumps(excluded_sources, ensure_ascii=False),
            )

        return jsonify({'sources': sources})
    except Exception as e:
        logger.error(f"Failed to fetch import workbench sources: {e}")
        return jsonify({'error': 'Failed to fetch import workbench sources'}), 500

@workbench_core_bp.route('/<int:workbench_id>', methods=['GET'])
@require_auth
def get_workbench(workbench_id):
    """Get workbench details."""
    try:
        user_id = get_current_user_id()
        logger.info(f"🔍 [GET-WORKBENCH] Function started - Workbench ID: {workbench_id}, User ID: {user_id}")

        with get_db_connection() as conn:
            logger.info(f"🔗 [GET-WORKBENCH] Database connection established")

            # Get workbench with creator info (allow owner or shared users)
            logger.info(f"📋 [GET-WORKBENCH] Executing query with params: workbench_id={workbench_id}, user_id={user_id}")
            workbench = conn.execute('''
                SELECT w.*, u.username as created_by_username, u.full_name as created_by_name
                FROM vizr_workbench w
                LEFT JOIN users u ON w.user_id = u.id
                WHERE w.id = ? AND (w.user_id = ? OR json_extract(w.shared_users, '$') LIKE '%' || ? || '%')
            ''', (workbench_id, user_id, user_id)).fetchone()

            if not workbench:
                logger.warning(f"⚠️ [GET-WORKBENCH] Workbench {workbench_id} not found or access denied for user {user_id}")
                logger.warning(f"   - Checking if workbench exists at all...")
                check_exists = conn.execute('SELECT id, user_id, shared_users FROM vizr_workbench WHERE id = ?', (workbench_id,)).fetchone()
                if check_exists:
                    logger.warning(f"   - Workbench {workbench_id} EXISTS but user {user_id} has no access")
                    logger.warning(f"   - Owner: {check_exists['user_id']}, Shared users: {check_exists['shared_users']}")
                else:
                    logger.warning(f"   - Workbench {workbench_id} does NOT exist in database")
                return jsonify({'error': 'Workbench not found'}), 404

            logger.info(f"✅ [GET-WORKBENCH] Workbench found successfully")

            # Add permission info
            workbench_dict = dict(workbench)
            is_owner = workbench_dict['user_id'] == user_id
            workbench_dict['is_owner'] = is_owner
            workbench_dict['permission'] = 'owner' if is_owner else 'shared'

            # Parse shared_users
            shared_users_json = workbench_dict.get('shared_users', '[]')
            try:
                workbench_dict['shared_users'] = json.loads(shared_users_json) if shared_users_json else []
            except json.JSONDecodeError:
                workbench_dict['shared_users'] = []

            logger.info(f"✅ [GET-WORKBENCH] Workbench {workbench_id} accessed by user {user_id} (permission: {workbench_dict['permission']})")

            # Get pipeline configuration
            pipeline_config = conn.execute('''
                SELECT * FROM vizr_pipeline_configurations 
                WHERE workbench_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            # Get samples (fixed ORDER BY clause)
            samples = conn.execute('''
                SELECT id, workbench_id, layout, samples, created_at 
                FROM vizr_pipeline_samples 
                WHERE workbench_id = ?
                ORDER BY created_at DESC
            ''', (workbench_id,)).fetchall()
            
        # Parse sample_file_mappings from JSON data and get layout
        sample_file_mappings = []
        samples_list = []  # 파싱된 샘플 목록
        layout = None

        # DEBUG: samples 데이터 확인
        logger.debug(f"[WORKBENCH-GET] Checking samples for workbench {workbench_id}:")
        logger.debug(f"   - Number of sample records: {len(samples) if samples else 0}")

        if samples:
            for i, sample_record in enumerate(samples):
                logger.debug(f"   - Sample record {i}: keys = {list(sample_record.keys()) if sample_record else 'None'}")
                # SQLite Row 객체는 get() 메서드가 없으므로 직접 접근
                record_layout = sample_record['layout'] if sample_record and 'layout' in sample_record.keys() else 'NOT FOUND'
                logger.debug(f"   - Sample record {i} layout: {record_layout}")
                try:
                    # Parse the JSON samples data
                    samples_json = json.loads(sample_record['samples'])
                    logger.info(f"[WORKBENCH-GET] Parsed samples_json type: {type(samples_json)}, length: {len(samples_json) if isinstance(samples_json, list) else 'N/A'}")
                    if isinstance(samples_json, list) and len(samples_json) > 0:
                        logger.info(f"[WORKBENCH-GET] First sample structure: {samples_json[0]}")
                        sample_file_mappings.extend(samples_json)
                        # 샘플 목록도 추출 (파일 매핑과 별개로)
                        for sample_data in samples_json:
                            if sample_data not in samples_list:
                                samples_list.append(sample_data)
                    # Get layout from the first sample record
                    if layout is None and 'layout' in sample_record.keys():
                        layout = sample_record['layout']
                        logger.debug(f"   ✅ Layout found: {layout}")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse samples JSON for workbench {workbench_id}: {e}")
        else:
            logger.debug(f"   ⚠️ No samples found for workbench {workbench_id}")

        # Calculate actual file count based on layout
        # PE (Paired-End): Each sample has file1 and file2
        # SE (Single-End): Each sample has only file1
        raw_files_count = 0
        for sample_data in sample_file_mappings:
            if sample_data.get('file1'):
                raw_files_count += 1
            if sample_data.get('file2'):
                raw_files_count += 1

        # Prepare enhanced workbench data (use workbench_dict that already has permission info)
        workbench_data = workbench_dict
        workbench_data['created_by'] = workbench_dict.get('created_by_name') or workbench_dict.get('created_by_username') or 'Unknown'
        workbench_data['samples_count'] = len(sample_file_mappings)
        workbench_data['raw_files_count'] = raw_files_count  # 실제 파일 개수 (PE이면 샘플*2, SE이면 샘플*1)
        workbench_data['layout'] = layout  # Add layout to workbench data

        # 🔍 DEBUG: Layout 정보 확인 로그
        logger.info(f"📊 [WORKBENCH-GET] Layout information for workbench {workbench_id}:")
        logger.info(f"   - Layout from DB: {layout}")
        logger.info(f"   - Layout in workbench_data: {workbench_data.get('layout')}")
        logger.info(f"   - Sample count: {len(samples_list)}")
        logger.info(f"   - File mappings count: {len(sample_file_mappings)}")
        
        # Parse pipeline steps from JSON if available
        pipeline_steps = []
        if pipeline_config and pipeline_config['pipeline_steps']:
            try:
                pipeline_steps = json.loads(pipeline_config['pipeline_steps'])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse pipeline steps JSON for workbench {workbench_id}: {e}")
        source_mode = _derive_source_mode(pipeline_steps)
        has_tpm_matrix = _derive_has_tpm_matrix(pipeline_steps)
        has_gsea_results = _derive_has_gsea_results(conn, workbench_dict)
        workbench_data['source_mode'] = source_mode
        workbench_data['has_tpm_matrix'] = has_tpm_matrix
        workbench_data['has_gsea_results'] = has_gsea_results
        count_step = next((step for step in pipeline_steps if step.get('step') == 'count'), None)
        locked_steps = [
            {
                'step': step.get('step'),
                'tool': step.get('tool'),
                'disabled': bool((step.get('parameters') or {}).get('disabled')),
                'locked_reason': (step.get('parameters') or {}).get('locked_reason'),
            }
            for step in pipeline_steps
            if bool((step.get('parameters') or {}).get('disabled')) or (step.get('parameters') or {}).get('locked_reason')
        ]
        logger.info(f"[WORKBENCH-GET] Source context for workbench {workbench_id}:")
        logger.info(f"   - source_mode: {source_mode}")
        logger.info(f"   - has_tpm_matrix: {has_tpm_matrix}")
        logger.info(f"   - has_gsea_results: {has_gsea_results}")
        logger.info(f"   - pipeline_steps count: {len(pipeline_steps)}")
        logger.info(f"   - count step tool: {count_step.get('tool') if count_step else None}")
        logger.info(f"   - count step description: {count_step.get('description') if count_step else None}")
        logger.info(f"   - locked steps: {locked_steps}")
        
        # Check for currently running job and get pipeline status
        current_job_id = None
        pipeline_status = None
        with get_db_connection() as conn:
            running_job = conn.execute('''
                SELECT job_id, status, COUNT(*) as step_count
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND status IN ('running', 'pending')
                GROUP BY job_id, status
                ORDER BY MAX(created_at) DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if running_job:
                current_job_id = running_job['job_id']
                logger.info(f"🔍 Found running job for workbench {workbench_id}: {current_job_id}")

            # Get pipeline status from pipeline_job_steps
            pipeline_status_data = conn.execute('''
                SELECT
                    COUNT(*) as total_steps,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_steps,
                    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running_steps,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_steps,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_steps,
                    MIN(created_at) as started_at,
                    MAX(updated_at) as updated_at,
                    MAX(CASE WHEN status = 'running' THEN step_name ELSE NULL END) as current_step
                FROM pipeline_job_steps
                WHERE workbench_id = ?
            ''', (workbench_id,)).fetchone()

            # Get list of executed step names from pipeline_job_steps
            executed_steps_rows = conn.execute('''
                SELECT DISTINCT step_name
                FROM pipeline_job_steps
                WHERE workbench_id = ?
            ''', (workbench_id,)).fetchall()

            executed_step_names = [row['step_name'] for row in executed_steps_rows]

            # Log raw pipeline_status_data
            logger.info(f"📊 [WORKBENCH-GET] Raw pipeline_status_data for workbench {workbench_id}:")
            logger.info(f"   - total_steps: {pipeline_status_data['total_steps'] if pipeline_status_data else 0}")
            logger.info(f"   - completed_steps: {pipeline_status_data['completed_steps'] if pipeline_status_data else 0}")
            logger.info(f"   - running_steps: {pipeline_status_data['running_steps'] if pipeline_status_data else 0}")
            logger.info(f"   - failed_steps: {pipeline_status_data['failed_steps'] if pipeline_status_data else 0}")
            logger.info(f"   - pending_steps: {pipeline_status_data['pending_steps'] if pipeline_status_data else 0}")
            logger.info(f"   - workbench DB status: {workbench_dict['status']}")
            logger.info(f"   - executed_step_names: {executed_step_names}")

            # Determine overall pipeline status
            if pipeline_status_data and pipeline_status_data['total_steps'] > 0:
                if pipeline_status_data['running_steps'] > 0:
                    status = 'running'
                elif pipeline_status_data['pending_steps'] > 0:
                    status = 'pending'
                elif pipeline_status_data['failed_steps'] > 0:
                    status = 'failed'
                elif pipeline_status_data['completed_steps'] == pipeline_status_data['total_steps']:
                    status = 'completed'
                else:
                    # Use workbench status from DB if no clear pipeline status
                    status = workbench_dict['status']

                # Calculate progress percentage
                progress_percentage = 0
                if pipeline_status_data['total_steps'] > 0:
                    progress_percentage = (pipeline_status_data['completed_steps'] / pipeline_status_data['total_steps']) * 100

                pipeline_status = {
                    'status': status,
                    'total_steps': pipeline_status_data['total_steps'],
                    'completed_steps': pipeline_status_data['completed_steps'],
                    'running_steps': pipeline_status_data['running_steps'],
                    'failed_steps': pipeline_status_data['failed_steps'],
                    'pending_steps': pipeline_status_data['pending_steps'],
                    'current_step': pipeline_status_data['current_step'],
                    'started_at': pipeline_status_data['started_at'],
                    'updated_at': pipeline_status_data['updated_at'],
                    'progress_percentage': progress_percentage
                }
                logger.info(f"📊 [WORKBENCH-GET] Final pipeline_status determined:")
                logger.info(f"   - status: {status}")
                logger.info(f"   - total_steps: {pipeline_status_data['total_steps']}")
                logger.info(f"   - completed_steps: {pipeline_status_data['completed_steps']}")
                logger.info(f"   - progress_percentage: {progress_percentage:.1f}%")
                logger.info(f"   - current_step: {pipeline_status_data['current_step']}")
            else:
                # No pipeline steps found, use workbench status
                logger.info(f"📊 [WORKBENCH-GET] No pipeline steps found for workbench {workbench_id}, using workbench status: {workbench_dict['status']}")
                pipeline_status = None

        # Prepare pipeline_config with data_layout
        pipeline_config_dict = dict(pipeline_config) if pipeline_config else {}
        pipeline_config_dict['data_layout'] = layout  # layout 추가
        pipeline_config_dict['source_mode'] = source_mode
        pipeline_config_dict['has_tpm_matrix'] = has_tpm_matrix
        pipeline_config_dict['has_gsea_results'] = has_gsea_results

        logger.info(f"📤 [WORKBENCH-GET] Sending response:")
        logger.info(f"   - samples_list count: {len(samples_list)}")
        logger.info(f"   - sample_file_mappings count: {len(sample_file_mappings)}")
        logger.info(f"   - pipeline_config data_layout: {pipeline_config_dict.get('data_layout')}")
        logger.info(f"   - pipeline_status: {pipeline_status['status'] if pipeline_status else None}")
        logger.info(f"   - response workbench.source_mode: {workbench_data.get('source_mode')}")
        logger.info(f"   - response workbench.has_tpm_matrix: {workbench_data.get('has_tpm_matrix')}")
        logger.info(f"   - response workbench.has_gsea_results: {workbench_data.get('has_gsea_results')}")

        return jsonify({
            'workbench': workbench_data,
            'pipeline_config': pipeline_config_dict,
            'pipeline_steps': pipeline_steps,
            'samples': samples_list,  # 파싱된 샘플 목록 사용
            'sample_file_mappings': sample_file_mappings,
            'current_job_id': current_job_id,  # 실행 중인 job ID 추가
            'pipeline_status': pipeline_status,  # 파이프라인 상태 추가
            'executed_step_names': executed_step_names  # 실제 실행된 단계 이름 목록
        })

    except Exception as e:
        logger.error(f"Workbench fetch error: {e}")
        return jsonify({'error': 'Failed to fetch workbench'}), 500
    

@workbench_core_bp.route('/<int:workbench_id>', methods=['DELETE'])
@require_auth
def delete_workbench(workbench_id):
    """Delete a workbench and all associated data."""
    import os
    import shutil
    import tempfile
    
    logger.info(f"🗑️ DELETE WORKBENCH REQUEST - ID: {workbench_id}")
    
    try:
        # Get request data for delete options
        data = request.get_json() or {}
        delete_raw_data = data.get('delete_raw_data', False)  # 기본값은 raw data 보존
        logger.info(f"📋 Delete options - raw_data: {delete_raw_data}")

        user_id = get_current_user_id()
        logger.info(f"👤 User ID: {user_id}")
        
        with get_db_connection() as conn:
            # Check if workbench exists and belongs to user (only owner can delete)
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ? AND user_id = ?
            ''', (workbench_id, user_id)).fetchone()

            if not workbench:
                logger.warning(f"⚠️ [DELETE-WORKBENCH] Workbench {workbench_id} not found or user {user_id} is not the owner")
                return jsonify({'error': 'Workbench not found or only the owner can delete'}), 404
        
        workbench_name = workbench['name']
        
        # Check if there are any running pipeline jobs
        try:
            from backend.pipeline.job_manager import PipelineJobManager
            JOB_MANAGEMENT_AVAILABLE = True
        except ImportError:
            JOB_MANAGEMENT_AVAILABLE = False
            
        if JOB_MANAGEMENT_AVAILABLE:
            logger.info(f"🔍 Checking job status for workbench {workbench_id}")
            
            # Get total row count for this workbench
            total_rows = conn.execute('''
                SELECT COUNT(*) as count FROM pipeline_job_steps 
                WHERE workbench_id = ?
            ''', (workbench_id,)).fetchone()['count']
            
            # Get pending row count for this workbench  
            pending_rows = conn.execute('''
                SELECT COUNT(*) as count FROM pipeline_job_steps 
                WHERE workbench_id = ? AND status = 'pending'
            ''', (workbench_id,)).fetchone()['count']
            
            logger.info(f"📊 Job status - Total rows: {total_rows}, Pending rows: {pending_rows}")
            
            # If total rows == pending rows, it means no execution has started yet
            if total_rows > 0 and total_rows == pending_rows:
                logger.info(f"🟡 All jobs are pending (not started) - safe to delete")
            elif total_rows > 0 and pending_rows < total_rows:
                # Some jobs have started execution - check for running jobs only
                running_jobs = conn.execute('''
                    SELECT DISTINCT job_id FROM pipeline_job_steps 
                    WHERE workbench_id = ? AND status = 'running'
                ''', (workbench_id,)).fetchall()
                
                if running_jobs:
                    logger.warning(f"❌ Cannot delete workbench {workbench_id} - has running jobs: {[job['job_id'] for job in running_jobs]}")
                    conn.close()
                    return jsonify({
                        'error': 'Cannot delete workbench with running pipeline jobs',
                        'running_jobs': [job['job_id'] for job in running_jobs]
                    }), 400
                else:
                    # No running jobs - all must be completed/failed/cancelled
                    logger.info(f"✅ Jobs are completed/failed/cancelled - safe to delete")
            else:
                logger.info(f"✅ No jobs found - proceeding with deletion")

        # Delete associated files from filesystem
        logger.info(f"🗂️ Starting filesystem cleanup for workbench ID {workbench_id}")

        # Get workbench info (name and user_id)
        workbench_info = conn.execute(
            'SELECT name, user_id FROM vizr_workbench WHERE id = ?',
            (workbench_id,)
        ).fetchone()

        if not workbench_info:
            logger.error(f"❌ Failed to get workbench info for ID {workbench_id}")
            workbench_name_fs = None
        else:
            workbench_name_from_db = workbench_info['name']
            workbench_user_id = workbench_info['user_id']
            # Make filesystem-safe
            workbench_name_fs = workbench_name_from_db.replace(' ', '_').replace('/', '_').replace('\\', '_')
            logger.info(f"   Workbench: '{workbench_name_fs}', User ID: {workbench_user_id}")

        # Construct user-specific workbench directory path using get_workbench_schema
        if workbench_name_fs:
            # Use get_workbench_schema to get the correct user-specific path
            workbench_structure = get_workbench_schema(workbench_name_from_db, workbench_user_id)
            workbench_dir = workbench_structure["base"]
            logger.info(f"   Target directory: {workbench_dir}")

            # Check if directory exists before proceeding
            if os.path.exists(workbench_dir):
                logger.info(f"   Directory exists, proceeding with deletion")
                
                try:
                    if delete_raw_data:
                        # 모든 파일 삭제
                        logger.info(f"🔥 Complete deletion mode - removing entire directory")
                        shutil.rmtree(workbench_dir)
                        logger.info(f"✅ Successfully deleted workbench directory: {workbench_dir}")

                    else:
                        # Raw data는 보존하고 나머지만 삭제
                        logger.info(f"🔄 Partial deletion mode - preserving raw data")

                        quanti_raw_dir = os.path.join(workbench_dir, 'quanti', 'raw')

                        # raw 폴더가 있으면 나머지만 삭제
                        if os.path.exists(quanti_raw_dir):
                            # 워크벤치 디렉토리 내의 모든 항목 순회
                            for item in os.listdir(workbench_dir):
                                item_path = os.path.join(workbench_dir, item)

                                # quanti 폴더는 별도 처리
                                if item == 'quanti':
                                    # quanti 내의 raw가 아닌 다른 폴더/파일만 삭제
                                    quanti_dir = item_path
                                    for quanti_item in os.listdir(quanti_dir):
                                        if quanti_item != 'raw':
                                            quanti_item_path = os.path.join(quanti_dir, quanti_item)
                                            if os.path.isdir(quanti_item_path):
                                                shutil.rmtree(quanti_item_path)
                                            else:
                                                os.remove(quanti_item_path)
                                else:
                                    # quanti가 아닌 다른 폴더/파일은 모두 삭제
                                    if os.path.isdir(item_path):
                                        shutil.rmtree(item_path)
                                    else:
                                        os.remove(item_path)

                            raw_file_count = len(os.listdir(quanti_raw_dir))
                            logger.info(f"   Preserved raw data ({raw_file_count} files)")
                        else:
                            # raw 폴더가 없으면 전체 삭제
                            shutil.rmtree(workbench_dir)
                            logger.info(f"   No raw data found, deleted entire directory")

                        logger.info(f"✅ Partial deletion completed for: {workbench_dir}")
                        
                except Exception as e:
                    logger.error(f"❌ Filesystem deletion failed: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            else:
                logger.warning(f"⚠️ Workbench directory does not exist: {workbench_dir}")
        else:
            logger.warning(f"⚠️ Could not determine workbench information for ID {workbench_id}")
        
        # Delete from database (CASCADE will handle related records)
        logger.info(f"🗄️ Starting database cleanup for workbench ID {workbench_id}")
        logger.info(f"📊 Delete mode: {'COMPLETE' if delete_raw_data else 'PARTIAL'} (delete_raw_data={delete_raw_data})")
        
        try:
            if delete_raw_data:
                # 모든 데이터 삭제 (CASCADE로 raw_data_files 포함 모든 연관 테이블 삭제)
                logger.info(f"🔥 COMPLETE DB DELETION: Removing workbench record and all CASCADE data")
                result = conn.execute('DELETE FROM vizr_workbench WHERE id = ?', (workbench_id,))
                rows_affected = result.rowcount
                logger.info(f"✅ Deleted {rows_affected} workbench record(s) (ID: {workbench_id})")
                logger.info(f"ℹ️ CASCADE deletion will automatically remove all related records")
                logger.info(f"✅ Complete database deletion: {workbench_name} (ID: {workbench_id})")
            else:
                # 부분 삭제: 파일 시스템에서는 raw data만 보존, DB에서는 모든 데이터 삭제 (CASCADE)
                # 워크벤치 레코드도 완전 삭제하여 재사용하지 않음
                logger.info(f"🔄 PARTIAL DB DELETION: Removing workbench record and all CASCADE data (filesystem raw data preserved)")
                result = conn.execute('DELETE FROM vizr_workbench WHERE id = ?', (workbench_id,))
                rows_affected = result.rowcount
                logger.info(f"✅ Deleted {rows_affected} workbench record(s) (ID: {workbench_id})")
                logger.info(f"ℹ️ CASCADE deletion will automatically remove all related records")
                logger.info(f"✅ Partial database deletion completed: {workbench_name} (ID: {workbench_id})")
            
            # Commit the transaction
            logger.info(f"💾 Committing database transaction")
            conn.commit()
            logger.info(f"✅ Database transaction committed successfully")
            
        except Exception as e:
            logger.error(f"❌ DATABASE DELETION FAILED for workbench ID {workbench_id}: {str(e)}")
            logger.error(f"❌ Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            conn.rollback()
            logger.info(f"🔄 Database transaction rolled back")
            raise
        finally:
            conn.close()
            logger.info(f"🔌 Database connection closed")
        
        logger.info(f"🎉 WORKBENCH DELETION COMPLETED - User: {user_id}, Mode: {'COMPLETE' if delete_raw_data else 'PARTIAL'}, WorkbenchID: {workbench_id}")
        
        if delete_raw_data:
            return jsonify({
                'message': f'워크벤치 "{workbench_name}"가 모든 데이터와 함께 완전히 삭제되었습니다.',
                'workbench_id': workbench_id,
                'deleted_completely': True
            })
        else:
            return jsonify({
                'message': f'워크벤치 "{workbench_name}"가 삭제되었습니다. 원본 Raw Data 파일만 서버에 보존되었습니다.',
                'workbench_id': workbench_id,
                'deleted_completely': True,  # 워크벤치는 완전히 삭제됨
                'raw_data_preserved': True   # 파일만 보존
            })
        
    except Exception as e:
        logger.error(f"Workbench deletion error: {e}")
        return jsonify({'error': 'Failed to delete workbench'}), 500

# Workbench validation endpoints
@workbench_core_bp.route('/validate-name', methods=['POST'])
@require_auth
def validate_workbench_name():
    """Check if workbench name is available."""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'available': True, 'message': ''})

        user_id = get_current_user_id()

        with get_db_connection() as conn:
            existing = conn.execute('''
                SELECT id FROM vizr_workbench 
                WHERE user_id = ? AND name = ?
            ''', (user_id, name)).fetchone()
        
        if existing:
            return jsonify({
                'available': False,
                'message': 'A workbench with this name already exists'
            })
        else:
            return jsonify({
                'available': True,
                'message': 'Name is available'
            })
            
    except Exception as e:
        logger.error(f"Name validation error: {e}")
        return jsonify({'available': False, 'message': 'Validation failed'}), 500

# Workbench Structure Management Endpoints

@workbench_core_bp.route('/<int:workbench_id>/structure', methods=['GET'])
@require_auth
def get_workbench_structure(workbench_id):
    """워크벤치 디렉토리 구조 정보 조회"""
    try:
        conn = get_db_connection()
        
        # 워크벤치 존재 확인 및 권한 체크
        workbench = conn.execute('''
            SELECT name FROM vizr_workbench 
            WHERE id = ? AND user_id = ?
        ''', (workbench_id, session['user_id'])).fetchone()
        
        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404
        
        conn.close()
        
        # 워크벤치 구조 정보 조회
        # get_workbench_schema를 통해 사용자별 경로 자동 계산
        workbench_name = get_workbench_name_by_id(workbench_id)
        workbench_schema = get_workbench_schema(workbench_name, session['user_id'])

        from utils.workbench_utils import get_workbench_structure_info
        structure_info = get_workbench_structure_info(
            workbench_schema['base'],
            ""  # workbench_name은 이미 경로에 포함됨
        )
        
        return jsonify({
            'workbench_id': workbench_id,
            'workbench_name': workbench['name'],
            'structure': structure_info,
            'timestamp': datetime.now(timezone(timedelta(hours=9))).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get workbench structure: {e}")
        return jsonify({'error': str(e)}), 500

@workbench_core_bp.route('/<int:workbench_id>/structure/validate', methods=['GET'])
@require_auth
def validate_workbench_structure(workbench_id):
    """워크벤치 구조 유효성 검사"""
    try:
        conn = get_db_connection()
        
        # 워크벤치 존재 확인 및 권한 체크
        workbench = conn.execute('''
            SELECT name FROM vizr_workbench 
            WHERE id = ? AND user_id = ?
        ''', (workbench_id, session['user_id'])).fetchone()
        
        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404
        
        conn.close()
        
        # 워크벤치 구조 유효성 검사
        # get_workbench_schema를 통해 사용자별 경로 자동 계산
        workbench_name = get_workbench_name_by_id(workbench_id)
        workbench_schema = get_workbench_schema(workbench_name, session['user_id'])

        from utils.workbench_utils import validate_workbench_structure
        validation_result = validate_workbench_structure(
            workbench_schema['base'],
            ""  # workbench_name은 이미 경로에 포함됨
        )
        
        return jsonify({
            'workbench_id': workbench_id,
            'workbench_name': workbench['name'],
            'validation': validation_result,
            'timestamp': datetime.now(timezone(timedelta(hours=9))).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to validate workbench structure: {e}")
        return jsonify({'error': str(e)}), 500


@workbench_core_bp.route('/<int:workbench_id>/download-progress', methods=['GET'])
@require_auth
def get_download_progress(workbench_id):
    """워크벤치의 다운로드 진행상황 조회"""
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [DOWNLOAD-PROGRESS-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        logger.info(f"✅ [DOWNLOAD-PROGRESS-API] Workbench access granted (permission: {permission})")

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            if not workbench:
                logger.warning(f"⚠️ [DOWNLOAD-PROGRESS-API] Workbench {workbench_id} not found in database")
                return jsonify({'error': 'Workbench not found'}), 404
            
            # download step의 progress_detail과 parameters 조회
            download_step = conn.execute('''
                SELECT progress_detail, parameters, status, updated_at
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'download'
                ORDER BY id DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if not download_step:
                # download step이 없으면 빈 진행상황 반환
                return jsonify({
                    'workbench_id': workbench_id,
                    'workbench_name': workbench['name'],
                    'files': {},
                    'overall_status': 'pending',
                    'last_updated': None
                }), 200

            # progress_detail JSON 파싱
            files_progress = {}
            summary = {
                "total_files": 0,
                "downloading_files": 0,
                "completed_files": 0,
                "pending_files": 0,
                "last_updated": None,
                "total_size": 0,
                "downloaded_size": 0
            }

            # 1. 먼저 progress_detail에서 파일 정보 추출
            if download_step['progress_detail']:
                try:
                    progress_data = json.loads(download_step['progress_detail'])
                    files_progress = progress_data.get('files', {})
                    summary = progress_data.get('summary', summary)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse progress_detail for workbench {workbench_id}: {e}")
                    files_progress = {}

            # 2. progress_detail이 비어있으면 parameters에서 파일 정보 추출
            if not files_progress and download_step['parameters']:
                try:
                    params = json.loads(download_step['parameters'])

                    # SRR_Runs 정보가 있으면 파일 리스트 생성 (NCBI)
                    if params.get('SRR_Runs'):
                        srr_sizes = params.get('SRR_Sizes', {})
                        for srr_run in params['SRR_Runs']:
                            files_progress[srr_run] = {
                                'status': 'pending',
                                'progress': 0,
                                'file_size': srr_sizes.get(srr_run, 0),
                                'downloaded_size': 0,
                                'timestamp': None
                            }
                        summary['total_files'] = len(params['SRR_Runs'])
                        summary['pending_files'] = len(params['SRR_Runs'])

                    # file_mappings 정보가 있으면 파일 리스트 생성 (Local)
                    elif params.get('file_mappings'):
                        file_set = set()
                        for mapping in params['file_mappings']:
                            if mapping.get('file1'):
                                file_set.add(mapping['file1'])
                            if mapping.get('file2'):
                                file_set.add(mapping['file2'])

                        for file_name in file_set:
                            files_progress[file_name] = {
                                'status': 'pending',
                                'progress': 0,
                                'file_size': 0,
                                'downloaded_size': 0,
                                'timestamp': None
                            }
                        summary['total_files'] = len(file_set)
                        summary['pending_files'] = len(file_set)

                    # serverFilePaths 정보가 있으면 파일 리스트 생성 (Server)
                    elif params.get('serverFilePaths'):
                        server_paths = params['serverFilePaths'].strip()
                        if server_paths:
                            # 줄바꿈으로 분리된 서버 파일 경로들 파싱
                            file_paths = [path.strip() for path in server_paths.split('\n') if path.strip()]

                            for file_path in file_paths:
                                # 파일명만 추출 (경로에서 basename)
                                import os
                                file_name = os.path.basename(file_path)

                                # 파일 크기 확인 시도 (서버 파일이므로 실제 크기 확인 가능)
                                file_size = 0
                                try:
                                    if os.path.exists(file_path):
                                        file_size = os.path.getsize(file_path)
                                except Exception:
                                    pass  # 파일 크기 확인 실패해도 계속 진행

                                files_progress[file_name] = {
                                    'status': 'pending',
                                    'progress': 0,
                                    'file_size': file_size,
                                    'downloaded_size': 0,
                                    'timestamp': None
                                }

                            summary['total_files'] = len(file_paths)
                            summary['pending_files'] = len(file_paths)

                    logger.info(f"Initialized files from parameters for workbench {workbench_id}: {len(files_progress)} files")

                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse parameters for workbench {workbench_id}: {e}")
                    files_progress = {}
            
            return jsonify({
                'workbench_id': workbench_id,
                'workbench_name': workbench['name'],
                'summary': summary,  # 프론트엔드 즉시 업데이트용
                'files': files_progress,
                'overall_status': download_step['status'],
                'last_updated': download_step['updated_at']
            }), 200
            
    except Exception as e:
        logger.error(f"Failed to get download progress for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@workbench_core_bp.route('/<int:workbench_id>/pipeline', methods=['PUT'])
@require_auth
def update_workbench_pipeline(workbench_id):
    """
    파이프라인 설정 업데이트

    Request JSON:
    {
        "pipelineSteps": [
            {
                "step": "qc",
                "tool": "fastqc",
                "description": "...",
                "parameters": {...}
            },
            ...
        ],
        "referenceSet": "TAIR10"  # Optional, included in alignment step parameters
    }
    """
    logger.info(f"[UPDATE-PIPELINE] Starting pipeline update for workbench {workbench_id}")

    try:
        user_id = get_current_user_id()
        data = request.get_json()

        if not data or 'pipelineSteps' not in data:
            logger.error("[UPDATE-PIPELINE] Missing pipelineSteps in request")
            return jsonify({'error': 'pipelineSteps is required'}), 400

        # Check workbench access permission
        has_access, permission = check_workbench_access(workbench_id, user_id)
        if not has_access:
            logger.warning(f"[UPDATE-PIPELINE] Access denied for user {user_id} to workbench {workbench_id}")
            return jsonify({'error': 'Access denied'}), 403

        # Shared users cannot edit pipeline
        if permission == 'shared':
            logger.warning(f"[UPDATE-PIPELINE] Shared user {user_id} attempted to edit pipeline")
            return jsonify({'error': 'Shared users cannot edit pipeline configuration'}), 403

        with get_db_connection() as conn:
            # Check if workbench exists
            workbench = conn.execute(
                'SELECT * FROM vizr_workbench WHERE id = ?',
                (workbench_id,)
            ).fetchone()

            if not workbench:
                logger.error(f"[UPDATE-PIPELINE] Workbench {workbench_id} not found")
                return jsonify({'error': 'Workbench not found'}), 404

            # Check if pipeline is running
            running_jobs = conn.execute('''
                SELECT COUNT(*) as count
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND status IN ('running', 'pending')
            ''', (workbench_id,)).fetchone()

            if running_jobs and running_jobs['count'] > 0:
                logger.warning(f"[UPDATE-PIPELINE] Cannot edit - {running_jobs['count']} job(s) running")
                return jsonify({'error': 'Cannot edit pipeline while it is running'}), 400

            # Delete existing pipeline configurations
            conn.execute(
                'DELETE FROM vizr_pipeline_configurations WHERE workbench_id = ?',
                (workbench_id,)
            )

            # Insert new pipeline configuration
            pipeline_steps = data['pipelineSteps']
            count_step = next((step for step in pipeline_steps if step.get('step') == 'count'), None)
            locked_steps = [
                {
                    'step': step.get('step'),
                    'tool': step.get('tool'),
                    'disabled': bool((step.get('parameters') or {}).get('disabled')),
                    'locked_reason': (step.get('parameters') or {}).get('locked_reason'),
                }
                for step in pipeline_steps
                if bool((step.get('parameters') or {}).get('disabled')) or (step.get('parameters') or {}).get('locked_reason')
            ]
            logger.info(f"[UPDATE-PIPELINE] Incoming source context for workbench {workbench_id}:")
            logger.info(f"   - step count: {len(pipeline_steps)}")
            logger.info(f"   - count step tool: {count_step.get('tool') if count_step else None}")
            logger.info(f"   - count step description: {count_step.get('description') if count_step else None}")
            logger.info(f"   - locked steps: {locked_steps}")

            conn.execute('''
                INSERT INTO vizr_pipeline_configurations
                (workbench_id, pipeline_steps, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
            ''', (workbench_id, json.dumps(pipeline_steps)))

            # Update workbench updated_at timestamp
            conn.execute('''
                UPDATE vizr_workbench
                SET updated_at = ?
                WHERE id = ?
            ''', (
                datetime.now(timezone.utc).isoformat(),
                workbench_id
            ))

            conn.commit()

            logger.info(f"[UPDATE-PIPELINE] Successfully updated pipeline for workbench {workbench_id} with {len(pipeline_steps)} steps")

            return jsonify({
                'message': 'Pipeline configuration updated successfully',
                'workbench_id': workbench_id
            }), 200

    except Exception as e:
        logger.error(f"[UPDATE-PIPELINE] Failed to update pipeline configuration: {e}")
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to update pipeline configuration'}), 500


@workbench_core_bp.route('/<int:workbench_id>/method-text', methods=['GET'])
@require_auth
def get_method_text(workbench_id):
    """Generate Method section text for paper writing based on actual pipeline parameters."""
    try:
        user_id = get_current_user_id()
        has_access = check_workbench_access(workbench_id, user_id)
        if not has_access:
            return jsonify({'error': 'Access denied'}), 403

        with get_db_connection() as conn:
            # Get workbench info
            workbench = conn.execute(
                'SELECT id, name, species FROM vizr_workbench WHERE id = ?',
                (workbench_id,)
            ).fetchone()
            if not workbench:
                return jsonify({'error': 'Workbench not found'}), 404

            # Get pipeline configuration
            pipeline_config = conn.execute('''
                SELECT pipeline_steps FROM vizr_pipeline_configurations
                WHERE workbench_id = ?
                ORDER BY created_at DESC LIMIT 1
            ''', (workbench_id,)).fetchone()

            if not pipeline_config or not pipeline_config['pipeline_steps']:
                return jsonify({'error': 'No pipeline configuration found'}), 404

            pipeline_steps = json.loads(pipeline_config['pipeline_steps'])

            # Get sample info
            sample_record = conn.execute('''
                SELECT layout, samples FROM vizr_pipeline_samples
                WHERE workbench_id = ?
                ORDER BY created_at DESC LIMIT 1
            ''', (workbench_id,)).fetchone()

            layout = sample_record['layout'] if sample_record else 'unknown'
            samples = json.loads(sample_record['samples']) if sample_record else []
            sample_count = len(samples)

            # Get executed steps info (for completion status)
            executed_steps = conn.execute('''
                SELECT DISTINCT step_name, tool_name, parameters, status
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND status = 'completed'
            ''', (workbench_id,)).fetchall()

        # Build method text from pipeline steps
        method_sections = []
        step_details = {}

        for step in pipeline_steps:
            step_name = step.get('step', '')
            tool = step.get('tool', '')
            params = step.get('parameters', {})
            step_details[step_name] = {'tool': tool, 'parameters': params}

        # --- Data Overview ---
        layout_text = 'paired-end' if layout == 'pe' else 'single-end'
        species = workbench.get('species', '') if isinstance(workbench, dict) else (workbench['species'] if workbench else '')
        species_display = _format_species_name(species)
        method_sections.append(
            f"A total of {sample_count} {layout_text} samples"
            f"{' from ' + species_display if species_display else ''} were processed "
            f"through the following pipeline."
        )

        # --- QC ---
        if 'qc' in step_details:
            qc = step_details['qc']
            tool_name = qc['tool'].upper() if qc['tool'] else 'FastQC'
            if qc['tool'] == 'fastqc':
                tool_name = 'FastQC'
            elif qc['tool'] == 'multiqc':
                tool_name = 'MultiQC'
            elif qc['tool'] == 'fastp':
                tool_name = 'fastp'
            method_sections.append(
                f"Raw read quality was assessed using {tool_name}."
            )

        # --- Preprocessing (Clean) ---
        if 'clean' in step_details:
            clean = step_details['clean']
            params = clean['parameters']
            clean_tools = params.get('clean_tools', [])
            clean_parts = []

            if 'trimmomatic' in clean_tools:
                adapter = params.get('trimmomaticAdapter', params.get('trimmomatic_adapter', 'TruSeq3'))
                seed_mm = params.get('illuminaclipSeedMismatches', params.get('illuminaclip_seed_mismatches', 2))
                palindrome = params.get('illuminaclipPalindromeClip', params.get('illuminaclip_palindrome_clip', 30))
                simple = params.get('illuminaclipSimpleClip', params.get('illuminaclip_simple_clip', 10))

                # Get trimmomatic-specific params (handle both naming conventions)
                leading = params.get('trimmomatic_leading', params.get('leading', 3))
                trailing = params.get('trimmomatic_trailing', params.get('trailing', 3))
                slidingwindow = params.get('trimmomatic_slidingwindow', params.get('slidingwindow', '4:15'))
                minlen = params.get('trimmomatic_minlen', params.get('minlen', 36))

                adapter_map = {
                    'TruSeq3': {'se': 'TruSeq3-SE.fa', 'pe': 'TruSeq3-PE-2.fa'},
                    'TruSeq2': {'se': 'TruSeq2-SE.fa', 'pe': 'TruSeq2-PE.fa'},
                    'NexteraPE': {'pe': 'NexteraPE-PE.fa'}
                }
                adapter_value = str(adapter)
                if adapter_value.lower() == 'none':
                    clean_parts.append(
                        f"Reads were quality-trimmed using Trimmomatic without adapter clipping, "
                        f"LEADING:{leading}, TRAILING:{trailing}, "
                        f"SLIDINGWINDOW:{slidingwindow}, MINLEN:{minlen}."
                    )
                else:
                    adapter_file = adapter_value if adapter_value.endswith('.fa') else adapter_map.get(adapter_value, {}).get(layout, adapter_value)
                    clean_parts.append(
                        f"Adapter sequences were removed using Trimmomatic with "
                        f"ILLUMINACLIP:{adapter_file}:{seed_mm}:{palindrome}:{simple}, "
                        f"LEADING:{leading}, TRAILING:{trailing}, "
                        f"SLIDINGWINDOW:{slidingwindow}, MINLEN:{minlen}."
                    )

            if 'prinseq' in clean_tools:
                min_len = params.get('prinseq_min_len', params.get('min_len', 50))
                min_qual = params.get('prinseq_min_qual_mean', params.get('min_qual_mean', 20))
                trim_left = params.get('prinseq_trim_qual_left', params.get('trim_qual_left', 20))
                trim_right = params.get('prinseq_trim_qual_right', params.get('trim_qual_right', 20))

                clean_parts.append(
                    f"Additional quality filtering was performed using PRINSEQ with "
                    f"minimum length {min_len} bp, minimum mean quality score {min_qual}, "
                    f"and quality trimming threshold of {trim_left} (5') and {trim_right} (3')."
                )

            if clean_parts:
                method_sections.append(' '.join(clean_parts))

        # --- Alignment ---
        if 'alignment' in step_details:
            align = step_details['alignment']
            params = align['parameters']
            tool = align['tool']
            ref_set = params.get('reference_set', '')
            max_intronlen = params.get('max_intronlen', '')
            reads_label = 'Clean reads' if 'clean' in step_details else 'Reads'

            if tool == 'hisat2':
                align_text = f"{reads_label} were aligned to the {ref_set} reference genome using HISAT2"
                if max_intronlen:
                    align_text += f" with maximum intron length of {max_intronlen:,} bp"
                align_text += "."
            elif tool == 'bowtie2':
                preset = params.get('preset', 'sensitive')
                align_text = f"{reads_label} were aligned to the {ref_set} reference genome using Bowtie2 ({preset} mode)."
            elif tool == 'bowtie':
                max_mm = params.get('max_mismatches', 2)
                align_text = f"{reads_label} were aligned to the {ref_set} reference genome using Bowtie (max mismatches: {max_mm})."
            else:
                align_text = f"{reads_label} were aligned to the {ref_set} reference genome using {tool}."

            method_sections.append(align_text)

        # --- Quantification ---
        if 'count' in step_details:
            count = step_details['count']
            params = count['parameters']
            tool = count['tool']

            if tool == 'stringtie':
                min_cov = params.get('min_coverage', 2.5)
                min_len = params.get('min_transcript_len', 200)
                method_sections.append(
                    f"Transcript assembly and expression quantification were performed using StringTie "
                    f"with minimum coverage of {min_cov} and minimum transcript length of {min_len} bp."
                )
            elif tool == 'rsem':
                method_sections.append(
                    f"Expression quantification was performed using RSEM."
                )

        # Citation
        method_sections.append(
            "All analyses were performed using VizR (Jeon et al., 2026)."
        )

        # Combine all sections
        method_text = ' '.join(method_sections)

        return jsonify({
            'method_text': method_text,
            'workbench_name': workbench['name'] if workbench else '',
            'pipeline_steps': pipeline_steps,
            'sample_count': sample_count,
            'layout': layout,
            'species': species
        })

    except Exception as e:
        logger.error(f"[METHOD-TEXT] Failed to generate method text for workbench {workbench_id}: {e}")
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to generate method text'}), 500


def _format_species_name(species: str) -> str:
    """Format species identifier to display name."""
    species_map = {
        'arabidopsis': 'Arabidopsis thaliana',
        'lemna_gibba': 'Lemna gibba',
        'lemna_minor': 'Lemna minor',
        'human': 'Homo sapiens',
        'mouse': 'Mus musculus',
        'rice': 'Oryza sativa',
        'maize': 'Zea mays',
    }
    return species_map.get(species, species.replace('_', ' ').title() if species else '')
