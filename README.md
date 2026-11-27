# ros_sandbox

ROS 2 스터디용 저장소입니다. OS와 상관없이 같은 환경을 쓸 수 있도록 Docker로 **ROS 2 Jazzy**를 실행합니다.

## 준비물

- Docker, Docker Compose v2 (`docker compose version`으로 확인)
- Linux에서는 sudo 없이 docker를 쓰려면 다음을 실행한 뒤 다시 로그인하세요: `sudo usermod -aG docker $USER`

## 빠른 시작

```bash
git clone https://github.com/JuheonHwang/ros_sandbox.git
cd ros_sandbox
docker compose up -d --build     # 처음 한 번은 이미지를 받느라 몇 분 걸립니다
docker compose exec ros bash     # 컨테이너 셸에 들어가기 (터미널마다 실행)
```

설치 확인: 터미널 두 개에서 각각 실행합니다.

```bash
ros2 run demo_nodes_cpp talker     # 터미널 1
ros2 run demo_nodes_py listener    # 터미널 2 → "I heard: [Hello World: N]"이 보이면 성공
```

## 자주 쓰는 명령

| 하고 싶은 일 | 명령 (호스트에서) |
|---|---|
| 셸 들어가기 | `docker compose exec ros bash` |
| 컨테이너 멈추기 / 다시 켜기 | `docker compose stop` / `docker compose start` |
| 컨테이너 삭제 (`ws/`의 내용은 남음) | `docker compose down` |

## 워크스페이스

호스트의 `ws/` 폴더가 컨테이너의 `/ws`로 연결되어 있습니다. 패키지는 `ws/src`에 만들고, 빌드는 컨테이너 안에서 합니다.

```bash
cd /ws/src && ros2 pkg create --build-type ament_python my_pkg
cd /ws && colcon build
source install/setup.bash          # 새 셸을 열면 자동으로 적용됩니다
```

- `build/`, `install/`, `log/`는 git에서 제외됩니다.
- 컨테이너 안에서는 root로 실행되므로 호스트에서 보면 이 파일들의 소유자가 root입니다. 지울 때는 컨테이너 안에서 지우세요.

## 학습 자료

[docs/study/](docs/study/README.md)에 주제별 예제 코드와 설명 문서가 있습니다. 노드 → 토픽 → QoS → 서비스 → executor → 지연 측정 → 동기화 순서로 공부합니다.

## 실습: 통신 지연과 동기화 (`latency_lab`)

`ws/src/latency_lab`은 토픽 지연(latency)과 센서 동기화를 직접 측정해 보는 패키지입니다. 빌드는 한 번만 하면 됩니다.

```bash
cd /ws && colcon build --symlink-install && source install/setup.bash
```

### 1) 토픽 지연 측정

talker가 메시지에 보낸 시각(`header.stamp`)을 넣고, listener가 받은 시각과의 차이를 1초마다 출력합니다.

```bash
ros2 run latency_lab talker   --ros-args -p size:=1024 -p rate:=100.0   # 터미널 1
ros2 run latency_lab listener                                          # 터미널 2
# 출력 예: n=100 lost=0 | latency ms: mean=0.39 p50=0.32 p99=0.92 max=0.92
```

| 파라미터 | 기본값 | 의미 |
|---|---|---|
| `size` | 1024 | 메시지 크기(byte). 1920×1080 RGB 영상은 6220800 |
| `rate` | 100.0 | 초당 발행 횟수(Hz) |
| `reliability` | reliable | `reliable` 또는 `best_effort` (talker와 listener에 같이 지정) |
| `depth` | 10 | QoS history depth |

바꿔 볼 것:
- 메시지 크기 키우기: `-p size:=6220800 -p rate:=30.0`
- QoS: 두 노드 모두 `-p reliability:=best_effort` → `lost` 값을 보세요
- 미들웨어(RMW): 두 터미널 모두 `export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` (기본값은 `rmw_fastrtps_cpp`)
- 내장 도구와 비교: `ros2 topic hz /latency_test`, `ros2 topic delay /latency_test`

64코어 서버의 컨테이너 1개 안에서 Python으로 측정한 예시입니다(p50 / p99, ms).

| 조건 | Fast DDS | Cyclone DDS |
|---|---|---|
| 1 KB, 100 Hz | 0.33 / 0.9 | 0.28 / 0.9 |
| 1 MB, 30 Hz | 3.7 / 15 | — |
| 6 MB, 30 Hz | 24 / 37 | 20 / 90~130 |
| 6 MB, 30 Hz, best_effort | 16 / 22, **약 70% 유실** | — |

### 2) 센서 동기화 (`message_filters`)

camera(30 Hz)와 lidar(10 Hz)를 `header.stamp` 기준으로 짝짓습니다. `slop`은 짝으로 인정하는 최대 시각 차이(초)입니다.

```bash
ros2 run latency_lab fake_sensors  --ros-args -p jitter_ms:=5.0   # 터미널 1
ros2 run latency_lab sync_listener --ros-args -p slop:=0.02       # 터미널 2
# 출력 예: pairs=10/10 lidar msgs | mean |dt|=1.51 ms
```

`jitter_ms`(센서 시각 오차)를 키우거나 `slop`을 줄이면 짝이 맞는 비율이 떨어집니다. 예: jitter 20 ms, slop 0.001이면 10개 중 1~2개만 짝이 맞습니다.

## GUI (turtlesim, rviz2)

Linux 데스크톱이나 WSL2처럼 화면이 있는 환경에서는 호스트에서 먼저 아래를 실행하고 **컨테이너를 다시 만드세요.**

```bash
xhost +local:docker
docker compose up -d --force-recreate
docker compose exec ros ros2 run turtlesim turtlesim_node
```

원격 서버(SSH)나 macOS처럼 화면이 없는 환경에서는 별도로 X 포워딩을 설정해야 합니다.

## 주의

이 저장소는 **public**입니다. 회사 코드, 데이터, 내부 자료는 올리지 마세요.
