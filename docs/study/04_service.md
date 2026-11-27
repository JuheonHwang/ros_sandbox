# 04. 서비스 (Service)

## 이 장의 목표

- 서비스가 토픽·액션과 어떻게 다른지, `.srv` 파일의 요청/응답 구조를 설명하고 언제 서비스를 쓰는지 판단할 수 있다.
- `call_async()` + `spin_until_future_complete()`로 올바른 rclpy 클라이언트를 만들고, `ros2 service list -t / type / call`로 서비스를 다룰 수 있다.
- **콜백 안에서 동기 호출(`client.call()`)을 하면 왜 데드락이 나는지** executor 관점에서 설명하고, 두 가지 해결책(비동기 + done 콜백, 별도 콜백 그룹 + MultiThreadedExecutor)을 적용할 수 있다.

## 핵심 개념

### 서비스 = 요청 1개에 응답 1개

토픽이 "방송"이라면 서비스는 "전화"입니다. 클라이언트가 요청을 보내면 서버가 처리해서 **그 클라이언트에게만** 응답을 돌려줍니다.

```
  클라이언트 노드                                   서버 노드
 ┌──────────────┐  ① Request {a: 3, b: 5}      ┌──────────────┐
 │ add_client   │ ───────────────────────────▶ │ add_server   │
 │              │                              │  on_request()│ ② sum = a + b
 │  future ◀────┼──────────────────────────────┤              │
 └──────────────┘  ③ Response {sum: 8}         └──────────────┘
      ④ executor가 응답을 받아 future를 "완료"로 바꿔야 결과를 꺼낼 수 있다
```

④가 이 장의 핵심입니다. 응답이 네트워크로 도착하는 것만으로는 부족하고, **클라이언트 쪽 executor가 spin하면서 그 응답을 꺼내 future에 넣어 줘야** 합니다. 이 일을 할 스레드가 없으면 응답이 와 있어도 영원히 기다리게 됩니다(데드락).

### `.srv` 파일: `---` 위가 요청, 아래가 응답

```text
$ ros2 interface show example_interfaces/srv/AddTwoInts
int64 a
int64 b
---
int64 sum
```

이 파일 하나로 `AddTwoInts.Request`(필드 `a`, `b`)와 `AddTwoInts.Response`(필드 `sum`) 두 타입이 생성됩니다. 서버와 클라이언트가 같은 서비스 타입을 써야 연결됩니다.

### 토픽 vs 서비스 vs 액션

| | 토픽 | 서비스 | 액션 |
|---|---|---|---|
| 모양 | 발행자 → 구독자 (N:M) | 요청 → 응답 (클라이언트 N : 서버 1) | 목표 → (피드백 여러 번) → 결과 |
| 응답 | 없음 | 1번 | 진행 중 피드백 + 최종 결과, 중간 취소 가능 |
| 걸리는 시간 | 계속 흐름 | **짧게 끝나는 일** | 몇 초~몇 분 걸리는 일 |
| 예 | 센서 데이터, `cmd_vel`, 상태 | 파라미터 조회/설정, 모드 전환, 계산 요청 | 목표 지점까지 이동, 팔 동작 |
| 인터페이스 파일 | `.msg` | `.srv` (`---` 1개) | `.action` (`---` 2개: goal/result/feedback) |

서비스 서버는 요청을 처리하는 동안 그 콜백을 차지하므로, 오래 걸리는 일은 서비스가 아니라 액션으로 만듭니다.

### 데드락이 나는 이유 (단일 스레드 executor)

```
SingleThreadedExecutor (스레드 1개)
 │
 ├─ 타이머 만료 → tick() 실행
 │     └─ client.call(req)  ── 요청 전송 ──▶ 서버: "1 + 100 = 101" 응답 전송 (서버는 정상!)
 │           └─ 응답이 future에 들어올 때까지 대기...
 │                                     ▲
 │                    응답을 꺼내 future에 넣는 일 = executor의 일
 │                    그런데 executor의 유일한 스레드가 바로 위에서 대기 중
 │
 └─ (tick()이 끝나야 다음 일을 할 수 있음) → 영원히 안 끝남
```

rclpy의 `Client.call()` 소스 docstring에도 그대로 적혀 있습니다: *"Do not call this method in a callback, or a deadlock or timeout may occur."*

## 코드 읽기

소스: [`ws/src/ros2_study/ros2_study/service_demo.py`](../../ws/src/ros2_study/ros2_study/service_demo.py)

### 1) 서버: 콜백은 `(request, response)`를 받아 response를 돌려준다

```python
self.create_service(AddTwoInts, SERVICE, self.on_request)

def on_request(self, request, response):
    response.sum = request.a + request.b
    ...
    return response
```

- `create_service(타입, 이름, 콜백)`. 이름 `add_two_ints`는 상대 이름이라 실제로는 `/add_two_ints`가 됩니다.
- rclpy가 빈 `response` 객체를 미리 만들어 넘겨 줍니다. 필드를 채워 **return하는 것이 곧 응답 전송**입니다. `return response`를 지우고 실행해 보니 요청이 오는 순간 서버가 `send_response`에서 `TypeError`로 죽었고, `ros2 service call`은 응답을 받지 못했습니다.

### 2) 클라이언트: 서버 기다리기 → call_async → spin_until_future_complete

```python
cli = node.create_client(AddTwoInts, SERVICE)
if not cli.wait_for_service(timeout_sec=5.0):
    node.get_logger().error(f'/{SERVICE} 서버를 찾지 못했습니다')
else:
    future = cli.call_async(AddTwoInts.Request(a=a, b=b))
    rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
    if future.done():
        node.get_logger().info(f'{a} + {b} = {future.result().sum}')
```

- `wait_for_service()`: 서버가 discovery로 보일 때까지 기다립니다. 서버가 없을 때 요청을 보내면 받아 줄 곳이 없어 응답이 영원히 오지 않으므로 먼저 확인합니다. timeout을 꼭 줘서 "무한 대기"를 피합니다.
- `call_async()`: 요청을 보내고 **바로** `Future`(나중에 결과가 채워질 상자)를 돌려줍니다.
- `spin_until_future_complete()`: future가 완료될 때까지 executor를 돌립니다. 이 spin 덕분에 응답이 꺼내져 future에 들어갑니다(핵심 개념의 ④). 이 코드는 콜백 안이 아니라 `main` 흐름이라서 직접 spin해도 안전합니다.
- `a`, `b`는 ROS 파라미터입니다(`--ros-args -p a:=3 -p b:=5`, 기본값 2, 3).

### 3) 데드락 데모: 타이머 콜백 안에서 서비스 부르기

```python
def tick(self):
    ...
    req = AddTwoInts.Request(a=self.n, b=100)
    self.get_logger().info(f'요청 보냄: {req.a} + 100')
    if self.mode == 'async':
        self.cli.call_async(req).add_done_callback(
            lambda f, a=req.a: self.get_logger().info(f'응답(async): {a} + 100 = {f.result().sum}'))
        return
    res = self.cli.call(req)
    self.get_logger().info(f'응답(call): {req.a} + 100 = {res.sum}')
```

`mode` 파라미터로 세 가지를 고릅니다.

| mode | 호출 방식 | executor | 결과 |
|---|---|---|---|
| `sync` (기본) | `call()` (블로킹) | SingleThreaded | **멈춤** |
| `async` | `call_async()` + `add_done_callback()` | SingleThreaded | 동작 |
| `multi` | `call()` (블로킹) | MultiThreaded + 클라이언트를 별도 콜백 그룹에 | 동작 |

- **async**: tick()은 요청만 보내고 바로 return합니다. 스레드가 풀려나니 executor가 응답을 꺼내 future를 완료시키고, 그때 등록해 둔 done 콜백을 실행합니다. "기다리지 말고, 끝나면 불러 달라"는 방식입니다. `lambda f, a=req.a:`의 `a=req.a`는 람다가 만들어질 때의 값을 고정하기 위한 것입니다.
- **multi**: 아래 두 줄이 짝입니다.

```python
group = MutuallyExclusiveCallbackGroup() if mode == 'multi' else None
self.cli = self.create_client(AddTwoInts, SERVICE, callback_group=group)
...
executor = MultiThreadedExecutor() if node.mode == 'multi' else SingleThreadedExecutor()
```

  스레드가 여러 개여도, 같은 MutuallyExclusive 콜백 그룹에 속한 콜백은 동시에 실행되지 않습니다. 그룹을 안 주면 타이머와 클라이언트가 모두 노드의 **기본 그룹(MutuallyExclusive)** 에 들어가서, 타이머 콜백이 끝나기 전에는 응답 처리도 못 합니다. 그래서 클라이언트를 **다른 그룹**에 넣어야 다른 스레드가 응답을 처리할 수 있습니다(실험해 보기 1에서 확인). 콜백 그룹은 05장에서 더 자세히 다룹니다.

## 실행해 보기

모든 터미널에서 먼저 컨테이너 셸에 들어가 빌드/환경 설정을 합니다.

```bash
docker compose exec ros bash
cd /ws && colcon build --symlink-install --packages-select ros2_study && source install/setup.bash
```

아래 출력은 컨테이너에서 실제로 실행해 얻은 것입니다(일부 생략).

### 서버와 클라이언트

```bash
ros2 run ros2_study add_server                               # 터미널 1
ros2 run ros2_study add_client                               # 터미널 2 (기본값 a=2, b=3)
ros2 run ros2_study add_client --ros-args -p a:=3 -p b:=5    # 터미널 2
```

```text
# 터미널 2 (기본값)
[INFO] [1795743999.049937110] [add_client]: 2 + 3 = 5
# 터미널 2 (a=3, b=5)
[INFO] [1795743678.022325647] [add_client]: 3 + 5 = 8

# 터미널 1 (a=3, b=5 요청을 받았을 때)
[INFO] [1795743676.756820454] [add_server]: /add_two_ints 서비스 대기 중
[INFO] [1795743678.010028145] [add_server]: 요청: 3 + 5 → 응답: 8
```

(두 클라이언트 출력은 서로 다른 실행에서 캡처해 타임스탬프가 이어지지 않습니다.)

### CLI로 서비스 다루기 (서버를 켜 둔 상태에서, 터미널 3)

```bash
ros2 service list -t
ros2 service type /add_two_ints
ros2 service call /add_two_ints example_interfaces/srv/AddTwoInts "{a: 10, b: 20}"
```

```text
$ ros2 service list -t
/add_server/describe_parameters [rcl_interfaces/srv/DescribeParameters]
/add_server/get_parameter_types [rcl_interfaces/srv/GetParameterTypes]
/add_server/get_parameters [rcl_interfaces/srv/GetParameters]
/add_server/get_type_description [type_description_interfaces/srv/GetTypeDescription]
/add_server/list_parameters [rcl_interfaces/srv/ListParameters]
/add_server/set_parameters [rcl_interfaces/srv/SetParameters]
/add_server/set_parameters_atomically [rcl_interfaces/srv/SetParametersAtomically]
/add_two_ints [example_interfaces/srv/AddTwoInts]

$ ros2 service type /add_two_ints
example_interfaces/srv/AddTwoInts

$ ros2 service call /add_two_ints example_interfaces/srv/AddTwoInts "{a: 10, b: 20}"
waiting for service to become available...
requester: making request: example_interfaces.srv.AddTwoInts_Request(a=10, b=20)

response:
example_interfaces.srv.AddTwoInts_Response(sum=30)
```

- `-t`는 서비스 타입을 같이 보여 줍니다. 우리가 만든 건 `/add_two_ints` 하나인데 `/add_server/...` 서비스가 7개 더 보입니다. 모든 노드는 파라미터를 다루는 서비스를 자동으로 갖고 있고, `ros2 param` 명령이 바로 이 서비스들을 부르는 것입니다.
- `ros2 service call`의 마지막 인자는 요청을 YAML로 적은 것입니다.

### 데드락 재현: `mode:=sync`

서버(터미널 1)를 켜 둔 상태에서 실행합니다. 5초 기다려도 응답이 안 나오는 것을 확인하고 Ctrl+C로 끕니다. 아래는 `timeout -s INT 5`(5초 뒤 Ctrl+C와 같은 SIGINT를 보냄)로 실행한 결과입니다.

```bash
ros2 run ros2_study deadlock_demo                          # 터미널 2
# 자동으로 끄고 싶으면: timeout -s INT 5 ros2 run ros2_study deadlock_demo
```

```text
# 터미널 2 (deadlock_demo, mode=sync)
[INFO] [1795743943.156771935] [deadlock_demo]: mode=sync
[INFO] [1795743944.142681254] [deadlock_demo]: 요청 보냄: 1 + 100
exit code: 124          ← 5초 동안 아무 출력 없이 멈춰 있다가 timeout이 끊음

# 터미널 1 (add_server) — 서버는 요청을 받고 약 2 ms 뒤에 이미 응답했다!
[INFO] [1795743944.145001186] [add_server]: 요청: 1 + 100 → 응답: 101
```

서버 로그를 보면 요청은 944.142에 나갔고, 서버는 944.145에 이미 응답을 보냈습니다. **응답은 도착했는데 클라이언트 쪽에서 그것을 꺼낼 스레드가 없어서** 멈춘 것입니다. 1초 주기 타이머도 두 번째 tick을 하지 못합니다.

### 해결 1: `mode:=async`

```bash
ros2 run ros2_study deadlock_demo --ros-args -p mode:=async
```

```text
[INFO] [1795743686.082416894] [deadlock_demo]: mode=async
[INFO] [1795743687.072697822] [deadlock_demo]: 요청 보냄: 1 + 100
[INFO] [1795743687.074737759] [deadlock_demo]: 응답(async): 1 + 100 = 101
[INFO] [1795743688.072497908] [deadlock_demo]: 요청 보냄: 2 + 100
[INFO] [1795743688.075403855] [deadlock_demo]: 응답(async): 2 + 100 = 102
[INFO] [1795743689.072934924] [deadlock_demo]: 요청 보냄: 3 + 100
[INFO] [1795743689.075125898] [deadlock_demo]: 응답(async): 3 + 100 = 103
```

요청 후 2~3 ms 만에 응답 콜백이 실행되고, 타이머도 매초 계속 돕니다.

### 해결 2: `mode:=multi`

```bash
ros2 run ros2_study deadlock_demo --ros-args -p mode:=multi
```

```text
[INFO] [1795743690.017056010] [deadlock_demo]: mode=multi
[INFO] [1795743691.007550440] [deadlock_demo]: 요청 보냄: 1 + 100
[INFO] [1795743691.011726680] [deadlock_demo]: 응답(call): 1 + 100 = 101
[INFO] [1795743692.005691730] [deadlock_demo]: 요청 보냄: 2 + 100
[INFO] [1795743692.009057824] [deadlock_demo]: 응답(call): 2 + 100 = 102
```

같은 `call()`(블로킹)인데도 동작합니다. 타이머 콜백을 실행하는 스레드는 기다리고 있지만, **다른 스레드**가 별도 그룹에 있는 클라이언트의 응답을 처리해 주기 때문입니다.

## 실험해 보기

1. **multi 모드에서 콜백 그룹을 빼 보기** — `service_demo.py`에서 `group = MutuallyExclusiveCallbackGroup() if mode == 'multi' else None`을 `group = None`으로 바꾸고 `mode:=multi`로 실행했습니다.
   - 관찰: `요청 보냄: 1 + 100` 뒤로 멈춤. **스레드를 늘리는 것만으로는 해결되지 않습니다.** 타이머와 클라이언트가 같은 기본 그룹(MutuallyExclusive)에 있어서, 타이머 콜백이 끝나기 전에는 남는 스레드도 응답을 처리하지 못합니다. 게다가 이 상태는 SIGINT(Ctrl+C)를 보내도 프로세스가 끝나지 않아 `kill -9`로 종료해야 했습니다.
2. **`call()`에 timeout 주기** — `res = self.cli.call(req)`를 `res = self.cli.call(req, timeout_sec=2.0)`로 바꾸고 `mode:=sync`로 실행했습니다.
   - 관찰: 2초 뒤 `call()`이 `None`을 돌려주고, 다음 줄에서 `AttributeError: 'NoneType' object has no attribute 'sum'`으로 죽었습니다. timeout은 "무한 대기"를 "2초 뒤 실패"로 바꿀 뿐, 응답을 받게 해 주지는 않습니다. 단일 스레드에서는 몇 초를 기다리든 응답이 처리되지 않습니다.
3. **서버 없이 클라이언트 실행** — 서버를 끄고 `ros2 run ros2_study add_client`.
   - 관찰: 5초 뒤 `[ERROR] ... [add_client]: /add_two_ints 서버를 찾지 못했습니다`. `wait_for_service()`에 timeout을 줬기 때문에 무한 대기하지 않습니다.
4. **데드락 노드를 어떤 신호로 끌 수 있나** — `mode:=sync`로 멈춘 프로세스에 신호를 보내 봤습니다.
   - 관찰: SIGINT(Ctrl+C)에는 종료됐지만 SIGTERM(`kill PID`, `timeout`의 기본 신호)에는 살아 있었습니다. 특히 `timeout 5 ros2 run ...`처럼 SIGTERM으로 끊으면 `ros2 run`만 끝나고 실제 노드 프로세스는 남아 있었습니다. 데드락 실험 뒤에는 `ps aux | grep deadlock_demo`로 남은 프로세스가 없는지 확인하세요.

## 발표할 때 이렇게 설명하기

> 서비스는 요청 하나에 응답 하나를 돌려받는 통신이고, `.srv` 파일에서 `---` 위가 요청, 아래가 응답입니다. 짧게 끝나는 일은 서비스, 계속 흐르는 데이터는 토픽, 오래 걸리고 진행 상황이 필요한 일은 액션을 씁니다. 중요한 점은 응답이 도착해도 클라이언트 쪽 executor가 spin하면서 그 응답을 꺼내 future에 넣어 줘야 결과를 쓸 수 있다는 것입니다. 그래서 단일 스레드 executor의 타이머 콜백 안에서 `call()`로 기다리면, 응답을 꺼내 줄 유일한 스레드가 기다리고 있는 셈이라 서버는 이미 응답했는데도 영원히 멈춥니다. 해결책은 `call_async()`에 done 콜백을 달아 기다리지 않고 바로 돌아오거나, 클라이언트를 별도 콜백 그룹에 넣고 MultiThreadedExecutor를 써서 다른 스레드가 응답을 처리하게 하는 것입니다. 스레드만 늘리고 콜백 그룹을 나누지 않으면 여전히 멈춘다는 것도 실험으로 확인했습니다.

## 자주 하는 실수

- **콜백 안에서 `client.call()`을 부른다.** 단일 스레드 executor에서는 반드시 멈춥니다. 콜백 안에서는 `call_async()` + `add_done_callback()`을 기본으로 쓰세요.
- **MultiThreadedExecutor만 쓰면 해결된다고 생각한다.** 클라이언트를 타이머와 다른 콜백 그룹에 넣지 않으면 여전히 멈춥니다(실험 1).
- **서버 콜백에서 `return response`를 빠뜨린다.** 콜백의 반환값이 곧 응답입니다. 빠뜨리면 요청이 오는 순간 서버가 `TypeError`로 죽습니다(실제로 확인).
- **`wait_for_service()`를 timeout 없이 쓰거나 아예 안 쓴다.** 서버 이름 오타 하나로 프로그램이 조용히 무한 대기합니다.
- **오래 걸리는 작업을 서비스로 만든다.** 클라이언트는 그동안 결과만 기다리고, 진행 상황도 취소도 없습니다. 몇 초 이상 걸리는 일은 액션을 쓰세요.

## 확인 문제

1. `.srv` 파일에서 `---`는 무엇을 나누나요? `AddTwoInts`에서 클라이언트가 채우는 필드는?

<details><summary>답</summary>

`---` 위는 요청(Request), 아래는 응답(Response)입니다. 클라이언트는 `AddTwoInts.Request`의 `a`, `b`를 채워 보내고, 서버는 `AddTwoInts.Response`의 `sum`을 채워 돌려줍니다.
</details>

2. `deadlock_demo`(mode=sync)에서 서버 로그에는 "응답: 101"이 찍혔는데 클라이언트는 멈췄습니다. 응답은 어디에 있고, 왜 처리되지 않나요?

<details><summary>답</summary>

응답은 클라이언트 쪽에 도착해 꺼내지기를 기다리고 있습니다. 응답을 꺼내 future를 완료시키는 일은 executor가 하는데, SingleThreadedExecutor의 유일한 스레드가 타이머 콜백 안의 `call()`에서 future 완료를 기다리며 멈춰 있어서 아무도 그 일을 하지 못합니다.
</details>

3. MultiThreadedExecutor로 바꿨는데도 여전히 멈춥니다. 무엇을 빠뜨렸을까요?

<details><summary>답</summary>

콜백 그룹입니다. 그룹을 지정하지 않으면 타이머와 클라이언트가 노드의 기본 MutuallyExclusive 그룹을 공유하므로, 타이머 콜백이 끝나기 전에는 다른 스레드도 응답을 처리할 수 없습니다. 클라이언트를 별도 콜백 그룹(예: `MutuallyExclusiveCallbackGroup()`)에 넣어야 합니다.
</details>

4. 다음 중 서비스보다 액션이 어울리는 것은? (a) 현재 배터리 잔량 조회 (b) 10 m 떨어진 목표 지점까지 이동 (c) 카메라 영상 전송

<details><summary>답</summary>

(b). 오래 걸리고 진행 상황(피드백)과 취소가 필요합니다. (a)는 짧은 요청/응답이라 서비스, (c)는 계속 흐르는 데이터라 토픽이 맞습니다.
</details>

5. `main` 함수의 `rclpy.spin_until_future_complete(node, future)`는 괜찮은데, 콜백 안의 `client.call()`은 왜 문제인가요?

<details><summary>답</summary>

`main`에서는 아무 executor도 돌고 있지 않으므로 `spin_until_future_complete`가 직접 executor를 돌리면서 응답을 처리합니다. 콜백 안은 이미 executor의 스레드 위에서 실행 중이라, 그 스레드가 기다리기 시작하면 응답을 처리할 주체가 없어집니다.
</details>

## 더 읽을거리

- 서비스 개념: https://docs.ros.org/en/jazzy/Concepts/Basic/About-Services.html
- 서비스 CLI 튜토리얼: https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Services/Understanding-ROS2-Services.html
- 파이썬 서비스/클라이언트 작성: https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Py-Service-And-Client.html
- 동기 vs 비동기 서비스 클라이언트: https://docs.ros.org/en/jazzy/How-To-Guides/Sync-Vs-Async.html
- 콜백 그룹 사용하기: https://docs.ros.org/en/jazzy/How-To-Guides/Using-callback-groups.html
- Executor 개념: https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Executors.html
- 인터페이스(.msg/.srv/.action): https://docs.ros.org/en/jazzy/Concepts/Basic/About-Interfaces.html
- 액션 CLI 튜토리얼: https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Actions/Understanding-ROS2-Actions.html
