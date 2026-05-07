"""
전역 Redis 구독 관리자
Room별로 하나의 Redis 구독만 유지하는 시스템
1 Room = 1 Redis 구독 원칙을 보장
"""
import threading
import logging
from typing import Dict, Set, Optional
from backend.pipeline.utils.redis_broker import get_redis_broker

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class SubscriptionManager:
    """Redis 구독을 Room별로 관리하는 전역 관리자
    
    핵심 보장사항:
    - 1 Room = 1 Redis 구독: 클라이언트 수와 무관하게 구독 수 일정
    - 동적 관리: 필요할 때만 생성, 불필요하면 즉시 해제
    - 스레드 안전성: Lock을 통한 동시 접속/해제 안전 처리
    - 메모리 효율성: 클라이언트 0명 시 즉시 리소스 정리
    """
    
    def __init__(self):
        self._active_subscriptions: Dict[str, threading.Thread] = {}
        self._room_clients: Dict[str, Set[str]] = {}  # room -> client_ids
        self._lock = threading.Lock()
        self._stop_events: Dict[str, threading.Event] = {}  # room -> stop_event
    
    def add_client_to_room(self, room: str, client_id: str, socketio) -> None:
        """클라이언트를 room에 추가하고 필요시 Redis 구독 시작
        
        Args:
            room: Room 이름 (예: wb_1_ncbi_download)
            client_id: 클라이언트 세션 ID
            socketio: Flask-SocketIO 인스턴스
        """
        with self._lock:
            # Room에 클라이언트 추가
            if room not in self._room_clients:
                self._room_clients[room] = set()
            
            self._room_clients[room].add(client_id)
            
            # 첫 번째 클라이언트인 경우 Redis 구독 시작
            if len(self._room_clients[room]) == 1:
                self._start_redis_subscription(room, socketio)
    
    def remove_client_from_room(self, room: str, client_id: str) -> None:
        """클라이언트를 room에서 제거하고 필요시 Redis 구독 중지
        
        Args:
            room: Room 이름
            client_id: 클라이언트 세션 ID
        """
        with self._lock:
            if room not in self._room_clients:
                return
                
            self._room_clients[room].discard(client_id)
            
            # 마지막 클라이언트가 나간 경우 Redis 구독 중지
            if len(self._room_clients[room]) == 0:
                self._stop_redis_subscription(room)
                del self._room_clients[room]
    
    def _start_redis_subscription(self, room: str, socketio) -> None:
        """특정 room에 대한 Redis 구독 시작 (내부 메서드)
        
        Args:
            room: Room 이름
            socketio: Flask-SocketIO 인스턴스
        """
        # room에서 workbench_id, task_type 추출
        parts = room.split('_')
        if len(parts) < 3:
            logger.error(f"[SUB-MGR] Invalid room format: {room}")
            return
            
        try:
            workbench_id = int(parts[1])
            task_type = '_'.join(parts[2:])
        except (ValueError, IndexError) as e:
            logger.error(f"[SUB-MGR] Failed to parse room {room}: {e}")
            return
        
        # Stop event 생성 (스레드 종료용)
        stop_event = threading.Event()
        self._stop_events[room] = stop_event
        
        def redis_to_websocket():
            """Redis 메시지를 WebSocket으로 중계하는 워커 스레드"""
            redis_broker = get_redis_broker()
            try:
                # Redis 구독 시작
                message_count = 0

                for message in redis_broker.subscribe_progress(workbench_id, task_type):
                    # 종료 시그널 체크
                    if stop_event.is_set():
                        break

                    message_count += 1

                    # 해당 room의 모든 클라이언트에게 브로드캐스트
                    with self._lock:
                        client_count = len(self._room_clients.get(room, set()))
                        client_list = list(self._room_clients.get(room, set()))

                    if client_count > 0:
                        socketio.emit('progress_update', message, room=room, namespace='/progress')
                    else:
                        pass
                    
            except Exception as e:
                logger.error(f"[SUB-MGR] Redis subscription error for {room}: {e}")
            finally:
                pass
        
        # 백그라운드 스레드로 구독 시작
        thread = threading.Thread(
            target=redis_to_websocket,
            name=f"Redis-WS-{room}",
            daemon=True
        )
        thread.start()
        self._active_subscriptions[room] = thread
    
    def _stop_redis_subscription(self, room: str) -> None:
        """특정 room에 대한 Redis 구독 중지 (내부 메서드)
        
        Args:
            room: Room 이름
        """
        if room in self._active_subscriptions:
            # Stop event 설정하여 스레드 종료 시그널
            if room in self._stop_events:
                self._stop_events[room].set()
                del self._stop_events[room]
            
            # 스레드 참조 제거 (daemon thread이므로 자동 정리됨)
            del self._active_subscriptions[room]
    
    def get_stats(self) -> Dict:
        """현재 구독 상태 통계 반환
        
        Returns:
            구독 상태 정보를 담은 딕셔너리
        """
        with self._lock:
            return {
                'active_rooms': len(self._room_clients),
                'total_clients': sum(len(clients) for clients in self._room_clients.values()),
                'active_subscriptions': len(self._active_subscriptions),
                'rooms_detail': {
                    room: {
                        'client_count': len(clients),
                        'clients': list(clients)
                    } 
                    for room, clients in self._room_clients.items()
                }
            }
    
    def cleanup(self) -> None:
        """모든 구독 정리 (서버 종료시 호출)"""
        with self._lock:
            # 모든 stop event 설정
            for stop_event in self._stop_events.values():
                stop_event.set()
            
            # 정리
            self._stop_events.clear()
            self._active_subscriptions.clear()
            self._room_clients.clear()


# 전역 싱글톤 인스턴스
_subscription_manager: Optional[SubscriptionManager] = None


def get_subscription_manager() -> SubscriptionManager:
    """구독 관리자 싱글톤 인스턴스 반환
    
    Returns:
        SubscriptionManager 인스턴스
    """
    global _subscription_manager
    if _subscription_manager is None:
        _subscription_manager = SubscriptionManager()
    return _subscription_manager