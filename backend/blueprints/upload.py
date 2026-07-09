"""
VizR Upload Blueprint
"""
from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.utils import secure_filename
from werkzeug.exceptions import ClientDisconnected
from datetime import datetime, timezone, timedelta
import logging
import sqlite3
import os
import hashlib

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Import validators
from backend.utils.fastq_validator import validate_fastq_file
from backend.utils.fasta_validator import validate_fasta_file
from backend.utils.file_format_detector import detect_file_format

# Create blueprint
upload_bp = Blueprint('upload', __name__, url_prefix='/api/upload')

# Import database configuration
from config.backend_settings import BackendConfig as Config
from config.shared_config import SharedConfig
DATABASE_FILE = Config.DATABASE_FILE

def get_db_connection():
    """Get database connection with foreign key support."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
    return conn

def require_auth(f):
    """Decorator to require authentication for routes."""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def get_workbench_name_by_id(workbench_id):
    """Get filesystem-safe workbench name by workbench ID."""
    conn = get_db_connection()
    try:
        workbench = conn.execute(
            'SELECT name FROM vizr_workbench WHERE id = ?', 
            (workbench_id,)
        ).fetchone()
        if workbench:
            # Make filesystem-safe
            return workbench['name'].replace(' ', '_').replace('/', '_').replace('\\', '_')
        return None
    finally:
        conn.close()

def calculate_md5(file_path: str) -> str:
    """Calculate MD5 checksum of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating MD5 for {file_path}: {e}")
        return ""


def _save_temp_upload(file_storage, temp_dir: str):
    filename = secure_filename(file_storage.filename)
    temp_filename = filename
    temp_file_path = os.path.join(temp_dir, temp_filename)
    temp_file_path_incomplete = temp_file_path + '.incomplete'

    file_storage.save(temp_file_path_incomplete)
    file_size = os.path.getsize(temp_file_path_incomplete)
    os.rename(temp_file_path_incomplete, temp_file_path)
    return temp_filename, temp_file_path, file_size

@upload_bp.route('/temp', methods=['POST'])
@require_auth
def upload_temp_file():
    """Upload file to temporary storage during workbench creation."""
    try:
        user_id = session.get('user_id')
        username = session.get('username')

        if 'file' not in request.files:
            logger.error("No file provided in request")
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            logger.error("Empty filename provided")
            return jsonify({'error': 'No file selected'}), 400

        logger.info(f"Processing temp upload: {file.filename} from user {username}")

        # Create temp upload directory for user
        user_id = session['user_id']
        username = session['username']
        temp_base_dir = os.path.join(SharedConfig.VIZR_PATH, "users")  # Docker volume mounted at /data
        temp_dir = os.path.join(temp_base_dir, username, "tmp")
        os.makedirs(temp_dir, exist_ok=True)

        # Generate upload ID first (millisecond timestamp)
        import time
        temp_upload_id = int(time.time() * 1000)

        filename = secure_filename(file.filename)
        temp_file_path = os.path.join(temp_dir, filename)
        temp_file_path_incomplete = temp_file_path + '.incomplete'

        try:
            temp_filename, temp_file_path, file_size = _save_temp_upload(file, temp_dir)
            logger.info(f"File saved successfully: {temp_filename} ({file_size} bytes)")

        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, IOError, ClientDisconnected) as err:
            # Handle upload interruption/cancellation
            logger.warning(f"Upload cancelled by client: {type(err).__name__}")

            # Clean up incomplete file if it exists
            if os.path.exists(temp_file_path_incomplete):
                try:
                    os.remove(temp_file_path_incomplete)
                except Exception as cleanup_err:
                    logger.error(f"Error cleaning up incomplete file: {cleanup_err}")

            return jsonify({'error': 'Upload cancelled by client'}), 499

        except Exception as save_error:
            # Handle other errors
            logger.error(f"Error saving file {filename}: {type(save_error).__name__} - {save_error}")

            # Clean up incomplete file if it exists
            if os.path.exists(temp_file_path_incomplete):
                try:
                    os.remove(temp_file_path_incomplete)
                except Exception as cleanup_err:
                    logger.error(f"Error during cleanup: {cleanup_err}")

            raise save_error

        file_size = os.path.getsize(temp_file_path)

        # Validate file format based on extension or content
        validation_error = None
        detected_format = None

        # Try to determine format from extension first
        if filename.lower().endswith(('.fastq', '.fastq.gz', '.fq', '.fq.gz')):
            detected_format = 'fastq'
        elif filename.lower().endswith(('.fasta', '.fasta.gz', '.fa', '.fa.gz')):
            detected_format = 'fasta'
        elif filename.lower().endswith('.gz'):
            # For .gz files without clear extension, detect format from content
            logger.info(f"Detecting format for {filename} from content...")
            detected_format, error_msg = detect_file_format(temp_file_path, max_lines=100)
            if detected_format is None:
                validation_error = error_msg
                logger.warning(f"Format detection failed for {filename}: {error_msg}")
            else:
                logger.info(f"Detected format for {filename}: {detected_format.upper()}")

        # Validate based on detected format
        if detected_format == 'fastq' and not validation_error:
            logger.info(f"Starting FASTQ validation for {filename} (size: {file_size} bytes)")
            is_valid, error_message = validate_fastq_file(temp_file_path, sample_size=10000)
            if not is_valid:
                validation_error = error_message
                logger.warning(f"FASTQ validation failed for {filename}: {error_message}")
            else:
                logger.info(f"FASTQ validation passed for {filename}")

        elif detected_format == 'fasta' and not validation_error:
            logger.info(f"Starting FASTA validation for {filename} (size: {file_size} bytes)")
            is_valid, error_message = validate_fasta_file(temp_file_path, sample_size=1000)
            if not is_valid:
                validation_error = error_message
                logger.warning(f"FASTA validation failed for {filename}: {error_message}")
            else:
                logger.info(f"FASTA validation passed for {filename}")

        elif not detected_format and not validation_error:
            # Unsupported file type - reject it
            validation_error = f"Unsupported file type. Only FASTQ (.fastq, .fq) and FASTA (.fasta, .fa) files are supported (gzip compressed files are also supported)."
            logger.warning(f"Unsupported file type rejected: {filename}")

        # If validation failed or unsupported format, delete file and return error
        if validation_error:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.info(f"Deleted invalid file: {temp_filename}")

            return jsonify({
                'error': validation_error,
                'file_invalid': True
            }), 400

        logger.info(f"Temp file uploaded: {temp_filename} (ID: {temp_upload_id})")

        return jsonify({
            'message': 'File uploaded successfully',
            'temp_upload_id': temp_upload_id,
            'temp_filename': temp_filename,
            'original_filename': filename,
            'file_size': file_size
        })

    except ClientDisconnected as e:
        # Handle client disconnection during request parsing
        logger.warning(f"Client disconnected during request parsing: {e}")
        return jsonify({'error': 'Upload cancelled by client'}), 499

    except Exception as e:
        logger.error(f"Temp file upload error: {type(e).__name__} - {e}", exc_info=True)
        return jsonify({'error': 'File upload failed'}), 500


@upload_bp.route('/temp-matrix', methods=['POST'])
@require_auth
def upload_temp_matrix_file():
    """Upload matrix file to temporary storage without FASTQ/FASTA validation."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        username = session['username']
        temp_base_dir = os.path.join(SharedConfig.VIZR_PATH, "users")
        temp_dir = os.path.join(temp_base_dir, username, "tmp")
        os.makedirs(temp_dir, exist_ok=True)

        import time
        temp_upload_id = int(time.time() * 1000)

        temp_filename, _, file_size = _save_temp_upload(file, temp_dir)

        logger.info(f"Matrix temp file uploaded: {temp_filename} ({file_size} bytes)")
        return jsonify({
            'message': 'Matrix file uploaded successfully',
            'temp_upload_id': temp_upload_id,
            'temp_filename': temp_filename,
            'original_filename': secure_filename(file.filename),
            'file_size': file_size
        })
    except ClientDisconnected:
        return jsonify({'error': 'Upload cancelled by client'}), 499
    except Exception as e:
        logger.error(f"Matrix temp file upload error: {type(e).__name__} - {e}", exc_info=True)
        return jsonify({'error': 'Matrix file upload failed'}), 500

@upload_bp.route('/temp/<path:filename>', methods=['DELETE'])
@require_auth
def delete_temp_file(filename):
    """Delete temporary uploaded file by filename."""
    logger.info(f"🗑️ [DELETE-TEMP] Request received - Filename: {filename}, User: {session.get('username')}")
    try:
        username = session['username']
        temp_base_dir = os.path.join(SharedConfig.VIZR_PATH, "users")
        temp_dir = os.path.join(temp_base_dir, username, "tmp")

        # Secure the filename to prevent path traversal
        safe_filename = secure_filename(filename)
        file_path = os.path.join(temp_dir, safe_filename)

        logger.info(f"🔍 [DELETE-TEMP] Looking for file: {file_path}")

        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            logger.info(f"✅ [DELETE-TEMP] File deleted: {safe_filename}")
            return jsonify({
                'message': 'File deleted successfully',
                'filename': safe_filename
            })
        else:
            logger.warning(f"⚠️ [DELETE-TEMP] File not found: {safe_filename}")
            return jsonify({'error': 'File not found'}), 404

    except Exception as e:
        logger.error(f"Temp file deletion error: {type(e).__name__} - {e}", exc_info=True)
        return jsonify({'error': 'File deletion failed'}), 500
