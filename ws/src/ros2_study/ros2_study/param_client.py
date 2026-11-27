"""01a 파라미터: 다른 노드의 파라미터를 코드에서 읽고/쓰고, 변경을 구독하기.

param_client  : /node_basics 의 파라미터를 list → get → set(성공 2개, 거절 1개) 순서로 다룬다.
param_watcher : /parameter_events 토픽을 구독해서 누가 무엇을 바꿨는지 로그로 찍는다.
"""
import rclpy
from rcl_interfaces.msg import ParameterEvent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.parameter import Parameter, parameter_value_to_python
from rclpy.parameter_client import AsyncParameterClient
from rclpy.qos import qos_profile_parameter_events


def main():
    rclpy.init()
    node = Node('param_client')
    target = node.declare_parameter('target', 'node_basics').value
    log = node.get_logger()

    # 파라미터는 사실 서비스다. 이 클라이언트는 /<target>/list_parameters,
    # /<target>/get_parameters, /<target>/set_parameters ... 서비스 클라이언트 묶음이다.
    client = AsyncParameterClient(node, target)

    def wait(future):
        # 04장과 같은 패턴: 비동기로 보내고, 응답을 꺼내 줄 executor는 여기서(콜백 밖에서) 돌린다.
        # 콜백 안에서 이렇게 기다리면 04장의 데드락이 그대로 난다.
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
        if not future.done():
            raise TimeoutError(f'/{target} 응답 없음')
        return future.result()

    try:
        # 서버(대상 노드)가 discovery로 보일 때까지 기다린다. 없으면 요청이 허공으로 간다.
        if not client.wait_for_services(timeout_sec=5.0):
            log.error(f'/{target} 의 파라미터 서비스를 찾지 못했습니다')
            return

        # 1) 목록: 이름만 온다. (use_sim_time 같은 기본 파라미터도 섞여 있다)
        names = wait(client.list_parameters()).result.names
        log.info(f'list: {names}')

        # 2) 값 읽기: 요청한 이름 순서대로 ParameterValue가 온다 (타입 태그 + 필드들).
        values = wait(client.get_parameters(['greeting', 'rate'])).values
        for name, v in zip(['greeting', 'rate'], values):
            log.info(f'get: {name} = {parameter_value_to_python(v)!r}')

        # 3) 쓰기: 파라미터마다 결과(successful, reason)가 하나씩 온다.
        #    세 번째 rate=50.0 은 node_basics 가 선언한 범위(0.1~10.0) 밖이라 거절돼야 한다.
        #    set_parameters 는 하나씩 적용하므로 앞의 두 개는 거절과 상관없이 반영된다.
        #    (전부 아니면 전무가 필요하면 set_parameters_atomically)
        requests = [
            Parameter('greeting', value='코드에서 바꿈'),
            Parameter('rate', value=2.0),
            Parameter('rate', value=50.0),
        ]
        results = wait(client.set_parameters(requests)).results
        for p, r in zip(requests, results):
            status = '성공' if r.successful else f'거절: {r.reason}'
            log.info(f'set: {p.name}={p.value} → {status}')
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def watcher():
    rclpy.init()
    node = Node('param_watcher')
    log = node.get_logger()

    # /parameter_events 는 평범한 토픽이다. 파라미터를 가진 모든 노드가 여기에 발행한다.
    # QoS는 rclpy가 발행 쪽에 쓰는 프로파일(qos_profile_parameter_events)을 그대로 맞춘다.
    def on_event(msg: ParameterEvent):
        # 메시지 하나 = 한 노드에서 일어난 한 번의 변경. 같은 이름은 세 목록 중 하나에만 들어간다.
        for kind, params in (('new', msg.new_parameters),
                             ('changed', msg.changed_parameters),
                             ('deleted', msg.deleted_parameters)):
            for p in params:
                log.info(f'{msg.node}: {kind} {p.name} = {parameter_value_to_python(p.value)!r}')

    node.create_subscription(ParameterEvent, '/parameter_events', on_event,
                             qos_profile_parameter_events)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
