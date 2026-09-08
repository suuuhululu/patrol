# Safety Arbiter -> AMR emergency-stop state.
# Topic: /control/estop
# QoS: RELIABLE / TRANSIENT_LOCAL. Depth and reason enum values remain
# TBD-IF-004 and are intentionally not declared here.

std_msgs/Header header
string target_robot_id
bool active
uint8 reason
bool latched
uint64 sequence
