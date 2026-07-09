"""
VizR API Blueprint - Health Check and General API Routes
"""
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'version': '1.0.0'
    })