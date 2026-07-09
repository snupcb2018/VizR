"""
VizR Workbench Utility Functions
워크벤치 관련 공통 유틸리티 함수 모음
"""
import os
import re
import pandas as pd
import urllib.request
from backend.utils.logger import setup_module_logger
from backend.utils.database import get_db_connection_simple as get_db_connection
from backend.utils.auth import get_current_username
from config.backend_settings import BackendConfig as Config

logger = setup_module_logger(__name__, 'INFO')

# Global variable to cache gene annotations
_gene_annotations = None


def get_user_annotation_path(filename, species='arabidopsis'):
    """
    Get user-specific annotation file path.

    Args:
        filename: Annotation filename
        species: Species name (default: 'arabidopsis')

    Returns:
        str: Full path to annotation file
    """
    username = get_current_username()
    return f"{Config.VIZR_DIR}/users/{username}/resource/{species}/reference/TAIR10/{filename}"


def download_gene_annotations(species='arabidopsis', force_update=False):
    """
    Check and download TAIR10 gene functional descriptions if needed.

    Args:
        species: Species name (currently only 'arabidopsis' supported)
        force_update: Force re-download even if file exists

    Returns:
        str: Path to the annotation file
    """
    if species != 'arabidopsis':
        raise ValueError(f"Species '{species}' not supported. Currently only 'arabidopsis' is supported.")

    annotation_file = get_user_annotation_path('TAIR10_functional_descriptions.txt', species)

    # Check if file already exists
    if os.path.exists(annotation_file) and not force_update:
        logger.info(f"✅ [GENE-ANNOTATION] Annotation file already exists: {annotation_file}")
        return annotation_file

    # 파일이 없으면 디렉토리 생성 후 다운로드 시도
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(annotation_file), exist_ok=True)

        # TAIR API download URL (discovered via browser network inspection)
        url = "https://www.arabidopsis.org/api/download-files/download?filePath=Genes%2FTAIR10_genome_release%2FTAIR10_functional_descriptions"

        logger.info(f"📥 [GENE-ANNOTATION] Downloading TAIR10 functional descriptions...")
        logger.info(f"📥 [GENE-ANNOTATION] URL: {url}")

        temp_file = f"{annotation_file}.tmp"

        # HTTP download with browser-like headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.arabidopsis.org/'
        }
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=60) as response, open(temp_file, 'wb') as out_file:
            out_file.write(response.read())

        # Validate downloaded file (check if it's actually a TSV, not HTML)
        with open(temp_file, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            if first_line.startswith('<!DOCTYPE') or first_line.startswith('<html'):
                raise Exception("Downloaded HTML page instead of data file. The download URL may have changed.")

        # Success!
        os.replace(temp_file, annotation_file)

        # Check file size
        file_size = os.path.getsize(annotation_file)
        logger.info(f"✅ [GENE-ANNOTATION] Downloaded successfully: {annotation_file} ({file_size:,} bytes)")

        return annotation_file

    except Exception as e:
        logger.error(f"❌ [GENE-ANNOTATION] Failed to download annotation file: {e}")
        import traceback
        logger.error(f"❌ [GENE-ANNOTATION] Traceback: {traceback.format_exc()}")
        logger.error(f"💡 [GENE-ANNOTATION] Please manually download from: https://www.arabidopsis.org/download/list?dir=Genes%2FTAIR10_genome_release")
        logger.error(f"💡 [GENE-ANNOTATION] Or place the file manually at: {annotation_file}")
        raise


def load_gene_annotations(force_reload=False):
    """
    Load gene annotations (Symbol + Description).
    - Symbol: from TAIR10_GeneSymbolTable_v2.xlsx
    - Description: from TAIR10_functional_descriptions.txt
    Cached in memory for performance.

    Returns:
        dict: {
            gene_id: {
                'symbol': gene_symbol,
                'description': gene_description
            }
        }
    """
    global _gene_annotations

    # Return cached data if available
    if _gene_annotations is not None and not force_reload:
        return _gene_annotations

    try:
        def _normalize_gene_id(gene_id: str) -> str:
            """Normalize gene ID for robust cross-file matching."""
            if gene_id is None:
                return ''
            raw = str(gene_id).strip()
            if not raw:
                return ''
            return re.sub(r'\.\d+$', '', raw).upper()

        def _pick_first_non_empty(row, candidates):
            """Return first non-empty column value from candidates."""
            for col in candidates:
                if col in row.index:
                    value = row.get(col)
                    if pd.notna(value):
                        text = str(value).strip()
                        if text:
                            return text
            return ''

        # Step 1: Load Gene Symbols from Excel
        symbol_file = get_user_annotation_path('TAIR10_GeneSymbolTable_v2.xlsx')

        symbol_map = {}
        if os.path.exists(symbol_file):
            df_symbol = pd.read_excel(symbol_file)
            df_symbol.columns = [str(c).strip() for c in df_symbol.columns]
            id_col = next((c for c in ['ID', 'GeneID', 'gene_id', 'Model_name'] if c in df_symbol.columns), None)
            symbol_col = next((c for c in ['Symbol', 'symbol', 'GeneSymbol'] if c in df_symbol.columns), None)

            if id_col and symbol_col:
                for _, row in df_symbol.iterrows():
                    raw_id = str(row.get(id_col, '')).strip()
                    if not raw_id:
                        continue

                    normalized_id = _normalize_gene_id(raw_id)
                    if not normalized_id.startswith('AT'):
                        continue

                    symbol_value = row.get(symbol_col, '')
                    symbol = str(symbol_value).strip() if pd.notna(symbol_value) and str(symbol_value).strip() else normalized_id

                    # Store both normalized and isoform keys (if different) for safer lookup
                    symbol_map[normalized_id] = symbol
                    raw_upper = raw_id.upper()
                    if raw_upper != normalized_id:
                        symbol_map[raw_upper] = symbol
            else:
                logger.warning(f"⚠️ [GENE-ANNOTATION] Unexpected symbol file columns: {df_symbol.columns.tolist()}")

            logger.info(f"📖 [GENE-ANNOTATION] Loaded {len(symbol_map)} gene symbols")
        else:
            logger.warning(f"⚠️ [GENE-ANNOTATION] Symbol file not found: {symbol_file}")

        # Step 2: Load Descriptions from TAIR10 (Gene ID direct matching)
        annotation_file = download_gene_annotations()

        description_map = {}
        description_base_ids = set()
        if os.path.exists(annotation_file):
            # Try different encodings (TAIR files may use Latin-1 or Windows-1252)
            df_desc = None
            used_encoding = None
            for encoding in ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1']:
                try:
                    df_desc = pd.read_csv(annotation_file, sep='\t', low_memory=False, encoding=encoding)
                    used_encoding = encoding
                    break
                except UnicodeDecodeError:
                    if encoding == 'iso-8859-1':  # Last attempt
                        logger.error(f"❌ [GENE-ANNOTATION] Failed to decode file with any encoding")
                        raise
                    continue

            if df_desc is None:
                raise RuntimeError("Failed to load TAIR10 description file")

            df_desc.columns = [str(c).strip() for c in df_desc.columns]

            # Backward compatibility: legacy files may not have header row
            known_cols = {'Model_name', 'GeneID', 'ID_with_isoform', 'Short_desc', 'Short_description'}
            if not any(col in known_cols for col in df_desc.columns):
                df_desc = pd.read_csv(
                    annotation_file,
                    sep='\t',
                    header=None,
                    names=['ID_with_isoform', 'GeneID', 'Type', 'Short_desc', 'Medium_desc', 'Long_desc', 'Extra'],
                    low_memory=False,
                    encoding=used_encoding or 'utf-8'
                )
                df_desc.columns = [str(c).strip() for c in df_desc.columns]

            # Build Gene ID -> Description mapping (supports both modern and legacy TAIR formats)
            for idx, row in df_desc.iterrows():
                raw_gene_id = _pick_first_non_empty(row, ['GeneID', 'ID_with_isoform', 'Model_name'])
                normalized_id = _normalize_gene_id(raw_gene_id)
                if not normalized_id.startswith('AT'):
                    continue

                # Priority order across old/new formats
                description = _pick_first_non_empty(
                    row,
                    ['Long_desc', 'Computational_description', 'Curator_summary', 'Medium_desc', 'Short_desc', 'Short_description']
                )

                if description:
                    # Keep richer description if duplicate appears
                    if normalized_id not in description_map or len(description) > len(description_map[normalized_id]):
                        description_map[normalized_id] = description
                    description_base_ids.add(normalized_id)

                    # Also store isoform key if source carries it (e.g., AT1G01010.1)
                    raw_upper = str(raw_gene_id).strip().upper()
                    if raw_upper and raw_upper != normalized_id:
                        if raw_upper not in description_map or len(description) > len(description_map[raw_upper]):
                            description_map[raw_upper] = description

            if symbol_map:
                coverage = (len(description_base_ids) / len(symbol_map)) * 100
                logger.info(
                    f"✅ [GENE-ANNOTATION] Loaded {len(description_base_ids)} gene descriptions ({coverage:.1f}% coverage)"
                )
            else:
                logger.info(
                    f"✅ [GENE-ANNOTATION] Loaded {len(description_base_ids)} gene descriptions (symbol map unavailable)"
                )
        else:
            logger.warning(f"⚠️ [GENE-ANNOTATION] Description file not found: {annotation_file}")

        # Step 3: Combine Symbol + Description
        _gene_annotations = {}

        # Get all unique gene IDs from both sources
        all_gene_ids = set(symbol_map.keys()) | set(description_map.keys())

        for gene_id in all_gene_ids:
            symbol = symbol_map.get(gene_id, gene_id)  # Fallback to gene_id if no symbol
            description = description_map.get(gene_id, 'No description available')

            _gene_annotations[gene_id] = {
                'symbol': symbol,
                'description': description
            }

        logger.info(f"✅ [GENE-ANNOTATION] Loaded {len(_gene_annotations)} gene annotations")

        return _gene_annotations

    except Exception as e:
        logger.error(f"❌ [GENE-ANNOTATION] Failed to load gene annotations: {e}")
        import traceback
        logger.error(f"❌ [GENE-ANNOTATION] Traceback: {traceback.format_exc()}")
        return {}


def get_workbench_name_by_id(workbench_id):
    """Get filesystem-safe workbench name by workbench ID."""
    with get_db_connection() as conn:
        workbench = conn.execute(
            'SELECT name FROM vizr_workbench WHERE id = ?',
            (workbench_id,)
        ).fetchone()
        if workbench:
            # Make filesystem-safe
            return workbench['name'].replace(' ', '_').replace('/', '_').replace('\\', '_')
        return None


def get_workbench_schema(workbench_name, user_id):
    """Generate standard workbench directory structure definition.

    Args:
        workbench_name (str): Name of the workbench
        user_id (int): User ID for user-specific directory structure

    Returns:
        dict: Dictionary containing workbench directory structure paths
    """
    from config.shared_config import SharedConfig
    from backend.utils.database import get_db_connection

    # Get username from database
    with get_db_connection() as conn:
        user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
        username = user['username'] if user else str(user_id)

    # Build user-specific workbench path
    # VIZR_PATH/users/{username}/workbench/{workbench_name}
    base_vizr_path = SharedConfig.VIZR_PATH
    workbench_dir = f"{base_vizr_path}/users/{username}/workbench/{workbench_name}"

    logger.debug(f"Using VIZR_PATH: {base_vizr_path}")
    logger.debug(f"Username: {username}")
    logger.debug(f"Final workbench directory: {workbench_dir}")

    # 표준 워크벤치 디렉토리 구조 정의
    workbench_structure = {
        "base": workbench_dir,
        "deg": f"{workbench_dir}/deg",           # DEG 분석 결과
        "log": f"{workbench_dir}/log",           # 로그 파일들
        "quanti": {
            "base": f"{workbench_dir}/quanti",
            "alignment": f"{workbench_dir}/quanti/alignment",  # Alignment 결과
            "counts": f"{workbench_dir}/quanti/counts",    # Read counting 결과
            "clean": f"{workbench_dir}/quanti/clean",      # Cleaned reads
            "qc": f"{workbench_dir}/quanti/qc",            # Quality control 결과
            "raw": f"{workbench_dir}/quanti/raw",          # Raw data files
            "samples": f"{workbench_dir}/quanti/samples"   # Sample information
        },
        "report": f"{workbench_dir}/report",     # 최종 리포트
        "visual": f"{workbench_dir}/visual",     # 시각화 결과
        "ref": f"{workbench_dir}/ref"            # Reference files
    }

    return workbench_structure
