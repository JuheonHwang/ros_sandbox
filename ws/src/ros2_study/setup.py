from setuptools import setup

setup(
    name='ros2_study',
    version='0.1.0',
    packages=['ros2_study'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/ros2_study']),
        ('share/ros2_study', ['package.xml']),
    ],
    install_requires=['setuptools'],
    entry_points={'console_scripts': [
        # 01 노드
        'node_basics = ros2_study.node_basics:main',
        'param_callbacks = ros2_study.param_callbacks:main',
        # 02 토픽
        'topic_talker = ros2_study.topic_demo:talker',
        'topic_listener = ros2_study.topic_demo:listener',
        # 03 QoS
        'qos_pub = ros2_study.qos_demo:pub',
        'qos_sub = ros2_study.qos_demo:sub',
        # 04 서비스
        'add_server = ros2_study.service_demo:server',
        'add_client = ros2_study.service_demo:client',
        'deadlock_demo = ros2_study.service_demo:deadlock',
        # 05 executor
        'executor_demo = ros2_study.executor_demo:main',
    ]},
)
