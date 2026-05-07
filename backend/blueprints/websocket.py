"""
WebSocket 이벤트 핸들러
전역 구독 관리자를 사용한 효율적인 Redis 구독 관리
SSE fallback 없이 100% WebSocket으로만 구현
"""
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from flask import request
from backend.utils.subscription_manager import get_subscription_manager
import logging
import time

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def init_websocket(socketio: SocketIO) -> None:
    """WebSocket 이벤트 핸들러 초기화
    
    Args:
        socketio: Flask-SocketIO 인스턴스
    """
    
    # 전역 구독 관리자 획득
    subscription_manager = get_subscription_manager()
    
    @socketio.on('connect', namespace='/progress')
    def handle_connect():
        """클라이언트 연결 이벤트 처리"""
        client_id = request.sid
        logger.info(f"[WS-CONNECT] Client connected: {client_id}")
        
        # 연결 확인 메시지 전송
        emit('connected', {
            'status': 'connected', 
            'client_id': client_id,
            'timestamp': time.time()
        })
    
    @socketio.on('disconnect', namespace='/progress')  
    def handle_disconnect(auth=None):
        """클라이언트 연결 해제 이벤트 처리"""
        client_id = request.sid
        logger.info(f"[WS-DISCONNECT] Client disconnected: {client_id}")
        
        # 해당 클라이언트가 속한 모든 room에서 제거
        # Flask-SocketIO가 자동으로 room에서 제거하지만, 구독 관리자에도 알려야 함
        try:
            # 클라이언트가 속한 room들 가져오기
            rooms = socketio.server.manager.get_rooms(sid=client_id, namespace='/progress')
            
            for room in rooms:
                # 기본 개인 room(client_id와 같은)은 제외
                if room != client_id:
                    subscription_manager.remove_client_from_room(room, client_id)
                    logger.info(f"[WS-DISCONNECT] Removed {client_id} from room {room}")
                    
        except Exception as e:
            logger.error(f"[WS-DISCONNECT] Error cleaning up client {client_id}: {e}")
    
    @socketio.on('subscribe_progress', namespace='/progress')
    def handle_subscribe_progress(data):
        """진행상황 구독 요청 처리

        Args:
            data: {workbench_id: int, task_type: str}
        """
        client_id = request.sid

        logger.info(f"📥 [WS-SUBSCRIBE] Request from {client_id}: {data}")

        # 파라미터 검증
        workbench_id = data.get('workbench_id')
        task_type = data.get('task_type')

        if not workbench_id or not task_type:
            logger.warning(f"❌ [WS-SUBSCRIBE] Invalid parameters from {client_id}: {data}")
            emit('error', {
                'message': 'workbench_id and task_type are required',
                'timestamp': time.time()
            })
            return

        # Room 이름 생성 (wb_{workbench_id}_{task_type} 형식)
        room = f"wb_{workbench_id}_{task_type}"
        logger.info(f"🏠 [WS-SUBSCRIBE] Generated room name: {room}")

        try:
            # Flask-SocketIO room 참여
            join_room(room)
            logger.info(f"🚪 [WS-SUBSCRIBE] {client_id} joined Flask-SocketIO room {room}")

            # 구독 관리자에 클라이언트 추가 (필요시 Redis 구독 시작)
            subscription_manager.add_client_to_room(room, client_id, socketio)
            logger.info(f"📊 [WS-SUBSCRIBE] Added {client_id} to subscription manager for room {room}")

            # 구독 확인 메시지 전송
            response_data = {
                'room': room,
                'status': 'subscribed',
                'workbench_id': workbench_id,
                'task_type': task_type,
                'timestamp': time.time()
            }
            emit('subscribed', response_data)
            logger.info(f"✅ [WS-SUBSCRIBE] Sent subscribed confirmation to {client_id}: {response_data}")

        except Exception as e:
            logger.error(f"❌ [WS-SUBSCRIBE] Error subscribing {client_id} to {room}: {e}")
            emit('error', {
                'message': f'Failed to subscribe: {str(e)}',
                'timestamp': time.time()
            })
    
    @socketio.on('unsubscribe_progress', namespace='/progress')
    def handle_unsubscribe_progress(data):
        """진행상황 구독 해제 요청 처리 (선택적)
        
        Args:
            data: {workbench_id: int, task_type: str}
        """
        client_id = request.sid
        
        workbench_id = data.get('workbench_id')
        task_type = data.get('task_type')
        
        if not workbench_id or not task_type:
            emit('error', {
                'message': 'workbench_id and task_type are required',
                'timestamp': time.time()
            })
            return
        
        room = f"wb_{workbench_id}_{task_type}"
        
        try:
            # Flask-SocketIO room 떠나기
            leave_room(room)
            
            # 구독 관리자에서 클라이언트 제거
            subscription_manager.remove_client_from_room(room, client_id)
            
            logger.info(f"[WS-UNSUBSCRIBE] {client_id} left room {room}")
            
            # 구독 해제 확인 메시지 전송
            emit('unsubscribed', {
                'room': room,
                'status': 'unsubscribed',
                'timestamp': time.time()
            })
            
        except Exception as e:
            logger.error(f"[WS-UNSUBSCRIBE] Error unsubscribing {client_id} from {room}: {e}")
    
    @socketio.on('get_subscription_stats', namespace='/progress')
    def handle_get_stats():
        """구독 통계 조회 (디버그용)"""
        client_id = request.sid
        
        try:
            stats = subscription_manager.get_stats()
            emit('subscription_stats', {
                **stats,
                'timestamp': time.time()
            })
            logger.info(f"[WS-STATS] Stats requested by {client_id}")
            
        except Exception as e:
            logger.error(f"[WS-STATS] Error getting stats for {client_id}: {e}")
            emit('error', {
                'message': f'Failed to get stats: {str(e)}',
                'timestamp': time.time()
            })
    
    @socketio.on('ping', namespace='/progress')
    def handle_ping():
        """핑 요청 처리 (연결 상태 확인용)"""
        emit('pong', {
            'timestamp': time.time()
        })
    
    # 에러 핸들러
    @socketio.on_error(namespace='/progress')
    def error_handler(e):
        """WebSocket 에러 처리"""
        logger.error(f"[WS-ERROR] WebSocket error: {e}")
    
    logger.info("[WEBSOCKET] WebSocket handlers initialized")