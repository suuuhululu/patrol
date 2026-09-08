# AMR -> control server and system monitor command result.
# Topic: /{robot}/patrol_report
# QoS: RELIABLE / VOLATILE / KEEP_LAST(20)

uint8 SUCCEEDED=0
uint8 FAILED=1
uint8 CANCELED=2

uint32 NONE=0
uint32 CONTROL_CANCELED=100
uint32 COMMAND_SUPERSEDED=101
uint32 SAFETY_POLICY_CANCELED=102
uint32 INVALID_COMMAND=200
uint32 INVALID_TARGET=201
uint32 UNSUPPORTED_COMMAND=202
uint32 NAV_NO_PATH=300
uint32 NAV_TIMEOUT=301
uint32 NAV_GOAL_REJECTED=302
uint32 NAV_GOAL_ABORTED=303
uint32 SAFE_ZONE_NOT_FOUND=400
uint32 KEEPOUT_APPLY_FAILED=401
uint32 KEEPOUT_ROLLBACK_FAILED=402
uint32 LOCALIZATION_INVALID=500
uint32 POSE_STALE=501
uint32 LIDAR_VERIFICATION_FAILED=502
uint32 DRIVE_TOKEN_MISSING=600
uint32 DRIVE_TOKEN_EXPIRED=601
uint32 COMMUNICATION_LOST=602
uint32 E_STOP_ACTIVE=700
uint32 OBSTACLE_BLOCKED=701
uint32 FIRE_DETECTED=702
uint32 BATTERY_LOW=800
uint32 BATTERY_CRITICAL=801
uint32 DOCKING_TIMEOUT=900
uint32 ROLE_HANDOFF=901
uint32 SENSOR_ERROR=1000
uint32 INTERNAL_ERROR=1001

std_msgs/Header header
string report_id
string robot_id
string source_session_id
string command_id
string mission_id
uint8 result
uint32 reason_code
string reason
builtin_interfaces/Time started_at
builtin_interfaces/Time finished_at
string final_waypoint_id
string[] related_event_ids
