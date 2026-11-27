# 01. 노드 (Node)

## 이 장의 목표

- 노드가 무엇인지, 프로세스와 어떻게 다른지, 노드 이름과 네임스페이스가 왜 필요한지 설명할 수 있다.
- 타이머 · 로거 · 파라미터를 가진 최소한의 rclpy 노드를 읽고, `spin()`이 하는 일을 말할 수 있다.
- `ros2 run`, `ros2 node`, `ros2 param` 명령으로 실행 중인 노드를 들여다보고 바꿀 수 있다.

## 핵심 개념

### 노드 = ROS 2 그래프에 참여하는 하나의 "부품"

로봇 소프트웨어는 카메라 드라이버, 물체 인식, 경로 계획, 모터 제어처럼 여러 부품으로 나뉩니다. ROS 2에서는 이 부품 하나하나를 **노드**라고 부릅니다. 노드는 토픽(02장), 서비스(04장), 파라미터로 다른 노드와 이야기합니다.

```
   프로세스 A (python3)            프로세스 B (C++ 실행 파일)
  ┌─────────────────────┐        ┌──────────────────────────┐
  │  노드 /node_basics   │        │ 노드 /camera  노드 /detector │
  └──────────┬──────────┘        └─────┬──────────────┬─────┘
             │                         │              │
  ═══════════╧═════════════════════════╧══════════════╧════════
                   ROS 2 그래프 (DDS 미들웨어 위)
       노드들은 이름으로 서로를 찾고, 토픽/서비스/파라미터로 통신
```

- **프로세스 vs 노드**: 프로세스는 OS가 실행하는 프로그램이고, 노드는 ROS 2 그래프 안의 논리적 참여자입니다. 보통은 1 프로세스 = 1 노드로 만들지만, 한 프로세스 안에 노드 여러 개를 넣을 수도 있습니다(그림의 프로세스 B). 이 장의 예제는 1 프로세스 = 1 노드입니다.
- **노드 이름**: 그래프 안에서 노드를 부르는 이름입니다(`/node_basics`). `ros2 param set /node_basics ...`처럼 CLI도 이 이름으로 노드를 찾습니다. 이름은 코드에서 정하지만 실행할 때 `--ros-args -r __node:=새이름`으로 바꿀 수 있습니다. 같은 이름의 노드가 둘이면 ROS 2가 경고를 띄웁니다(아래 "실험해 보기").
- **네임스페이스**: 이름 앞에 붙는 폴더 같은 접두사입니다. 같은 프로그램을 로봇 두 대에 띄울 때 `/robot1/node_basics`, `/robot2/node_basics`처럼 구분합니다. `--ros-args -r __ns:=/robot1`로 지정합니다.

### `spin()` = 이벤트 루프

노드는 "할 일이 생기면 콜백을 실행하는" 방식으로 동작합니다. 타이머가 울리거나, 메시지가 오거나, 누가 파라미터를 바꾸면 그에 맞는 콜백이 불려야 하는데, 이걸 기다렸다가 불러 주는 반복문이 `rclpy.spin(node)`입니다.

```
rclpy.spin(node):
    while ROS가 살아 있는 동안:
        준비된 일(타이머 만료, 메시지 도착, 서비스 요청...)이 생길 때까지 기다림
        → 해당 콜백 실행 (on_timer 등)
```

실제로 이 반복을 돌리는 객체를 **executor**라고 부릅니다. `rclpy.spin()`은 기본 executor(SingleThreadedExecutor)를 만들어 돌려 주는 지름길입니다. executor와 콜백이 동시에 실행되는 방식은 [05장](05_executor.md)에서 자세히 다룹니다.

`spin()`을 부르지 않으면 타이머도, 구독도, 파라미터 변경도 전혀 처리되지 않습니다. 콜백 안에서 오래 걸리는 일을 하면 그동안 다른 콜백도 모두 멈춥니다.

### 파라미터 = 노드의 설정값

파라미터는 노드가 외부에 공개하는 설정값입니다(이 예제의 `rate`, `greeting`). 코드를 고치지 않고 실행할 때 `-p 이름:=값`으로 주거나, 실행 중에 `ros2 param set`으로 바꿀 수 있습니다. ROS 2에서는 파라미터를 **선언(declare)** 해야 쓸 수 있고, 선언할 때 정해진 타입과 범위를 벗어나는 값은 거부됩니다.

## 코드 읽기

소스: [`ws/src/ros2_study/ros2_study/node_basics.py`](../../ws/src/ros2_study/ros2_study/node_basics.py)

### 1) Node를 상속하고 이름 정하기

```python
class NodeBasics(Node):
    def __init__(self):
        super().__init__('node_basics')
```

rclpy에서는 `Node`를 상속한 클래스를 만들고 생성자에서 노드 이름을 넘기는 것이 기본 형태입니다. 타이머, 퍼블리셔, 파라미터는 모두 `self.create_...`, `self.declare_...`처럼 노드 객체의 메서드로 만듭니다. 그래서 "이 타이머는 이 노드의 것"이라는 소속이 분명해집니다.

### 2) 파라미터 선언

```python
self.declare_parameter('greeting', '안녕, ROS 2')
self.declare_parameter(
    'rate', 1.0,
    ParameterDescriptor(
        description='타이머 주기(Hz)',
        floating_point_range=[FloatingPointRange(from_value=0.1, to_value=10.0)],
    ),
)
```

- 기본값의 파이썬 타입이 곧 파라미터 타입이 됩니다. `'안녕, ROS 2'`는 string, `1.0`은 double입니다. 그래서 `rate`에 정수 `5`를 넣으면 타입이 달라 거부됩니다(아래 실행 결과 참고).
- `ParameterDescriptor`로 설명과 허용 범위(0.1~10.0)를 붙였습니다. 이렇게 하면 범위 검사를 직접 짜지 않아도 ROS가 알아서 거부해 줍니다. 코드에서 `1/rate`를 계산하므로 0이 들어오면 안 되기 때문입니다.

### 3) 타이머와 로거

```python
rate = self.get_parameter('rate').value
self.timer = self.create_timer(1.0 / rate, self.on_timer)
...
log = self.get_logger()
log.debug('debug: 기본 설정에서는 안 보임')
log.info(f'시작: rate={rate} Hz')
log.warn('warn: 주의할 일')
log.error('error: 문제가 생김')
```

- `create_timer(주기_초, 콜백)`: `spin()`이 도는 동안 주기마다 콜백을 불러 줍니다. 반환값을 `self.timer`에 보관하는 이유는 나중에 주기를 바꾸기 위해서입니다.
- 로거 레벨은 `DEBUG < INFO < WARN < ERROR < FATAL` 순서입니다. 기본 레벨이 INFO라서 debug 줄은 평소에 안 보입니다. `print()` 대신 로거를 쓰면 시간·노드 이름이 함께 찍히고, `/rosout` 토픽으로도 나가서 다른 도구로 모아 볼 수 있습니다.

### 4) 실행 중 파라미터 변경에 반응하기

```python
def on_timer(self):
    greeting = self.get_parameter('greeting').value
    rate = self.get_parameter('rate').value

    period_ns = int(1e9 / rate)
    if self.timer.timer_period_ns != period_ns:
        self.timer.timer_period_ns = period_ns
        self.timer.reset()
        self.get_logger().info(f'rate 변경 → {rate} Hz')
```

`ros2 param set`으로 값을 바꾸면 노드 안의 파라미터 값은 즉시 바뀌지만, **그 값을 다시 읽지 않으면 동작은 그대로**입니다. 가장 단순한 방법은 이렇게 타이머 콜백에서 매번 다시 읽는 것입니다.

- `greeting`은 다음 틱부터 바로 바뀝니다.
- `rate`가 바뀌면 타이머 주기를 바꿉니다. 타이머를 새로 만들 필요 없이 `timer_period_ns`만 바꾸면 됩니다. `reset()`을 부르지 않으면 이미 예약된 다음 틱은 옛 주기대로 옵니다.
- 이 방식의 한계: 변경이 **다음 틱에** 반영됩니다. rate가 0.1 Hz면 최대 10초 늦게 반영됩니다. 바로 반응해야 하면 `add_post_set_parameters_callback()`으로 "값이 바뀐 직후" 불리는 콜백을 등록하는 방법이 있습니다.

### 5) 시작과 깔끔한 종료

```python
def main():
    rclpy.init()
    node = NodeBasics()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
```

- `rclpy.init()`: ROS 2 통신을 준비합니다. `--ros-args ...` 인자도 여기서 읽힙니다.
- Ctrl+C를 누르면 `spin()`에서 `KeyboardInterrupt`가, `kill`(SIGTERM) 같은 외부 종료면 `ExternalShutdownException`이 올라옵니다. 둘 다 정상 종료이므로 잡아서 조용히 끝냅니다. 잡지 않으면 종료할 때마다 긴 트레이스백이 찍힙니다.
- `finally`에서 노드를 정리하고 `try_shutdown()`을 부릅니다. 신호 처리 중에 이미 shutdown 되었을 수 있어서 `shutdown()` 대신 두 번 불려도 안전한 `try_shutdown()`을 씁니다.

## 실행해 보기

모든 터미널에서 먼저 컨테이너 셸에 들어갑니다(호스트의 저장소 폴더에서).

```bash
docker compose exec ros bash
```

**터미널 1** — 빌드하고 노드 실행

```bash
cd /ws && colcon build --symlink-install --packages-select ros2_study && source install/setup.bash
ros2 run ros2_study node_basics
```

```text
Starting >>> ros2_study
Finished <<< ros2_study [1.35s]

Summary: 1 package finished [1.45s]

[INFO] [1795743573.380483272] [node_basics]: 시작: rate=1.0 Hz
[WARN] [1795743573.380868069] [node_basics]: warn: 주의할 일
[ERROR] [1795743573.381112655] [node_basics]: error: 문제가 생김
[INFO] [1795743574.370637912] [node_basics]: 안녕, ROS 2 #1
[INFO] [1795743575.370630720] [node_basics]: 안녕, ROS 2 #2
[INFO] [1795743576.370642928] [node_basics]: 안녕, ROS 2 #3
```

`debug` 줄은 기본 레벨(INFO)보다 낮아서 보이지 않습니다.

**터미널 2** — 실행 중인 노드 살펴보기

```bash
source /ws/install/setup.bash
ros2 node list
ros2 node info /node_basics
```

```text
/node_basics
```

```text
/node_basics
  Subscribers:

  Publishers:
    /parameter_events: rcl_interfaces/msg/ParameterEvent
    /rosout: rcl_interfaces/msg/Log
  Service Servers:
    /node_basics/describe_parameters: rcl_interfaces/srv/DescribeParameters
    /node_basics/get_parameter_types: rcl_interfaces/srv/GetParameterTypes
    /node_basics/get_parameters: rcl_interfaces/srv/GetParameters
    /node_basics/get_type_description: type_description_interfaces/srv/GetTypeDescription
    /node_basics/list_parameters: rcl_interfaces/srv/ListParameters
    /node_basics/set_parameters: rcl_interfaces/srv/SetParameters
    /node_basics/set_parameters_atomically: rcl_interfaces/srv/SetParametersAtomically
  Service Clients:

  Action Servers:

  Action Clients:

```

코드에서 만든 것은 타이머뿐인데 퍼블리셔와 서비스가 보입니다. 모든 노드가 기본으로 갖는 것들입니다. `/rosout`은 로그를 내보내는 토픽이고, `*_parameters` 서비스들은 `ros2 param` 명령이 노드와 대화하는 창구입니다. 즉 **`ros2 param set`은 내부적으로 이 노드의 서비스를 호출하는 것**입니다.

파라미터 보기·바꾸기:

```bash
ros2 param list /node_basics
ros2 param get /node_basics greeting
ros2 param set /node_basics greeting 반가워
ros2 param set /node_basics rate 4.0
```

```text
  greeting
  rate
  start_type_description_service
  use_sim_time
String value is: 안녕, ROS 2
Set parameter successful
Set parameter successful
```

이때 터미널 1의 출력:

```text
[INFO] [1795743579.370632045] [node_basics]: 안녕, ROS 2 #6
[INFO] [1795743580.370725092] [node_basics]: 반가워 #7
[INFO] [1795743581.370776626] [node_basics]: 반가워 #8
[INFO] [1795743582.370773539] [node_basics]: rate 변경 → 4.0 Hz
[INFO] [1795743582.371240106] [node_basics]: 반가워 #9
[INFO] [1795743582.621140732] [node_basics]: 반가워 #10
[INFO] [1795743582.871593499] [node_basics]: 반가워 #11
[INFO] [1795743583.121043750] [node_basics]: 반가워 #12
```

인사말은 다음 틱부터 바뀌고, rate를 바꾼 뒤에는 다음 틱(최대 1초 뒤)에 "rate 변경"이 찍히고 그 뒤로 0.25초 간격이 됩니다. 터미널 1에서 Ctrl+C를 누르면 트레이스백 없이 조용히 끝납니다.

선언된 범위·타입을 벗어난 값, 선언하지 않은 파라미터는 거부됩니다.

```bash
ros2 param set /node_basics rate 0.0
ros2 param set /node_basics rate 5
ros2 param set /node_basics nope 1
ros2 param describe /node_basics rate
```

```text
Setting parameter failed: Parameter rate out of range Min: 0.1, Max: 10.0, value: 0.0
Setting parameter failed: Wrong parameter type, expected 'Type.DOUBLE' got 'Type.INTEGER'
Setting parameter failed: Invalid access to undeclared parameter(s): []
Parameter name: rate
  Type: double
  Description: 타이머 주기(Hz)
  Constraints:
    Min value: 0.1
    Max value: 10.0
```

`5`는 정수로 해석되므로 double 파라미터에는 `5.0`처럼 소수점을 붙여야 합니다.

**노드 이름 바꿔서 실행하기 (remapping)** — 터미널 1을 Ctrl+C로 끄고 다음처럼 실행합니다. 이름과 파라미터 초기값을 한꺼번에 줄 수 있습니다.

```bash
ros2 run ros2_study node_basics --ros-args -r __node:=my_node -p greeting:=hi -p rate:=2.0
```

```text
[INFO] [1795743603.421829031] [my_node]: 시작: rate=2.0 Hz
[WARN] [1795743603.422228911] [my_node]: warn: 주의할 일
[ERROR] [1795743603.422482478] [my_node]: error: 문제가 생김
[INFO] [1795743603.912097818] [my_node]: hi #1
[INFO] [1795743604.412642133] [my_node]: hi #2
```

로그의 대괄호 안 이름도 `my_node`로 바뀌었습니다. 터미널 2에서는 이제 `/my_node`로 접근합니다.

```bash
ros2 param get /my_node greeting
```

```text
String value is: hi
```

## 실험해 보기

### 1. 로그 레벨 바꾸기

```bash
ros2 run ros2_study node_basics --ros-args --log-level node_basics:=debug
```

```text
[DEBUG] [1795743627.408195238] [node_basics]: debug: 기본 설정에서는 안 보임
[INFO] [1795743627.408502232] [node_basics]: 시작: rate=1.0 Hz
[WARN] [1795743627.408777238] [node_basics]: warn: 주의할 일
[ERROR] [1795743627.409031558] [node_basics]: error: 문제가 생김
```

숨어 있던 debug 줄이 나옵니다. 반대로 `node_basics:=warn`으로 주면 WARN과 ERROR 두 줄만 나오고 매초 찍히던 INFO 줄은 사라졌습니다. 이름 없이 `--log-level debug`만 주면 내 노드뿐 아니라 `rcl`, `rmw_fastrtps_cpp` 같은 내부 라이브러리의 debug 로그까지 쏟아집니다(직접 해 보니 2.5초 동안 `[rcl]: Initializing node 'node_basics' in namespace ''` 같은 DEBUG 줄이 93개 나왔습니다). 그래서 보통은 노드 이름을 붙여 좁힙니다.

### 2. 네임스페이스 붙이기, 같은 노드 여러 개 띄우기

터미널 세 개에서 각각 실행:

```bash
ros2 run ros2_study node_basics
ros2 run ros2_study node_basics --ros-args -r __node:=my_node
ros2 run ros2_study node_basics --ros-args -r __ns:=/robot1
```

```text
$ ros2 node list
/my_node
/node_basics
/robot1/node_basics
```

같은 코드로 이름이 다른 노드 세 개가 생겼습니다. 네임스페이스를 준 노드의 로그에는 `[robot1.node_basics]`처럼 찍힙니다. 반대로 **아무 옵션 없이 두 개를** 띄우면 이렇게 됩니다.

```text
$ ros2 node list
/node_basics
/node_basics
WARNING: Be aware that there are nodes in the graph that share an exact name, which can have unintended side effects.
```

실행은 되지만, 이 상태에서는 `ros2 param set /node_basics ...`가 두 노드 중 어느 쪽을 가리키는지 이름만으로 구분할 수 없습니다.

### 3. 범위를 벗어난 초기값으로 시작하기

```bash
ros2 run ros2_study node_basics --ros-args -p rate:=0.0
```

```text
rclpy.exceptions.InvalidParameterValueException: Invalid parameter value (0.0) for parameter. Reason: Parameter rate out of range Min: 0.1, Max: 10.0, value: 0.0: rate
[ros2run]: Process exited with failure 1
```

실행 중 `param set`은 거부 메시지만 돌려주지만, 시작할 때 잘못된 값을 주면 `declare_parameter()`에서 예외가 나서 노드가 아예 뜨지 않습니다.

### 4. 범위 검사를 빼면? (일부러 망가뜨리기)

`rate` 선언을 `self.declare_parameter('rate', 1.0)`로 바꿔 `ParameterDescriptor`를 빼고 다시 실행한 뒤, 다른 터미널에서 `ros2 param set /node_basics rate 0.0`을 해 보세요. `Set parameter successful`이 뜨고, 다음 틱에 노드가 이렇게 죽습니다.

```text
  File ".../node_basics.py", line 39, in on_timer
    period_ns = int(1e9 / rate)
                    ~~~~^~~~~~
ZeroDivisionError: float division by zero
[ros2run]: Process exited with failure 1
```

콜백에서 난 예외는 `spin()` 밖으로 올라와 노드 전체를 끝냅니다. 외부에서 들어오는 값(파라미터)은 꼭 검증해야 하는 이유입니다.

## 발표할 때 이렇게 설명하기

> 노드는 ROS 2 그래프에 참여하는 부품 하나입니다. 보통 프로그램 하나에 노드 하나를 두고, 노드는 `/node_basics` 같은 이름으로 서로를 찾습니다. 노드 코드는 "타이머가 울리면 이 함수, 메시지가 오면 저 함수"처럼 콜백을 등록해 두는 방식이고, `spin()`이 이벤트를 기다렸다가 그 콜백을 불러 주는 반복문 역할을 합니다. 파라미터는 노드의 설정값인데, 선언할 때 타입과 범위를 정해 두면 `ros2 param set`으로 실행 중에 바꿀 수 있고 잘못된 값은 ROS가 막아 줍니다. 다만 값이 바뀌었다고 동작이 저절로 바뀌는 건 아니라서, 코드에서 값을 다시 읽어 반영해야 합니다. 그리고 `--ros-args -r __node:=...`로 코드 수정 없이 이름을 바꿔 같은 프로그램을 여러 개 띄울 수 있습니다.

## 자주 하는 실수

1. **`spin()`을 안 부르거나, 콜백 안에서 오래 걸리는 일을 한다.** 콜백은 `spin()`이 불러 줘야 실행됩니다. 콜백 하나가 `time.sleep(5)`를 하면 그동안 다른 타이머·구독도 모두 멈춥니다(05장).
2. **double 파라미터에 정수를 넣는다.** `ros2 param set ... rate 5`는 INTEGER로 해석되어 `Wrong parameter type`으로 거부됩니다. `5.0`으로 써야 합니다.
3. **파라미터를 바꿨는데 동작이 안 바뀐다고 당황한다.** 생성자에서 한 번만 읽고 끝내면 `param set`은 "성공"하지만 노드는 옛 값으로 계속 돕니다. 콜백에서 다시 읽거나 파라미터 콜백을 등록해야 합니다.
4. **메시지·디스크립터 필드 이름 오타.** ROS 메시지 생성자는 모르는 키워드 인자를 조용히 무시합니다. 실제로 `floating_point_range`를 `floating_point_ranges`로 잘못 썼을 때 에러 없이 실행되고 범위 검사만 사라졌습니다. `ros2 param describe`로 Constraints가 실제로 붙었는지 확인하세요.
5. **같은 이름의 노드를 여러 개 띄운다.** 경고만 뜨고 실행은 되므로 놓치기 쉽습니다. `__node:=` 또는 `__ns:=`로 이름을 구분하세요.

## 확인 문제

**Q1.** 프로세스와 노드는 같은 것인가요?

<details><summary>정답</summary>

아닙니다. 프로세스는 OS가 실행하는 프로그램이고, 노드는 ROS 2 그래프 안의 논리적 참여자입니다. 보통 1:1로 만들지만 한 프로세스에 여러 노드를 둘 수도 있습니다.
</details>

**Q2.** `rclpy.spin(node)` 줄을 지우고 `main()`이 바로 끝나게 하면 `on_timer`는 몇 번 불릴까요?

<details><summary>정답</summary>

0번입니다. 타이머는 `create_timer()`로 등록만 될 뿐이고, 실제로 콜백을 부르는 것은 `spin()`(executor)입니다.
</details>

**Q3.** 코드 수정 없이 같은 `node_basics`를 `/left/node_basics`, `/right/node_basics` 두 개로 띄우려면?

<details><summary>정답</summary>

```bash
ros2 run ros2_study node_basics --ros-args -r __ns:=/left
ros2 run ros2_study node_basics --ros-args -r __ns:=/right
```
</details>

**Q4.** `ros2 param set /node_basics rate 3`이 실패했습니다. 이유와 고치는 방법은?

<details><summary>정답</summary>

`rate`는 기본값 `1.0`으로 선언되어 double 타입인데 `3`은 정수로 해석됩니다. `ros2 param set /node_basics rate 3.0`으로 보내면 됩니다.
</details>

**Q5.** `ros2 node info`에 내가 만들지 않은 `/node_basics/set_parameters` 서비스가 보이는 이유는?

<details><summary>정답</summary>

모든 노드는 파라미터를 외부에서 읽고 쓸 수 있도록 파라미터 서비스들을 자동으로 만듭니다. `ros2 param get/set` 명령은 이 서비스를 호출해서 동작합니다.
</details>

## 더 읽을거리

- [Concepts: Nodes](https://docs.ros.org/en/jazzy/Concepts/Basic/About-Nodes.html)
- [Concepts: Parameters](https://docs.ros.org/en/jazzy/Concepts/Basic/About-Parameters.html)
- [Concepts: Logging and logger configuration](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Logging.html)
- [Concepts: Executors](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Executors.html)
- [Tutorial: Understanding nodes](https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Nodes/Understanding-ROS2-Nodes.html)
- [Tutorial: Understanding parameters](https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Parameters/Understanding-ROS2-Parameters.html)
- [Tutorial: Using parameters in a class (Python)](https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Using-Parameters-In-A-Class-Python.html)
- [How-to: Passing ROS arguments to nodes via the command-line](https://docs.ros.org/en/jazzy/How-To-Guides/Node-arguments.html)
