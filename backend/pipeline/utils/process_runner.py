# process_runner.py
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed, Future
import multiprocessing as mp
import logging
import time
from typing import Callable, Iterable, Tuple, Any, List, Optional, Iterator

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

def worker_initializer():
    """워커 프로세스 초기화 함수 (독립 함수로 pickle 가능)"""
    # 자식 프로세스에서 한 번만 설정
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')
    logger.info(f"[POOL] worker initialized (pid={mp.current_process().pid})")

def worker_initializer_with_shared_lock(shared_lock):
    """공유 Lock과 함께 워커 프로세스를 초기화하는 함수 (pickle 가능)"""
    # 기본 로깅 초기화
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')

    logger.info(f"[POOL] worker initialized with shared lock (pid={mp.current_process().pid}, lock_id={id(shared_lock)})")

class ProcessPoolRunner:
    """
    공용 프로세스 풀 러너.
    - spawn 컨텍스트 고정 (OS 일관성)
    - Manager().Event() 기반 stop 전파
    - shutdown(cancel_futures=True)로 대기 작업 취소
    - 실행 중 작업은 워커 함수 내부(run_command의 stop_event 폴링)에서 외부 프로세스 그룹 종료
    사용 규약:
      - 워커 함수 시그니처: fn(*args, stop_event=None)  # stop_event 마지막 인자로 받게 권장
      - 워커 내부에서 모든 외부 커맨드는 ProcessWrapper.run_command(..., stop_event=stop_event)로 실행
    """
    def __init__(self, max_workers: int = 4, external_stop_event=None, shared_db_lock=None):
        self.max_workers = max_workers
        self.ctx: mp.context.BaseContext = mp.get_context("spawn")
        self.external_stop_event = external_stop_event  # ✅ 외부 Event 저장
        self.shared_db_lock = shared_db_lock  # ✅ 공유 DB Lock 저장
        self._executor: Optional[ProcessPoolExecutor] = None
        self._started: bool = False
        self._futures: List[Future] = []

    # ───── lifecycle ──────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._started:
            return

        # 공유 DB Lock이 있으면 Lock과 함께 초기화, 없으면 기본 초기화
        if self.shared_db_lock is not None:
            self._executor = ProcessPoolExecutor(
                max_workers=self.max_workers,
                initializer=worker_initializer_with_shared_lock,
                initargs=(self.shared_db_lock,),
                mp_context=self.ctx
            )
            logger.info(f"[POOL] started (spawn) max_workers={self.max_workers} with shared DB lock (lock_id={id(self.shared_db_lock)})")
        else:
            self._executor = ProcessPoolExecutor(
                max_workers=self.max_workers,
                initializer=worker_initializer,
                mp_context=self.ctx
            )
            logger.info(f"[POOL] started (spawn) max_workers={self.max_workers} without shared DB lock")

        self._started = True

    def close(self, wait: bool = True) -> None:
        if not self._started:
            return
        try:
            if self._executor is not None:
                # wait=True: 남은 작업이 있다면 정상 종료 대기(이미 stop을 쓴 경우 남아있지 않음)
                self._executor.shutdown(wait=wait, cancel_futures=False)
        except Exception as e:
            logger.warning(f"[POOL] close error: {e}")
        finally:
            self._executor = None
            self._started = False
            self._futures.clear()
            logger.info("[POOL] closed")

    def __enter__(self) -> "ProcessPoolRunner":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # 예외가 있었든 없든 안전 종료
        self.close(wait=True)

    # ───── submit / iterate ───────────────────────────────────────────────────
    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        """
        워커 함수에 stop_event 자동 주입.
        워커 시그니처: fn(..., stop_event=None) 형태 권장.
        """
        if not self._started:
            self.start()
        if "stop_event" not in kwargs and self.external_stop_event:
            kwargs["stop_event"] = self.external_stop_event
        if "shared_db_lock" not in kwargs and self.shared_db_lock:
            kwargs["shared_db_lock"] = self.shared_db_lock
        fut = self._executor.submit(fn, *args, **kwargs)  # type: ignore[arg-type]
        self._futures.append(fut)
        return fut

    def map_unordered(self, fn: Callable, arg_iter: Iterable[Tuple],
                      poll_interval: float = 0.2) -> Iterator[Any]:
        """
        as_completed 기반으로 결과를 완료 순서대로 yield.
        arg_iter의 각 튜플을 fn의 위치 인자로 전달.
        """
        futures: List[Future] = [self.submit(fn, *args) for args in arg_iter]
        for fut in as_completed(futures):
            yield fut.result()

    # ───── stop / cancel ──────────────────────────────────────────────────────
    def stop(self, grace: float = 0.2) -> None:
        """
        정지 시나리오:
          1) external_stop_event.set() → 워커가 즉시 감지, run_command에서 외부 커맨드 종료
          2) 짧은 유예(기본 200ms)
          3) executor.shutdown(wait=False, cancel_futures=True) → 대기 작업 취소
        """
        if not self._started:
            return
        try:
            if self.external_stop_event:
                logger.warning("[POOL] STOP requested -> set external_stop_event")
                self.external_stop_event.set()
            time.sleep(max(0.0, grace))
            if self._executor:
                self._executor.shutdown(wait=False, cancel_futures=True)
                logger.info("[POOL] executor.shutdown(wait=False, cancel_futures=True)")
        except Exception as e:
            logger.warning(f"[POOL] stop error: {e}")

    # 선택: 모든 미래를 기다리며 결과 수집(오류는 즉시 raise)
    def gather(self) -> List[Any]:
        results: List[Any] = []
        for fut in as_completed(self._futures):
            results.append(fut.result())
        return results
