"""센서 동기화: 주기가 다른 두 센서 메시지를 header.stamp 기준으로 짝짓는다.

fake_sensors  : camera(30 Hz)와 lidar(10 Hz)를 발행. 실제 센서처럼 stamp에 촬영 시각 오차(jitter)를 섞는다.
sync_listener : message_filters.ApproximateTimeSynchronizer로 stamp 차이가 slop 이내인 쌍만 콜백.
"""
import random

import rclpy
from message_filters import ApproximateTimeSynchronizer, Subscriber
from rclpy.duration import Duration
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import Image, PointCloud2


class FakeSensors(Node):
    def __init__(self):
        super().__init__('fake_sensors')
        self.jitter = self.declare_parameter('jitter_ms', 5.0).value / 1000.0
        self.cam_pub = self.create_publisher(Image, 'camera', 10)
        self.lidar_pub = self.create_publisher(PointCloud2, 'lidar', 10)
        self.create_timer(1 / 30, lambda: self.publish(self.cam_pub, Image()))
        self.create_timer(1 / 10, lambda: self.publish(self.lidar_pub, PointCloud2()))

    def publish(self, pub, msg):
        stamp = self.get_clock().now() - Duration(seconds=random.uniform(0, self.jitter))
        msg.header.stamp = stamp.to_msg()
        msg.header.frame_id = 'sensor'
        pub.publish(msg)


class SyncListener(Node):
    def __init__(self):
        super().__init__('sync_listener')
        slop = self.declare_parameter('slop', 0.02).value  # 허용 stamp 차이(초)
        cam = Subscriber(self, Image, 'camera')
        lidar = Subscriber(self, PointCloud2, 'lidar')
        lidar.registerCallback(self.on_lidar)
        ApproximateTimeSynchronizer([cam, lidar], queue_size=10, slop=slop).registerCallback(self.on_pair)
        self.lidar_count, self.diffs = 0, []
        self.create_timer(1.0, self.report)
        self.get_logger().info(f'slop={slop * 1000:.0f} ms')

    def on_lidar(self, _msg):
        self.lidar_count += 1

    def on_pair(self, cam, lidar):
        dt = Time.from_msg(cam.header.stamp) - Time.from_msg(lidar.header.stamp)
        self.diffs.append(abs(dt.nanoseconds) / 1e6)

    def report(self):
        if self.lidar_count:
            mean = sum(self.diffs) / len(self.diffs) if self.diffs else float('nan')
            self.get_logger().info(
                f'pairs={len(self.diffs)}/{self.lidar_count} lidar msgs | mean |dt|={mean:.2f} ms')
        self.lidar_count, self.diffs = 0, []


def run(node_cls):
    rclpy.init()
    try:
        rclpy.spin(node_cls())
    except (KeyboardInterrupt, ExternalShutdownException, RCLError):
        pass  # Ctrl+C 도중 context가 먼저 닫히면 RCLError가 날 수 있음: 종료 중이라 무시
    finally:
        rclpy.try_shutdown()


def fake_sensors():
    run(FakeSensors)


def sync_listener():
    run(SyncListener)
