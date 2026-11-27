"""talker와 listener를 컨테이너 프로세스 하나에 넣어 실행한다(Composition).

ros2 launch ipc_lab composed.launch.py ipc:=true size:=6220800 rate:=30.0
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    arg = LaunchConfiguration
    params = [{
        'size': ParameterValue(arg('size'), value_type=int),
        'rate': ParameterValue(arg('rate'), value_type=float),
        'depth': ParameterValue(arg('depth'), value_type=int),
    }]
    # use_intra_process_comms는 노드 파라미터가 아니라 NodeOptions라서 extra_arguments로 넘긴다
    extra = [{'use_intra_process_comms': ParameterValue(arg('ipc'), value_type=bool)}]

    def node(plugin, name):
        return ComposableNode(package='ipc_lab', plugin=plugin, name=name,
                              parameters=params, extra_arguments=extra)

    return LaunchDescription([
        DeclareLaunchArgument('ipc', default_value='true'),
        DeclareLaunchArgument('size', default_value='1024'),
        DeclareLaunchArgument('rate', default_value='100.0'),
        DeclareLaunchArgument('depth', default_value='10'),
        ComposableNodeContainer(
            name='ipc_container', namespace='',
            package='rclcpp_components', executable='component_container',
            # listener를 먼저 올려야 talker의 첫 메시지(seq=1)부터 받아 주소를 비교할 수 있다
            composable_node_descriptions=[
                node('ipc_lab::Listener', 'ipc_listener'),
                node('ipc_lab::Talker', 'ipc_talker'),
            ],
            output='screen',
        ),
    ])
