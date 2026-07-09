/**
 * WebSocket Hook for VizR
 * SSE와 독립적으로 동작하며, 점진적 마이그레이션을 지원합니다.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';

// WebSocket 이벤트 타입 정의
interface ProgressData {
  srr_run?: string;
  metric?: string;
  value?: number;
  message?: string;
  timestamp?: number;
  [key: string]: any;
}

interface ConnectionState {
  isConnected: boolean;
  connectionId: string | null;
  lastError: string | null;
}

interface UseWebSocketOptions {
  workbenchId: number;
  taskType: string;
  enabled?: boolean;  // WebSocket 사용 여부 (SSE 폴백 지원)
  onProgressUpdate?: (data: ProgressData) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: string) => void;
}

/**
 * WebSocket 연결 관리 Hook
 * 1 Room = 1 Redis 구독 원칙에 따라 서버와 통신
 */
export const useWebSocket = ({
  workbenchId,
  taskType,
  enabled = true,
  onProgressUpdate,
  onConnect,
  onDisconnect,
  onError
}: UseWebSocketOptions) => {
  const socketRef = useRef<Socket | null>(null);
  const onProgressUpdateRef = useRef(onProgressUpdate);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onErrorRef = useRef(onError);
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    isConnected: false,
    connectionId: null,
    lastError: null
  });
  const [progressData, setProgressData] = useState<ProgressData[]>([]);

  useEffect(() => {
    onProgressUpdateRef.current = onProgressUpdate;
    onConnectRef.current = onConnect;
    onDisconnectRef.current = onDisconnect;
    onErrorRef.current = onError;
  }, [onProgressUpdate, onConnect, onDisconnect, onError]);

  // WebSocket 연결 초기화
  const initSocket = useCallback(() => {
    if (!enabled || socketRef.current?.connected) {
      return;
    }


    // 환경별 Socket URL 설정
    const SOCKET_URL = window.location.hostname === 'localhost'
      ? 'http://localhost:5001'
      : `http://${window.location.hostname}:5001`;

    // Socket.IO 클라이언트 생성 - namespace 포함
    const socket = io(`${SOCKET_URL}/progress`, {
      path: '/socket.io/',  // 명시적 path 지정
      transports: ['websocket'],  // WebSocket만 사용
      withCredentials: true,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 10000
    });

    // 연결 성공 이벤트
    socket.on('connect', () => {
      setConnectionState(prev => ({
        ...prev,
        isConnected: true,
        connectionId: socket.id || null,
        lastError: null
      }));
      onConnectRef.current?.();
    });

    // 서버로부터 연결 확인 메시지
    socket.on('connected', (data: any) => {
      // 자동으로 진행상황 구독
      const subscribeData = {
        workbench_id: workbenchId,
        task_type: taskType
      };

      socket.emit('subscribe_progress', subscribeData);
    });

    // 구독 확인 메시지
    socket.on('subscribed', (data: any) => {
    });

    // 진행상황 업데이트 수신 ⭐ 가장 중요한 부분
    socket.on('progress_update', (data: ProgressData) => {
      // 상태 업데이트
      setProgressData(prev => {
        const updated = [...prev, data];
        return updated;
      });

      // 콜백 실행
      if (onProgressUpdateRef.current) {
        onProgressUpdateRef.current(data);
      } else {
      }
    });

    // 연결 해제 이벤트
    socket.on('disconnect', (reason: string) => {
      setConnectionState(prev => ({
        ...prev,
        isConnected: false,
        connectionId: null
      }));
      onDisconnectRef.current?.();
    });

    // 에러 이벤트
    socket.on('error', (error: any) => {
      const errorMessage = error?.message || 'Unknown WebSocket error';
      setConnectionState(prev => ({
        ...prev,
        lastError: errorMessage
      }));
      onErrorRef.current?.(errorMessage);
    });

    // 재연결 시도 이벤트
    socket.on('reconnect_attempt', (attemptNumber: number) => {
    });

    // 재연결 성공
    socket.on('reconnect', (attemptNumber: number) => {
      // 재구독
      socket.emit('subscribe_progress', {
        workbench_id: workbenchId,
        task_type: taskType
      });
    });

    socketRef.current = socket;
  }, [enabled, workbenchId, taskType]);

  // 연결 해제 함수
  const disconnect = useCallback(() => {
    if (socketRef.current?.connected) {

      // 구독 해제 (옵션)
      socketRef.current.emit('unsubscribe_progress', {
        workbench_id: workbenchId,
        task_type: taskType
      });

      socketRef.current.disconnect();
      socketRef.current = null;
    }
  }, [workbenchId, taskType]);

  // 수동 재연결 함수
  const reconnect = useCallback(() => {
    disconnect();
    setTimeout(() => {
      initSocket();
    }, 100);
  }, [disconnect, initSocket]);

  // 진행상황 데이터 초기화
  const clearProgress = useCallback(() => {
    setProgressData([]);
  }, []);

  // Effect: WebSocket 라이프사이클 관리
  useEffect(() => {
    if (enabled) {
      initSocket();
    }

    // Cleanup
    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
      }
    };
  }, [enabled, workbenchId, taskType]); // 의존성 변경 시 재연결


  return {
    // 연결 상태
    isConnected: connectionState.isConnected,
    connectionId: connectionState.connectionId,
    lastError: connectionState.lastError,

    // 진행상황 데이터
    progressData,

    // 액션 함수
    disconnect,
    reconnect,
    clearProgress,

    // Socket 인스턴스 (고급 사용)
    socket: socketRef.current
  };
};

// 기본 export
export default useWebSocket;
