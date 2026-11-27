# 01a. 파라미터

01장에서 파라미터를 "노드의 설정값"으로 짧게 봤습니다. 이 장은 파라미터만 따로 깊게 봅니다. 값을 어디서 어떻게 넣는지, 실행 중에 바뀔 때 어떻게 검증하고 반응하는지, 다른 노드의 파라미터를 코드로 어떻게 다루는지까지 다룹니다. 발표 범위(노드·토픽·서비스) 밖의 보충 장이라, 01장을 읽은 뒤 필요할 때 보면 됩니다.

## 이 장의 목표

- 파라미터가 노드 하나에 속하고, 선언해야 존재하며, 내부적으로 서비스와 토픽 위에서 동작한다는 것을 설명할 수 있다.
- 기본값, `-p`, YAML, launch, `ros2 param set`으로 값을 주고, 어떤 값이 이기는지 예측할 수 있다.
- pre_set / on_set / post_set 콜백으로 값을 고치고, 검증하고, 반응하는 코드를 읽고 쓸 수 있다.
- 다른 노드의 파라미터를 코드로 읽고 쓰고, `/parameter_events`로 변경을 지켜볼 수 있다.

## 전체 그림

```
 값을 넣는 곳                         노드 (/node_basics)                       밖에서 보는 곳
┌──────────────────┐            ┌───────────────────────────┐
│ 코드 기본값        │──시작할 때─▶│ declare_parameter         │
│ --params-file YAML│──시작할 때─▶│   (이름·타입·범위 고정)      │◀─ get/list/describe ─ ros2 param, 다른 노드
│ -p 이름:=값        │──시작할 때─▶│                           │
│ launch parameters │──시작할 때─▶│ ① pre_set  요청 고치기      │
│ ros2 param set    │──실행 중───▶│ ② on_set   검증 (거절 가능) │◀─ set_parameters ── ros2 param, 다른 노드
│ 다른 노드의 코드    │──실행 중───▶│ ③ post_set 반응            │
└──────────────────┘            └─────────────┬─────────────┘
                                              │ 성공한 변경마다
                                              ▼
                                      /parameter_events 토픽 ──▶ 감시 노드
```

- 이 장의 순서: **정체** (아래 핵심 개념) → **값 주는 방법** → **변경에 반응하기** (①②③) → **다른 노드에서 다루기**.
- 예제는 모두 `ws/src/ros2_study`에 있습니다. 컨테이너 셸에서 `cd /ws && colcon build --symlink-install --packages-select ros2_study && source install/setup.bash`로 빌드한 뒤 실행합니다.

## 핵심 개념

### 파라미터의 정체

01장에서 파라미터를 "노드의 설정값"이라고 했습니다. 조금 더 정확히 말하면 세 가지 성질이 있습니다.

- **노드 하나에 속합니다.** 모든 노드가 함께 쓰는 전역 설정 저장소는 없습니다. `rate`는 "`/node_basics`의 `rate`"이고, 다른 노드가 같은 이름의 파라미터를 가져도 서로 상관없습니다. 노드가 꺼지면 그 노드의 파라미터도 사라집니다.
- **선언(declare)해야 존재하고, 타입은 선언할 때 정해집니다.** `declare_parameter('rate', 1.0)`처럼 기본값이 `1.0`(double)이면 `rate`는 끝까지 double입니다.
- **서비스와 토픽 위에서 동작합니다.** 노드를 만들면 파라미터용 서비스 6개와 `/parameter_events` 토픽 퍼블리셔가 자동으로 생깁니다. `ros2 param` 명령은 이 서비스를 부르는 클라이언트일 뿐입니다.

#### 선언하지 않은 파라미터

코드에서 선언하지 않은 이름을 읽으면 예외가 납니다(rclpy, 실제 출력).

```python
node.get_parameter('nope')
```

```text
ParameterNotDeclaredException : Invalid access to undeclared parameter(s): nope
```

밖에서 값을 줄 때는 경로마다 반응이 다릅니다.

```bash
ros2 run ros2_study node_basics --ros-args -p nope:=1     # 터미널 1: 에러 없이 정상 실행
ros2 param list /node_basics                              # 터미널 2
ros2 param get /node_basics nope
ros2 param set /node_basics nope 1
```

```text
  greeting
  rate
  start_type_description_service
  use_sim_time
Parameter not set
Setting parameter failed: Invalid access to undeclared parameter(s): []
```

> 주의: 시작할 때 주는 값(`-p`, YAML)은 선언되지 않은 이름이면 **경고 없이 무시됩니다.** 이름 오타(`-p rtae:=2.0`)를 내도 노드는 잘 뜨고 기본값으로 돕니다. 값이 들어갔는지는 `ros2 param get`으로 확인하세요. (모든 이름을 받아 주게 하는 `allow_undeclared_parameters` 옵션도 있지만 이 예제는 쓰지 않습니다. [Concepts: Parameters](https://docs.ros.org/en/jazzy/Concepts/Basic/About-Parameters.html) 참고)

#### 파라미터는 서비스다

`node_basics`를 띄우고 다른 터미널에서 봅니다.

```bash
ros2 service list | grep node_basics
ros2 topic list
```

```text
/node_basics/describe_parameters
/node_basics/get_parameter_types
/node_basics/get_parameters
/node_basics/get_type_description
/node_basics/list_parameters
/node_basics/set_parameters
/node_basics/set_parameters_atomically
/parameter_events
/rosout
```

(`get_type_description`은 파라미터용이 아니라 메시지 타입 정보를 알려 주는 서비스입니다.) `ros2 param get`이 하는 일을 서비스로 직접 해 볼 수도 있습니다.

```bash
ros2 service call /node_basics/get_parameters rcl_interfaces/srv/GetParameters "{names: [rate, greeting]}"
```

```text
response:
rcl_interfaces.srv.GetParameters_Response(values=[rcl_interfaces.msg.ParameterValue(type=3, ..., double_value=4.0, ...), rcl_interfaces.msg.ParameterValue(type=4, ..., string_value='YAML에서 온 인사', ...)])
```

`ParameterValue`에는 타입마다 칸이 하나씩 있고 `type`(3=double, 4=string)이 어느 칸이 진짜인지 알려 줍니다. 값이 바뀌면 노드가 `/parameter_events`에 알림을 냅니다. `ros2 topic echo /parameter_events`를 켜 두고 `ros2 param set /node_basics rate 4.0`을 하면:

```text
node: /node_basics
new_parameters: []
changed_parameters:
- name: rate
  value:
    type: 3
    double_value: 4.0
    ...
deleted_parameters: []
```

여러 노드의 파라미터 변경을 한곳에서 지켜보고 싶을 때 이 토픽을 구독합니다.

#### describe: 타입과 제약 보기

`ros2 param describe`는 선언할 때 붙인 descriptor(설명, 범위, 읽기 전용 여부)를 보여 줍니다.

```bash
ros2 param describe /node_basics rate
ros2 param describe /node_basics start_type_description_service
```

```text
Parameter name: rate
  Type: double
  Description: 타이머 주기(Hz)
  Constraints:
    Min value: 0.1
    Max value: 10.0
Parameter name: start_type_description_service
  Type: boolean
  Description: If enabled, start the ~/get_type_description service.
  Constraints:
    Read only: true
```

`start_type_description_service`는 rclpy가 모든 노드에 넣어 주는 **읽기 전용(read_only)** 파라미터입니다. 시작할 때만 정할 수 있고 실행 중에는 못 바꿉니다.

```bash
ros2 param set /node_basics start_type_description_service false
```

```text
Setting parameter failed: Trying to set a read-only parameter: start_type_description_service.
```

내 파라미터도 `ParameterDescriptor(read_only=True)`로 선언하면 같은 보호를 받습니다. 하드웨어 포트 이름처럼 "실행 중에 바뀌면 곤란한" 값에 씁니다.

## 값을 주는 방법과 우선순위

값이 들어오는 길은 다섯 가지입니다. 아래 표는 모두 같은 `node_basics`를 실행해서 시작 로그의 `rate`와 인사말을 확인한 결과입니다.

| # | 방법 | 명령 | 결과 |
|---|---|---|---|
| ① | 코드 기본값 | `ros2 run ros2_study node_basics` | `rate=1.0`, `안녕, ROS 2` |
| ② | YAML 파일 | `... --ros-args --params-file node_basics.yaml` | `rate=2.0`, `YAML에서 온 인사` |
| ③ | YAML 뒤에 `-p` | `... --params-file node_basics.yaml -p rate:=5.0` | `rate=5.0`, `YAML에서 온 인사` |
| ③' | `-p` 뒤에 YAML | `... -p rate:=5.0 --params-file node_basics.yaml` | **`rate=2.0`** |
| ④ | launch | `ros2 launch ros2_study params.launch.py` | `rate=2.0`, `launch에서 덮어씀` |
| ⑤ | 실행 중 | `ros2 param set /node_basics rate 4.0` | `rate 변경 → 4.0 Hz` |

③과 ③'를 보세요. **`-p`가 YAML보다 "강한" 것이 아니라, 명령줄에서 나중에 쓴 것이 이깁니다.** YAML 파일 두 개를 줘도 마찬가지로 뒤의 파일이 이겼습니다. 정리하면:

- 시작할 때 주는 값(②③④)은 **코드 기본값을 덮어쓰고**, 그들끼리는 **나중에 적용된 것이 이깁니다**.
- 실행 중 `ros2 param set`(⑤)은 시작 값이 무엇이었든 그 위에 덮어씁니다. 단, 노드를 재시작하면 사라집니다(아래 "저장하고 다시 불러오기").

> 주의: 시작 값도 선언 때 검사됩니다. 범위를 벗어나거나(01장 실험 3) 타입이 틀리면(아래 "타입 함정") `declare_parameter()`에서 예외가 나 노드가 뜨지 않습니다.

### YAML 파일 구조

[`config/node_basics.yaml`](../../ws/src/ros2_study/config/node_basics.yaml):

```yaml
node_basics:            # ← 노드 이름
  ros__parameters:      # ← 고정 키워드 (밑줄 두 개)
    rate: 2.0           # double 이므로 2 가 아니라 2.0
    greeting: "YAML에서 온 인사"
```

```bash
ros2 run ros2_study node_basics --ros-args \
  --params-file $(ros2 pkg prefix ros2_study)/share/ros2_study/config/node_basics.yaml
```

```text
[INFO] [node_basics]: 시작: rate=2.0 Hz
[INFO] [node_basics]: YAML에서 온 인사 #1
[INFO] [node_basics]: YAML에서 온 인사 #2
```

파일 하나에 여러 노드의 섹션을 넣을 수 있고, 노드는 **자기 이름과 맞는 섹션만** 가져갑니다.

### 노드 이름이 맞지 않으면: 조용히 무시

같은 파일을 쓰되 노드 이름을 바꿔 실행합니다.

```bash
ros2 run ros2_study node_basics --ros-args --params-file .../node_basics.yaml -r __node:=other
```

```text
[INFO] [other]: 시작: rate=1.0 Hz
[INFO] [other]: 안녕, ROS 2 #1
```

에러도 경고도 없이 코드 기본값으로 돕니다. 이름은 그대로 두고 `-r __ns:=/robot1`로 네임스페이스만 붙여도 결과가 같았습니다(`[robot1.node_basics]: 시작: rate=1.0 Hz`). YAML의 `node_basics:`는 `/node_basics`, 즉 루트 네임스페이스의 노드만 가리킵니다.

> 주의: "YAML을 줬는데 값이 안 들어간다"면 가장 먼저 YAML의 최상위 키와 `ros2 node list`에 보이는 노드 이름(네임스페이스 포함)을 비교하세요.

### 와일드카드 `/**`

[`config/all_nodes.yaml`](../../ws/src/ros2_study/config/all_nodes.yaml):

```yaml
/**:
  ros__parameters:
    greeting: "와일드카드에서 온 인사"
```

```bash
ros2 run ros2_study node_basics --ros-args --params-file .../all_nodes.yaml -r __node:=other
ros2 run ros2_study node_basics --ros-args --params-file .../all_nodes.yaml -r __ns:=/robot1
```

```text
[INFO] [other]: 와일드카드에서 온 인사 #1
[INFO] [robot1.node_basics]: 와일드카드에서 온 인사 #1
```

`/**`는 "모든 네임스페이스의 모든 노드"라서 이름을 바꿔도 적용됩니다. `use_sim_time`처럼 모든 노드에 똑같이 줄 값에 편합니다. `*`(슬래시 사이 한 토큰)와 `/**/node_basics`(아무 네임스페이스의 node_basics) 같은 형태도 있습니다([Node arguments](https://docs.ros.org/en/jazzy/How-To-Guides/Node-arguments.html)).

와일드카드 파일과 노드 이름 파일을 함께 주면? 여기서도 **뒤에 준 파일이 이겼습니다.**

```text
# --params-file node_basics.yaml --params-file all_nodes.yaml
[INFO] [node_basics]: 시작: rate=2.0 Hz
[INFO] [node_basics]: 와일드카드에서 온 인사 #1
# --params-file all_nodes.yaml --params-file node_basics.yaml
[INFO] [node_basics]: 시작: rate=2.0 Hz
[INFO] [node_basics]: YAML에서 온 인사 #1
```

### launch 파일에서

[`launch/params.launch.py`](../../ws/src/ros2_study/launch/params.launch.py)의 핵심:

```python
yaml = os.path.join(get_package_share_directory('ros2_study'), 'config', 'node_basics.yaml')
Node(
    package='ros2_study',
    executable='node_basics',
    parameters=[yaml, {'greeting': 'launch에서 덮어씀'}],
)
```

```bash
ros2 launch ros2_study params.launch.py
```

```text
[node_basics-1] [INFO] [node_basics]: 시작: rate=2.0 Hz
[node_basics-1] [INFO] [node_basics]: launch에서 덮어씀 #1
[node_basics-1] [INFO] [node_basics]: launch에서 덮어씀 #2
```

`rate`는 YAML에서(2.0) 왔고, `greeting`은 리스트에서 YAML 뒤에 쓴 딕셔너리가 YAML 값을 덮어썼습니다. YAML은 `setup.py`의 `data_files`로 `share/ros2_study/config`에 설치되므로, 소스 경로가 아니라 `get_package_share_directory()`로 찾습니다.

## 저장하고 다시 불러오기

`ros2 param set`으로 바꾼 값은 노드 메모리에만 있어서 재시작하면 사라집니다. 맞춰 놓은 값을 남기려면 `dump`로 YAML을 뽑습니다. Jazzy의 `ros2 param dump`는 **표준 출력**으로만 내보내므로 파일로 남길 때는 `>`로 리다이렉트합니다.

```bash
# YAML로 시작 → rate 4.0으로 바꾼 상태에서
ros2 param dump /node_basics
ros2 param dump /node_basics > my_params.yaml
```

```text
/node_basics:
  ros__parameters:
    greeting: "YAML에서 온 인사"
    rate: 4.0
    start_type_description_service: true
    use_sim_time: false
```

한글이 `에` 같은 이스케이프로 나오지만 올바른 YAML이고, 다시 읽으면 한글로 돌아옵니다. 최상위 키가 `/node_basics`(슬래시 포함 전체 이름)라는 점도 보세요.

실행 중인 노드에 파일을 다시 넣을 때는 `load`:

```bash
ros2 param set /node_basics greeting 바뀐값
ros2 param load /node_basics my_params.yaml
ros2 param get /node_basics greeting
```

```text
Set parameter successful
Set parameter greeting successful
Set parameter rate successful
Set parameter use_sim_time successful
Set parameter start_type_description_service failed: Trying to set a read-only parameter: start_type_description_service.
String value is: YAML에서 온 인사
```

파라미터마다 따로 set되므로, 읽기 전용인 `start_type_description_service` 하나가 실패해도 나머지는 들어갑니다. dump 파일에는 읽기 전용 파라미터까지 들어 있어서 이 실패 줄은 매번 보입니다.

같은 파일로 노드를 새로 시작할 수도 있습니다. 시작할 때는 읽기 전용 값도 정할 수 있으므로 에러가 없습니다.

```bash
ros2 run ros2_study node_basics --ros-args --params-file my_params.yaml
```

```text
[INFO] [node_basics]: 시작: rate=4.0 Hz
[INFO] [node_basics]: YAML에서 온 인사 #1
```

> 주의: dump는 `use_sim_time` 같은 기본 파라미터까지 전부 씁니다. 패키지에 넣을 설정 파일로 쓰려면 직접 관리할 값만 남기고 정리하세요.

## 타입 함정: `5`와 `5.0`

YAML과 명령줄 값은 글자 모양으로 타입이 정해집니다. `5`는 integer, `5.0`은 double, `true`는 bool, `"5"`는 string입니다. `rate`는 double로 선언되어 있으므로 정수를 주면 거부됩니다. 실행 중 `ros2 param set ... rate 5`가 거부되는 것은 01장에서 봤고, **시작할 때** 주면 더 아픕니다. 노드가 아예 뜨지 않습니다.

```bash
ros2 run ros2_study node_basics --ros-args -p rate:=5
```

```text
  File "/opt/ros/jazzy/lib/python3.12/site-packages/rclpy/node.py", line 584, in _declare_parameter_common
    raise InvalidParameterTypeException(
rclpy.exceptions.InvalidParameterTypeException: Trying to set parameter 'rate' to '5' of type 'INTEGER', expecting type 'DOUBLE': rate
[ros2run]: Process exited with failure 1
```

YAML에 `rate: 2`라고 써도 똑같이 `Trying to set parameter 'rate' to '2' of type 'INTEGER', expecting type 'DOUBLE'`으로 죽었습니다. 실행 중에는:

```bash
ros2 param set /node_basics rate 5
```

```text
Setting parameter failed: Wrong parameter type, expected 'Type.DOUBLE' got 'Type.INTEGER'
```

> 주의: double 파라미터에는 YAML·`-p`·`param set` 어디서든 소수점을 붙이세요(`5.0`). 노드 쪽에서 정수도 받게 하려면 descriptor에 `dynamic_typing=True`를 주는 방법이 있지만, 그러면 코드가 두 타입을 모두 처리해야 합니다.

## 모든 노드가 가진 파라미터: `use_sim_time`

`ros2 param list`에 늘 보이는 `use_sim_time`(bool, 기본 `false`)은 모든 노드에 자동으로 선언되는 파라미터입니다. `true`로 주면 노드의 시계와 타이머가 벽시계 대신 `/clock` 토픽의 시뮬레이션 시각을 따릅니다. 시스템 전체가 같은 값이어야 하므로 보통 위의 `/**` 와일드카드 YAML이나 launch로 한꺼번에 줍니다. 자세한 함정은 [07장 use_sim_time과 /clock](07_sync.md#use_sim_time과-clock)에서 다룹니다.

## 실행 중 변경에 반응하기: 콜백 3단계

01장의 `node_basics.py`는 타이머에서 매번 파라미터를 다시 읽습니다(폴링). 가장 단순하지만 다음 틱까지 늦게 반영되고, 잘못된 값을 거절할 수도 없습니다. 바뀌는 순간 검증하고 반응하려면 파라미터 콜백을 씁니다.

### 기본형: 검증(on_set)과 반응(post_set) 짝

[`param_callbacks.py`](../../ws/src/ros2_study/ros2_study/param_callbacks.py)는 `node_basics.py`와 같은 일(rate, greeting)을 "매번 다시 읽기" 대신 콜백으로 합니다. rclpy에는 파라미터 콜백이 세 종류 있습니다.

| 등록 함수 | 언제 불리나 | 할 수 있는 일 |
|---|---|---|
| `add_pre_set_parameters_callback` | 검증 **전** | 바꾸려는 값 목록을 고치거나 다른 파라미터를 끼워 넣기 |
| `add_on_set_parameters_callback` | 값이 바뀌기 **전** | 검증. `successful=False`를 돌려주면 변경이 거절됨 |
| `add_post_set_parameters_callback` | 값이 바뀐 **뒤** | 반응만 (거절 불가). 타이머 주기 바꾸기 등 |

이 예제는 자주 쓰는 두 개, 검증(on_set)과 반응(post_set)을 짝으로 씁니다.

```python
self.add_on_set_parameters_callback(self.validate)      # ① 바꾸기 전: 거절 가능
self.add_post_set_parameters_callback(self.on_changed)  # ② 바뀐 뒤: 반응만

def validate(self, params):
    for p in params:
        if p.name == 'rate' and p.value <= 0.0:
            return SetParametersResult(successful=False, reason='rate는 0보다 커야 합니다')
    return SetParametersResult(successful=True)

def on_changed(self, params):
    for p in params:
        self.get_logger().info(f'설정됨: {p.name} = {p.value}')
        if p.name == 'rate':
            period_ns = int(1e9 / p.value)
            if self.timer.timer_period_ns != period_ns:  # 같은 값이면 타이머를 건드리지 않음
                self.timer.timer_period_ns = period_ns
                self.timer.reset()
                self.get_logger().info(f'타이머 주기 변경 → {p.value} Hz')
```

- `params`에는 노드의 모든 파라미터가 아니라 **이번 set 요청에 들어 있던 파라미터만** 들어옵니다. `rate`만 set하면 `rate`만 들어옵니다. 그래서 `p.name`으로 무엇이 왔는지 확인합니다.
- 단, **"요청에 들어 있었다" ≠ "값이 바뀌었다"** 입니다. 같은 값으로 다시 set해도 콜백이 불리고, `ros2 param load`로 여러 개를 한꺼번에 넣으면 그대로인 값까지 전부 들어옵니다(실제로 확인함). 그래서 로그는 "설정됨"이라고 쓰고, 정말 바뀌었을 때만 할 일(타이머 `reset()`)은 현재 값과 직접 비교한 뒤에 합니다. 비교하지 않으면 같은 값을 넣을 때마다 타이머가 다시 시작돼 주기가 흔들립니다.
- 검증은 반드시 on_set 쪽에서 합니다. post_set은 이미 값이 바뀐 뒤라서 거절할 수 없습니다.
- 두 콜백도 `spin()` 안에서 다른 콜백과 같은 줄에 서서 실행됩니다(05장). 짧게 끝내야 합니다.

실행해 보면(터미널 1에서 노드, 터미널 2에서 `ros2 param set`) 이렇게 나옵니다. 실제 출력입니다.

```text
# 터미널 1
$ ros2 run ros2_study param_callbacks
# 터미널 2
$ ros2 param set /param_callbacks rate 2.0
Set parameter successful
$ ros2 param set /param_callbacks rate 2.0        # 같은 값으로 한 번 더
Set parameter successful
$ ros2 param set /param_callbacks greeting 안녕
Set parameter successful
$ ros2 param set /param_callbacks rate -1.0
Setting parameter failed: rate는 0보다 커야 합니다
$ ros2 param get /param_callbacks rate
Double value is: 2.0
```

```text
# 터미널 1 로그 (시각 생략, 반복되는 hello 줄 일부 생략)
[param_callbacks]: hello
[param_callbacks]: 설정됨: rate = 2.0
[param_callbacks]: 타이머 주기 변경 → 2.0 Hz
[param_callbacks]: hello
[param_callbacks]: 설정됨: rate = 2.0
[param_callbacks]: hello
[param_callbacks]: 설정됨: greeting = 안녕
[param_callbacks]: 안녕
```

- 같은 값 `2.0`을 다시 넣었을 때도 post_set은 불려서 `설정됨`이 찍히지만, 비교 덕분에 `타이머 주기 변경`은 찍히지 않습니다.
- `rate -1.0`은 검증(on_set)에서 거절되어 값이 2.0 그대로이고, 거절된 변경에는 post_set 자체가 불리지 않습니다.

| 방식 | 장점 | 단점 |
|---|---|---|
| 타이머에서 매번 다시 읽기 (`node_basics.py`) | 코드가 가장 단순 | 다음 틱까지 늦게 반영. 매번 읽는 비용 |
| 파라미터 콜백 (`param_callbacks.py`) | 바뀌는 순간 반응, 잘못된 값 거절 | 콜백 코드가 늘어남 |

### 세 콜백을 한 번에: 요청 하나가 거치는 순서

[`param_stages.py`](../../ws/src/ros2_study/ros2_study/param_stages.py)는 세 콜백을 모두 등록하고, 각 단계에서 받은 목록을 로그로 찍습니다. `ros2 param set` 한 번이 이렇게 흘러갑니다.

```
ros2 param set ...
      │  요청 목록 [rate=50.0]
      ▼
 ① pre_set   요청 목록을 "고친다" ── 고친 목록을 return
      │  [rate=10.0]
      ▼
 ② on_set    고친 목록을 "검증한다" ──┬─ 하나라도 거절 → 아무것도 안 바뀜, CLI에 reason 출력, ③ 안 불림
      │                              └─ 통과 ↓
      ▼                                   값 적용
 ③ post_set  적용된 목록에 "반응한다" (거절 불가)
```

**① pre_set: 요청을 고친다**

```python
def pre_set(self, params):
    out = []
    for p in params:
        if p.name == 'rate' and p.value > MAX_RATE:
            p = Parameter('rate', value=MAX_RATE)  # 보정: 상한으로 깎기
        out.append(p)
        if p.name == 'mode' and p.value in MODE_RATES:
            out.append(Parameter('rate', value=MODE_RATES[p.value]))  # 끼워 넣기
    return out
```

- 받은 목록을 바탕으로 **새 목록을 돌려줍니다.** 돌려준 목록이 다음 단계(on_set)로 갑니다.
- 쓰임새:
  - **보정:** 범위를 넘는 값을 깎거나 단위를 맞춥니다(`rate 50` → `10`).
  - **연관 파라미터 같이 바꾸기:** `mode fast` 하나만 바꿔도 거기에 맞는 `rate 10.0`이 같은 요청에 들어가서, 둘이 함께 검증되고 함께 적용됩니다.
- 주의: 요청한 사람은 `Set parameter successful`만 보고, 값이 보정된 줄은 모릅니다. 보정했다면 로그를 남기세요.

**② on_set: 검증하고 거절한다**

```python
def on_set(self, params):
    for p in params:
        if p.name == 'rate' and p.value <= 0.0:
            return self.reject('rate는 0보다 커야 합니다')
        if p.name == 'mode' and p.value not in MODE_RATES:
            return self.reject(f'mode는 {"/".join(MODE_RATES)} 중 하나여야 합니다')
        if p.name == 'greeting' and not p.value.strip():
            return self.reject('greeting은 비울 수 없습니다')
    return SetParametersResult(successful=True)
```

- `successful=False`를 돌려주면 이번 목록 **전체**가 적용되지 않고, `reason`이 요청한 쪽 CLI에 그대로 나옵니다.
- 쓰임새: 범위 검사, 정해진 값만 허용(enum), 비어 있으면 안 되는 값, 여러 파라미터 사이의 관계 검사(예: `min < max`), "동작 중에는 이 값을 바꿀 수 없음".
- 주의: **여기서는 아무것도 실행하지 마세요(부수 효과 금지).** 검증만 합니다. 여기서 타이머를 바꿨는데 뒤에서 거절되면, 값은 그대로인데 동작만 바뀐 상태가 됩니다. 반응은 ③에서 합니다.

**③ post_set: 적용된 뒤 반응한다**

```python
def post_set(self, params):
    for p in params:
        if p.name == 'rate':
            period_ns = int(1e9 / p.value)
            if self.timer.timer_period_ns != period_ns:
                self.timer.timer_period_ns = period_ns
                self.timer.reset()
```

- 검증을 통과해 값이 **실제로 적용된 뒤에만** 불립니다. 거절할 수 없습니다.
- 쓰임새: 타이머 주기 바꾸기, 장치 다시 연결하기, 바뀐 설정을 다른 노드에 알리기.
- 주의: 위에서 본 것처럼 요청에 들어 있었다고 값이 바뀐 건 아니므로, 필요하면 직접 비교합니다. 짧게 끝내야 합니다(05장).

**실행 결과** (터미널 1: `ros2 run ros2_study param_stages`, 터미널 2: 아래 명령. 실제 출력이며, 2초마다 찍히는 틱 보고 줄은 일부만 남김)

| 터미널 2 요청 | ① pre_set이 고친 결과 | ② on_set | ③ post_set | 결과 |
|---|---|---|---|---|
| `rate 5.0` | 그대로 | 통과 | 타이머 5 Hz로 | 2초 틱 1회 → 10회 |
| `mode fast` | `mode='fast', rate=10.0` (끼워 넣음) | 통과 | 타이머 10 Hz로 | 2초 틱 20회 |
| `rate 50.0` | `rate=10.0` (보정) | 통과 | 이미 10이라 타이머 그대로 | `get rate` → 10.0 |
| `mode turbo` | 그대로 | **거절** | 안 불림 | CLI: `mode는 slow/fast 중 하나여야 합니다` |
| `greeting ''` | 그대로 | **거절** | 안 불림 | CLI: `greeting은 비울 수 없습니다` |
| `rate -1.0` | 그대로 | **거절** | 안 불림 | CLI: `rate는 0보다 커야 합니다` |
| `greeting 안녕` | 그대로 | 통과 | (rate 아님) | 보고 줄이 `[안녕]`으로 바뀜 |

```text
# 터미널 1 로그 일부 (시각 생략)
[param_stages]: ① pre_set  받은 요청: mode='fast'
[param_stages]:    pre_set  고친 요청: mode='fast', rate=10.0
[param_stages]: ② on_set   검증할 목록: mode='fast', rate=10.0
[param_stages]: ③ post_set 적용된 목록: mode='fast', rate=10.0
[param_stages]:    post_set 타이머 주기 변경 → 10.0 Hz
[param_stages]: [hello] 최근 2초 틱 20회
[param_stages]: ① pre_set  받은 요청: rate=50.0
[param_stages]:    pre_set  고친 요청: rate=10.0
[param_stages]: ② on_set   검증할 목록: rate=10.0
[param_stages]: ③ post_set 적용된 목록: rate=10.0
[param_stages]: ① pre_set  받은 요청: mode='turbo'
[param_stages]: ② on_set   검증할 목록: mode='turbo'
[param_stages]:    on_set   거절: mode는 slow/fast 중 하나여야 합니다
```

한 줄로 정리하면 **"① 고치고, ② 판정하고, ③ 반응한다. 판정하는 곳에서 행동하지 않고, 반응하는 곳에서 판정하지 않는다."**

<details><summary>생각해 보기: on_set 안에서 타이머 주기를 바꾸면 무엇이 문제일까?</summary>
on_set 콜백은 여러 개 등록될 수 있고, 내 콜백이 통과시켜도 다른 콜백이 거절할 수 있습니다. 그러면 파라미터 값은 옛 값 그대로인데 타이머만 새 주기로 바뀌어, <code>ros2 param get</code>으로 본 값과 실제 동작이 달라집니다. 그래서 행동은 값이 확정된 뒤 불리는 post_set에서 합니다.
</details>

## 다른 노드의 파라미터를 코드에서 다루기

### 왜 필요한가

`ros2 param set`은 사람이 터미널에서 하나씩 바꿀 때 편합니다. 그런데 같은 일을 **프로그램이** 해야 할 때가 있습니다.

- **중앙 튜너 / GUI**: 슬라이더를 움직이면 여러 노드의 게인(gain)·주기를 바꿔 주는 도구 (`rqt_reconfigure`가 바로 이런 도구입니다).
- **설정 담당 노드**: 시스템이 뜬 뒤 상황(실내/실외, 저속/고속 모드)에 맞춰 다른 노드들의 설정을 한꺼번에 바꾸는 노드.
- **모니터링**: 각 노드가 지금 어떤 값으로 돌고 있는지 읽어서 기록하는 노드.

### 다시 보기: 파라미터 = 서비스 호출

앞의 [파라미터는 서비스다](#파라미터는-서비스다)에서 본 것처럼, 파라미터를 가진 노드에는 `get_parameters`, `set_parameters` 같은 서비스 서버가 자동으로 생깁니다. 그러니 "다른 노드의 파라미터를 바꾼다" = "`/<노드이름>/set_parameters` 서비스를 호출한다"입니다. `ros2 param set`도, 아래의 우리 코드도 모두 이 서비스의 클라이언트입니다.
(`get_type_description`은 파라미터와 상관없는 Jazzy의 다른 기능입니다.) 그러니 "다른 노드의 파라미터를 바꾼다" = "`/<노드이름>/set_parameters` 서비스를 호출한다"입니다. `ros2 param set`도, 아래의 우리 코드도 모두 이 서비스의 클라이언트입니다.

```
 param_client 노드                                   node_basics 노드
┌──────────────────────┐  /node_basics/set_parameters  ┌─────────────────────────┐
│ AsyncParameterClient │ ── Request [greeting, rate] ─▶│ (rclpy가 만든 서비스 서버) │
│                      │ ◀─ Response [결과, 결과]  ─────│  선언·범위 검사 → 값 저장  │
└──────────────────────┘                               └───────────┬─────────────┘
                                                                   │ 성공한 변경마다
                                                                   ▼
                                                        /parameter_events 토픽 발행
```

`set_parameters`와 `set_parameters_atomically`의 차이는 공식 문서([About parameters](https://docs.ros.org/en/jazzy/Concepts/Basic/About-Parameters.html))에 이렇게 적혀 있습니다. `set_parameters`는 파라미터마다 결과를 따로 돌려주고, `set_parameters_atomically`는 "결과를 하나만 돌려주므로, 하나가 실패하면 전부 실패"합니다. rclpy 소스(`Node.set_parameters`)를 보면 실제로 목록을 돌면서 **한 개씩** 적용합니다. 이 차이는 아래 실행 결과에서 바로 보입니다.

### 코드 읽기: `param_client.py`의 `main()`

소스: [`ws/src/ros2_study/ros2_study/param_client.py`](../../ws/src/ros2_study/ros2_study/param_client.py)

서비스 클라이언트를 직접 6개 만들어도 되지만, rclpy(Jazzy)에는 이걸 묶어 둔 `rclpy.parameter_client.AsyncParameterClient`가 있습니다. Jazzy 컨테이너에서 `list_parameters / get_parameters / set_parameters / set_parameters_atomically / describe_parameters / wait_for_services` 메서드가 있는 것을 확인했고, 모두 `Future`를 돌려줍니다(이름 그대로 **비동기**).

#### 1) 대상 노드 이름으로 클라이언트 만들기

```python
node = Node('param_client')
target = node.declare_parameter('target', 'node_basics').value
client = AsyncParameterClient(node, target)
```

- 대상 노드 이름을 하드코딩하지 않고 이 노드의 파라미터 `target`으로 받습니다. `ros2 run ros2_study param_client --ros-args -p target:=param_stages`처럼 다른 노드를 겨눌 수 있습니다.
- `AsyncParameterClient(node, 'node_basics')`는 `/node_basics/get_parameters` 등의 서비스 클라이언트를 내 노드(`node`) 안에 만듭니다. 응답을 받아 future에 넣는 일은 **내 노드를 spin하는 executor**가 합니다(04장 ④).

#### 2) 기다리는 방법: 04장과 같은 패턴

```python
def wait(future):
    rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
    if not future.done():
        raise TimeoutError(f'/{target} 응답 없음')
    return future.result()

if not client.wait_for_services(timeout_sec=5.0):
    log.error(f'/{target} 의 파라미터 서비스를 찾지 못했습니다')
    return
```

- `wait_for_services()`: 대상 노드의 파라미터 서비스가 discovery로 보일 때까지 기다립니다. 대상이 없는데 요청을 보내면 응답이 영원히 오지 않으므로 timeout을 줍니다.
- `wait()`는 `main()`에서, 즉 **콜백 밖에서** 부릅니다. 그래서 `spin_until_future_complete`가 executor를 직접 돌려 응답을 꺼낼 수 있습니다. 응답을 꺼내 주는 executor가 이미 내 콜백을 실행하고 있으면 이 방법은 쓸 수 없습니다(04장 데드락과 같은 뿌리). 실제로 타이머 콜백 안에서 `spin_until_future_complete`를 불러 봤더니 Jazzy rclpy는 기다리지도 않고 `RuntimeError: Executor is already spinning`을 던졌습니다(확인 문제 2). 콜백 안에서 써야 한다면 `client.set_parameters(..., callback=함수)`처럼 done 콜백을 넘기고 바로 return 하면 됩니다(04장의 해결책 1).

#### 3) 목록 → 값 읽기

```python
names = wait(client.list_parameters()).result.names
values = wait(client.get_parameters(['greeting', 'rate'])).values
for name, v in zip(['greeting', 'rate'], values):
    log.info(f'get: {name} = {parameter_value_to_python(v)!r}')
```

- 서비스 응답을 그대로 돌려받습니다. `ListParameters` 응답은 `result.names`, `GetParameters` 응답은 `values`(요청한 이름 순서대로)입니다.
- `values`의 원소는 `ParameterValue` 메시지입니다. 타입 번호(`type`)와 `bool_value`, `double_value`, `string_value` ... 필드가 전부 들어 있는 구조라(아래 `/parameter_events` 출력에서 생김새가 보입니다), `rclpy.parameter.parameter_value_to_python()`으로 파이썬 값 하나로 바꿔 찍습니다.

#### 4) 쓰기: 성공 2개 + 거절 1개를 한 번에

```python
requests = [
    Parameter('greeting', value='코드에서 바꿈'),
    Parameter('rate', value=2.0),
    Parameter('rate', value=50.0),   # 범위(0.1~10.0) 밖 → 거절돼야 함
]
results = wait(client.set_parameters(requests)).results
for p, r in zip(requests, results):
    status = '성공' if r.successful else f'거절: {r.reason}'
```

- 결과(`SetParametersResult`)가 파라미터마다 하나씩 오고, 거절이면 `reason`에 이유 문자열이 들어 있습니다. 거절 이유는 클라이언트가 지어내는 게 아니라 **대상 노드가 만들어 보낸 것**입니다. 범위 검사는 `node_basics`가 선언할 때 붙인 `FloatingPointRange`로 rclpy가 해 줍니다.

### 실행 결과

터미널 1에서 `ros2 run ros2_study node_basics`, 터미널 2에서 `ros2 run ros2_study param_client`:

```text
[INFO] [1795761599.512305933] [param_client]: list: ['use_sim_time', 'start_type_description_service', 'greeting', 'rate']
[INFO] [1795761599.514159797] [param_client]: get: greeting = '안녕, ROS 2'
[INFO] [1795761599.514717030] [param_client]: get: rate = 1.0
[INFO] [1795761599.516800797] [param_client]: set: greeting=코드에서 바꿈 → 성공
[INFO] [1795761599.517246727] [param_client]: set: rate=2.0 → 성공
[INFO] [1795761599.517661253] [param_client]: set: rate=50.0 → 거절: Parameter rate out of range Min: 0.1, Max: 10.0, value: 50.0
```

같은 시간 `node_basics` 쪽 로그:

```text
[INFO] [1795761598.958893984] [node_basics]: 안녕, ROS 2 #2
[INFO] [1795761599.958545689] [node_basics]: rate 변경 → 2.0 Hz
[INFO] [1795761599.958990402] [node_basics]: 코드에서 바꿈 #3
[INFO] [1795761600.458975324] [node_basics]: 코드에서 바꿈 #4
[INFO] [1795761600.958919591] [node_basics]: 코드에서 바꿈 #5
```

읽을거리:

- `list`에 우리가 선언하지 않은 `use_sim_time`, `start_type_description_service`가 섞여 있습니다. 모든 노드가 기본으로 갖는 파라미터입니다.
- **한 요청 안에서 `rate=2.0`은 성공, `rate=50.0`은 거절**됐습니다. 이후 틱 간격이 0.5초인 것으로 보아 최종 값은 2.0입니다(CLI로 `rate 50.0`을 거절당한 뒤 `ros2 param get /node_basics rate`를 해 봐도 `Double value is: 1.0`, 즉 원래 값 그대로였습니다). `set_parameters`가 하나씩 적용하기 때문입니다. "셋 다 되거나 셋 다 안 되거나"가 필요하면 `set_parameters_atomically`를 씁니다.
- 대상을 01장 보충의 `param_stages`로 바꿔(`--ros-args -p target:=param_stages`) 같은 요청을 보내면, 대상 노드 로그에 ①pre_set → ②on_set → ③post_set 묶음이 **파라미터마다 한 번씩, 세 번** 찍혀서 하나씩 적용된다는 것이 그대로 보입니다. 이때 `rate=50.0`은 `param_stages`의 pre_set이 `rate=10.0`으로 깎은 뒤 통과시켜서, 클라이언트에는 `set: rate=50.0 → 성공`으로 돌아왔습니다. **"성공"이 "보낸 값 그대로 저장됨"을 뜻하지는 않습니다.** 확실히 하려면 다시 get 하거나 `/parameter_events`를 봅니다.
- 대상이 없으면(`-p target:=nobody`) 5초 뒤 `/nobody 의 파라미터 서비스를 찾지 못했습니다`를 찍고 끝납니다.
- 이 컨테이너(같은 머신, 루프백)에서는 list 요청부터 마지막 set 결과까지 약 5 ms(…599.512 → …599.517) 걸렸습니다. 서비스 왕복 3번입니다. 네트워크 너머의 노드라면 왕복마다 그만큼 더 듭니다.
- **값이 저장된 시각과 노드 동작이 바뀐 시각은 다릅니다.** set은 …599.517에 끝났지만, `node_basics`의 출력이 바뀐 건 다음 타이머 틱인 …599.958입니다. `node_basics`가 타이머 콜백에서 값을 다시 읽도록 짜여 있기 때문입니다. 즉시 반응해야 하는 노드라면 01장 보충의 set 콜백(`param_stages`)처럼 변경 시점에 반응하도록 만들어야 합니다.

## 파라미터 변경 구독하기

### `/parameter_events` 토픽

서비스로 값을 바꾸는 쪽과 별개로, **값이 바뀌었다는 사실**은 토픽으로 퍼집니다. 파라미터 변경이 성공하면 그 노드가 `/parameter_events` 토픽(`rcl_interfaces/msg/ParameterEvent`)에 메시지를 발행합니다. 메시지 구조:

```text
$ ros2 interface show rcl_interfaces/msg/ParameterEvent   (주석·하위 필드 일부 생략)
builtin_interfaces/Time stamp
string node                    # 바뀐 노드의 전체 이름
Parameter[] new_parameters     # 새로 생긴 파라미터
Parameter[] changed_parameters # 값이 바뀐 파라미터
Parameter[] deleted_parameters # 지워진 파라미터
```

인터페이스 주석에 따르면 한 메시지는 원자적인 한 번의 변경이라, 같은 이름은 세 목록 중 한 곳에만 들어갑니다.

### 직접 보기: `ros2 topic echo`

터미널 1 `node_basics`, 터미널 2 `ros2 topic echo /parameter_events`, 터미널 3에서 `ros2 param set /node_basics greeting hi`:

```text
stamp:
  sec: 1795761629
  nanosec: 112832256
node: /node_basics
new_parameters: []
changed_parameters:
- name: greeting
  value:
    type: 4
    bool_value: false
    integer_value: 0
    double_value: 0.0
    string_value: hi
    byte_array_value: []
    bool_array_value: []
    integer_array_value: []
    double_array_value: []
    string_array_value: []
deleted_parameters: []
---
```

`type: 4`는 문자열(`PARAMETER_STRING`)이고, 그래서 `string_value`만 의미가 있습니다. 나머지 필드는 모두 기본값으로 함께 실려 옵니다.

### 언제 발행되고, 언제 안 되나 (직접 확인)

이어서 몇 가지를 더 해 보고 echo에 무엇이 찍히는지 봤습니다.

| 한 일 | CLI 결과 | `/parameter_events` |
|---|---|---|
| `ros2 param set /node_basics greeting hi` | `Set parameter successful` | `changed greeting = hi` 1건 |
| 같은 명령을 **같은 값**으로 한 번 더 | `Set parameter successful` | `changed greeting = hi` **또 1건** |
| `ros2 param set /node_basics rate 50.0` (범위 밖) | `Setting parameter failed: Parameter rate out of range Min: 0.1, Max: 10.0, value: 50.0` | **없음** |
| `ros2 param delete /node_basics greeting` | `Deleting parameter failed: Static parameter cannot be undeclared` | 없음 |
| `param_client` 실행 (greeting·rate 성공, rate=50 거절) | 위 실행 결과와 같음 | `changed greeting`, `changed rate = 2.0` **2건(메시지 따로)**, 거절된 것은 없음 |

정리하면:

- **성공한 set만** 이벤트가 나갑니다. 거절된 set은 아무 흔적도 남기지 않습니다. rclpy 소스(`Node._set_parameters_atomically_common`)도 검사·on_set 콜백을 통과한 뒤에만 `ParameterEvent`를 만들어 발행합니다.
- **값이 같아도** 이벤트가 나갑니다(이름은 "changed"지만 실제로 바뀌었는지 비교하지 않습니다). 구독하는 쪽에서 "진짜 바뀌었나"가 중요하면 직접 이전 값과 비교해야 합니다.
- `param_client`의 set 요청 1번에 이벤트는 **2건**이었습니다(stamp …606043955, …606213442). `set_parameters`가 하나씩 적용하기 때문입니다.
- 선언할 때 정적 타입(기본)으로 만든 파라미터는 지울 수 없습니다. `deleted_parameters`를 보려면 `dynamic_typing=True`로 선언한 파라미터가 필요합니다. 임시 노드로 시험한 결과는 아래 watcher 출력에 있습니다.

### 코드 읽기: `param_client.py`의 `watcher()`

```python
def on_event(msg: ParameterEvent):
    for kind, params in (('new', msg.new_parameters),
                         ('changed', msg.changed_parameters),
                         ('deleted', msg.deleted_parameters)):
        for p in params:
            log.info(f'{msg.node}: {kind} {p.name} = {parameter_value_to_python(p.value)!r}')

node.create_subscription(ParameterEvent, '/parameter_events', on_event,
                         qos_profile_parameter_events)
```

- 특별한 API가 아니라 02장의 **평범한 구독**입니다. 대상 노드 이름을 주지 않았으므로 **모든 노드**의 변경이 들어옵니다. 어느 노드인지는 `msg.node`로 구분합니다.
- QoS는 rclpy가 발행 쪽에 쓰는 `qos_profile_parameter_events`를 그대로 맞췄습니다(03장: QoS가 안 맞으면 연결이 안 됨). `ros2 topic info -v /parameter_events`로 보면 발행·구독 모두 `RELIABLE`, `VOLATILE`이었습니다.
- rclpy에는 이 구독을 감싼 `rclpy.parameter_event_handler.ParameterEventHandler`도 있습니다(Jazzy에 있음 확인). 소스를 보면 생성자에서 똑같이 `/parameter_events`를 `qos_profile_parameter_events`로 구독하고, `add_parameter_callback(parameter_name, node_name, callback)`으로 "특정 노드의 특정 파라미터"만 골라 콜백을 받게 해 줍니다. 여기서는 토픽이라는 사실이 잘 보이도록 직접 구독했습니다. 사용법은 공식 튜토리얼(아래 더 읽을거리)에 있습니다.

### 실행 결과

터미널 1 `ros2 run ros2_study param_watcher`, 터미널 2 `node_basics`, 터미널 3에서 앞의 표와 같은 순서로 명령 실행:

```text
[INFO] [1795761629.130127990] [param_watcher]: /node_basics: changed greeting = 'hi'
[INFO] [1795761631.598135512] [param_watcher]: /node_basics: changed greeting = 'hi'
[INFO] [1795761641.607828258] [param_watcher]: /node_basics: changed greeting = '코드에서 바꿈'
[INFO] [1795761641.609308064] [param_watcher]: /node_basics: changed rate = 2.0
```

`new`와 `deleted`를 보기 위해 (저장소에 넣지 않은) 임시 노드 `late_declare`를 따로 돌렸습니다. 이 노드는 생성 직후 `early`를 선언하고, 2초 쉰 뒤 `late`와 `temp`(`dynamic_typing=True`)를 선언합니다. 그 뒤 `ros2 param delete /late_declare temp`:

```text
[INFO] [1795761693.070948223] [param_watcher]: /late_declare: new late = 2
[INFO] [1795761693.071879860] [param_watcher]: /late_declare: new temp = 'x'
[INFO] [1795761695.664942172] [param_watcher]: /_ros2cli_daemon_72_963ce344aef74d0e9d3fde7742759723: new use_sim_time = False
[INFO] [1795761695.665672361] [param_watcher]: /_ros2cli_daemon_72_963ce344aef74d0e9d3fde7742759723: new start_type_description_service = False
[INFO] [1795761696.237026832] [param_watcher]: /late_declare: deleted temp = None
```

여기서 볼 것이 세 가지입니다.

1. **선언도 이벤트입니다** (`new late`, `new temp`). rclpy의 `declare_parameter`가 내부적으로 set과 같은 경로를 타기 때문입니다.
2. **그런데 생성 직후 선언한 `early`는 안 보였습니다.** `node_basics`를 띄울 때도 `greeting`·`rate`의 `new` 이벤트는 한 번도 받지 못했습니다. 노드가 막 생겨 아직 구독자와 discovery로 연결되기 전에 발행됐고, 토픽이 `VOLATILE`이라 늦게 연결된 구독자에게 다시 보내 주지 않기 때문으로 보입니다(2초 뒤 선언한 `late`는 받았다는 점이 이를 뒷받침합니다). **`/parameter_events`만으로 "노드의 현재 설정 전체"를 알 수는 없습니다.** 처음 상태는 `get_parameters`로 읽고, 이후 변화를 이벤트로 따라가야 합니다.
3. **우리가 건드리지 않은 노드도 발행합니다.** `ros2` CLI가 쓰는 데몬 노드(`_ros2cli_daemon_...`)가 새로 뜨면서 자기 기본 파라미터를 `new`로 알렸습니다. `ros2 topic info -v /parameter_events`를 했을 때도 발행자가 4개였는데(`node_basics`, `param_watcher`, CLI 노드, CLI 데몬), **구독만 하는 `param_watcher`조차 발행자로 잡혀 있었습니다.** rclpy `Node` 생성자가 모든 노드에 `/parameter_events` 발행자를 만들기 때문입니다. 노드가 많은 시스템에서는 이 토픽에 모든 노드의 변경이 섞여 흐른다는 뜻이므로, 구독 쪽에서 `msg.node`로 걸러야 합니다.

> 발표용 한 문장: "파라미터를 **바꾸는 건 서비스**(요청한 쪽만 결과를 받음), 바뀌었다는 **소식은 토픽**(`/parameter_events`, 누구나 들을 수 있음)입니다."

## 발표할 때 이렇게 설명하기

> "파라미터는 노드마다 따로 가진 설정값입니다. 선언할 때 타입과 범위가 정해지고, 값은 코드 기본값, YAML, 명령줄, launch로 넣는데, 명령줄에서는 나중에 적은 값이 이깁니다. 실행 중에 `ros2 param set`으로 바꾸면 노드 안에서 세 단계 콜백이 돕니다. pre_set이 요청을 고치고, on_set이 검증해서 거절할 수 있고, 통과하면 값이 적용된 뒤 post_set에서 반응합니다. 사실 이건 전부 서비스 호출이라, 다른 노드도 코드로 똑같이 읽고 쓸 수 있고, 바뀐 내용은 `/parameter_events` 토픽으로 모두에게 알려집니다."

## 자주 하는 실수

- **정수와 실수를 섞기**: `rate`가 double이면 `-p rate:=5`나 YAML의 `rate: 2`는 시작할 때 노드를 죽입니다(`InvalidParameterTypeException`). 실행 중 `param set`은 거절만 합니다. 실수는 항상 `5.0`처럼 씁니다.
- **YAML의 노드 이름이 실제 이름과 다름**: `-r __node:=other`나 네임스페이스를 붙이면 `node_basics:` 섹션은 경고 없이 무시되고 기본값으로 뜹니다. 확실하지 않으면 `ros2 param get`으로 확인하거나 `/**`를 씁니다.
- **선언하지 않은 이름에 값 주기**: `-p nope:=1`은 경고 없이 무시됩니다. 오타도 마찬가지입니다.
- **"성공 = 내가 보낸 값이 들어감"이라고 믿기**: pre_set이 값을 보정하면 요청한 쪽은 `successful`만 봅니다. 중요한 값은 set 뒤에 get으로 확인합니다.
- **on_set에서 행동하기**: on_set은 검증만 합니다. 다른 on_set 콜백이 거절하면 값은 그대로인데 동작만 바뀝니다. 행동은 post_set에서 합니다.
- **post_set의 목록 = 바뀐 값이라고 믿기**: 같은 값으로 다시 set해도, `param load`로 여러 개를 넣어도 목록에 들어옵니다. 실제로 바뀌었을 때만 할 일은 직접 비교합니다.
- **`set_parameters`가 원자적이라고 믿기**: 목록을 하나씩 적용하므로 일부만 성공할 수 있습니다. 전부 아니면 전무가 필요하면 `set_parameters_atomically`를 씁니다.
- **`/parameter_events`만으로 현재 값을 알려고 하기**: 늦게 뜬 감시 노드는 지난 이벤트를 받지 못합니다. 먼저 get으로 현재 값을 읽고, 그다음 이벤트를 따라갑니다.

## 확인 문제

**Q1.** `ros2 run ros2_study node_basics --ros-args -p rate:=5.0 --params-file node_basics.yaml`(YAML에는 `rate: 2.0`)로 실행하면 rate는 몇 Hz일까요? 순서를 바꾸면?

<details><summary>정답</summary>

2.0 Hz입니다. 명령줄에서는 나중에 준 값이 이기므로 뒤에 온 YAML이 `-p`를 덮어씁니다. `--params-file node_basics.yaml -p rate:=5.0` 순서면 5.0 Hz입니다(둘 다 실제로 확인).
</details>

**Q2.** YAML로 값을 줬는데 노드가 계속 기본값으로 돕니다. 에러 메시지도 없습니다. 무엇부터 확인하나요?

<details><summary>정답</summary>

YAML의 최상위 키와 실제 노드 이름(`ros2 node list`, 네임스페이스 포함)이 맞는지 봅니다. `-r __node:=other`나 `-r __ns:=/robot1`로 이름이 바뀌면 `node_basics:` 섹션은 조용히 무시됩니다. 이름과 상관없이 적용하려면 `/**`를 씁니다. 그다음 `ros__parameters` 철자(밑줄 두 개)와 파라미터 이름 오타를 확인합니다. 선언되지 않은 이름도 경고 없이 무시되기 때문입니다.
</details>

**Q3.** `ros2 param load /node_basics my_params.yaml`(dump로 만든 파일)에서 `start_type_description_service failed`가 뜹니다. 나머지 값은 들어갔을까요?

<details><summary>정답</summary>

들어갔습니다. load는 파라미터마다 따로 set하므로 읽기 전용 파라미터 하나만 실패하고 `greeting`, `rate`, `use_sim_time`은 성공했습니다. 이 파라미터는 시작할 때만 정할 수 있어서, 같은 파일을 `--params-file`로 주고 새로 시작하면 에러가 없습니다.
</details>

**Q4.** `ros2 param get`을 쓰지 않고, `ros2 service call`만으로 `/node_basics`의 `rate`를 읽으려면?

<details><summary>정답</summary>

```bash
ros2 service call /node_basics/get_parameters rcl_interfaces/srv/GetParameters "{names: [rate]}"
```

파라미터는 노드가 자동으로 만드는 서비스(`get_parameters`, `set_parameters`, `list_parameters`, `describe_parameters` 등) 위에서 동작하고, `ros2 param`은 이 서비스들의 클라이언트입니다.
</details>

**Q5.** `param_client`가 `[greeting='코드에서 바꿈', rate=2.0, rate=50.0]`을 `set_parameters` 한 번으로 보냈습니다. 요청이 끝난 뒤 `node_basics`의 `rate`는 얼마이고, 왜 그런가요? `set_parameters_atomically`로 보냈다면 어떻게 달라질까요?

<details><summary>답</summary>

`rate`는 2.0입니다. `set_parameters`는 목록을 하나씩 적용하므로 `rate=2.0`은 성공해 저장되고, 뒤의 `rate=50.0`만 범위 밖이라 거절됩니다(실행 결과의 `거절: Parameter rate out of range ...`와 이후 0.5초 틱). `set_parameters_atomically`는 결과가 하나뿐이고 하나라도 실패하면 전부 실패하므로(공식 문서 About parameters), greeting과 rate 모두 바뀌지 않습니다.
</details>

**Q6.** 다음 코드는 어떤 문제가 있나요?

   ```python
   def on_timer(self):
       future = self.client.get_parameters(['rate'])
       rclpy.spin_until_future_complete(self, future)
   ```

<details><summary>답</summary>

타이머 콜백 **안에서** 응답을 기다립니다. 응답을 꺼내 future에 넣어 줄 executor가 이미 이 콜백을 실행 중이라는 점에서 04장 데드락과 같은 구조입니다. 다만 `spin_until_future_complete`는 데드락까지 가지 않고, 이 코드를 `node_basics`에 대고 실제로 돌려 보니 첫 틱에서 바로 `RuntimeError: Executor is already spinning`으로 노드가 죽었습니다(rclpy가 같은 executor를 두 번 돌리는 것을 막음). `get_parameters(['rate'], callback=self.on_rate)`처럼 done 콜백을 넘기고 바로 return 하거나, 이 문서의 `param_client`처럼 콜백 밖(`main`)에서 기다립니다.
</details>

**Q7.** `ros2 param set /node_basics rate 50.0`(거절)과 `ros2 param set /node_basics greeting hi`를 같은 값으로 두 번 했을 때, `/parameter_events`에는 각각 몇 건이 나오나요?

<details><summary>답</summary>

거절된 set은 0건, 같은 값 set은 매번 1건씩(`changed`) 나옵니다. 이벤트는 "성공한 set"마다 나가고, 값이 실제로 바뀌었는지는 비교하지 않습니다. 둘 다 이 문서에서 `ros2 topic echo`로 직접 확인한 결과입니다.
</details>

**Q8.** 감시 노드를 나중에 띄웠더니 이미 떠 있던 `node_basics`의 `greeting`·`rate` 이벤트를 하나도 받지 못했습니다. 감시 노드가 지금 값을 알려면 어떻게 해야 하나요?

<details><summary>답</summary>

`/parameter_events`는 `VOLATILE`이라 구독하기 전에 나간 이벤트(선언 시의 `new` 포함)를 다시 받을 수 없습니다. 실험에서도 노드 생성 직후 선언한 파라미터의 `new` 이벤트는 보이지 않았습니다. 그래서 시작할 때 `get_parameters`(서비스)로 현재 값을 한 번 읽고, 그 뒤 변화는 이벤트로 따라갑니다.
</details>

## 더 읽을거리

- [Concepts: Parameters](https://docs.ros.org/en/jazzy/Concepts/Basic/About-Parameters.html): 선언, 타입, 콜백, 파라미터 서비스 목록
- [Understanding parameters (CLI 튜토리얼)](https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Parameters/Understanding-ROS2-Parameters.html): `ros2 param` list/get/set/dump/load
- [Passing ROS arguments to nodes via the command-line](https://docs.ros.org/en/jazzy/How-To-Guides/Node-arguments.html): `-p`, `--params-file`, 와일드카드 `*`/`**`
- [Using parameters in a class (Python)](https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Using-Parameters-In-A-Class-Python.html): 선언과 descriptor
- [Managing large projects (launch)](https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Using-ROS2-Launch-For-Large-Projects.html): launch에서 YAML·파라미터 넘기기
- [Monitoring for parameter changes (Python)](https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Monitoring-For-Parameter-Changes-Python.html): `ParameterEventHandler`로 자기 노드·다른 노드의 파라미터 변경에 반응하기.
- [rclpy API: Parameters](https://docs.ros.org/en/jazzy/p/rclpy/api/parameters.html): `Parameter`, `parameter_value_to_python` 등 rclpy 파라미터 API.
- [01장 노드](01_node.md), [04장 서비스](04_service.md), [05장 executor](05_executor.md), [07장 동기화](07_sync.md): 이 장과 이어지는 장
