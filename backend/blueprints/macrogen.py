"""
VizR Macrogen Blueprint
API to fetch FASTQ file list from a Macrogen report ZIP URL.
"""
from flask import Blueprint, request, jsonify, session
import re
import base64
import binascii
from urllib.parse import parse_qs, unquote, urlparse

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
macrogen_bp = Blueprint('macrogen', __name__, url_prefix='/api/macrogen')


def require_auth(f):
    """Decorator to require authentication for routes."""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


@macrogen_bp.route('/fetch-file-list', methods=['POST'])
@require_auth
def fetch_macrogen_file_list():
    """Extract file list from a Macrogen report ZIP."""
    try:
        import requests
        import zipfile
        import io

        data = request.get_json()
        if not data or 'report_url' not in data:
            return jsonify({'error': 'report_url is required'}), 400

        report_url = data['report_url'].strip()
        logger.info(f"Fetching Macrogen file list from: {report_url}")

        # URL validation: must be macrogen.com + ZIP-looking link pattern.
        parsed_url = urlparse(report_url)
        hostname = (parsed_url.hostname or '').lower()
        if not hostname.endswith('macrogen.com'):
            return jsonify({'error': 'URL must be from macrogen.com domain'}), 400
        if not _looks_like_zip_report_url(report_url):
            return jsonify({'error': 'URL must point to a Macrogen report ZIP (direct or download query URL)'}), 400

        # Download report ZIP.
        try:
            response = requests.get(report_url, timeout=120, stream=True)
            response.raise_for_status()
        except requests.Timeout:
            logger.error(f"Request timed out for URL: {report_url}")
            return jsonify({'error': 'Request timed out. Please check the URL and try again.'}), 408
        except requests.RequestException as e:
            logger.error(f"Failed to download ZIP from {report_url}: {e}")
            return jsonify({'error': f'Failed to download report: {str(e)}'}), 500

        zip_content = io.BytesIO(response.content)

        try:
            with zipfile.ZipFile(zip_content, 'r') as zf:
                # Find expected download-list file inside ZIP.
                txt_file = None
                for name in zf.namelist():
                    if name.lower().endswith('samples_md5sum_downloadlink.txt'):
                        txt_file = name
                        break

                if not txt_file:
                    logger.error("No samples_md5sum_downloadlink.txt found in ZIP")
                    return jsonify({'error': 'No download list file found in report ZIP. Expected *samples_md5sum_downloadlink.txt'}), 404

                logger.info(f"Found download list file: {txt_file}")
                txt_content = zf.read(txt_file).decode('utf-8', errors='replace')
                files = _parse_download_list(txt_content)

        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP file from {report_url}")
            return jsonify({'error': 'The downloaded file is not a valid ZIP file'}), 400

        if not files:
            return jsonify({'error': 'No fastq files found in download list'}), 404

        # Detect layout from parsed files.
        has_r1 = any(f['read_num'] == 1 for f in files)
        has_r2 = any(f['read_num'] == 2 for f in files)
        layout = 'paired' if (has_r1 and has_r2) else 'single'

        logger.info(f"Found {len(files)} files, layout: {layout}")

        return jsonify({
            'success': True,
            'report_url': report_url,
            'files': files,
            'total_files': len(files),
            'layout': layout
        })

    except Exception as e:
        logger.error(f"Macrogen fetch error: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


def _parse_download_list(txt_content: str) -> list:
    """
    Parse *samples_md5sum_downloadlink.txt.
    Format: filename\\tsize\\tmd5\\turl
    """
    files = []

    for line in txt_content.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split('\t')
        if len(parts) < 4:
            logger.warning(f"Skipping malformed line: {line}")
            continue

        name = parts[0].strip()
        size_str = parts[1].strip()
        md5 = parts[2].strip()
        url = parts[3].strip()

        # Keep FASTQ/FQ only.
        if not (name.endswith('.fastq.gz') or name.endswith('.fq.gz') or
                name.endswith('.fastq') or name.endswith('.fq')):
            continue

        size_bytes = _parse_size_bytes(size_str)

        size_mb = f"{size_bytes / (1024 * 1024):.1f}" if size_bytes > 0 else "0.0"

        sample_name, read_num = _extract_sample_info(name)

        files.append({
            'name': name,
            'sample_name': sample_name,
            'size_bytes': size_bytes,
            'size_mb': size_mb,
            'md5': md5,
            'url': url,
            'read_num': read_num
        })

    return files


def _looks_like_zip_report_url(report_url: str) -> bool:
    """
    Accept:
    - direct .zip links
    - download links with .zip hints in query values (plain or encoded)
    """
    parsed = urlparse(report_url)
    path = (parsed.path or '').lower()

    if path.endswith('.zip'):
        return True

    query = parse_qs(parsed.query, keep_blank_values=True)
    if not query:
        return False

    # Common Macrogen pattern:
    # https://datadownload.macrogen.com/download?file=<opaque/encoded value>
    if path.endswith('/download') and 'file' in query:
        for value in query.get('file', []):
            if _contains_zip_hint(value):
                return True
        return False

    for values in query.values():
        for value in values:
            if _contains_zip_hint(value):
                return True

    return False


def _contains_zip_hint(value: str) -> bool:
    decoded = unquote(value or '')
    if '.zip' in decoded.lower():
        return True

    compact = ''.join(decoded.split())
    if not compact:
        return False

    padded = compact + '=' * (-len(compact) % 4)
    candidates = [padded, padded.replace('-', '+').replace('_', '/')]
    for candidate in candidates:
        try:
            raw = base64.b64decode(candidate, validate=False)
            text = raw.decode('utf-8', errors='ignore').lower()
            if '.zip' in text:
                return True
        except (ValueError, binascii.Error):
            continue

    return False


def _parse_size_bytes(size_str: str) -> int:
    """
    Parse size value from report row.
    Examples:
    - "1165505347" -> 1165505347
    - "1,165,505,347" -> 1165505347
    """
    raw = (size_str or '').strip()
    if not raw:
        return 0

    normalized = raw.replace(',', '')
    try:
        return int(normalized)
    except (ValueError, TypeError):
        pass

    try:
        return int(float(normalized))
    except (ValueError, TypeError):
        return 0


def _extract_sample_info(filename: str) -> tuple:
    """
    Extract sample name and read number from filename.
    Example: Col-0Day10_5-5X_1.fastq.gz -> ('Col-0Day10_5-5X', 1)
    Example: Sample_2.fastq.gz -> ('Sample', 2)
    Example: SampleName.fastq.gz -> ('SampleName', 0)
    """
    base = filename
    for ext in ['.fastq.gz', '.fq.gz', '.fastq', '.fq']:
        if base.endswith(ext):
            base = base[:-len(ext)]
            break

    # Detect _1/_2 suffix (paired-end).
    match_paired = re.match(r'^(.+?)_([12])$', base)
    if match_paired:
        return match_paired.group(1), int(match_paired.group(2))

    # Detect _R1/_R2 suffix (paired-end).
    match_r = re.match(r'^(.+?)_R([12])$', base, re.IGNORECASE)
    if match_r:
        return match_r.group(1), int(match_r.group(2))

    # Single-end
    return base, 0
