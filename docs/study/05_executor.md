# 05. Executor와 콜백 그룹

> 핵심 질문: 콜백 하나가 느리면 왜 다른 콜백도 늦어지나?

## 1. 이 장의 목표

- executor가 "준비된 콜백을 골라 실행하는 루프"라는 것을 이해하고, `spin()` / `spin_once()`의 차이를 설명할 수 있다.
- `SingleThreadedExecutor` / `MultiThreadedExecutor`와 콜백 그룹(MutuallyExclusive, Reentrant)의 조합에 따라 빠른 타이머가 **얼마나 늦어지는지 직접 측정**한다.
- 멀티스레드로 바꿀 때 따라오는 스레드 안전성 문제와 Python GIL의 한계를 알고, 이것이 06장의 지연(⑤⑥ 단계)과 어떻게 연결되는지 설명할 수 있다.

## 2. 핵심 개념

### Executor = 콜백 실행 루프

노드는 "타이머, 구독, 서비스 같은 콜백의 목록"일 뿐이고, 스스로 아무것도 실행하지 않습니다. 실제로 일을 하는 것은 **executor**입니다.

```
           ┌──────────────── executor ────────────────┐
 타이머 ──▶ │ ① wait set에서 "준비된 것"을 기다린다      │
 구독   ──▶ │ ② 준비된 콜백 중 실행 가능한 것을 하나 고른다 │──▶ 콜백 실행
 서비스 ──▶ │ ③ 실행한다 (싱글: 그 자리에서 / 멀티: 스레드 풀) │
           │ ④ ①로 돌아간다                            │
           └──────────────────────────────────────────┘
```

- `rclpy.spin(node)`: 내부적으로 `SingleThreadedExecutor`에 노드를 넣고 위 루프를 **끝없이** 돕니다.
- `executor.spin_once(timeout_sec)`: 위 루프를 **한 바퀴만** 돕니다. 준비된 콜백이 없으면 `timeout_sec`까지 기다렸다가 돌아옵니다. 직접 루프를 짜고 싶을 때(이 장의 데모처럼 "6초만 돌기") 씁니다.
- `spin_until_future_complete(future)`: future가 끝날 때까지 돕니다(04장 서비스 클라이언트에서 사용).

### 싱글 스레드에서는 콜백이 줄을 선다

`SingleThreadedExecutor`는 콜백을 하나씩 차례대로 실행합니다. 느린 콜백이 300 ms 동안 붙잡고 있으면, 그 사이에 시간이 된 빠른 타이머는 기다릴 수밖에 없습니다.

```
시간(ms)   0   100  200  300  400  500 ...  1000 1100 1200 1300 1400
fast      ■    ■    ■    ■    ■    ■  ...   ■    ·    ·    ■    ■
slow                                         ■■■■■■■■■■■■■■■
                                             └ 300ms 동안 스레드 점유 ┘
                         · = 원래 불려야 했지만 건너뛴 틱
```

### 콜백 그룹 = "누구끼리 동시에 돌아도 되는가"

`MultiThreadedExecutor`는 스레드 풀을 가지고 있어서 콜백을 동시에 실행할 수 있습니다. 하지만 **동시에 실행해도 되는지는 콜백 그룹이 정합니다.**

| 콜백 그룹 | 규칙 |
|---|---|
| `MutuallyExclusiveCallbackGroup` | 같은 그룹 안의 콜백은 한 번에 하나만 실행 |
| `ReentrantCallbackGroup` | 같은 그룹 안의 콜백(같은 콜백 자신 포함)도 동시에 실행 가능 |

콜백 그룹을 지정하지 않으면 노드의 **기본 그룹**에 들어가는데, 이것이 MutuallyExclusive입니다. 그래서 스레드를 아무리 늘려도, 그룹을 나누지 않으면 한 노드의 콜백은 여전히 하나씩 실행됩니다.

```
multi_exclusive:  [기본 그룹: fast, slow]  → 스레드 4개, 하지만 동시에 1개만
multi_separate:   [그룹A: fast] [그룹B: slow] → 서로 막지 않음
multi_reentrant:  [Reentrant 그룹: fast, slow] → 서로 막지 않음
```

## 3. 코드 읽기

소스: [`ws/src/ros2_study/ros2_study/executor_demo.py`](../../ws/src/ros2_study/ros2_study/executor_demo.py)

### 3-1. 실험 조건을 파라미터로

```python
self.mode = self.declare_parameter('mode', 'single').value
self.slow_ms = self.declare_parameter('slow_ms', 300).value
self.busy = self.declare_parameter('busy', False).value
self.duration = self.declare_parameter('duration', 6.0).value
```

코드를 고치지 않고 `--ros-args -p mode:=...`로 조건을 바꿔 비교하려고 모두 파라미터로 뺐습니다. `duration`초 동안 돌고 통계를 출력한 뒤 스스로 종료합니다.

### 3-2. 콜백 그룹 고르기 — 이 장의 핵심 세 줄

```python
if self.mode == 'multi_separate':
    fast_group = MutuallyExclusiveCallbackGroup()
    slow_group = MutuallyExclusiveCallbackGroup()  # 그룹이 다르면 서로 막지 않는다
elif self.mode == 'multi_reentrant':
    fast_group = slow_group = ReentrantCallbackGroup()  # 같은 그룹이어도 동시 실행 허용
else:
    fast_group = slow_group = None  # None = 기본 그룹
...
self.create_timer(FAST_PERIOD, self.on_fast, callback_group=fast_group)
self.create_timer(SLOW_PERIOD, self.on_slow, callback_group=slow_group)
```

`create_timer`, `create_subscription`, `create_service` 등은 모두 `callback_group=` 인자를 받습니다. `None`이면 노드 기본 그룹(MutuallyExclusive)입니다. `single`과 `multi_exclusive`는 그룹 설정이 **완전히 같고**, executor만 다릅니다.

### 3-3. 빠른 타이머: 실제 간격 재기

```python
def on_fast(self):
    now = time.monotonic()
    if self.last is not None:
        self.intervals.append(now - self.last)
    self.last = now
```

콜백이 **실제로 불린 시각** 사이의 간격을 모읍니다. 이상적이면 항상 100 ms입니다. `time.time()`(벽시계)은 NTP 보정으로 앞뒤로 움직일 수 있으므로 간격 측정에는 `time.monotonic()`을 씁니다.

### 3-4. 느린 콜백: sleep vs busy

```python
if self.busy:
    end = time.monotonic() + self.slow_ms / 1000
    while time.monotonic() < end:
        pass
else:
    time.sleep(self.slow_ms / 1000)
```

- `time.sleep`: 파일/네트워크 대기, 블로킹 서비스 호출처럼 "기다리기만 하는" 작업을 흉내 냅니다. 기다리는 동안 **GIL을 놓습니다.**
- busy 루프: 영상 처리 같은 "CPU를 계속 쓰는" 순수 Python 계산을 흉내 냅니다. 이 동안 GIL을 거의 놓지 않습니다(→ 실험 3).

### 3-5. executor 고르고 직접 spin_once 반복

```python
if node.mode == 'single':
    executor = SingleThreadedExecutor()
else:
    executor = MultiThreadedExecutor(num_threads=4)
executor.add_node(node)
...
end = time.monotonic() + node.duration
while rclpy.ok() and time.monotonic() < end:
    executor.spin_once(timeout_sec=0.1)
```

`rclpy.spin(node)`는 사실 이 `while` 루프와 같은 일을 끝없이 하는 것입니다. 여기서는 정해진 시간만 돌고 멈추려고 `spin_once`를 직접 반복했습니다. 멀티스레드 executor의 `spin_once`는 콜백을 스레드 풀에 **넘기고 바로 돌아오므로**, 콜백이 끝나기를 기다리지 않습니다.

### 3-6. 종료 처리

```python
time.sleep(node.slow_ms / 1000 + 0.1)
executor.shutdown()
node.report()
```

Jazzy의 rclpy `MultiThreadedExecutor`는 스레드 풀에서 아직 실행 중인 콜백을 기다려 주지 않고 내부 객체를 정리합니다. 그래서 바로 종료하면 늦게 끝난 콜백이 정리된 객체를 건드려 `The following exception was never retrieved: cannot use Destroyable because destruction was requested` 경고가 찍혔습니다(실제로 겪은 일). spin을 멈춘 뒤 가장 긴 콜백이 끝날 만큼 기다리고 정리합니다. `report()`도 콜백 스레드가 모두 멈춘 다음에 읽으므로 경합이 없습니다.

## 4. 실행해 보기

터미널 1개면 충분합니다.

```bash
docker compose exec ros bash
cd /ws && colcon build --symlink-install && source install/setup.bash

ros2 run ros2_study executor_demo --ros-args -p mode:=single
ros2 run ros2_study executor_demo --ros-args -p mode:=multi_exclusive
ros2 run ros2_study executor_demo --ros-args -p mode:=multi_separate
ros2 run ros2_study executor_demo --ros-args -p mode:=multi_reentrant
```

실제 출력(64코어 서버의 Docker 컨테이너, 다른 작업이 함께 돌고 있던 상태):

```
mode=single slow_ms=300 busy=False threads=['MainThread']
  fast ticks=50 (이상적이면 60)
  period ms: mean=120.4 min=98.9 max=301.1
  deviation ms: mean|dev|=20.6 max=201.1 | 50ms 넘게 늦은 틱=5
mode=multi_exclusive slow_ms=300 busy=False threads=['ThreadPoolExecutor-0_0', 'ThreadPoolExecutor-0_1', 'ThreadPoolExecutor-0_2']
  fast ticks=50 (이상적이면 60)
  period ms: mean=120.4 min=98.5 max=301.4
  deviation ms: mean|dev|=20.8 max=201.4 | 50ms 넘게 늦은 틱=5
mode=multi_separate slow_ms=300 busy=False threads=['ThreadPoolExecutor-0_0', 'ThreadPoolExecutor-0_1', 'ThreadPoolExecutor-0_2', 'ThreadPoolExecutor-0_3']
  fast ticks=60 (이상적이면 60)
  period ms: mean=100.0 min=99.6 max=100.4
  deviation ms: mean|dev|=0.2 max=0.4 | 50ms 넘게 늦은 틱=0
mode=multi_reentrant slow_ms=300 busy=False threads=['ThreadPoolExecutor-0_0', 'ThreadPoolExecutor-0_1', 'ThreadPoolExecutor-0_2', 'ThreadPoolExecutor-0_3']
  fast ticks=60 (이상적이면 60)
  period ms: mean=100.0 min=99.4 max=100.4
  deviation ms: mean|dev|=0.2 max=0.4 | 50ms 넘게 늦은 틱=0
```

같은 명령을 네 번씩 반복했을 때도 숫자가 거의 같았습니다(예: `multi_exclusive`의 ticks는 49 또는 50).

| mode | fast 틱 (이상 60) | 최대 간격 | 평균 \|오차\| | 최대 오차 |
|---|---|---|---|---|
| `single` | 50 | 301 ms | 20.6 ms | +201 ms |
| `multi_exclusive` | 49~50 | 301 ms | 20.8 ms | +201 ms |
| `multi_separate` | 60 | 100.4~100.6 ms | 0.2 ms | +0.6 ms 이하 |
| `multi_reentrant` | 60 | 100.4~100.5 ms | 0.2 ms | +0.5 ms 이하 |

읽는 법:

- **`single`**: slow가 300 ms 동안 스레드를 잡고 있으니 fast 간격이 최대 301 ms가 됩니다. 늦은 틱(5개)은 slow가 실행된 횟수(1~5초, 5번)와 같습니다.
- **틱 수가 60이 아니라 50인 이유**: slow가 돌던 300 ms 동안 원래 있어야 할 틱 2개는 **나중에 몰아서 실행되지 않고 건너뜁니다.** ROS 2 타이머는 밀린 호출을 쌓아 두지 않고 원래 박자(100 ms 격자)에 다시 맞춥니다. 5번 × 2틱 = 10틱이 사라졌습니다.
- **`multi_exclusive`**: 스레드 이름이 여러 개 보이니 "멀티스레드로 돌았다"는 건 맞습니다. 그런데 숫자는 `single`과 똑같습니다. 두 콜백이 같은 기본 그룹에 있어서 동시에 실행될 수 없기 때문입니다. **스레드 수가 아니라 콜백 그룹이 동시성을 결정합니다.**
- **`multi_separate` / `multi_reentrant`**: fast가 다른 스레드에서 제시간에 돌아 오차가 1 ms 미만입니다.

## 5. 실험해 보기

1. **느린 콜백을 짧게**: `-p mode:=single -p slow_ms:=50`
   관찰: `fast ticks=60`, `max=100.2`, 늦은 틱 0. slow(50 ms)가 fast 틱 사이(100 ms 간격)에 끝나서 싱글 스레드여도 문제가 없었습니다. **싱글 스레드가 나쁜 게 아니라, 콜백이 주기보다 오래 걸리는 게 문제입니다.**

2. **느린 콜백을 길게**: `-p mode:=single -p slow_ms:=600`
   관찰: `fast ticks=35`, `max=600.9`, 평균 주기 173.5 ms. 한 번 막힐 때마다 틱 5개씩 사라졌습니다(5번 × 5 = 25틱).

3. **sleep 대신 CPU 계산 (GIL)**: `-p mode:=multi_separate -p busy:=true`
   관찰: `mean|dev|=2.6`, `max=15.2`, `min=85.8` (sleep일 때는 0.2 / 0.6). 그룹을 나눴는데도 fast가 최대 15 ms 늦었습니다. CPython은 한 번에 한 스레드만 Python 코드를 실행하도록 **GIL**을 쓰고, CPU를 쓰는 스레드는 기본 5 ms(`sys.getswitchinterval()` = 0.005, 이 컨테이너에서 확인)마다 GIL을 넘겨줍니다. fast 타이머 하나가 실행되려면 executor 루프와 워커 스레드가 각각 GIL을 받아야 하므로 여러 번 기다린 것으로 보입니다(원인 해석은 추정). `min=85.8`은 늦게 불린 다음 틱이 원래 박자로 돌아오면서 간격이 짧아진 것입니다.
   같은 조건을 `mode:=single`로 돌리면 sleep 때와 똑같이 `max=201.3`이었습니다. 싱글 스레드에선 어차피 막히니까요.

4. **CPU 계산을 더 길게**: `-p mode:=multi_separate -p busy:=true -p slow_ms:=900`
   관찰: `mean|dev|=2.6`, `max=15.1`. slow를 3배로 늘려도 최대 오차는 그대로였습니다. GIL로 인한 지연은 "느린 콜백의 길이"가 아니라 "GIL을 넘겨받는 간격"에 묶인다는 뜻입니다. 대신 이 지연은 slow가 도는 **내내** 생깁니다.

## 6. 발표할 때 이렇게 설명하기

> "노드는 콜백 목록일 뿐이고, 그걸 꺼내서 실행하는 건 executor입니다. 기본인 SingleThreadedExecutor는 콜백을 한 줄로 세워서 하나씩 실행하기 때문에, 300 ms 걸리는 콜백이 있으면 10 Hz 타이머가 실제로 최대 300 ms 간격으로 불리고, 밀린 틱은 그냥 사라집니다. 그래서 MultiThreadedExecutor로 바꾸면 해결될 것 같지만, 콜백 그룹을 나누지 않으면 숫자가 전혀 안 바뀝니다. 기본 그룹이 MutuallyExclusive라서 스레드가 여러 개여도 동시에 하나만 돌기 때문입니다. 그룹을 나누면 오차가 200 ms에서 1 ms 미만으로 줄었지만, Python에서 CPU를 쓰는 콜백이면 GIL 때문에 여전히 최대 15 ms 정도 밀렸습니다. 이 '콜백이 실행되기를 기다리는 시간'이 다음 장에서 측정하는 통신 지연에 그대로 더해집니다."

## 7. 자주 하는 실수

1. **`MultiThreadedExecutor`만 쓰고 콜백 그룹을 안 나눈다.** 기본 그룹은 MutuallyExclusive라서 결과가 `single`과 같습니다(위 표의 `multi_exclusive`).
2. **콜백 안에서 오래 기다린다.** `time.sleep`, 블로킹 서비스 호출(`call()`), 무거운 계산을 콜백 안에 넣으면 같은 그룹의 다른 콜백이 모두 멈춥니다. 04장의 서비스 데드락도 같은 원리입니다.
3. **Reentrant로 바꾸고 공유 변수를 그냥 쓴다.** 콜백이 동시에 실행되면 `self.count += 1` 같은 "읽고-고치고-쓰기"는 값이 꼬일 수 있습니다. `threading.Lock`으로 감싸거나, 서로 다른 데이터를 쓰는 콜백만 다른 그룹으로 나누세요. Reentrant는 **같은 콜백끼리도** 겹칠 수 있어서(콜백이 주기보다 길면) 더 조심해야 합니다.
4. **Python에서 스레드를 늘리면 CPU 계산이 빨라진다고 기대한다.** GIL 때문에 Python 코드는 한 번에 한 스레드만 실행됩니다. 무거운 계산은 별도 프로세스(노드 분리), C++(rclcpp), 또는 GIL을 놓는 라이브러리(NumPy 등 일부 연산)로 옮겨야 합니다.
5. **타이머가 밀린 틱을 나중에 몰아서 실행해 줄 거라고 생각한다.** 위 측정처럼 건너뜁니다. 틱 수를 세서 처리량을 계산하면 틀립니다.

## 8. 확인 문제

1. `MultiThreadedExecutor(num_threads=4)`를 썼는데 빠른 타이머가 여전히 300 ms씩 밀립니다. 가장 먼저 의심할 것은?
   <details><summary>정답</summary>두 콜백이 같은 MutuallyExclusive 그룹(지정하지 않으면 노드 기본 그룹)에 있는지. 그룹을 나누거나 Reentrant 그룹에 넣어야 동시에 실행됩니다.</details>

2. `rclpy.spin(node)`과 `executor.spin_once(timeout_sec=0.1)`의 차이는?
   <details><summary>정답</summary><code>spin</code>은 종료될 때까지 "준비된 콜백 기다리기 → 실행"을 무한 반복하고, <code>spin_once</code>는 한 번만 합니다(준비된 콜백이 없으면 최대 0.1초 기다리고 돌아옴). <code>spin</code>은 <code>spin_once</code>를 반복하는 것과 같습니다.</details>

3. `single` 모드에서 6초 동안 fast 틱이 60개가 아니라 50개인 이유는?
   <details><summary>정답</summary>slow가 1초마다 300 ms씩 스레드를 점유하는 동안 놓친 틱(매번 2개)을 타이머가 나중에 몰아서 실행하지 않고 건너뛰기 때문입니다. 5번 × 2 = 10틱.</details>

4. Reentrant 그룹을 쓸 때 MutuallyExclusive 그룹을 여러 개 쓸 때보다 추가로 조심할 점은?
   <details><summary>정답</summary>같은 콜백이 자기 자신과 동시에 실행될 수 있습니다. 예를 들어 1초 주기 콜백이 1.5초 걸리면 두 개가 겹쳐 돌고, 공유 상태를 건드리면 경합(race)이 생깁니다.</details>

5. 그룹을 나눴는데 `busy:=true`일 때 fast가 최대 15 ms 늦은 이유와, 이를 줄이는 방법 하나는?
   <details><summary>정답</summary>Python GIL 때문에 CPU를 쓰는 slow 스레드가 GIL을 잡고 있으면 fast 쪽 스레드가 GIL을 받을 때까지(기본 5 ms 간격) 기다려야 합니다. 무거운 계산을 별도 프로세스의 노드로 분리하거나 C++로 옮기면 됩니다.</details>

## 9. 더 읽을거리

- Executors (개념): https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Executors.html
- Using Callback Groups (How-to): https://docs.ros.org/en/jazzy/How-To-Guides/Using-callback-groups.html
- 동기/비동기 서비스 호출 (04장과 연결): https://docs.ros.org/en/jazzy/How-To-Guides/Sync-Vs-Async.html
- rclpy API — Execution and Callbacks: https://docs.ros.org/en/jazzy/p/rclpy/api/execution_and_callbacks.html
- 다음 장: [06. 통신 지연 측정](06_latency.md)의 ⑤⑥ 단계(수신 측 executor 대기와 콜백 실행)가 이 장에서 본 지연입니다.
