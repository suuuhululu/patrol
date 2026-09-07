cmake_minimum_required(VERSION 3.8)
project(patrol_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

# 5종은 CR-001 의 묶음이다. 개별 추가·삭제는 수정 요청서를 거친다.
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/MissionCommand.msg"
  "msg/DriveToken.msg"
  "msg/RobotStatus.msg"
  "msg/PatrolReport.msg"
  "msg/EStop.msg"
  DEPENDENCIES std_msgs geometry_msgs builtin_interfaces
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
