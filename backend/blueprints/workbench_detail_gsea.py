"""
Workbench preranked GSEA API.
"""

from __future__ import annotations

import json
import os

from flask import Blueprint, jsonify, request, session

from backend.blueprints.workbench_share import check_workbench_access
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.pipeline.utils.gsea_builtin_db import (
    get_available_builtin_gsea_databases,
    load_builtin_gene_sets,
)
from backend.pipeline.utils.gsea_preranked import (
    DEFAULT_WEIGHT,
    GSEAValidationError,
    MAX_GENE_SET_SIZE,
    MIN_OVERLAP,
    compute_single_gene_set_detail,
    parse_gmt_file,
    parse_ranked_gene_list,
    run_preranked_gsea,
    summarize_gsea_rows,
)
from backend.pipeline.utils.gsea_result_store import (
    build_preranked_text_from_deg_result,
    extract_ranking_profile_from_deg_result,
    get_gsea_result_paths,
    load_gsea_comparison_detail,
    load_gsea_plot_detail_cache,
    load_precomputed_gsea_state,
    normalize_deg_tool_name,
    resolve_deg_result_file_from_schema,
    save_gsea_plot_detail_cache,
    save_precomputed_gsea_result,
)
from backend.utils.auth import get_current_user_id, require_auth
from backend.utils.database import get_db_connection
from backend.utils.logger import setup_module_logger
from config.shared_config import SharedConfig

logger = setup_module_logger(__name__, 'INFO')

gsea_bp = Blueprint('gsea', __name__, url_prefix='/api/workbenches')
LEGACY_GSEA_DATABASES = ['go_bp', 'kegg']
DEFAULT_GSEA_PERMUTATIONS = 25


def _build_gmt_text(database_bundle: dict) -> str:
    lines = []
    for gene_set_name, gene_set_data in database_bundle['gene_sets'].items():
        description = str(gene_set_data.get('description', '') or '')
        genes = gene_set_data.get('genes', []) or []
        lines.append('\t'.join([gene_set_name, description, *genes]))
    return '\n'.join(lines) + ('\n' if lines else '')


def _build_validation_readme(
    workbench: dict,
    comparison_name: str,
    resolved_tool: str,
    database_bundle: dict,
    rank_key: str,
    gene_count: int,
    permutations: int,
) -> str:
    database = database_bundle['database']
    comparison_label = comparison_name.replace('_vs_', ' vs ').replace('_', ' ')
    return f"""VizR GSEA validation input bundle

This bundle is generated from the exact inputs used by the current VizR GSEA result.

Workbench: {workbench.get('name', '')}
Species: {workbench.get('species', '')}
Comparison: {comparison_label}
Comparison key: {comparison_name}
DEG tool: {resolved_tool}
Ranking metric: {rank_key}
Ranked genes: {gene_count}
Permutations: {permutations}

Gene set database: {database.get('label', '')}
Database key: {database.get('key', '')}
Source: {database.get('source', '')}
Species (DB): {database.get('species', '')}
ID namespace: {database.get('id_namespace', '')}
Generation date: {database.get('generation_date', '')}

Files in this bundle:
1. ranked_genes.rnk
   - Two-column tab-delimited preranked gene list
   - Column 1: gene identifier
   - Column 2: ranking metric ({rank_key})

2. gene_sets.gmt
   - GMT gene set database used for this GSEA run

Recommended validation workflow:
1. Run an external preranked GSEA tool with ranked_genes.rnk and gene_sets.gmt.
2. Use the same ranking direction as VizR ({rank_key} descending).
3. Compare:
   - top enriched gene sets
   - NES correlation
   - nominal p-value and FDR trends
   - leading-edge overlap
   - enrichment plot shape

Notes:
- Small numerical differences can occur because of implementation details such as tie handling or permutation internals.
- If ranking metric or database snapshot differs, the results are not directly comparable.
"""


def _get_user_temp_file_path(temp_filename: str) -> str:
    username = session.get('username')
    if not username:
        raise GSEAValidationError('Authentication required')
    return os.path.join(SharedConfig.VIZR_PATH, "users", username, "tmp", temp_filename)


def _get_workbench_context(workbench_id: int) -> dict:
    with get_db_connection() as conn:
        workbench = conn.execute(
            '''
            SELECT w.id, w.name, w.user_id, w.species, u.username
            FROM vizr_workbench w
            JOIN users u ON u.id = w.user_id
            WHERE w.id = ?
            ''',
            (workbench_id,),
        ).fetchone()

    if not workbench:
        raise FileNotFoundError(f"Workbench {workbench_id} was not found")

    return dict(workbench)


def _get_workbench_schema_for_context(workbench: dict) -> dict:
    return get_workbench_schema(workbench['name'], workbench['user_id'])


def _get_selected_gsea_databases(workbench_id: int) -> list[str]:
    with get_db_connection() as conn:
        row = conn.execute(
            '''
            SELECT pipeline_steps
            FROM vizr_pipeline_configurations
            WHERE workbench_id = ?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            ''',
            (workbench_id,),
        ).fetchone()

    if not row or not row['pipeline_steps']:
        return LEGACY_GSEA_DATABASES

    try:
        pipeline_steps = json.loads(row['pipeline_steps'])
    except (TypeError, json.JSONDecodeError):
        return LEGACY_GSEA_DATABASES

    for step in pipeline_steps:
        if step.get('step') != 'deg':
            continue

        parameters = step.get('parameters') or {}
        configured_databases = parameters.get('gsea_databases')
        if isinstance(configured_databases, list):
            normalized = [
                str(key).strip().lower()
                for key in configured_databases
                if str(key).strip()
            ]
            return normalized

    return LEGACY_GSEA_DATABASES


def _get_selected_gsea_permutations(workbench_id: int) -> int:
    return DEFAULT_GSEA_PERMUTATIONS


def _build_comparison_gsea_payload(
    workbench: dict,
    comparison_name: str,
    deg_tool: str,
    gene_set_db: str,
) -> dict:
    workbench_schema = _get_workbench_schema_for_context(workbench)
    result_path, resolved_tool = resolve_deg_result_file_from_schema(workbench_schema, comparison_name, deg_tool)
    logger.info(
        f"[GSEA] DEG result path resolved: workbench_id={workbench['id']}, path='{result_path}', resolved_tool='{resolved_tool}'"
    )
    ranked_list_text, _, _ = build_preranked_text_from_deg_result(result_path)
    ranking_profile, zero_cross_index, resolved_rank_key = extract_ranking_profile_from_deg_result(result_path)
    ranked_entries = parse_ranked_gene_list(ranked_list_text)
    logger.info(
        f"[GSEA] Ranked entries parsed: workbench_id={workbench['id']}, comparison='{comparison_name}', count={len(ranked_entries)}"
    )
    database_bundle = load_builtin_gene_sets(workbench.get('species', ''), gene_set_db, workbench.get('username'))
    logger.info(
        f"[GSEA] Built-in gene sets loaded: workbench_id={workbench['id']}, gene_set_db='{gene_set_db}', resolved_label='{database_bundle['database']['label']}', gene_set_count={len(database_bundle['gene_sets'])}"
    )
    permutations = _get_selected_gsea_permutations(workbench['id'])
    result = run_preranked_gsea(
        ranked_entries,
        database_bundle['gene_sets'],
        permutations=permutations,
    )
    logger.info(
        f"[GSEA] Comparison GSEA completed: workbench_id={workbench['id']}, comparison='{comparison_name}', gene_set_db='{gene_set_db}', tested_gene_sets={result['tested_gene_sets']}, permutations={result['permutations']}, min_overlap={result['min_overlap']}, max_gene_set_size={result['max_gene_set_size']}, weight={DEFAULT_WEIGHT}"
    )

    payload = {
        'comparison_name': comparison_name,
        'deg_tool': resolved_tool,
        'gene_set_db': database_bundle['database']['key'],
        'gene_set_db_label': database_bundle['database']['label'],
        'database_metadata': database_bundle['database'],
        'ranking_metric': resolved_rank_key,
        'zero_cross_index': zero_cross_index,
        'validation': {
            'ranked_gene_count': result['ranked_gene_count'],
            'tested_gene_sets': result['tested_gene_sets'],
            'min_overlap': result['min_overlap'],
            'permutations': result['permutations'],
        },
        'rows': summarize_gsea_rows(result['rows']),
    }

    paths = get_gsea_result_paths(workbench_schema, resolved_tool, comparison_name, database_bundle['database']['key'])
    save_precomputed_gsea_result(
        paths,
        {
            **payload,
            'ranking_profile': ranking_profile,
            'rows': result['rows'],
        },
    )
    return payload


def _get_gsea_step_status(workbench_id: int) -> str | None:
    with get_db_connection() as conn:
        row = conn.execute(
            '''
            SELECT status
            FROM pipeline_job_steps
            WHERE workbench_id = ? AND step_name = 'gsea'
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            ''',
            (workbench_id,),
        ).fetchone()
    return row['status'] if row else None


@gsea_bp.route('/<int:workbench_id>/gsea/preranked-template', methods=['GET'])
@require_auth
def get_preranked_gsea_template(workbench_id: int):
    user_id = get_current_user_id()
    has_access, _ = check_workbench_access(workbench_id, user_id)
    if not has_access:
        return jsonify({'error': 'Access denied'}), 403

    comparison_name = (request.args.get('comparison_name') or '').strip()
    deg_tool = normalize_deg_tool_name(request.args.get('deg_tool'))
    if not comparison_name:
        return jsonify({'error': 'comparison_name is required'}), 400

    try:
        workbench = _get_workbench_context(workbench_id)
        workbench_schema = _get_workbench_schema_for_context(workbench)
        result_path, resolved_tool = resolve_deg_result_file_from_schema(workbench_schema, comparison_name, deg_tool)
        ranked_list_text, gene_count, rank_key = build_preranked_text_from_deg_result(result_path)
        return jsonify({
            'ranked_list_text': ranked_list_text,
            'gene_count': gene_count,
            'comparison_name': comparison_name,
            'deg_tool': resolved_tool,
            'ranking_metric': rank_key,
        })
    except FileNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except GSEAValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error(f"[GSEA] Failed to generate preranked template: {exc}", exc_info=True)
        return jsonify({'error': 'Failed to generate preranked template'}), 500


@gsea_bp.route('/<int:workbench_id>/gsea/databases', methods=['GET'])
@require_auth
def get_builtin_gsea_databases(workbench_id: int):
    user_id = get_current_user_id()
    has_access, _ = check_workbench_access(workbench_id, user_id)
    if not has_access:
        return jsonify({'error': 'Access denied'}), 403

    try:
        workbench = _get_workbench_context(workbench_id)
        logger.info(
            f"[GSEA] Loading built-in DB list: workbench_id={workbench_id}, species='{workbench.get('species', '')}', name='{workbench.get('name', '')}'"
        )
        selected_databases = _get_selected_gsea_databases(workbench_id)
        databases = get_available_builtin_gsea_databases(
            workbench.get('species', ''),
            selected_databases,
            workbench.get('username'),
        )
        logger.info(
            f"[GSEA] Built-in DB list loaded: workbench_id={workbench_id}, species='{workbench.get('species', '')}', selected={selected_databases}, count={len(databases)}, keys={[db['key'] for db in databases]}"
        )
        return jsonify({
            'species': workbench.get('species', ''),
            'databases': databases,
        })
    except Exception as exc:
        logger.error(f"[GSEA] Failed to list built-in databases: {exc}", exc_info=True)
        return jsonify({'error': 'Failed to load built-in GSEA databases'}), 500


@gsea_bp.route('/<int:workbench_id>/gsea/results', methods=['GET'])
@require_auth
def get_precomputed_gsea_result(workbench_id: int):
    user_id = get_current_user_id()
    has_access, _ = check_workbench_access(workbench_id, user_id)
    if not has_access:
        return jsonify({'error': 'Access denied'}), 403

    comparison_name = (request.args.get('comparison_name') or '').strip()
    deg_tool = normalize_deg_tool_name(request.args.get('deg_tool'))
    gene_set_db = (request.args.get('gene_set_db') or '').strip().lower()

    if not comparison_name:
        return jsonify({'error': 'comparison_name is required'}), 400
    if not gene_set_db:
        return jsonify({'error': 'gene_set_db is required'}), 400

    try:
        workbench = _get_workbench_context(workbench_id)
        workbench_schema = _get_workbench_schema_for_context(workbench)
        paths = get_gsea_result_paths(workbench_schema, deg_tool, comparison_name, gene_set_db)
        logger.info(
            f"[GSEA] Loading precomputed result: workbench_id={workbench_id}, comparison='{comparison_name}', deg_tool='{deg_tool}', gene_set_db='{gene_set_db}', dir='{paths['dir']}', result_json='{paths['result_json']}', status_json='{paths['status_json']}'"
        )
        stored = load_precomputed_gsea_state(paths)
        if stored:
            comparison_detail = load_gsea_comparison_detail(paths) or {}
            if comparison_detail:
                stored.setdefault('ranking_metric', comparison_detail.get('ranking_metric'))
                stored.setdefault('zero_cross_index', comparison_detail.get('zero_cross_index'))
                if isinstance(stored.get('validation'), dict):
                    stored['validation'].setdefault(
                        'ranked_gene_count',
                        comparison_detail.get('ranked_gene_count'),
                    )
            logger.info(
                f"[GSEA] Returning stored result: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}', state='{stored.get('state', 'ready')}', rows={len(stored.get('rows', [])) if isinstance(stored.get('rows'), list) else 'n/a'}, tested_gene_sets={stored.get('validation', {}).get('tested_gene_sets') if isinstance(stored.get('validation'), dict) else 'n/a'}, ranked_gene_count={stored.get('validation', {}).get('ranked_gene_count') if isinstance(stored.get('validation'), dict) else 'n/a'}, zero_cross_index={stored.get('zero_cross_index')}, database_label='{stored.get('gene_set_db_label', '')}'"
            )
            return jsonify(stored)

        step_status = _get_gsea_step_status(workbench_id)
        logger.info(
            f"[GSEA] No stored result found: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}', gsea_step_status='{step_status}'"
        )
        if step_status in ('pending', 'running'):
            return jsonify({
                'state': 'pending',
                'comparison_name': comparison_name,
                'deg_tool': deg_tool,
                'gene_set_db': gene_set_db,
                'message': 'GSEA precomputation is still in progress',
            })

        if step_status == 'failed':
            logger.info(
                f"[GSEA] Returning failed precomputed state from step status: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}'"
            )
            return jsonify({
                'state': 'failed',
                'comparison_name': comparison_name,
                'deg_tool': deg_tool,
                'gene_set_db': gene_set_db,
                'error_message': 'Precomputed GSEA generation failed for this workbench',
            })

        logger.info(
            f"[GSEA] Returning missing precomputed state: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}'"
        )
        return jsonify({
            'state': 'missing',
            'comparison_name': comparison_name,
            'deg_tool': deg_tool,
            'gene_set_db': gene_set_db,
            'message': 'Precomputed GSEA result is not available yet',
        })
    except Exception as exc:
        logger.error(f"[GSEA] Failed to load precomputed GSEA result: {exc}", exc_info=True)
        return jsonify({'error': 'Failed to load GSEA result'}), 500


@gsea_bp.route('/<int:workbench_id>/gsea/plot-detail', methods=['POST'])
@require_auth
def get_gsea_plot_detail(workbench_id: int):
    user_id = get_current_user_id()
    has_access, _ = check_workbench_access(workbench_id, user_id)
    if not has_access:
        return jsonify({'error': 'Access denied'}), 403

    payload = request.get_json() or {}
    comparison_name = (payload.get('comparison_name') or '').strip()
    deg_tool = normalize_deg_tool_name(payload.get('deg_tool'))
    gene_set_db = (payload.get('gene_set_db') or '').strip().lower()
    gene_set_name = (payload.get('gene_set') or '').strip()

    if not comparison_name:
        return jsonify({'error': 'comparison_name is required'}), 400
    if not gene_set_db:
        return jsonify({'error': 'gene_set_db is required'}), 400
    if not gene_set_name:
        return jsonify({'error': 'gene_set is required'}), 400

    try:
        workbench = _get_workbench_context(workbench_id)
        workbench_schema = _get_workbench_schema_for_context(workbench)
        paths = get_gsea_result_paths(workbench_schema, deg_tool, comparison_name, gene_set_db)
        logger.info(
            f"[GSEA] Plot detail request: workbench_id={workbench_id}, comparison='{comparison_name}', deg_tool='{deg_tool}', gene_set_db='{gene_set_db}', gene_set='{gene_set_name}', detail_dir='{paths['detail_dir']}', min_overlap={MIN_OVERLAP}, max_gene_set_size={MAX_GENE_SET_SIZE}, weight={DEFAULT_WEIGHT}"
        )
        stored_summary = load_precomputed_gsea_state(paths)
        if not stored_summary or stored_summary.get('state') != 'ready':
            logger.warning(
                f"[GSEA] Plot detail unavailable because summary state is not ready: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}', gene_set='{gene_set_name}', state='{stored_summary.get('state') if stored_summary else None}'"
            )
            return jsonify({'error': 'Stored GSEA summary is not ready'}), 409

        database_bundle = load_builtin_gene_sets(
            workbench.get('species', ''),
            gene_set_db,
            workbench.get('username'),
        )
        detail_payload = load_gsea_plot_detail_cache(
            paths,
            gene_set_name,
            comparison_name,
            deg_tool,
            gene_set_db,
            str(stored_summary.get('ranking_metric') or 'logFC'),
            workbench.get('species', ''),
            int((stored_summary.get('validation') or {}).get('permutations', DEFAULT_GSEA_PERMUTATIONS)),
            database_bundle.get('database'),
        )
        if detail_payload:
            logger.info(
                f"[GSEA] Returning cached plot detail: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}', gene_set='{gene_set_name}', leading_edge_size={detail_payload.get('leading_edge_size')}, hit_count={len(detail_payload.get('hit_indices', []))}, running_score_count={len(detail_payload.get('running_scores', []))}"
            )
            return jsonify(detail_payload)

        result_path, resolved_tool = resolve_deg_result_file_from_schema(workbench_schema, comparison_name, deg_tool)
        ranked_list_text, _, rank_key = build_preranked_text_from_deg_result(result_path)
        ranking_profile, zero_cross_index, _ = extract_ranking_profile_from_deg_result(result_path)
        ranked_entries = parse_ranked_gene_list(ranked_list_text)
        gene_set_info = database_bundle['gene_sets'].get(gene_set_name)
        if not gene_set_info:
            return jsonify({'error': f"Gene set not found in database: {gene_set_name}"}), 404

        computed_detail = compute_single_gene_set_detail(
            ranked_entries,
            gene_set_name,
            gene_set_info,
        )
        summary_row = next(
            (
                row
                for row in stored_summary.get('rows', [])
                if row.get('gene_set') == gene_set_name
            ),
            None,
        )
        if not summary_row:
            return jsonify({'error': f"Gene set not found in stored summary: {gene_set_name}"}), 404

        detail_payload = {
            'comparison_name': comparison_name,
            'deg_tool': resolved_tool,
            'gene_set_db': gene_set_db,
            'gene_set': gene_set_name,
            'database_metadata': database_bundle.get('database'),
            'species': workbench.get('species', ''),
            'ranking_metric': rank_key,
            'permutations': int((stored_summary.get('validation') or {}).get('permutations', DEFAULT_GSEA_PERMUTATIONS)),
            'ranking_profile': ranking_profile,
            'zero_cross_index': zero_cross_index,
            'description': summary_row.get('description', ''),
            'gene_set_size': summary_row.get('gene_set_size'),
            'overlap_size': summary_row.get('overlap_size'),
            'es': summary_row.get('es'),
            'nes': summary_row.get('nes'),
            'p_value': summary_row.get('p_value'),
            'fdr': summary_row.get('fdr'),
            'leading_edge_size': computed_detail.get('leading_edge_size'),
            'leading_edge_genes': computed_detail.get('leading_edge_genes'),
            'hit_genes': computed_detail.get('hit_genes'),
            'hit_indices': computed_detail.get('hit_indices'),
            'hit_scores': computed_detail.get('hit_scores'),
            'running_scores': computed_detail.get('running_scores'),
            'peak_index': computed_detail.get('peak_index'),
        }
        save_gsea_plot_detail_cache(paths, detail_payload)
        logger.info(
            f"[GSEA] Returning computed plot detail: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}', gene_set='{gene_set_name}', leading_edge_size={detail_payload.get('leading_edge_size')}, hit_count={len(detail_payload.get('hit_indices', []))}, running_score_count={len(detail_payload['running_scores'])}, peak_index={detail_payload.get('peak_index')}, min_overlap={MIN_OVERLAP}, max_gene_set_size={MAX_GENE_SET_SIZE}, weight={DEFAULT_WEIGHT}, permutations={detail_payload.get('permutations')}"
        )
        return jsonify(detail_payload)
    except FileNotFoundError as exc:
        logger.warning(
            f"[GSEA] Plot detail DEG result file missing: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}', gene_set='{gene_set_name}', error='{exc}'"
        )
        return jsonify({'error': str(exc)}), 404
    except GSEAValidationError as exc:
        logger.warning(
            f"[GSEA] Plot detail validation error: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{gene_set_db}', gene_set='{gene_set_name}', error='{exc}'"
        )
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error(f"[GSEA] Failed to build GSEA plot detail: {exc}", exc_info=True)
        return jsonify({'error': 'Failed to load GSEA plot detail'}), 500


@gsea_bp.route('/<int:workbench_id>/gsea/validation-inputs', methods=['GET'])
@require_auth
def get_gsea_validation_inputs(workbench_id: int):
    user_id = get_current_user_id()
    has_access, _ = check_workbench_access(workbench_id, user_id)
    if not has_access:
        return jsonify({'error': 'Access denied'}), 403

    comparison_name = (request.args.get('comparison_name') or '').strip()
    deg_tool = normalize_deg_tool_name(request.args.get('deg_tool'))
    gene_set_db = (request.args.get('gene_set_db') or '').strip().lower()

    if not comparison_name:
        return jsonify({'error': 'comparison_name is required'}), 400
    if not gene_set_db:
        return jsonify({'error': 'gene_set_db is required'}), 400

    try:
        workbench = _get_workbench_context(workbench_id)
        workbench_schema = _get_workbench_schema_for_context(workbench)
        result_path, resolved_tool = resolve_deg_result_file_from_schema(workbench_schema, comparison_name, deg_tool)
        ranked_list_text, gene_count, rank_key = build_preranked_text_from_deg_result(result_path)
        database_bundle = load_builtin_gene_sets(
            workbench.get('species', ''),
            gene_set_db,
            workbench.get('username'),
        )
        gmt_text = _build_gmt_text(database_bundle)
        readme_text = _build_validation_readme(
            workbench,
            comparison_name,
            resolved_tool,
            database_bundle,
            rank_key,
            gene_count,
            _get_selected_gsea_permutations(workbench_id),
        )

        return jsonify({
            'comparison_name': comparison_name,
            'deg_tool': resolved_tool,
            'gene_set_db': database_bundle['database']['key'],
            'gene_set_db_label': database_bundle['database']['label'],
            'ranking_metric': rank_key,
            'ranked_gene_count': gene_count,
            'ranked_filename': f"{comparison_name}.{resolved_tool}.{rank_key}.rnk",
            'ranked_list_text': ranked_list_text,
            'gmt_filename': f"{database_bundle['database']['key']}.{workbench.get('species', '').replace(' ', '_')}.gmt",
            'gmt_text': gmt_text,
            'readme_filename': f"README_GSEA_validation_{comparison_name}.{database_bundle['database']['key']}.txt",
            'readme_text': readme_text,
        })
    except FileNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except GSEAValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error(f"[GSEA] Failed to build validation inputs: {exc}", exc_info=True)
        return jsonify({'error': 'Failed to build GSEA validation inputs'}), 500


@gsea_bp.route('/<int:workbench_id>/gsea/deg-comparison', methods=['POST'])
@require_auth
def run_workbench_comparison_gsea(workbench_id: int):
    user_id = get_current_user_id()
    has_access, _ = check_workbench_access(workbench_id, user_id)
    if not has_access:
        return jsonify({'error': 'Access denied'}), 403

    payload = request.get_json() or {}
    comparison_name = (payload.get('comparison_name') or '').strip()
    deg_tool = normalize_deg_tool_name(payload.get('deg_tool'))
    gene_set_db = (payload.get('gene_set_db') or '').strip().lower()

    if not comparison_name:
        return jsonify({'error': 'comparison_name is required'}), 400
    if not gene_set_db:
        return jsonify({'error': 'gene_set_db is required'}), 400

    try:
        workbench = _get_workbench_context(workbench_id)
        logger.info(
            f"[GSEA] Run comparison GSEA request: workbench_id={workbench_id}, workbench='{workbench.get('name', '')}', species='{workbench.get('species', '')}', comparison='{comparison_name}', deg_tool='{deg_tool}', gene_set_db='{gene_set_db}'"
        )
        return jsonify(_build_comparison_gsea_payload(workbench, comparison_name, deg_tool, gene_set_db))
    except FileNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except GSEAValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error(f"[GSEA] Failed to run comparison GSEA: {exc}", exc_info=True)
        return jsonify({'error': 'Failed to run comparison GSEA'}), 500


@gsea_bp.route('/<int:workbench_id>/gsea/preranked', methods=['POST'])
@require_auth
def run_workbench_preranked_gsea(workbench_id: int):
    user_id = get_current_user_id()
    has_access, _ = check_workbench_access(workbench_id, user_id)
    if not has_access:
        return jsonify({'error': 'Access denied'}), 403

    payload = request.get_json() or {}
    comparison_name = (payload.get('comparison_name') or '').strip()
    deg_tool = (payload.get('deg_tool') or '').strip()
    ranked_list_text = payload.get('ranked_list_text') or ''
    gmt_temp_file = (payload.get('gmt_temp_file') or '').strip()

    if not ranked_list_text.strip():
        return jsonify({'error': 'ranked_list_text is required'}), 400
    if not gmt_temp_file:
        return jsonify({'error': 'gmt_temp_file is required'}), 400

    try:
        gmt_path = _get_user_temp_file_path(gmt_temp_file)
        if not os.path.exists(gmt_path):
            return jsonify({'error': 'GMT temp file was not found'}), 404

        ranked_entries = parse_ranked_gene_list(ranked_list_text)
        gene_sets = parse_gmt_file(gmt_path)
        result = run_preranked_gsea(ranked_entries, gene_sets, permutations=DEFAULT_GSEA_PERMUTATIONS)

        return jsonify({
            'comparison_name': comparison_name,
            'deg_tool': deg_tool,
            'ranking_metric': 'logFC' if comparison_name else 'user_supplied',
            'validation': {
                'ranked_gene_count': result['ranked_gene_count'],
                'tested_gene_sets': result['tested_gene_sets'],
                'min_overlap': result['min_overlap'],
                'permutations': result['permutations'],
            },
            'rows': result['rows'],
        })
    except GSEAValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error(f"[GSEA] Failed to run preranked GSEA: {exc}", exc_info=True)
        return jsonify({'error': 'Failed to run preranked GSEA'}), 500
