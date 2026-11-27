"""03 QoS: reliability / durability / depth를 파라미터로 바꿔 가며 통신 결과를 비교한다.

    ros2 run ros2_study qos_pub --ros-args -p reliability:=best_effort
    ros2 run ros2_study qos_sub --ros-args -p reliability:=reliable   # → 호환 안 됨, 수신 0건
"""
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

TOPIC = 'qos_chatter'


def qos_from_params(node):
    """파라미터 문자열('reliable', 'transient_local' 등)을 QoSProfile로 바꾼다.

    get_from_short_key()는 ros2 CLI(--qos-reliability 등)가 쓰는 짧은 이름을 enum으로 바꿔 준다.
    """
    return QoSProfile(
        # KEEP_LAST: 최근 depth개만 큐에 보관한다. 큐가 차면 가장 오래된 것부터 버린다.
        history=HistoryPolicy.KEEP_LAST,
        depth=node.declare_parameter('depth', 10).value,
        reliability=ReliabilityPolicy.get_from_short_key(
            node.declare_parameter('reliability', 'reliable').value),
        durability=DurabilityPolicy.get_from_short_key(
            node.declare_parameter('durability', 'volatile').value),
    )


def describe(qos):
    return f'reliability={qos.reliability.name} durability={qos.durability.name} depth={qos.depth}'


class QosPub(Node):
    def __init__(self):
        super().__init__('qos_pub')
        qos = qos_from_params(self)
        # count개를 보낸 뒤에는 발행만 멈추고 노드는 계속 살아 있다.
        # (transient_local 실험: 늦게 붙은 구독자가 '지난 메시지'를 받으려면 발행자가 살아 있어야 한다)
        self.count = self.declare_parameter('count', 0).value  # 0이면 무한히 발행
        rate = self.declare_parameter('rate', 2.0).value
        self.pub = self.create_publisher(String, TOPIC, qos)
        self.seq = 0
        self.timer = self.create_timer(1.0 / rate, self.tick)
        self.get_logger().info(f'pub QoS: {describe(qos)}')

    def tick(self):
        self.seq += 1
        self.pub.publish(String(data=f'msg {self.seq}'))
        self.get_logger().info(f'sent: msg {self.seq}')
        if self.seq == self.count:
            self.timer.cancel()
            self.get_logger().info(f'{self.count}개 발행 완료. 노드는 계속 실행 중')


class QosSub(Node):
    def __init__(self):
        super().__init__('qos_sub')
        qos = qos_from_params(self)
        # 느린 구독자 흉내: 콜백 하나에 delay초가 걸린다.
        # 그동안 도착한 메시지는 구독자 쪽 큐(depth)에 쌓이고, 넘치면 오래된 것이 버려진다.
        self.delay = self.declare_parameter('delay', 0.0).value
        self.create_subscription(String, TOPIC, self.on_msg, qos)
        self.get_logger().info(f'sub QoS: {describe(qos)}')

    def on_msg(self, msg):
        self.get_logger().info(f'heard: {msg.data}')
        time.sleep(self.delay)  # 실제 코드에서는 콜백 안에서 sleep하지 말 것 (executor를 막는다)


def run(node_cls):
    rclpy.init()
    try:
        rclpy.spin(node_cls())
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


def pub():
    run(QosPub)


def sub():
    run(QosSub)
