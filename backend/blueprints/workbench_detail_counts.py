"""
Counts Results API
Gene expression count quantification results (TMM, TPM, Raw) API
"""

import os
import json
import math
import re
import time
import io
import pandas as pd
from flask import Blueprint, jsonify, request, session, make_response
from backend.utils import database
from backend.utils.database import get_db_connection
from backend.blueprints.workbench_utils import get_workbench_schema, load_gene_annotations, get_workbench_name_by_id
from backend.blueprints.auth import require_auth
from backend.blueprints.workbench_share import check_workbench_access
from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'INFO')

counts_bp = Blueprint('counts', __name__, url_prefix='/api/workbenches')


def normalize_tool_name(tool_name: str) -> str:
    """
    DEG 도구 이름을 정규화 (대소문자 관계없이 올바른 형식으로 변환)

    Args:
        tool_name: 입력된 도구 이름

    Returns:
        str: 정규화된 도구 이름 (edgeR 또는 DESeq2)
    """
    tool_name_lower = tool_name.lower()

    if tool_name_lower == 'edger':
        return 'edgeR'
    elif tool_name_lower == 'deseq2':
        return 'DESeq2'
    else:
        # 기본값: 입력된 그대로 반환 (향후 다른 도구 추가 시)
        return tool_name


@counts_bp.route('/<int:workbench_id>/count-progress', methods=['GET'])
@require_auth
def get_counts_progress(workbench_id):
    """
    Count quantification 진행률 조회 API

    Response:
    {
        "workbench_id": 1,
        "status": "running",
        "progress_data": {
            "completed_files": 2,
            "total_files": 5,
            "progress_percent": 40.0,
            "tool_name": "stringtie"
        },
        "last_updated": "2024-01-15T10:35:00Z"
    }
    """
    logger.info(f"🧬 [COUNTS-PROGRESS-API] Starting count progress query for workbench {workbench_id}")
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [COUNTS-PROGRESS-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        logger.info(f"✅ [COUNTS-PROGRESS-API] Workbench access granted (permission: {permission})")

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            logger.info(f"✅ [COUNTS-PROGRESS-API] Workbench loaded: {workbench['name']}")

            # Count step 조회 (step_name이 count인 경우)
            logger.info(f"🔍 [COUNTS-PROGRESS-API] Querying count step for workbench {workbench_id}")
            count_step = conn.execute('''
                SELECT progress_detail, status, updated_at, tool_name
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'count'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if count_step:
                logger.info(f"📊 [COUNTS-PROGRESS-API] Found count step: tool={count_step['tool_name']}, status={count_step['status']}, updated_at={count_step['updated_at']}")
            else:
                logger.info(f"ℹ️ [COUNTS-PROGRESS-API] No count step found for workbench {workbench_id}")

            # Count 진행률 처리
            progress_data = None
            status = 'not_started'
            last_updated = None

            if count_step:
                status = count_step['status']
                last_updated = count_step['updated_at']

                if count_step['progress_detail']:
                    try:
                        logger.info(f"📄 [COUNTS-PROGRESS-API] Parsing progress_detail JSON for workbench {workbench_id}")
                        progress_detail_json = json.loads(count_step['progress_detail'])

                        # Count 진행률 구조에서 정보 추출
                        completed = progress_detail_json.get('summary', {}).get('completed_files', 0)
                        total = progress_detail_json.get('summary', {}).get('total_files', 0)
                        progress_percent = progress_detail_json.get('summary', {}).get('progress_percent', 0.0)

                        logger.info(f"📈 [COUNTS-PROGRESS-API] Progress extracted: {completed}/{total} files ({progress_percent:.1f}%)")

                        # 진행률에 따른 상태 업데이트
                        if total > 0 and completed == total:
                            status = 'completed'
                            logger.info(f"✅ [COUNTS-PROGRESS-API] Count quantification completed for workbench {workbench_id}")
                        elif completed > 0:
                            status = 'running'
                            logger.info(f"🔄 [COUNTS-PROGRESS-API] Count quantification running for workbench {workbench_id}")

                        # 프론트엔드 호환성을 위한 progress_data 구성
                        progress_data = {
                            'completed_files': completed,
                            'total_files': total,
                            'progress_percent': progress_percent,
                            'tool_name': count_step['tool_name']
                        }

                        logger.info(f"📊 [COUNTS-PROGRESS-API] Final progress_data prepared: {progress_data}")

                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"❌ [COUNTS-PROGRESS-API] Failed to parse StringTie progress_detail for workbench {workbench_id}: {e}")

            logger.info(f"📊 [COUNTS-PROGRESS-API] Final response for workbench {workbench_id}: Status({status}), Data({progress_data})")

            return jsonify({
                'workbench_id': workbench_id,
                'status': status,
                'progress_data': progress_data,
                'last_updated': last_updated
            }), 200

    except Exception as e:
        logger.error(f"Failed to get counts progress for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@counts_bp.route('/<int:workbench_id>/count-results', methods=['GET'])
@require_auth
def get_counts_result(workbench_id):
    """
    Count quantification 결과 조회 API

    Query Parameters:
        matrix_type: 'TMM' | 'TPM' | 'Raw' (default: 'TMM')
        limit: 결과 행 제한 (default: 1000)

    Response:
    {
        "workbench_id": 1,
        "matrix_type": "TMM",
        "matrix": [
            {"gene_id": "AT1G01010", "sample1": 123.45, "sample2": 234.56, ...},
            ...
        ],
        "samples": ["sample1", "sample2", ...],
        "total_genes": 27416,
        "showing_genes": 1000,
        "matrix_file": "/path/to/matrix.csv",
        "status": "available"
    }
    """
    start_time = time.time()

    logger.info(f"🧬 [COUNTS-RESULTS-API] Starting count results query for workbench {workbench_id}")

    # Query parameters
    matrix_type = request.args.get('matrix_type', 'TMM').upper()
    page = int(request.args.get('page', 1))  # 1-based page number
    limit = int(request.args.get('limit', 1000))
    offset = (page - 1) * limit
    search_query = request.args.get('search', '').strip()  # 검색어 (comma/space/tab/newline separated)

    # Validate matrix_type
    valid_types = ['TMM', 'TPM', 'RAW']
    if matrix_type not in valid_types:
        logger.warning(f"⚠️ [COUNTS-RESULTS-API] Invalid matrix_type: {matrix_type}")
        return jsonify({'error': f'Invalid matrix_type. Must be one of: {valid_types}'}), 400

    logger.info(f"📊 [COUNTS-RESULTS-API] Request params: matrix_type={matrix_type}, page={page}, limit={limit}, offset={offset}, search={search_query[:100] if search_query else 'None'}")

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [COUNTS-RESULTS-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        logger.info(f"✅ [COUNTS-RESULTS-API] Workbench access granted (permission: {permission})")

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            logger.info(f"✅ [COUNTS-RESULTS-API] Workbench loaded: {workbench['name']}")

            # 워크벤치 디렉토리 구조 가져오기
            # Note: DB status 체크를 제거하고 실제 파일 존재 여부로 판단 (race condition 방지)
            logger.info(f"📂 [COUNTS-RESULTS-API] Workbench name: {workbench['name']}")

            wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
            counts_dir = wb_schema['quanti']['counts']
            logger.info(f"📂 [COUNTS-RESULTS-API] Counts directory: {counts_dir}")

            # Matrix 파일 경로 결정 (통일된 파일명 사용)
            # StringTie와 RSEM 모두 genes.counts.matrix 생성
            matrix_file_map = {
                'TMM': 'genes.TMM.matrix',
                'TPM': 'genes.TPM.matrix',
                'RAW': 'genes.counts.matrix'  # StringTie, RSEM 공통
            }

            matrix_filename = matrix_file_map.get(matrix_type)
            matrix_filepath = os.path.join(counts_dir, matrix_filename)

            logger.info(f"📂 [COUNTS-RESULTS-API] Looking for matrix file: {matrix_filepath}")

            # 디렉토리 존재 및 파일 목록 확인
            if os.path.exists(counts_dir):
                files_in_dir = os.listdir(counts_dir)
                logger.info(f"📂 [COUNTS-RESULTS-API] Files in counts_dir: {files_in_dir}")
            else:
                logger.warning(f"⚠️ [COUNTS-RESULTS-API] Counts directory does not exist: {counts_dir}")

            # 파일 존재 확인
            if not os.path.exists(matrix_filepath):
                logger.warning(f"⚠️ [COUNTS-RESULTS-API] Matrix file not found: {matrix_filepath}")
                logger.warning(f"⚠️ [COUNTS-RESULTS-API] Expected filename: {matrix_filename}")
                return jsonify({
                    'workbench_id': workbench_id,
                    'matrix_type': matrix_type,
                    'matrix': [],
                    'samples': [],
                    'total_genes': 0,
                    'showing_genes': 0,
                    'matrix_file': None,
                    'status': 'not_available'
                }), 200

            # TSV 파일 읽기 (모든 매트릭스 타입이 탭 구분자 사용)
            # StringTie와 RSEM 모두 genes.counts.matrix는 TSV 형식
            logger.info(f"📖 [COUNTS-RESULTS-API] Reading matrix file with pandas")
            df = pd.read_csv(matrix_filepath, sep='\t')

            # gene_id 컬럼 확인 (GeneID 또는 gene_id)
            gene_id_col = None
            if 'GeneID' in df.columns:
                gene_id_col = 'GeneID'
            elif 'gene_id' in df.columns:
                gene_id_col = 'gene_id'
            else:
                logger.error(f"❌ [COUNTS-RESULTS-API] Gene ID column not found in matrix. Columns: {df.columns.tolist()}")
                return jsonify({'error': 'Invalid matrix format: missing gene_id or GeneID column'}), 500

            # 샘플 컬럼 추출 (gene_id 컬럼 제외한 나머지)
            samples = [col for col in df.columns if col != gene_id_col]
            total_genes = len(df)

            logger.info(f"📊 [COUNTS-RESULTS-API] Matrix loaded: {total_genes} genes, {len(samples)} samples")

            # vizr_pipeline_samples에서 그룹 정보 가져오기
            groups = []
            try:
                pipeline_samples = conn.execute('''
                    SELECT samples FROM vizr_pipeline_samples
                    WHERE workbench_id = ?
                    LIMIT 1
                ''', (workbench_id,)).fetchone()

                if pipeline_samples and pipeline_samples['samples']:
                    samples_data = json.loads(pipeline_samples['samples'])
                    # vizr_pipeline_samples 순서를 유지하면서 중복 제거한 그룹 이름 추출
                    seen = set()
                    groups = []
                    for s in samples_data:
                        if 'groupName' in s and s['groupName'] not in seen:
                            groups.append(s['groupName'])
                            seen.add(s['groupName'])
                    logger.info(f"📊 [COUNTS-RESULTS-API] Extracted {len(groups)} unique groups (in vizr_pipeline_samples order): {groups}")
            except Exception as e:
                logger.warning(f"⚠️ [COUNTS-RESULTS-API] Failed to extract groups: {e}")
                # 그룹 정보를 가져올 수 없으면 빈 배열

            # 검색 필터링 적용 (페이지네이션 전에 수행)
            if search_query:
                logger.info(f"🔍 [COUNTS-RESULTS-API] Search query received: {search_query[:100]}")

                # 검색어 파싱 (쉼표, 공백, 탭, 줄바꿈으로 구분)
                search_terms = re.split(r'[,\s\t\n]+', search_query)
                search_terms = [term.strip().upper() for term in search_terms if term.strip()]

                logger.info(f"🔍 [COUNTS-RESULTS-API] Parsed {len(search_terms)} search terms")

                if search_terms:
                    # gene_symbol_map 미리 로드 (검색용)
                    gene_annotations = load_gene_annotations()

                    # 1. gene_id로 부분 일치 검색 (대소문자 구분 없이)
                    mask = pd.Series([False] * len(df), index=df.index)
                    for term in search_terms:
                        mask |= df[gene_id_col].str.upper().str.contains(term, regex=False, na=False)
                    matched_by_id = mask.sum()

                    # 2. gene_symbol로 부분 일치 검색
                    gene_ids_from_symbols = []
                    for gene_id, info in gene_annotations.items():
                        symbol = info.get('symbol', '')
                        symbol_upper = symbol.upper()
                        # 부분 일치 검색: 검색어가 심볼에 포함되어 있는지 확인
                        if any(term in symbol_upper for term in search_terms):
                            gene_ids_from_symbols.append(gene_id)

                    matched_by_symbol = 0
                    if gene_ids_from_symbols:
                        symbol_mask = df[gene_id_col].isin(gene_ids_from_symbols)
                        mask |= symbol_mask
                        matched_by_symbol = symbol_mask.sum()

                    # 필터링 적용
                    df = df[mask]
                    total_genes = len(df)

                    logger.info(f"✅ [COUNTS-RESULTS-API] Search complete: {total_genes} genes matched")
                    logger.info(f"   ├─ By gene_id: {matched_by_id}")
                    logger.info(f"   └─ By gene_symbol: {matched_by_symbol}")

                    if total_genes == 0:
                        logger.warning(f"⚠️ [COUNTS-RESULTS-API] No genes matched search query: {search_terms[:10]}")
                else:
                    logger.info(f"ℹ️ [COUNTS-RESULTS-API] Empty search terms after parsing")

            # 페이지네이션 적용 (offset + limit)
            df_limited = df.iloc[offset:offset + limit]
            showing_genes = len(df_limited)

            # 전체 페이지 수 계산
            total_pages = math.ceil(total_genes / limit) if limit > 0 else 1

            # Load gene symbol mapping
            gene_annotations = load_gene_annotations()

            # DataFrame을 dict 리스트로 변환 (gene_id + gene_symbol + gene_description)
            conversion_start = time.time()

            matrix_data = []
            for _, row in df_limited.iterrows():
                gene_id = row[gene_id_col]
                gene_info = gene_annotations.get(gene_id, {})
                gene_symbol = gene_info.get("symbol", gene_id)  # Fallback to gene_id if no symbol
                gene_description = gene_info.get("description", "No description available")

                gene_dict = {
                    'gene_id': gene_id,
                    'gene_symbol': gene_symbol,
                    'gene_description': gene_description
                }
                for sample in samples:
                    gene_dict[sample] = row[sample]
                matrix_data.append(gene_dict)

            conversion_time = time.time() - conversion_start
            logger.info(f"✅ [COUNTS-RESULTS-API] Converted {len(matrix_data)} genes in {conversion_time:.3f}s")
            logger.info(f"✅ [COUNTS-RESULTS-API] Returning {showing_genes} genes (page {page}/{total_pages})")

            # JSON 직렬화 시작
            logger.info(f"🔄 [COUNTS-RESULTS-API] Starting JSON serialization...")
            json_start = time.time()

            response_data = {
                'workbench_id': workbench_id,
                'matrix_type': matrix_type,
                'matrix': matrix_data,
                'samples': samples,
                'groups': groups,  # 그룹 이름 리스트 추가
                'total_genes': total_genes,
                'showing_genes': showing_genes,
                'current_page': page,
                'total_pages': total_pages,
                'page_size': limit,
                'matrix_file': matrix_filepath,
                'status': 'available',
                # 검색 관련 메타데이터 추가
                'search_query': search_query,
                'is_search_result': bool(search_query)
            }

            json_time = time.time() - json_start
            total_time = time.time() - start_time

            logger.info(f"✅ [COUNTS-RESULTS-API] JSON serialization completed in {json_time:.3f}s")
            logger.info(f"🎉 [COUNTS-RESULTS-API] Total API processing time: {total_time:.3f}s")
            logger.info(f"📊 [COUNTS-RESULTS-API] Performance breakdown:")
            logger.info(f"   ├─ Conversion: {conversion_time:.3f}s ({conversion_time/total_time*100:.1f}%)")
            logger.info(f"   ├─ JSON serialization: {json_time:.3f}s ({json_time/total_time*100:.1f}%)")
            logger.info(f"   └─ Other: {total_time-conversion_time-json_time:.3f}s")

            return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"❌ [COUNTS-RESULTS-API] Failed to get counts results for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@counts_bp.route('/<int:workbench_id>/count-results/selected', methods=['POST'])
@require_auth
def get_selected_counts_result(workbench_id):
    """
    Exact selected gene list 기반 count matrix 조회 API.
    """
    start_time = time.time()

    try:
        request_data = request.get_json(silent=True) or {}
        matrix_type = str(request_data.get('matrix_type', 'TMM')).upper()
        selected_genes = request_data.get('selected_genes', [])
        search_query = str(request_data.get('search', '')).strip()
        page = max(1, int(request_data.get('page', 1)))
        limit = max(1, int(request_data.get('limit', 500)))
        offset = (page - 1) * limit

        if not isinstance(selected_genes, list) or not selected_genes:
            return jsonify({'error': 'selected_genes must be a non-empty list'}), 400

        valid_types = ['TMM', 'TPM', 'RAW']
        if matrix_type not in valid_types:
            return jsonify({'error': f'Invalid matrix_type. Must be one of: {valid_types}'}), 400

        selected_gene_list = []
        seen_genes = set()
        for gene in selected_genes:
            gene_id = str(gene).strip()
            if gene_id and gene_id not in seen_genes:
                seen_genes.add(gene_id)
                selected_gene_list.append(gene_id)

        logger.info(
            f"[COUNTS-SELECTED-API] Request: workbench_id={workbench_id}, matrix_type={matrix_type}, "
            f"selected_genes={len(selected_gene_list)}, page={page}, limit={limit}, "
            f"search={search_query[:100] if search_query else 'None'}"
        )

        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            return jsonify({'error': 'Workbench not found'}), 404

        with get_db_connection() as conn:
            workbench = conn.execute(
                '''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
                ''',
                (workbench_id,)
            ).fetchone()

            if not workbench:
                return jsonify({'error': 'Workbench not found'}), 404

            wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
            counts_dir = wb_schema['quanti']['counts']

            matrix_file_map = {
                'TMM': 'genes.TMM.matrix',
                'TPM': 'genes.TPM.matrix',
                'RAW': 'genes.counts.matrix'
            }
            matrix_filename = matrix_file_map.get(matrix_type)
            matrix_filepath = os.path.join(counts_dir, matrix_filename)

            if not os.path.exists(matrix_filepath):
                return jsonify({
                    'workbench_id': workbench_id,
                    'matrix_type': matrix_type,
                    'matrix': [],
                    'samples': [],
                    'groups': [],
                    'total_genes': 0,
                    'showing_genes': 0,
                    'current_page': page,
                    'total_pages': 0,
                    'page_size': limit,
                    'matched_gene_ids': [],
                    'matrix_file': None,
                    'status': 'not_available'
                }), 200

            logger.info(f"[COUNTS-SELECTED-API] Reading matrix file: {matrix_filepath}")
            if matrix_type in ['TMM', 'TPM']:
                df = pd.read_csv(matrix_filepath, sep='\t')
            else:
                df = pd.read_csv(matrix_filepath)

            gene_id_col = None
            if 'GeneID' in df.columns:
                gene_id_col = 'GeneID'
            elif 'gene_id' in df.columns:
                gene_id_col = 'gene_id'
            else:
                return jsonify({'error': 'Invalid matrix format: missing gene_id or GeneID column'}), 500

            df[gene_id_col] = df[gene_id_col].astype(str)
            samples = [col for col in df.columns if col != gene_id_col]

            groups = []
            try:
                pipeline_samples = conn.execute(
                    '''
                    SELECT samples FROM vizr_pipeline_samples
                    WHERE workbench_id = ?
                    LIMIT 1
                    ''',
                    (workbench_id,)
                ).fetchone()

                if pipeline_samples and pipeline_samples['samples']:
                    samples_data = json.loads(pipeline_samples['samples'])
                    seen = set()
                    for sample in samples_data:
                        group_name = sample.get('groupName')
                        if group_name and group_name not in seen:
                            groups.append(group_name)
                            seen.add(group_name)
            except Exception as e:
                logger.warning(f"[COUNTS-SELECTED-API] Failed to extract groups: {e}")

            df = df[df[gene_id_col].isin(set(selected_gene_list))]
            logger.info(f"[COUNTS-SELECTED-API] Exact gene filter complete: matched={len(df)}")

            gene_annotations = load_gene_annotations()

            if search_query:
                search_terms = [term.strip().upper() for term in re.split(r'[,;\s\t\n]+', search_query) if term.strip()]
                if search_terms:
                    gene_symbols = df[gene_id_col].map(lambda gene_id: gene_annotations.get(gene_id, {}).get('symbol', ''))
                    gene_symbols_upper = gene_symbols.str.upper()
                    mask = pd.Series([False] * len(df), index=df.index)
                    for term in search_terms:
                        mask |= df[gene_id_col].str.upper().str.contains(term, regex=False, na=False)
                        mask |= gene_symbols_upper.str.contains(term, regex=False, na=False)
                    df = df[mask]
                    logger.info(f"[COUNTS-SELECTED-API] Search filter complete: matched={len(df)}")

            matched_gene_ids = df[gene_id_col].tolist()
            total_genes = len(df)
            total_pages = math.ceil(total_genes / limit) if total_genes > 0 else 0
            df_limited = df.iloc[offset:offset + limit]
            showing_genes = len(df_limited)

            matrix_data = []
            for _, row in df_limited.iterrows():
                gene_id = row[gene_id_col]
                gene_info = gene_annotations.get(gene_id, {})
                gene_dict = {
                    'gene_id': gene_id,
                    'gene_symbol': gene_info.get('symbol', gene_id),
                    'gene_description': gene_info.get('description', 'No description available')
                }
                for sample in samples:
                    gene_dict[sample] = row[sample]
                matrix_data.append(gene_dict)

            total_time = time.time() - start_time
            logger.info(
                f"[COUNTS-SELECTED-API] Response ready: total={total_genes}, showing={showing_genes}, "
                f"page={page}/{total_pages if total_pages > 0 else 1}, elapsed={total_time:.3f}s"
            )

            return jsonify({
                'workbench_id': workbench_id,
                'matrix_type': matrix_type,
                'matrix': matrix_data,
                'samples': samples,
                'groups': groups,
                'total_genes': total_genes,
                'showing_genes': showing_genes,
                'current_page': page,
                'total_pages': total_pages,
                'page_size': limit,
                'matched_gene_ids': matched_gene_ids,
                'matrix_file': matrix_filepath,
                'status': 'available',
                'search_query': search_query,
                'is_search_result': bool(search_query)
            }), 200

    except Exception as e:
        logger.error(f"[COUNTS-SELECTED-API] Failed to get selected counts for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500


@counts_bp.route('/<int:workbench_id>/count-results/download', methods=['GET', 'POST'])
@require_auth
def download_counts_result(workbench_id):
    """
    Count quantification 결과 전체 다운로드 API (페이지네이션 없음)

    Query Parameters:
        matrix_type: 'TMM' | 'TPM' | 'Raw' (default: 'TMM')
        search: 검색어 (optional)

    Response:
        CSV file with gene_id, gene_symbol, and all sample columns
    """
    logger.info(f"📥 [DOWNLOAD-API] Starting download for workbench {workbench_id}")

    # Query parameters (GET 기본)
    matrix_type = request.args.get('matrix_type', 'TMM').upper()
    search_query = request.args.get('search', '').strip()
    selected_genes = []

    # POST body 지원: 선택 유전자 다운로드
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}

        if body.get('matrix_type'):
            matrix_type = str(body.get('matrix_type')).upper()
        if body.get('search') is not None:
            search_query = str(body.get('search', '')).strip()

        raw_selected = body.get('selected_genes', [])
        if isinstance(raw_selected, list):
            selected_genes = [str(g).strip() for g in raw_selected if str(g).strip()]
        elif isinstance(raw_selected, str):
            selected_genes = [g.strip() for g in raw_selected.split(',') if g.strip()]

    selected_gene_set = set(selected_genes)

    # Validate matrix_type
    valid_types = ['TMM', 'TPM', 'RAW']
    if matrix_type not in valid_types:
        logger.warning(f"⚠️ [DOWNLOAD-API] Invalid matrix_type: {matrix_type}")
        return jsonify({'error': f'Invalid matrix_type. Must be one of: {valid_types}'}), 400

    logger.info(
        f"📊 [DOWNLOAD-API] Request params: matrix_type={matrix_type}, "
        f"search={search_query[:100] if search_query else 'None'}, "
        f"selected_genes={len(selected_gene_set)}"
    )

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [DOWNLOAD-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        logger.info(f"✅ [DOWNLOAD-API] Workbench access granted (permission: {permission})")

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            if not workbench:
                logger.warning(f"⚠️ [DOWNLOAD-API] Workbench {workbench_id} not found in database")
                return jsonify({'error': 'Workbench not found'}), 404

            workbench_name = workbench['name']

            # Count step 완료 여부 확인
            count_step = conn.execute('''
                SELECT status FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'count'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if not count_step or count_step['status'] != 'completed':
                logger.info(f"ℹ️ [DOWNLOAD-API] Count quantification not completed yet")
                return jsonify({'error': 'Count quantification not completed yet'}), 404

            # 워크벤치 디렉토리 구조 가져오기
            wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
            counts_dir = wb_schema['quanti']['counts']

            # Matrix 파일 경로 결정
            matrix_file_map = {
                'TMM': 'genes.TMM.matrix',
                'TPM': 'genes.TPM.matrix',
                'RAW': 'gene_count_matrix.csv'
            }

            matrix_filename = matrix_file_map.get(matrix_type)
            matrix_filepath = os.path.join(counts_dir, matrix_filename)

            if not os.path.exists(matrix_filepath):
                logger.warning(f"⚠️ [DOWNLOAD-API] Matrix file not found: {matrix_filepath}")
                return jsonify({'error': 'Matrix file not found'}), 404

            # CSV/TSV 파일 읽기
            logger.info(f"📖 [DOWNLOAD-API] Reading matrix file: {matrix_filepath}")
            if matrix_type in ['TMM', 'TPM']:
                df = pd.read_csv(matrix_filepath, sep='\t')
            else:
                df = pd.read_csv(matrix_filepath)

            # gene_id 컬럼 확인
            gene_id_col = None
            if 'GeneID' in df.columns:
                gene_id_col = 'GeneID'
            elif 'gene_id' in df.columns:
                gene_id_col = 'gene_id'
            else:
                logger.error(f"❌ [DOWNLOAD-API] Gene ID column not found in matrix")
                return jsonify({'error': 'Invalid matrix format'}), 500

            # 샘플 컬럼 추출
            samples = [col for col in df.columns if col != gene_id_col]
            total_genes = len(df)

            logger.info(f"📊 [DOWNLOAD-API] Matrix loaded: {total_genes} genes, {len(samples)} samples")

            # 검색 필터링 적용
            if search_query:
                logger.info(f"🔍 [DOWNLOAD-API] Applying search filter")

                # 검색어 파싱
                search_terms = re.split(r'[,\s\t\n]+', search_query)
                search_terms = [term.strip().upper() for term in search_terms if term.strip()]

                if search_terms:
                    gene_annotations = load_gene_annotations()

                    # gene_id로 부분 일치 검색
                    mask = pd.Series([False] * len(df), index=df.index)
                    for term in search_terms:
                        mask |= df[gene_id_col].str.upper().str.contains(term, regex=False, na=False)

                    # gene_symbol로 부분 일치 검색
                    gene_ids_from_symbols = [
                        gene_id for gene_id, info in gene_annotations.items()
                        if any(term in info.get('symbol', '').upper() for term in search_terms)
                    ]

                    if gene_ids_from_symbols:
                        mask |= df[gene_id_col].isin(gene_ids_from_symbols)

                    df = df[mask]
                    logger.info(f"✅ [DOWNLOAD-API] Search complete: {len(df)} genes matched")

            # 선택 유전자 필터링 적용
            if selected_gene_set:
                logger.info(f"🎯 [DOWNLOAD-API] Applying selected genes filter: {len(selected_gene_set)} requested")
                df = df[df[gene_id_col].astype(str).isin(selected_gene_set)]
                logger.info(f"✅ [DOWNLOAD-API] Selected genes filter complete: {len(df)} genes matched")

            # gene_symbol 추가
            gene_annotations = load_gene_annotations()
            df['gene_symbol'] = df[gene_id_col].map(lambda x: gene_annotations.get(x, {}).get("symbol", x))

            # 컬럼 순서 재배열: gene_id, gene_symbol, samples...
            df = df.rename(columns={gene_id_col: 'gene_id'})
            column_order = ['gene_id', 'gene_symbol'] + samples
            df = df[column_order]

            # CSV로 변환
            output = io.StringIO()
            df.to_csv(output, index=False)
            output.seek(0)

            # Response 생성
            filename = f"counts_{matrix_type}_{workbench_name}.csv"
            if search_query:
                filename = f"counts_{matrix_type}_{workbench_name}_filtered.csv"
            if selected_gene_set:
                filename = f"counts_{matrix_type}_{workbench_name}_selected_{len(df)}_genes.csv"

            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Cache-Control'] = 'no-cache'

            logger.info(f"✅ [DOWNLOAD-API] Download complete: {len(df)} genes, filename={filename}")

            return response

    except Exception as e:
        logger.error(f"❌ [DOWNLOAD-API] Failed to download counts results: {e}")
        return jsonify({'error': str(e)}), 500


@counts_bp.route('/<int:workbench_id>/deg/significant-tmm-counts', methods=['GET'])
def get_significant_tmm_counts(workbench_id: int):
    """
    Significant 유전자들의 TMM normalized count 데이터 조회

    Query Parameters:
        comparison: 비교 조합 이름 (예: DC_vs_DH)
        tool_name: DEG 도구 이름 (edgeR, DESeq2)
        fdr_cutoff: FDR cutoff (default: 0.05)

    Returns:
        {
            "success": true,
            "gene_count": 500,
            "sample_names": ["DC_1", "DC_2", "DH_1", "DH_2", ...],
            "data": {
                "AT1G01010": [120.5, 98.3, 115.2, ...],
                "AT1G01020": [45.2, 52.1, 48.9, ...],
                ...
            }
        }
    """
    try:
        comparison_name = request.args.get('comparison', '').strip()
        tool_name = request.args.get('tool_name', 'edgeR').strip()
        fdr_cutoff = float(request.args.get('fdr_cutoff', 0.05))

        if not comparison_name:
            return jsonify({'error': 'comparison parameter is required'}), 400

        # 도구 이름 정규화
        tool_name = normalize_tool_name(tool_name)

        logger.info(f"📊 [TMM-COUNTS] Fetching significant TMM counts for {comparison_name} (FDR < {fdr_cutoff})")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']  # quanti 아래의 counts 디렉토리

        logger.info(f"📁 [TMM-COUNTS] DEG directory: {deg_dir}")
        logger.info(f"📁 [TMM-COUNTS] Counts directory: {counts_dir}")

        # 1. DEG 결과에서 significant 유전자 목록 가져오기
        deg_result_file = os.path.join(
            deg_dir,
            tool_name,
            f"genes.counts.matrix.{comparison_name}.{tool_name}.DE_results"
        )

        if not os.path.exists(deg_result_file):
            logger.error(f"❌ [TMM-COUNTS] DEG result file not found: {deg_result_file}")
            return jsonify({'error': 'DEG result file not found'}), 404

        # DEG 결과 로드
        deg_df = pd.read_csv(deg_result_file, sep='\t', index_col=0)

        # Significant 유전자 필터링 (FDR < cutoff)
        if 'FDR' not in deg_df.columns:
            logger.error(f"❌ [TMM-COUNTS] FDR column not found in DEG results")
            return jsonify({'error': 'FDR column not found in DEG results'}), 404

        significant_genes = deg_df[deg_df['FDR'] < fdr_cutoff].index.tolist()

        logger.info(f"✅ [TMM-COUNTS] Found {len(significant_genes)} significant genes (FDR < {fdr_cutoff})")

        if len(significant_genes) == 0:
            logger.warning(f"⚠️ [TMM-COUNTS] No significant genes found")
            return jsonify({
                'success': True,
                'gene_count': 0,
                'sample_names': [],
                'data': {}
            }), 200

        # 2. TMM normalized count 파일 로드
        # 여러 가능한 TMM 파일 경로들
        possible_tmm_paths = [
            # 실제 파이프라인에서 생성하는 파일명
            os.path.join(counts_dir, 'genes.TMM.matrix'),
            # 표준 형식들
            os.path.join(counts_dir, 'TMM', 'genes.counts.matrix.TMM_normalized.txt'),
            os.path.join(counts_dir, 'genes.counts.matrix.TMM_normalized.txt'),
            os.path.join(deg_dir, tool_name, f'genes.counts.matrix.{comparison_name}.{tool_name}.count_matrix.TMM_normalized.txt')
        ]

        logger.info(f"🔍 [TMM-COUNTS] Searching for TMM file in {len(possible_tmm_paths)} possible locations")

        tmm_file = None
        for i, path in enumerate(possible_tmm_paths, 1):
            logger.info(f"   {i}. Checking: {path}")
            logger.info(f"      Exists: {os.path.exists(path)}")
            if os.path.exists(path):
                tmm_file = path
                logger.info(f"✅ [TMM-COUNTS] Found TMM file at: {path}")
                break

        if not tmm_file:
            logger.error(f"❌ [TMM-COUNTS] TMM normalized count file not found")
            logger.error(f"   Tried {len(possible_tmm_paths)} paths:")
            for i, path in enumerate(possible_tmm_paths, 1):
                logger.error(f"   {i}. {path}")
            return jsonify({'error': 'TMM normalized count file not found'}), 404

        logger.info(f"📖 [TMM-COUNTS] Loading TMM counts from: {tmm_file}")

        # TMM count 파일 로드
        tmm_df = pd.read_csv(tmm_file, sep='\t', index_col=0)

        # 3. Significant 유전자들의 TMM count만 추출
        # 존재하는 유전자만 필터링
        available_genes = [gene for gene in significant_genes if gene in tmm_df.index]

        if len(available_genes) < len(significant_genes):
            logger.warning(f"⚠️ [TMM-COUNTS] {len(significant_genes) - len(available_genes)} genes not found in TMM file")

        tmm_subset = tmm_df.loc[available_genes]

        # 4. JSON 형식으로 변환
        sample_names = tmm_subset.columns.tolist()
        tmm_data = {}

        for gene_id in tmm_subset.index:
            tmm_data[gene_id] = tmm_subset.loc[gene_id].tolist()

        logger.info(f"✅ [TMM-COUNTS] Returning {len(tmm_data)} genes x {len(sample_names)} samples")

        return jsonify({
            'success': True,
            'gene_count': len(tmm_data),
            'sample_names': sample_names,
            'data': tmm_data
        }), 200

    except KeyError as e:
        logger.error(f"❌ [TMM-COUNTS] Schema key error: {str(e)}")
        logger.error(f"   Workbench schema keys: {list(workbench_schema.keys()) if 'workbench_schema' in locals() else 'Not loaded'}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Schema configuration error: {str(e)}'}), 500
    except FileNotFoundError as e:
        logger.error(f"❌ [TMM-COUNTS] File not found: {str(e)}")
        return jsonify({'error': f'Required file not found: {str(e)}'}), 404
    except Exception as e:
        logger.error(f"❌ [TMM-COUNTS] Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500
