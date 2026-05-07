"""
VizR Workbench Share Blueprint
워크벤치 공유 기능 전용 API 엔드포인트
"""
from flask import Blueprint, request, jsonify
import json
import logging

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
workbench_share_bp = Blueprint('workbench_share', __name__, url_prefix='/api/workbenches')

# Import database and auth utilities
from backend.utils.database import get_db_connection_simple as get_db_connection
from backend.utils.auth import require_auth, get_current_user_id


def check_workbench_owner(workbench_id: int, user_id: int) -> bool:
    """
    워크벤치 소유자인지 확인하는 헬퍼 함수

    Args:
        workbench_id: 워크벤치 ID
        user_id: 사용자 ID

    Returns:
        bool: 소유자이면 True, 아니면 False
    """
    with get_db_connection() as conn:
        workbench = conn.execute(
            'SELECT user_id FROM vizr_workbench WHERE id = ?',
            (workbench_id,)
        ).fetchone()

        if not workbench:
            return False

        return workbench['user_id'] == user_id


def check_workbench_access(workbench_id: int, user_id: int) -> tuple[bool, str]:
    """
    워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)

    Args:
        workbench_id: 워크벤치 ID
        user_id: 사용자 ID

    Returns:
        tuple: (접근 가능 여부, 권한 타입: 'owner' | 'shared' | None)
    """
    with get_db_connection() as conn:
        workbench = conn.execute(
            'SELECT user_id, shared_users FROM vizr_workbench WHERE id = ?',
            (workbench_id,)
        ).fetchone()

        if not workbench:
            return False, None

        # 소유자 확인
        if workbench['user_id'] == user_id:
            return True, 'owner'

        # 공유 사용자 확인
        shared_users_json = workbench['shared_users'] or '[]'
        try:
            shared_users = json.loads(shared_users_json)
            if user_id in shared_users:
                return True, 'shared'
        except json.JSONDecodeError:
            logger.error(f"❌ [WORKBENCH-ACCESS] Invalid JSON in shared_users for workbench {workbench_id}")
            return False, None

        return False, None


@workbench_share_bp.route('/<int:workbench_id>/available-users', methods=['GET'])
@require_auth
def get_available_users(workbench_id):
    """
    공유 가능한 사용자 목록 조회
    - 본인(소유자) 제외
    - 이미 공유된 사용자 제외
    - admin 계정 제외 (선택사항)
    """
    try:
        user_id = get_current_user_id()
        logger.info(f"📋 [AVAILABLE-USERS] User {user_id} requesting available users for workbench {workbench_id}")

        # 소유자 권한 확인
        if not check_workbench_owner(workbench_id, user_id):
            logger.warning(f"⚠️ [AVAILABLE-USERS] User {user_id} is not the owner of workbench {workbench_id}")
            return jsonify({'error': 'Only the workbench owner can view available users'}), 403

        with get_db_connection() as conn:
            # 현재 공유된 사용자 목록 가져오기
            workbench = conn.execute(
                'SELECT shared_users FROM vizr_workbench WHERE id = ?',
                (workbench_id,)
            ).fetchone()

            if not workbench:
                return jsonify({'error': 'Workbench not found'}), 404

            shared_users_json = workbench['shared_users'] or '[]'
            try:
                shared_user_ids = json.loads(shared_users_json)
            except json.JSONDecodeError:
                logger.error(f"❌ [AVAILABLE-USERS] Invalid JSON in shared_users")
                shared_user_ids = []

            # 공유 가능한 사용자 조회 (본인, 이미 공유된 사용자, admin 제외)
            excluded_ids = [user_id] + shared_user_ids
            placeholders = ','.join('?' * len(excluded_ids))

            available_users = conn.execute(f'''
                SELECT id, username, email, full_name
                FROM users
                WHERE id NOT IN ({placeholders})
                  AND username != 'admin'
                ORDER BY username ASC
            ''', excluded_ids).fetchall()

            users_list = [dict(user) for user in available_users]

            logger.info(f"✅ [AVAILABLE-USERS] Found {len(users_list)} available users for workbench {workbench_id}")
            return jsonify({'users': users_list})

    except Exception as e:
        logger.error(f"💥 [AVAILABLE-USERS] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to fetch available users'}), 500


@workbench_share_bp.route('/<int:workbench_id>/shared-users', methods=['GET'])
@require_auth
def get_shared_users(workbench_id):
    """
    현재 공유된 사용자 목록 조회
    """
    try:
        user_id = get_current_user_id()
        logger.info(f"📋 [SHARED-USERS] User {user_id} requesting shared users for workbench {workbench_id}")

        # 워크벤치 접근 권한 확인 (소유자 또는 공유 사용자)
        has_access, permission = check_workbench_access(workbench_id, user_id)
        if not has_access:
            logger.warning(f"⚠️ [SHARED-USERS] User {user_id} has no access to workbench {workbench_id}")
            return jsonify({'error': 'Access denied'}), 403

        with get_db_connection() as conn:
            workbench = conn.execute(
                'SELECT shared_users FROM vizr_workbench WHERE id = ?',
                (workbench_id,)
            ).fetchone()

            if not workbench:
                return jsonify({'error': 'Workbench not found'}), 404

            shared_users_json = workbench['shared_users'] or '[]'
            try:
                shared_user_ids = json.loads(shared_users_json)
            except json.JSONDecodeError:
                logger.error(f"❌ [SHARED-USERS] Invalid JSON in shared_users")
                shared_user_ids = []

            if not shared_user_ids:
                return jsonify({'shared_users': []})

            # 공유된 사용자 정보 조회
            placeholders = ','.join('?' * len(shared_user_ids))
            shared_users = conn.execute(f'''
                SELECT id, username, email, full_name
                FROM users
                WHERE id IN ({placeholders})
                ORDER BY username ASC
            ''', shared_user_ids).fetchall()

            users_list = [dict(user) for user in shared_users]

            logger.info(f"✅ [SHARED-USERS] Found {len(users_list)} shared users for workbench {workbench_id}")
            return jsonify({'shared_users': users_list})

    except Exception as e:
        logger.error(f"💥 [SHARED-USERS] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to fetch shared users'}), 500


@workbench_share_bp.route('/<int:workbench_id>/share', methods=['POST'])
@require_auth
def share_workbench(workbench_id):
    """
    워크벤치 공유 추가
    Body: {"user_ids": [2, 5, 7]}
    """
    try:
        user_id = get_current_user_id()
        data = request.get_json()

        # 요청 데이터 검증
        if not data or 'user_ids' not in data:
            return jsonify({'error': 'user_ids is required'}), 400

        new_user_ids = data['user_ids']
        if not isinstance(new_user_ids, list) or not new_user_ids:
            return jsonify({'error': 'user_ids must be a non-empty array'}), 400

        logger.info(f"🔗 [SHARE-WORKBENCH] User {user_id} sharing workbench {workbench_id} with users {new_user_ids}")

        # 소유자 권한 확인
        if not check_workbench_owner(workbench_id, user_id):
            logger.warning(f"⚠️ [SHARE-WORKBENCH] User {user_id} is not the owner of workbench {workbench_id}")
            return jsonify({'error': 'Only the workbench owner can share the workbench'}), 403

        with get_db_connection() as conn:
            # 공유하려는 사용자들이 실제로 존재하는지 확인
            placeholders = ','.join('?' * len(new_user_ids))
            existing_users = conn.execute(f'''
                SELECT id FROM users WHERE id IN ({placeholders})
            ''', new_user_ids).fetchall()

            existing_user_ids = [user['id'] for user in existing_users]
            invalid_user_ids = [uid for uid in new_user_ids if uid not in existing_user_ids]

            if invalid_user_ids:
                logger.warning(f"⚠️ [SHARE-WORKBENCH] Invalid user IDs: {invalid_user_ids}")
                return jsonify({'error': f'Invalid user IDs: {invalid_user_ids}'}), 400

            # 기존 공유 목록 가져오기
            workbench = conn.execute(
                'SELECT shared_users FROM vizr_workbench WHERE id = ?',
                (workbench_id,)
            ).fetchone()

            if not workbench:
                return jsonify({'error': 'Workbench not found'}), 404

            shared_users_json = workbench['shared_users'] or '[]'
            try:
                current_shared_users = json.loads(shared_users_json)
            except json.JSONDecodeError:
                logger.error(f"❌ [SHARE-WORKBENCH] Invalid JSON in shared_users")
                current_shared_users = []

            # 새로운 사용자 추가 (중복 제거)
            updated_shared_users = list(set(current_shared_users + new_user_ids))
            updated_json = json.dumps(updated_shared_users)

            # DB 업데이트
            conn.execute('''
                UPDATE vizr_workbench
                SET shared_users = ?
                WHERE id = ?
            ''', (updated_json, workbench_id))
            conn.commit()

            logger.info(f"✅ [SHARE-WORKBENCH] Successfully shared workbench {workbench_id} with {len(new_user_ids)} users")
            logger.info(f"📊 [SHARE-WORKBENCH] Total shared users: {len(updated_shared_users)}")

            return jsonify({
                'message': 'Workbench shared successfully',
                'shared_user_ids': updated_shared_users
            })

    except Exception as e:
        logger.error(f"💥 [SHARE-WORKBENCH] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to share workbench'}), 500


@workbench_share_bp.route('/<int:workbench_id>/share/<int:target_user_id>', methods=['DELETE'])
@require_auth
def unshare_workbench(workbench_id, target_user_id):
    """
    워크벤치 공유 제거
    - 소유자: 다른 사용자를 공유 목록에서 제거 가능
    - 공유 대상자: 자기 자신만 공유 목록에서 제거 가능
    """
    try:
        user_id = get_current_user_id()
        logger.info(f"🔓 [UNSHARE-WORKBENCH] User {user_id} removing user {target_user_id} from workbench {workbench_id}")

        # 권한 확인: 소유자이거나 자기 자신을 제거하는 경우
        is_owner = check_workbench_owner(workbench_id, user_id)
        is_removing_self = (user_id == target_user_id)

        if not is_owner and not is_removing_self:
            logger.warning(f"⚠️ [UNSHARE-WORKBENCH] User {user_id} has no permission to remove user {target_user_id}")
            return jsonify({'error': 'You can only remove yourself from shared workbenches'}), 403

        with get_db_connection() as conn:
            # 기존 공유 목록 가져오기
            workbench = conn.execute(
                'SELECT shared_users FROM vizr_workbench WHERE id = ?',
                (workbench_id,)
            ).fetchone()

            if not workbench:
                return jsonify({'error': 'Workbench not found'}), 404

            shared_users_json = workbench['shared_users'] or '[]'
            try:
                current_shared_users = json.loads(shared_users_json)
            except json.JSONDecodeError:
                logger.error(f"❌ [UNSHARE-WORKBENCH] Invalid JSON in shared_users")
                current_shared_users = []

            # 대상 사용자 제거
            if target_user_id not in current_shared_users:
                logger.warning(f"⚠️ [UNSHARE-WORKBENCH] User {target_user_id} is not in shared list")
                return jsonify({'error': 'User is not in the shared list'}), 400

            updated_shared_users = [uid for uid in current_shared_users if uid != target_user_id]
            updated_json = json.dumps(updated_shared_users)

            # DB 업데이트
            conn.execute('''
                UPDATE vizr_workbench
                SET shared_users = ?
                WHERE id = ?
            ''', (updated_json, workbench_id))
            conn.commit()

            # 로그 메시지 구분
            if is_removing_self:
                logger.info(f"✅ [UNSHARE-WORKBENCH] User {user_id} left shared workbench {workbench_id}")
                message = 'You have been removed from the shared workbench'
            else:
                logger.info(f"✅ [UNSHARE-WORKBENCH] Owner removed user {target_user_id} from workbench {workbench_id}")
                message = 'User removed from shared list successfully'

            logger.info(f"📊 [UNSHARE-WORKBENCH] Remaining shared users: {len(updated_shared_users)}")

            return jsonify({
                'message': message,
                'shared_user_ids': updated_shared_users
            })

    except Exception as e:
        logger.error(f"💥 [UNSHARE-WORKBENCH] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to unshare workbench'}), 500
