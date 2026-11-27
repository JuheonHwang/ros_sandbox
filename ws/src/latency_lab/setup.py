from setuptools import setup

setup(
    name='latency_lab',
    version='0.1.0',
    packages=['latency_lab'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/latency_lab']),
        ('share/latency_lab', ['package.xml']),
    ],
    install_requires=['setuptools'],
    entry_points={'console_scripts': [
        'talker = latency_lab.latency:talker',
        'listener = latency_lab.latency:listener',
        'fake_sensors = latency_lab.sync:fake_sensors',
        'sync_listener = latency_lab.sync:sync_listener',
    ]},
)
