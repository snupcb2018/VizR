"""
Client-side debug log receiver.
"""
import json
import logging
from flask import Blueprint, jsonify, request, session

from backend.blueprints.auth import require_auth
from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'DEBUG')

client_logs_bp = Blueprint('client_logs', __name__, url_prefix='/api/client-logs')


def _truncate(value, limit=6000):
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)

    if len(text) > limit:
        return text[:limit] + f"... [truncated {len(text) - limit} chars]"
    return text


@client_logs_bp.route('', methods=['POST'])
@require_auth
def receive_client_log():
    data = request.get_json(silent=True) or {}

    level = str(data.get('level', 'info')).lower()
    source = str(data.get('source', 'client'))
    event = str(data.get('event', 'unknown'))
    payload = data.get('payload', {})
    user_id = session.get('user_id')

    message = (
        f"[CLIENT-LOG] source={source} event={event} user_id={user_id} "
        f"payload={_truncate(payload)}"
    )

    log_level = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warn': logging.WARNING,
        'warning': logging.WARNING,
        'error': logging.ERROR,
    }.get(level, logging.INFO)

    logger.log(log_level, message)
    return jsonify({'success': True})
