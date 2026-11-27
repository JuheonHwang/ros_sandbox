# 06. 통신 지연 측정

> 핵심 질문: 메시지는 얼마나 늦게 도착하고, 무엇이 지연을 좌우하나?

## 1. 이 장의 목표

- `header.stamp`로 단방향 지연(one-way latency)을 재는 원리와, 그것이 **같은 시계를 쓸 때만** 맞는 이유를 설명할 수 있다.
- 평균이 아니라 **p50 / p99(꼬리 지연)** 와 **유실 수**로 통신 품질을 읽을 수 있다.
- 메시지 크기, QoS(reliability, depth), 미들웨어(RMW)를 바꿔 가며 직접 측정하고, 숫자가 왜 그렇게 나오는지 해석할 수 있다.

## 2. 핵심 개념

### 지연은 여러 단계의 합이다

```
 talker 프로세스                                listener 프로세스
 ┌──────────────────────┐                      ┌────────────────────────────┐
 │ ① stamp = now()      │                      │ ④ DDS가 수신 큐(history)에 보관 │
 │ ② publish: 직렬화     │ ─── ③ DDS 전송 ───▶ │ ⑤ executor가 깨어나 콜백 선택   │
 │    (Python → C → CDR) │  (공유메모리/UDP,    │ ⑥ take + 역직렬화 → on_msg()   │
 └──────────────────────┘   조각화, 재전송)    │    지연 = now() - stamp        │
                                               └────────────────────────────┘
        측정 구간: ①에서 stamp를 찍은 순간부터 ⑥에서 콜백이 시작된 순간까지
```

- ②③⑥은 **메시지 크기**에 비례해서 커집니다(복사, 직렬화, 조각화).
- ③은 **RMW(DDS 구현체)** 와 **QoS** 에 따라 달라집니다. reliable이면 잃어버린 조각을 다시 보냅니다.
- ④⑤는 **수신 측이 바쁠 때** 커집니다. 05장에서 본 "다른 콜백이 끝나기를 기다리는 시간"이 바로 ⑤입니다.

### 같은 프로세스로 합치면?

C++(rclcpp) 노드를 Composition으로 한 프로세스에 넣고 **intra-process 통신**을 켜면, 같은 프로세스 안의 발행자→구독자 메시지는 DDS를 거치지 않고 메모리 안에서 직접 전달됩니다. 위 그림에서:

- **빠지는 것**: ② 직렬화, ③ DDS 전송, ⑥의 역직렬화. 메시지를 `std::unique_ptr`로 publish하면 복사 없이 포인터를 넘길 수도 있습니다.
- **남는 것**: ⑤ executor가 깨어나 콜백을 고르는 대기, 그리고 콜백 실행 자체. ④는 DDS 수신 큐 대신 rclcpp 내부 버퍼가 맡습니다.
- **대가**: 한 프로세스이므로 한 노드가 죽으면 같이 죽습니다([01장](01_node.md)).

rclpy에는 intra-process 통신 기능이 없습니다. 게다가 이 장의 talker와 listener는 별도 프로세스이므로, **이 장의 Python 숫자에는 ②③⑥이 항상 들어 있습니다.** C++로 같은 프로세스에서 잰 결과는 [08장](08_intra_process.md)에서 봅니다.

### 왜 같은 PC에서는 이 방법이 맞나

```
지연 = (listener 시계로 잰 수신 시각) - (talker 시계로 잰 송신 시각)
     = 진짜 지연 + (listener 시계 - talker 시계)
                    └──── 같은 PC면 0 ────┘
```

같은 PC(같은 커널)의 프로세스는 같은 시스템 시계를 읽습니다. Docker 컨테이너도 호스트 커널의 시계를 그대로 씁니다. 그래서 시계 차이가 0이고, 뺄셈 결과가 그대로 단방향 지연입니다.

**PC가 두 대면** 두 시계의 차이(offset)가 결과에 그대로 더해집니다. 시계가 5 ms 어긋나 있으면 모든 지연이 5 ms 크게(또는 작게, 심하면 음수로) 나옵니다. 그래서 여러 대에서 잴 때는:

- 시계를 맞춥니다: **chrony(NTP)** 또는 **PTP(IEEE 1588, `linuxptp`)**. 얼마나 정확히 맞는지는 네트워크와 하드웨어(하드웨어 타임스탬프 지원 NIC 여부)에 따라 다르므로, `chronyc tracking` 등으로 실제 오프셋을 확인하고 그 값을 측정 오차로 함께 적습니다.
- 또는 시계 동기화가 필요 없는 **왕복(ping-pong) 측정**을 하고 절반을 단방향 근사치로 씁니다(왕복 경로가 대칭이라는 가정이 들어감).

### 평균이 아니라 꼬리를 본다

```
지연 분포 (예)
 개수 │█
      │██
      │████
      │██████▆▃▂ ▁           ▁        ← 드물지만 아주 늦은 메시지
      └──────────────────────────────── 지연
        ↑p50                  ↑p99
```

- **p50(중앙값)**: 보통 이 정도 걸린다.
- **p99**: 100개 중 가장 늦은 1개 수준. 30 Hz 카메라라면 **약 3초에 한 번** 이만큼 늦습니다.
- 제어 루프나 센서 융합은 "보통"이 아니라 "가장 늦을 때"에 맞춰 설계해야 하므로 꼬리 지연이 중요합니다. 평균은 드문 큰 값을 희석시켜 이 문제를 숨깁니다.

## 3. 코드 읽기

소스: [`ws/src/latency_lab/latency_lab/latency.py`](../../ws/src/latency_lab/latency_lab/latency.py)

### 3-1. QoS를 파라미터로

```python
def qos_from_params(node):
    best_effort = node.declare_parameter('reliability', 'reliable').value == 'best_effort'
    return QoSProfile(
        depth=node.declare_parameter('depth', 10).value,
        reliability=ReliabilityPolicy.BEST_EFFORT if best_effort else ReliabilityPolicy.RELIABLE,
    )
```

talker와 listener가 **같은 함수**로 QoS를 만들므로, 두 노드에 같은 파라미터를 주면 같은 QoS가 됩니다. history는 기본값 KEEP_LAST이고 `depth`가 그 크기입니다. "최근 depth개까지만 보관하고, 넘치면 가장 오래된 것을 버린다"는 뜻입니다.

- **RELIABLE**: 못 받은 것을 다시 보냅니다(단, 큐에 아직 남아 있는 동안만).
- **BEST_EFFORT**: 다시 보내지 않습니다. 늦게 오느니 안 오는 게 나은 센서 데이터에 씁니다.
- 발행자 BEST_EFFORT + 구독자 RELIABLE은 **호환되지 않아 연결 자체가 안 됩니다**(실험 4). 반대 조합(발행 RELIABLE, 구독 BEST_EFFORT)은 됩니다.

### 3-2. 통계: p50 / p99

```python
def summarize(samples_ms):
    s = sorted(samples_ms)
    n = len(s)
    rank = lambda q: s[max(0, math.ceil(q * n) - 1)]  # nearest-rank 백분위수
    return {'n': n, 'mean': sum(s) / n, 'p50': rank(0.50), 'p99': rank(0.99), 'max': s[-1]}
```

정렬해서 해당 순위의 값을 꺼냅니다(nearest-rank 방식: 하위 q 비율을 덮는 가장 작은 값). **주의할 점**: 샘플이 적으면 p99는 사실상 최댓값입니다. 30 Hz의 1초 창(n=30)이면 `ceil(0.99 × 30) = 30`번째, 즉 max이고, 100 Hz(n=100)여도 99번째 값이라 max와 거의 같습니다. 그래서 아래 출력에서 p99와 max가 같거나 아주 가깝게 나옵니다. 1초 창으로는 "그 1초 동안의 최악에 가까운 값"을 보는 셈이고, 진짜 p99가 필요하면 수백~수천 개를 모아서 계산해야 합니다.

> 참고: 이 장의 측정 출력은 수정 전 코드(`s[int(n * 0.99)]`, n ≤ 100이면 항상 max)로 얻은 것입니다. 30 Hz 행은 새 코드에서도 값이 같고, 100 Hz 행의 p99는 새 코드에서 max보다 약간 작게 나올 수 있습니다.

파일 맨 아래 `if __name__ == '__main__':`에 이 함수의 자체 검사가 있습니다. `python3 /ws/src/latency_lab/latency_lab/latency.py`를 실행하면 `summarize OK`가 나옵니다(확인함).

### 3-3. Talker: 큰 메시지를 일정 주기로

```python
self.msg = Image(height=1, width=size, step=size, encoding='mono8', data=bytes(size))
...
def tick(self):
    self.seq += 1
    self.msg.header.frame_id = str(self.seq)  # 유실 계산용 일련번호
    self.msg.header.stamp = self.get_clock().now().to_msg()
    self.pub.publish(self.msg)
```

- 카메라 영상처럼 큰 payload를 흉내 내려고 `sensor_msgs/Image`를 씁니다. 1920×1080 RGB 한 장이 6,220,800 byte입니다.
- 메시지 객체를 매번 새로 만들지 않고 재사용합니다. 측정하고 싶은 건 통신이지 Python 객체 생성이 아니기 때문입니다.
- **stamp를 publish 직전에** 찍습니다. 그래서 측정 구간에 ②직렬화부터 ⑥역직렬화까지가 모두 들어갑니다.
- ROS 2의 `Header`에는 ROS 1과 달리 `seq` 필드가 없습니다. 그래서 실습용으로 `frame_id`에 일련번호를 넣었습니다. `frame_id`는 원래 좌표계 이름(`camera_link` 등)을 넣는 곳이므로 **실제 코드에서는 이렇게 쓰면 안 됩니다.**

### 3-4. Listener: 지연과 유실 계산

```python
def on_msg(self, msg):
    latency = self.get_clock().now() - Time.from_msg(msg.header.stamp)
    self.samples.append(latency.nanoseconds / 1e6)
    seq = int(msg.header.frame_id)
    if self.last_seq is not None and seq > self.last_seq + 1:
        self.lost += seq - self.last_seq - 1
    self.last_seq = seq
```

- 콜백이 **시작된 시각**에서 stamp를 뺍니다. rclpy는 콜백을 부르기 전에 역직렬화를 마치므로 ⑥까지 포함됩니다.
- 일련번호가 건너뛰면 그만큼 유실로 셉니다. 리스너를 늦게 켜도 첫 메시지 전의 번호는 세지 않습니다(`last_seq is None`). 맨 마지막에 사라진 메시지나 순서가 뒤바뀐 경우는 세지 못하는 단순한 방식입니다.
- `report()`는 1초마다 통계를 찍고 표본을 비웁니다. 이 `report` 타이머도 `on_msg`와 같은 싱글 스레드 executor에서 돌므로, 정렬하는 동안 들어온 메시지는 잠깐 기다립니다(05장의 ⑤).

### 3-5. RMW 바꾸기

코드에는 RMW 관련 내용이 전혀 없습니다. 환경 변수 `RMW_IMPLEMENTATION`이 프로세스가 시작될 때 어떤 DDS 구현체를 쓸지 정합니다. Jazzy의 기본값은 `rmw_fastrtps_cpp`(Fast DDS)이고, 이 컨테이너에는 `rmw_cyclonedds_cpp`(Cyclone DDS)도 설치되어 있습니다. **talker와 listener가 같은 RMW를 써야** 확실하게 통신됩니다.

## 4. 실행해 보기

각 터미널에서 먼저:

```bash
docker compose exec ros bash
cd /ws && colcon build --symlink-install && source install/setup.bash   # 빌드는 한 번만
```

**기본 측정 (1 KB, 100 Hz)**

```bash
ros2 run latency_lab listener                                          # 터미널 1
ros2 run latency_lab talker --ros-args -p size:=1024 -p rate:=100.0    # 터미널 2
```

터미널 1의 실제 출력(Fast DDS, 일부):

```
[INFO] [1795743935.415783302] [latency_listener]: n=100 lost=0 | latency ms: mean=0.417 p50=0.334 p99=0.925 max=0.925
[INFO] [1795743936.415639215] [latency_listener]: n=100 lost=0 | latency ms: mean=0.357 p50=0.307 p99=0.836 max=0.836
[INFO] [1795743937.415666181] [latency_listener]: n=100 lost=0 | latency ms: mean=0.366 p50=0.330 p99=0.874 max=0.874
[INFO] [1795743938.415770772] [latency_listener]: n=100 lost=0 | latency ms: mean=0.338 p50=0.310 p99=0.597 max=0.597
```

**크기와 QoS 바꾸기** (두 노드에 같은 QoS 파라미터를 줍니다)

```bash
# 1 MB
ros2 run latency_lab listener
ros2 run latency_lab talker --ros-args -p size:=1048576 -p rate:=30.0
# 1920x1080 RGB 한 장 (약 6 MB)
ros2 run latency_lab listener
ros2 run latency_lab talker --ros-args -p size:=6220800 -p rate:=30.0
# 6 MB + best_effort
ros2 run latency_lab listener --ros-args -p reliability:=best_effort
ros2 run latency_lab talker   --ros-args -p size:=6220800 -p rate:=30.0 -p reliability:=best_effort
```

**RMW 바꾸기**: 두 터미널 모두에서 노드 실행 전에

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

**내 측정 결과** (64코어 서버, Docker 컨테이너 1개 안, Python, 서버 load average 약 28로 다른 작업이 돌고 있던 상태. 각 조건 6초 = 1초 창 6개의 범위. 위 설명대로 이 창 크기에선 p99 = 그 1초의 max)

| 조건 | RMW | p50 (ms) | p99=max (ms) | 유실 |
|---|---|---|---|---|
| 1 KB, 100 Hz | Fast DDS | 0.31 ~ 0.33 | 0.60 ~ 0.97 | 0 |
| 1 KB, 100 Hz | Cyclone DDS | 0.26 ~ 0.28 | 0.64 ~ 0.84 | 0 |
| 1 MB, 30 Hz | Fast DDS | 3.5 ~ 4.2 | 13.6 ~ 15.4 | 0 |
| 1 MB, 30 Hz | Cyclone DDS | 4.4 ~ 5.5 | 6.8 ~ 74 | 0 |
| 6 MB, 30 Hz (3회) | Fast DDS | 14 ~ 24 | 23 ~ 128 (대부분 25 ~ 37) | 0 |
| 6 MB, 30 Hz (3회) | Cyclone DDS | 19 ~ 297 | 29 ~ 338 | 0 ~ 20개 / 6초 |
| 6 MB, 30 Hz, best_effort | Fast DDS | 13.6 ~ 15.4 | 15.7 ~ 17.0 | 78 / 181 (43%) |
| 6 MB, 30 Hz, best_effort | Cyclone DDS | 16.5 ~ 20.3 | 20.3 ~ 22.2 | 123 / 184 (67%) |

같은 서버에서 이전에 측정한 참고값(p50 / p99, ms): 1 KB Fast DDS 0.33 / 0.9, Cyclone 0.28 / 0.9 · 1 MB 3.7 / 15 · 6 MB Fast DDS 24 / 37, Cyclone 20 / 90~130 · 6 MB best_effort 약 70% 유실. 1 KB, 1 MB, 6 MB Fast DDS는 이번과 거의 같고, **6 MB Cyclone은 실행할 때마다 크게 흔들렸습니다.**

6 MB Cyclone reliable에서 가장 나빴던 구간(실제 출력):

```
[latency_listener]: n=21 lost=11 | latency ms: mean=288.573 p50=297.055 p99=337.685 max=337.685
[latency_listener]: n=30 lost=4 | latency ms: mean=231.377 p50=239.274 p99=334.154 max=334.154
```

해석:

- **크기**: 1 KB → 1 MB → 6 MB로 p50이 약 0.3 → 4 → 15~24 ms로 커졌습니다. 이 범위에선 크기가 지연을 지배합니다.
- **reliable인데 유실(lost)이 생긴 이유**: QoS가 RELIABLE이어도 history가 **KEEP_LAST, depth 10**이면 큐가 넘칠 때 가장 오래된 메시지를 버립니다. 최댓값이 약 335 ms에서 멈춘 것은 "30 Hz × 10개 = 약 333 ms 분량이 큐에 쌓였다"는 해석과 맞습니다. 다만 어느 쪽(송신/수신) 큐에서 버려졌는지는 이 실험으로 확인하지 않았습니다.
- **best_effort가 reliable보다 지연이 작게 나온 이유**: 늦어질 메시지가 **버려졌기 때문**입니다. 살아남은 메시지만 통계에 들어갑니다(생존자 편향). best_effort의 지연은 반드시 유실률과 함께 읽어야 합니다.
- **Fast DDS와 Cyclone DDS의 차이**: Fast DDS는 같은 호스트의 프로세스끼리 기본으로 공유 메모리 전송을 쓰고, Cyclone DDS는 별도 설정이 없으면 UDP(loopback)를 씁니다. 큰 메시지에서의 차이가 이것 때문일 가능성이 있지만, **이 실험에서 원인을 검증하지는 않았습니다.** RMW 비교 결과는 설정(XML), 메시지 크기, 머신에 따라 바뀌므로 "어느 RMW가 더 빠르다"는 일반 결론을 내리면 안 됩니다.

**내장 도구와 비교** — talker를 켠 채로 터미널 3에서:

```bash
ros2 topic delay /latency_test
ros2 topic hz /latency_test
ros2 topic info -v /latency_test
```

1 KB, 100 Hz일 때 실제 출력(일부):

```
$ ros2 topic delay /latency_test
average delay: 0.000
	min: 0.000s max: 0.001s std dev: 0.00016s window: 499

$ ros2 topic hz /latency_test
average rate: 99.998
	min: 0.009s max: 0.011s std dev: 0.00026s window: 504

$ ros2 topic info -v /latency_test     (구독자 부분만)
Node name: _ros2cli_5149
...
QoS profile:
  Reliability: BEST_EFFORT
```

6 MB, 30 Hz일 때:

```
$ ros2 topic delay /latency_test
average delay: 0.016
	min: 0.012s max: 0.022s std dev: 0.00168s window: 114

$ ros2 topic hz /latency_test
average rate: 16.799
	min: 0.026s max: 0.528s std dev: 0.06176s window: 112
```

- `ros2 topic delay`도 우리 listener와 같은 방식(`now - header.stamp`)입니다. 다만 **ms 단위로 반올림**해 보여 주므로 1 KB처럼 1 ms 미만인 지연은 `0.000`으로만 보입니다.
- `ros2 topic info -v`를 보면 CLI 도구들은 **BEST_EFFORT로 구독**합니다. 그래서 6 MB에서 `hz`가 30이 아니라 16.8로 나왔습니다. talker는 30 Hz로 보내고 있었고, 도구가 받은 만큼만 센 것입니다(위 표의 best_effort 유실률과 같은 현상으로 보입니다). **측정 도구도 하나의 구독자이고, 측정 대상에 부하를 더한다**는 것을 기억하세요.

### Python 오버헤드에 대해

이 장의 모든 숫자는 **Python(rclpy) 노드**로 잰 것입니다. rclpy에서는 ② publish 때 Python 메시지 객체를 C 구조체로 변환하고, ⑥ 수신 때 다시 Python 객체로 변환하는 복사가 추가로 들어갑니다. 또 executor 루프 자체가 Python이고 GIL의 영향을 받습니다(05장). 그래서 C++(rclcpp) 노드보다 느릴 것으로 예상하지만, **이 저장소에서 C++로 같은 측정을 하지는 않았으므로 몇 배 차이인지는 말할 수 없습니다.** 숫자를 비교할 때는 언어, RMW, 메시지 크기, 머신 부하를 함께 적어야 합니다.

## 5. 실험해 보기

1. **크기 키우기** (위 표): 1 KB → 6 MB에서 p50이 약 0.3 ms → 15~24 ms. 6 MB에서는 p99가 창마다 크게 달라졌습니다(Fast DDS 23~128 ms). 큰 메시지일수록 꼬리가 길어집니다.

2. **best_effort**: 6 MB에서 Fast DDS 43%, Cyclone DDS 67%가 유실됐습니다(이전 측정은 약 70%). 지연 숫자는 오히려 작아졌는데, 늦을 메시지가 버려졌기 때문입니다.

3. **depth 바꾸기** (Cyclone DDS, 6 MB, reliable, 두 노드 모두 `-p depth:=N`):
   - `depth:=1` → p99 25.9 ~ 32.6 ms로 한 주기(33 ms) 근처에 묶였지만, 154개 받고 **25개 유실(약 14%)**. 큐에 하나만 두니 오래 기다리는 메시지가 없는 대신 밀리면 버려집니다.
   - `depth:=30` → 유실 0, p99 32 ~ 158 ms. 이번 실행에서는 300 ms대 스파이크가 나오지 않았습니다. 6 MB Cyclone은 실행마다 편차가 커서 depth 10과의 차이를 결론 내리려면 더 여러 번 반복해야 합니다.
   - 같은 `depth:=1`을 Fast DDS에서 하면 유실 0, p99 25 ~ 47 ms였습니다. 수신 측이 따라가는 동안에는 depth가 작아도 버릴 일이 없습니다.
   - 정리: **depth는 "지연 상한"과 "유실"을 맞바꾸는 손잡이**입니다. 최신 영상만 필요하면 작게, 하나도 놓치면 안 되면 크게(대신 밀리면 지연이 쌓임).

4. **QoS 불일치**: talker만 `-p reliability:=best_effort`, listener는 기본(reliable).
   관찰(실제 출력):
   ```
   [WARN] [latency_listener]: New publisher discovered on topic 'latency_test', offering incompatible QoS. No messages will be received from it. Last incompatible policy: RELIABILITY
   [INFO] [latency_listener]: waiting for messages...
   ```
   talker 쪽에도 `requesting incompatible QoS. No messages will be sent to it.` 경고가 찍히고 메시지는 하나도 오지 않았습니다. 에러로 종료되지 않으므로 경고를 놓치기 쉽습니다.

## 6. 발표할 때 이렇게 설명하기

> "보낼 때 메시지 header.stamp에 현재 시각을 넣고, 받은 쪽에서 현재 시각에서 빼면 단방향 지연이 나옵니다. 같은 PC에서는 두 프로세스가 같은 시계를 보니까 이게 정확하지만, PC가 두 대면 시계 차이가 그대로 지연에 더해지기 때문에 chrony나 PTP로 시계를 먼저 맞춰야 합니다. 이 서버에서 Python 노드로 재 보니 1 KB는 0.3 ms 정도인데, 1080p 영상 한 장 크기인 6 MB는 15~24 ms였고, 꼬리 지연은 실행마다 수십에서 수백 ms까지 흔들렸습니다. 그래서 평균이 아니라 p99 같은 꼬리와 유실을 같이 봐야 합니다. 특히 best_effort로 바꾸면 지연이 줄어든 것처럼 보이는데, 사실은 늦을 메시지가 40~70% 버려진 결과였습니다."

## 7. 자주 하는 실수

1. **두 PC 사이에서 시계를 안 맞추고 `now - stamp`를 잰다.** 결과에 시계 오프셋이 그대로 섞여, 음수 지연이 나오기도 합니다.
2. **샘플 100개 이하로 p99를 말한다.** 이 코드에선 그 경우 p99 = max입니다. 꼬리를 말하려면 충분히 오래 모으세요.
3. **best_effort의 지연만 보고 "더 빠르다"고 결론 낸다.** 유실률을 같이 보지 않으면 생존자 편향에 속습니다.
4. **reliable이면 절대 안 잃어버린다고 생각한다.** KEEP_LAST + depth가 작으면 수신 측이 밀릴 때 버려집니다(6 MB Cyclone에서 실제로 발생).
5. **talker와 listener의 QoS나 RMW를 다르게 실행한다.** 경고만 찍히고 아무것도 안 옵니다. 터미널마다 `export`를 다시 해야 한다는 것도 잊기 쉽습니다.

## 8. 확인 문제

1. 같은 PC에서는 `now() - header.stamp`가 단방향 지연이 되는데, PC 두 대에서는 왜 안 되나?
   <details><summary>정답</summary>stamp는 송신 PC의 시계, now()는 수신 PC의 시계로 잰 값이라 두 시계의 차이(offset)가 결과에 더해집니다. chrony/PTP로 시계를 맞추고 그 오차를 함께 적거나, 왕복 측정으로 우회해야 합니다.</details>

2. 이 코드에서 30 Hz로 1초 창을 쓰면 p99와 max가 항상 같은 이유는?
   <details><summary>정답</summary>nearest-rank로 n=30이면 <code>ceil(0.99 × 30) = 30</code>번째, 즉 정렬된 배열의 마지막 값(max)입니다. 1%보다 촘촘한 꼬리를 보려면 최소 100개 이상, 안정적으로는 수천 개의 샘플이 필요합니다.</details>

3. 6 MB에서 best_effort의 p50이 reliable보다 작게 나왔다. best_effort가 더 좋은 설정인가?
   <details><summary>정답</summary>아닙니다. 43~67%의 메시지가 유실되었고, 늦게 도착했을 메시지가 버려져서 살아남은 메시지만 측정된 결과(생존자 편향)입니다. "최신 것만 있으면 된다"는 용도에서만 의미가 있습니다.</details>

4. RELIABLE QoS인데 `lost`가 0이 아니었다. 어떻게 가능한가?
   <details><summary>정답</summary>history가 KEEP_LAST(depth 10)이면 큐가 가득 찼을 때 가장 오래된 메시지가 덮어써집니다. 수신 측이 처리 속도를 못 따라가면 reliable이어도 유실됩니다.</details>

5. 미들웨어를 Cyclone DDS로 바꾸려면 코드를 어떻게 고쳐야 하나?
   <details><summary>정답</summary>코드는 고치지 않습니다. 노드를 실행하기 전에 <code>export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp</code>를 설정하고, 통신하는 모든 노드에 똑같이 적용합니다.</details>

## 9. 더 읽을거리

- QoS 설정: https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html
- 미들웨어(RMW) 구현체: https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Different-Middleware-Vendors.html
- 여러 RMW 함께 쓰기: https://docs.ros.org/en/jazzy/How-To-Guides/Working-with-multiple-RMW-implementations.html
- DDS 튜닝(큰 메시지, 네트워크 버퍼): https://docs.ros.org/en/jazzy/How-To-Guides/DDS-tuning.html
- 토픽 통계(Topic Statistics): https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Topic-Statistics.html
- Composition 개념: https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Composition.html
- Intra-process 통신 데모(C++): https://docs.ros.org/en/jazzy/Tutorials/Demos/Intra-Process-Communication.html
- ros2_tracing 튜토리얼(콜백·통신 구간을 추적): https://docs.ros.org/en/jazzy/Tutorials/Advanced/ROS2-Tracing-Trace-and-Analyze.html
- ros2_tracing 저장소: https://github.com/ros2/ros2_tracing
- CARET (ros2_tracing 기반 end-to-end 지연 분석 도구): https://tier4.github.io/caret_doc/latest/
- 이전 장: [05. Executor와 콜백 그룹](05_executor.md) — ⑤단계의 대기를 직접 재 봤습니다.
