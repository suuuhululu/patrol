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

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/MissionCommand.msg"
  "msg/CommandCheck.msg"
  "msg/DriveToken.msg"
  "msg/RobotStatus.msg"
  "msg/PatrolReport.msg"
  "msg/EStop.msg"
  "msg/CameraState.msg"
  # [시스템 모니터 수신용] 공용 패키지에 없던 메시지를 옮겨 이름을 patrol_interfaces로 통일한다.
  "msg/MissionCommandAck.msg"
  "msg/ControlHeartbeat.msg"
  "msg/EStopState.msg"
  "msg/PatrolVisit.msg"
  "msg/IngestionAck.msg"
  "msg/DetectionCandidate.msg"
  "msg/DetectionEvent.msg"
  "msg/EvidenceChunk.msg"
  "msg/KeepoutStatus.msg"
  "msg/AlignmentStatus.msg"
  DEPENDENCIES std_msgs geometry_msgs builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
