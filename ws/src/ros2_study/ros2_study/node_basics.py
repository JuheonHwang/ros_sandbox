"""01 노드: 타이머, 로거, 파라미터를 가진 최소한의 노드."""
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rcl_interfaces.msg import FloatingPointRange, ParameterDescriptor


class NodeBasics(Node):
    def __init__(self):
        # 노드 이름. `ros2 node list`에 /node_basics 로 보인다.
        # 실행할 때 --ros-args -r __node:=새이름 으로 바꿀 수 있다.
        super().__init__('node_basics')

        # 파라미터는 "선언"해야 쓸 수 있다. 선언하지 않은 이름을 set 하면 거부된다.
        # 범위를 descriptor로 정해 두면 rate:=0 같은 잘못된 값은 ROS가 알아서 거부한다
        # (아래에서 1/rate 를 계산하므로 0이 들어오면 안 된다).
        self.declare_parameter('greeting', '안녕, ROS 2')

        self.declare_parameter(
            'rate', 1.0,
            ParameterDescriptor(
                description='타이머 주기(Hz)',
                floating_point_range=[FloatingPointRange(from_value=0.1, to_value=10.0)],
            ),
        )
        # # 예외 처리 안할때 예시
        # self.declare_parameter('rate', 1.0)

        rate = self.get_parameter('rate').value
        # 타이머: rclpy.spin()이 도는 동안 주기마다 on_timer를 불러 준다.
        self.timer = self.create_timer(1.0 / rate, self.on_timer)
        self.count = 0

        # 로거 레벨은 DEBUG < INFO < WARN < ERROR < FATAL.
        # 기본 레벨이 INFO라서 debug 메시지는 --log-level debug 를 줘야 보인다.
        log = self.get_logger()
        log.debug('debug: 기본 설정에서는 안 보임')
        log.info(f'시작: rate={rate} Hz')
        log.warn('warn: 주의할 일')
        log.error('error: 문제가 생김')

    def on_timer(self):
        # 파라미터를 매번 다시 읽는다. 그래서 `ros2 param set` 으로 바꾸면
        # 다음 틱부터 바로 반영된다. (콜백을 따로 등록하는 방법도 있지만 이게 가장 단순하다)
        greeting = self.get_parameter('greeting').value
        rate = self.get_parameter('rate').value

        period_ns = int(1e9 / rate)
        if self.timer.timer_period_ns != period_ns:
            # 타이머를 새로 만들 필요 없이 주기만 바꿀 수 있다.
            self.timer.timer_period_ns = period_ns
            # reset()을 부르지 않으면 이미 예약된 다음 틱은 옛 주기대로 온다.
            self.timer.reset()
            self.get_logger().info(f'rate 변경 → {rate} Hz')

        self.count += 1
        self.get_logger().info(f'{greeting} #{self.count}')


def main():
    rclpy.init()  # ROS 2 통신 준비 (프로세스당 한 번)
    node = NodeBasics()
    try:
        # spin: 이벤트 루프. 타이머·구독 등의 콜백을 기다렸다가 실행하는 일을 Ctrl+C 전까지 반복한다.
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        # Ctrl+C(SIGINT)나 외부 종료 신호는 정상 종료로 취급한다. 트레이스백을 찍지 않기 위함.
        pass
    finally:
        node.destroy_node()
        # 신호 처리기에서 이미 shutdown 되었을 수 있으므로 try_shutdown 사용 (두 번 불러도 안전)
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
