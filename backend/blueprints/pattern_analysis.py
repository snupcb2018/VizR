"""
Pattern-based gene selection API for RNA-Seq data analysis
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify, session
from scipy.stats import spearmanr
from functools import wraps
from itertools import combinations

# Import database and auth utilities
from backend.utils.database import get_db_connection_simple as get_db_connection
from backend.blueprints.workbench_utils import get_workbench_schema, get_workbench_name_by_id
from backend.blueprints.workbench_share import check_workbench_access

# Create logger
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
pattern_bp = Blueprint('pattern', __name__, url_prefix='/api/workbenches')


def require_auth(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


@pattern_bp.route('/<int:workbench_id>/pattern-analysis', methods=['POST'])
@require_auth
def analyze_pattern(workbench_id):
    """
    Analyze gene expression patterns based on user-defined equalizer values.

    Request body:
    {
        "matrix_type": "TMM" | "TPM" | "Raw",
        "pattern": {"DC": 3, "DH": 1, "LC": 4, "LH": 2},
        "constraints": {
            "minSpearman": 0.6,
            "equalTol": 0.3,
            "orderGap": 0.5,
            "minLog2FC": 1.0,
            "minCPM": 0.0
        },
        "cvFilter": {
            "enabled": true,
            "maxCV": 0.5,
            "minGroups": 1
        },
        "equalityPairs": [["DH", "LH"], ["DC", "LC"]]
    }
    """
    logger.info(f"🎯 [PATTERN-API] Starting pattern analysis for workbench {workbench_id}")

    try:
        # Parse request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        matrix_type = data.get('matrix_type', 'TMM').upper()
        pattern = data.get('pattern', {})
        constraints = data.get('constraints', {})
        cv_filter = data.get('cvFilter', {})
        equality_pairs = data.get('equalityPairs', [])

        # 모든 파라미터 상세 로깅
        logger.info(f"📊 [PATTERN-API] ===== Request Parameters =====")
        logger.info(f"📊 [PATTERN-API] Workbench ID: {workbench_id}")
        logger.info(f"📊 [PATTERN-API] Matrix Type: {matrix_type}")
        logger.info(f"📊 [PATTERN-API] Pattern: {pattern}")
        logger.info(f"📊 [PATTERN-API] Constraints: {constraints}")
        logger.info(f"📊 [PATTERN-API]   - minSpearman: {constraints.get('minSpearman')}")
        logger.info(f"📊 [PATTERN-API]   - equalTol: {constraints.get('equalTol')}")
        logger.info(f"📊 [PATTERN-API]   - orderGap: {constraints.get('orderGap')}")
        logger.info(f"📊 [PATTERN-API]   - minLog2FC: {constraints.get('minLog2FC')}")
        logger.info(f"📊 [PATTERN-API]   - minCPM: {constraints.get('minCPM')}")
        logger.info(f"📊 [PATTERN-API] CV Filter: {cv_filter}")
        if cv_filter:
            logger.info(f"📊 [PATTERN-API]   - enabled: {cv_filter.get('enabled')}")
            logger.info(f"📊 [PATTERN-API]   - maxCV: {cv_filter.get('maxCV')}")
            logger.info(f"📊 [PATTERN-API]   - minGroups: {cv_filter.get('minGroups')}")
        logger.info(f"📊 [PATTERN-API] Equality Pairs: {equality_pairs}")
        logger.info(f"📊 [PATTERN-API] =================================")

        # Validate pattern
        if len(pattern) < 2:
            return jsonify({'error': 'Pattern must have at least 2 groups'}), 400

        # Shared workbench access check (owner or shared user)
        has_access, permission = check_workbench_access(workbench_id, session['user_id'])
        if not has_access:
            return jsonify({'error': 'Workbench not found'}), 404

        logger.info(f"✅ [PATTERN-API] Workbench access granted (permission: {permission})")

        # Get workbench info
        with get_db_connection() as conn:
            workbench = conn.execute('''
                SELECT id, name, user_id FROM vizr_workbench
                WHERE id = ?
            ''', (workbench_id,)).fetchone()

            if not workbench:
                return jsonify({'error': 'Workbench not found'}), 404

            # Check if count step is completed
            count_step = conn.execute('''
                SELECT status FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'count'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if not count_step or count_step['status'] != 'completed':
                return jsonify({'error': 'Count quantification not completed'}), 400

        # Get matrix file path
        wb_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        counts_dir = wb_schema['quanti']['counts']

        # Load sample-to-group mapping from database
        with get_db_connection() as conn:
            sample_record = conn.execute('''
                SELECT samples FROM vizr_pipeline_samples
                WHERE workbench_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()

            if not sample_record or not sample_record['samples']:
                return jsonify({'error': 'No sample information found for this workbench'}), 404

            # Parse samples JSON
            samples_data = json.loads(sample_record['samples'])
            logger.info(f"📊 [PATTERN-API] Loaded {len(samples_data)} samples from database")

        # Build group-to-sampleNames mapping
        group_to_samples = {}
        for sample in samples_data:
            group_name = sample.get('groupName')
            sample_name = sample.get('sampleName')

            if group_name and sample_name:
                if group_name not in group_to_samples:
                    group_to_samples[group_name] = []
                group_to_samples[group_name].append(sample_name)

        logger.info(f"📊 [PATTERN-API] Group mapping: {group_to_samples}")

        # Load count matrix
        matrix_files = {
            'TMM': os.path.join(counts_dir, 'genes.TMM.matrix'),
            'TPM': os.path.join(counts_dir, 'genes.TPM.matrix'),
            'RAW': os.path.join(counts_dir, 'gene_count_matrix.csv')
        }

        matrix_file = matrix_files.get(matrix_type)
        if not matrix_file or not os.path.exists(matrix_file):
            return jsonify({'error': f'Matrix file not found for type {matrix_type}'}), 404

        # Convert pattern dict to string format
        pattern_str = ','.join([f"{k}:{v}" for k, v in pattern.items()])
        groups_str = ','.join(pattern.keys())

        # Prepare output file path
        output_file = os.path.join(counts_dir, f'pattern_analysis_{workbench_id}.csv')

        # Prepare equality pairs parameter
        eq_pairs_str = None
        emit_eq_diag = False
        if equality_pairs and len(equality_pairs) > 0:
            # Convert [["DC", "DH"], ["LC", "LH"]] to "DC=DH;LC=LH"
            eq_pairs_str = ";".join(["=".join(pair) for pair in equality_pairs])
            emit_eq_diag = True
            logger.info(f"📊 [PATTERN-API] Equality pairs string: {eq_pairs_str}")

        # Execute pattern matching with group_to_samples dict directly
        logger.info(f"🚀 [PATTERN-API] Executing pattern matching...")
        result_df = execute_pattern_matching(
            counts=matrix_file,
            metadata=group_to_samples,  # Pass dict directly
            pattern=pattern_str,
            groups=groups_str,
            out=output_file,
            pseudocount=0.5,
            min_spearman=constraints.get('minSpearman', 0.6),
            min_log2fc=constraints.get('minLog2FC', 1.0),
            equal_tol=constraints.get('equalTol', 0.3),
            order_gap=constraints.get('orderGap', 0.5),
            min_cpm=constraints.get('minCPM', 0.0),
            max_cv=cv_filter.get('maxCV') if cv_filter.get('enabled') else None,
            cv_min_groups=cv_filter.get('minGroups', 1) if cv_filter.get('enabled') else 1,
            emit_eq_diag=emit_eq_diag,
            eq_pairs=eq_pairs_str
        )

        # Extract gene IDs from pattern matching result
        if result_df.empty:
            logger.warning(f"⚠️ [PATTERN-API] No genes matched pattern")
            return jsonify({
                'workbench_id': workbench_id,
                'matrix_type': matrix_type,
                'status': 'available',
                'matrix_file': matrix_file,
                'samples': [],
                'matrix': [],
                'total_genes': 0,
                'showing_genes': 0,
                'current_page': 1,
                'total_pages': 0,
                'page_size': 1000,
                'is_search_result': True,
                'search_query': f'Pattern Analysis (0 genes)'
            }), 200

        matched_gene_ids = result_df['gene'].tolist()
        logger.info(f"📤 [PATTERN-API] Found {len(matched_gene_ids)} genes matching pattern")

        # Load full matrix and filter by matched gene IDs
        logger.info(f"📂 [PATTERN-API] Loading full matrix for matched genes...")
        full_df = pd.read_csv(matrix_file, sep='\t')

        # Filter to only matched genes
        gene_id_col = full_df.columns[0]
        full_df = full_df[full_df[gene_id_col].isin(matched_gene_ids)]

        # Get sample columns
        samples = [col for col in full_df.columns if col != gene_id_col]

        # Load gene annotations
        from backend.blueprints.workbench_utils import load_gene_annotations
        gene_annotations = load_gene_annotations()

        # Convert to response format
        logger.info(f"🔄 [PATTERN-API] Converting {len(full_df)} genes to response format...")
        matrix_data = []
        for _, row in full_df.iterrows():
            gene_id = row[gene_id_col]
            gene_info = gene_annotations.get(gene_id, {})
            gene_symbol = gene_info.get('symbol', gene_id)
            gene_description = gene_info.get('description', 'No description available')

            gene_dict = {
                'gene_id': gene_id,
                'gene_symbol': gene_symbol,
                'gene_description': gene_description
            }
            for sample in samples:
                gene_dict[sample] = row[sample]
            matrix_data.append(gene_dict)

        response = {
            'workbench_id': workbench_id,
            'matrix_type': matrix_type,
            'status': 'available',
            'matrix_file': matrix_file,
            'samples': samples,
            'matrix': matrix_data,
            'total_genes': len(matrix_data),
            'showing_genes': len(matrix_data),
            'current_page': 1,
            'total_pages': 1,
            'page_size': len(matrix_data),
            'is_search_result': True,
            'search_query': f'Pattern Analysis ({len(matrix_data)} genes)'
        }

        logger.info(f"✅ [PATTERN-API] Returning {len(matrix_data)} genes with full sample data")
        logger.info(f"📊 [PATTERN-API] Response structure: {len(samples)} samples, {len(matrix_data)} genes")

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ [PATTERN-API] Failed to analyze pattern: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


def sniff_sep(path: str):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        chunk = f.read(2048)
    if '\t' in chunk and ',' not in chunk.splitlines()[0]:
        return '\t'
    return ','

def parse_pattern(s: str):
    d = {}
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Invalid pattern part: {part}")
        g, v = part.split(":", 1)
        g = g.strip()
        v = v.strip()
        if v == "" or v.lower() in {"x", "na", "nan", "none"}:
            d[g] = None
        else:
            d[g] = float(v)
    return d

def parse_eq_pairs(s: str|None):
    pairs = set()
    if not s:
        return pairs
    for chunk in [x for y in s.replace(';',',').split(',') for x in [y.strip()] if x]:
        if not chunk:
            continue
        if '=' in chunk:
            a,b = chunk.split('=',1)
        elif ':' in chunk:
            a,b = chunk.split(':',1)
        else:
            raise ValueError(f"Cannot parse eq pair '{chunk}'; use A=B or A:B")
        a,b = a.strip(), b.strip()
        if not a or not b or a==b:
            continue
        pairs.add(frozenset([a,b]))
    return pairs

def implied_equal_pairs_from_pattern(pattern_dict: dict, groups_order, rtol=0.0, atol=1e-12):
    active = [g for g in groups_order if pattern_dict.get(g) is not None]
    pairs = set()
    for i, g1 in enumerate(active):
        for g2 in combinations(active[i+1:], 1):
            pass
    pairs = set()
    for i, g1 in enumerate(active):
        for g2 in active[i+1:]:
            h1, h2 = pattern_dict[g1], pattern_dict[g2]
            if np.isclose(h1, h2, rtol=rtol, atol=atol):
                pairs.add(frozenset([g1,g2]))
    return pairs

def load_counts(path: str, gene_col: str|None, sep: str):
    if sep == "auto":
        sep = sniff_sep(path)
    df = pd.read_csv(path, sep=sep)
    if gene_col and gene_col in df.columns:
        gene = df[gene_col].astype(str)
        df = df.drop(columns=[gene_col])
    else:
        gene = df.iloc[:,0].astype(str)
        df = df.iloc[:,1:]
    df.index = gene
    df = df.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return df

def load_meta(path: str, sep: str):
    if sep == "auto":
        sep = sniff_sep(path)
    m = pd.read_csv(path, sep=sep)
    needed = {"sample","group"}
    if not needed.issubset(set(m.columns)):
        raise ValueError(f"metadata must have columns: {needed}")
    return m

def summarize_by_group(counts: pd.DataFrame, meta: pd.DataFrame, groups_order):
    out = {}
    for g in groups_order:
        samples = meta.loc[meta["group"]==g, "sample"].tolist()
        missing = [s for s in samples if s not in counts.columns]
        if missing:
            raise ValueError(f"Samples for group '{g}' not found in counts: {missing[:10]}{'...' if len(missing)>10 else ''}")
        if len(samples)==0:
            raise ValueError(f"No samples for group '{g}' in metadata.")
        out[g] = counts[samples].median(axis=1)
    return pd.DataFrame(out)

def build_constraints(pattern_dict: dict, groups_order):
    active = [g for g in groups_order if pattern_dict.get(g) is not None]
    heights = {g: pattern_dict[g] for g in active}
    cons = []
    for i, g1 in enumerate(active):
        for g2 in active[i+1:]:
            h1, h2 = heights[g1], heights[g2]
            if np.isclose(h1, h2):
                cons.append((g1, "eq", g2))
            elif h1 > h2:
                cons.append((g1, "gt", g2))
            else:
                cons.append((g1, "lt", g2))

    n_eq = sum(1 for _, r, _ in cons if r == "eq")
    n_gt = sum(1 for _, r, _ in cons if r == "gt")
    n_lt = sum(1 for _, r, _ in cons if r == "lt")
    logger.info(f"📐 [CONSTRAINTS] Active groups ({len(active)}): {active}")
    logger.info(f"📐 [CONSTRAINTS] Pattern values: { {g: heights[g] for g in active} }")
    logger.info(f"📐 [CONSTRAINTS] Total constraints: {len(cons)}  (eq={n_eq}, gt={n_gt}, lt={n_lt})")
    if n_eq > 0:
        eq_list = [(g1, g2) for g1, r, g2 in cons if r == "eq"]
        logger.info(f"📐 [CONSTRAINTS] EQ pairs (|Δlog2| must be < equalTol): {eq_list}")
    if n_gt > 0:
        gt_list = [(g1, g2) for g1, r, g2 in cons if r == "gt"]
        logger.info(f"📐 [CONSTRAINTS] GT pairs (Δlog2 must be ≥ orderGap): {gt_list}")

    return cons, active

def check_constraints(row_log2: pd.Series, constraints, equal_tol: float, order_gap: float):
    viol = []
    for g1, rel, g2 in constraints:
        d = row_log2[g1] - row_log2[g2]
        if rel == "eq":
            if abs(d) > equal_tol:
                viol.append(f"{g1}≈{g2} |Δ|={abs(d):.3f} > tol={equal_tol}")
        elif rel == "gt":
            if d < order_gap:
                viol.append(f"{g1}>{g2} Δ={d:.3f} < gap={order_gap}")
        elif rel == "lt":
            if -d < order_gap:
                viol.append(f"{g2}>{g1} Δ={-d:.3f} < gap={order_gap}")
    return len(viol)==0, viol

def within_group_cv_filter(counts: pd.DataFrame, meta: pd.DataFrame, min_groups:int, max_cv: float):
    eps = 1e-8
    passes = pd.Series(0, index=counts.index, dtype=int)
    for g in meta["group"].unique():
        samples = meta.loc[meta["group"]==g, "sample"]
        if len(samples) < 2:
            passes += 1
            continue
        sub = counts[samples]
        mean = sub.mean(axis=1)
        sd = sub.std(axis=1, ddof=1)
        cv = (sd + eps) / (mean + eps)
        passes += (cv <= max_cv).astype(int)
    return passes >= min_groups

def execute_pattern_matching(
    counts: str,
    metadata: dict,
    pattern: str,
    groups: str,
    out: str,
    gene_col: str = None,
    pseudocount: float = 0.5,
    min_spearman: float = 0.6,
    min_log2fc: float = 0.0,
    equal_tol: float = 0.3,
    order_gap: float = 0.5,
    min_cpm: float = 0.0,
    max_cv: float = None,
    cv_min_groups: int = 1,
    counts_sep: str = "auto",
    emit_eq_diag: bool = False,
    eq_pairs: str = None,
    eq_all: bool = False
):
    """
    Execute pattern matching analysis on gene expression data.

    Args:
        counts: Path to TMM count matrix CSV/TSV (genes x samples)
        metadata: Dict mapping group -> sample names (e.g., {"DC": ["DC1", "DC2"], "DH": ["DH1", "DH2"]})
        pattern: Pattern string, e.g., "DC:3,DH:1,LC:4,LH:2". Use x/NA to ignore a group.
        groups: Comma-separated group order, e.g., "DC,DH,LC,LH"
        out: Output CSV path
        gene_col: Name of gene id column (default: first column)
        pseudocount: Pseudocount before log2 (default: 0.5)
        min_spearman: Minimum Spearman rho to match trend (default: 0.6)
        min_log2fc: Minimum (max-min) log2 fold-change across active groups (default: 0.0)
        equal_tol: Tolerance for 'equal' pairs in log2 scale (default: 0.3)
        order_gap: Required gap for ordered pairs in log2 scale (default: 0.5)
        min_cpm: Minimum median CPM in at least one active group (default: 0.0)
        max_cv: Optional within-group CV filter (sd/mean); applies if set
        cv_min_groups: Minimum number of groups that must pass the CV threshold (default: 1)
        counts_sep: Separator for counts file (default: "auto")
        meta_sep: Separator for metadata file (default: "auto")
        emit_eq_diag: Emit equality deviation diagnostics for pairs (default: False)
        eq_pairs: Manual equality pairs, e.g., "DH=LH,DC=LC" or "DH:LH;DC:LC"
        eq_all: Compute equality deviation for all unordered pairs among ACTIVE groups (default: False)

    Returns:
        pd.DataFrame: Filtered genes with pattern matching results
    """
    groups_order = [g.strip() for g in groups.split(",") if g.strip()]
    pattern_dict = parse_pattern(pattern)

    counts_df = load_counts(counts, gene_col, counts_sep)

    # Convert group_to_samples dict to DataFrame
    metadata_rows = []
    for group_name, sample_names in metadata.items():
        for sample_name in sample_names:
            metadata_rows.append({'sample': sample_name, 'group': group_name})
    meta = pd.DataFrame(metadata_rows)
    logger.info(f"📊 [PATTERN] Converted dict to metadata DataFrame: {len(metadata_rows)} samples")

    missing_samples = [s for s in meta["sample"] if s not in counts_df.columns]
    if missing_samples:
        raise ValueError(f"ERROR: metadata samples not in counts: {missing_samples[:10]}{'...' if len(missing_samples)>10 else ''}")

    grp_medians = summarize_by_group(counts_df, meta, groups_order)

    constraints, active_groups = build_constraints(pattern_dict, groups_order)
    if len(active_groups) < 2:
        raise ValueError("Pattern must specify at least two groups (non-NA).")

    pattern_vec = np.array([pattern_dict[g] for g in active_groups], dtype=float)
    log2_mat = np.log2(grp_medians[active_groups] + pseudocount)

    # Equality pairs to compute diagnostics for
    eq_pairs_set = set()
    if eq_all:
        eq_pairs_set = {frozenset(p) for p in combinations(active_groups, 2)}
    else:
        eq_pairs_set |= implied_equal_pairs_from_pattern(pattern_dict, active_groups)
        eq_pairs_set |= parse_eq_pairs(eq_pairs)

    total_genes = len(grp_medians)
    logger.info(f"🔬 [FILTER] Total genes in matrix: {total_genes}")
    logger.info(f"🔬 [FILTER] Pattern vector: {list(zip(active_groups, pattern_vec.tolist()))}")
    logger.info(f"🔬 [FILTER] Thresholds — minSpearman={min_spearman}, orderGap={order_gap}, equalTol={equal_tol}, minLog2FC={min_log2fc}, minCPM={min_cpm}")

    if max_cv is not None:
        cv_mask = within_group_cv_filter(counts_df, meta, cv_min_groups, max_cv)
        n_cv_pass = int(cv_mask.sum())
        logger.info(f"🔬 [FILTER] CV filter (maxCV={max_cv}, minGroups={cv_min_groups}): {n_cv_pass}/{total_genes} pass")
    else:
        cv_mask = pd.Series(True, index=counts_df.index)

    min_expr_mask = (grp_medians[active_groups].max(axis=1) >= min_cpm)
    n_expr_pass = int(min_expr_mask.sum())
    logger.info(f"🔬 [FILTER] minCPM filter (>={min_cpm}): {n_expr_pass}/{total_genes} pass")

    # Per-filter rejection counters
    n_skipped_prefilter = 0
    n_nan_rho = 0
    n_fail_spearman = 0
    n_fail_constraint = 0
    n_fail_log2fc = 0
    n_pass = 0

    # Constraint violation type counter
    constraint_viol_counter = {}

    records = []
    for gene, med_vals in grp_medians[active_groups].iterrows():
        if not (cv_mask.get(gene, True) and min_expr_mask.get(gene, True)):
            n_skipped_prefilter += 1
            continue
        x = med_vals.values.astype(float)
        rho, p = spearmanr(x, pattern_vec)
        row_log2 = log2_mat.loc[gene]
        ok, viol = check_constraints(row_log2, constraints, equal_tol, order_gap)
        log2fc = float(row_log2.max() - row_log2.min())

        if np.isnan(rho):
            n_nan_rho += 1
            continue
        if rho < min_spearman:
            n_fail_spearman += 1
            continue
        if not ok:
            n_fail_constraint += 1
            for v in viol:
                # 제약 위반 유형 집계 (첫 번째 토큰 = 쌍 이름)
                key = v.split(" ")[0]
                constraint_viol_counter[key] = constraint_viol_counter.get(key, 0) + 1
            continue
        if log2fc < min_log2fc:
            n_fail_log2fc += 1
            continue

        n_pass += 1
        rec = {
            "gene": gene,
            **{f"median_{g}": float(med_vals[g]) for g in active_groups},
            **{f"log2_{g}": float(row_log2[g]) for g in active_groups},
            "spearman_rho": float(rho),
            "spearman_p": float(p) if p is not None else np.nan,
            "log2FC_max_min": log2fc,
            "top_group": active_groups[int(np.argmax(row_log2.values))],
            "bottom_group": active_groups[int(np.argmin(row_log2.values))],
            "violations": "; ".join(viol)
        }
        if emit_eq_diag and eq_pairs_set:
            for pair in sorted(eq_pairs_set, key=lambda t: tuple(sorted(t))):
                g1, g2 = sorted(list(pair))
                if (g1 in row_log2.index) and (g2 in row_log2.index):
                    rec[f"eqdev_log2_{g1}_{g2}"] = float(abs(row_log2[g1] - row_log2[g2]))
        records.append(rec)

    logger.info(f"📊 [FILTER] ===== Filter Result Summary =====")
    logger.info(f"📊 [FILTER]   Total genes:            {total_genes}")
    logger.info(f"📊 [FILTER]   Pre-filter rejected:    {n_skipped_prefilter}  (CV or minCPM)")
    logger.info(f"📊 [FILTER]   NaN rho (constant expr):{n_nan_rho}")
    logger.info(f"📊 [FILTER]   Low Spearman rho:       {n_fail_spearman}  (< {min_spearman})")
    logger.info(f"📊 [FILTER]   Constraint violation:   {n_fail_constraint}  (orderGap/equalTol)")
    logger.info(f"📊 [FILTER]   Low log2FC:             {n_fail_log2fc}  (< {min_log2fc})")
    logger.info(f"📊 [FILTER]   ✅ PASSED:              {n_pass}")
    logger.info(f"📊 [FILTER] ========================================")
    if constraint_viol_counter:
        top_viols = sorted(constraint_viol_counter.items(), key=lambda x: -x[1])[:10]
        logger.info(f"📊 [FILTER] Top constraint violations: {top_viols}")

    out_df = pd.DataFrame.from_records(records)
    if out_df.empty:
        cols = ["gene"] + [f"median_{g}" for g in active_groups] + [f"log2_{g}" for g in active_groups] + \
               ["spearman_rho","spearman_p","log2FC_max_min","top_group","bottom_group","violations"]
        if emit_eq_diag and eq_pairs_set:
            for pair in sorted(eq_pairs_set, key=lambda t: tuple(sorted(t))):
                g1, g2 = sorted(list(pair))
                cols.append(f"eqdev_log2_{g1}_{g2}")
        out_df = pd.DataFrame(columns=cols)

    out_df = out_df.sort_values(by=["spearman_rho","log2FC_max_min"], ascending=[False, False], ignore_index=True)

    logger.info(f"✅ [PATTERN] Pattern matching completed: {len(out_df)} genes found")
    if len(out_df) == 0:
        logger.warning("⚠️ [PATTERN] No genes matched given thresholds. Consider relaxing --min-spearman, --order-gap, --equal-tol, or --min-log2fc.")
    else:
        logger.info(f"📊 [PATTERN] Top 10 genes:")
        logger.info(f"\n{out_df.head(10).to_string()}")
        logger.info(f"📊 [PATTERN] Full result shape: {out_df.shape}")

    return out_df
