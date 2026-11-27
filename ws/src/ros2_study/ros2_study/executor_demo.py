"""05 Executor와 콜백 그룹: 느린 콜백 하나가 빠른 타이머를 얼마나 늦추는지 잰다.

fast 타이머(10 Hz)는 실제로 불린 간격을 기록하고, slow 타이머(1 Hz)는 일부러 slow_ms 동안 멈춘다.
mode 파라미터로 executor와 콜백 그룹 조합을 바꿔 가며 fast 타이머의 주기 오차를 비교한다.

  single          : SingleThreadedExecutor            → 스레드가 1개라 slow가 도는 동안 fast는 대기
  multi_exclusive : MultiThreadedExecutor + 기본 그룹  → 스레드는 여럿이지만 같은 MutuallyExclusive 그룹이라 대기
  multi_separate  : MultiThreadedExecutor + 그룹 분리  → fast와 slow가 다른 스레드에서 동시에 실행
  multi_reentrant : MultiThreadedExecutor + Reentrant 그룹 하나 → 그룹 안에서도 동시 실행 허용
"""
import statistics
import threading
import time

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node

FAST_PERIOD = 0.1  # 10 Hz
SLOW_PERIOD = 1.0  # 1 Hz
MODES = ('single', 'multi_exclusive', 'multi_separate', 'multi_reentrant')


class ExecutorDemo(Node):
    def __init__(self):
        super().__init__('executor_demo')
        self.mode = self.declare_parameter('mode', 'single').value
        self.slow_ms = self.declare_parameter('slow_ms', 300).value
        # busy=True면 sleep 대신 CPU를 계속 쓰는 계산을 한다 (Python GIL 영향 확인용)
        self.busy = self.declare_parameter('busy', False).value
        self.duration = self.declare_parameter('duration', 6.0).value
        if self.mode not in MODES:
            raise ValueError(f'mode는 {MODES} 중 하나여야 합니다: {self.mode}')

        # 콜백 그룹 고르기. 그룹을 안 주면 노드의 기본 그룹(MutuallyExclusive 하나)에 들어간다.
        # → 기본 상태에서는 이 노드의 모든 콜백이 "한 번에 하나만" 실행된다.
        if self.mode == 'multi_separate':
            fast_group = MutuallyExclusiveCallbackGroup()
            slow_group = MutuallyExclusiveCallbackGroup()  # 그룹이 다르면 서로 막지 않는다
        elif self.mode == 'multi_reentrant':
            fast_group = slow_group = ReentrantCallbackGroup()  # 같은 그룹이어도 동시 실행 허용
        else:
            fast_group = slow_group = None  # None = 기본 그룹

        self.intervals = []  # fast 타이머가 실제로 불린 간격(초)
        self.last = None
        # 어떤 스레드가 콜백을 실행했는지 (멀티스레드인지 눈으로 확인).
        # fast/slow가 동시에 add 할 수 있지만 set.add 한 번은 CPython에서 원자적이라 괜찮다.
        # count += 1 같은 "읽고-고치고-쓰기"였다면 threading.Lock이 필요하다.
        self.threads = set()
        self.create_timer(FAST_PERIOD, self.on_fast, callback_group=fast_group)
        self.create_timer(SLOW_PERIOD, self.on_slow, callback_group=slow_group)

    def on_fast(self):
        # 벽시계(time.time)는 NTP 보정으로 뒤로 갈 수도 있으므로 간격 측정에는 monotonic 시계를 쓴다.
        now = time.monotonic()
        if self.last is not None:
            self.intervals.append(now - self.last)
        self.last = now
        self.threads.add(threading.current_thread().name)

    def on_slow(self):
        self.threads.add(threading.current_thread().name)
        if self.busy:
            # CPU를 붙잡고 도는 순수 Python 루프: 이 동안 GIL을 거의 놓지 않는다.
            end = time.monotonic() + self.slow_ms / 1000
            while time.monotonic() < end:
                pass
        else:
            # time.sleep은 기다리는 동안 GIL을 놓는다 (I/O 대기, 블로킹 서비스 호출과 비슷).
            time.sleep(self.slow_ms / 1000)

    def report(self):
        if not self.intervals:
            print('fast 타이머가 한 번도 두 번 이상 불리지 않았습니다.')
            return
        devs_ms = [(i - FAST_PERIOD) * 1000 for i in self.intervals]
        late = sum(d > FAST_PERIOD * 1000 / 2 for d in devs_ms)  # 반 주기(50 ms) 넘게 늦은 틱
        print(f'mode={self.mode} slow_ms={self.slow_ms} busy={self.busy} threads={sorted(self.threads)}')
        print(f'  fast ticks={len(self.intervals) + 1} (이상적이면 {int(self.duration / FAST_PERIOD)})')
        print(f'  period ms: mean={statistics.mean(self.intervals) * 1000:.1f} '
              f'min={min(self.intervals) * 1000:.1f} max={max(self.intervals) * 1000:.1f}')
        print(f'  deviation ms: mean|dev|={statistics.mean(abs(d) for d in devs_ms):.1f} '
              f'max={max(devs_ms):.1f} | 50ms 넘게 늦은 틱={late}')


def main():
    rclpy.init()
    node = ExecutorDemo()
    # Executor 고르기. 노드는 "콜백 목록"일 뿐이고, 실제로 콜백을 꺼내 실행하는 것은 executor다.
    if node.mode == 'single':
        executor = SingleThreadedExecutor()
    else:
        executor = MultiThreadedExecutor(num_threads=4)  # 생략하면 CPU 코어 수만큼 만든다
    executor.add_node(node)
    try:
        # spin()은 "spin_once()를 끝없이 반복"하는 것. 여기서는 duration 초만 돌고 멈추려고 직접 반복한다.
        # spin_once: 실행 준비된 콜백을 하나 골라 실행(멀티스레드면 스레드 풀에 넘김)하고 돌아온다.
        end = time.monotonic() + node.duration
        while rclpy.ok() and time.monotonic() < end:
            executor.spin_once(timeout_sec=0.1)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # 멀티스레드 executor는 스레드 풀에서 아직 돌고 있는 콜백을 기다려 주지 않는다(Jazzy rclpy).
        # 바로 종료하면 그 콜백이 끝나면서 이미 정리된 executor 내부 객체를 건드려 경고가 찍히므로,
        # 가장 긴 콜백(slow)이 끝날 만큼 잠깐 기다린다. spin을 멈췄으니 새 콜백은 시작되지 않는다.
        time.sleep(node.slow_ms / 1000 + 0.1)
        executor.shutdown()
        node.report()  # 콜백 스레드가 모두 끝난 뒤 읽으므로 경합(race)이 없다
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
