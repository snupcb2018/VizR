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
from config.shared_config import SharedConfig

logger = setup_module_logger(__name__, 'INFO')

IMPORTED_MATRIX_FILES_LOG_MARKER = "IMPORTED_MATRIX_FILES_CODE_V2026_03_13_01"


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


def _load_matrix(file_path: str, label: str) -> pd.DataFrame:
    df = pd.read_csv(file_path, sep='\t')
    first_column = df.columns[0]
    if first_column not in ('gene_id', 'GeneID'):
        raise ValueError(f"{label} must start with a gene_id or GeneID column")
    df = df.rename(columns={first_column: 'gene_id'})
    if df['gene_id'].astype(str).str.strip().eq('').any():
        raise ValueError(f"{label} contains blank gene_id values")
    if df['gene_id'].duplicated().any():
        raise ValueError(f"{label} contains duplicate gene_id values")
    return df.set_index('gene_id')


def execute_imported_matrix_files(job_step: sqlite3.Row, worker_id: str = "worker") -> Dict[str, str]:
    try:
        plugin_mtime = datetime.fromtimestamp(os.path.getmtime(__file__)).isoformat()
        parameters = json.loads(job_step['parameters']) if job_step['parameters'] else {}
        workbench_id = job_step['workbench_id']
        matrix_file_data = parameters.get('matrix_file_data', {}) or {}
        counts_temp_file = matrix_file_data.get('counts_temp_file')
        tpm_temp_file = matrix_file_data.get('tpm_temp_file')
        has_tpm_matrix = bool(matrix_file_data.get('has_tpm_matrix'))

        logger.info(
            "[IMPORTED-MATRIX-FILES] Plugin marker=%s file=%s mtime=%s workbench_id=%s has_tpm_matrix=%s",
            IMPORTED_MATRIX_FILES_LOG_MARKER,
            __file__,
            plugin_mtime,
            workbench_id,
            has_tpm_matrix
        )

        if not counts_temp_file:
            raise ValueError('Counts matrix temp file was not provided')

        with database.get_db_connection() as conn:
            target_workbench = conn.execute(
                'SELECT w.*, u.username FROM vizr_workbench w JOIN users u ON w.user_id = u.id WHERE w.id = ?',
                (workbench_id,)
            ).fetchone()

        if not target_workbench:
            raise ValueError(f'Workbench {workbench_id} not found')

        temp_dir = os.path.join(SharedConfig.VIZR_PATH, 'users', target_workbench['username'], 'tmp')
        counts_path = os.path.join(temp_dir, counts_temp_file)
        tpm_path = os.path.join(temp_dir, tpm_temp_file) if tpm_temp_file else None

        if not os.path.exists(counts_path):
            raise ValueError(f'Counts matrix temp file not found: {counts_temp_file}')
        if has_tpm_matrix and (not tpm_path or not os.path.exists(tpm_path)):
            raise ValueError(f'TPM matrix temp file not found: {tpm_temp_file}')

        counts_df = _load_matrix(counts_path, 'Counts matrix')
        tpm_df = _load_matrix(tpm_path, 'TPM matrix') if has_tpm_matrix and tpm_path else None

        if tpm_df is not None:
            if set(counts_df.columns) != set(tpm_df.columns):
                raise ValueError('Counts and TPM matrices must contain the same sample columns')
            if set(counts_df.index) != set(tpm_df.index):
                raise ValueError('Counts and TPM matrices must contain the same gene_id set')

        target_samples = _load_latest_samples_json(workbench_id)
        if not target_samples:
            raise ValueError('No target sample mapping was found')

        rename_map = {}
        target_sample_order = []
        for sample in target_samples:
            source_column = sample.get('sourceColumnName') or sample.get('sourceSampleName')
            target_name = sample.get('sampleName')
            if not source_column or not target_name:
                raise ValueError('Invalid sample mapping: sourceColumnName and sampleName are required')
            if source_column not in counts_df.columns:
                raise ValueError(f"Sample column '{source_column}' not found in counts matrix")
            if tpm_df is not None and source_column not in tpm_df.columns:
                raise ValueError(f"Sample column '{source_column}' not found in TPM matrix")
            rename_map[source_column] = target_name
            target_sample_order.append(target_name)

        selected_source_columns = list(rename_map.keys())
        counts_df = counts_df[selected_source_columns].rename(columns=rename_map)
        if tpm_df is not None:
            tpm_df = tpm_df[selected_source_columns].rename(columns=rename_map)

        target_schema = get_workbench_schema(target_workbench['name'], target_workbench['user_id'])
        counts_dir = target_schema['quanti']['counts']
        samples_dir = target_schema['quanti']['samples']
        os.makedirs(counts_dir, exist_ok=True)
        os.makedirs(samples_dir, exist_ok=True)

        counts_output = os.path.join(counts_dir, 'genes.counts.matrix')
        counts_df.reset_index().to_csv(counts_output, sep='\t', index=False)

        tpm_output = None
        if tpm_df is not None:
            tpm_output = os.path.join(counts_dir, 'genes.TPM.matrix')
            tpm_df.reset_index().to_csv(tpm_output, sep='\t', index=False)

        if tpm_output:
            logger.info(
                "[IMPORTED-MATRIX-FILES] Marker=%s using TPM-based legacy TMM path: %s",
                IMPORTED_MATRIX_FILES_LOG_MARKER,
                tpm_output
            )
            tmm_result = run_tmm_normalization(counts_dir, tpm_output)
            tmm_generation_mode = 'tpm_legacy'
        else:
            logger.info(
                "[IMPORTED-MATRIX-FILES] Marker=%s using counts-based TMM path: %s",
                IMPORTED_MATRIX_FILES_LOG_MARKER,
                counts_output
            )
            tmm_result = run_tmm_normalization_from_counts_native(counts_dir, counts_output)
            tmm_generation_mode = 'counts_native'

        if not tmm_result.get('success'):
            raise RuntimeError(tmm_result.get('error', 'Failed to create genes.TMM.matrix'))

        reorder_matrix_samples(counts_output, target_sample_order)
        if tpm_output and os.path.exists(tpm_output):
            reorder_matrix_samples(tpm_output, target_sample_order)
        reorder_matrix_samples(tmm_result['tmm_matrix_file'], target_sample_order)

        samples_file = _write_samples_file(samples_dir, target_samples)
        provenance_file = os.path.join(counts_dir, 'imported_matrix_sources.json')
        provenance_payload = dict(matrix_file_data)
        provenance_payload['tmm_generation_mode'] = tmm_generation_mode
        with open(provenance_file, 'w', encoding='utf-8') as handle:
            json.dump(provenance_payload, handle, indent=2, ensure_ascii=False)

        logger.info(
            "[IMPORTED-MATRIX-FILES] Prepared matrices for workbench %s with %s samples (TPM=%s, tmm_mode=%s)",
            workbench_id,
            len(target_samples),
            bool(tpm_output),
            tmm_generation_mode
        )
        return {
            'success': True,
            'stdout': f'Prepared imported matrices for {len(target_samples)} samples',
            'stderr': '',
            'timestamp': datetime.now().isoformat(),
            'counts_matrix_file': counts_output,
            'tpm_matrix_file': tpm_output,
            'samples_file': samples_file
        }
    except Exception as e:
        logger.error(f"[IMPORTED-MATRIX-FILES] Failed to prepare imported matrix files: {e}")
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'timestamp': datetime.now().isoformat()
        }


def REGISTER_TOOL(coordinator):
    metadata = {
        'name': 'imported_matrix_files',
        'description': 'Prepare uploaded counts/optional TPM matrices and regenerate TMM',
        'version': '1.0.0',
        'parameters': {}
    }
    return coordinator.register_tool('imported_matrix_files', execute_imported_matrix_files, metadata)
