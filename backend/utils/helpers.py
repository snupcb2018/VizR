"""
VizR General Helper Utilities
"""
import os
import hashlib
import logging
from datetime import datetime
from typing import Optional

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

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

def ensure_directory_exists(directory_path: str) -> None:
    """Ensure a directory exists, create if it doesn't."""
    os.makedirs(directory_path, exist_ok=True)

def create_workbench_directories(workbench_folder: str, workbench_id: int) -> str:
    """Create directory structure for a new workbench."""
    workbench_dir = os.path.join(workbench_folder, f'wb_{workbench_id}')
    ensure_directory_exists(workbench_dir)
    ensure_directory_exists(os.path.join(workbench_dir, 'raw_data'))
    ensure_directory_exists(os.path.join(workbench_dir, 'analysis'))
    ensure_directory_exists(os.path.join(workbench_dir, 'results'))
    return workbench_dir

def get_file_extension(filename: str) -> str:
    """Get file extension from filename."""
    return filename.split('.')[-1].lower() if '.' in filename else ''

def generate_timestamped_filename(original_filename: str) -> str:
    """Generate a timestamped filename to avoid conflicts."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{timestamp}_{original_filename}"

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f}{size_names[i]}"

def validate_bioproject_id(bioproject_id: str) -> bool:
    """Validate NCBI BioProject ID format."""
    # BioProject IDs typically start with PRJNA followed by digits
    return bioproject_id.startswith('PRJNA') and len(bioproject_id) > 5

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Remove or replace potentially dangerous characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename.strip()

class APIResponse:
    """Helper class for consistent API responses."""
    
    @staticmethod
    def success(data: dict, message: str = "Success", status_code: int = 200) -> tuple:
        """Create success response."""
        response = {
            'success': True,
            'message': message,
            'data': data
        }
        return response, status_code
    
    @staticmethod
    def error(message: str, status_code: int = 400, details: Optional[dict] = None) -> tuple:
        """Create error response."""
        response = {
            'success': False,
            'error': message
        }
        if details:
            response['details'] = details
        return response, status_code