# ROS 2 학습 노트

작은 예제 코드를 직접 돌려 보면서 ROS 2 통신을 이해하기 위한 자료입니다. 각 장은 **코드 1개 + 설명 문서 1개**로 되어 있습니다. 문서를 옆에 띄워 두고 코드를 읽고, 직접 실행한 다음, "실험해 보기"로 값을 바꿔 보세요.

## 준비

```bash
docker compose up -d                  # 컨테이너 켜기 (처음이면 루트 README의 빠른 시작 참고)
docker compose exec ros bash          # 컨테이너 셸 (터미널마다)
cd /ws && colcon build --symlink-install && source install/setup.bash
```

## 학습 순서

| 장 | 주제 | 코드 | 핵심 질문 |
|---|---|---|---|
| [01](01_node.md) | 노드 | `ros2_study/node_basics.py` | 노드는 무엇이고, `spin()`은 무슨 일을 하나? |
| [02](02_topic.md) | 토픽 | `ros2_study/topic_demo.py` | 발행자와 구독자는 어떻게 서로를 찾나? |
| [03](03_qos.md) | QoS | `ros2_study/qos_demo.py` | 왜 코드가 맞는데도 메시지가 안 올까? |
| [04](04_service.md) | 서비스 | `ros2_study/service_demo.py` | 요청/응답은 언제 쓰고, 왜 데드락이 나나? |
| [05](05_executor.md) | Executor와 콜백 그룹 | `ros2_study/executor_demo.py` | 콜백 하나가 느리면 왜 다른 콜백도 늦어지나? |
| [06](06_latency.md) | 통신 지연 측정 | `latency_lab/latency.py` | 메시지는 얼마나 늦게 도착하고, 무엇이 지연을 좌우하나? |
| [07](07_sync.md) | 센서 동기화 | `latency_lab/sync.py` | 주기가 다른 센서 데이터를 어떻게 같은 순간끼리 묶나? |
| [08](08_intra_process.md) | 같은 프로세스 통신 (C++) | `ipc_lab/src/*.cpp` | 노드를 한 프로세스에 합치면 지연이 얼마나 줄어드나? |

코드 경로는 `ws/src/ros2_study/`, `ws/src/latency_lab/`, `ws/src/ipc_lab/` 아래 기준입니다.

- **01~04**는 발표 자료(노드·토픽·서비스)의 바탕입니다.
- **05~08**은 통신·지연·동기화를 더 깊게 보는 트랙입니다. 08장만 C++ 예제입니다.

## 공부하는 방법

1. **문서의 "핵심 개념"을 먼저 읽습니다.** 그림 하나로 전체 구조를 잡습니다.
2. **"코드 읽기"를 따라 실제 파일을 열어 봅니다.** 한 줄씩 왜 그렇게 썼는지 확인합니다.
3. **"실행해 보기"를 그대로 따라 합니다.** 문서에 적힌 출력과 내 출력이 같은지 비교합니다.
4. **"실험해 보기"에서 값을 하나씩 바꿔 봅니다.** 결과를 미리 예측해 보고, 예측과 다르면 그 이유가 가장 좋은 공부거리입니다.
5. **"발표할 때 이렇게 설명하기"를 소리 내어 읽어 봅니다.** 막히는 부분이 아직 이해 안 된 부분입니다.
6. **"확인 문제"를 답을 열지 않고 풀어 봅니다.**

## 공식 자료

- ROS 2 Jazzy 문서: https://docs.ros.org/en/jazzy/
- 개념 설명(Concepts): https://docs.ros.org/en/jazzy/Concepts.html
- 튜토리얼: https://docs.ros.org/en/jazzy/Tutorials.html
