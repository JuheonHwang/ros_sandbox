"""01장 보충: 파라미터 콜백 3단계를 한 노드에서 순서대로 보기.

set 요청 하나가 거치는 순서:
  ① pre_set  : 요청 목록을 "고친다"   (값 보정, 다른 파라미터 끼워 넣기)  → 고친 목록을 돌려줌
  ② on_set   : 고친 목록을 "검증한다" (하나라도 거절하면 목록 전체가 적용 안 됨)
  ③ post_set : 적용된 뒤 "반응한다"   (거절 불가, 짧게)
각 단계에서 받은 목록을 로그로 찍어서 순서와 내용을 눈으로 확인한다.
"""
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.parameter import Parameter

MAX_RATE = 10.0
MODE_RATES = {'slow': 1.0, 'fast': 10.0}  # mode를 바꾸면 rate도 같이 바뀌게 할 값


def fmt(params):
    return ', '.join(f'{p.name}={p.value!r}' for p in params)


class ParamStages(Node):
    def __init__(self):
        super().__init__('param_stages')
        self.declare_parameter('rate', 1.0)
        self.declare_parameter('mode', 'slow')
        self.declare_parameter('greeting', 'hello')

        self.add_pre_set_parameters_callback(self.pre_set)
        self.add_on_set_parameters_callback(self.on_set)
        self.add_post_set_parameters_callback(self.post_set)

        self.ticks = 0
        self.timer = self.create_timer(1.0 / self.get_parameter('rate').value, self.on_tick)
        self.create_timer(2.0, self.report)  # rate 변화가 숫자로 보이도록 2초마다 틱 수 보고

    # ① 요청 고치기: 받은 목록을 바탕으로 새 목록을 만들어 돌려준다.
    def pre_set(self, params):
        self.get_logger().info(f'① pre_set  받은 요청: {fmt(params)}')
        out = []
        for p in params:
            if p.name == 'rate' and p.value > MAX_RATE:
                p = Parameter('rate', value=MAX_RATE)  # 보정: 상한으로 깎기
            out.append(p)
            if p.name == 'mode' and p.value in MODE_RATES:
                out.append(Parameter('rate', value=MODE_RATES[p.value]))  # 끼워 넣기
        if fmt(out) != fmt(params):
            self.get_logger().info(f'   pre_set  고친 요청: {fmt(out)}')
        return out

    # ② 검증: 하나라도 실패하면 이번 목록 전체가 적용되지 않는다.
    def on_set(self, params):
        self.get_logger().info(f'② on_set   검증할 목록: {fmt(params)}')
        for p in params:
            if p.name == 'rate' and p.value <= 0.0:
                return self.reject('rate는 0보다 커야 합니다')
            if p.name == 'mode' and p.value not in MODE_RATES:
                return self.reject(f'mode는 {"/".join(MODE_RATES)} 중 하나여야 합니다')
            if p.name == 'greeting' and not p.value.strip():
                return self.reject('greeting은 비울 수 없습니다')
        return SetParametersResult(successful=True)

    def reject(self, reason):
        self.get_logger().warn(f'   on_set   거절: {reason}')
        return SetParametersResult(successful=False, reason=reason)

    # ③ 반응: 이미 적용된 값. 요청에 있었다고 바뀐 건 아니므로 직접 비교한다.
    def post_set(self, params):
        self.get_logger().info(f'③ post_set 적용된 목록: {fmt(params)}')
        for p in params:
            if p.name == 'rate':
                period_ns = int(1e9 / p.value)
                if self.timer.timer_period_ns != period_ns:
                    self.timer.timer_period_ns = period_ns
                    self.timer.reset()
                    self.get_logger().info(f'   post_set 타이머 주기 변경 → {p.value} Hz')

    def on_tick(self):
        self.ticks += 1

    def report(self):
        greeting = self.get_parameter('greeting').value
        self.get_logger().info(f'[{greeting}] 최근 2초 틱 {self.ticks}회')
        self.ticks = 0


def main():
    rclpy.init()
    try:
        rclpy.spin(ParamStages())
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        rclpy.try_shutdown()
