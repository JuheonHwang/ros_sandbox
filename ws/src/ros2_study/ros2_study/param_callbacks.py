"""01장 보충: 파라미터가 바뀔 때 콜백으로 반응하기.

node_basics.py는 타이머에서 매번 파라미터를 다시 읽지만(폴링), 여기서는 바뀌는 순간에만 불리는
콜백 두 개를 쓴다.
  ① add_on_set_parameters_callback  : 값이 바뀌기 "전"에 불림. 검증하고 거절할 수 있다.
  ② add_post_set_parameters_callback: 값이 바뀐 "뒤"에 불림. 거절은 못 하고 반응만 한다.
"""
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


class ParamCallbacks(Node):
    def __init__(self):
        super().__init__('param_callbacks')
        self.declare_parameter('rate', 1.0)
        self.declare_parameter('greeting', 'hello')

        # ① 검증: False를 돌려주면 변경이 거절되고 값은 그대로 남는다.
        self.add_on_set_parameters_callback(self.validate)
        # ② 반응: 검증을 통과해 실제로 값이 바뀐 뒤에만 불린다.
        self.add_post_set_parameters_callback(self.on_changed)

        self.timer = self.create_timer(1.0 / self.get_parameter('rate').value, self.on_timer)

    def validate(self, params):
        for p in params:
            if p.name == 'rate' and p.value <= 0.0:
                return SetParametersResult(successful=False, reason='rate는 0보다 커야 합니다')
        return SetParametersResult(successful=True)

    def on_changed(self, params):
        # 여기서는 이미 바뀐 값이 들어온다. 무거운 일은 피하고 짧게 반응만 한다.
        for p in params:
            self.get_logger().info(f'변경됨: {p.name} = {p.value}')
            if p.name == 'rate':
                self.timer.timer_period_ns = int(1e9 / p.value)
                self.timer.reset()  # 이미 잡힌 다음 틱도 새 주기로

    def on_timer(self):
        self.get_logger().info(self.get_parameter('greeting').value)


def main():
    rclpy.init()
    try:
        rclpy.spin(ParamCallbacks())
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        rclpy.try_shutdown()
