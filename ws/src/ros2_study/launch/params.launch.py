"""01a 파라미터: YAML 파일 + 인라인 값으로 node_basics 실행.

parameters 리스트는 앞에서 뒤로 적용되므로, 뒤에 쓴 인라인 값이 YAML을 덮어쓴다.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    yaml = os.path.join(get_package_share_directory('ros2_study'), 'config', 'node_basics.yaml')
    return LaunchDescription([
        Node(
            package='ros2_study',
            executable='node_basics',
            parameters=[yaml, {'greeting': 'launch에서 덮어씀'}],
        ),
    ])
