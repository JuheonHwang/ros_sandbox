"""토픽 지연 측정: talker가 보낸 시각(header.stamp)과 listener가 받은 시각의 차이를 잰다.

같은 PC 안에서는 두 노드가 같은 시계를 쓰므로 (받은 시각 - stamp)가 곧 단방향 지연이다.
"""
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import Image


def qos_from_params(node):
    best_effort = node.declare_parameter('reliability', 'reliable').value == 'best_effort'
    return QoSProfile(
        depth=node.declare_parameter('depth', 10).value,
        reliability=ReliabilityPolicy.BEST_EFFORT if best_effort else ReliabilityPolicy.RELIABLE,
    )


def summarize(samples_ms):
    s = sorted(samples_ms)
    n = len(s)
    return {'n': n, 'mean': sum(s) / n, 'p50': s[n // 2], 'p99': s[int(n * 0.99)], 'max': s[-1]}


class Talker(Node):
    def __init__(self):
        super().__init__('latency_talker')
        rate = self.declare_parameter('rate', 100.0).value
        size = self.declare_parameter('size', 1024).value  # payload bytes
        self.pub = self.create_publisher(Image, 'latency_test', qos_from_params(self))
        # 카메라 영상처럼 큰 payload를 흉내 내려고 sensor_msgs/Image를 사용
        self.msg = Image(height=1, width=size, step=size, encoding='mono8', data=bytes(size))
        self.seq = 0
        self.create_timer(1.0 / rate, self.tick)
        self.get_logger().info(f'publishing {size} bytes at {rate} Hz')

    def tick(self):
        self.seq += 1
        self.msg.header.frame_id = str(self.seq)  # 유실 계산용 일련번호
        self.msg.header.stamp = self.get_clock().now().to_msg()
        self.pub.publish(self.msg)


class Listener(Node):
    def __init__(self):
        super().__init__('latency_listener')
        self.samples = []
        self.last_seq = None
        self.lost = 0
        self.create_subscription(Image, 'latency_test', self.on_msg, qos_from_params(self))
        self.create_timer(1.0, self.report)

    def on_msg(self, msg):
        latency = self.get_clock().now() - Time.from_msg(msg.header.stamp)
        self.samples.append(latency.nanoseconds / 1e6)
        seq = int(msg.header.frame_id)
        if self.last_seq is not None and seq > self.last_seq + 1:
            self.lost += seq - self.last_seq - 1
        self.last_seq = seq

    def report(self):
        if not self.samples:
            self.get_logger().info('waiting for messages...')
            return
        r = summarize(self.samples)
        self.get_logger().info(
            f"n={r['n']} lost={self.lost} | latency ms: mean={r['mean']:.3f} "
            f"p50={r['p50']:.3f} p99={r['p99']:.3f} max={r['max']:.3f}")
        self.samples, self.lost = [], 0


def run(node_cls):
    rclpy.init()
    try:
        rclpy.spin(node_cls())
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


def talker():
    run(Talker)


def listener():
    run(Listener)


if __name__ == '__main__':
    r = summarize([float(i) for i in range(1, 101)])
    assert (r['n'], r['mean'], r['p50'], r['p99'], r['max']) == (100, 50.5, 51.0, 100.0, 100.0), r
    print('summarize OK')
