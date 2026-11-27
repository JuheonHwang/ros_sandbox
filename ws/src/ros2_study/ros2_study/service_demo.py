"""04 서비스: AddTwoInts 서버/클라이언트, 그리고 '콜백 안에서 동기 호출' 데드락 재현.

    ros2 run ros2_study add_server
    ros2 run ros2_study add_client --ros-args -p a:=3 -p b:=5
    ros2 run ros2_study deadlock_demo --ros-args -p mode:=sync    # 멈춤
    ros2 run ros2_study deadlock_demo --ros-args -p mode:=async   # 해결 1
    ros2 run ros2_study deadlock_demo --ros-args -p mode:=multi   # 해결 2
"""
import rclpy
from example_interfaces.srv import AddTwoInts
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node

SERVICE = 'add_two_ints'


class AddServer(Node):
    def __init__(self):
        super().__init__('add_server')
        self.create_service(AddTwoInts, SERVICE, self.on_request)
        self.get_logger().info(f'/{SERVICE} 서비스 대기 중')

    def on_request(self, request, response):
        # response는 rclpy가 미리 만들어 넘겨준 빈 객체. 채워서 return하면 클라이언트로 전송된다.
        response.sum = request.a + request.b
        self.get_logger().info(f'요청: {request.a} + {request.b} → 응답: {response.sum}')
        return response


def server():
    rclpy.init()
    try:
        rclpy.spin(AddServer())
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


def client():
    rclpy.init()
    node = Node('add_client')
    a = node.declare_parameter('a', 2).value
    b = node.declare_parameter('b', 3).value
    cli = node.create_client(AddTwoInts, SERVICE)

    # 서버가 없을 때 보낸 요청은 받아 줄 곳이 없어 응답이 영원히 오지 않는다. 먼저 서버를 기다린다.
    if not cli.wait_for_service(timeout_sec=5.0):
        node.get_logger().error(f'/{SERVICE} 서버를 찾지 못했습니다')
    else:
        # call_async()는 요청만 보내고 바로 Future(나중에 채워질 결과 상자)를 돌려준다.
        future = cli.call_async(AddTwoInts.Request(a=a, b=b))
        # 응답을 받아 future를 채우는 것은 executor의 일이다. 여기는 콜백 밖(main)이므로 직접 spin해도 안전하다.
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
        if future.done():
            node.get_logger().info(f'{a} + {b} = {future.result().sum}')
        else:
            node.get_logger().error('5초 안에 응답이 없습니다')
    node.destroy_node()
    rclpy.shutdown()


class DeadlockDemo(Node):
    """타이머 콜백 안에서 서비스를 부른다. mode에 따라 멈추거나(sync) 동작한다(async/multi)."""

    def __init__(self):
        super().__init__('deadlock_demo')
        mode = self.declare_parameter('mode', 'sync').value  # sync | async | multi
        self.mode = mode
        # multi 모드: 클라이언트를 타이머와 '다른' 콜백 그룹에 넣어야 응답 처리가 다른 스레드에서 돌 수 있다.
        # (같은 MutuallyExclusive 그룹이면 타이머 콜백이 끝날 때까지 응답 콜백도 못 돈다)
        group = MutuallyExclusiveCallbackGroup() if mode == 'multi' else None
        self.cli = self.create_client(AddTwoInts, SERVICE, callback_group=group)
        self.n = 0
        self.create_timer(1.0, self.tick)
        self.get_logger().info(f'mode={mode}')

    def tick(self):
        if not self.cli.service_is_ready():
            self.get_logger().info('서버 대기 중...')
            return
        self.n += 1
        req = AddTwoInts.Request(a=self.n, b=100)
        self.get_logger().info(f'요청 보냄: {req.a} + 100')
        if self.mode == 'async':
            # 해결 1: 기다리지 않고 콜백을 등록한 뒤 바로 return → executor가 응답을 처리할 수 있다.
            self.cli.call_async(req).add_done_callback(
                lambda f, a=req.a: self.get_logger().info(f'응답(async): {a} + 100 = {f.result().sum}'))
            return
        # sync/multi: 응답이 올 때까지 이 스레드가 멈춘다.
        # 응답을 받아 future를 완료시키는 것도 executor의 일인데, 단일 스레드 executor의 유일한 스레드가
        # 바로 여기서 기다리고 있으므로 영원히 끝나지 않는다(sync). multi는 다른 스레드가 응답을 처리한다.
        res = self.cli.call(req)
        self.get_logger().info(f'응답(call): {req.a} + 100 = {res.sum}')


def deadlock():
    rclpy.init()
    node = DeadlockDemo()
    # rclpy.spin(node)이 내부에서 쓰는 기본 executor가 SingleThreadedExecutor다(스레드 1개).
    executor = MultiThreadedExecutor() if node.mode == 'multi' else SingleThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
