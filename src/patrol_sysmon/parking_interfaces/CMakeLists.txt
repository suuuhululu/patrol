cmake_minimum_required(VERSION 3.8)
project(parking_interfaces)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/MissionCommand.msg"
  "msg/MissionCommandAck.msg"
  "msg/DriveToken.msg"
  "msg/ControlHeartbeat.msg"
  "msg/EStopState.msg"
  "msg/RobotStatus.msg"
  "msg/PatrolVisit.msg"
  "msg/PatrolReport.msg"
  "msg/IngestionAck.msg"
  "msg/CameraState.msg"
  "msg/DetectionCandidate.msg"
  "msg/DetectionEvent.msg"
  "msg/EvidenceChunk.msg"
  "msg/KeepoutStatus.msg"
  DEPENDENCIES builtin_interfaces geometry_msgs std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
