FROM osrf/ros:jazzy-desktop
# rmw_cyclonedds_cpp: 미들웨어(RMW)별 latency 비교 실습용
RUN apt-get update && apt-get install -y --no-install-recommends ros-jazzy-rmw-cyclonedds-cpp \
 && rm -rf /var/lib/apt/lists/*
RUN echo 'source /opt/ros/jazzy/setup.bash' >> /root/.bashrc \
 && echo '[ -f /ws/install/setup.bash ] && source /ws/install/setup.bash' >> /root/.bashrc
WORKDIR /ws
