"""
Redis 기반 메시지 브로커
멀티프로세스 간 SSE 메시지 전달을 위한 Redis 브로커
"""
import os
import json
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

class RedisBroker:
    """Redis 기반 메시지 브로커"""
    
    def __init__(self):
        """Redis 브로커 초기화"""
        self.redis_client = None
        self.use_redis = os.getenv('USE_REDIS', 'false').lower() == 'true'
        
        if self.use_redis:
            try:
                import redis
                self.redis_client = redis.Redis(
                    host=os.getenv('REDIS_HOST', 'localhost'),
                    port=int(os.getenv('REDIS_PORT', 6379)),
                    db=int(os.getenv('REDIS_DB', 0)),
                    decode_responses=True
                )
                # 연결 테스트
                self.redis_client.ping()
                logger.info("✅ Redis 브로커 연결 성공")
            except Exception as e:
                logger.error(f"❌ Redis 연결 실패: {e}")
                self.use_redis = False
                self.redis_client = None

        # Unified logging system already set up

    
    def is_available(self) -> bool:
        """Redis 사용 가능 여부"""
        return self.use_redis and self.redis_client is not None
    
    def publish_progress(self, 
                        workbench_id: int,
                        task_type: str,
                        progress_data: Dict[str, Any]) -> bool:
        """
        진행률 메시지 발행
        
        Args:
            workbench_id: 워크벤치 ID
            task_type: 작업 유형 (data_download, qc, alignment 등)
            progress_data: 진행률 데이터
        
        Returns:
            발행 성공 여부
        """
        if not self.is_available():
            return False
        
        try:
            # 채널 이름
            channel = f"vizr:progress:{workbench_id}:{task_type}"

            # 구독자 수 미리 확인 (Redis 트래픽 최적화)
            subscriber_count = self.redis_client.pubsub_numsub(channel)[0][1]

            if subscriber_count == 0:
                return False

            # 메시지 구성
            message = {
                "event": "progress_update",
                "workbench_id": workbench_id,
                "task_type": task_type,
                "data": progress_data,
                "timestamp": time.time()
            }


            # Redis 발행 (구독자가 있을 때만)
            message_json = json.dumps(message)
            subscribers = self.redis_client.publish(channel, message_json)

            # 리스트에도 저장 (최근 100개 유지)
            list_key = f"vizr:progress:history:{workbench_id}:{task_type}"
            self.redis_client.lpush(list_key, message_json)
            self.redis_client.ltrim(list_key, 0, 99)
            self.redis_client.expire(list_key, 3600)  # 1시간 후 만료

            return True
            
        except Exception as e:
            logger.error(f"Redis 발행 실패: {e}")
            return False
    
    def get_recent_progress(self, 
                           workbench_id: int,
                           task_type: str,
                           limit: int = 10) -> List[Dict[str, Any]]:
        """
        최근 진행률 메시지 조회
        
        Args:
            workbench_id: 워크벤치 ID
            task_type: 작업 유형
            limit: 조회할 메시지 수
        
        Returns:
            최근 메시지 리스트
        """
        if not self.is_available():
            return []
        
        try:
            list_key = f"vizr:progress:history:{workbench_id}:{task_type}"
            messages = self.redis_client.lrange(list_key, 0, limit - 1)
            return [json.loads(msg) for msg in messages]
            
        except Exception as e:
            logger.error(f"Redis 조회 실패: {e}")
            return []
    
    def subscribe_progress(self, workbench_id: int, task_type: str):
        """
        진행률 채널 구독 (Generator)
        
        Args:
            workbench_id: 워크벤치 ID
            task_type: 작업 유형
        
        Yields:
            진행률 메시지
        """
        if not self.is_available():
            return
        
        pubsub = None
        channel = f"vizr:progress:{workbench_id}:{task_type}"
        
        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe(channel)
            
            message_count = 0

            # 구독 메시지 루프
            for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        message_count += 1
                        data = json.loads(message['data'])
                        yield data
                    except json.JSONDecodeError as e:
                        continue
                elif message['type'] == 'subscribe':
                    pass
                elif message['type'] == 'unsubscribe':
                    break
                    
        except GeneratorExit:
            # 클라이언트가 정상적으로 연결을 끊었을 때
            pass
        except ConnectionError as e:
            # Redis 연결 오류
            pass
        except Exception as e:
            # 기타 예외
            pass
        finally:
            # 정리 작업
            if pubsub:
                try:
                    pubsub.unsubscribe()
                    pubsub.close()
                except Exception as cleanup_error:
                    pass
            else:
                pass
    
    def cleanup_old_messages(self, older_than_seconds: int = 3600):
        """
        오래된 메시지 정리
        
        Args:
            older_than_seconds: 이 시간보다 오래된 메시지 삭제
        """
        if not self.is_available():
            return
        
        try:
            # 패턴 매칭으로 모든 progress 키 찾기
            pattern = "vizr:progress:history:*"
            cursor = 0
            
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor, match=pattern, count=100
                )
                
                for key in keys:
                    # TTL 재설정 (자동 정리)
                    ttl = self.redis_client.ttl(key)
                    if ttl == -1:  # TTL이 설정되지 않은 경우
                        self.redis_client.expire(key, older_than_seconds)
                
                if cursor == 0:
                    break
                    
            
        except Exception as e:
            logger.error(f"Redis 정리 실패: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Redis 상태 정보 조회
        
        Returns:
            상태 정보 딕셔너리
        """
        if not self.is_available():
            return {"available": False}
        
        try:
            info = self.redis_client.info()
            memory_info = self.redis_client.info('memory')
            
            return {
                "available": True,
                "version": info.get('redis_version', 'unknown'),
                "connected_clients": info.get('connected_clients', 0),
                "used_memory_human": memory_info.get('used_memory_human', 'unknown'),
                "uptime_in_seconds": info.get('uptime_in_seconds', 0)
            }
            
        except Exception as e:
            logger.error(f"Redis 상태 조회 실패: {e}")
            return {"available": False, "error": str(e)}


# 싱글톤 인스턴스
_redis_broker = None

def get_redis_broker() -> RedisBroker:
    """Redis 브로커 싱글톤 인스턴스 반환"""
    global _redis_broker
    if _redis_broker is None:
        _redis_broker = RedisBroker()
    return _redis_broker
