# 08. 한 프로세스에 모으기: Composition과 intra-process 통신

> 핵심 질문: 노드를 한 프로세스에 넣고 intra-process 통신을 켜면 지연이 얼마나, 왜 줄어드나?

## 1. 이 장의 목표

- "노드를 어떻게 나눌까(역할)"와 "노드를 몇 개의 프로세스에 담을까(배치)"가 **서로 다른 결정**이라는 것을 설명할 수 있다.
- intra-process 통신이 06장의 ①~⑥ 중 **어느 단계를 건너뛰는지**, 그리고 `unique_ptr`로 주고받을 때만 **복사 없이(zero-copy)** 전달된다는 것을 포인터 주소로 직접 확인할 수 있다.
- 같은 측정을 (A) 별도 프로세스, (B) 한 프로세스 + intra-process 끔, (C) 한 프로세스 + intra-process 켬으로 돌려 보고, 숫자 차이와 그 대가(장애 격리, QoS 제약, 복사가 다시 생기는 조건)를 함께 말할 수 있다.

## 2. 핵심 개념

### 노드와 프로세스는 다른 것이다

- **노드**는 기능 단위입니다. "카메라 드라이버", "이미지 전처리", "물체 인식"처럼 **역할로** 나눕니다(01장).
- **프로세스**는 OS가 실행하는 프로그램 단위입니다. 지금까지는 `ros2 run`으로 노드 1개 = 프로세스 1개였습니다.
- ROS 2(C++)에서는 노드를 **컴포넌트**(공유 라이브러리 `.so` 안의 클래스)로 만들어 두면, 실행할 때 **컨테이너 프로세스 하나에 여러 노드를 올릴 수 있습니다**. 이것을 **Composition**이라고 합니다.
- 노드 코드는 그대로 두고, "같은 프로세스에 둘지 따로 둘지"를 **실행(배포) 시점에** 정할 수 있다는 것이 핵심입니다. 공식 문서도 이것을 "process layout을 deploy-time 결정으로 만든다"고 표현합니다. 즉, 노드 분리는 설계 결정, 프로세스 배치는 **성능과 견고성 사이의 배포 결정**입니다.

### intra-process 통신은 무엇을 건너뛰나

같은 프로세스 안의 발행자와 구독자는 같은 메모리를 봅니다. 그래서 rclcpp는 `use_intra_process_comms`를 켠 노드끼리는 메시지를 DDS로 보내지 않고 **포인터를 직접 넘깁니다**.

```
06장의 단계: ① stamp  ② 직렬화  ③ DDS 전송  ④ 수신 큐  ⑤ executor  ⑥ 역직렬화 → 콜백

(A) 별도 프로세스 — ros2 run talker / ros2 run listener
    talker 프로세스                     listener 프로세스
    ① → ② 직렬화(CDR) ==③ DDS(공유메모리/UDP)==> ④ DDS 큐 → ⑤ → ⑥ 역직렬화 → 콜백

(B) 한 프로세스, intra-process 끔 — composed.launch.py ipc:=false
    [ component_container 프로세스 하나 ]
    ① → ② 직렬화 ==③' Fast DDS의 프로세스 내 전달(전송 계층 생략)==> ④ → ⑤ → ⑥ 역직렬화 → 콜백

(C) 한 프로세스, intra-process 켬 — composed.launch.py ipc:=true
    [ component_container 프로세스 하나 ]
    ① → publish(unique_ptr) --포인터만 이동--> ④' 구독별 버퍼(depth) → ⑤ → 콜백
         ②③⑥ 없음: 직렬화·DDS·역직렬화를 모두 건너뛰고, 콜백은 "같은 주소"의 메시지를 받음
```

- (B)에서 ③'은 rclcpp가 아니라 **Fast DDS 자체 기능**(intra-process delivery, 기본 켜짐)입니다. 이 기능을 끄면 B가 A 수준으로 느려지는 것으로 확인했습니다(5장 실험 4). 직렬화와 역직렬화(②⑥)는 그대로 남습니다. B의 지연이 메시지 크기에 따라 커지고, 받은 버퍼 주소가 보낸 주소와 다른 것이 그 근거입니다(4장).
- (C)에서 남는 것은 ④'(버퍼에 넣기)와 ⑤(executor가 깨어나 콜백 실행)뿐입니다. 메시지 크기와 상관없는 단계만 남습니다.

### 언제 복사 없이(zero-copy), 언제 복사가 생기나

- `publish(std::unique_ptr<Msg>)` → 구독자가 **하나**이고 콜백이 `UniquePtr`를 받으면: **소유권만 넘어갑니다.** 발행자가 만든 메모리를 구독자가 그대로 받습니다. 주소가 같습니다.
- `publish(const Msg &)`(참조로 발행) → rclcpp가 힙에 **한 번 복사**한 뒤 보냅니다.
- 구독자가 **여러 개**이고 둘 다 `UniquePtr`를 원하면 → 원본은 하나뿐이므로 **나머지에게는 복사본**을 줍니다(실험 1).
- `shared_ptr<const Msg>` 콜백은 여러 구독자가 하나의 메시지를 함께 읽을 수 있지만, 공식 데모 문서는 `const &`나 `shared_ptr`로 발행·구독하면 zero-copy가 일어나지 않는다고 설명합니다. 이 장에서는 `unique_ptr` 경우만 측정했습니다.
- 같은 토픽에 **다른 프로세스의 구독자**가 있으면 → 그쪽으로 보낼 복사본을 만들고 DDS로도 보냅니다. 이 작업이 `publish()` 안에서 일어나므로 같은 프로세스 구독자의 지연도 늘어납니다(실험 2).

### 왜 C++에서만 되나

- Composition은 C++ 클래스를 `.so`에서 불러오는 방식(`rclcpp_components`)입니다. Python 노드는 이 컨테이너에 올릴 수 없습니다.
- intra-process 통신은 **rclcpp의 기능**입니다. rclpy에는 이 경로가 없습니다(이 컨테이너의 rclpy 소스에서 `intra_process`를 검색하면 아무것도 나오지 않습니다). Python 노드 여러 개를 한 프로세스의 executor에 넣을 수는 있지만, 메시지는 RMW를 거쳐 갑니다(B와 같은 종류의 경로).
- 그래서 지연이 중요한 큰 메시지(영상, 점군) 파이프라인은 C++ 컴포넌트로 만드는 경우가 많습니다.

### 대가(trade-off)

- **장애 격리를 잃습니다.** 한 노드가 segfault 등으로 죽으면 같은 프로세스의 노드가 **전부** 함께 죽습니다. 따로 띄우면 하나만 재시작하면 됩니다. 공식 Composition 개념 문서도 "별도 프로세스 = process/fault isolation과 쉬운 디버깅, 한 프로세스 = 낮은 오버헤드"로 둘을 비교합니다.
- **executor를 함께 씁니다.** `component_container`는 SingleThreadedExecutor **하나**로 모든 컴포넌트를 돌립니다. 한 노드의 느린 콜백이 다른 노드의 콜백을 막습니다(05장의 ⑤). 필요하면 `component_container_mt`(MultiThreadedExecutor 하나)나 `component_container_isolated`(컴포넌트마다 executor)를 씁니다.
- **QoS 제약이 있습니다.** Jazzy의 rclcpp(28.1.21) 소스를 직접 확인한 내용입니다.
  - history가 **KEEP_LAST가 아니면**(KEEP_ALL) 발행자/구독자를 만들 때 예외(`allowed only with keep last history qos policy`)를 던집니다(`rclcpp/publisher.hpp`, `subscription.hpp`). 이 경우는 실행해 보지 않았습니다.
  - depth 0도 금지 조건으로 코드에 있지만, 실제로 `depth:=0`을 주면 rclcpp가 먼저 SYSTEM_DEFAULT로 바꿔 버려 예외 없이 동작했습니다(실험 3).
  - durability: 예전 구현은 transient_local을 쓸 수 없었다는 설명이 설계 문서에 남아 있지만, Jazzy rclcpp는 transient_local 발행자에 별도 버퍼를 두고 지원합니다(소스 확인, 실행해 보지는 않음). 이 장의 노드는 기본값 volatile을 씁니다.

## 3. 코드 읽기

소스:
- [`ws/src/ipc_lab/src/talker.cpp`](../../ws/src/ipc_lab/src/talker.cpp)
- [`ws/src/ipc_lab/src/listener.cpp`](../../ws/src/ipc_lab/src/listener.cpp)
- [`ws/src/ipc_lab/launch/composed.launch.py`](../../ws/src/ipc_lab/launch/composed.launch.py)
- [`ws/src/ipc_lab/CMakeLists.txt`](../../ws/src/ipc_lab/CMakeLists.txt)

측정 방식(stamp → 콜백 시작 시각의 차이, `frame_id`의 일련번호로 유실 계산, nearest-rank 백분위수)과 파라미터 이름(`size`, `rate`, `depth`)은 06장 Python 버전과 같습니다. 그래서 숫자를 나란히 놓고 비교할 수 있습니다.

### 3-1. 컴포넌트 = NodeOptions를 받는 생성자

```cpp
class Talker : public rclcpp::Node
{
public:
  explicit Talker(const rclcpp::NodeOptions & options)
  : Node("ipc_talker", options)
  {
    size_ = declare_parameter("size", 1024);  // payload bytes
    const double rate = declare_parameter("rate", 100.0);
    const int depth = declare_parameter("depth", 10);
    pub_ = create_publisher<sensor_msgs::msg::Image>("latency_test", rclcpp::QoS(depth));
    ...
    RCLCPP_INFO(..., "publishing %ld bytes at %.1f Hz (intra-process: %s)", ...,
      get_node_options().use_intra_process_comms() ? "on" : "off");
```

- 컴포넌트가 되려면 `const rclcpp::NodeOptions &` 하나를 받는 생성자가 있어야 합니다. 컨테이너가 노드를 만들 때 `use_intra_process_comms` 같은 설정을 이 `options`에 담아 넘깁니다. **코드에는 intra-process를 켜는 줄이 없습니다.** 켜고 끄는 것은 실행할 때 정합니다.
- 시작할 때 `intra-process: on/off`를 찍어 둡니다. B와 C를 헷갈리지 않으려면 이 줄부터 확인하세요.
- `rclcpp::QoS(depth)`는 KEEP_LAST(depth), RELIABLE, VOLATILE입니다(06장 Python 버전의 기본값과 같음).

### 3-2. Talker: 매번 새 메시지를 만들어 소유권을 넘긴다

```cpp
void tick()
{
  auto msg = std::make_unique<sensor_msgs::msg::Image>();
  msg->height = 1;
  msg->width = msg->step = size_;
  msg->encoding = "mono8";
  msg->data.resize(size_);
  msg->header.frame_id = std::to_string(++seq_);  // 유실 계산용 일련번호
  if (seq_ == 1) {
    RCLCPP_INFO(get_logger(), "seq=1 data addr=%p", static_cast<const void *>(msg->data.data()));
  }
  msg->header.stamp = now();
  pub_->publish(std::move(msg));
}
```

- 06장 Python 버전은 메시지 하나를 재사용했지만, 여기서는 **매번 새로 만듭니다.** `publish(std::move(msg))`는 메시지의 소유권을 넘기는 것이라, 보낸 뒤 `msg`는 비어 있고(nullptr) 다시 쓸 수 없기 때문입니다.
- `msg->data.data()`는 실제 픽셀 버퍼(6 MB면 6 MB짜리 배열)의 주소입니다. 첫 메시지의 주소를 찍어 두고 listener가 받은 주소와 비교합니다.
- **stamp는 할당이 끝난 뒤, publish 직전에** 찍습니다. 그래서 측정값에는 "메시지 만들기"가 들어가지 않고 "전달"만 들어갑니다. 할당 비용은 따로 쟀습니다(4장 끝).
- `frame_id`에 일련번호를 넣는 것은 06장과 같은 실습용 편법입니다. 실제 코드에서는 좌표계 이름을 넣어야 합니다.

### 3-3. Listener: UniquePtr로 받기

```cpp
sub_ = create_subscription<Image>(
  "latency_test", rclcpp::QoS(depth),
  [this](Image::UniquePtr msg) {on_msg(std::move(msg));});
...
void on_msg(Image::UniquePtr msg)
{
  const double ms = (now() - rclcpp::Time(msg->header.stamp)).nanoseconds() / 1e6;
  const int64_t seq = std::stoll(msg->header.frame_id);
  if (last_seq_ < 0) {
    RCLCPP_INFO(get_logger(), "first msg seq=%ld data addr=%p", seq, ...msg->data.data());
  } else if (seq > last_seq_ + 1) {
    lost_ += seq - last_seq_ - 1;
    ...
```

- 콜백 인자 타입이 `Image::UniquePtr`(= `std::unique_ptr<Image>`)입니다. rclcpp는 콜백 타입을 보고 "이 구독자는 소유권을 원한다"고 판단하고, 구독자가 하나면 발행자가 넘긴 메시지를 **그대로** 줍니다.
- 콜백에 들어오자마자 `now()`를 읽습니다. 06장과 같이 ①~⑥(C에서는 ①④⑤)이 모두 측정값에 들어갑니다.
- 처음 받은 메시지의 일련번호와 주소를 찍습니다. 따로 띄운 경우(A)에는 listener가 talker의 첫 메시지를 놓칠 수 있어 `seq=1`이 아닐 수 있습니다. 주소 비교는 seq가 같은 줄끼리 하세요.

### 3-4. 1초 창과 누적(total) 통계

```cpp
void report()
{
  ...
  print("", window_, lost_);             // 최근 1초 창
  print("total ", total_, total_lost_);  // 시작부터 누적
  window_.clear();
  lost_ = 0;
}

void print(const char * label, std::vector<double> s, int64_t lost)
{
  std::sort(s.begin(), s.end());
  const size_t n = s.size();
  auto rank = [&](double q) {
      return s[std::max<size_t>(1, static_cast<size_t>(std::ceil(q * n))) - 1];
    };
  ...
```

- 06장에서 본 것처럼 1초 창(30 Hz면 n=30)의 p99는 사실상 max입니다. 그래서 **누적 표본**도 따로 모아 매초 `total ...` 줄로 찍습니다. 실행을 멈추기 직전의 `total` 줄이 그 실행 전체의 통계입니다.
- 30 Hz로 12초면 n≈359이고, 이때 p99는 `ceil(0.99 × 359) = 356`번째, 즉 위에서 4번째 값입니다. max와 구분은 되지만 아직 거친 값이라는 것을 기억하세요. 100 Hz(n≈1200)는 좀 더 믿을 만합니다.
- 백분위수 계산은 06장 Python 버전의 `summarize()`와 같은 nearest-rank 방식입니다.

### 3-5. 컴포넌트 등록과 빌드

```cpp
RCLCPP_COMPONENTS_REGISTER_NODE(ipc_lab::Talker)
```

```cmake
add_library(ipc_lab SHARED src/talker.cpp src/listener.cpp)
rclcpp_components_register_node(ipc_lab PLUGIN "ipc_lab::Talker" EXECUTABLE talker)
rclcpp_components_register_node(ipc_lab PLUGIN "ipc_lab::Listener" EXECUTABLE listener)
```

- 두 노드를 **공유 라이브러리 하나**(`libipc_lab.so`)로 빌드합니다. 컨테이너는 이 `.so`를 불러와(`Load Library`) 클래스를 찾아(`Found class`) 노드를 만듭니다(`Instantiate class`). 실행 로그에 이 세 줄이 그대로 찍힙니다.
- `rclcpp_components_register_node(... EXECUTABLE talker)`는 컴포넌트 등록과 함께, 이 컴포넌트 하나만 띄우는 **단독 실행 파일**도 만들어 줍니다. 그래서 `ros2 run ipc_lab talker`(모드 A)가 됩니다. 단독 실행 파일은 intra-process를 켜지 않습니다(`intra-process: off`).
- 지연 실험이므로 `CMAKE_BUILD_TYPE`이 비어 있으면 Release로 빌드하게 했습니다.

### 3-6. launch 파일: 컨테이너에 두 노드 넣기

```python
extra = [{'use_intra_process_comms': ParameterValue(arg('ipc'), value_type=bool)}]

def node(plugin, name):
    return ComposableNode(package='ipc_lab', plugin=plugin, name=name,
                          parameters=params, extra_arguments=extra)
...
ComposableNodeContainer(
    name='ipc_container', namespace='',
    package='rclcpp_components', executable='component_container',
    composable_node_descriptions=[
        node('ipc_lab::Listener', 'ipc_listener'),
        node('ipc_lab::Talker', 'ipc_talker'),
    ],
```

- `use_intra_process_comms`는 노드 **파라미터가 아니라 NodeOptions**라서 `parameters`가 아니라 `extra_arguments`로 넘깁니다. 같은 이유로 `ros2 component load`에서는 `-p`가 아니라 `-e`로 넘깁니다(실험 1).
- launch 인자는 문자열이므로 `ParameterValue(..., value_type=...)`로 타입을 정해 줍니다. 특히 `rate`는 노드가 실수(double)로 선언했기 때문에 `30`처럼 정수로 들어가면 타입 오류가 납니다.
- **listener를 먼저** 올립니다. 그래야 talker의 첫 메시지(seq=1)부터 받아서 두 주소를 바로 비교할 수 있습니다.
- intra-process는 **발행자와 구독자 양쪽 노드 모두** 켜져 있어야 동작합니다. 그래서 두 노드에 같은 `extra`를 줍니다.

## 4. 실행해 보기

각 터미널에서 먼저:

```bash
docker compose exec ros bash
cd /ws && colcon build --symlink-install --packages-select ipc_lab && source install/setup.bash
```

> 서버를 여러 사람이 함께 쓰면 `export ROS_DOMAIN_ID=<겹치지 않는 번호>`로 분리하세요. 아래 측정은 `ROS_DOMAIN_ID=88`, RMW는 Jazzy 기본값(Fast DDS, `rmw_fastrtps_cpp`)으로 했습니다.

**(A) 별도 프로세스** — 터미널 2개

```bash
ros2 run ipc_lab listener                                                   # 터미널 1
ros2 run ipc_lab talker --ros-args -p size:=6220800 -p rate:=30.0           # 터미널 2
```

**(B) 한 프로세스, intra-process 끔** / **(C) 한 프로세스, intra-process 켬** — 터미널 1개

```bash
ros2 launch ipc_lab composed.launch.py ipc:=false size:=6220800 rate:=30.0  # (B)
ros2 launch ipc_lab composed.launch.py ipc:=true  size:=6220800 rate:=30.0  # (C)
```

Ctrl+C로 끝내기 직전의 `total` 줄이 그 실행 전체의 결과입니다. 크기를 바꾸려면 `size:=1024 rate:=100.0`, `size:=1048576 rate:=30.0`처럼 줍니다.

### 실제 출력 (6 MB = 1920×1080 RGB 한 장, 30 Hz)

**(A) 별도 프로세스** — talker와 listener가 각자의 터미널에 찍은 것(일부):

```
[INFO] [1795753179.295793794] [ipc_talker]: publishing 6220800 bytes at 30.0 Hz (intra-process: off)
[INFO] [1795753179.333635595] [ipc_talker]: seq=1 data addr=0x7fbf58597010

[INFO] [1795753179.457363842] [ipc_listener]: first msg seq=4 data addr=0x7f6a84329010
[INFO] [1795753180.289796859] [ipc_listener]: n=26 lost=0 | latency ms: mean=12.002 p50=10.559 p99=27.328 max=27.328
...
[INFO] [1795753191.289823931] [ipc_listener]: n=30 lost=0 | latency ms: mean=11.736 p50=8.288 p99=46.076 max=46.076
[INFO] [1795753191.289991595] [ipc_listener]: total n=356 lost=0 | latency ms: mean=10.526 p50=7.923 p99=25.708 max=46.076
```

listener는 talker의 seq 1~3을 놓치고 seq=4부터 받았습니다(DDS가 서로를 발견하기 전에 보낸 것). 주소는 프로세스가 다르니 비교 자체가 의미가 없습니다. 각자 자기 메모리에 따로 있습니다.

**(B) 한 프로세스, intra-process 끔** (일부):

```
[component_container-1] [INFO] [1795753194.318161339] [ipc_talker]: publishing 6220800 bytes at 30.0 Hz (intra-process: off)
[component_container-1] [INFO] [1795753194.356210707] [ipc_talker]: seq=1 data addr=0x7fc4b7210010
[component_container-1] [INFO] [1795753194.365102707] [ipc_listener]: first msg seq=1 data addr=0x55f0790dd990
[component_container-1] [INFO] [1795753195.314136522] [ipc_listener]: n=29 lost=0 | latency ms: mean=4.503 p50=4.261 p99=8.840 max=8.840
...
[component_container-1] [INFO] [1795753206.314242947] [ipc_listener]: total n=359 lost=0 | latency ms: mean=3.754 p50=3.934 p99=5.672 max=8.840
```

같은 프로세스, 같은 seq=1인데 **주소가 다릅니다.** listener는 역직렬화하면서 새 메모리에 복사본을 만들었습니다.

**(C) 한 프로세스, intra-process 켬** (일부):

```
[component_container-1] [INFO] [1795753209.557323170] [ipc_talker]: publishing 6220800 bytes at 30.0 Hz (intra-process: on)
[component_container-1] [INFO] [1795753209.594546410] [ipc_talker]: seq=1 data addr=0x7fc5b2ebc010
[component_container-1] [INFO] [1795753209.594689520] [ipc_listener]: first msg seq=1 data addr=0x7fc5b2ebc010
[component_container-1] [INFO] [1795753210.553203883] [ipc_listener]: n=29 lost=0 | latency ms: mean=0.026 p50=0.027 p99=0.053 max=0.053
...
[component_container-1] [INFO] [1795753221.553176045] [ipc_listener]: total n=359 lost=0 | latency ms: mean=0.024 p50=0.023 p99=0.048 max=0.056
```

talker가 만든 버퍼 주소 `0x7fc5b2ebc010`을 listener가 **그대로** 받았습니다. 6 MB를 한 바이트도 복사하지 않았다는 증거입니다. 지연은 ms가 아니라 **수십 µs**(0.023 ms)입니다.

### 내 측정 결과

환경: 64코어 서버, Docker 컨테이너 1개 안, C++(Release 빌드), 측정하는 동안 서버 load average 약 27(다른 작업이 돌고 있던 상태). 조건마다 약 12초, 표의 값은 마지막 `total` 줄입니다. Fast DDS는 9개 조건을 **3번 반복**해서 범위로 적었고, Cyclone DDS는 1번씩 돌렸습니다. 유실(lost)은 모든 Fast DDS 실행에서 0이었습니다.

**Fast DDS (Jazzy 기본 RMW), 3회 반복 범위**

| 크기, 주기 | 모드 | n (회당) | p50 (ms) | p99 (ms) | max (ms) |
|---|---|---|---|---|---|
| 1 KB, 100 Hz | A 별도 프로세스 | 1186 ~ 1192 | 0.093 ~ 0.112 | 0.339 ~ 0.365 | 0.382 ~ 5.509 |
| 1 KB, 100 Hz | B 한 프로세스, ipc 끔 | 1199 | 0.037 ~ 0.042 | 0.204 ~ 0.216 | 0.229 ~ 0.242 |
| 1 KB, 100 Hz | C 한 프로세스, ipc 켬 | 1199 | 0.004 ~ 0.006 | 0.035 ~ 0.042 | 0.041 ~ 0.124 |
| 1 MB, 30 Hz | A | 355 ~ 357 | 1.27 ~ 1.52 | 11.9 ~ 21.5 | 21.4 ~ 21.9 |
| 1 MB, 30 Hz | B | 359 | 0.82 ~ 0.88 | 1.91 ~ 1.98 | 1.96 ~ 2.72 |
| 1 MB, 30 Hz | C | 359 | 0.020 ~ 0.023 | 0.043 ~ 0.051 | 0.048 ~ 0.101 |
| 6 MB, 30 Hz | A | 356 ~ 358 | 7.3 ~ 9.2 | 25.1 ~ 25.9 | 34.9 ~ 46.1 |
| 6 MB, 30 Hz | B | 359 | 3.8 ~ 4.3 | 5.7 ~ 6.6 | 8.8 ~ 20.2 |
| 6 MB, 30 Hz | C | 359 | 0.023 ~ 0.028 | 0.046 ~ 0.051 | 0.055 ~ 0.057 |

**Cyclone DDS (`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`), 1회씩**

| 크기, 주기 | 모드 | n | p50 (ms) | p99 (ms) | max (ms) | 유실 |
|---|---|---|---|---|---|---|
| 1 KB, 100 Hz | A | 1203 | 0.071 | 0.229 | 0.306 | 0 |
| 1 KB, 100 Hz | B | 1199 | 0.030 | 0.127 | 0.133 | 0 |
| 1 MB, 30 Hz | A | 359 | 2.78 | 74.2 | 138.8 | 0 |
| 1 MB, 30 Hz | B | 359 | 0.71 | 2.01 | 2.89 | 0 |
| 6 MB, 30 Hz | A | 344 | 18.95 | 334.9 | 408.4 | 15 |
| 6 MB, 30 Hz | B | 359 | 3.39 | 5.43 | 7.76 | 0 |
| 6 MB, 30 Hz | C | 359 | 0.025 | 0.044 | 0.059 | 0 |

**포인터 주소** (talker의 seq=1 주소 → listener가 받은 주소): 모든 C 실행(Fast DDS 9회 + Cyclone 1회 + 실험 실행들)에서 **같았고**, 모든 A·B 실행에서 **달랐습니다.** C의 결과는 RMW를 바꿔도 같았습니다(C는 RMW를 거치지 않으므로 당연한 결과).

해석:

- **C는 크기와 거의 무관합니다.** 1 KB, 1 MB, 6 MB 모두 p50이 수 µs ~ 수십 µs입니다. 메시지 내용을 건드리지 않고 포인터만 넘기기 때문입니다. 남은 시간은 ④'(버퍼에 넣기)와 ⑤(executor가 깨어나 콜백 실행)입니다. 1 KB(100 Hz)가 1 MB·6 MB(30 Hz)보다 더 작게 나온 이유(주기 차이 등)는 확인하지 않았습니다.
- **6 MB에서 A → C로 p50이 7.3~9.2 ms → 0.023~0.028 ms가 됐습니다**(수백 배). p99도 약 25 ms → 약 0.05 ms입니다. 30 Hz 카메라의 한 주기가 33 ms인 것을 생각하면, A의 꼬리 지연은 한 주기의 3/4에 가깝고 C는 무시할 만한 수준입니다.
- **B는 A보다 빨랐지만 크기에 따라 커졌습니다**(p50: 1 KB 0.04 ms → 1 MB 0.85 ms → 6 MB 4 ms). 처음엔 의외였습니다. intra-process를 끈 B는 "같은 프로세스지만 DDS를 거치는" 경로라 A와 비슷할 거라고 예상했기 때문입니다. 원인을 확인해 보니 **Fast DDS 자체의 intra-process delivery**(기본 켜짐) 때문이었습니다. XML로 이 기능을 끄자 B가 A 수준으로 돌아왔습니다(실험 4). 그래도 직렬화와 역직렬화(복사)는 남아 있어서 크기에 따라 커집니다.
- **Cyclone DDS에서도 B가 A보다 빨랐습니다.** Cyclone이 같은 프로세스 안에서 어떤 경로로 전달하는지는 이 실험에서 확인하지 않았습니다.
- **Cyclone A 6 MB에서 15개 유실, p99 약 335 ms**가 나왔습니다. 06장(Python)에서 본 "depth 10 큐가 넘쳐 버려지고, 약 333 ms 분량이 쌓인다"는 현상과 같은 모양입니다. 같은 조건의 B와 C에서는 유실이 없었습니다.
- **1 MB A의 꼬리가 긴 편이었습니다.** p50은 1.3~1.5 ms인데 p99가 12~21 ms였습니다. 원인은 조사하지 않았습니다.
- 06장 Python 측정의 A 1 KB p50(0.31~0.33 ms)보다 이번 C++ A 1 KB(0.09~0.11 ms)가 작았습니다. 하지만 측정 시점과 서버 부하가 달랐으므로 이 둘로 "C++가 몇 배 빠르다"고 말할 수는 없습니다.

### 메시지 할당 비용은 어디에 숨어 있나

talker는 stamp를 찍기 **전에** 메시지를 할당합니다. 그래서 C의 숫자에는 할당 비용이 빠져 있습니다. 따로 재 보려고, 같은 컨테이너에서 `make_unique<Image>()` + `data.resize(N)`을 300번 반복해 시간을 재는 작은 프로그램(-O2, ROS 노드 아님)을 돌렸습니다.

```
size=1024    alloc+zero ms: p50=0.000 p99=0.000 max=0.001 | copy ms: p50=0.000 p99=0.000 max=0.000
size=1048576 alloc+zero ms: p50=0.022 p99=0.024 max=0.389 | copy ms: p50=0.035 p99=0.041 max=0.430
size=6220800 alloc+zero ms: p50=0.258 p99=0.298 max=3.802 | copy ms: p50=0.508 p99=1.434 max=3.261
```

- 6 MB 할당+0 채우기는 p50 0.26 ms, 메시지 통째 복사는 p50 0.51 ms였습니다. 반복문에서 같은 메모리가 재사용되는 조건이라 실제 노드에서는 다를 수 있습니다.
- 이 비용은 A, B, C **모두에서** 발행 측이 똑같이 냅니다(측정 구간 밖). 반면 A와 B에서는 **구독 측**도 역직렬화하면서 새 메모리를 할당하고 복사하는데, 이것은 측정 구간 **안**에 들어갑니다. C에서는 구독 측 할당이 없습니다.
- 따라서 "C의 6 MB 결과를 할당 비용이 지배한다"는 현상은 없었습니다. 할당은 설계상 측정에서 빠져 있고, 빼지 않더라도 0.3 ms 정도였습니다.

## 5. 실험해 보기

1. **실행 중인 컨테이너에 컴포넌트를 하나씩 올리기 + 구독자 2개 → 복사**

   launch 파일 없이 빈 컨테이너를 띄우고 CLI로 올립니다.

   ```bash
   ros2 run rclcpp_components component_container --ros-args -r __node:=ipc_container   # 터미널 1
   # 터미널 2
   ros2 component load /ipc_container ipc_lab ipc_lab::Listener -e use_intra_process_comms:=true
   ros2 component load /ipc_container ipc_lab ipc_lab::Listener -n ipc_listener2 -e use_intra_process_comms:=true
   ros2 component load /ipc_container ipc_lab ipc_lab::Talker -p size:=6220800 -p rate:=30.0 -e use_intra_process_comms:=true
   ros2 component list
   ```

   실제 출력:

   ```
   Loaded component 1 into '/ipc_container' container node as '/ipc_listener'
   Loaded component 2 into '/ipc_container' container node as '/ipc_listener2'
   Loaded component 3 into '/ipc_container' container node as '/ipc_talker'
   /ipc_container
     1  /ipc_listener
     2  /ipc_listener2
     3  /ipc_talker

   [ipc_talker]: seq=1 data addr=0x7f127fa11010
   [ipc_listener]: first msg seq=1 data addr=0x7f127fa11010
   [ipc_listener2]: first msg seq=1 data addr=0x7f127f422010
   ...
   [ipc_listener2]: total n=443 lost=0 | latency ms: mean=1.913 p50=1.594 p99=4.036 max=4.758
   [ipc_listener]:  total n=445 lost=0 | latency ms: mean=1.901 p50=1.584 p99=4.028 max=4.754
   ```

   - `ipc_listener`는 원본(같은 주소), `ipc_listener2`는 **복사본**(다른 주소)을 받았습니다. 공식 데모 문서에 따르면 누가 원본을 받을지는 정해져 있지 않습니다.
   - 지연은 **두 구독자 모두** p50 약 1.6 ms로 늘었습니다(구독자 1개일 때 0.023 ms). 복사가 `publish()` 안에서 일어나고, 싱글 스레드 executor는 `publish()`가 끝나야 콜백을 돌릴 수 있으므로 원본을 받은 쪽도 함께 기다리기 때문입니다. 처음 5초 정도는 1초 창 p50이 2.8~3.3 ms였다가 이후 1.3~1.6 ms로 내려갔습니다. 위 할당 측정의 복사 시간(p50 0.5 ms)보다 큰 이유는 확인하지 않았습니다.
   - `-p`는 노드 파라미터, `-e`는 컨테이너에 주는 extra argument(NodeOptions)입니다.

2. **C에 다른 프로세스의 구독자를 붙이기**

   (C)를 6 MB로 띄운 채, 다른 터미널에서 약 9초 동안 외부 listener를 붙였다 뗐습니다.

   ```bash
   ros2 launch ipc_lab composed.launch.py ipc:=true size:=6220800 rate:=30.0     # 터미널 1
   ros2 run ipc_lab listener --ros-args -r __node:=ext_listener                   # 터미널 2 (잠깐 켰다 끔)
   ```

   컨테이너 안 listener의 1초 창(실제 출력, 일부):

   ```
   [ipc_listener]: n=30 lost=0 | latency ms: mean=0.019 p50=0.013 p99=0.050 max=0.050   ← 외부 구독자 없음
   [ipc_listener]: n=30 lost=0 | latency ms: mean=4.502 p50=4.465 p99=6.720 max=6.720   ← 외부 구독자 붙음
   [ipc_listener]: n=30 lost=0 | latency ms: mean=4.007 p50=3.804 p99=6.390 max=6.390
   [ipc_listener]: n=30 lost=0 | latency ms: mean=5.326 p50=4.564 p99=23.701 max=23.701
   [ipc_listener]: n=30 lost=0 | latency ms: mean=0.018 p50=0.013 p99=0.056 max=0.056   ← 외부 구독자 떠남
   ```

   - 외부 구독자가 있는 동안 컨테이너 안 listener의 1초 창 p50이 0.01~0.04 ms에서 **3.8~4.6 ms**로 뛰었고, 떠나자 바로 돌아왔습니다. 외부 listener 자신은 1초 창 p50 9~21 ms를 봤습니다.
   - rclcpp 소스(`publisher.hpp`)를 보면, 다른 프로세스 구독자가 있으면 `publish(unique_ptr)`가 (1) DDS로 보낼 복사본을 만들고 (2) 원본은 같은 프로세스 구독자에게 넘긴 뒤 (3) 복사본을 직렬화해 DDS로 보냅니다. 이 모든 것이 `publish()` 안에서 끝나야 executor가 listener 콜백을 돌립니다.
   - 공식 데모 문서는 이 경우에도 같은 프로세스 쪽의 zero-copy는 **유지된다**고 설명합니다. 이 실험에서는 첫 메시지의 주소만 찍었기 때문에 붙은 뒤의 주소는 확인하지 않았습니다. 확인한 것은 지연이 늘었다는 것입니다. **zero-copy가 유지되는 것과 지연이 그대로인 것은 다른 이야기**입니다.
   - 교훈: rviz, `ros2 topic hz`, rosbag처럼 **다른 프로세스에서 토픽을 구독하는 도구를 붙이면 측정 대상이 바뀝니다.**

3. **depth 바꾸기: `depth:=0`**

   ```bash
   ros2 launch ipc_lab composed.launch.py ipc:=true depth:=0
   ```

   예외를 기대했지만 실제로는 경고 한 줄 뒤에 정상 동작했습니다(1 KB, 100 Hz, 1초 창 p50 0.004~0.005 ms).

   ```
   [WARN] [rclcpp]: A zero depth with KEEP_LAST doesn't make sense; no data could be stored. This will be interpreted as SYSTEM_DEFAULT
   ```

   rclcpp가 depth 0을 SYSTEM_DEFAULT로 바꿔 버리기 때문에 intra-process의 "depth 0 금지" 검사까지 가지 않습니다. 실제 depth가 몇이 되었는지는 확인하지 않았습니다. 진짜 제약은 KEEP_ALL인데, 이 노드에는 history 파라미터가 없어 실행해 보지는 않았고 소스로만 확인했습니다(2장).

4. **B가 왜 A보다 빠른가: Fast DDS의 intra-process delivery 끄기**

   ```bash
   cat > /tmp/fastdds_intra_off.xml <<'XML'
   <?xml version="1.0" encoding="UTF-8" ?>
   <dds xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
     <library_settings>
       <intraprocess_delivery>OFF</intraprocess_delivery>
     </library_settings>
   </dds>
   XML
   export FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/fastdds_intra_off.xml
   ros2 launch ipc_lab composed.launch.py ipc:=false size:=6220800 rate:=30.0
   ```

   | 조건 (B, Fast DDS) | p50 (ms) | p99 (ms) | max (ms) |
   |---|---|---|---|
   | 1 KB, 100 Hz, Fast DDS intra-process **켬**(기본, 위 표) | 0.037 ~ 0.042 | 0.204 ~ 0.216 | 0.229 ~ 0.242 |
   | 1 KB, 100 Hz, Fast DDS intra-process **끔** | 0.092 | 0.387 | 0.460 |
   | 6 MB, 30 Hz, Fast DDS intra-process **켬**(기본, 위 표) | 3.8 ~ 4.3 | 5.7 ~ 6.6 | 8.8 ~ 20.2 |
   | 6 MB, 30 Hz, Fast DDS intra-process **끔** | 13.3 | 27.5 | 61.9 |

   끄자 B가 A(1 KB p50 0.09~0.11, 6 MB p50 7.3~9.2) 수준이거나 그보다 느려졌습니다(끈 쪽은 1회 측정). 즉 B의 이득은 rclcpp가 아니라 **Fast DDS가 같은 프로세스의 엔티티끼리 전송 계층을 건너뛰는 기능**에서 왔습니다(Fast DDS 문서: 기본값 `INTRAPROCESS_FULL`). rclcpp의 intra-process(C)는 이것과 별개로, 직렬화까지 통째로 건너뜁니다.

## 6. 발표할 때 이렇게 설명하기

> "ROS 2에서 노드를 나누는 것과, 그 노드들을 몇 개의 프로세스에 담는 것은 별개의 결정입니다. C++ 노드를 컴포넌트로 만들어 두면 코드 수정 없이 컨테이너 프로세스 하나에 모을 수 있고, intra-process 통신을 켜면 메시지를 직렬화하거나 DDS로 보내지 않고 포인터만 넘깁니다. 실제로 1080p 영상 크기인 6 MB를 30 Hz로 보내 보니, 별도 프로세스에서는 p50이 7~9 ms, p99가 약 25 ms였는데 intra-process를 켜자 p50 0.02 ms, p99 0.05 ms로 줄었고, 발행한 버퍼 주소와 받은 주소가 같아서 복사가 없다는 것도 확인했습니다. 다만 구독자가 둘이 되거나 다른 프로세스에서 같은 토픽을 구독하면 복사가 다시 생기고 지연이 1~5 ms 수준으로 늘었습니다. 그리고 한 노드가 죽으면 같은 프로세스의 노드가 모두 죽기 때문에, 큰 데이터를 주고받는 안정된 노드끼리만 묶고 나머지는 분리하는 것이 보통입니다."

## 7. 자주 하는 실수

1. **컨테이너에 넣기만 하고 `use_intra_process_comms`를 안 켠다.** 그러면 B입니다. 빨라지긴 하지만(Fast DDS 덕분) 직렬화와 복사는 그대로입니다. talker 로그의 `intra-process: on`과 주소 비교로 확인하세요.
2. **`publish(msg)`(const 참조)나 `shared_ptr` 콜백을 쓰고 zero-copy를 기대한다.** 참조로 발행하면 rclcpp가 내부에서 복사합니다. zero-copy를 원하면 `publish(std::move(unique_ptr))` + `UniquePtr` 콜백 + 구독자 1개 조건을 맞춰야 합니다.
3. **`publish(std::move(msg))` 뒤에 `msg`를 다시 쓴다.** 소유권이 넘어가서 `msg`는 nullptr입니다. 매 주기 새 메시지를 만들어야 합니다.
4. **측정 중에 rviz, `ros2 topic hz`, rosbag을 붙인다.** 다른 프로세스 구독자가 생기면 발행 측이 복사와 DDS 전송을 추가로 하고, 같은 프로세스 구독자의 지연도 늘어납니다(실험 2: 0.02 ms → 약 4 ms).
5. **Python 노드로 같은 효과를 기대한다.** rclpy에는 intra-process 통신이 없고, Python 노드는 `component_container`에 올릴 수 없습니다.
6. **불안정한 노드까지 한 컨테이너에 넣는다.** 하나가 죽으면 전부 죽습니다. 또 기본 `component_container`는 싱글 스레드라서 느린 콜백 하나가 다른 노드를 모두 막습니다.
7. **`-p rate:=30`처럼 정수를 준다.** 노드는 `rate`를 실수로 선언했기 때문에 바로 죽습니다(실제 출력: `InvalidParameterTypeException ... parameter {rate} is of type {double}, setting it to {integer} is not allowed.`). `30.0`으로 주세요. launch 파일은 `ParameterValue`로 실수로 바꿔 넘기므로 `rate:=30`도 됩니다.

## 8. 확인 문제

1. intra-process를 켠 (C)에서 06장의 ①~⑥ 중 건너뛰는 단계와 남는 단계는?
   <details><summary>정답</summary>②직렬화, ③DDS 전송, ⑥역직렬화를 건너뜁니다. ①stamp, ④(rclcpp의 구독별 intra-process 버퍼에 넣기), ⑤(executor가 깨어나 콜백 실행)는 남습니다. 그래서 C의 지연은 메시지 크기와 거의 무관했습니다(1 KB ~ 6 MB 모두 p50 수 µs ~ 수십 µs).</details>

2. zero-copy가 실제로 일어났는지 이 실습에서 무엇으로 확인했나? 그리고 어떤 조건에서 깨지나?
   <details><summary>정답</summary>talker가 찍은 <code>seq=1 data addr</code>와 listener가 받은 <code>first msg seq=1 data addr</code>가 같은지 비교했습니다(C에서 항상 같음, A·B에서는 항상 다름). <code>const &amp;</code>로 발행하거나, <code>UniquePtr</code>를 원하는 구독자가 둘 이상이면(나머지는 복사본) 깨집니다. 다른 프로세스 구독자가 있으면 그쪽으로 보낼 복사본이 추가로 만들어집니다.</details>

3. intra-process를 끈 (B)도 (A)보다 빨랐다. 이유는? rclcpp가 무언가 해 준 것인가?
   <details><summary>정답</summary>rclcpp가 아니라 Fast DDS의 intra-process delivery(기본 켜짐)가 같은 프로세스 안에서 전송 계층을 건너뛰었기 때문입니다. XML로 이 기능을 끄자 B가 A 수준(1 KB p50 0.092 ms, 6 MB p50 13.3 ms)으로 돌아왔습니다. 직렬화·역직렬화는 남아 있어 B의 지연은 크기에 따라 커졌습니다(p50: 1 KB 0.04 ms → 6 MB 4 ms).</details>

4. 구독자 2개를 같은 컨테이너에 넣었더니 **원본을 받은 구독자의 지연도** 0.02 ms에서 약 1.6 ms로 늘었다. 왜?
   <details><summary>정답</summary>두 번째 구독자에게 줄 6 MB 복사본을 <code>publish()</code> 안에서 만들고, 기본 컨테이너는 SingleThreadedExecutor 하나라서 <code>publish()</code>를 포함한 talker 타이머 콜백이 끝나야 어느 listener 콜백이든 실행될 수 있기 때문입니다. stamp는 publish 직전에 찍었으므로 복사 시간이 두 구독자 모두의 측정값에 들어갑니다.</details>

5. 카메라 드라이버, 이미지 전처리, 물체 인식, 웹 대시보드용 브리지 노드가 있다. 무엇을 한 프로세스에 묶고 무엇을 분리하겠나?
   <details><summary>정답</summary>정답은 하나가 아니지만, 큰 영상을 주고받는 C++ 노드(드라이버 → 전처리 → 인식)는 intra-process를 켜고 한 컨테이너에 묶어 복사와 직렬화를 없애는 것이 이득입니다. 대시보드 브리지처럼 외부 연결이 있거나 불안정하거나 Python인 노드는 따로 둡니다. 다만 브리지가 같은 영상 토픽을 다른 프로세스에서 구독하면 실험 2처럼 컨테이너 안 경로의 지연도 늘어나므로, 브리지용으로는 축소·압축한 별도 토픽을 발행하는 식으로 나누는 것을 고려합니다. 묶은 노드 중 하나가 죽으면 모두 죽는다는 점도 함께 판단합니다.</details>

## 9. 더 읽을거리

- Composition 개념(컨테이너 종류, 배포 시점 결정): https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Composition.html
- Composition 튜토리얼(`ros2 component load`, `-e use_intra_process_comms`): https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Composition.html
- 컴포넌트 노드 작성하기: https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Writing-a-Composable-Node.html
- launch로 컴포넌트 띄우기: https://docs.ros.org/en/jazzy/How-To-Guides/Launching-composable-nodes.html
- intra-process 통신 데모(주소 비교, 구독자 여러 개일 때의 복사): https://docs.ros.org/en/jazzy/Tutorials/Demos/Intra-Process-Communication.html
- Executor 종류: https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Executors.html
- 프로세스 사이의 zero-copy(Loaned Messages): https://docs.ros.org/en/jazzy/How-To-Guides/Configure-ZeroCopy-loaned-messages.html
- intra-process 설계 문서(버퍼, QoS 처리): https://design.ros2.org/articles/intraprocess_communications.html
- Fast DDS intra-process delivery(실험 4): https://fast-dds.docs.eprosima.com/en/2.14.x/fastdds/transport/intraprocess.html
- 이전 장: [06. 통신 지연 측정](06_latency.md) — ①~⑥ 단계와 측정 방법, [05. Executor와 콜백 그룹](05_executor.md) — ⑤단계
