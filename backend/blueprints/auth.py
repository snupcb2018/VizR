"""
VizR Authentication Blueprint
"""
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import sqlite3
import os
import shutil
import tarfile
from pathlib import Path
from typing import Dict, Any

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

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

def hash_password(password: str) -> str:
    """Hash password using werkzeug's secure method."""
    return generate_password_hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    return check_password_hash(password_hash, password)

def setup_user_directories(username: str) -> Dict[str, Any]:
    """
    Create user directory structure and copy resources.

    This function:
    1. Creates VIZR_PATH/users/{username} directory
    2. Copies /app/resource to user's resource directory
    3. Extracts tair10_reference.tar.gz if it exists

    Args:
        username: Username for directory creation

    Returns:
        {'success': True/False, 'error': 'error message if failed'}
    """
    try:
        # Create user directory
        user_dir = Path(SharedConfig.VIZR_PATH) / 'users' / username
        logger.info(f"Creating user directory: {user_dir}")
        user_dir.mkdir(parents=True, exist_ok=True)

        # Copy resource directory
        source_resource = Path('/app/resource')
        dest_resource = user_dir / 'resource'

        if not source_resource.exists():
            logger.error(f"Source resource directory does not exist: {source_resource}")
            return {'success': False, 'error': f'Source resource directory not found: {source_resource}'}

        logger.info(f"Copying resources from {source_resource} to {dest_resource}")
        shutil.copytree(source_resource, dest_resource, dirs_exist_ok=False)

        # Extract tair10_reference.tar.gz
        tar_file = dest_resource / 'arabidopsis' / 'reference' / 'TAIR10' / 'tair10_reference.tar.gz'
        if tar_file.exists():
            logger.info(f"Extracting reference archive: {tar_file}")
            with tarfile.open(tar_file, 'r:gz') as tar:
                tar.extractall(path=tar_file.parent)
            logger.info(f"Successfully extracted reference files to {tar_file.parent}")

            # Remove the archive after successful extraction
            tar_file.unlink()
            logger.info(f"Removed archive file: {tar_file}")
        else:
            logger.warning(f"Reference archive not found: {tar_file}")

        logger.info(f"User directory setup completed successfully for: {username}")
        return {'success': True}

    except Exception as e:
        logger.error(f"User directory setup failed for {username}: {str(e)}", exc_info=True)
        return {'success': False, 'error': str(e)}

@auth_bp.route('/register', methods=['POST'])
@require_auth
def register():
    """Register a new user (Admin only)."""
    try:
        # Check if current user is admin
        conn = get_db_connection()
        current_user = conn.execute(
            'SELECT username FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()

        if not current_user or current_user['username'] != 'admin':
            conn.close()
            logger.warning(f"Unauthorized registration attempt by user_id={session['user_id']}")
            return jsonify({'error': 'Only admin can create new users'}), 403

        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        full_name = data.get('full_name', '').strip()

        if not all([username, email, password]):
            conn.close()
            return jsonify({'error': 'Username, email, and password are required'}), 400

        # Check if user already exists
        existing_user = conn.execute(
            'SELECT id FROM users WHERE username = ? OR email = ?',
            (username, email)
        ).fetchone()

        if existing_user:
            conn.close()
            return jsonify({'error': 'Username or email already exists'}), 409

        # Create new user with provided password
        password_hash = hash_password(password)
        cursor = conn.execute(
            '''INSERT INTO users (username, email, password_hash, full_name)
               VALUES (?, ?, ?, ?)''',
            (username, email, password_hash, full_name)
        )
        user_id = cursor.lastrowid

        # Setup user directories (before commit to allow rollback on failure)
        logger.info(f"Setting up directories for new user: {username} (ID: {user_id})")
        setup_result = setup_user_directories(username)

        if not setup_result['success']:
            # Rollback database transaction if directory setup fails
            conn.rollback()
            conn.close()
            error_msg = f"Failed to setup user directories: {setup_result.get('error', 'Unknown error')}"
            logger.error(f"User creation rolled back for {username}: {error_msg}")
            return jsonify({'error': error_msg}), 500

        # Commit transaction only after successful directory setup
        conn.commit()
        conn.close()

        logger.info(f"New user created successfully by admin: {username} (ID: {user_id})")
        return jsonify({
            'message': 'User created successfully',
            'user': {
                'id': user_id,
                'username': username,
                'email': email,
                'full_name': full_name
            }
        }), 201

    except Exception as e:
        logger.error(f"User creation error: {e}")
        return jsonify({'error': 'Failed to create user'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """Login user."""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        conn = get_db_connection()
        user = conn.execute(
            '''SELECT id, username, email, password_hash, full_name 
               FROM users WHERE username = ? OR email = ?''',
            (username, username)
        ).fetchone()
        conn.close()

        if not user or not verify_password(password, user['password_hash']):
            return jsonify({'error': 'Invalid credentials'}), 401

        # Create session
        session['user_id'] = user['id']
        session['username'] = user['username']

        logger.info(f"User logged in: {user['username']} (ID: {user['id']})")
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'full_name': user['full_name']
            }
        })

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@auth_bp.route('/logout', methods=['POST'])
@require_auth
def logout():
    """Logout user."""
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f"User logged out: {username}")
    return jsonify({'message': 'Logout successful'})

@auth_bp.route('/profile', methods=['GET'])
@require_auth
def get_profile():
    """Get current user profile."""
    try:
        conn = get_db_connection()
        user = conn.execute(
            '''SELECT id, username, email, full_name, created_at 
               FROM users WHERE id = ?''',
            (session['user_id'],)
        ).fetchone()
        conn.close()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        return jsonify({
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'full_name': user['full_name'],
                'created_at': user['created_at']
            }
        })

    except Exception as e:
        logger.error(f"Profile fetch error: {e}")
        return jsonify({'error': 'Failed to fetch profile'}), 500

@auth_bp.route('/profile', methods=['PUT'])
@require_auth
def update_profile():
    """Update user profile (email and full_name only)."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        full_name = data.get('full_name', '').strip()

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        conn = get_db_connection()

        # Check if email is already taken by another user
        existing_user = conn.execute(
            'SELECT id FROM users WHERE email = ? AND id != ?',
            (email, session['user_id'])
        ).fetchone()

        if existing_user:
            conn.close()
            return jsonify({'error': 'Email already exists'}), 409

        # Update user profile
        conn.execute(
            '''UPDATE users
               SET email = ?, full_name = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?''',
            (email, full_name, session['user_id'])
        )
        conn.commit()

        # Fetch updated user data
        user = conn.execute(
            '''SELECT id, username, email, full_name, created_at
               FROM users WHERE id = ?''',
            (session['user_id'],)
        ).fetchone()
        conn.close()

        logger.info(f"Profile updated: {user['username']} (ID: {user['id']})")
        return jsonify({
            'message': 'Profile updated successfully',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'full_name': user['full_name'],
                'created_at': user['created_at']
            }
        })

    except Exception as e:
        logger.error(f"Profile update error: {e}")
        return jsonify({'error': 'Failed to update profile'}), 500

@auth_bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    """Change user password."""
    try:
        data = request.get_json()
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')

        if not all([current_password, new_password, confirm_password]):
            return jsonify({'error': 'All password fields are required'}), 400

        if new_password != confirm_password:
            return jsonify({'error': 'New passwords do not match'}), 400

        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        conn = get_db_connection()

        # Verify current password
        user = conn.execute(
            'SELECT password_hash FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()

        if not user or not verify_password(current_password, user['password_hash']):
            conn.close()
            return jsonify({'error': 'Current password is incorrect'}), 401

        # Update password
        new_password_hash = hash_password(new_password)
        conn.execute(
            '''UPDATE users
               SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?''',
            (new_password_hash, session['user_id'])
        )
        conn.commit()
        conn.close()

        logger.info(f"Password changed: user_id={session['user_id']}")
        return jsonify({'message': 'Password changed successfully'})

    except Exception as e:
        logger.error(f"Password change error: {e}")
        return jsonify({'error': 'Failed to change password'}), 500

@auth_bp.route('/users', methods=['GET'])
@require_auth
def get_users():
    """Get all users (Admin only)."""
    try:
        # Check if current user is admin
        conn = get_db_connection()
        current_user = conn.execute(
            'SELECT username FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()

        if not current_user or current_user['username'] != 'admin':
            conn.close()
            logger.warning(f"Unauthorized user list access attempt by user_id={session['user_id']}")
            return jsonify({'error': 'Only admin can view user list'}), 403

        # Fetch all users
        users = conn.execute(
            '''SELECT id, username, email, full_name, created_at
               FROM users
               ORDER BY created_at DESC'''
        ).fetchall()
        conn.close()

        return jsonify({
            'users': [dict(user) for user in users]
        })

    except Exception as e:
        logger.error(f"User list fetch error: {e}")
        return jsonify({'error': 'Failed to fetch users'}), 500

@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@require_auth
def update_user(user_id):
    """Update user information (Admin only)."""
    try:
        # Check if current user is admin
        conn = get_db_connection()
        current_user = conn.execute(
            'SELECT username FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()

        if not current_user or current_user['username'] != 'admin':
            conn.close()
            logger.warning(f"Unauthorized user update attempt by user_id={session['user_id']}")
            return jsonify({'error': 'Only admin can update users'}), 403

        data = request.get_json()
        email = data.get('email', '').strip()
        full_name = data.get('full_name', '').strip()
        password = data.get('password', '').strip()

        if not email:
            conn.close()
            return jsonify({'error': 'Email is required'}), 400

        # Check if user exists
        user = conn.execute(
            'SELECT username FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()

        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        # Cannot update admin account
        if user['username'] == 'admin':
            conn.close()
            return jsonify({'error': 'Cannot update admin account'}), 403

        # Check if email is already taken by another user
        existing_user = conn.execute(
            'SELECT id FROM users WHERE email = ? AND id != ?',
            (email, user_id)
        ).fetchone()

        if existing_user:
            conn.close()
            return jsonify({'error': 'Email already exists'}), 409

        # Update user
        if password:
            password_hash = hash_password(password)
            conn.execute(
                '''UPDATE users
                   SET email = ?, full_name = ?, password_hash = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?''',
                (email, full_name, password_hash, user_id)
            )
        else:
            conn.execute(
                '''UPDATE users
                   SET email = ?, full_name = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?''',
                (email, full_name, user_id)
            )

        conn.commit()
        conn.close()

        logger.info(f"User updated by admin: user_id={user_id}")
        return jsonify({'message': 'User updated successfully'})

    except Exception as e:
        logger.error(f"User update error: {e}")
        return jsonify({'error': 'Failed to update user'}), 500

@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@require_auth
def delete_user(user_id):
    """Delete user (Admin only)."""
    try:
        # Check if current user is admin
        conn = get_db_connection()
        current_user = conn.execute(
            'SELECT username FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()

        if not current_user or current_user['username'] != 'admin':
            conn.close()
            logger.warning(f"Unauthorized user delete attempt by user_id={session['user_id']}")
            return jsonify({'error': 'Only admin can delete users'}), 403

        # Check if user exists
        user = conn.execute(
            'SELECT username FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()

        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        # Cannot delete admin account
        if user['username'] == 'admin':
            conn.close()
            return jsonify({'error': 'Cannot delete admin account'}), 403

        # Store username before deletion
        username = user['username']

        # Delete user from database
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()

        logger.info(f"User deleted from database: user_id={user_id}, username={username}")

        # Delete user directory
        user_dir = Path(SharedConfig.VIZR_PATH) / 'users' / username
        if user_dir.exists():
            try:
                shutil.rmtree(user_dir)
                logger.info(f"User directory deleted successfully: {user_dir}")
            except Exception as e:
                logger.error(f"Failed to delete user directory {user_dir}: {str(e)}", exc_info=True)
                # Continue even if directory deletion fails (can be cleaned up manually)
        else:
            logger.warning(f"User directory not found: {user_dir}")

        return jsonify({'message': 'User deleted successfully'})

    except Exception as e:
        logger.error(f"User delete error: {e}")
        return jsonify({'error': 'Failed to delete user'}), 500