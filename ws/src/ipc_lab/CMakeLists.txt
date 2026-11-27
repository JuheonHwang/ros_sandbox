cmake_minimum_required(VERSION 3.8)
project(ipc_lab)

# 지연을 재는 실험이므로 최적화 빌드를 기본으로 한다
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
add_compile_options(-Wall -Wextra -Wpedantic)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(sensor_msgs REQUIRED)

# 두 노드를 공유 라이브러리(컴포넌트) 하나로 만든다.
# 컨테이너 프로세스가 이 .so를 불러와 노드를 "같은 프로세스 안에" 생성한다.
add_library(ipc_lab SHARED src/talker.cpp src/listener.cpp)
target_link_libraries(ipc_lab PUBLIC
  rclcpp::rclcpp rclcpp_components::component ${sensor_msgs_TARGETS})

# 컴포넌트로 등록 + 단독 실행 파일(ros2 run ipc_lab talker|listener)도 자동 생성
rclcpp_components_register_node(ipc_lab PLUGIN "ipc_lab::Talker" EXECUTABLE talker)
rclcpp_components_register_node(ipc_lab PLUGIN "ipc_lab::Listener" EXECUTABLE listener)

install(TARGETS ipc_lab
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)
install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})

ament_package()
