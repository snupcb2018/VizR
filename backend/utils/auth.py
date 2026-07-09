"""
VizR Authentication Utilities
"""
import hashlib
import logging
from functools import wraps
from flask import session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

def hash_password(password: str) -> str:
    """Hash password using werkzeug's secure method."""
    return generate_password_hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    return check_password_hash(password_hash, password)

def require_auth(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return wrapper

def get_current_user_id() -> int:
    """Get current authenticated user ID from session."""
    return session.get('user_id')

def get_current_username() -> str:
    """Get current authenticated username from session."""
    return session.get('username', 'Unknown')

def create_user_session(user_id: int, username: str) -> None:
    """Create user session after successful authentication."""
    session['user_id'] = user_id
    session['username'] = username
    logger.info(f"Session created for user: {username} (ID: {user_id})")

def clear_user_session() -> None:
    """Clear user session on logout."""
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f"Session cleared for user: {username}")