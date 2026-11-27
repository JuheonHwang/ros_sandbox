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
