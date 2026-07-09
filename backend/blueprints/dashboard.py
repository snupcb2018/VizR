"""
VizR Dashboard Blueprint
"""
from flask import Blueprint, jsonify, session
import logging
import sqlite3

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')

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

@dashboard_bp.route('/stats', methods=['GET'])
@require_auth
def get_dashboard_stats():
    """Get dashboard statistics."""
    try:
        conn = get_db_connection()
        user_id = session['user_id']

        # Get workbench counts by status
        stats = conn.execute('''
            SELECT 
                COUNT(*) as total_workbenches,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as active_workbenches,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_workbenches,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_workbenches,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_workbenches
            FROM vizr_workbench 
            WHERE user_id = ?
        ''', (user_id,)).fetchone()

        conn.close()

        return jsonify({
            'stats': {
                'total_workbenches': stats['total_workbenches'] or 0,
                'active_workbenches': stats['active_workbenches'] or 0,
                'completed_workbenches': stats['completed_workbenches'] or 0,
                'failed_workbenches': stats['failed_workbenches'] or 0,
                'pending_workbenches': stats['pending_workbenches'] or 0
            }
        })

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return jsonify({'error': 'Failed to fetch dashboard stats'}), 500

@dashboard_bp.route('/recent-workbenches', methods=['GET'])
@require_auth
def get_recent_workbenches():
    """Get recent workbenches for dashboard."""
    try:
        conn = get_db_connection()
        user_id = session['user_id']

        workbenches = conn.execute('''
            SELECT id, name, status, updated_at
            FROM vizr_workbench 
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT 5
        ''', (user_id,)).fetchall()

        conn.close()

        return jsonify({
            'workbenches': [dict(wb) for wb in workbenches]
        })

    except Exception as e:
        logger.error(f"Recent workbenches error: {e}")
        return jsonify({'error': 'Failed to fetch recent workbenches'}), 500