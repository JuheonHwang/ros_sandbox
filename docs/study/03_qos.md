# 03. QoS (Quality of Service)

## 이 장의 목표

- QoS의 세 가지 기본 정책(reliability, durability, history/depth)이 각각 무엇을 정하는지, 그리고 **"요청(request) ≤ 제공(offer)"** 호환 규칙 때문에 왜 "코드는 맞는데 메시지가 안 오는" 일이 생기는지 설명할 수 있다.
- `ros2 topic info -v`와 rclpy가 출력하는 incompatible QoS 경고로 QoS 문제를 진단할 수 있다.
- 센서 데이터 / 명령 / 지도·`tf_static`처럼 데이터 성격에 맞는 QoS를 고르고, depth가 **유실과 지연(신선도)** 사이의 trade-off라는 것을 실험 결과로 설명할 수 있다.

## 핵심 개념

### QoS = 발행자와 구독자가 맺는 "배달 계약"

토픽(02장)은 이름과 메시지 타입만 맞으면 연결된다고 배웠습니다. 사실은 하나가 더 있습니다. 발행자와 구독자는 각자 QoS 정책을 갖고 있고, DDS는 둘을 비교해서 **호환될 때만** 연결합니다. 호환되지 않으면 에러로 죽지 않고, 경고 한 줄만 남긴 채 **조용히 메시지가 0건**입니다.

```
  발행자 (offer: "나는 이만큼 해 줄 수 있다")      구독자 (request: "나는 이만큼 필요하다")
 ┌──────────────────────────────┐            ┌──────────────────────────────┐
 │ reliability = BEST_EFFORT    │            │ reliability = RELIABLE       │
 │ durability  = VOLATILE       │   DDS가     │ durability  = VOLATILE       │
 │ depth       = 10  (발행 큐)   │ ─ 비교 ──▶  │ depth       = 10  (수신 큐)   │
 └──────────────────────────────┘            └──────────────────────────────┘
          offer(BEST_EFFORT) < request(RELIABLE)  →  연결 안 됨, 메시지 0건
```

### 세 가지 기본 정책

| 정책 | 값 | 의미 |
|---|---|---|
| **reliability** | `RELIABLE` | 못 받은 샘플은 재전송해서라도 전달하려고 한다. 네트워크가 나쁘면 재전송 때문에 지연이 늘 수 있다. |
| | `BEST_EFFORT` | 한 번 보내고 끝. 빠지면 빠진 대로 간다. 재전송이 없으니 지연이 일정하다. |
| **durability** | `VOLATILE` | 구독자가 연결된 **이후**에 발행된 메시지만 받는다. |
| | `TRANSIENT_LOCAL` | 발행자가 최근 `depth`개를 보관해 두었다가, **늦게 붙은 구독자에게도** 보내 준다(ROS 1의 latch와 비슷). 발행자가 살아 있는 동안만 유효하다. |
| **history / depth** | `KEEP_LAST` + `depth=N` | 큐에 최근 N개만 보관한다. 꽉 차면 **가장 오래된 것부터 버린다**. |
| | `KEEP_ALL` | (DDS 자원 한도까지) 모두 보관한다. |

depth는 발행자 쪽(보내기 전/재전송용 보관)과 구독자 쪽(콜백이 꺼내 가기 전까지 보관) 큐에 각각 따로 적용됩니다. 느린 구독자에서 메시지가 버려지는 곳은 **구독자 쪽 큐**입니다(실험 (d)).

이 밖에 deadline, lifespan, liveliness 같은 정책도 있지만 이 장에서는 위 셋만 다룹니다.

### 호환 규칙: 요청 ≤ 제공

구독자가 **요구하는 수준**이 발행자가 **제공하는 수준**보다 높으면 연결되지 않습니다. 순서는 `RELIABLE > BEST_EFFORT`, `TRANSIENT_LOCAL > VOLATILE`입니다.

| 발행자 (offer) | 구독자 (request) | 결과 |
|---|---|---|
| RELIABLE | RELIABLE | 연결 (실험 a) |
| RELIABLE | BEST_EFFORT | 연결 (best effort로 동작) |
| BEST_EFFORT | RELIABLE | **연결 안 됨** (실험 b) |
| BEST_EFFORT | BEST_EFFORT | 연결 |
| TRANSIENT_LOCAL | TRANSIENT_LOCAL | 연결, 늦게 와도 지난 메시지 받음 (실험 c) |
| TRANSIENT_LOCAL | VOLATILE | 연결, 지난 메시지는 못 받음 (실험 c) |
| VOLATILE | TRANSIENT_LOCAL | **연결 안 됨** (실험해 보기 2) |

history/depth는 호환 여부에 영향을 주지 않습니다. 각자 자기 큐 크기일 뿐입니다.

외우는 요령: **구독자를 느슨하게(best_effort, volatile) 만들면 누구와도 연결된다.** 그래서 "받기만 하는" 쪽(모니터링, 시각화)은 보통 sensor data 프로파일로 구독합니다.

### 미리 만들어진 프로파일 (Jazzy rclpy에서 직접 출력해 확인한 값)

| 이름 | history | depth | reliability | durability | 용도 |
|---|---|---|---|---|---|
| `create_publisher(..., 10)` 처럼 정수만 줄 때 | KEEP_LAST | 10 | RELIABLE | VOLATILE | 일반 토픽 기본값 |
| `qos_profile_sensor_data` | KEEP_LAST | 5 | BEST_EFFORT | VOLATILE | 카메라, 라이다, IMU |
| `qos_profile_system_default` | SYSTEM_DEFAULT | 0 | SYSTEM_DEFAULT | SYSTEM_DEFAULT | 값을 정하지 않고 RMW(DDS 벤더)의 기본값을 그대로 씀 |
| `qos_profile_services_default` | KEEP_LAST | 10 | RELIABLE | VOLATILE | 서비스 (04장) |

`qos_profile_system_default`는 "ROS의 기본값"이 아니라 "DDS 구현이 정한 기본값"이라는 뜻입니다. RMW를 바꾸면 동작이 달라질 수 있으니 의도를 분명히 하고 싶으면 값을 직접 적는 편이 낫습니다.

### 언제 무엇을 고르나

| 데이터 | 추천 | 이유 |
|---|---|---|
| 센서 스트림 (카메라, 라이다, IMU) | `qos_profile_sensor_data` (best_effort, depth 작게) | 하나 빠져도 곧 다음 프레임이 온다. 옛날 프레임을 재전송받느니 최신 프레임이 낫다. |
| 명령 (`cmd_vel`, 목표 지점, 상태 전환) | reliable, volatile, depth 작게(1~10) | 빠지면 안 되지만, 오래된 명령이 나중에 도착해 실행되는 것도 위험하다. |
| 지도(`/map`), `/tf_static`, 로봇 설명(`/robot_description`) | reliable + **transient_local**, depth 1 | 한 번만(가끔만) 발행된다. 나중에 켜진 rviz나 노드도 받아야 한다. |
| 로그, 통계처럼 빠짐없이 모아야 하는 것 | reliable, depth 크게 또는 KEEP_ALL | 지연보다 완전성이 중요하다. 메모리를 더 쓴다. |

## 코드 읽기

소스: [`ws/src/ros2_study/ros2_study/qos_demo.py`](../../ws/src/ros2_study/ros2_study/qos_demo.py)

### 1) 파라미터 문자열 → QoSProfile

```python
def qos_from_params(node):
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=node.declare_parameter('depth', 10).value,
        reliability=ReliabilityPolicy.get_from_short_key(
            node.declare_parameter('reliability', 'reliable').value),
        durability=DurabilityPolicy.get_from_short_key(
            node.declare_parameter('durability', 'volatile').value),
    )
```

- QoS를 코드에 박아 두지 않고 ROS 파라미터로 받습니다. 그래서 **같은 실행 파일**을 `-p reliability:=best_effort`처럼 옵션만 바꿔 띄우며 비교할 수 있습니다.
- `get_from_short_key()`는 `'best_effort'`, `'transient_local'` 같은 짧은 이름을 enum으로 바꿔 줍니다. `ros2 topic echo --qos-reliability best_effort`처럼 CLI가 쓰는 이름과 같습니다. 오타를 내면 `KeyError`로 바로 죽기 때문에 잘못된 QoS로 조용히 실행되는 일이 없습니다.
- 발행자와 구독자가 **같은 함수**를 씁니다. 실제 프로젝트에서도 QoS를 한곳에서 정의해 두면 짝이 어긋나는 실수를 줄일 수 있습니다.

### 2) 발행자: count개만 보내고 계속 살아 있기

```python
self.count = self.declare_parameter('count', 0).value  # 0이면 무한히 발행
...
def tick(self):
    self.seq += 1
    self.pub.publish(String(data=f'msg {self.seq}'))
    ...
    if self.seq == self.count:
        self.timer.cancel()
```

- 메시지에 일련번호(`msg 1`, `msg 2`...)를 넣어서, 구독자 로그만 봐도 **어떤 메시지가 빠졌는지** 알 수 있게 했습니다.
- `count`개를 보낸 뒤 타이머만 멈추고 노드는 끝내지 않습니다. `TRANSIENT_LOCAL`의 보관함은 발행자 안에 있으므로, 발행자가 죽으면 늦게 온 구독자에게 줄 것이 없기 때문입니다.

### 3) 구독자: 일부러 느리게

```python
self.delay = self.declare_parameter('delay', 0.0).value
...
def on_msg(self, msg):
    self.get_logger().info(f'heard: {msg.data}')
    time.sleep(self.delay)
```

- 콜백에서 `delay`초 동안 잠들어 "처리가 느린 구독자"를 흉내 냅니다. 콜백이 자는 동안 도착한 메시지는 구독자 쪽 큐(depth)에 쌓이고, 넘치면 오래된 것부터 버려집니다.
- 실제 코드에서 콜백 안 `sleep`은 executor 전체를 막으므로 쓰면 안 됩니다(05장). 여기서는 일부러 막는 것이 목적입니다.

### 4) 기본 incompatible QoS 경고

코드에는 경고를 출력하는 부분이 없습니다. rclpy는 `create_publisher` / `create_subscription`에 이벤트 콜백을 따로 주지 않으면 **기본 핸들러를 달아서** 호환되지 않는 상대를 발견했을 때 `[WARN] ... incompatible QoS ...`를 출력합니다(실험 b에서 실제로 확인).

## 실행해 보기

모든 터미널에서 먼저 컨테이너 셸에 들어가 빌드/환경 설정을 합니다.

```bash
docker compose exec ros bash
cd /ws && colcon build --symlink-install --packages-select ros2_study && source install/setup.bash
```

아래 출력은 컨테이너에서 실제로 실행해 얻은 것입니다(앞부분 시각은 `[INFO] [초.나노초]` 형태의 타임스탬프). 길이 때문에 일부 줄을 생략했습니다.

### (a) reliable ↔ reliable: 정상 동작

```bash
ros2 run ros2_study qos_pub     # 터미널 1
ros2 run ros2_study qos_sub     # 터미널 2 (조금 늦게)
```

```text
# 터미널 1 (qos_pub)
[INFO] [1795743564.544647465] [qos_pub]: pub QoS: reliability=RELIABLE durability=VOLATILE depth=10
[INFO] [1795743565.034024963] [qos_pub]: sent: msg 1
[INFO] [1795743565.534188965] [qos_pub]: sent: msg 2
[INFO] [1795743566.034067622] [qos_pub]: sent: msg 3
...
# 터미널 2 (qos_sub)
[INFO] [1795743565.053070481] [qos_sub]: sub QoS: reliability=RELIABLE durability=VOLATILE depth=10
[INFO] [1795743565.534327509] [qos_sub]: heard: msg 2
[INFO] [1795743566.034285230] [qos_sub]: heard: msg 3
[INFO] [1795743566.535005363] [qos_sub]: heard: msg 4
```

`msg 1`은 구독자가 뜨기 직전(565.034 < 565.053)에 발행되어 받지 못했습니다. durability가 `VOLATILE`이면 "연결된 이후의 메시지만" 받기 때문입니다. 이것이 (c)에서 `TRANSIENT_LOCAL`이 필요한 이유입니다.

### (b) 발행자 best_effort + 구독자 reliable: 연결 안 됨

```bash
ros2 run ros2_study qos_pub --ros-args -p reliability:=best_effort   # 터미널 1
ros2 run ros2_study qos_sub --ros-args -p reliability:=reliable      # 터미널 2
ros2 topic info -v /qos_chatter                                      # 터미널 3
```

```text
# 터미널 1 (qos_pub) — 발행자 쪽에도 경고가 뜬다
[INFO] [1795743568.646049594] [qos_pub]: pub QoS: reliability=BEST_EFFORT durability=VOLATILE depth=10
[WARN] [1795743569.111943344] [qos_pub]: New subscription discovered on topic 'qos_chatter', requesting incompatible QoS. No messages will be sent to it. Last incompatible policy: RELIABILITY
[INFO] [1795743569.132401019] [qos_pub]: sent: msg 1
[INFO] [1795743569.632766218] [qos_pub]: sent: msg 2
...
[INFO] [1795743573.132634675] [qos_pub]: sent: msg 9

# 터미널 2 (qos_sub) — 경고 1줄 이후 heard가 한 번도 없다
[INFO] [1795743569.124825312] [qos_sub]: sub QoS: reliability=RELIABLE durability=VOLATILE depth=10
[WARN] [1795743569.189699071] [qos_sub]: New publisher discovered on topic 'qos_chatter', offering incompatible QoS. No messages will be received from it. Last incompatible policy: RELIABILITY
```

```text
# 터미널 3 (ros2 topic info -v /qos_chatter) — 일부 생략
Type: std_msgs/msg/String

Publisher count: 1

Node name: qos_pub
Endpoint type: PUBLISHER
QoS profile:
  Reliability: BEST_EFFORT
  History (Depth): UNKNOWN
  Durability: VOLATILE
  ...

Subscription count: 1

Node name: qos_sub
Endpoint type: SUBSCRIPTION
QoS profile:
  Reliability: RELIABLE
  History (Depth): UNKNOWN
  Durability: VOLATILE
  ...
```

- 경고는 **양쪽 모두**에 뜹니다. 발행자는 "requesting incompatible QoS"(구독자가 무리한 걸 요구함), 구독자는 "offering incompatible QoS"(발행자가 부족하게 제공함)라고 말합니다. `Last incompatible policy`가 어떤 정책이 문제인지 알려 줍니다.
- `ros2 topic info -v`에서 Publisher count 1, Subscription count 1로 **둘 다 보이는데도** 통신이 안 됩니다. "노드가 보이니 연결됐겠지"가 아니라 QoS 줄을 나란히 비교해야 합니다.
- `History (Depth): UNKNOWN`으로 나오는 이유: depth는 호환성에 쓰이지 않는 각자의 설정이라 discovery 정보로 상대에게 전달되지 않습니다.

### (c) transient_local: 늦게 온 구독자도 지난 메시지를 받는다

발행자는 10 Hz로 5개만 보내고 멈춘 채 살아 있습니다. 3초 뒤에 구독자를 하나씩 띄웁니다(구독자는 하나 확인하고 Ctrl+C로 끈 뒤 다음 것).

```bash
# 터미널 1
ros2 run ros2_study qos_pub --ros-args -p durability:=transient_local -p depth:=3 -p count:=5 -p rate:=10.0
# 터미널 2 (발행이 끝난 뒤에)
ros2 run ros2_study qos_sub --ros-args -p durability:=transient_local -p depth:=3
ros2 run ros2_study qos_sub --ros-args -p durability:=volatile
```

```text
# 터미널 1 (qos_pub)
[INFO] [1795743586.151053486] [qos_pub]: pub QoS: reliability=RELIABLE durability=TRANSIENT_LOCAL depth=3
[INFO] [1795743586.240802059] [qos_pub]: sent: msg 1
...
[INFO] [1795743586.640559963] [qos_pub]: sent: msg 5
[INFO] [1795743586.640966074] [qos_pub]: 5개 발행 완료. 노드는 계속 실행 중

# 터미널 2, transient_local 구독자 (발행 끝나고 약 3초 뒤 시작)
[INFO] [1795743589.211003269] [qos_sub]: sub QoS: reliability=RELIABLE durability=TRANSIENT_LOCAL depth=3
[INFO] [1795743589.349530946] [qos_sub]: heard: msg 3
[INFO] [1795743589.350492456] [qos_sub]: heard: msg 4
[INFO] [1795743589.350900016] [qos_sub]: heard: msg 5

# 터미널 2, volatile 구독자 — 아무것도 받지 못함 (경고도 없음: 호환은 되기 때문)
[INFO] [1795743591.154409980] [qos_sub]: sub QoS: reliability=RELIABLE durability=VOLATILE depth=10
```

발행자가 depth=3이므로 최근 3개(`msg 3, 4, 5`)만 보관했다가 새 구독자에게 보냈습니다. `msg 1, 2`는 이미 버려졌습니다.

### (d) depth와 느린 구독자: 유실 vs 신선도

구독자는 메시지 하나에 0.5초가 걸리고(2 Hz 처리), 발행자는 10 Hz로 20개를 보냅니다. depth만 바꿔 비교합니다.

```bash
ros2 run ros2_study qos_sub --ros-args -p depth:=10 -p delay:=0.5                  # 터미널 2 (먼저)
ros2 run ros2_study qos_pub --ros-args -p depth:=10 -p count:=20 -p rate:=10.0     # 터미널 1
# 그다음 두 터미널 모두 depth:=1 로 바꿔서 다시
```

```text
# depth=10  (msg 20 발행 시각: 1795743611.527)
[INFO] [1795743609.627033077] [qos_sub]: heard: msg 1
[INFO] [1795743610.127844093] [qos_sub]: heard: msg 2
[INFO] [1795743610.629735073] [qos_sub]: heard: msg 3
[INFO] [1795743611.130564552] [qos_sub]: heard: msg 7
[INFO] [1795743611.631399459] [qos_sub]: heard: msg 11
[INFO] [1795743612.132338442] [qos_sub]: heard: msg 12
...
[INFO] [1795743616.142094336] [qos_sub]: heard: msg 20

# depth=1  (msg 20 발행 시각: 1795743620.530)
[INFO] [1795743618.630980221] [qos_sub]: heard: msg 1
[INFO] [1795743619.133222553] [qos_sub]: heard: msg 6
[INFO] [1795743619.634604530] [qos_sub]: heard: msg 11
[INFO] [1795743620.136596842] [qos_sub]: heard: msg 16
[INFO] [1795743620.638740279] [qos_sub]: heard: msg 20
```

| depth | 받은 개수 | 마지막 메시지(msg 20)가 처리된 시점 |
|---|---|---|
| 10 | 14 / 20 (4~6, 8~10 유실) | 발행 후 **약 4.6초** 뒤 |
| 1 | 5 / 20 | 발행 후 **약 0.1초** 뒤 |

- **reliable인데도 유실이 났습니다.** reliable은 "네트워크에서 빠진 샘플을 재전송한다"는 약속이지, "느린 콜백이 다 꺼내 갈 때까지 보관한다"는 약속이 아닙니다. 구독자 큐(KEEP_LAST 10)가 넘치면 가장 오래된 것부터 덮어씁니다. 예: `msg 7`을 꺼낼 때 큐에는 7~16이 있었고, 다음에 꺼낼 때는 17~20이 더 들어와 8~10이 밀려났기 때문에 `msg 11`이 나왔습니다.
- **depth가 크면 오래된 데이터를 처리하느라 지연이 커집니다.** depth=10은 마지막 메시지를 4.6초 늦게 처리했고, depth=1은 언제나 최신 것만 처리해서 0.1초 만에 따라잡았습니다. 제어 루프에서 "몇 초 전 센서값"으로 움직이는 것이 얼마나 위험한지 생각해 보세요. 센서/명령 토픽에 depth를 작게 두는 이유입니다.
- 같은 조건을 best_effort + depth=1로 돌려도 결과는 `1, 6, 11, 16, 20`으로 같았습니다. 이 실험에서 유실의 원인은 네트워크가 아니라 구독자 큐이기 때문입니다.

### 큰 메시지 + best_effort 유실 실험은 latency_lab에서

여기서는 작은 문자열이라 네트워크 유실이 생기지 않습니다. 카메라 영상처럼 **큰 메시지**에서 best_effort가 실제로 얼마나 잃어버리는지는 `ws/src/latency_lab`의 talker/listener로 측정할 수 있습니다([`latency.py`](../../ws/src/latency_lab/latency_lab/latency.py), 같은 `reliability`/`depth` 파라미터를 씀, [06장](06_latency.md)). 루트 README의 측정 예시에서는 6 MB, 30 Hz, best_effort일 때 약 70%가 유실되었습니다.

```bash
ros2 run latency_lab talker   --ros-args -p size:=6220800 -p rate:=30.0 -p reliability:=best_effort
ros2 run latency_lab listener --ros-args -p reliability:=best_effort
```

## 실험해 보기

1. **transient_local 구독자의 depth를 바꾸기** — 발행자는 (c)와 같이 `depth:=3 count:=5`로 두고 구독자만 `-p durability:=transient_local -p depth:=10` / `-p depth:=1`로 띄워 봤습니다.
   - 관찰: depth=10 → `msg 3, 4, 5` (3개. 발행자가 3개만 갖고 있으므로). depth=1 → `msg 5` 하나만. 늦게 받을 수 있는 개수는 **발행자 depth와 구독자 depth 중 작은 쪽**으로 제한됩니다.
2. **발행자 volatile + 구독자 transient_local** — `qos_pub` (기본값) + `qos_sub --ros-args -p durability:=transient_local`.
   - 관찰: 양쪽에 `Last incompatible policy: DURABILITY` 경고가 뜨고 메시지는 0건. 구독자가 "지난 것까지 달라"고 요구하는데 발행자가 보관하지 않으니 호환되지 않습니다. 반대 방향(발행자 transient_local + 구독자 volatile)은 (c)에서처럼 연결됩니다.
3. **구독자 depth를 버스트보다 크게** — (d)에서 구독자만 `-p depth:=20 -p delay:=0.5`, 발행자는 `-p count:=20 -p rate:=10.0`(depth 기본 10).
   - 관찰: 20개 모두 `1 2 3 ... 20` 순서대로 받았습니다. 대신 마지막 메시지는 그만큼 늦게 처리됩니다. 유실을 없애는 대가가 지연입니다.
4. **`best_available` 구독자** — `qos_pub --ros-args -p reliability:=best_effort` + `qos_sub --ros-args -p reliability:=best_available`.
   - 관찰: 경고 없이 `heard: msg 2`, `msg 3`, ... 정상 수신. `BEST_AVAILABLE`(Iron부터)은 구독자가 상대 발행자에 맞춰 가능한 최선의 값을 고르게 하는 옵션입니다. 상대 QoS를 모를 때(범용 도구 등) 유용합니다.

## 발표할 때 이렇게 설명하기

> 토픽은 이름과 타입만 맞으면 연결되는 것 같지만, 실제로는 발행자와 구독자가 QoS라는 배달 계약을 비교해서 맞을 때만 연결됩니다. 규칙은 하나, 구독자가 요구하는 수준이 발행자가 제공하는 수준보다 높으면 안 된다는 것입니다. 그래서 best_effort로 보내는 카메라를 reliable로 구독하면 에러 없이 경고 한 줄만 남기고 메시지가 0건이 되고, 이때는 `ros2 topic info -v`로 양쪽 QoS를 나란히 비교하면 원인이 보입니다. durability를 transient_local로 하면 발행자가 최근 depth개를 보관했다가 늦게 온 구독자에게도 주기 때문에, 한 번만 발행하는 지도나 tf_static에 씁니다. depth는 큐 크기인데, 느린 구독자에서는 reliable이어도 큐가 넘치면 오래된 것부터 버려지고, 큐가 크면 오래된 데이터를 처리하느라 지연이 커진다는 것을 실험으로 확인했습니다. 그래서 센서와 명령은 depth를 작게, 빠짐없이 모아야 하는 데이터만 크게 잡습니다.

## 자주 하는 실수

- **best_effort로 발행하는 센서 토픽을 기본값(reliable)으로 구독한다.** 많은 센서 드라이버가 `qos_profile_sensor_data`로 발행합니다. 받는 쪽도 `qos_profile_sensor_data`(또는 best_effort)로 구독하세요. 증상은 "토픽은 보이는데 콜백이 안 불림"입니다.
- **경고를 못 보고 지나친다.** incompatible QoS는 예외가 아니라 `[WARN]` 한 줄입니다. 로그가 많은 launch 환경에서는 묻히기 쉬우니 메시지가 안 오면 먼저 `ros2 topic info -v`를 보세요.
- **"reliable이면 하나도 안 잃어버린다"고 믿는다.** KEEP_LAST에서는 구독자 큐가 넘치면 reliable이어도 버려집니다(실험 d). 전부 받아야 한다면 depth를 충분히 크게 하고 콜백을 빠르게 유지해야 합니다.
- **transient_local 발행자를 금방 종료한다.** 보관함은 발행자 프로세스 안에 있습니다. 발행자가 죽으면 늦게 온 구독자는 아무것도 받지 못합니다.
- **double 파라미터에 정수를 넣는다.** `-p rate:=10`이나 `-p delay:=1`은 `InvalidParameterTypeException: ... of type 'INTEGER', expecting type 'DOUBLE'`로 죽습니다(실제로 확인). `10.0`, `1.0`처럼 소수점을 붙이세요.

## 확인 문제

1. 발행자가 RELIABLE, 구독자가 BEST_EFFORT이면 연결될까요? 반대라면?

<details><summary>답</summary>

RELIABLE 발행자 + BEST_EFFORT 구독자는 연결됩니다(제공 ≥ 요청). BEST_EFFORT 발행자 + RELIABLE 구독자는 구독자가 제공받을 수 없는 수준을 요구하므로 연결되지 않고, 양쪽에 `Last incompatible policy: RELIABILITY` 경고가 뜹니다.
</details>

2. `ros2 topic info -v`에서 Publisher count와 Subscription count가 모두 1인데 메시지가 안 옵니다. 무엇을 확인하나요?

<details><summary>답</summary>

같은 출력의 각 endpoint `QoS profile`에서 Reliability와 Durability를 비교합니다. 발행자 BEST_EFFORT/구독자 RELIABLE이거나 발행자 VOLATILE/구독자 TRANSIENT_LOCAL이면 호환되지 않습니다. 노드 로그에서 `incompatible QoS` 경고도 찾아봅니다.
</details>

3. 지도를 한 번만 발행하는 노드가 있습니다. 나중에 켠 rviz가 지도를 받으려면 발행자와 구독자 QoS를 어떻게 해야 하나요?

<details><summary>답</summary>

둘 다 RELIABLE + TRANSIENT_LOCAL(depth 1이면 충분)로 합니다. 발행자가 transient_local이어야 마지막 지도를 보관하고, 구독자도 transient_local을 요청해야 지난 메시지를 받습니다. 발행자 노드는 계속 살아 있어야 합니다.
</details>

4. 실험 (d)에서 depth=10일 때 reliable인데도 메시지가 빠진 이유와, depth=1일 때 지연이 훨씬 작았던 이유는?

<details><summary>답</summary>

구독자 콜백이 2 Hz로만 꺼내 가는데 10 Hz로 들어오니 구독자 쪽 KEEP_LAST 큐가 넘쳐 가장 오래된 것이 덮어써졌습니다. reliable은 네트워크 재전송 보장이지 앱 처리 보장이 아닙니다. depth=1은 매번 가장 최신 것 하나만 남기므로, 밀린 옛날 메시지를 처리하지 않고 곧바로 최신 메시지를 처리해 지연이 작습니다(약 0.1초 vs 4.6초).
</details>

5. `qos_profile_system_default`를 쓰면 reliability는 무엇이 되나요?

<details><summary>답</summary>

ROS가 정하지 않고(SYSTEM_DEFAULT) 사용 중인 RMW/DDS 구현의 기본값을 따릅니다. 따라서 RMW에 따라 달라질 수 있고, 의도를 분명히 하려면 값을 직접 지정하는 것이 좋습니다.
</details>

## 더 읽을거리

- Quality of Service settings (개념, 호환 규칙 표): https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html
- QoS 데모 튜토리얼: https://docs.ros.org/en/jazzy/Tutorials/Demos/Quality-of-Service.html
- 토픽 개념: https://docs.ros.org/en/jazzy/Concepts/Basic/About-Topics.html
- DDS 미들웨어 벤더 차이: https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Different-Middleware-Vendors.html
- DDS 튜닝 (큰 메시지, 유실): https://docs.ros.org/en/jazzy/How-To-Guides/DDS-tuning.html
