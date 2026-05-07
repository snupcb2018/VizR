"""
Precompute built-in GSEA results for all DEG comparisons.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.blueprints.workbench_utils import get_workbench_schema
from backend.pipeline.utils.gsea_builtin_db import (
    ensure_provisioned_gsea_databases,
    get_available_builtin_gsea_databases,
    load_builtin_gene_sets,
)
from backend.pipeline.utils.gsea_preranked import parse_ranked_gene_list, run_preranked_gsea
from backend.pipeline.utils.gsea_preranked import (
    DEFAULT_PERMUTATIONS,
    DEFAULT_WEIGHT,
    MAX_GENE_SET_SIZE,
    MIN_OVERLAP,
)
from backend.pipeline.utils.gsea_result_store import (
    can_reuse_precomputed_gsea_result,
    build_preranked_text_from_deg_result,
    discover_deg_result_files,
    extract_ranking_profile_from_deg_result,
    get_gsea_output_dir,
    get_gsea_result_paths,
    save_precomputed_gsea_failure,
    save_precomputed_gsea_result,
)
from backend.utils import database
from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'INFO')

LEGACY_GSEA_DATABASES = ['go_bp', 'kegg']
DEFAULT_GSEA_PERMUTATIONS = DEFAULT_PERMUTATIONS


def _write_summary(summary_path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def execute_builtin_preranked(job_step, worker_id: str = "worker") -> dict[str, Any]:
    try:
        workbench_id = job_step['workbench_id']
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        preferred_deg_tool = parameters.get('deg_tool', 'edgeR')
        database_scope = parameters.get('database_scope', 'legacy')
        requested_databases = parameters.get('built_in_databases') or []
        permutations = DEFAULT_GSEA_PERMUTATIONS
        if database_scope == 'legacy':
            requested_databases = LEGACY_GSEA_DATABASES
        logger.info(
            f"[GSEA-PRECOMPUTE] Requested database scope: workbench_id={job_step['workbench_id']}, scope='{database_scope}', requested_databases={requested_databases}, permutations={permutations}"
        )

        with database.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            workbench = conn.execute(
                """
                SELECT w.id, w.name, w.user_id, w.species, u.username
                FROM vizr_workbench w
                JOIN users u ON u.id = w.user_id
                WHERE w.id = ?
                """,
                (workbench_id,),
            ).fetchone()

        if not workbench:
            return {'success': True, 'had_failures': True, 'error': f'Workbench {workbench_id} not found'}

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        provisioning = ensure_provisioned_gsea_databases(
            workbench['species'],
            requested_databases,
            workbench['username'],
        )
        available_databases = provisioning['databases'] or get_available_builtin_gsea_databases(
            workbench['species'],
            requested_databases,
            workbench['username'],
        )
        database_entries = [db for db in available_databases if db['key'] in requested_databases]
        logger.info(
            f"[GSEA-PRECOMPUTE] Database resolution: workbench_id={workbench_id}, available={[db['key'] for db in available_databases]}, selected={[db['key'] for db in database_entries]}, failures={[failure.get('key') for failure in provisioning.get('failures', [])]}"
        )
        comparisons = discover_deg_result_files(workbench_schema, preferred_deg_tool)

        logger.info(
            f"[GSEA-PRECOMPUTE] Starting: workbench_id={workbench_id}, comparisons={len(comparisons)}, databases={[db['key'] for db in database_entries]}"
        )

        summary: dict[str, Any] = {
            'workbench_id': workbench_id,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'deg_tool': preferred_deg_tool,
            'species': workbench['species'],
            'database_provisioning': provisioning,
            'results': [],
        }
        had_failures = bool(provisioning.get('failures'))

        for comparison in comparisons:
            comparison_name = comparison['comparison_name']
            resolved_tool = comparison['deg_tool']
            result_path = comparison['result_path']

            try:
                ranked_list_text, _, rank_key = build_preranked_text_from_deg_result(result_path)
                ranking_profile, zero_cross_index, resolved_rank_key = extract_ranking_profile_from_deg_result(result_path)
                ranked_entries = parse_ranked_gene_list(ranked_list_text)
            except Exception as exc:
                had_failures = True
                summary['results'].append({
                    'comparison_name': comparison_name,
                    'deg_tool': resolved_tool,
                    'state': 'failed',
                    'error_message': str(exc),
                })
                continue

            for database_entry in database_entries:
                db_key = database_entry['key']
                paths = get_gsea_result_paths(workbench_schema, resolved_tool, comparison_name, db_key)
                try:
                    logger.info(
                        f"[GSEA-PRECOMPUTE] Comparison/database start: workbench_id={workbench_id}, comparison='{comparison_name}', deg_tool='{resolved_tool}', gene_set_db='{db_key}', result_path='{result_path}', permutations={permutations}, min_overlap={MIN_OVERLAP}, max_gene_set_size={MAX_GENE_SET_SIZE}, weight={DEFAULT_WEIGHT}"
                    )
                    db_bundle = load_builtin_gene_sets(workbench['species'], db_key, workbench['username'])
                    logger.info(
                        f"[GSEA-PRECOMPUTE] Database bundle loaded: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{db_key}', database_label='{db_bundle['database']['label']}', database_source='{db_bundle['database'].get('source', '')}', database_generation_date='{db_bundle['database'].get('generation_date', '')}', gene_set_count={len(db_bundle['gene_sets'])}, ranked_gene_count={len(ranked_entries)}"
                    )
                    if can_reuse_precomputed_gsea_result(
                        paths=paths,
                        comparison_name=comparison_name,
                        deg_tool=resolved_tool,
                        gene_set_db=db_bundle['database']['key'],
                        ranking_metric=resolved_rank_key or rank_key,
                        species=workbench['species'],
                        permutations=permutations,
                        database_metadata=db_bundle['database'],
                    ):
                        logger.info(
                            f"[GSEA-PRECOMPUTE] Reused precomputed result: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{db_key}', output_dir='{paths['dir']}'"
                        )
                        summary['results'].append({
                            'comparison_name': comparison_name,
                            'deg_tool': resolved_tool,
                            'gene_set_db': db_key,
                            'state': 'ready',
                            'output_dir': get_gsea_output_dir(workbench_schema, resolved_tool, comparison_name, db_key),
                            'cache_reused': True,
                        })
                        continue
                    result = run_preranked_gsea(ranked_entries, db_bundle['gene_sets'], permutations=permutations)
                    top_gene_set = result['rows'][0]['gene_set'] if result.get('rows') else ''
                    top_nes = result['rows'][0]['nes'] if result.get('rows') else None
                    logger.info(
                        f"[GSEA-PRECOMPUTE] Calculation complete: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{db_key}', tested_gene_sets={result['tested_gene_sets']}, ranked_gene_count={result['ranked_gene_count']}, min_overlap={result['min_overlap']}, max_gene_set_size={result['max_gene_set_size']}, permutations={result['permutations']}, weight={DEFAULT_WEIGHT}, row_count={len(result.get('rows', []))}, top_gene_set='{top_gene_set}', top_nes={top_nes}"
                    )
                    payload = {
                        'comparison_name': comparison_name,
                        'deg_tool': resolved_tool,
                        'gene_set_db': db_bundle['database']['key'],
                        'gene_set_db_label': db_bundle['database']['label'],
                        'database_metadata': db_bundle['database'],
                        'ranking_metric': resolved_rank_key or rank_key,
                        'ranking_profile': ranking_profile,
                        'zero_cross_index': zero_cross_index,
                        'validation': {
                            'ranked_gene_count': result['ranked_gene_count'],
                            'tested_gene_sets': result['tested_gene_sets'],
                            'min_overlap': result['min_overlap'],
                            'permutations': result['permutations'],
                        },
                        'rows': result['rows'],
                    }
                    save_precomputed_gsea_result(paths, payload)
                    try:
                        result_json_size = os.path.getsize(paths['result_json']) if os.path.exists(paths['result_json']) else 0
                        comparison_detail_size = os.path.getsize(paths['comparison_detail_json']) if os.path.exists(paths['comparison_detail_json']) else 0
                        results_csv_size = os.path.getsize(paths['results_csv']) if os.path.exists(paths['results_csv']) else 0
                        leading_edge_csv_size = os.path.getsize(paths['leading_edge_csv']) if os.path.exists(paths['leading_edge_csv']) else 0
                    except OSError:
                        result_json_size = comparison_detail_size = results_csv_size = leading_edge_csv_size = 0
                    logger.info(
                        f"[GSEA-PRECOMPUTE] Result saved: workbench_id={workbench_id}, comparison='{comparison_name}', gene_set_db='{db_key}', output_dir='{paths['dir']}', result_json_size={result_json_size}, comparison_detail_size={comparison_detail_size}, results_csv_size={results_csv_size}, leading_edge_csv_size={leading_edge_csv_size}"
                    )
                    summary['results'].append({
                        'comparison_name': comparison_name,
                        'deg_tool': resolved_tool,
                        'gene_set_db': db_key,
                        'state': 'ready',
                        'output_dir': get_gsea_output_dir(workbench_schema, resolved_tool, comparison_name, db_key),
                        'tested_gene_sets': result['tested_gene_sets'],
                    })
                except Exception as exc:
                    had_failures = True
                    logger.error(
                        f"[GSEA-PRECOMPUTE] Comparison/database failed: workbench_id={workbench_id}, comparison='{comparison_name}', deg_tool='{resolved_tool}', gene_set_db='{db_key}', error='{exc}'",
                        exc_info=True,
                    )
                    save_precomputed_gsea_failure(paths, comparison_name, resolved_tool, db_key, str(exc))
                    summary['results'].append({
                        'comparison_name': comparison_name,
                        'deg_tool': resolved_tool,
                        'gene_set_db': db_key,
                        'state': 'failed',
                        'error_message': str(exc),
                    })

        summary_path = os.path.join(workbench_schema['deg'], preferred_deg_tool, 'gsea', 'summary.json')
        _write_summary(summary_path, summary)
        return {
            'success': True,
            'had_failures': had_failures,
            'summary_path': summary_path,
            'result_count': len(summary['results']),
        }
    except Exception as exc:
        logger.error(f"[GSEA-PRECOMPUTE] Unexpected failure: {exc}", exc_info=True)
        return {
            'success': True,
            'had_failures': True,
            'error': str(exc),
        }


def REGISTER_TOOL(coordinator):
    return coordinator.register_tool(
        'builtin_preranked',
        execute_builtin_preranked,
        metadata={'description': 'Precompute built-in preranked GSEA results'},
    )
