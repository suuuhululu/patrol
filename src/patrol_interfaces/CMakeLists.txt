cmake_minimum_required(VERSION 3.8)
project(patrol_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  # patrol_interfaces 2.0.0: 기본 순찰 시나리오의 최소 공용 계약.
  "action/Patrol.action"
  "action/DetectEvent.action"
  "msg/PatrolCommand.msg"
  "msg/DriveToken.msg"
  "msg/EStop.msg"
  "msg/CameraState.msg"
  "msg/DetectionEvidence.msg"
  "msg/MissionExecutionEvent.msg"
  "srv/ReportDetection.srv"
  DEPENDENCIES std_msgs sensor_msgs geometry_msgs builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
