"""
DEG (Differential Expression Gene) Analysis Results API
EdgeR/DESeq2 결과 조회 API
"""

import os
import re
import time
import pandas as pd
import numpy as np
from flask import Blueprint, jsonify, request, session
from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema, load_gene_annotations
from backend.blueprints.settings import UserSettings
from backend.utils.logger import setup_module_logger
from backend.pipeline.utils.david_go_enrichment import DavidConfig, DavidGOEnrichmentAPI, DavidAPIError
from backend.pipeline.utils.go_enrichment import GProfilerAPI
from backend.pipeline.utils.kegg_pathway import analyze_kegg_pathways
from backend.pipeline.utils.process_wrapper import ProcessWrapper
from backend.pipeline.utils.redis_broker import get_redis_broker
from config.shared_config import SharedConfig

logger = setup_module_logger(__name__, 'INFO')

deg_bp = Blueprint('deg', __name__, url_prefix='/api/workbenches')


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


def find_tmm_matrix_file(workbench_schema: dict, tool_name: str, comparison_name: str = '') -> str | None:
    """
    Find the canonical TMM matrix file used across DEG-related views.
    """
    deg_dir = workbench_schema['deg']
    counts_dir = workbench_schema['quanti']['counts']

    possible_tmm_paths = [
        os.path.join(counts_dir, 'genes.TMM.matrix'),
        os.path.join(counts_dir, 'TMM', 'genes.counts.matrix.TMM_normalized.txt'),
        os.path.join(counts_dir, 'genes.counts.matrix.TMM_normalized.txt'),
        os.path.join(deg_dir, tool_name, f'genes.counts.matrix.{comparison_name}.{tool_name}.count_matrix.TMM_normalized.txt')
    ]

    for path in possible_tmm_paths:
        if os.path.exists(path):
            return path

    return None


def get_low_expression_pass_gene_ids(
    tmm_matrix_file: str,
    min_tmm: float,
    min_sample_pct: float
) -> set[str]:
    """
    Return genes whose TMM values pass the low-expression filter:
    TMM >= min_tmm in at least min_sample_pct percent of samples.
    """
    start_time = time.perf_counter()
    logger.info(
        f"[DEG-LOWEXPR] Loading TMM matrix for low-expression filter: "
        f"file={tmm_matrix_file}, min_tmm={min_tmm}, min_sample_pct={min_sample_pct}"
    )
    tmm_df = pd.read_csv(tmm_matrix_file, sep='\t', index_col=0)
    if tmm_df.empty or len(tmm_df.columns) == 0:
        elapsed = time.perf_counter() - start_time
        logger.warning(f"[DEG-LOWEXPR] TMM matrix is empty or has no sample columns: shape={tmm_df.shape}")
        logger.info(f"[DEG-LOWEXPR] Filter evaluation elapsed time: {elapsed:.3f}s")
        return set()

    numeric_tmm_df = tmm_df.apply(pd.to_numeric, errors='coerce').fillna(0)
    sample_count = len(numeric_tmm_df.columns)
    required_fraction = min_sample_pct / 100.0
    required_sample_count = int(np.ceil(sample_count * required_fraction))
    passing_mask = numeric_tmm_df.ge(min_tmm).sum(axis=1) / sample_count >= required_fraction
    pass_gene_ids = set(numeric_tmm_df.index[passing_mask].tolist())
    elapsed = time.perf_counter() - start_time
    logger.info(
        f"[DEG-LOWEXPR] Filter evaluation complete: total_genes={len(numeric_tmm_df)}, "
        f"samples={sample_count}, required_samples>={required_sample_count}, "
        f"passed={len(pass_gene_ids)}, filtered_out={len(numeric_tmm_df) - len(pass_gene_ids)}, "
        f"elapsed={elapsed:.3f}s"
    )
    return pass_gene_ids


def format_low_expression_value(value: float) -> str:
    text = f"{value:.4f}".rstrip('0').rstrip('.')
    return text.replace('-', 'm').replace('.', 'p') or '0'


def count_replicates_per_group(samples_file: str) -> dict[str, int]:
    group_counts: dict[str, int] = {}

    with open(samples_file, 'r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                group_counts[parts[0]] = group_counts.get(parts[0], 0) + 1

    return group_counts


def send_deg_lowexpr_progress_update(workbench_id: int, progress_data: dict) -> bool:
    """Publish DEG low-expression recalculation progress via Redis/WebSocket."""
    try:
        redis_broker = get_redis_broker()
        if not redis_broker.is_available():
            return False

        return redis_broker.publish_progress(
            workbench_id=workbench_id,
            task_type='deg_lowexpr',
            progress_data=progress_data
        )
    except Exception as e:
        logger.error(f"[DEG-LOWEXPR] Failed to publish progress update: {e}")
        return False


def write_filtered_counts_matrix(
    counts_matrix_file: str,
    pass_gene_ids: set[str],
    output_file: str
) -> int:
    counts_df = pd.read_csv(counts_matrix_file, sep='\t', index_col=0)
    filtered_counts_df = counts_df[counts_df.index.isin(pass_gene_ids)]
    filtered_counts_df.to_csv(output_file, sep='\t')
    logger.info(
        f"[DEG-LOWEXPR] Wrote filtered counts matrix: source_genes={len(counts_df)}, "
        f"retained={len(filtered_counts_df)}, removed={len(counts_df) - len(filtered_counts_df)}, output={output_file}"
    )
    return len(filtered_counts_df)


def run_low_expression_deg_recalculation(
    workbench_id: int,
    workbench_schema: dict,
    comparison_name: str,
    tool_name: str,
    filtered_counts_matrix_file: str,
    output_dir: str,
    samples_file: str,
    worker_id: str
) -> dict:
    workbench_root = workbench_schema['base']
    host_workbench_root = workbench_root.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
    matrix_relative_path = os.path.relpath(filtered_counts_matrix_file, workbench_root).replace('\\', '/')
    samples_relative_path = os.path.relpath(samples_file, workbench_root).replace('\\', '/')
    output_relative_path = os.path.relpath(output_dir, workbench_root).replace('\\', '/')

    group_replicates = count_replicates_per_group(samples_file)
    total_groups = len(group_replicates)
    total_contrasts = (total_groups * (total_groups - 1)) // 2 if total_groups >= 2 else 0
    min_replicates = min(group_replicates.values()) if group_replicates else 0
    dispersion_param = ""
    if min_replicates < 2:
        dispersion_value = "0.1" if min_replicates == 1 else "0.4"
        dispersion_param = f" --dispersion {dispersion_value}"

    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{host_workbench_root}:/data",
        SharedConfig.TRINITY_IMAGE,
        "bash", "-c",
        "cd /data && /usr/local/bin/Analysis/DifferentialExpression/run_DE_analysis.pl "
        f"--matrix {matrix_relative_path} "
        f"--method {tool_name} "
        f"--samples_file {samples_relative_path} "
        f"--output {output_relative_path}{dispersion_param}"
    ]

    logger.info(
        f"[DEG-LOWEXPR] Starting DEG recalculation: tool={tool_name}, worker_id={worker_id}, "
        f"matrix={filtered_counts_matrix_file}, output_dir={output_dir}"
    )
    logger.info(
        f"[DEG-LOWEXPR] Recalculation sample groups: {group_replicates}, "
        f"min_replicates={min_replicates}, total_contrasts={total_contrasts}, "
        f"dispersion_param={'none' if not dispersion_param else dispersion_param.strip()}"
    )

    send_deg_lowexpr_progress_update(workbench_id, {
        'status': 'preparing',
        'stage': 'preparing',
        'message': 'Preparing low-expression DEG recalculation...',
        'comparison_name': comparison_name,
        'tool_name': tool_name,
        'total_contrasts': total_contrasts,
        'completed_contrasts': 0,
        'current_contrast': 0,
        'progress_percent': 5
    })

    progress_state = {
        'current_contrast': 0,
        'completed_contrasts': 0
    }

    def handle_progress_output(line: str) -> None:
        stripped = line.strip()
        logger.info(f"[DEG-LOWEXPR] run_DE_analysis.pl output: {stripped}")
        if not stripped.startswith('CMD:'):
            return

        progress_state['current_contrast'] += 1
        current_contrast = min(progress_state['current_contrast'], total_contrasts) if total_contrasts > 0 else progress_state['current_contrast']
        completed_contrasts = max(0, current_contrast - 1)
        progress_state['completed_contrasts'] = completed_contrasts

        progress_percent = 5
        if total_contrasts > 0:
            progress_percent = 5 + int(90 * (completed_contrasts / total_contrasts))

        send_deg_lowexpr_progress_update(workbench_id, {
            'status': 'running',
            'stage': 'contrasts',
            'message': f'Running DEG contrast {current_contrast} of {total_contrasts}',
            'comparison_name': comparison_name,
            'tool_name': tool_name,
            'total_contrasts': total_contrasts,
            'completed_contrasts': completed_contrasts,
            'current_contrast': current_contrast,
            'progress_percent': min(progress_percent, 95)
        })

    wrapper = ProcessWrapper(worker_id)
    result = wrapper.run_command(docker_cmd, progress_callback=handle_progress_output)
    logger.info(
        f"[DEG-LOWEXPR] Recalculation completed: success={result.get('success', False)}, "
        f"return_code={result.get('return_code', 'n/a')}"
    )
    if not result.get('success', False):
        logger.error(
            f"[DEG-LOWEXPR] Recalculation failed: "
            f"stderr={str(result.get('stderr', ''))[:1000]}, error={str(result.get('error', ''))[:1000]}"
        )
        send_deg_lowexpr_progress_update(workbench_id, {
            'status': 'failed',
            'stage': 'failed',
            'message': 'Low-expression DEG recalculation failed.',
            'comparison_name': comparison_name,
            'tool_name': tool_name,
            'total_contrasts': total_contrasts,
            'completed_contrasts': progress_state['completed_contrasts'],
            'current_contrast': progress_state['current_contrast'],
            'progress_percent': 0
        })
    else:
        completed_contrasts = total_contrasts if total_contrasts > 0 else progress_state['completed_contrasts']
        send_deg_lowexpr_progress_update(workbench_id, {
            'status': 'finalizing',
            'stage': 'finalizing',
            'message': 'Finalizing DEG result files...',
            'comparison_name': comparison_name,
            'tool_name': tool_name,
            'total_contrasts': total_contrasts,
            'completed_contrasts': completed_contrasts,
            'current_contrast': total_contrasts,
            'progress_percent': 98
        })
        send_deg_lowexpr_progress_update(workbench_id, {
            'status': 'completed',
            'stage': 'completed',
            'message': 'Low-expression DEG recalculation completed.',
            'comparison_name': comparison_name,
            'tool_name': tool_name,
            'total_contrasts': total_contrasts,
            'completed_contrasts': completed_contrasts,
            'current_contrast': total_contrasts,
            'progress_percent': 100
        })
    return result


def get_low_expression_result_paths(
    workbench_schema: dict,
    comparison_name: str,
    tool_name: str,
    min_tmm: float,
    min_sample_pct: float
) -> dict[str, str]:
    deg_dir = workbench_schema['deg']
    counts_dir = workbench_schema['quanti']['counts']
    cache_suffix = f"tmm_{format_low_expression_value(min_tmm)}_pct_{format_low_expression_value(min_sample_pct)}"
    cache_dir = os.path.join(deg_dir, tool_name, 'low_expr_cache', cache_suffix)
    matrix_basename = f"genes.counts.matrix.lowexpr.{cache_suffix}"
    filtered_counts_matrix_file = os.path.join(cache_dir, matrix_basename)
    result_filename = f"{matrix_basename}.{comparison_name}.{tool_name}.DE_results"

    return {
        'cache_dir': cache_dir,
        'counts_matrix_file': os.path.join(counts_dir, 'genes.counts.matrix'),
        'filtered_counts_matrix_file': filtered_counts_matrix_file,
        'result_file': os.path.join(cache_dir, result_filename)
    }


def ensure_low_expression_deg_result_file(
    workbench_schema: dict,
    comparison_name: str,
    tool_name: str,
    min_tmm: float,
    min_sample_pct: float,
    workbench_id: int
) -> dict:
    logger.info(
        f"[DEG-LOWEXPR] Ensuring cached DEG result: comparison={comparison_name}, tool={tool_name}, "
        f"min_tmm={min_tmm}, min_sample_pct={min_sample_pct}"
    )
    paths = get_low_expression_result_paths(
        workbench_schema=workbench_schema,
        comparison_name=comparison_name,
        tool_name=tool_name,
        min_tmm=min_tmm,
        min_sample_pct=min_sample_pct
    )

    tmm_matrix_file = find_tmm_matrix_file(workbench_schema, tool_name, comparison_name)
    if not tmm_matrix_file:
        raise FileNotFoundError('TMM matrix file not found for low-expression recalculation')
    logger.info(f"[DEG-LOWEXPR] Using TMM matrix: {tmm_matrix_file}")

    samples_file = os.path.join(workbench_schema['quanti']['samples'], 'samples.txt')
    if not os.path.exists(samples_file):
        raise FileNotFoundError('Samples file not found for low-expression recalculation')
    logger.info(f"[DEG-LOWEXPR] Using samples file: {samples_file}")

    pass_gene_ids = get_low_expression_pass_gene_ids(tmm_matrix_file, min_tmm, min_sample_pct)
    if len(pass_gene_ids) == 0:
        logger.warning(
            f"[DEG-LOWEXPR] No genes passed low-expression filter for comparison={comparison_name}, tool={tool_name}"
        )
        return {
            'result_file': paths['result_file'],
            'gene_count': 0,
            'generated': False
        }

    os.makedirs(paths['cache_dir'], exist_ok=True)
    logger.info(
        f"[DEG-LOWEXPR] Cache prepared: cache_dir={paths['cache_dir']}, "
        f"filtered_counts={paths['filtered_counts_matrix_file']}, result_file={paths['result_file']}"
    )

    if not os.path.exists(paths['filtered_counts_matrix_file']):
        retained_gene_count = write_filtered_counts_matrix(
            counts_matrix_file=paths['counts_matrix_file'],
            pass_gene_ids=pass_gene_ids,
            output_file=paths['filtered_counts_matrix_file']
        )
        logger.info(f"[DEG-LOWEXPR] Created filtered counts matrix cache with {retained_gene_count} genes")
    else:
        logger.info(f"[DEG-LOWEXPR] Reusing existing filtered counts matrix cache: {paths['filtered_counts_matrix_file']}")

    if not os.path.exists(paths['result_file']):
        logger.info(f"[DEG-LOWEXPR] Cache miss for DEG result; recalculating cache_key={os.path.basename(paths['cache_dir'])}")
        recalc_result = run_low_expression_deg_recalculation(
            workbench_id=workbench_id,
            workbench_schema=workbench_schema,
            comparison_name=comparison_name,
            tool_name=tool_name,
            filtered_counts_matrix_file=paths['filtered_counts_matrix_file'],
            output_dir=paths['cache_dir'],
            samples_file=samples_file,
            worker_id=f"deg_lowexpr_{workbench_id}"
        )
        if not recalc_result.get('success', False):
            raise RuntimeError(recalc_result.get('stderr') or recalc_result.get('error') or 'Low-expression DEG recalculation failed')
    else:
        logger.info(f"[DEG-LOWEXPR] Cache hit for DEG result: {paths['result_file']}")

    if not os.path.exists(paths['result_file']):
        raise FileNotFoundError(f"Low-expression DEG result file not found after recalculation: {paths['result_file']}")

    logger.info(
        f"[DEG-LOWEXPR] Result ready: retained_genes={len(pass_gene_ids)}, result_file={paths['result_file']}"
    )

    return {
        'result_file': paths['result_file'],
        'gene_count': len(pass_gene_ids),
        'generated': True
    }


def parse_deg_result_file(file_path: str, limit: int = None, offset: int = 0, search: str = None, filter_type: str = None,
                          filters: dict = None, sort_by: str = None, sort_order: str = 'asc',
                          low_expr_pass_gene_ids: set[str] | None = None):
    """
    EdgeR/DESeq2 결과 파일 파싱

    Args:
        file_path: DE 결과 파일 경로
        limit: 최대 개수 (페이지네이션)
        offset: 시작 인덱스
        search: 검색 키워드 (Gene ID 또는 Gene Symbol)
        filter_type: 필터 타입 (up, down, all)
        filters: 컬럼별 필터 조건 (예: {'logFC': {'operator': 'gt', 'value': '1'}})
        sort_by: 정렬할 컬럼 이름
        sort_order: 정렬 순서 ('asc' 또는 'desc')

    Returns:
        dict: {
            'data': 파싱된 데이터 레코드,
            'total': 전체 개수,
            'columns': 컬럼 이름 목록
        }
    """
    try:
        # TSV 파일 읽기 (첫 번째 컬럼을 index로 읽음 - Gene ID)
        logger.info(
            f"[DEG-PARSE] Parsing result file: file={file_path}, limit={limit}, offset={offset}, "
            f"search={'yes' if search else 'no'}, filter_type={filter_type or 'all'}, "
            f"custom_filters={len(filters) if filters else 0}, sort_by={sort_by or 'none'}"
        )
        df = pd.read_csv(file_path, sep='\t', index_col=0)
        initial_gene_count = len(df)
        logger.info(f"[DEG-PARSE] Raw rows loaded: {initial_gene_count}")

        # index를 'GeneID' 컬럼으로 변환
        df.index.name = 'GeneID'
        df = df.reset_index()

        # 컬럼명 정리
        df.columns = df.columns.str.strip()

        # GeneSymbol 및 GeneDescription 컬럼 추가 (workbench.py와 동일한 로직)
        gene_annotations = load_gene_annotations()
        df.insert(1, 'GeneSymbol', df['GeneID'].map(lambda x: gene_annotations.get(x, {}).get("symbol", x)))
        df.insert(2, 'GeneDescription', df['GeneID'].map(lambda x: gene_annotations.get(x, {}).get("description", "No description available")))

        # filter_type에 따른 필터링
        if low_expr_pass_gene_ids is not None:
            before_low_expr = len(df)
            df = df[df['GeneID'].isin(low_expr_pass_gene_ids)]
            logger.info(
                f"[DEG-PARSE] Applied low-expression pass list: before={before_low_expr}, "
                f"after={len(df)}, removed={before_low_expr - len(df)}"
            )

        if filter_type == 'up':
            # Up-regulated genes만 (logFC > 0)
            if 'logFC' in df.columns:
                before_up = len(df)
                df = df[df['logFC'] > 0]
                logger.info(
                    f"[DEG-PARSE] Applied 'up' filter: before={before_up}, after={len(df)}, removed={before_up - len(df)}"
                )
        elif filter_type == 'down':
            # Down-regulated genes만 (logFC < 0)
            if 'logFC' in df.columns:
                before_down = len(df)
                df = df[df['logFC'] < 0]
                logger.info(
                    f"[DEG-PARSE] Applied 'down' filter: before={before_down}, after={len(df)}, removed={before_down - len(df)}"
                )
        elif filter_type == 'significant':
            # Significant genes만 (FDR < 0.05)
            if 'FDR' in df.columns:
                before_sig = len(df)
                df = df[df['FDR'] < 0.05]
                logger.info(
                    f"[DEG-PARSE] Applied 'significant' filter: before={before_sig}, after={len(df)}, removed={before_sig - len(df)}"
                )

        # 검색 필터 적용 (workbench.py와 동일한 로직)
        if search:
            # 검색어 파싱 (쉼표, 공백, 탭, 줄바꿈으로 구분)
            search_terms = re.split(r'[,\s\t\n]+', search)
            search_terms = [term.strip().upper() for term in search_terms if term.strip()]

            logger.debug(f"🔍 [DEG-SEARCH] Parsed {len(search_terms)} search terms")

            if search_terms:
                # gene_symbol_map 미리 로드 (검색용)
                gene_annotations = load_gene_annotations()

                # 1. gene_id로 부분 일치 검색 (대소문자 구분 없이)
                mask = pd.Series([False] * len(df), index=df.index)
                for term in search_terms:
                    mask |= df['GeneID'].str.upper().str.contains(term, regex=False, na=False)
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
                    symbol_mask = df['GeneID'].isin(gene_ids_from_symbols)
                    mask |= symbol_mask
                    matched_by_symbol = symbol_mask.sum()

                # 필터링 적용
                before_search = len(df)
                df = df[mask]

                logger.info(
                    f"[DEG-PARSE] Applied search: before={before_search}, after={len(df)}, "
                    f"removed={before_search - len(df)}, matched_by_id={matched_by_id}, matched_by_symbol={matched_by_symbol}"
                )

                if len(df) == 0:
                    logger.debug(f"⚠️ [DEG-SEARCH] No genes matched search query")
            else:
                logger.debug(f"ℹ️ [DEG-SEARCH] Empty search terms after parsing")

        # 사용자 정의 필터 적용 (전체 데이터에 대해)
        if filters:
            logger.info(f"[DEG-PARSE] Applying {len(filters)} user-defined filters")
            for col_name, filter_config in filters.items():
                if col_name in df.columns and filter_config.get('operator') and filter_config.get('value'):
                    operator = filter_config['operator']
                    try:
                        filter_value = float(filter_config['value'])
                        col_values = pd.to_numeric(df[col_name], errors='coerce')
                        before_custom_filter = len(df)

                        if operator == 'gt':
                            df = df[col_values > filter_value]
                        elif operator == 'gte':
                            df = df[col_values >= filter_value]
                        elif operator == 'lt':
                            df = df[col_values < filter_value]
                        elif operator == 'lte':
                            df = df[col_values <= filter_value]
                        elif operator == 'eq':
                            df = df[col_values == filter_value]

                        logger.info(
                            f"[DEG-PARSE] Applied custom filter {col_name} {operator} {filter_value}: "
                            f"before={before_custom_filter}, after={len(df)}, removed={before_custom_filter - len(df)}"
                        )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"⚠️ [DEG-FILTER] Failed to apply filter on {col_name}: {str(e)}")

        # 정렬 적용 (전체 데이터에 대해)
        if sort_by and sort_by in df.columns:
            ascending = (sort_order == 'asc')
            df = df.sort_values(by=sort_by, ascending=ascending)
            logger.debug(f"📊 [DEG-SORT] Sorted by {sort_by} ({sort_order}): {len(df)} genes")

        total_count = len(df)
        logger.info(
            f"[DEG-PARSE] Final count before pagination: total={total_count}, "
            f"offset={offset}, limit={limit if limit is not None else 'all'}"
        )

        # 페이지네이션 적용
        if limit is not None:
            df = df.iloc[offset:offset + limit]
        logger.info(f"[DEG-PARSE] Returning rows after pagination: returned={len(df)}")

        # 데이터 변환
        records = df.to_dict('records')
        columns = df.columns.tolist()

        return {
            'data': records,
            'total': total_count,
            'columns': columns
        }

    except Exception as e:
        logger.error(f"❌ [DEG] Failed to parse DEG result file: {file_path}")
        logger.error(f"   └─ Error: {str(e)}")
        raise


@deg_bp.route('/<int:workbench_id>/deg/progress', methods=['GET'])
def get_deg_progress(workbench_id: int):
    """
    DEG 파이프라인 진행 상태 조회

    Returns:
        {
            "status": "pending" | "running" | "completed" | "failed" | "not_started" | "insufficient_replicates",
            "tool_name": "edgeR" | "DESeq2" | null,
            "has_insufficient_replicates": boolean,
            "sample_structure": {"RH50": 1, "RH90": 1}
        }
    """
    try:
        # pipeline_job_steps에서 deg 단계 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, tool_name
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'deg'
                ORDER BY id DESC
                LIMIT 1
            """, (workbench_id,))
            deg_step = cursor.fetchone()

            # Replicate 정보 조회 (vizr_pipeline_samples에서)
            cursor.execute("""
                SELECT samples
                FROM vizr_pipeline_samples
                WHERE workbench_id = ?
            """, (workbench_id,))
            samples_row = cursor.fetchone()

        # Replicate 구조 분석
        sample_structure = {}
        has_insufficient_replicates = False

        if samples_row and samples_row['samples']:
            try:
                import json
                samples_data = json.loads(samples_row['samples'])

                # 그룹별 샘플 개수 세기
                for sample in samples_data:
                    group_name = sample.get('groupName', sample.get('group_name', sample.get('group', 'Unknown')))
                    sample_structure[group_name] = sample_structure.get(group_name, 0) + 1

                # DESeq2의 경우 replicate 체크
                if deg_step and deg_step['tool_name'] and deg_step['tool_name'].lower() == 'deseq2':
                    # 어느 한 그룹이라도 replicate가 2개 미만이면 insufficient
                    has_insufficient_replicates = any(count < 2 for count in sample_structure.values())

            except Exception as e:
                logger.warning(f"⚠️ [DEG-PROGRESS] Failed to parse samples: {str(e)}")

        if not deg_step:
            return jsonify({
                'status': 'not_started',
                'tool_name': None,
                'has_insufficient_replicates': has_insufficient_replicates,
                'sample_structure': sample_structure
            }), 200

        # sqlite3.Row 객체를 dict로 변환하여 안전하게 접근
        tool_name = deg_step['tool_name'] if deg_step['tool_name'] else None
        status = deg_step['status']

        # DESeq2이고 completed 상태인데 결과 파일이 없으면 insufficient_replicates로 판단
        if tool_name and tool_name.lower() == 'deseq2' and status == 'completed':
            try:
                # 워크벤치 정보 조회 (workbench name과 user_id 가져오기)
                with database.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, user_id FROM vizr_workbench WHERE id = ?", (workbench_id,))
                    wb_row = cursor.fetchone()

                if not wb_row:
                    logger.warning(f"⚠️ [DEG-PROGRESS] Workbench {workbench_id} not found in database")
                    raise Exception(f"Workbench {workbench_id} not found")

                # 워크벤치 스키마에서 DESeq2 output 디렉토리 가져오기
                workbench_schema = get_workbench_schema(wb_row['name'], wb_row['user_id'])
                deg_dir = workbench_schema['deg']
                deseq2_dir = os.path.join(deg_dir, 'DESeq2')

                # 주요 결과 파일 경로 생성
                critical_files = {
                    'DESeq2.DE_results': None,
                    'DESeq2.count_matrix.RData': None
                }

                # 파일 존재 여부 체크
                all_files_missing = True
                if os.path.exists(deseq2_dir):
                    for filename in os.listdir(deseq2_dir):
                        for cf_key in critical_files.keys():
                            if cf_key in filename:
                                critical_files[cf_key] = os.path.join(deseq2_dir, filename)
                                all_files_missing = False

                # 모든 주요 파일이 없으면 replicate 부족으로 판단
                if all_files_missing:
                    has_insufficient_replicates = True
                    status = 'insufficient_replicates'

            except Exception as e:
                logger.warning(f"⚠️ [DEG-PROGRESS] Failed to check DESeq2 output files: {str(e)}")

        return jsonify({
            'status': status,
            'tool_name': tool_name,
            'has_insufficient_replicates': has_insufficient_replicates,
            'sample_structure': sample_structure
        }), 200

    except Exception as e:
        logger.error(f"❌ [DEG] Failed to fetch DEG progress: {str(e)}")
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/comparisons', methods=['GET'])
def get_deg_comparisons(workbench_id: int):
    """
    사용 가능한 DEG comparison 목록 조회

    Returns:
        {
            "comparisons": [
                {"name": "DC_vs_DH", "file_count": 3},
                {"name": "DC_vs_LC", "file_count": 3},
                ...
            ],
            "total": 6
        }
    """
    try:
        logger.debug(f"🔍 [DEG] Fetching DEG comparisons for workbench {workbench_id}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']

        # EdgeR 결과 디렉토리 확인
        edger_dir = os.path.join(deg_dir, 'edgeR')

        comparisons = []

        if os.path.exists(edger_dir):
            # EdgeR 결과 파일 스캔
            for filename in os.listdir(edger_dir):
                if filename.endswith('.edgeR.DE_results'):
                    # 파일명 파싱: genes.counts.matrix.DC_vs_DH.edgeR.DE_results
                    parts = filename.replace('genes.counts.matrix.', '').replace('.edgeR.DE_results', '')
                    comparison_name = parts

                    # 관련 파일 개수 확인
                    related_files = [
                        f for f in os.listdir(edger_dir)
                        if comparison_name in f
                    ]

                    comparisons.append({
                        'name': comparison_name,
                        'tool_name': 'edgeR',
                        'file_count': len(related_files),
                        'de_result_file': filename
                    })

        # DESeq2 결과 확인 (향후 지원)
        deseq2_dir = os.path.join(deg_dir, 'DESeq2')
        if os.path.exists(deseq2_dir):
            for filename in os.listdir(deseq2_dir):
                if filename.endswith('.DESeq2.DE_results'):
                    parts = filename.replace('genes.counts.matrix.', '').replace('.DESeq2.DE_results', '')
                    comparison_name = parts

                    related_files = [
                        f for f in os.listdir(deseq2_dir)
                        if comparison_name in f
                    ]

                    comparisons.append({
                        'name': comparison_name,
                        'tool_name': 'DESeq2',
                        'file_count': len(related_files),
                        'de_result_file': filename
                    })

        logger.debug(f"✅ [DEG] Found {len(comparisons)} comparisons")

        # vizr_pipeline_samples의 그룹 순서 기반으로 comparisons 정렬
        # 사용자가 워크벤치 생성 시 입력한 샘플 매핑 순서를 따름
        try:
            with database.get_db_connection() as conn:
                row = conn.execute(
                    "SELECT samples FROM vizr_pipeline_samples WHERE workbench_id = ? LIMIT 1",
                    (workbench_id,)
                ).fetchone()

            if row and row['samples']:
                import json as _json
                samples_data = _json.loads(row['samples'])
                seen = set()
                group_order = []
                for s in samples_data:
                    g = s.get('groupName', '')
                    if g and g not in seen:
                        group_order.append(g)
                        seen.add(g)

                def sort_key(c):
                    # "A_vs_B" → condition1=A, condition2=B
                    # groupName 자체에 _가 포함될 수 있으므로
                    # group_order에서 직접 매칭하는 방식 사용
                    name = c['name']
                    cond1_idx = len(group_order)
                    cond2_idx = len(group_order)
                    for idx, g in enumerate(group_order):
                        # "GroupA_vs_GroupB" → startswith(GroupA + '_vs_')
                        if name.startswith(g + '_vs_'):
                            cond1_idx = idx
                            remainder = name[len(g) + 4:]  # 4 = len('_vs_')
                            for idx2, g2 in enumerate(group_order):
                                if remainder == g2:
                                    cond2_idx = idx2
                                    break
                            break
                    return (cond1_idx, cond2_idx, name)

                comparisons.sort(key=sort_key)
                logger.debug(f"✅ [DEG] Sorted comparisons by vizr_pipeline_samples group order: {group_order}")
        except Exception as e:
            logger.warning(f"⚠️ [DEG] Failed to sort comparisons by group order, falling back to name sort: {e}")
            comparisons.sort(key=lambda c: c['name'])

        return jsonify({
            'comparisons': comparisons,
            'total': len(comparisons)
        }), 200

    except Exception as e:
        logger.error(f"❌ [DEG] Failed to fetch comparisons: {str(e)}")
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/results/<comparison_name>', methods=['GET'])
def get_deg_result(workbench_id: int, comparison_name: str):
    """
    특정 comparison의 DEG 결과 조회

    Query Parameters:
        - tool_name: edgeR 또는 DESeq2 (default: edgeR)
        - page: 페이지 번호 (default: 1)
        - limit: 페이지당 항목 수 (default: 1000)
        - search: 검색 키워드 (Gene ID 또는 Symbol, 쉼표로 구분)
        - data_type: matrix, ma_plot, volcano_plot (default: matrix)
        - filter_type: up, down, significant, all (default: all)
        - filters: JSON string of column filters (e.g., {"logFC": {"operator": "gt", "value": "1"}})
        - sort_by: Column name to sort by
        - sort_order: asc or desc (default: asc)

    Returns:
        {
            "comparison": "DC_vs_DH",
            "tool_name": "edgeR",
            "data": [...],
            "total": 27416,
            "page": 1,
            "limit": 1000,
            "columns": [...],
            "filter_type": "up"
        }
    """
    try:
        tool_name = request.args.get('tool_name', 'edgeR')
        # 도구 이름 정규화 (대소문자 관계없이 올바른 형식으로 변환)
        tool_name = normalize_tool_name(tool_name)

        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 1000))
        search = request.args.get('search', None)
        data_type = request.args.get('data_type', 'matrix')
        filter_type = request.args.get('filter_type', 'all')  # up, down, all
        low_expr_enabled = request.args.get('low_expr_enabled', 'false').lower() == 'true'
        low_expr_min_tmm = float(request.args.get('low_expr_min_tmm', 1))
        low_expr_min_sample_pct = float(request.args.get('low_expr_min_sample_pct', 25))

        # 새로운 필터/정렬 파라미터
        filters_json = request.args.get('filters', None)
        sort_by = request.args.get('sort_by', None)
        sort_order = request.args.get('sort_order', 'asc')

        # JSON 파싱
        filters = None
        if filters_json:
            try:
                import json
                filters = json.loads(filters_json)
                logger.debug(f"🔧 [DEG] Received filters: {filters}")
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ [DEG] Failed to parse filters JSON: {str(e)}")

        offset = (page - 1) * limit

        # 샘플 정보 파싱 (예: DC_vs_DH → DC vs DH)
        samples = comparison_name.replace('_vs_', ' vs ') if '_vs_' in comparison_name else comparison_name

        # Tree 형태 로그 출력
        logger.info(f"📊 [DEG] Request Details:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"├─ Comparison: {samples}")
        logger.info(f"├─ Tool: {tool_name}")
        logger.info(f"├─ Data Type: {data_type}")
        logger.info(f"├─ Filter Type: {filter_type}")
        logger.info(f"├─ Page: {page} (limit: {limit})")

        if search:
            search_display = f"'{search[:50]}...'" if len(search) > 50 else f"'{search}'"
            logger.info(f"├─ Search: {search_display}")
        else:
            logger.info(f"├─ Search: None")

        if sort_by:
            logger.info(f"├─ Sort: {sort_by} ({sort_order})")
        else:
            logger.info(f"├─ Sort: None")

        if filters:
            logger.info(f"└─ Custom Filters ({len(filters)}):")
            filter_items = list(filters.items())
            for idx, (col_name, filter_config) in enumerate(filter_items):
                operator = filter_config.get('operator', 'N/A')
                value = filter_config.get('value', 'N/A')

                # 연산자 기호 변환
                op_symbols = {
                    'gt': '>',
                    'gte': '>=',
                    'lt': '<',
                    'lte': '<=',
                    'eq': '='
                }
                op_symbol = op_symbols.get(operator, operator)

                is_last = (idx == len(filter_items) - 1)
                prefix = "   └─" if is_last else "   ├─"
                logger.info(f"{prefix} {col_name} {op_symbol} {value}")
        else:
            logger.info(f"└─ Custom Filters: None")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']

        # 결과 파일 경로 구성
        tool_name_dir = os.path.join(deg_dir, tool_name)
        result_filename = f"genes.counts.matrix.{comparison_name}.{tool_name}.DE_results"
        result_file = os.path.join(tool_name_dir, result_filename)
        low_expr_gene_count = None

        if low_expr_enabled:
            logger.info(f"[DEG] Low expression recalculation: TMM >= {low_expr_min_tmm} in >= {low_expr_min_sample_pct}% samples")
            low_expr_result = ensure_low_expression_deg_result_file(
                workbench_schema=workbench_schema,
                comparison_name=comparison_name,
                tool_name=tool_name,
                min_tmm=low_expr_min_tmm,
                min_sample_pct=low_expr_min_sample_pct,
                workbench_id=workbench_id
            )
            low_expr_gene_count = low_expr_result['gene_count']
            logger.info(
                f"[DEG] Low expression result prepared: retained_genes={low_expr_gene_count}, "
                f"generated={low_expr_result['generated']}, result_file={low_expr_result['result_file']}"
            )

            if low_expr_gene_count == 0:
                logger.warning("[DEG] No genes passed low-expression recalculation filter; returning empty response")
                return jsonify({
                    'comparison': comparison_name,
                    'tool_name': tool_name,
                    'data': [],
                    'total': 0,
                    'page': page,
                    'limit': limit,
                    'columns': [],
                    'filter_type': filter_type,
                    'low_expression_filter': {
                        'enabled': True,
                        'min_tmm': low_expr_min_tmm,
                        'min_sample_pct': low_expr_min_sample_pct,
                        'retained_genes': 0,
                        'mode': 'recalculated'
                    }
                }), 200

            result_file = low_expr_result['result_file']
        else:
            logger.info(f"[DEG] Low expression recalculation: Off")

        logger.info(f"[DEG] Using DEG result file: {result_file}")

        if not os.path.exists(result_file):
            logger.error(f"❌ [DEG] Result file not found: {result_file}")
            return jsonify({'error': f'DEG result file not found for {comparison_name}'}), 404

        # 파일 파싱
        if data_type == 'matrix':
            # Matrix 데이터 (페이지네이션 적용)
            parsed_data = parse_deg_result_file(
                result_file,
                limit=limit,
                offset=offset,
                search=search,
                filter_type=filter_type,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order
            )

            response = {
                'comparison': comparison_name,
                'tool_name': tool_name,
                'data': parsed_data['data'],
                'total': parsed_data['total'],
                'page': page,
                'limit': limit,
                'columns': parsed_data['columns'],
                'filter_type': filter_type,
                'low_expression_filter': {
                    'enabled': low_expr_enabled,
                    'min_tmm': low_expr_min_tmm,
                    'min_sample_pct': low_expr_min_sample_pct,
                    'retained_genes': low_expr_gene_count,
                    'mode': 'recalculated' if low_expr_enabled else 'off'
                }
            }
            logger.info(
                f"[DEG] Matrix response ready: total={parsed_data['total']}, returned={len(parsed_data['data'])}, "
                f"columns={len(parsed_data['columns'])}, low_expr_enabled={low_expr_enabled}"
            )

        elif data_type == 'ma_plot':
            # MA Plot 데이터 (다운샘플링 적용)
            parsed_data = parse_deg_result_file(result_file, limit=None, offset=0, search=None)
            df = pd.DataFrame(parsed_data['data'])

            # MA Plot: x=logCPM, y=logFC
            ma_plot_data = []
            total_significant = 0

            if 'logCPM' in df.columns and 'logFC' in df.columns:
                # FDR 컬럼으로 significant/non-significant 분리
                if 'FDR' in df.columns:
                    df['significant'] = df['FDR'] < 0.05
                else:
                    df['significant'] = False

                df_significant = df[df['significant'] == True]
                df_non_significant = df[df['significant'] == False]

                total_significant = len(df_significant)

                # Non-significant 다운샘플링 (우선순위: |logFC| 큰 것 → p-value 낮은 것)
                max_non_significant = 3000

                if len(df_non_significant) > max_non_significant:
                    # 1차: |logFC| 절댓값 기준 내림차순
                    # 2차: PValue 오름차순 (p-value가 낮을수록 우선)
                    df_non_significant = df_non_significant.assign(
                        abs_logFC=df_non_significant['logFC'].abs()
                    ).sort_values(
                        by=['abs_logFC', 'PValue'],
                        ascending=[False, True]
                    ).head(max_non_significant).drop(columns=['abs_logFC'])

                # Significant + Downsampled non-significant 합치기
                df_combined = pd.concat([df_significant, df_non_significant])

                for _, row in df_combined.iterrows():
                    gene_id = row['GeneID'] if 'GeneID' in row.index else row.iloc[0]
                    gene_symbol = row['GeneSymbol'] if 'GeneSymbol' in row.index else gene_id
                    fdr_value = float(row['FDR']) if 'FDR' in row.index and pd.notna(row['FDR']) else 1.0
                    # FDR 값을 기준으로 significant 재계산 (DataFrame 컬럼 값 사용 안함)
                    is_significant = fdr_value < 0.05

                    ma_plot_data.append({
                        'gene_id': gene_id,
                        'gene_symbol': gene_symbol,
                        'logCPM': float(row['logCPM']) if pd.notna(row['logCPM']) else 0,
                        'logFC': float(row['logFC']) if pd.notna(row['logFC']) else 0,
                        'fdr': fdr_value,
                        'significant': is_significant
                    })

            response = {
                'comparison': comparison_name,
                'tool_name': tool_name,
                'data_type': 'ma_plot',
                'data': ma_plot_data,
                'total': len(df),  # 원본 전체 개수
                'returned': len(ma_plot_data),  # 실제 반환된 개수
                'total_significant': total_significant  # Significant genes 총 개수 (페이지네이션용)
            }
            logger.info(
                f"[DEG] MA plot response ready: total={len(df)}, returned={len(ma_plot_data)}, "
                f"significant={total_significant}, low_expr_enabled={low_expr_enabled}"
            )

        elif data_type == 'volcano_plot':
            # Volcano Plot 데이터 (다운샘플링 적용)
            parsed_data = parse_deg_result_file(result_file, limit=None, offset=0, search=None)
            df = pd.DataFrame(parsed_data['data'])

            # Volcano Plot: x=logFC, y=-log10(PValue)
            volcano_plot_data = []
            if 'logFC' in df.columns and 'PValue' in df.columns:
                # FDR 컬럼으로 significant/non-significant 분리
                if 'FDR' in df.columns:
                    df['significant'] = df['FDR'] < 0.05
                else:
                    df['significant'] = False

                df_significant = df[df['significant'] == True]
                df_non_significant = df[df['significant'] == False]

                # Non-significant 다운샘플링 (우선순위: |logFC| 큰 것 → p-value 낮은 것)
                max_non_significant = 3000

                if len(df_non_significant) > max_non_significant:
                    # 1차: |logFC| 절댓값 기준 내림차순
                    # 2차: PValue 오름차순 (p-value가 낮을수록 우선)
                    df_non_significant = df_non_significant.assign(
                        abs_logFC=df_non_significant['logFC'].abs()
                    ).sort_values(
                        by=['abs_logFC', 'PValue'],
                        ascending=[False, True]
                    ).head(max_non_significant).drop(columns=['abs_logFC'])

                # Significant + Downsampled non-significant 합치기
                df_combined = pd.concat([df_significant, df_non_significant])

                for _, row in df_combined.iterrows():
                    gene_id = row['GeneID'] if 'GeneID' in row.index else row.iloc[0]
                    gene_symbol = row['GeneSymbol'] if 'GeneSymbol' in row.index else gene_id
                    p_value = float(row['PValue']) if pd.notna(row['PValue']) and row['PValue'] > 0 else 1e-300
                    neg_log10_pval = -np.log10(p_value)
                    fdr_value = float(row['FDR']) if 'FDR' in row.index and pd.notna(row['FDR']) else 1.0

                    volcano_plot_data.append({
                        'gene_id': gene_id,
                        'gene_symbol': gene_symbol,
                        'logFC': float(row['logFC']) if pd.notna(row['logFC']) else 0,
                        'neg_log10_pval': float(neg_log10_pval),
                        'fdr': fdr_value,
                        # FDR 값을 기준으로 significant 재계산 (DataFrame 컬럼 값 사용 안함)
                        'significant': fdr_value < 0.05
                    })

            response = {
                'comparison': comparison_name,
                'tool_name': tool_name,
                'data_type': 'volcano_plot',
                'data': volcano_plot_data,
                'total': len(df),  # 원본 전체 개수
                'returned': len(volcano_plot_data)  # 실제 반환된 개수
            }
            logger.info(
                f"[DEG] Volcano response ready: total={len(df)}, returned={len(volcano_plot_data)}, "
                f"low_expr_enabled={low_expr_enabled}"
            )

        else:
            return jsonify({'error': f'Invalid data_type: {data_type}'}), 400

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ [DEG] Failed to fetch DEG results: {str(e)}")
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg-results/download', methods=['GET'])
def download_deg_results(workbench_id):
    """
    DEG 결과 전체 다운로드 API

    Query Parameters:
        comparison: 비교 조합 이름 (예: DC_vs_DH)
        tool_name: DEG 도구 이름 (edgeR, DESeq2)
        filter_type: 필터 타입 (up, down, all) - optional
        search: 검색어 (optional)

    Response:
        CSV file with all DEG results
    """
    from flask import make_response
    import io

    logger.info(f"📥 [DEG-DOWNLOAD] Starting download for workbench {workbench_id}")

    # Query parameters
    comparison_name = request.args.get('comparison', '').strip()
    tool_name = request.args.get('tool_name', '').strip()
    filter_type = request.args.get('filter_type', 'all').strip().lower()
    search_query = request.args.get('search', '').strip()
    low_expr_enabled = request.args.get('low_expr_enabled', 'false').lower() == 'true'
    low_expr_min_tmm = float(request.args.get('low_expr_min_tmm', 1))
    low_expr_min_sample_pct = float(request.args.get('low_expr_min_sample_pct', 25))

    if not comparison_name or not tool_name:
        logger.warning(f"⚠️ [DEG-DOWNLOAD] Missing required parameters")
        return jsonify({'error': 'comparison and tool_name are required'}), 400

    # 도구 이름 정규화
    tool_name = normalize_tool_name(tool_name)

    logger.info(
        f"📊 [DEG-DOWNLOAD] Request params: comparison={comparison_name}, tool={tool_name}, "
        f"filter={filter_type}, search={search_query[:100] if search_query else 'None'}, "
        f"low_expr_enabled={low_expr_enabled}, min_tmm={low_expr_min_tmm}, min_sample_pct={low_expr_min_sample_pct}"
    )

    try:
        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            logger.warning(f"⚠️ [DEG-DOWNLOAD] Workbench {workbench_id} not found")
            return jsonify({'error': 'Workbench not found'}), 404

        # 워크벤치 디렉토리 경로 가져오기
        wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = wb_schema['deg']

        # 결과 파일 경로 구성
        result_file_pattern = f"{deg_dir}/{tool_name}/genes.counts.matrix.{comparison_name}.{tool_name}.DE_results"
        if low_expr_enabled:
            low_expr_result = ensure_low_expression_deg_result_file(
                workbench_schema=wb_schema,
                comparison_name=comparison_name,
                tool_name=tool_name,
                min_tmm=low_expr_min_tmm,
                min_sample_pct=low_expr_min_sample_pct,
                workbench_id=workbench_id
            )
            logger.info(
                f"[DEG-DOWNLOAD] Low-expression result prepared: retained_genes={low_expr_result['gene_count']}, "
                f"generated={low_expr_result['generated']}, result_file={low_expr_result['result_file']}"
            )
            if low_expr_result['gene_count'] == 0:
                return jsonify({'error': 'No genes found matching low-expression recalculation criteria'}), 404
            result_file_pattern = low_expr_result['result_file']

        # 파일 존재 여부 확인
        result_file = None
        if os.path.exists(result_file_pattern):
            result_file = result_file_pattern

        if not result_file:
            logger.warning(f"⚠️ [DEG-DOWNLOAD] Result file not found for comparison {comparison_name}")
            return jsonify({'error': 'DEG results not found for this comparison'}), 404

        logger.info(f"📖 [DEG-DOWNLOAD] Reading result file: {result_file}")

        # 파일 파싱 (필터 및 검색 적용)
        parsed_data = parse_deg_result_file(
            result_file,
            limit=None,  # 전체 데이터
            offset=0,
            search=search_query if search_query else None,
            filter_type=filter_type if filter_type != 'all' else None
        )

        # DataFrame 생성
        df = pd.DataFrame(parsed_data['data'])

        logger.info(f"📊 [DEG-DOWNLOAD] Data loaded after filters/search: {len(df)} genes")

        if len(df) == 0:
            logger.warning(f"⚠️ [DEG-DOWNLOAD] No genes found matching criteria")
            return jsonify({'error': 'No genes found matching criteria'}), 404

        # CSV로 변환
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)

        # 파일명 생성
        filter_suffix = f"_{filter_type}" if filter_type != 'all' else ""
        search_suffix = "_filtered" if search_query else ""
        low_expr_suffix = "_lowexpr" if low_expr_enabled else ""
        filename = f"deg_{tool_name}_{comparison_name}{filter_suffix}{search_suffix}{low_expr_suffix}.csv"

        # Response 생성
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-cache'

        logger.info(f"✅ [DEG-DOWNLOAD] Download complete: {len(df)} genes, filename={filename}")

        return response

    except Exception as e:
        logger.error(f"❌ [DEG-DOWNLOAD] Failed to download DEG results: {str(e)}")
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/go-enrichment', methods=['POST'])
def run_go_enrichment(workbench_id: int):
    """
    Run GO enrichment analysis using the configured provider.

    Request Body:
        {
            "genes": ["TP53", "BRCA1", "EGFR", ...],  # Required: List of gene symbols
            "databases": ["GO_BP_2023", "GO_MF_2023"],  # Optional: Databases to query
            "p_value_cutoff": 0.05,  # Optional: Adjusted p-value cutoff
            "description": "Up-regulated genes"  # Optional: Description
        }

    Returns:
        {
            "success": true,
            "gene_count": 150,
            "results": {
                "GO_BP_2023": [
                    {
                        "Rank": 1,
                        "Term": "GO:0006955 immune response",
                        "P-value": 1.23e-10,
                        "Adjusted P-value": 2.45e-08,
                        "Combined Score": 123.45,
                        "Genes": "TP53;BRCA1;EGFR",
                        "Gene Count": 3
                    },
                    ...
                ],
                "GO_MF_2023": [...]
            }
        }
    """
    try:
        # Parse request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        genes = data.get('genes', [])
        databases = data.get('databases', ['GO_BP', 'GO_MF', 'GO_CC'])
        p_value_cutoff = data.get('p_value_cutoff', 0.05)
        description = data.get('description', f'VizR Workbench {workbench_id} Gene List')
        organism = data.get('organism', 'arabidopsis')  # Default to Arabidopsis
        provider = (data.get('provider') or 'gprofiler').lower()

        # Validate input
        if not genes or not isinstance(genes, list):
            return jsonify({'error': 'genes must be a non-empty list'}), 400

        if len(genes) < 2:
            return jsonify({'error': 'At least 2 genes are required for enrichment analysis'}), 400

        if provider not in {'david', 'gprofiler'}:
            return jsonify({'error': 'provider must be one of: david, gprofiler'}), 400

        logger.info(f"🧬 [GO-ENRICHMENT] Workbench {workbench_id}: Starting analysis for {len(genes)} genes")
        logger.info(f"📚 [GO-ENRICHMENT] Organism: {organism}")
        logger.info(f"📚 [GO-ENRICHMENT] Provider: {provider}")
        logger.info(f"📚 [GO-ENRICHMENT] Databases: {', '.join(databases)}")
        logger.info(f"🎯 [GO-ENRICHMENT] P-value cutoff: {p_value_cutoff}")
        logger.info(f"📋 [GO-ENRICHMENT] Gene list (first 10): {genes[:10]}")
        logger.info(f"📋 [GO-ENRICHMENT] Description: {description}")

        if provider == 'david':
            user_id = session.get('user_id')
            david_email = UserSettings.get_value(user_id, 'go.david.email', '') if user_id else ''
            if not str(david_email).strip():
                return jsonify({'error': 'DAVID email is not configured in Settings -> AI Analysis'}), 400

            api = DavidGOEnrichmentAPI(DavidConfig(email=str(david_email).strip()))
            results = api.run_enrichment(
                genes=genes,
                databases=databases,
                organism=organism,
                p_value_cutoff=p_value_cutoff
            )
        else:
            api = GProfilerAPI(organism=organism, timeout=60)
            results = api.run_enrichment(
                genes=genes,
                databases=databases,
                description=description,
                p_value_cutoff=p_value_cutoff
            )

        if not results:
            logger.warning(f"⚠️ [GO-ENRICHMENT] No significant enrichment found")
            return jsonify({
                'success': True,
                'provider': provider,
                'gene_count': len(genes),
                'results': {},
                'message': 'No significant enrichment terms found'
            }), 200

        # Convert DataFrames to JSON-serializable format
        # Add gene symbol mapping to results
        gene_annotations = load_gene_annotations()

        json_results = {}
        total_terms = 0

        for db_name, df in results.items():
            # Add GeneSymbols field by mapping each gene ID to its symbol
            df['GeneSymbols'] = df['Genes'].apply(
                lambda genes_str: ';'.join([
                    gene_annotations.get(gene_id.strip(), {}).get("symbol", gene_id.strip())
                    for gene_id in genes_str.split(';')
                ])
            )

            # Convert DataFrame to list of dicts
            json_results[db_name] = df.to_dict('records')
            total_terms += len(df)

        logger.info(f"✅ [GO-ENRICHMENT] Analysis complete: {total_terms} enriched terms across {len(results)} databases")

        return jsonify({
            'success': True,
            'provider': provider,
            'gene_count': len(genes),
            'databases': list(results.keys()),
            'total_terms': total_terms,
            'results': json_results
        }), 200

    except DavidAPIError as e:
        logger.error(f"❌ [GO-ENRICHMENT] DAVID failed: {str(e)}")
        return jsonify({'error': str(e)}), 502
    except Exception as e:
        logger.error(f"❌ [GO-ENRICHMENT] Failed to run GO enrichment: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/kegg-pathway', methods=['POST'])
def run_kegg_pathway(workbench_id: int):
    """
    Run KEGG pathway enrichment analysis

    Request Body:
        {
            "genes": ["AT1G01010", "AT1G01020", ...],  # Required: List of gene IDs
            "p_value_cutoff": 0.05,  # Optional: Adjusted p-value cutoff
            "organism": "arabidopsis"  # Optional: Organism name
        }

    Returns:
        {
            "success": true,
            "gene_count": 150,
            "pathways": [
                {
                    "Rank": 1,
                    "Term ID": "KEGG:00195",
                    "Term Name": "Photosynthesis",
                    "P-value": 0.00012,
                    "Adjusted P-value": 0.0024,
                    "Genes": "AT1G01010;AT1G01020;...",
                    "Gene Count": 15,
                    "Term Size": 45,
                    "kegg_url": "https://www.kegg.jp/pathway/ath00195+...",
                    "GeneSymbols": "NAC001;ARV1;..."
                },
                ...
            ]
        }
    """
    try:
        # Parse request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        genes = data.get('genes', [])
        p_value_cutoff = data.get('p_value_cutoff', 0.05)
        organism = data.get('organism', 'arabidopsis')

        # Validate input
        if not genes or not isinstance(genes, list):
            return jsonify({'error': 'genes must be a non-empty list'}), 400

        if len(genes) < 2:
            return jsonify({'error': 'At least 2 genes are required for enrichment analysis'}), 400

        logger.info(f"🧬 [KEGG-PATHWAY] Workbench {workbench_id}: Starting analysis for {len(genes)} genes")
        logger.info(f"📚 [KEGG-PATHWAY] Organism: {organism}")
        logger.info(f"🎯 [KEGG-PATHWAY] P-value cutoff: {p_value_cutoff}")
        logger.info(f"📋 [KEGG-PATHWAY] Gene list (first 10): {genes[:10]}")

        # Load gene annotations for this workbench
        gene_annotations = load_gene_annotations()

        # Run KEGG pathway analysis
        result = analyze_kegg_pathways(
            genes=genes,
            organism=organism,
            p_value_cutoff=p_value_cutoff,
            gene_symbol_map=gene_annotations
        )

        if not result['success']:
            logger.error(f"❌ [KEGG-PATHWAY] Analysis failed: {result.get('error', 'Unknown error')}")
            return jsonify({
                'error': result.get('error', 'KEGG pathway analysis failed'),
                'success': False
            }), 500

        logger.info(f"✅ [KEGG-PATHWAY] Analysis complete: {len(result['pathways'])} enriched pathways")

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"❌ [KEGG-PATHWAY] Failed to run KEGG pathway analysis: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/go-enrichment/databases', methods=['GET'])
def get_available_databases(workbench_id: int):
    """
    Get list of available g:Profiler databases

    Returns:
        {
            "databases": {
                "GO_BP": "GO:BP",
                "GO_MF": "GO:MF",
                "GO_CC": "GO:CC",
                "KEGG": "KEGG",
                "REAC": "REAC"
            }
        }
    """
    try:
        return jsonify({
            'databases': GProfilerAPI.DATABASES
        }), 200

    except Exception as e:
        logger.error(f"❌ [GO-ENRICHMENT] Failed to get databases: {str(e)}")
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/tmm-counts-by-genes', methods=['POST'])
def get_tmm_counts_by_genes(workbench_id: int):
    """
    특정 유전자 리스트에 대한 TMM-normalized counts 조회

    Request Body:
        {
            "gene_ids": ["AT1G01010", "AT1G01020", ...],
            "comparison": "DC_vs_DH",
            "tool_name": "edgeR"
        }

    Response:
        {
            "success": true,
            "data": {
                "AT1G01010": [12.5, 15.2, ...],
                "AT1G01020": [8.3, 10.1, ...]
            },
            "sample_names": ["DC_rep1", "DC_rep2", ...]
        }
    """
    try:
        # Parse request body
        request_data = request.get_json()
        if not request_data:
            return jsonify({'error': 'Request body is required'}), 400

        gene_ids = request_data.get('gene_ids', [])
        comparison_name = request_data.get('comparison', '').strip()
        tool_name = request_data.get('tool_name', '').strip()

        if not gene_ids or not isinstance(gene_ids, list):
            return jsonify({'error': 'gene_ids must be a non-empty list'}), 400

        if not comparison_name or not tool_name:
            return jsonify({'error': 'comparison and tool_name are required'}), 400

        # 도구 이름 정규화
        tool_name = normalize_tool_name(tool_name)

        logger.info(f"🔍 [TMM-BY-GENES] Fetching TMM counts for {len(gene_ids)} genes (workbench {workbench_id})")
        logger.debug(f"📋 [TMM-BY-GENES] First 10 genes: {gene_ids[:10]}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            logger.warning(f"⚠️ [TMM-BY-GENES] Workbench {workbench_id} not found")
            return jsonify({'error': 'Workbench not found'}), 404

        # 워크벤치 디렉토리 경로
        wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = wb_schema['deg']
        counts_dir = wb_schema['quanti']['counts']  # quanti 아래의 counts 디렉토리

        logger.info(f"📁 [TMM-BY-GENES] DEG directory: {deg_dir}")
        logger.info(f"📁 [TMM-BY-GENES] Counts directory: {counts_dir}")

        # TMM counts matrix 파일 경로 (여러 가능한 경로 시도)
        possible_tmm_paths = [
            # 실제 파이프라인에서 생성하는 파일명
            os.path.join(counts_dir, 'genes.TMM.matrix'),
            # 표준 형식들
            os.path.join(counts_dir, 'TMM', 'genes.counts.matrix.TMM_normalized.txt'),
            os.path.join(counts_dir, 'genes.counts.matrix.TMM_normalized.txt'),
            os.path.join(deg_dir, tool_name, f'genes.counts.matrix.{comparison_name}.{tool_name}.count_matrix.TMM_normalized.txt')
        ]

        logger.info(f"🔍 [TMM-BY-GENES] Searching for TMM file in {len(possible_tmm_paths)} possible locations")

        tmm_matrix_file = None
        for i, path in enumerate(possible_tmm_paths, 1):
            logger.info(f"   {i}. Checking: {path}")
            logger.info(f"      Exists: {os.path.exists(path)}")
            if os.path.exists(path):
                tmm_matrix_file = path
                logger.info(f"   ✅ Found TMM file: {path}")
                break

        if not tmm_matrix_file:
            logger.warning(f"⚠️ [TMM-BY-GENES] TMM matrix file not found in any of the possible locations")
            return jsonify({'error': 'TMM matrix file not found'}), 404

        logger.info(f"📖 [TMM-BY-GENES] Reading TMM matrix: {tmm_matrix_file}")

        # TMM matrix 읽기
        tmm_df = pd.read_csv(tmm_matrix_file, sep='\t', index_col=0)
        sample_names = tmm_df.columns.tolist()

        logger.info(f"📊 [TMM-BY-GENES] TMM matrix shape: {tmm_df.shape} (genes x samples)")

        # 요청된 유전자들의 TMM 값 추출
        tmm_data = {}
        found_genes = 0
        missing_genes = []

        for gene_id in gene_ids:
            if gene_id in tmm_df.index:
                tmm_data[gene_id] = tmm_df.loc[gene_id].tolist()
                found_genes += 1
            else:
                missing_genes.append(gene_id)

        logger.info(f"✅ [TMM-BY-GENES] Found {found_genes}/{len(gene_ids)} genes in TMM matrix")
        if missing_genes:
            logger.debug(f"⚠️ [TMM-BY-GENES] Missing genes (first 10): {missing_genes[:10]}")

        return jsonify({
            'success': True,
            'data': tmm_data,
            'sample_names': sample_names,
            'found_count': found_genes,
            'total_requested': len(gene_ids)
        }), 200

    except Exception as e:
        logger.error(f"❌ [TMM-BY-GENES] Failed to fetch TMM counts: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/expression-matrix', methods=['GET'])
def get_expression_matrix(workbench_id: int):
    """
    Expression Matrix 데이터 조회 (diffExpr.P{p}_C{c}.matrix.log2.centered.dat)

    Query Parameters:
        p_value: P-value cutoff (default: 0.01)
        fold_change: Fold-change cutoff in log2 scale (default: 2.0)
        page: 페이지 번호 (default: 1)
        limit: 페이지당 항목 수 (default: 500)
        search: 검색 키워드 (Gene ID 또는 Symbol, 쉼표로 구분)

    Returns:
        {
            "data": [...],
            "samples": ["DC_rep1", ...],
            "total": 15000,
            "page": 1,
            "limit": 500,
            "p_value": 0.01,
            "fold_change": 2.0,
            "file_generated": false
        }
    """
    try:
        # Query parameters
        p_value = float(request.args.get('p_value', 0.01))
        fold_change = float(request.args.get('fold_change', 2.0))
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 500))
        search = request.args.get('search', None)
        offset = (page - 1) * limit

        logger.info(f"📊 [EXPR-MATRIX] Request Details:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"├─ P-value: {p_value}")
        logger.info(f"├─ Fold-change: {fold_change}")
        logger.info(f"├─ Page: {page} (limit: {limit})")
        if search:
            search_display = f"'{search[:50]}...'" if len(search) > 50 else f"'{search}'"
            logger.info(f"└─ Search: {search_display}")
        else:
            logger.info(f"└─ Search: None")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            logger.warning(f"⚠️ [EXPR-MATRIX] Workbench {workbench_id} not found")
            return jsonify({'error': 'Workbench not found'}), 404

        # 워크벤치 디렉토리 경로
        wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = wb_schema['deg']
        edger_dir = os.path.join(deg_dir, 'edgeR')

        # 파일명 생성 (Trinity 규칙: diffExpr.P0.01_C2.0.matrix.log2.centered.dat)
        matrix_filename = f"diffExpr.P{p_value}_C{fold_change}.matrix.log2.centered.dat"
        matrix_file = os.path.join(edger_dir, matrix_filename)

        file_generated = False

        # 파일 존재 여부 확인
        if not os.path.exists(matrix_file):
            logger.info(f"📁 [EXPR-MATRIX] File not found, generating: {matrix_filename}")

            # run_dea() 호출하여 파일 생성
            from backend.pipeline.utils.de_analysis import run_dea

            # TMM matrix 경로
            counts_dir = wb_schema['quanti']['counts']
            tmm_matrix_file = os.path.join(counts_dir, 'genes.TMM.matrix')

            # samples.txt 경로
            samples_dir = wb_schema['quanti']['samples']
            samples_file = os.path.join(samples_dir, 'samples.txt')

            # 파일 존재 확인
            if not os.path.exists(tmm_matrix_file):
                logger.error(f"❌ [EXPR-MATRIX] TMM matrix not found: {tmm_matrix_file}")
                return jsonify({'error': 'TMM matrix file not found. Please run DEG analysis first.'}), 404

            if not os.path.exists(samples_file):
                logger.error(f"❌ [EXPR-MATRIX] Samples file not found: {samples_file}")
                return jsonify({'error': 'Samples file not found. Please run DEG analysis first.'}), 404

            # run_dea() 호출
            workbench_root = wb_schema["base"]
            dea_result = run_dea(
                workbench_root=workbench_root,
                output_dir=edger_dir,
                tmm_matrix_file=tmm_matrix_file,
                samples_file=samples_file,
                workbench_id=workbench_id,
                worker_id="api_worker",
                p_value=p_value,
                fold_change=fold_change
            )

            if not dea_result.get('success', False):
                error_msg = dea_result.get('error', 'Unknown error')
                logger.error(f"❌ [EXPR-MATRIX] Failed to generate matrix: {error_msg}")
                return jsonify({'error': f'Failed to generate expression matrix: {error_msg}'}), 500

            file_generated = True
            logger.info(f"✅ [EXPR-MATRIX] File generated successfully: {matrix_filename}")
        else:
            logger.info(f"✅ [EXPR-MATRIX] Using existing file: {matrix_filename}")

        # 파일 파싱
        logger.info(f"📖 [EXPR-MATRIX] Reading matrix file: {matrix_file}")

        df = pd.read_csv(matrix_file, sep='\t', index_col=0)
        df.index.name = 'GeneID'
        df = df.reset_index()

        # Gene symbol 및 description 추가
        gene_annotations = load_gene_annotations()
        df.insert(1, 'GeneSymbol', df['GeneID'].map(lambda x: gene_annotations.get(x, {}).get("symbol", x)))
        df.insert(2, 'GeneDescription', df['GeneID'].map(lambda x: gene_annotations.get(x, {}).get("description", "No description available")))

        # 검색 필터 적용
        if search:
            # 검색어 파싱 (쉼표, 공백, 탭, 줄바꿈으로 구분)
            search_terms = re.split(r'[,\s\t\n]+', search)
            search_terms = [term.strip().upper() for term in search_terms if term.strip()]

            logger.debug(f"🔍 [EXPR-MATRIX-SEARCH] Parsed {len(search_terms)} search terms")

            if search_terms:
                # 1. gene_id로 부분 일치 검색 (대소문자 구분 없이)
                mask = pd.Series([False] * len(df), index=df.index)
                for term in search_terms:
                    mask |= df['GeneID'].str.upper().str.contains(term, regex=False, na=False)
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
                    symbol_mask = df['GeneID'].isin(gene_ids_from_symbols)
                    mask |= symbol_mask
                    matched_by_symbol = symbol_mask.sum()

                # 필터링 적용
                df = df[mask]

                logger.debug(f"✅ [EXPR-MATRIX-SEARCH] {len(df)} genes matched (ID: {matched_by_id}, Symbol: {matched_by_symbol})")

                if len(df) == 0:
                    logger.debug(f"⚠️ [EXPR-MATRIX-SEARCH] No genes matched search query")
            else:
                logger.debug(f"ℹ️ [EXPR-MATRIX-SEARCH] Empty search terms after parsing")

        total_count = len(df)

        # 페이지네이션 적용
        if limit:
            df = df.iloc[offset:offset + limit]

        # 샘플 컬럼 추출 (GeneID, GeneSymbol, GeneDescription 제외)
        samples = df.columns[3:].tolist()

        # 데이터 변환
        data = df.to_dict('records')

        logger.info(f"✅ [EXPR-MATRIX] Matrix loaded: {total_count} genes, {len(samples)} samples")

        return jsonify({
            'data': data,
            'samples': samples,
            'total': total_count,
            'page': page,
            'limit': limit,
            'p_value': p_value,
            'fold_change': fold_change,
            'file_generated': file_generated
        }), 200

    except Exception as e:
        logger.error(f"❌ [EXPR-MATRIX] Failed to fetch expression matrix: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/heatmap', methods=['POST'])
def generate_heatmap(workbench_id: int):
    """
    히트맵 데이터 생성 (TMM counts 기반 정규화 + 클러스터링)

    Request Body:
        {
            "genes": ["AT1G01010", "AT1G01020", ...],
            "comparison": "DC_vs_DH",
            "tool": "edgeR",
            "clustering_method": "ward",  # ward, average, complete
            "normalize": "zscore",  # zscore, log2_centered, log2fc_reference, none
            "reference_sample": "A-rep1"  # required when normalize is log2fc_reference
        }

    Normalization Methods:
        - zscore: Z-score 정규화 (평균 0, 표준편차 1), ±3 클리핑
        - log2_centered: log2(x+1) 변환 후 row centering (평균 빼기)
        - log2fc_reference: log2(sample / reference_sample) - 기준 샘플 대비 fold change
        - none: 정규화 없음 (원본 TMM counts)

    Response:
        {
            "z": [[values...]],  # 2D array (genes x samples)
            "x": ["Sample1", "Sample2", ...],
            "y": ["Gene1", "Gene2", ...],
            "gene_symbols": ["Symbol1", "Symbol2", ...],
            "row_order": [0, 5, 3, ...],  # clustered gene order
            "col_order": [0, 1, 2, ...]   # clustered sample order
        }
    """
    try:
        import numpy as np
        from scipy.cluster.hierarchy import linkage, dendrogram
        from scipy.spatial.distance import pdist

        # Parse request body
        request_data = request.get_json()
        if not request_data:
            return jsonify({'error': 'Request body is required'}), 400

        genes = request_data.get('genes', [])
        comparison_name = request_data.get('comparison', '').strip()
        tool_name = request_data.get('tool', '').strip()
        clustering_method = request_data.get('clustering_method', 'ward')
        normalize = request_data.get('normalize', 'zscore')
        reference_sample = request_data.get('reference_sample', '').strip()

        if not genes or not isinstance(genes, list):
            return jsonify({'error': 'genes must be a non-empty list'}), 400

        # comparison과 tool은 optional (Count 데이터에서는 없을 수 있음)
        # 도구 이름 정규화 (tool_name이 있는 경우에만)
        if tool_name:
            tool_name = normalize_tool_name(tool_name)

        # 로깅
        logger.info(f"🎨 [HEATMAP] Generating heatmap for {len(genes)} genes (workbench {workbench_id})")
        if comparison_name and tool_name:
            logger.info(f"📋 [HEATMAP] Comparison: {comparison_name}, Tool: {tool_name}, Clustering: {clustering_method}")
        else:
            logger.info(f"📋 [HEATMAP] Count data (no comparison), Clustering: {clustering_method}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            logger.warning(f"⚠️ [HEATMAP] Workbench {workbench_id} not found")
            return jsonify({'error': 'Workbench not found'}), 404

        # 워크벤치 디렉토리 경로
        wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        counts_dir = wb_schema['quanti']['counts']

        # TMM counts matrix 파일 경로
        possible_tmm_paths = [
            os.path.join(counts_dir, 'genes.TMM.matrix'),
            os.path.join(counts_dir, 'TMM', 'genes.counts.matrix.TMM_normalized.txt'),
            os.path.join(counts_dir, 'genes.counts.matrix.TMM_normalized.txt')
        ]

        tmm_matrix_file = None
        for path in possible_tmm_paths:
            if os.path.exists(path):
                tmm_matrix_file = path
                logger.info(f"✅ [HEATMAP] Found TMM matrix: {path}")
                break

        if not tmm_matrix_file:
            logger.error(f"❌ [HEATMAP] TMM matrix file not found")
            return jsonify({'error': 'TMM matrix file not found'}), 404

        # TMM matrix 로드
        logger.info(f"📊 [HEATMAP] Loading TMM matrix from {tmm_matrix_file}")
        tmm_df = pd.read_csv(tmm_matrix_file, sep='\t', index_col=0)

        # 선택된 유전자만 필터링 (대소문자 구분 없이 매핑)
        tmm_index_upper = {idx.upper(): idx for idx in tmm_df.index}
        valid_genes = [tmm_index_upper[g.upper()] for g in genes if g.upper() in tmm_index_upper]
        if not valid_genes:
            logger.error(f"❌ [HEATMAP] No valid genes found in TMM matrix")
            return jsonify({'error': 'No valid genes found in TMM matrix'}), 404

        logger.info(f"✅ [HEATMAP] Found {len(valid_genes)}/{len(genes)} genes in TMM matrix")

        # 유전자 서브셋 추출
        tmm_subset = tmm_df.loc[valid_genes]

        # 정규화
        if normalize == 'zscore':
            logger.info(f"🔢 [HEATMAP] Applying Z-score normalization")
            # 각 유전자(행)별로 Z-score 계산
            normalized_matrix = (tmm_subset - tmm_subset.mean(axis=1).values.reshape(-1, 1)) / tmm_subset.std(axis=1).values.reshape(-1, 1)
            # NaN 처리 (표준편차가 0인 경우)
            normalized_matrix = normalized_matrix.fillna(0)
            # ±3으로 클리핑
            normalized_matrix = normalized_matrix.clip(-3, 3)
        elif normalize == 'log2_centered':
            logger.info(f"🔢 [HEATMAP] Applying log2(centered) normalization")
            # 1. Log2 변환 (pseudo-count +1)
            log2_matrix = np.log2(tmm_subset + 1)
            # 2. Row centering (각 유전자별로 평균 빼기)
            normalized_matrix = log2_matrix - log2_matrix.mean(axis=1).values.reshape(-1, 1)
            # NaN 처리
            normalized_matrix = normalized_matrix.fillna(0)
        elif normalize == 'log2fc_reference':
            # reference_sample이 없으면 첫 번째 컬럼 사용
            if not reference_sample:
                reference_sample = tmm_subset.columns[0]
                logger.info(f"🔢 [HEATMAP] No reference sample specified, using first sample: {reference_sample}")

            logger.info(f"🔢 [HEATMAP] Applying Log2FC vs Reference normalization (reference: {reference_sample})")

            # 기준 샘플이 존재하는지 확인
            if reference_sample not in tmm_subset.columns:
                logger.error(f"❌ [HEATMAP] Reference sample '{reference_sample}' not found in TMM matrix")
                return jsonify({'error': f"Reference sample '{reference_sample}' not found"}), 400

            # 기준 샘플 데이터 추출
            reference_values = tmm_subset[reference_sample].values.reshape(-1, 1)

            # Log2 Fold Change 계산: log2(sample / reference)
            # pseudo-count +1을 추가하여 0으로 나누기 방지
            normalized_matrix = np.log2((tmm_subset + 1).values / (reference_values + 1))
            normalized_matrix = pd.DataFrame(normalized_matrix, index=tmm_subset.index, columns=tmm_subset.columns)

            # NaN/Inf 처리
            normalized_matrix = normalized_matrix.replace([np.inf, -np.inf], np.nan).fillna(0)

            logger.info(f"✅ [HEATMAP] Log2FC calculated (reference: {reference_sample})")
        else:
            # 정규화 없음
            normalized_matrix = tmm_subset

        # vizr_pipeline_samples에서 샘플 순서 가져오기
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT samples FROM vizr_pipeline_samples WHERE workbench_id = ?", (workbench_id,))
            pipeline_samples_row = cursor.fetchone()

        # 샘플 순서 결정
        col_order = list(range(len(tmm_subset.columns)))  # 기본 순서

        if pipeline_samples_row and pipeline_samples_row['samples']:
            try:
                import json
                samples_json = json.loads(pipeline_samples_row['samples'])
                # samples JSON에서 sampleName 순서 추출
                ordered_sample_names = [s['sampleName'] for s in samples_json]

                # TMM matrix 컬럼을 ordered_sample_names 순서로 재배열
                available_samples = list(tmm_subset.columns)
                col_order = []
                for sample_name in ordered_sample_names:
                    if sample_name in available_samples:
                        col_order.append(available_samples.index(sample_name))

                # 누락된 샘플이 있다면 뒤에 추가
                for idx, sample_name in enumerate(available_samples):
                    if idx not in col_order:
                        col_order.append(idx)

                logger.info(f"✅ [HEATMAP] Using sample order from vizr_pipeline_samples: {len(col_order)} samples")
            except Exception as e:
                logger.warning(f"⚠️ [HEATMAP] Failed to parse sample order from DB: {str(e)}, using TMM matrix order")
                col_order = list(range(len(tmm_subset.columns)))

        # 클러스터링 (유전자만)
        row_order = list(range(len(valid_genes)))

        if clustering_method in ['ward', 'average', 'complete']:
            try:
                logger.info(f"🔗 [HEATMAP] Performing hierarchical clustering on genes ({clustering_method})")

                # 행(유전자) 클러스터링만 수행
                if len(valid_genes) > 1:
                    row_linkage = linkage(normalized_matrix.values, method=clustering_method)
                    row_dendrogram = dendrogram(row_linkage, no_plot=True)
                    row_order = row_dendrogram['leaves']
                    logger.info(f"✅ [HEATMAP] Gene clustering completed")

            except Exception as e:
                logger.warning(f"⚠️ [HEATMAP] Clustering failed: {str(e)}, using original order")

        # 클러스터링 순서대로 재배열
        normalized_reordered = normalized_matrix.iloc[row_order, col_order]

        # Gene symbol mapping 로드
        gene_annotations = load_gene_annotations()

        # Gene symbols 배열 생성 (클러스터링 순서 적용)
        gene_symbols = [gene_annotations.get(valid_genes[i], {}).get("symbol", valid_genes[i]) for i in row_order]

        # 응답 데이터 생성
        response_data = {
            'z': normalized_reordered.values.tolist(),
            'x': [tmm_subset.columns[i] for i in col_order],
            'y': [valid_genes[i] for i in row_order],
            'gene_symbols': gene_symbols,
            'row_order': row_order,
            'col_order': col_order
        }

        logger.info(f"✅ [HEATMAP] Heatmap generated successfully: {len(valid_genes)} genes x {len(tmm_subset.columns)} samples")

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"❌ [HEATMAP] Failed to generate heatmap: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@deg_bp.route('/<int:workbench_id>/deg/expression-matrix/download', methods=['POST'])
def download_expression_matrix(workbench_id: int):
    """
    Expression Matrix 파일 다운로드 (선택된 유전자 또는 전체)

    Request Body:
        {
            "p_value": 0.01,
            "fold_change": 2.0,
            "selected_genes": ["AT1G01010", ...] (optional)
        }

    Returns:
        File download (CSV format with GeneID and GeneSymbol columns)
    """
    try:
        from flask import send_file
        import pandas as pd
        import tempfile

        # Request body 파싱
        request_data = request.get_json()
        if not request_data:
            return jsonify({'error': 'Request body is required'}), 400

        p_value = float(request_data.get('p_value', 0.01))
        fold_change = float(request_data.get('fold_change', 2.0))
        selected_genes = request_data.get('selected_genes', [])

        logger.info(f"📥 [DOWNLOAD] Expression Matrix download request:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"├─ P-value: {p_value}")
        logger.info(f"├─ Fold-change: {fold_change}")
        logger.info(f"└─ Selected genes: {len(selected_genes) if selected_genes else 'All'}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            logger.warning(f"⚠️ [DOWNLOAD] Workbench {workbench_id} not found")
            return jsonify({'error': 'Workbench not found'}), 404

        # 워크벤치 디렉토리 경로
        wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = wb_schema['deg']
        edger_dir = os.path.join(deg_dir, 'edgeR')

        # 원본 TSV 파일명 생성
        matrix_filename = f"diffExpr.P{p_value}_C{fold_change}.matrix.log2.centered.dat"
        matrix_file = os.path.join(edger_dir, matrix_filename)

        # 파일 존재 여부 확인
        if not os.path.exists(matrix_file):
            logger.warning(f"⚠️ [DOWNLOAD] File not found: {matrix_filename}")
            return jsonify({'error': 'Expression matrix file not found. Please generate it first.'}), 404

        # TSV 파일 읽기 및 GeneSymbol 추가
        df = pd.read_csv(matrix_file, sep='\t', index_col=0)
        df.index.name = 'GeneID'
        df = df.reset_index()

        # Gene symbol 추가
        gene_annotations = load_gene_annotations()
        df.insert(1, 'GeneSymbol', df['GeneID'].map(lambda x: gene_annotations.get(x, {}).get("symbol", x)))

        # 선택된 유전자만 필터링
        if selected_genes:
            logger.info(f"🔍 [DOWNLOAD] Filtering {len(selected_genes)} selected genes")
            df = df[df['GeneID'].isin(selected_genes)]
            logger.info(f"📊 [DOWNLOAD] Filtered: {len(df)} genes found")

        # CSV 파일명 생성 (점 제거)
        p_str = str(p_value).replace('.', '')
        c_str = str(fold_change).replace('.', '')

        if selected_genes:
            csv_filename = f"diffExpr.P{p_str}_C{c_str}.selected_{len(selected_genes)}_genes.csv"
        else:
            csv_filename = f"diffExpr.P{p_str}_C{c_str}.matrix.log2.centered.csv"

        # 임시 CSV 파일 생성
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='', encoding='utf-8') as temp_file:
            df.to_csv(temp_file, sep=',', index=False)
            temp_path = temp_file.name

        logger.info(f"✅ [DOWNLOAD] Sending CSV file with {len(df)} genes: {csv_filename}")

        return send_file(
            temp_path,
            mimetype='text/csv',
            as_attachment=True,
            download_name=csv_filename
        )

    except Exception as e:
        logger.error(f"❌ [DOWNLOAD] Failed to download expression matrix: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
