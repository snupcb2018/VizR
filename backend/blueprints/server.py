"""
VizR Server File Validation Blueprint
"""
from flask import Blueprint, request, jsonify, session
import os
import logging

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Import validators
from backend.utils.fastq_validator import validate_fastq_file, detect_read_type
from backend.utils.fasta_validator import validate_fasta_file
from backend.utils.file_format_detector import detect_file_format
from backend.utils.files import is_gzip_file

# Create blueprint
server_bp = Blueprint('server', __name__, url_prefix='/api/server')

def require_auth(f):
    """Decorator to require authentication for routes."""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


@server_bp.route('/validate-files', methods=['POST'])
@require_auth
def validate_server_files():
    """
    Validate server file paths before workbench creation.

    Request JSON:
    {
        "file_paths": ["path1", "path2", ...]
    }

    Response JSON:
    {
        "valid_files": [
            {
                "path": "path1",
                "filename": "file1.fastq.gz",
                "format": "fastq",
                "is_gzipped": true,
                "read_type": "short",
                "size": 12345
            }
        ],
        "invalid_files": [
            {
                "path": "path2",
                "filename": "file2.txt",
                "error": "Unsupported file type"
            }
        ]
    }
    """
    try:
        data = request.get_json()

        if not data or 'file_paths' not in data:
            return jsonify({'error': 'file_paths is required'}), 400

        file_paths = data['file_paths']

        if not isinstance(file_paths, list):
            return jsonify({'error': 'file_paths must be a list'}), 400

        if len(file_paths) == 0:
            return jsonify({'error': 'At least one file path is required'}), 400

        username = session.get('username')
        logger.info(f"Validating {len(file_paths)} server file(s) for user {username}")

        valid_files = []
        invalid_files = []

        for file_path in file_paths:
            file_path = file_path.strip()
            if not file_path:
                continue

            validation_result = validate_single_file(file_path)

            if validation_result['valid']:
                valid_files.append(validation_result['file_info'])
            else:
                invalid_files.append({
                    'path': file_path,
                    'filename': os.path.basename(file_path),
                    'error': validation_result['error']
                })

        logger.info(f"Validation complete: {len(valid_files)} valid, {len(invalid_files)} invalid")

        return jsonify({
            'valid_files': valid_files,
            'invalid_files': invalid_files
        })

    except Exception as e:
        logger.error(f"Server file validation error: {type(e).__name__} - {e}", exc_info=True)
        return jsonify({'error': 'File validation failed'}), 500


def validate_single_file(file_path: str) -> dict:
    """
    Validate a single server file.

    Returns:
        dict with 'valid' (bool), 'file_info' (dict) or 'error' (str)
    """
    filename = os.path.basename(file_path)

    # Check 1: File exists
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return {
            'valid': False,
            'error': 'File not found'
        }

    # Check 2: Is a file (not directory)
    if not os.path.isfile(file_path):
        logger.warning(f"Path is not a file: {file_path}")
        return {
            'valid': False,
            'error': 'Path is not a file'
        }

    # Get file size
    try:
        file_size = os.path.getsize(file_path)
    except Exception as e:
        logger.error(f"Error getting file size for {file_path}: {e}")
        return {
            'valid': False,
            'error': 'Cannot access file'
        }

    # Check 3: File format (FASTQ or FASTA)
    validation_error = None
    detected_format = None
    is_gzipped = False
    read_type = None

    # Check if file is gzipped
    is_gzipped = is_gzip_file(file_path)

    # Try to determine format from extension first
    if filename.lower().endswith(('.fastq', '.fastq.gz', '.fq', '.fq.gz')):
        detected_format = 'fastq'
    elif filename.lower().endswith(('.fasta', '.fasta.gz', '.fa', '.fa.gz')):
        detected_format = 'fasta'
    elif filename.lower().endswith('.gz'):
        # For .gz files without clear extension, detect format from content
        logger.info(f"Detecting format for {filename} from content...")
        detected_format, error_msg = detect_file_format(file_path, max_lines=100)
        if detected_format is None:
            validation_error = error_msg
            logger.warning(f"Format detection failed for {filename}: {error_msg}")
        else:
            logger.info(f"Detected format for {filename}: {detected_format.upper()}")

    # Validate based on detected format
    if detected_format == 'fastq' and not validation_error:
        logger.info(f"Starting FASTQ validation for {filename} (size: {file_size} bytes)")

        # Check 4: FASTQ validation
        is_valid, error_message = validate_fastq_file(file_path, sample_size=10000)
        if not is_valid:
            validation_error = error_message
            logger.warning(f"FASTQ validation failed for {filename}: {error_message}")
        else:
            logger.info(f"FASTQ validation passed for {filename}")

            # Detect read type (short-read vs long-read)
            try:
                read_type_result = detect_read_type(file_path, sample_size=10000)
                read_type = read_type_result  # 'short' or 'long'
                logger.info(f"Detected read type for {filename}: {read_type}")
            except Exception as e:
                logger.warning(f"Failed to detect read type for {filename}: {e}")
                read_type = 'unknown'

    elif detected_format == 'fasta' and not validation_error:
        logger.info(f"Starting FASTA validation for {filename} (size: {file_size} bytes)")

        # Check 4: FASTA validation
        is_valid, error_message = validate_fasta_file(file_path, sample_size=1000)
        if not is_valid:
            validation_error = error_message
            logger.warning(f"FASTA validation failed for {filename}: {error_message}")
        else:
            logger.info(f"FASTA validation passed for {filename}")
            # FASTA files don't have read type distinction
            read_type = 'n/a'

    elif not detected_format and not validation_error:
        # Unsupported file type - reject it
        validation_error = f"Unsupported file type. Only FASTQ (.fastq, .fq) and FASTA (.fasta, .fa) files are supported (gzip compressed files are also supported)."
        logger.warning(f"Unsupported file type rejected: {filename}")

    # Return validation result
    if validation_error:
        return {
            'valid': False,
            'error': validation_error
        }

    return {
        'valid': True,
        'file_info': {
            'path': file_path,
            'filename': filename,
            'format': detected_format,
            'is_gzipped': is_gzipped,
            'read_type': read_type,
            'size': file_size
        }
    }
