# 07. 센서 동기화

> 핵심 질문: 주기가 다른 센서 데이터를 어떻게 같은 순간끼리 묶나?

## 1. 이 장의 목표

- `header.stamp`는 "메시지를 받은 시각"이 아니라 "**데이터가 측정된 시각**"이어야 한다는 것을 이해한다.
- `message_filters`의 `Subscriber` + `ApproximateTimeSynchronizer`로 30 Hz 카메라와 10 Hz 라이다를 짝짓고, `slop`·`queue_size`의 의미를 설명할 수 있다.
- 센서 시각 오차(jitter)와 `slop`을 바꿔 가며 짝이 맞는 비율을 직접 측정하고, `use_sim_time`, 여러 PC의 시계 동기화, tf2의 시간 조회와 연결해 설명할 수 있다.

## 2. 핵심 개념

### 도착 순서가 아니라 stamp로 짝짓는다

카메라와 라이다는 주기도 다르고, 06장에서 봤듯이 메시지 크기에 따라 도착 지연도 다릅니다. "최근에 받은 것끼리" 묶으면 서로 다른 순간의 데이터가 섞입니다. 그래서 각 메시지의 `header.stamp`(측정 시각)를 비교해 **같은 순간에 가까운 것끼리** 묶습니다.

```
stamp 시간축 (ms)   0      33      67     100     133     167     200
camera (30 Hz)      C0     C1      C2     C3      C4      C5      C6
lidar  (10 Hz)      L0                    L1                      L2
                    │                     │                       │
짝                 (C0,L0)              (C3,L1)                 (C6,L2)
                    └ |stamp 차이| < slop 인 것 중 가장 가까운 것

C1, C2, C4, C5 는 짝 없이 버려진다 (라이다보다 카메라가 3배 많으므로)
```

### ExactTime vs ApproximateTime

| | `TimeSynchronizer` (ExactTime) | `ApproximateTimeSynchronizer` |
|---|---|---|
| 짝 조건 | stamp가 **나노초까지 완전히 같아야** 함 | stamp 차이가 `slop` 미만 |
| 쓰는 곳 | 한 드라이버가 같은 stamp를 찍어 내보내는 경우 (예: 스테레오 카메라 좌/우, 이미지와 그 camera_info) | 서로 다른 센서, 서로 다른 드라이버 |

서로 다른 센서는 각자 시계를 읽어 stamp를 찍으므로 나노초까지 같을 일이 거의 없습니다. 이 장의 데모에서 jitter를 0으로 해도 ExactTime은 짝을 **하나도** 못 찾았습니다(실험 2).

### jitter와 slop

```
진짜 측정 시각      ──────●──────────────
카메라 stamp        ───●─────────────────   ← 진짜보다 0~jitter 만큼 이르게 찍힘
라이다 stamp        ─────●───────────────   ← 각자 독립적으로
                       |←→|  이 차이가 slop 미만이어야 짝이 된다
```

- **jitter**: 센서 stamp가 진짜 측정 시각에서 흔들리는 정도(드라이버가 "받은 시각"을 찍거나, 하드웨어 트리거가 없어서 생김).
- **slop**: 짝으로 인정할 최대 stamp 차이. 너무 작으면 짝이 안 맞고, 너무 크면 **다른 순간의 데이터가 짝이 될 수 있습니다.**

### use_sim_time과 /clock

시뮬레이터(Gazebo 등)나 `ros2 bag play --clock`은 `/clock` 토픽으로 "시뮬레이션 시각"을 발행합니다. 노드에 `use_sim_time:=true`를 주면 `get_clock().now()`와 타이머가 벽시계 대신 이 시각을 따릅니다. **한 시스템 안의 모든 노드가 같은 설정이어야 합니다.** 한 노드는 sim time(예: 120초), 다른 노드는 벽시계(예: 17억 초)로 stamp를 찍으면 stamp 차이가 엄청나게 커서 짝이 절대 맞지 않습니다. `/clock`이 없으면(실험 3) 타이머가 멈추는 것도 흔한 함정입니다.

### 여러 PC에서의 동기화

카메라는 PC A, 라이다는 PC B에 붙어 있으면 두 stamp는 서로 다른 시계로 찍힙니다. 두 시계가 10 ms 어긋나 있으면 모든 짝의 |dt|에 10 ms가 더해지고, slop이 그보다 작으면 짝이 안 맞거나 엉뚱한 프레임과 짝이 됩니다. 06장과 같은 이유로 **chrony(NTP)나 PTP로 시계를 맞추는 것이 전제**입니다. 정밀도가 중요하면 센서 자체의 하드웨어 타임스탬프나 트리거 신호를 쓰는 것이 가장 확실합니다.

### tf2의 시간 조회

센서를 짝지은 다음에는 보통 "라이다 점을 카메라 좌표계로 옮기기" 같은 좌표 변환이 필요한데, 로봇이 움직이고 있다면 **그 측정 순간의** 변환을 써야 합니다. tf2는 좌표 변환을 시간과 함께 버퍼에 쌓아 두고(기본 10초 분량), `lookup_transform(target, source, time)`에 메시지의 `header.stamp`를 넘기면 그 시각의 변환을 앞뒤 값으로 보간해서 돌려줍니다. 아직 그 시각의 변환이 도착하지 않았으면 "미래로 외삽(extrapolation)할 수 없다"는 예외가 나므로, timeout을 주고 기다리거나 C++의 `tf2_ros::MessageFilter`로 "변환이 준비된 메시지만 통과"시키는 방법을 씁니다. `message_filters`가 **센서끼리** 시간을 맞춘다면, tf2는 **센서와 로봇 자세**의 시간을 맞추는 도구라고 생각하면 됩니다.

## 3. 코드 읽기

소스: [`ws/src/latency_lab/latency_lab/sync.py`](../../ws/src/latency_lab/latency_lab/sync.py)

### 3-1. 가짜 센서: stamp에 측정 오차 섞기

```python
self.create_timer(1 / 30, lambda: self.publish(self.cam_pub, Image()))
self.create_timer(1 / 10, lambda: self.publish(self.lidar_pub, PointCloud2()))

def publish(self, pub, msg):
    stamp = self.get_clock().now() - Duration(seconds=random.uniform(0, self.jitter))
    msg.header.stamp = stamp.to_msg()
```

- 카메라 30 Hz, 라이다 10 Hz 타이머가 같은 노드에서 돕니다. 두 타이머의 박자가 맞물려서 라이다 1개마다 같은 시각의 카메라가 1개 있습니다.
- stamp를 "지금"에서 `0 ~ jitter_ms` 사이의 무작위 값만큼 **과거로** 당깁니다. 실제 센서에서 "측정한 순간"과 "stamp를 찍은 순간"이 다른 것을 흉내 냅니다.
- 내용(`Image()`, `PointCloud2()`)은 비어 있습니다. 동기화는 stamp만 보기 때문입니다.

### 3-2. message_filters.Subscriber

```python
cam = Subscriber(self, Image, 'camera')
lidar = Subscriber(self, PointCloud2, 'lidar')
lidar.registerCallback(self.on_lidar)
```

`message_filters.Subscriber`는 일반 구독을 감싸서, 받은 메시지를 **다음 필터로 흘려보내는** 입구입니다. 여기에 콜백을 따로 등록할 수도 있습니다. 이 코드는 라이다가 몇 개 왔는지 세려고(짝 맞은 비율의 분모) 라이다 구독에 콜백을 하나 더 붙였습니다. QoS를 따로 주지 않으면 depth 10, reliable입니다.

### 3-3. ApproximateTimeSynchronizer

```python
ApproximateTimeSynchronizer([cam, lidar], queue_size=10, slop=slop).registerCallback(self.on_pair)
```

- 입력 필터 목록, `queue_size`, `slop`(초)을 받고, 짝이 맞으면 `on_pair(cam, lidar)`를 부릅니다. 인자 순서는 목록 순서와 같습니다.
- **`queue_size`**: 토픽마다 짝을 기다리며 보관할 메시지 수. 넘치면 stamp가 가장 오래된 것부터 버립니다. 한 센서가 다른 센서보다 훨씬 늦게 도착한다면(예: 06장의 큰 메시지) 그 지연 동안 들어오는 메시지를 담을 만큼 커야 합니다.
- **`slop`**: 짝으로 인정하는 최대 stamp 차이(초).

Jazzy의 Python 구현(`message_filters/__init__.py`)을 직접 읽어 보면 동작은 이렇습니다.

1. 메시지가 오면 자기 토픽 큐에 `{stamp: msg}`로 넣는다.
2. **다른 토픽 큐에서 stamp 차이가 slop 이내인 후보**를 찾는다. 하나도 없으면 그냥 기다린다.
3. 후보 중 가장 가까운 조합부터 보고, 최대-최소 차이가 slop 미만이면 콜백을 부르고 사용한 메시지를 큐에서 지운다.

즉 "새 메시지가 도착한 순간 조건을 만족하는 가장 가까운 짝"을 바로 내보냅니다. C++ `message_filters`의 ApproximateTime 정책은 다른 알고리즘(더 나은 짝이 올 때까지 기다리는 방식)을 쓰므로, **Python과 C++의 결과가 같다고 가정하면 안 됩니다.** 또 큐가 stamp를 키로 쓰는 dict라서, 같은 토픽에 stamp가 똑같은 메시지가 두 개 오면 앞의 것이 덮어써집니다.

### 3-4. 결과 집계

```python
def on_pair(self, cam, lidar):
    dt = Time.from_msg(cam.header.stamp) - Time.from_msg(lidar.header.stamp)
    self.diffs.append(abs(dt.nanoseconds) / 1e6)
```

짝마다 두 stamp의 차이를 모아, 1초마다 `pairs=짝 수/라이다 수`와 평균 |dt|를 찍습니다. 라이다가 기준이므로 "라이다 프레임 중 몇 %가 카메라 짝을 찾았나"를 보는 것입니다.

## 4. 실행해 보기

각 터미널에서 먼저:

```bash
docker compose exec ros bash
cd /ws && colcon build --symlink-install && source install/setup.bash   # 빌드는 한 번만
```

```bash
ros2 run latency_lab fake_sensors  --ros-args -p jitter_ms:=5.0    # 터미널 1 (출력 없음)
ros2 run latency_lab sync_listener --ros-args -p slop:=0.02        # 터미널 2
```

터미널 2의 실제 출력:

```
[INFO] [1795744321.793401842] [sync_listener]: slop=20 ms
[INFO] [1795744322.781869093] [sync_listener]: pairs=10/10 lidar msgs | mean |dt|=1.48 ms
[INFO] [1795744323.782115296] [sync_listener]: pairs=10/10 lidar msgs | mean |dt|=1.43 ms
[INFO] [1795744324.781768154] [sync_listener]: pairs=10/10 lidar msgs | mean |dt|=1.98 ms
[INFO] [1795744325.782619545] [sync_listener]: pairs=10/10 lidar msgs | mean |dt|=2.12 ms
```

jitter 20 ms, slop 1 ms로 바꾸면(`-p jitter_ms:=20.0` / `-p slop:=0.001`):

```
[INFO] [1795744329.801246686] [sync_listener]: slop=1 ms
[INFO] [1795744330.782991315] [sync_listener]: pairs=1/10 lidar msgs | mean |dt|=0.14 ms
[INFO] [1795744331.782344916] [sync_listener]: pairs=2/10 lidar msgs | mean |dt|=0.42 ms
[INFO] [1795744332.782324471] [sync_listener]: pairs=2/10 lidar msgs | mean |dt|=0.56 ms
```

### jitter × slop 표 (직접 측정)

각 조합을 10초 돌리고 시작 직후 2초를 뺀 7초(라이다 70개)를 합산했습니다.

| jitter \ slop | 1 ms | 5 ms | 20 ms | 50 ms |
|---|---|---|---|---|
| **0 ms** | 100% (0.22) | 100% (0.30) | 100% (0.27) | 100% (0.33) |
| **5 ms** | 29% (0.43) | 100% (1.70) | 100% (1.83) | 100% (1.36) |
| **20 ms** | 13% (0.46) | 41% (2.48) | 99% (6.33) | 100% (6.46) |
| **50 ms** | 6% (0.18) | 39% (2.60) | 80% (9.11) | 100% (14.16) |

칸 = 짝이 맞은 라이다 비율 (괄호: 짝들의 평균 |dt|, ms)

읽는 법:

- **slop ≥ jitter이면 거의 100%** 짝이 맞습니다. slop은 센서 시각 오차보다 커야 합니다.
- **이론값과 비교**: 두 stamp가 각각 [0, J]에서 균일하게 흔들리면, 같은 순간 카메라와의 차이가 slop(s) 미만일 확률은 `1 - (1 - s/J)²`(s < J), 평균 |dt|는 `J/3`입니다. jitter 20 ms에서 이론값은 slop 1/5/20 ms일 때 10% / 44% / 100%이고, 측정값 13% / 41% / 99%와 비슷합니다. jitter 5 ms의 평균 |dt| 이론값 1.67 ms, jitter 20 ms의 6.67 ms도 측정값과 가깝습니다.
- **jitter 0인데 |dt|가 0.2~0.3 ms인 이유**: 두 타이머 콜백이 한 executor에서 차례로 실행되며 각자 `now()`를 읽기 때문으로 보입니다(05장). 이 작은 차이 때문에 ExactTime은 짝을 못 찾습니다.
- **jitter 50 ms, slop 20 ms가 이론값(64%)보다 높은 80%인 이유**: jitter(50 ms)가 카메라 주기(33 ms)보다 커서, **바로 옆 프레임의 카메라**가 slop 안에 들어와 짝이 되었기 때문으로 보입니다. 짝 비율은 올라갔지만 그 짝은 **다른 순간의 영상**일 수 있습니다. slop을 50 ms로 키워 100%가 된 것도 마찬가지입니다. 짝 비율 100%가 "정확한 동기화"를 뜻하지 않습니다.

## 5. 실험해 보기

1. **slop과 jitter 바꾸기**: 위 표가 그 결과입니다. 원하는 칸을 골라 직접 재 보고 비교해 보세요. 실행마다 몇 % 정도는 달라질 수 있습니다.

2. **ExactTime으로 바꾸기**: 같은 구독 두 개를 `TimeSynchronizer([cam, lidar], 10)`에 연결하는 작은 스크립트로 `jitter_ms:=0.0`에서 6초 돌렸습니다.
   관찰: `ExactTime pairs=0/60 lidar msgs`. jitter가 0이어도 두 센서가 stamp를 따로 찍으니 나노초까지 같을 수 없습니다.

3. **`use_sim_time:=true`로 리스너 실행**: `ros2 run latency_lab sync_listener --ros-args -p use_sim_time:=true` (fake_sensors는 그대로).
   관찰: `slop=20 ms` 한 줄만 찍히고 **그 뒤로 아무것도 출력되지 않았습니다.** `use_sim_time`이 켜지면 노드 시계가 `/clock` 토픽을 따르는데, 아무도 `/clock`을 발행하지 않으니 시간이 0에 멈춰 1초 `report` 타이머가 한 번도 불리지 않습니다. 짝짓기 자체는 메시지 stamp만 보므로 계속 일어나고 있었을 수 있지만 확인할 방법이 없었습니다.

4. **jitter를 카메라 주기보다 크게**: `jitter_ms:=50.0`, `slop:=0.05` → 100%, 평균 |dt| 14.16 ms. 같은 순간끼리만 짝이 됐다면 평균이 약 16.7 ms(J/3)여야 하는데 더 작습니다. 더 가까운 "옆 프레임"이 골라진 경우가 섞여 있다는 뜻으로 해석했습니다.

## 6. 발표할 때 이렇게 설명하기

> "카메라는 30 Hz, 라이다는 10 Hz이고 도착 지연도 다르기 때문에, 받은 순서대로 묶으면 서로 다른 순간의 데이터가 섞입니다. 그래서 각 메시지의 header.stamp, 즉 측정 시각을 기준으로 묶는데, 서로 다른 센서의 stamp는 나노초까지 같을 수 없으니 ExactTime 대신 ApproximateTimeSynchronizer를 쓰고 '이만큼 차이까지는 같은 순간으로 본다'는 slop을 정합니다. 직접 재 보니 센서 시각 오차가 20 ms일 때 slop 1 ms면 라이다 프레임의 13%만 짝을 찾았고, slop을 20 ms로 올리니 99%가 짝을 찾았습니다. 그런데 오차가 카메라 주기보다 커지면 옆 프레임과도 짝이 되어 버려서, 짝 비율 100%가 정확한 동기화를 뜻하지는 않습니다. 결국 slop을 키우는 것보다 stamp 자체를 정확하게, 그리고 여러 PC라면 시계를 맞추는 것이 먼저입니다."

## 7. 자주 하는 실수

1. **stamp에 "받은 시각"이나 "처리 끝난 시각"을 넣는다.** 동기화와 tf2 조회가 모두 그 시각을 "측정 시각"으로 믿기 때문에, 지연만큼 틀린 결과가 나옵니다. stamp는 가능한 한 측정 순간에 가깝게 찍습니다.
2. **짝이 안 맞는다고 slop만 키운다.** 짝 비율은 오르지만 다른 순간의 데이터가 섞일 수 있습니다(jitter 50 ms 사례). 먼저 jitter를 줄일 수 있는지 봅니다.
3. **한 센서가 훨씬 늦게 오는데 `queue_size`가 작다.** 늦은 센서를 기다리는 동안 빠른 센서의 해당 메시지가 큐에서 밀려나 짝이 사라집니다.
4. **`use_sim_time` 설정이 노드마다 다르다.** stamp의 시간 기준이 달라 짝이 절대 맞지 않고, `/clock`이 없으면 타이머가 멈춥니다.
5. **여러 PC의 시계를 맞추지 않는다.** 시계 오프셋이 그대로 stamp 차이가 됩니다.

## 8. 확인 문제

1. 서로 다른 두 센서 드라이버의 메시지에 `TimeSynchronizer`(ExactTime)를 쓰면 어떻게 되나?
   <details><summary>정답</summary>stamp가 나노초까지 같을 일이 거의 없어 짝이 거의(이 데모에선 전혀) 안 맞습니다. 서로 다른 센서에는 ApproximateTimeSynchronizer를 씁니다.</details>

2. jitter 20 ms인 센서들에 slop 5 ms를 쓰면 이론상 짝이 맞는 비율은? (같은 순간끼리만 짝을 짓는다고 가정)
   <details><summary>정답</summary><code>1 - (1 - 5/20)² = 1 - 0.5625 ≈ 44%</code>. 측정값은 41%였습니다.</details>

3. slop을 50 ms로 키웠더니 짝 비율이 100%가 됐다. 문제가 없나?
   <details><summary>정답</summary>카메라 주기(33 ms)보다 slop이 크면 다른 순간에 찍힌 옆 프레임과 짝이 될 수 있습니다. 짝 비율이 아니라 "맞는 짝"인지가 중요합니다.</details>

4. `queue_size`는 무엇을 정하고, 언제 키워야 하나?
   <details><summary>정답</summary>토픽마다 짝을 기다리며 보관할 메시지 수입니다. 한 센서가 다른 센서보다 늦게 도착하거나 주기 차이가 커서, 기다리는 동안 들어오는 메시지가 많을 때 키웁니다.</details>

5. 이미지의 `header.stamp`를 넘겨 tf2에서 변환을 조회했는데 extrapolation 예외가 났다. 무슨 뜻이고 어떻게 해결하나?
   <details><summary>정답</summary>요청한 시각의 변환이 아직 버퍼에 도착하지 않았다는 뜻입니다(또는 버퍼 범위를 벗어남). timeout을 주고 기다리거나, tf2_ros MessageFilter로 변환이 준비된 메시지만 처리합니다.</details>

## 9. 더 읽을거리

- message_filters 패키지 문서 (Jazzy): https://docs.ros.org/en/jazzy/p/message_filters/
- tf2 개념: https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Tf2.html
- tf2와 시간: https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Tf2/Learning-About-Tf2-And-Time-Cpp.html
- tf2 시간 여행(과거 시각 조회): https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Tf2/Time-Travel-With-Tf2-Cpp.html
- tf2_ros MessageFilter: https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Tf2/Using-Stamped-Datatypes-With-Tf2-Ros-MessageFilter.html
- 이전 장: [06. 통신 지연 측정](06_latency.md)
