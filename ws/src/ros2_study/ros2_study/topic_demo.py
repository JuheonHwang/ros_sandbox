"""02 토픽: std_msgs/String 을 주고받는 talker / listener."""
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String


class Talker(Node):
    def __init__(self):
        super().__init__('talker')
        self.declare_parameter('rate', 2.0)  # 초당 발행 횟수(Hz)
        rate = self.get_parameter('rate').value

        # create_publisher(메시지 타입, 토픽 이름, QoS)
        # 숫자 10은 QoS의 history depth(큐 깊이): 아직 못 보낸/못 꺼낸 메시지를 최대 10개까지 보관.
        # 이름이 'chatter'(앞에 / 없음)라서 노드의 네임스페이스 아래 /chatter 가 된다.
        self.pub = self.create_publisher(String, 'chatter', 10)
        self.timer = self.create_timer(1.0 / rate, self.on_timer)
        self.count = 0

    def on_timer(self):
        msg = String()
        msg.data = f'Hello ROS 2 #{self.count}'
        self.pub.publish(msg)  # 받는 쪽이 없어도 에러가 아니다. 그냥 아무도 안 받을 뿐.
        self.get_logger().info(f'보냄: "{msg.data}"')
        self.count += 1


class Listener(Node):
    def __init__(self):
        super().__init__('listener')
        # 토픽 이름과 타입이 talker와 같아야 연결된다. QoS도 호환되어야 한다(03장).
        # 반환값은 self.sub에 보관하는 것이 관례다(rclpy는 노드가 참조를 들고 있지만, C++에서는 필수).
        self.sub = self.create_subscription(String, 'chatter', self.on_msg, 10)

    def on_msg(self, msg: String):
        # 메시지가 도착할 때마다 spin()이 이 콜백을 불러 준다.
        self.get_logger().info(f'받음: "{msg.data}"')


def _run(node_cls):
    # 01장과 같은 init → spin → 정리 패턴. talker/listener가 공유한다.
    rclpy.init()
    node = node_cls()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def talker():
    _run(Talker)


def listener():
    _run(Listener)
