"""
PCA Analysis Results API
Principal Component Analysis visualization and data API for RNA-seq count matrices
"""

import os
import json
import pandas as pd
import numpy as np
from flask import Blueprint, jsonify, request, session
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform
from backend.utils.database import get_db_connection
from backend.blueprints.auth import require_auth
from backend.blueprints.workbench_utils import get_workbench_schema
from backend.blueprints.workbench_share import check_workbench_access
from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'INFO')

pca_bp = Blueprint('pca', __name__, url_prefix='/api/workbenches')


def get_workbench_pca_dir(workbench_name: str, user_id: int) -> str:
    """
    Get PCA analysis directory for workbench

    Args:
        workbench_name: Workbench name
        user_id: User ID

    Returns:
        str: Path to PCA analysis directory
    """
    workbench_schema = get_workbench_schema(workbench_name, user_id)
    counts_dir = workbench_schema['quanti']['counts']
    pca_dir = os.path.join(counts_dir, 'pca_results')
    return pca_dir


def read_pca_data_file(file_path: str, sep='\t', header=0, index_col=0):
    """
    Read PCA data file (TSV format)

    Args:
        file_path: Path to data file
        sep: Column separator
        header: Header row index
        index_col: Index column

    Returns:
        pd.DataFrame: Loaded data
    """
    try:
        df = pd.read_csv(file_path, sep=sep, header=header, index_col=index_col)
        return df
    except Exception as e:
        logger.error(f"❌ [PCA-DATA] Failed to read {file_path}: {e}")
        raise


@pca_bp.route('/<int:workbench_id>/pca/data', methods=['GET'])
@require_auth
def get_pca_data(workbench_id):
    """
    Get PCA scores, loadings, and variance explained

    Response:
    {
        "workbench_id": 1,
        "pca_scores": [...],  # Sample coordinates in PC space
        "variance_explained": [...],  # Variance explained by each PC
        "samples": [...],  # Sample names
        "num_components": 12,
        "status": "available"
    }
    """
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [PCA-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        logger.info(f"✅ [PCA-API] Workbench access granted (permission: {permission})")

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            pca_dir = get_workbench_pca_dir(workbench['name'], workbench['user_id'])
            # Read PCA scores (sample coordinates in PC space)
            scores_file = os.path.join(pca_dir, 'genes.counts.matrix.minRow10.CPM.log2.centered.PCA.prcomp.scores')

            if not os.path.exists(scores_file):
                logger.info(f"ℹ️ [PCA-API] PCA data not available for workbench {workbench_id}")
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': 'not_available',
                    'message': 'PCA analysis not yet performed'
                }), 200

            # Read PCA scores
            scores_df = read_pca_data_file(scores_file)

            # Calculate variance explained from loadings file
            loadings_file = os.path.join(pca_dir, 'genes.counts.matrix.minRow10.CPM.log2.centered.PCA.prcomp.loadings')
            variance_explained = None

            if os.path.exists(loadings_file):
                try:
                    loadings_df = read_pca_data_file(loadings_file)
                    # Calculate variance for each PC
                    variances = loadings_df.var(axis=0)
                    total_variance = variances.sum()
                    variance_explained = ((variances / total_variance) * 100).to_dict()
                except Exception as e:
                    logger.warning(f"⚠️ [PCA-API] Could not calculate variance explained: {e}")

            # Convert to dictionary
            pca_scores_dict = scores_df.to_dict(orient='index')

            pca_data = {
                'workbench_id': workbench_id,
                'pca_scores': pca_scores_dict,
                'samples': list(scores_df.index),
                'components': list(scores_df.columns),
                'num_components': len(scores_df.columns),
                'variance_explained': variance_explained,
                'status': 'available'
            }

            return jsonify(pca_data), 200

    except Exception as e:
        logger.error(f"❌ [PCA-API] Error getting PCA data: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@pca_bp.route('/<int:workbench_id>/pca/loadings', methods=['GET'])
@require_auth
def get_pca_loadings(workbench_id):
    """
    Get PCA loadings (gene contributions to principal components)

    Query params:
        - page: Page number (default: 1)
        - page_size: Number of genes per page (default: 50)
        - pc: Principal component to sort by (default: PC1)
        - sort_order: asc or desc (default: desc for absolute values)

    Response:
    {
        "workbench_id": 1,
        "loadings": [...],
        "genes": [...],
        "components": [...],
        "total_genes": 25000,
        "current_page": 1,
        "total_pages": 500,
        "status": "available"
    }
    """
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    pc = request.args.get('pc', 'PC1', type=str)
    sort_order = request.args.get('sort_order', 'desc', type=str)

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [PCA-LOADINGS-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            pca_dir = get_workbench_pca_dir(workbench['name'], workbench['user_id'])
            # Read PCA loadings (gene contributions to principal components)
            loadings_file = os.path.join(pca_dir, 'genes.counts.matrix.minRow10.CPM.log2.centered.PCA.prcomp.loadings')

            if not os.path.exists(loadings_file):
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': 'not_available',
                    'message': 'PCA loadings not available'
                }), 200

            # Read loadings file (from .scores file due to R script naming)
            loadings_df = read_pca_data_file(loadings_file)

            # Sort by absolute loading value for specified PC
            if pc in loadings_df.columns:
                loadings_df['abs_loading'] = loadings_df[pc].abs()
                loadings_df = loadings_df.sort_values('abs_loading', ascending=(sort_order == 'asc'))
                loadings_df = loadings_df.drop('abs_loading', axis=1)

            # Pagination
            total_genes = len(loadings_df)
            total_pages = (total_genes + page_size - 1) // page_size
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size

            page_df = loadings_df.iloc[start_idx:end_idx]

            response = {
                'workbench_id': workbench_id,
                'loadings': page_df.to_dict(orient='index'),
                'genes': list(page_df.index),
                'components': list(loadings_df.columns),
                'total_genes': total_genes,
                'current_page': page,
                'total_pages': total_pages,
                'page_size': page_size,
                'status': 'available'
            }

            return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ [PCA-LOADINGS-API] Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@pca_bp.route('/<int:workbench_id>/pca/correlation', methods=['GET'])
@require_auth
def get_sample_correlation(workbench_id):
    """
    Get sample correlation matrix

    Response:
    {
        "workbench_id": 1,
        "correlation_matrix": {...},
        "samples": [...],
        "status": "available"
    }
    """
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [PCA-CORRELATION-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            pca_dir = get_workbench_pca_dir(workbench['name'], workbench['user_id'])
            cor_file = os.path.join(pca_dir, 'genes.counts.matrix.minRow10.CPM.log2.centered.sample_cor.dat')

            if not os.path.exists(cor_file):
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': 'not_available',
                    'message': 'Correlation matrix not available'
                }), 200

            # Read correlation matrix
            cor_df = read_pca_data_file(cor_file)

            response = {
                'workbench_id': workbench_id,
                'correlation_matrix': cor_df.to_dict(orient='index'),
                'samples': list(cor_df.index),
                'status': 'available'
            }

            return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ [PCA-CORRELATION-API] Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@pca_bp.route('/<int:workbench_id>/pca/samples', methods=['GET'])
@require_auth
def get_pca_samples_info(workbench_id):
    """
    Get sample information from vizr_pipeline_samples table

    Response:
    {
        "workbench_id": 1,
        "samples": [
            {
                "sample_name": "DC1",
                "condition": "DC",
                "replicate": 1,
                "group": "Drought Control"
            },
            ...
        ],
        "groups": ["DC", "DH", "LC", "LH"],
        "status": "available"
    }
    """
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [PCA-SAMPLES-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        with get_db_connection() as conn:
            # Get sample information
            samples_raw = conn.execute('''
                SELECT * FROM vizr_pipeline_samples
                WHERE workbench_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if not samples_raw or not samples_raw['samples']:
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': 'not_available',
                    'message': 'Sample information not available'
                }), 200

            # Parse samples JSON
            samples_data = json.loads(samples_raw['samples'])

            # Extract sample info
            samples_list = []
            groups = []
            seen_groups = set()

            for sample in samples_data:
                # FileMapping structure: {groupName, sampleName, file1, file2}
                group_name = sample.get('groupName', '')
                sample_name = sample.get('sampleName', '')

                # Use groupName and sampleName as-is (preserve original names including underscores)
                replicate = ''.join([c for c in sample_name if c.isdigit()])

                samples_list.append({
                    'sample_name': sample_name,
                    'condition': group_name,
                    'replicate': replicate,
                    'file_paths': [sample.get('file1', ''), sample.get('file2', '')]
                })
                if group_name and group_name not in seen_groups:
                    groups.append(group_name)
                    seen_groups.add(group_name)

            response = {
                'workbench_id': workbench_id,
                'samples': samples_list,
                'groups': groups,
                'layout': samples_raw['layout'],
                'status': 'available'
            }

            return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ [PCA-SAMPLES-API] Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@pca_bp.route('/<int:workbench_id>/pca/expression-matrix', methods=['GET'])
@require_auth
def get_expression_matrix(workbench_id):
    """
    Get centered log2 CPM expression matrix

    Query params:
        - page: Page number (default: 1)
        - page_size: Number of genes per page (default: 100)
        - search: Gene ID search query

    Response:
    {
        "workbench_id": 1,
        "matrix": [...],
        "genes": [...],
        "samples": [...],
        "total_genes": 25000,
        "current_page": 1,
        "total_pages": 250,
        "status": "available"
    }
    """
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 100, type=int)
    search = request.args.get('search', '', type=str)

    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [PCA-MATRIX-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            pca_dir = get_workbench_pca_dir(workbench['name'], workbench['user_id'])
            matrix_file = os.path.join(pca_dir, 'genes.counts.matrix.minRow10.CPM.log2.centered.dat')

            if not os.path.exists(matrix_file):
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': 'not_available',
                    'message': 'Expression matrix not available'
                }), 200

            # Read expression matrix
            matrix_df = read_pca_data_file(matrix_file)

            # Search filter
            if search:
                mask = matrix_df.index.str.contains(search, case=False, na=False)
                matrix_df = matrix_df[mask]

            # Pagination
            total_genes = len(matrix_df)
            total_pages = (total_genes + page_size - 1) // page_size
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size

            page_df = matrix_df.iloc[start_idx:end_idx]

            response = {
                'workbench_id': workbench_id,
                'matrix': page_df.to_dict(orient='index'),
                'genes': list(page_df.index),
                'samples': list(matrix_df.columns),
                'total_genes': total_genes,
                'current_page': page,
                'total_pages': total_pages,
                'page_size': page_size,
                'search_query': search if search else None,
                'status': 'available'
            }

            return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ [PCA-MATRIX-API] Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@pca_bp.route('/<int:workbench_id>/pca/replicate-fragment-counts', methods=['GET'])
@require_auth
def get_replicate_fragment_counts(workbench_id):
    """
    Get fragment/read counts for each sample (replicate)

    Response:
    {
        "workbench_id": 1,
        "fragment_counts": {
            "DC1": 14000000,
            "DC2": 14000000,
            ...
        },
        "groups": {
            "DC": ["DC1", "DC2", "DC3"],
            "DH": ["DH1", "DH2", "DH3"],
            ...
        },
        "status": "available"
    }
    """
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [PCA-FRAGMENT-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            # Get workbench schema and count matrix file
            workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
            counts_dir = workbench_schema['quanti']['counts']
            count_matrix_file = os.path.join(counts_dir, 'gene_count_matrix.csv')

            if not os.path.exists(count_matrix_file):
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': 'not_available',
                    'message': 'Fragment count data not available'
                }), 200

            # Read count matrix
            count_df = pd.read_csv(count_matrix_file, index_col=0)

            # Calculate total fragment counts per sample (column sum)
            fragment_counts = count_df.sum(axis=0).to_dict()

            # Get sample information for grouping
            samples_raw = conn.execute('''
                SELECT samples FROM vizr_pipeline_samples
                WHERE workbench_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            groups = {}
            if samples_raw and samples_raw['samples']:
                samples_data = json.loads(samples_raw['samples'])

                # Group samples by groupName (e.g., WT-0h, WT-1h, WT-1D, etc.)
                for sample in samples_data:
                    sample_name = sample.get('sampleName', '')
                    # Use groupName directly for proper grouping by timepoint
                    group_name = sample.get('groupName', '')

                    if group_name not in groups:
                        groups[group_name] = []
                    groups[group_name].append(sample_name)

            response = {
                'workbench_id': workbench_id,
                'fragment_counts': fragment_counts,
                'groups': groups,
                'status': 'available'
            }

            return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ [PCA-FRAGMENT-API] Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@pca_bp.route('/<int:workbench_id>/pca/correlation-clustered', methods=['GET'])
@require_auth
def get_clustered_correlation(workbench_id):
    """
    Get hierarchically clustered sample correlation matrix with dendrogram data

    Response:
    {
        "workbench_id": 1,
        "correlation_matrix": {...},  # Reordered correlation matrix
        "samples": [...],  # Samples in clustered order
        "row_dendrogram": {...},  # Row dendrogram coordinates
        "col_dendrogram": {...},  # Column dendrogram coordinates
        "sample_groups": {...},  # Sample to group mapping
        "group_colors": {...},  # Group to color mapping
        "status": "available"
    }
    """
    try:
        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            logger.warning(f"⚠️ [PCA-CLUSTER-API] Workbench {workbench_id} access denied for user {session['user_id']}")
            return jsonify({'error': 'Workbench not found'}), 404

        with get_db_connection() as conn:
            # 워크벤치 정보 조회
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            pca_dir = get_workbench_pca_dir(workbench['name'], workbench['user_id'])
            cor_file = os.path.join(pca_dir, 'genes.counts.matrix.minRow10.CPM.log2.centered.sample_cor.dat')

            if not os.path.exists(cor_file):
                return jsonify({
                    'workbench_id': workbench_id,
                    'status': 'not_available',
                    'message': 'Correlation matrix not available'
                }), 200

            # Read correlation matrix
            cor_df = read_pca_data_file(cor_file)

            # Get sample information for grouping
            samples_raw = conn.execute('''
                SELECT samples FROM vizr_pipeline_samples
                WHERE workbench_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            # Build sample to group mapping
            sample_groups = {}
            if samples_raw and samples_raw['samples']:
                samples_data = json.loads(samples_raw['samples'])
                for sample in samples_data:
                    sample_name = sample.get('sampleName', '')
                    # Use groupName directly for proper grouping by timepoint
                    group_name = sample.get('groupName', '')
                    sample_groups[sample_name] = group_name

            # Assign colors to groups (matching the image style)
            unique_groups = sorted(set(sample_groups.values()))
            group_colors_list = ['#00FFFF', '#00FF00', '#FF0000', '#8B00FF', '#FFA500', '#FF69B4']
            group_colors = {group: group_colors_list[i % len(group_colors_list)]
                          for i, group in enumerate(unique_groups)}

            # Convert correlation to distance matrix (1 - correlation)
            distance_matrix = 1 - cor_df.values

            # Ensure distance matrix is valid (non-negative, symmetric)
            distance_matrix = np.clip(distance_matrix, 0, 2)

            # Convert to condensed distance matrix for clustering
            condensed_dist = squareform(distance_matrix, checks=False)

            # Perform hierarchical clustering (average linkage)
            linkage_matrix = hierarchy.linkage(condensed_dist, method='average')

            # Get dendrogram data
            dendrogram = hierarchy.dendrogram(linkage_matrix, no_plot=True)

            # Get clustered order
            clustered_order = dendrogram['leaves']
            ordered_samples = [cor_df.index[i] for i in clustered_order]

            # Reorder correlation matrix
            cor_df_ordered = cor_df.iloc[clustered_order, clustered_order]

            # Build dendrogram coordinates for plotting
            row_dendrogram = {
                'icoord': dendrogram['icoord'],
                'dcoord': dendrogram['dcoord'],
                'leaves': dendrogram['leaves'],
                'color_list': dendrogram['color_list']
            }

            # Column dendrogram is same as row dendrogram (symmetric matrix)
            col_dendrogram = row_dendrogram.copy()

            response = {
                'workbench_id': workbench_id,
                'correlation_matrix': cor_df_ordered.to_dict(orient='index'),
                'samples': list(ordered_samples),
                'row_dendrogram': row_dendrogram,
                'col_dendrogram': col_dendrogram,
                'sample_groups': sample_groups,
                'group_colors': group_colors,
                'status': 'available'
            }

            logger.info(f"✅ [PCA-CLUSTER-API] Successfully generated clustered correlation for workbench {workbench_id}")
            return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ [PCA-CLUSTER-API] Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
