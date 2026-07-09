import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List

import pandas as pd

from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.pipeline.utils.expression_matrix import (
    run_tmm_normalization,
    run_tmm_normalization_from_counts_native,
    reorder_matrix_samples,
)
from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'INFO')


def _load_latest_samples_json(workbench_id: int):
    with database.get_db_connection() as conn:
        row = conn.execute(
            '''
            SELECT samples
            FROM vizr_pipeline_samples
            WHERE workbench_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            ''',
            (workbench_id,)
        ).fetchone()
    return json.loads(row['samples']) if row and row['samples'] else []


def _write_samples_file(samples_dir: str, target_samples: List[Dict]) -> str:
    os.makedirs(samples_dir, exist_ok=True)
    samples_file = os.path.join(samples_dir, 'samples.txt')
    with open(samples_file, 'w', encoding='utf-8') as handle:
        for sample in target_samples:
            handle.write(f"{sample.get('groupName', '')}\t{sample.get('sampleName', '')}\n")
    return samples_file


def execute_imported_counts(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    try:
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        workbench_id = job_step['workbench_id']
        source_data = parameters.get('source_workbench_data', {}) or {}
        selected_samples = source_data.get('selected_samples', [])
        has_tpm_matrix = bool(source_data.get('has_tpm_matrix', parameters.get('has_tpm_matrix', True)))
        if not selected_samples:
            raise ValueError('No imported source samples were provided')

        with database.get_db_connection() as conn:
            target_workbench = conn.execute(
                'SELECT * FROM vizr_workbench WHERE id = ?',
                (workbench_id,)
            ).fetchone()

        if not target_workbench:
            raise ValueError(f'Workbench {workbench_id} not found')

        target_schema = get_workbench_schema(target_workbench['name'], target_workbench['user_id'])
        counts_dir = target_schema['quanti']['counts']
        samples_dir = target_schema['quanti']['samples']
        os.makedirs(counts_dir, exist_ok=True)
        os.makedirs(samples_dir, exist_ok=True)

        target_samples = _load_latest_samples_json(workbench_id)
        target_sample_order = [sample.get('sampleName', '') for sample in target_samples if sample.get('sampleName')]

        cached_matrices: Dict[int, Dict[str, pd.DataFrame]] = {}
        merged_counts_parts: List[pd.DataFrame] = []
        merged_tpm_parts: List[pd.DataFrame] = []

        for selected in selected_samples:
            source_workbench_id = selected['source_workbench_id']
            if source_workbench_id not in cached_matrices:
                with database.get_db_connection() as conn:
                    source_workbench = conn.execute(
                        'SELECT * FROM vizr_workbench WHERE id = ?',
                        (source_workbench_id,)
                    ).fetchone()

                if not source_workbench:
                    raise ValueError(f'Source workbench {source_workbench_id} not found')

                source_schema = get_workbench_schema(source_workbench['name'], source_workbench['user_id'])
                counts_path = os.path.join(source_schema['quanti']['counts'], 'genes.counts.matrix')
                tpm_path = os.path.join(source_schema['quanti']['counts'], 'genes.TPM.matrix')

                counts_df = pd.read_csv(counts_path, sep='\t')
                counts_df = counts_df.rename(columns={counts_df.columns[0]: 'gene_id'})
                counts_df = counts_df.set_index('gene_id')
                tpm_df = None
                if has_tpm_matrix and os.path.exists(tpm_path):
                    tpm_df = pd.read_csv(tpm_path, sep='\t')
                    tpm_df = tpm_df.rename(columns={tpm_df.columns[0]: 'gene_id'})
                    tpm_df = tpm_df.set_index('gene_id')
                cached_matrices[source_workbench_id] = {
                    'counts': counts_df,
                    'tpm': tpm_df
                }

            source_sample_name = selected['source_sample_name']
            target_sample_name = selected['target_sample_name']
            source_counts = cached_matrices[source_workbench_id]['counts']
            source_tpm = cached_matrices[source_workbench_id]['tpm']

            if source_sample_name not in source_counts.columns:
                raise ValueError(f"Sample '{source_sample_name}' was not found in source workbench {source_workbench_id}")
            if has_tpm_matrix and (source_tpm is None or source_sample_name not in source_tpm.columns):
                raise ValueError(f"Sample '{source_sample_name}' TPM matrix was not found in source workbench {source_workbench_id}")

            merged_counts_parts.append(source_counts[[source_sample_name]].rename(columns={source_sample_name: target_sample_name}))
            if has_tpm_matrix and source_tpm is not None:
                merged_tpm_parts.append(source_tpm[[source_sample_name]].rename(columns={source_sample_name: target_sample_name}))

        merged_counts = pd.concat(merged_counts_parts, axis=1, join='outer').fillna(0)

        counts_output = os.path.join(counts_dir, 'genes.counts.matrix')
        merged_counts.reset_index().to_csv(counts_output, sep='\t', index=False)

        tpm_output = None
        if has_tpm_matrix and merged_tpm_parts:
            merged_tpm = pd.concat(merged_tpm_parts, axis=1, join='outer').fillna(0)
            tpm_output = os.path.join(counts_dir, 'genes.TPM.matrix')
            merged_tpm.reset_index().to_csv(tpm_output, sep='\t', index=False)

        if tpm_output:
            tmm_result = run_tmm_normalization(counts_dir, tpm_output)
            tmm_generation_mode = 'tpm_legacy'
        else:
            tmm_result = run_tmm_normalization_from_counts_native(counts_dir, counts_output)
            tmm_generation_mode = 'counts_native'

        if not tmm_result.get('success'):
            raise RuntimeError(tmm_result.get('error', 'Failed to create genes.TMM.matrix'))

        if target_sample_order:
            reorder_matrix_samples(counts_output, target_sample_order)
            if tpm_output and os.path.exists(tpm_output):
                reorder_matrix_samples(tpm_output, target_sample_order)
            reorder_matrix_samples(tmm_result['tmm_matrix_file'], target_sample_order)

        samples_file = _write_samples_file(samples_dir, target_samples)
        provenance_file = os.path.join(counts_dir, 'import_sources.json')
        provenance_payload = dict(source_data)
        provenance_payload['has_tpm_matrix'] = bool(tpm_output)
        provenance_payload['tmm_generation_mode'] = tmm_generation_mode
        with open(provenance_file, 'w', encoding='utf-8') as handle:
            json.dump(provenance_payload, handle, indent=2, ensure_ascii=False)

        logger.info(
            "[IMPORTED-COUNTS] Created merged matrices for workbench %s with %s samples",
            workbench_id,
            len(selected_samples)
        )
        return {
            'success': True,
            'stdout': f'Imported {len(selected_samples)} samples from existing workbenches',
            'stderr': '',
            'timestamp': datetime.now().isoformat(),
            'counts_matrix_file': counts_output,
            'tpm_matrix_file': tpm_output,
            'samples_file': samples_file
        }
    except Exception as e:
        logger.error(f"[IMPORTED-COUNTS] Failed to build imported count matrices: {e}")
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'timestamp': datetime.now().isoformat()
        }


def REGISTER_TOOL(coordinator):
    metadata = {
        'name': 'imported_counts',
        'description': 'Merge counts/TPM matrices from existing workbenches and regenerate TMM',
        'version': '1.0.0',
        'parameters': {}
    }
    return coordinator.register_tool('imported_counts', execute_imported_counts, metadata)
