"""
VizR Settings Blueprint - User Settings Management
사용자별 설정 관리를 위한 Flask Blueprint
"""
from flask import Blueprint, request, jsonify, session
import logging
import sqlite3
import json
import time
from typing import Optional, Dict, Any
import requests

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

# Import database configuration
from config.backend_settings import BackendConfig as Config
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

class UserSettings:
    """Generic user settings management class"""

    @staticmethod
    def get_user_settings(user_id: int) -> Dict[str, Any]:
        """Get all user settings as dictionary"""
        conn = get_db_connection()
        try:
            user = conn.execute(
                'SELECT settings FROM users WHERE id = ?',
                (user_id,)
            ).fetchone()

            if not user or not user['settings']:
                return {}

            return json.loads(user['settings'])
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid settings JSON for user {user_id}")
            return {}
        finally:
            conn.close()

    @staticmethod
    def set_user_settings(user_id: int, settings: Dict[str, Any]):
        """Set all user settings from dictionary"""
        conn = get_db_connection()
        try:
            settings_json = json.dumps(settings)
            conn.execute(
                'UPDATE users SET settings = ? WHERE id = ?',
                (settings_json, user_id)
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_value(user_id: int, key: str, default_value: Any = None) -> Any:
        """Get a specific setting value"""
        settings = UserSettings.get_user_settings(user_id)
        return settings.get(key, default_value)

    @staticmethod
    def set_value(user_id: int, key: str, value: Any):
        """Set a specific setting value"""
        settings = UserSettings.get_user_settings(user_id)
        settings[key] = value
        UserSettings.set_user_settings(user_id, settings)

    @staticmethod
    def get_values(user_id: int, keys: list, defaults: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get multiple setting values"""
        if defaults is None:
            defaults = {}

        settings = UserSettings.get_user_settings(user_id)
        result = {}

        for key in keys:
            result[key] = settings.get(key, defaults.get(key))

        return result

    @staticmethod
    def set_values(user_id: int, values: Dict[str, Any]):
        """Set multiple setting values"""
        settings = UserSettings.get_user_settings(user_id)
        settings.update(values)
        UserSettings.set_user_settings(user_id, settings)

    @staticmethod
    def delete_value(user_id: int, key: str) -> bool:
        """Delete a specific setting value"""
        settings = UserSettings.get_user_settings(user_id)
        if key in settings:
            del settings[key]
            UserSettings.set_user_settings(user_id, settings)
            return True
        return False

@settings_bp.route('/value', methods=['GET'])
@require_auth
def get_setting_value():
    """Get setting value(s). Supports batch queries with multiple key parameters."""
    try:
        user_id = session['user_id']
        username = session.get('username', 'Unknown')

        # Check if multiple key parameters are provided
        keys = request.args.getlist('key')

        logger.debug(f"[SETTINGS GET] User {username} (ID: {user_id}) requesting keys: {keys}")

        if not keys:
            logger.warning(f"[SETTINGS GET] User {username} - missing key parameter")
            return jsonify({'error': 'Key parameter is required'}), 400

        # Check for batch query (multiple keys)
        is_batch_query = len(keys) > 1
        logger.debug(f"[SETTINGS GET] User {username} - batch query detected: {is_batch_query} ({len(keys)} keys)")

        if is_batch_query:
            defaults = {}

            logger.debug(f"[SETTINGS GET] User {username} - batch query for keys: {keys}")

            # Parse defaults from query parameters
            for k in keys:
                default_param = f'default_{k}'
                if default_param in request.args:
                    try:
                        defaults[k] = json.loads(request.args.get(default_param))
                    except json.JSONDecodeError:
                        defaults[k] = request.args.get(default_param)

            # Get all user settings first for debugging
            all_settings = UserSettings.get_user_settings(user_id)
            logger.debug(f"[SETTINGS GET] User {username} - all stored settings: {all_settings}")

            raw_values = UserSettings.get_values(user_id, keys, defaults)
            logger.debug(f"[SETTINGS GET] User {username} - raw_values result: {raw_values}")

            # Convert to expected format with exists flag
            values = {}
            for k in keys:
                stored_value = UserSettings.get_value(user_id, k)
                final_value = raw_values.get(k, defaults.get(k))
                exists = stored_value is not None
                values[k] = {
                    'value': final_value,
                    'exists': exists
                }
                logger.debug(f"[SETTINGS GET] User {username} - key '{k}': stored={stored_value}, final={final_value}, exists={exists}")

            logger.debug(f"[SETTINGS GET] User {username} - batch result: {len(values)} values returned")
            logger.debug(f"[SETTINGS GET] User {username} - final batch response: {values}")
            return jsonify({'values': values})
        else:
            # Single key query
            key = keys[0]
            default_value = None
            if 'default' in request.args:
                try:
                    default_value = json.loads(request.args.get('default'))
                except json.JSONDecodeError:
                    default_value = request.args.get('default')

            stored_value = UserSettings.get_value(user_id, key)
            value = stored_value if stored_value is not None else default_value
            exists = stored_value is not None

            logger.info(f"[SETTINGS GET] User {username} - single key '{key}' result: exists={exists}")
            return jsonify({
                'key': key,
                'value': value,
                'exists': exists
            })

    except Exception as e:
        logger.error(f"[SETTINGS GET] Error getting setting value for user {session.get('username', 'Unknown')}: {e}")
        return jsonify({'error': 'Failed to get setting value'}), 500

@settings_bp.route('/value', methods=['PUT'])
@require_auth
def set_setting_value():
    """Set setting value(s). Supports batch updates."""
    try:
        user_id = session['user_id']
        username = session.get('username', 'Unknown')
        data = request.get_json()

        logger.debug(f"[SETTINGS PUT] User {username} (ID: {user_id}) saving settings")

        # Log sanitized request data (hide sensitive values)
        sanitized_data = {}
        if data:
            for key, value in data.items():
                if key == 'values' and isinstance(value, dict):
                    sanitized_values = {}
                    for k, v in value.items():
                        if 'api_key' in k.lower() or 'password' in k.lower() or 'secret' in k.lower():
                            sanitized_values[k] = f"{'*' * min(8, len(str(v)) if v else 0)}" if v else None
                        else:
                            sanitized_values[k] = v
                    sanitized_data[key] = sanitized_values
                elif 'api_key' in key.lower() or 'password' in key.lower() or 'secret' in key.lower():
                    sanitized_data[key] = f"{'*' * min(8, len(str(value)) if value else 0)}" if value else None
                else:
                    sanitized_data[key] = value

        logger.debug(f"[SETTINGS PUT] Request data: {sanitized_data}")

        if not data:
            logger.warning(f"[SETTINGS PUT] User {username} - empty request body")
            return jsonify({'error': 'Request body is required'}), 400

        # Check for batch update (values object)
        if 'values' in data:
            values = data['values']
            if not isinstance(values, dict):
                logger.error(f"[SETTINGS PUT] User {username} - values is not a dict: {type(values)}")
                return jsonify({'error': 'Values must be an object'}), 400

            logger.debug(f"[SETTINGS PUT] User {username} - batch update with {len(values)} settings")
            logger.debug(f"[SETTINGS PUT] User {username} - batch values keys: {list(values.keys())}")

            # Get current settings before update
            current_settings = UserSettings.get_user_settings(user_id)
            logger.debug(f"[SETTINGS PUT] User {username} - current settings keys: {list(current_settings.keys()) if current_settings else 'None'}")

            UserSettings.set_values(user_id, values)

            # Get settings after update to verify
            updated_settings = UserSettings.get_user_settings(user_id)
            logger.debug(f"[SETTINGS PUT] User {username} - updated settings keys: {list(updated_settings.keys()) if updated_settings else 'None'}")
            logger.info(f"[SETTINGS PUT] User {username} - successfully saved {len(values)} settings")
            return jsonify({'message': f'Successfully updated {len(values)} settings'})
        else:
            # Single key update
            key = data.get('key')
            value = data.get('value')

            # Log with sanitized value for sensitive keys
            if 'api_key' in key.lower() or 'password' in key.lower() or 'secret' in key.lower():
                sanitized_value = f"{'*' * min(8, len(str(value)) if value else 0)}" if value else None
                logger.debug(f"[SETTINGS PUT] User {username} - single update for key: {key}, value: {sanitized_value}")
            else:
                logger.debug(f"[SETTINGS PUT] User {username} - single update for key: {key}")

            if not key:
                logger.warning(f"[SETTINGS PUT] User {username} - missing key in single update")
                return jsonify({'error': 'Key is required'}), 400

            UserSettings.set_value(user_id, key, value)
            logger.info(f"[SETTINGS PUT] User {username} - successfully saved setting: {key}")
            return jsonify({'message': f'Successfully updated setting: {key}'})

    except Exception as e:
        logger.error(f"[SETTINGS PUT] Error setting setting value for user {session.get('username', 'Unknown')}: {e}")
        return jsonify({'error': 'Failed to set setting value'}), 500

@settings_bp.route('/value', methods=['DELETE'])
@require_auth
def delete_setting_value():
    """Delete setting value(s). Supports batch deletion with multiple key parameters."""
    try:
        user_id = session['user_id']
        keys = request.args.getlist('key')

        if not keys:
            return jsonify({'error': 'Key parameter is required'}), 400

        # Check for batch deletion (multiple keys)
        if len(keys) > 1:
            deleted_count = 0

            for k in keys:
                if UserSettings.delete_value(user_id, k):
                    deleted_count += 1

            return jsonify({'message': f'Successfully deleted {deleted_count} of {len(keys)} settings'})
        else:
            # Single key deletion
            key = keys[0]
            if UserSettings.delete_value(user_id, key):
                return jsonify({'message': f'Successfully deleted setting: {key}'})
            else:
                return jsonify({'message': f'Setting not found: {key}'}), 404

    except Exception as e:
        logger.error(f"Error deleting setting value: {e}")
        return jsonify({'error': 'Failed to delete setting value'}), 500

@settings_bp.route('/ai/test-connection', methods=['POST'])
@require_auth
def test_ai_connection():
    """Test AI provider connection with provided settings."""
    try:
        user_id = session['user_id']
        username = session.get('username', 'Unknown')

        logger.info(f"[AI TEST] User {username} (ID: {user_id}) testing AI connection")
        data = request.get_json(silent=True)

        # If no data provided, use current user settings
        if not data:
            logger.info(f"[AI TEST] User {username} - using current user settings for test")

            # Get current AI settings from database
            current_settings = UserSettings.get_values(user_id, [
                'ai.provider',
                'ai.model',
                'ai.api_key'
            ])

            provider = current_settings.get('ai.provider')
            model = current_settings.get('ai.model')
            api_key = current_settings.get('ai.api_key')
        else:
            # Use provided parameters (for testing new credentials before saving)
            provider = data.get('provider')
            model = data.get('model')
            api_key = data.get('api_key')

            # If api_key is None, use configured API key
            if api_key is None:
                logger.info(f"[AI TEST] User {username} - API key is None, using configured key")
                current_settings = UserSettings.get_values(user_id, ['ai.api_key'])
                api_key = current_settings.get('ai.api_key')


        logger.info(f"[AI TEST] User {username} - testing provider: {provider}, model: {model}, has_api_key: {bool(api_key)}")

        if not provider or not model or not api_key:
            logger.warning(f"[AI TEST] User {username} - missing test parameters: provider={bool(provider)}, model={bool(model)}, api_key={bool(api_key)}")
            return jsonify({
                'status': 'error',
                'message': 'Provider, model, and API key are required for testing. Please configure AI settings first.'
            }), 400

        # Test connection based on provider using actual AI clients
        start_time = time.time()
        logger.info(f"[AI TEST] User {username} - starting {provider} connection test")

        try:
            # Create AI client directly based on provider
            if provider == 'google':
                from backend.utils.ai.ai_model_google import GoogleAIClient
                client = GoogleAIClient(user_id=user_id, api_key=api_key, model_name=model)
                test_result = client.test_connection()
            elif provider == 'openai':
                from backend.utils.ai.ai_model_openai import OpenAIClient
                client = OpenAIClient(user_id=user_id, api_key=api_key, model_name=model)
                test_result = client.test_connection()
            elif provider == 'anthropic':
                from backend.utils.ai.ai_model_anthropy import AnthropicClient
                client = AnthropicClient(user_id=user_id, api_key=api_key, model_name=model)
                test_result = client.test_connection()
            else:
                test_result = {
                    'success': False,
                    'error': f'Unsupported provider: {provider}'
                }

            response_time = time.time() - start_time
            success = test_result.get('success', False)
            message = test_result.get('message') or test_result.get('error', 'Unknown error')

            logger.info(f"[AI TEST] User {username} - test result: {success}, time: {response_time:.2f}s, message: {message}")

            return jsonify({
                'status': 'success' if success else 'error',
                'message': message,
                'response_time': round(response_time, 2)
            })

        except Exception as e:
            logger.error(f"[AI TEST] User {username} - connection test failed: {e}")
            return jsonify({
                'status': 'error',
                'message': f'Connection test failed: {str(e)}',
                'response_time': round(time.time() - start_time, 2)
            })

    except Exception as e:
        logger.error(f"[AI TEST] Error testing AI connection for user {session.get('username', 'Unknown')}: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Connection test failed'
        }), 500


# ===========================
# Reference Genome Management APIs
# ===========================
# 이 코드를 settings.py 파일 끝에 복사 붙여넣기 하세요

from config.shared_config import SharedConfig
import os
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename

def get_current_username():
    """Get current logged-in username from session"""
    return session.get('username', 'Unknown')

def calculate_reference_size(reference_dir, ref_set):
    """Calculate total size of reference files in MB"""
    total_size = 0
    ref_set_path = os.path.join(reference_dir, ref_set)

    if not os.path.exists(ref_set_path):
        return 0

    for root, dirs, files in os.walk(ref_set_path):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)

    return total_size / (1024 * 1024)

@settings_bp.route('/references', methods=['GET'])
@require_auth
def list_references():
    """사용자의 Reference 세트 목록 조회"""
    try:
        username = get_current_username()
        logger.info(f"[REFERENCE LIST] 🔍 User {username} requesting reference list")

        user_resource_dir = f"{SharedConfig.VIZR_PATH}/users/{username}/resource"
        logger.info(f"[REFERENCE LIST] 📁 Resource directory: {user_resource_dir}")
        references = []

        for species in ['arabidopsis', 'lemna_gibba', 'lemna_minor']:
            reference_dir = os.path.join(user_resource_dir, species, 'reference')
            logger.info(f"[REFERENCE LIST] 🧬 Checking species '{species}' at: {reference_dir}")

            if not os.path.exists(reference_dir):
                logger.info(f"[REFERENCE LIST]   ⚠️  Directory does not exist, skipping")
                continue

            ref_sets_found = os.listdir(reference_dir)
            logger.info(f"[REFERENCE LIST]   📂 Found {len(ref_sets_found)} items: {ref_sets_found}")

            for ref_set in ref_sets_found:
                ref_set_path = os.path.join(reference_dir, ref_set)
                metadata_file = os.path.join(ref_set_path, 'metadata.json')

                logger.info(f"[REFERENCE LIST]     🔎 Examining: {ref_set}")
                logger.info(f"[REFERENCE LIST]       - Path: {ref_set_path}")
                logger.info(f"[REFERENCE LIST]       - Is directory: {os.path.isdir(ref_set_path)}")
                logger.info(f"[REFERENCE LIST]       - Metadata exists: {os.path.exists(metadata_file)}")

                if os.path.isdir(ref_set_path) and os.path.exists(metadata_file):
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)

                        total_size = calculate_reference_size(reference_dir, ref_set)

                        ref_info = {
                            'name': metadata.get('name', ref_set),
                            'version': metadata.get('version', 'Unknown'),
                            'species': metadata.get('species', species),
                            'organism': metadata.get('organism', ''),
                            'description': metadata.get('description', ''),
                            'is_default': metadata.get('is_default', False),
                            'total_size_mb': round(total_size, 2),
                            'created_at': metadata.get('created_at', '')
                        }
                        references.append(ref_info)
                        logger.info(f"[REFERENCE LIST]       ✅ Added: {ref_info['name']} (species: {ref_info['species']})")
                    except Exception as e:
                        logger.error(f"[REFERENCE LIST]       ❌ Error reading {ref_set}: {e}")
                else:
                    logger.info(f"[REFERENCE LIST]       ⏭️  Skipped (not a valid reference set)")

        logger.info(f"[REFERENCE LIST] 📊 Total references found: {len(references)}")
        # Format reference list without nested f-strings
        ref_list = [f"{r['name']}({r['species']})" for r in references]
        logger.info(f"[REFERENCE LIST] 📋 Reference list: {ref_list}")
        return jsonify({'references': references})
    except Exception as e:
        logger.error(f"[REFERENCE LIST] Error: {e}")
        return jsonify({'error': 'Failed to list references'}), 500

@settings_bp.route('/references/upload', methods=['POST'])
@require_auth
def upload_reference():
    """새 Reference 세트 업로드"""
    try:
        username = get_current_username()

        if 'cdna' not in request.files or 'genomic' not in request.files or 'gtf' not in request.files:
            return jsonify({'error': 'Missing required files'}), 400

        name = request.form.get('name')
        if not name:
            return jsonify({'error': 'Reference name is required'}), 400

        user_resource_dir = f"{SharedConfig.VIZR_PATH}/users/{username}/resource"
        species = request.form.get('species', 'arabidopsis')
        ref_set_dir = os.path.join(user_resource_dir, species, 'reference', name)

        if os.path.exists(ref_set_dir):
            return jsonify({'error': f'Reference "{name}" already exists'}), 400

        os.makedirs(ref_set_dir, exist_ok=True)
        for tool in ['bowtie2', 'rsem', 'hisat2']:
            os.makedirs(os.path.join(ref_set_dir, 'indexes', tool), exist_ok=True)

        cdna_file = request.files['cdna']
        genomic_file = request.files['genomic']
        gtf_file = request.files['gtf']

        cdna_filename = secure_filename(cdna_file.filename)
        genomic_filename = secure_filename(genomic_file.filename)
        gtf_filename = secure_filename(gtf_file.filename)

        cdna_file.save(os.path.join(ref_set_dir, cdna_filename))
        genomic_file.save(os.path.join(ref_set_dir, genomic_filename))
        gtf_file.save(os.path.join(ref_set_dir, gtf_filename))

        metadata = {
            'name': name,
            'version': request.form.get('version', '1.0'),
            'species': species,
            'organism': request.form.get('organism', ''),
            'description': request.form.get('description', ''),
            'created_at': datetime.now().isoformat(),
            'uploaded_by': username,
            'is_default': False,
            'files': {
                'cdna': cdna_filename,
                'genomic': genomic_filename,
                'annotation': gtf_filename
            },
            'indexes': {
                'bowtie2': 'indexes/bowtie2',
                'rsem': 'indexes/rsem',
                'hisat2': 'indexes/hisat2'
            }
        }

        with open(os.path.join(ref_set_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return jsonify({'success': True, 'message': 'Reference uploaded successfully'})
    except Exception as e:
        logger.error(f"[REFERENCE UPLOAD] Error: {e}")
        if 'ref_set_dir' in locals() and os.path.exists(ref_set_dir):
            shutil.rmtree(ref_set_dir, ignore_errors=True)
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/references/<name>', methods=['DELETE'])
@require_auth
def delete_reference(name):
    """Reference 세트 삭제"""
    try:
        username = get_current_username()
        species = request.args.get('species', 'arabidopsis')

        user_resource_dir = f"{SharedConfig.VIZR_PATH}/users/{username}/resource"
        ref_set_dir = os.path.join(user_resource_dir, species, 'reference', name)

        if not os.path.exists(ref_set_dir):
            return jsonify({'error': f'Reference "{name}" not found'}), 404

        metadata_file = os.path.join(ref_set_dir, 'metadata.json')
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            if metadata.get('is_default', False):
                return jsonify({'error': 'Cannot delete default reference'}), 400

        shutil.rmtree(ref_set_dir)
        return jsonify({'success': True, 'message': 'Reference deleted successfully'})
    except Exception as e:
        logger.error(f"[REFERENCE DELETE] Error: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/references/<name>/default', methods=['PUT'])
@require_auth
def set_default_reference(name):
    """기본 Reference 세트 설정"""
    try:
        username = get_current_username()
        data = request.get_json()
        species = data.get('species', 'arabidopsis')

        user_resource_dir = f"{SharedConfig.VIZR_PATH}/users/{username}/resource"
        reference_dir = os.path.join(user_resource_dir, species, 'reference')

        for ref_set in os.listdir(reference_dir):
            metadata_file = os.path.join(reference_dir, ref_set, 'metadata.json')
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                metadata['is_default'] = (ref_set == name)
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

        return jsonify({'success': True, 'message': f'{name} set as default'})
    except Exception as e:
        logger.error(f"[REFERENCE DEFAULT] Error: {e}")
        return jsonify({'error': str(e)}), 500
