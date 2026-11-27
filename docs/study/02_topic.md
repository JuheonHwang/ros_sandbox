# 02. 토픽 (Topic)

## 이 장의 목표

- 발행/구독(pub/sub) 모델을 설명하고, 토픽이 연결되려면 이름 · 타입 · QoS가 맞아야 한다는 것을 안다.
- 메시지 타입이 어디서 오는지(`.msg` 파일) 알고, talker/listener 코드를 읽을 수 있다.
- `ros2 topic list / echo / info / hz / pub`과 remapping으로 토픽을 관찰하고 바꿀 수 있다.

## 핵심 개념

### 발행/구독 = 게시판 방식

토픽은 이름이 붙은 **단방향 데이터 통로**입니다. 보내는 노드(publisher)는 토픽에 메시지를 올려 두기만 하고, 누가 받는지 모릅니다. 받는 노드(subscriber)도 누가 보냈는지 신경 쓰지 않고 그 토픽을 구독할 뿐입니다. 둘을 이어 주는 것은 **토픽 이름**입니다.

```
                         토픽 /chatter  (타입: std_msgs/msg/String)
  ┌──────────┐ publish  ┌─────────────────┐  콜백 호출   ┌────────────┐
  │ /talker  │ ───────▶ │                 │ ─────────▶ │ /listener  │
  └──────────┘          │   "Hello #3"    │            └────────────┘
  ┌──────────────┐      │                 │ ─────────▶ ┌────────────┐
  │ ros2 topic   │ ───▶ │                 │            │ /listener2 │
  │ pub (CLI)    │      └─────────────────┘            └────────────┘
  └──────────────┘
   N개의 발행자  ───────────────────────────────▶  M개의 구독자 (N:M)
```

- **느슨한 연결**: talker는 listener가 몇 개인지, 아예 없는지 모릅니다. 받는 쪽이 없어도 `publish()`는 에러 없이 끝납니다. 그래서 노드를 독립적으로 만들고 바꿔 끼울 수 있습니다.
- **N:M**: 한 토픽에 발행자도 구독자도 여러 개 붙을 수 있습니다. 구독자가 둘이면 같은 메시지가 둘 모두에게 복사되어 갑니다.
- **중앙 서버가 없음**: ROS 1의 roscore 같은 중개자가 없습니다. 노드들이 DDS 미들웨어를 통해 서로를 직접 발견(discovery)하고 직접 데이터를 주고받습니다.

### 연결되려면 세 가지가 맞아야 한다

| 항목 | 예 | 안 맞으면 |
|---|---|---|
| 토픽 이름 | `/chatter` | 서로 다른 토픽이므로 아무 일도 없음 (에러도 없음) |
| 메시지 타입 | `std_msgs/msg/String` | 이름이 같아도 연결되지 않음 (에러 없이 조용히) |
| QoS | reliable / volatile ... | 호환되지 않으면 연결되지 않음 ([03장](03_qos.md)) |

세 경우 모두 **에러가 나지 않고 그냥 메시지가 안 옵니다.** 그래서 "왜 안 오지?" 할 때 `ros2 topic info -v`로 이 세 가지를 확인하는 습관이 중요합니다.

### 메시지 타입과 `.msg` 파일

메시지 타입은 `패키지/msg/이름` 형식입니다. `std_msgs/msg/String`은 `std_msgs` 패키지의 `msg/String.msg` 파일에 정의되어 있고, 내용은 `string data` 한 줄입니다. 빌드할 때 이 `.msg` 파일에서 파이썬 클래스(`from std_msgs.msg import String`)와 C++ 헤더가 자동 생성됩니다. 그래서 파이썬 노드와 C++ 노드가 같은 타입으로 대화할 수 있습니다. 직접 `.msg`를 만들어 새 타입을 정의할 수도 있습니다.

### 큐 깊이(depth)

`create_publisher(String, 'chatter', 10)`의 `10`은 QoS의 history depth입니다. "최근 메시지를 최대 몇 개까지 보관할지"를 뜻합니다.

- **발행 쪽**: 아직 상대에게 전달이 확인되지 않은 메시지를 보관하는 칸 수입니다.
- **구독 쪽**: 도착했지만 아직 콜백으로 꺼내 처리하지 못한 메시지를 쌓아 두는 칸 수입니다. 콜백이 느려서 10개가 넘게 밀리면 **가장 오래된 것부터 버려집니다**(KEEP_LAST).

즉 depth는 "느린 쪽을 얼마나 기다려 줄지"이고, 클수록 메모리를 더 쓰고 오래된 데이터가 남을 수 있습니다. 센서 데이터처럼 최신 값만 중요하면 작게, 명령처럼 하나도 빠지면 안 되면 크게 잡습니다.

## 코드 읽기

소스: [`ws/src/ros2_study/ros2_study/topic_demo.py`](../../ws/src/ros2_study/ros2_study/topic_demo.py)

파일 하나에 `Talker`, `Listener` 두 노드가 있고, `setup.py`의 entry point가 `talker()` → `topic_talker`, `listener()` → `topic_listener` 명령으로 연결합니다.

### 1) 발행자 만들기

```python
self.declare_parameter('rate', 2.0)  # 초당 발행 횟수(Hz)
rate = self.get_parameter('rate').value

self.pub = self.create_publisher(String, 'chatter', 10)
self.timer = self.create_timer(1.0 / rate, self.on_timer)
```

- `create_publisher(메시지 타입, 토픽 이름, QoS)`. QoS 자리에 숫자만 주면 "depth=10, 나머지는 기본값(reliable, volatile)"이라는 뜻입니다.
- 토픽 이름 `'chatter'`는 `/`로 시작하지 않는 **상대 이름**입니다. 노드의 네임스페이스 아래에 붙으므로 기본으로는 `/chatter`, `__ns:=/robot1`로 띄우면 `/robot1/chatter`가 됩니다.
- 발행 주기는 01장에서 배운 파라미터로 받습니다(이번에는 시작할 때 한 번만 읽습니다).

### 2) 메시지 채워서 보내기

```python
def on_timer(self):
    msg = String()
    msg.data = f'Hello ROS 2 #{self.count}'
    self.pub.publish(msg)
```

메시지는 `.msg` 파일에서 생성된 보통의 파이썬 객체입니다. 객체를 만들고 필드(`data`)를 채운 뒤 `publish()`에 넘깁니다. 필드 이름이 궁금하면 `ros2 interface show std_msgs/msg/String`으로 확인합니다.

### 3) 구독자 만들기

```python
self.sub = self.create_subscription(String, 'chatter', self.on_msg, 10)

def on_msg(self, msg: String):
    self.get_logger().info(f'받음: "{msg.data}"')
```

- `create_subscription(타입, 토픽 이름, 콜백, QoS)`. 타입과 이름이 talker와 같아야 연결됩니다.
- 메시지가 도착하면 `spin()`이 `on_msg`를 불러 줍니다. 구독 쪽에는 "메시지를 읽는 함수"가 없고, 오직 콜백으로만 받는다는 점이 중요합니다.

### 4) 실행 부분

```python
def _run(node_cls):
    rclpy.init()
    node = node_cls()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
```

01장의 `main()`과 같은 init → spin → 정리 패턴을 두 노드가 함께 씁니다.

## 실행해 보기

모든 터미널에서 먼저 컨테이너 셸에 들어갑니다(호스트의 저장소 폴더에서).

```bash
docker compose exec ros bash
```

**터미널 1** — 빌드하고 talker 실행

```bash
cd /ws && colcon build --symlink-install --packages-select ros2_study && source install/setup.bash
ros2 run ros2_study topic_talker
```

```text
[INFO] [1795743894.593549161] [talker]: 보냄: "Hello ROS 2 #0"
[INFO] [1795743895.078641785] [talker]: 보냄: "Hello ROS 2 #1"
[INFO] [1795743895.578613961] [talker]: 보냄: "Hello ROS 2 #2"
[INFO] [1795743896.077689988] [talker]: 보냄: "Hello ROS 2 #3"
```

**터미널 2** — listener 실행

```bash
source /ws/install/setup.bash
ros2 run ros2_study topic_listener
```

```text
[INFO] [1795743894.593532773] [listener]: 받음: "Hello ROS 2 #0"
[INFO] [1795743895.079352866] [listener]: 받음: "Hello ROS 2 #1"
[INFO] [1795743895.579133218] [listener]: 받음: "Hello ROS 2 #2"
[INFO] [1795743896.078943470] [listener]: 받음: "Hello ROS 2 #3"
```

0.5초(기본 rate 2.0 Hz)마다 보내고 받습니다.

**터미널 3** — CLI로 관찰하기

```bash
source /ws/install/setup.bash
ros2 topic list -t
```

```text
/chatter [std_msgs/msg/String]
/parameter_events [rcl_interfaces/msg/ParameterEvent]
/rosout [rcl_interfaces/msg/Log]
```

`-t`를 붙이면 타입까지 보입니다. `/parameter_events`, `/rosout`은 모든 노드가 기본으로 쓰는 토픽입니다(01장).

```bash
ros2 topic echo /chatter      # Ctrl+C로 종료
```

```text
data: 'Hello ROS 2 #8'
---
data: 'Hello ROS 2 #9'
---
```

`echo`는 임시 구독자를 하나 만들어서 받은 메시지를 출력합니다. 즉 CLI도 하나의 노드입니다.

```bash
ros2 topic info -v /chatter
```

```text
Type: std_msgs/msg/String

Publisher count: 1

Node name: talker
Node namespace: /
Topic type: std_msgs/msg/String
...
Endpoint type: PUBLISHER
...
QoS profile:
  Reliability: RELIABLE
  History (Depth): UNKNOWN
  Durability: VOLATILE
  ...

Subscription count: 1

Node name: listener
Node namespace: /
Topic type: std_msgs/msg/String
...
Endpoint type: SUBSCRIPTION
...
QoS profile:
  Reliability: RELIABLE
  History (Depth): UNKNOWN
  Durability: VOLATILE
  ...
```

누가 발행하고 누가 구독하는지, 각자의 타입과 QoS가 보입니다. "메시지가 안 와요" 할 때 가장 먼저 볼 명령입니다. Depth가 `UNKNOWN`인 것은 depth가 각자 내부 설정이라 다른 노드에게 알려지지 않기 때문입니다(연결 여부에도 영향을 주지 않습니다).

```bash
ros2 topic hz /chatter        # Ctrl+C로 종료
```

```text
average rate: 2.000
	min: 0.500s max: 0.500s std dev: 0.00021s window: 4
```

실제 발행 주기를 측정합니다. 파라미터로 준 rate가 정말 지켜지는지 확인할 때 씁니다.

**메시지 타입 살펴보기** — 노드가 없어도 됩니다.

```bash
ros2 interface show std_msgs/msg/String
```

```text
# This was originally provided as an example message.
# It is deprecated as of Foxy
# It is recommended to create your own semantically meaningful message.
# However if you would like to continue using this please use the equivalent in example_msgs.

string data
```

주석대로 `std_msgs/String`은 예제용입니다. 실제 프로젝트에서는 의미가 드러나는 타입(예: `sensor_msgs/msg/Image`)이나 직접 만든 타입을 씁니다. `.msg` 파일이 실제로 어디 있는지도 볼 수 있습니다.

```bash
ros2 interface package std_msgs | sort | head -5
ls /opt/ros/jazzy/share/std_msgs/msg/ | head -5
```

```text
std_msgs/msg/Bool
std_msgs/msg/Byte
std_msgs/msg/ByteMultiArray
std_msgs/msg/Char
std_msgs/msg/ColorRGBA
Bool.idl
Bool.json
Bool.msg
Byte.idl
Byte.json
```

**CLI로 직접 발행하기** — talker를 끄고(Ctrl+C) listener만 켜 둔 상태에서:

```bash
ros2 topic pub --times 3 /chatter std_msgs/msg/String "{data: 직접 보낸 메시지}"
```

```text
publisher: beginning loop
publishing #1: std_msgs.msg.String(data='직접 보낸 메시지')

publishing #2: std_msgs.msg.String(data='직접 보낸 메시지')

publishing #3: std_msgs.msg.String(data='직접 보낸 메시지')

```

listener 터미널:

```text
[INFO] [1795743678.870868901] [listener]: 받음: "직접 보낸 메시지"
[INFO] [1795743679.860567502] [listener]: 받음: "직접 보낸 메시지"
[INFO] [1795743680.861438297] [listener]: 받음: "직접 보낸 메시지"
```

listener는 보낸 쪽이 talker인지 CLI인지 모르고, 알 필요도 없습니다. 이것이 pub/sub의 느슨한 연결입니다. 메시지 내용은 YAML 형식으로 적고, 빈 틀은 `ros2 interface proto std_msgs/msg/String`으로 얻을 수 있습니다(출력: `"data: ''"`).

**rqt_graph** — 노드와 토픽의 연결을 그림으로 보여 주는 GUI 도구입니다. 화면이 있는 환경이면 `rqt_graph`로 실행합니다. 이 저장소를 돌린 원격 서버처럼 화면이 없는 곳에서는 창을 띄울 수 없어 Qt 플랫폼 플러그인 오류(`Available platform plugins are: ...`)로 끝납니다. 그럴 때는 `ros2 node info`, `ros2 topic info -v`로 같은 정보를 글로 확인합니다.

## 실험해 보기

### 1. listener를 두 개 띄우기 (1:N)

talker를 켠 상태에서 터미널을 하나 더 열고, 이름이 겹치지 않게 두 번째 listener를 띄웁니다.

```bash
ros2 run ros2_study topic_listener --ros-args -r __node:=listener2
```

```text
[INFO] [1795743639.772408330] [listener2]: 받음: "Hello ROS 2 #0"
[INFO] [1795743640.247363231] [listener2]: 받음: "Hello ROS 2 #1"
[INFO] [1795743640.747624409] [listener2]: 받음: "Hello ROS 2 #2"
```

첫 번째 listener도 같은 번호를 똑같이 받았습니다. 이때 `ros2 topic info -v /chatter`는 `Subscription count: 2`와 함께 `listener`, `listener2`를 모두 보여 줍니다. talker 코드는 한 줄도 바뀌지 않았습니다.

### 2. 토픽 이름 바꾸기 (remapping)

listener 쪽만 토픽을 바꿔 봅니다.

```bash
ros2 run ros2_study topic_listener --ros-args -r chatter:=other
```

listener는 아무것도 출력하지 않았습니다(받은 줄 0개). 이때 토픽 목록을 보면 이름이 갈라져 있습니다.

```text
$ ros2 topic list
/chatter
/other
/parameter_events
/rosout
```

talker도 같이 바꾸고, rate 파라미터도 함께 줘 봅니다.

```bash
ros2 run ros2_study topic_talker --ros-args -r chatter:=other -p rate:=5.0
ros2 run ros2_study topic_listener --ros-args -r chatter:=other
ros2 topic hz /other
```

```text
average rate: 5.002
	min: 0.200s max: 0.200s std dev: 0.00022s window: 6
```

다시 연결되고 5 Hz로 받습니다. 코드에 `'chatter'`라고 적어 두고, 실제로 어떤 토픽에 붙을지는 실행할 때 정할 수 있다는 점이 remapping의 핵심입니다.

### 3. 이름은 같고 타입이 다르면?

listener를 켜 두고, 같은 `/chatter`에 `Int32` 타입으로 발행합니다.

```bash
ros2 topic pub -r 2 /chatter std_msgs/msg/Int32 "{data: 7}"
```

listener는 아무것도 출력하지 않았습니다. 에러도 없습니다. 토픽 목록에서는 한 이름에 타입이 두 개 붙은 것이 보입니다.

```text
$ ros2 topic list -t
/chatter [std_msgs/msg/Int32, std_msgs/msg/String]
$ ros2 topic info /chatter
Type: ['std_msgs/msg/Int32', 'std_msgs/msg/String']
Publisher count: 1
Subscription count: 1
```

`Type`이 두 개로 나오면 누군가 타입을 잘못 쓰고 있다는 신호입니다.

### 4. listener를 늦게 켜면 지난 메시지를 받을까?

talker를 먼저 켜고 3초쯤 기다렸다가 listener를 켭니다.

```text
[INFO] [1795743710.974733842] [listener]: 받음: "Hello ROS 2 #5"
[INFO] [1795743711.317243842] [listener]: 받음: "Hello ROS 2 #6"
```

#0~#4는 받지 못하고 #5부터 받았습니다. 기본 QoS의 Durability가 `VOLATILE`이라서, 구독자가 생기기 전에 보낸 메시지는 새 구독자에게 다시 보내 주지 않습니다. 반대로 listener를 먼저 켜 두고 talker를 켜면 #0부터 받았습니다. 늦게 온 구독자에게도 마지막 값을 주고 싶다면 `TRANSIENT_LOCAL`을 씁니다([03장](03_qos.md)).

## 발표할 때 이렇게 설명하기

> 토픽은 이름이 붙은 단방향 데이터 통로이고, 발행자는 토픽에 메시지를 올리기만 하고 구독자는 그 토픽을 구독해서 콜백으로 받습니다. 발행자와 구독자는 서로를 모르기 때문에, 구독자를 하나 더 붙이거나 CLI로 대신 발행해도 기존 코드는 바뀌지 않습니다. 연결되려면 토픽 이름, 메시지 타입, QoS 세 가지가 맞아야 하는데, 하나라도 다르면 에러 없이 그냥 메시지가 안 오기 때문에 `ros2 topic info -v`로 확인하는 습관이 중요합니다. 메시지 타입은 `.msg` 파일로 정의되고 빌드할 때 파이썬과 C++ 코드가 생성되어 언어가 달라도 같은 데이터를 주고받을 수 있습니다. 큐 깊이는 처리가 밀렸을 때 몇 개까지 쌓아 둘지이고, 넘치면 오래된 것부터 버립니다. 마지막으로 remapping을 쓰면 코드를 고치지 않고 실행할 때 토픽 이름을 바꿔 다른 노드와 연결할 수 있습니다.

## 자주 하는 실수

1. **토픽 이름 오타나 `/` 유무 차이.** `chatter`와 `/chatter`는 네임스페이스가 없을 때는 같지만, `__ns:=/robot1`로 띄우면 `chatter`만 `/robot1/chatter`로 바뀝니다. 에러가 없으니 `ros2 topic list`로 실제 이름을 확인하세요.
2. **타입이 다른데 이름만 같게 맞춘다.** 실험 3처럼 조용히 아무것도 안 옵니다. `ros2 topic list -t`에서 한 토픽에 타입이 두 개 보이면 의심하세요.
3. **늦게 켠 구독자가 처음 메시지를 받을 거라 기대한다.** 기본 QoS(VOLATILE)에서는 구독 전에 보낸 메시지는 받지 못합니다. 지도·설정값처럼 한 번만 보내는 데이터는 QoS를 바꿔야 합니다.
4. **`ros2 topic echo`가 안 나오면 talker가 고장 났다고 생각한다.** echo도 하나의 구독자이므로 같은 이름·타입·QoS 규칙을 따릅니다. 먼저 `ros2 topic info -v`로 발행자가 있는지, QoS가 맞는지 보세요.
5. **구독 콜백에서 무거운 일을 한다.** 콜백이 느리면 구독 큐(depth)가 차서 오래된 메시지가 버려집니다. 무거운 일은 분리하거나 executor 구성을 바꿉니다([05장](05_executor.md)).

## 확인 문제

**Q1.** talker는 켜져 있는데 listener가 아무것도 받지 못합니다. 확인할 세 가지는?

<details><summary>정답</summary>

토픽 이름, 메시지 타입, QoS 호환성입니다. `ros2 topic list -t`와 `ros2 topic info -v /토픽이름`으로 발행자·구독자가 같은 토픽에 같은 타입으로 붙어 있는지, QoS가 호환되는지 봅니다.
</details>

**Q2.** 구독자가 하나도 없을 때 `self.pub.publish(msg)`를 부르면 어떻게 되나요?

<details><summary>정답</summary>

에러 없이 그냥 끝납니다. 발행자는 구독자가 있는지 신경 쓰지 않습니다(느슨한 연결).
</details>

**Q3.** `create_subscription(String, 'chatter', self.on_msg, 10)`에서 10의 의미는? 콜백이 너무 느려서 메시지가 15개 밀리면?

<details><summary>정답</summary>

QoS history depth(큐 깊이)입니다. 처리하지 못한 메시지를 최대 10개까지 보관하고, 넘치면 가장 오래된 메시지부터 버립니다(KEEP_LAST). 15개가 밀리면 오래된 5개는 버려집니다.
</details>

**Q4.** 코드 수정 없이 talker가 `/robot1/chatter`로 발행하게 하는 방법 두 가지는?

<details><summary>정답</summary>

1. 토픽 remapping: `ros2 run ros2_study topic_talker --ros-args -r chatter:=/robot1/chatter`
2. 네임스페이스 지정: `ros2 run ros2_study topic_talker --ros-args -r __ns:=/robot1` (코드의 토픽 이름이 `/`로 시작하지 않는 상대 이름이라 가능)
</details>

**Q5.** `from std_msgs.msg import String`의 `String` 클래스는 누가 만들었나요?

<details><summary>정답</summary>

`std_msgs` 패키지의 `msg/String.msg` 파일(`string data`)로부터 빌드할 때 자동 생성된 코드입니다. 같은 `.msg`에서 C++ 코드도 생성되므로 언어가 달라도 같은 타입으로 통신할 수 있습니다.
</details>

## 더 읽을거리

- [Concepts: Topics](https://docs.ros.org/en/jazzy/Concepts/Basic/About-Topics.html)
- [Concepts: Interfaces (msg, srv, action)](https://docs.ros.org/en/jazzy/Concepts/Basic/About-Interfaces.html)
- [Concepts: Quality of Service settings](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html)
- [Tutorial: Understanding topics](https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Topics/Understanding-ROS2-Topics.html)
- [Tutorial: Writing a simple publisher and subscriber (Python)](https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Py-Publisher-And-Subscriber.html)
- [How-to: Passing ROS arguments to nodes via the command-line](https://docs.ros.org/en/jazzy/How-To-Guides/Node-arguments.html)
