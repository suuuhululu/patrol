# Control server -> AMR local-safety driving authority.
# Topic: /control/drive_token
# QoS: BEST_EFFORT / VOLATILE / KEEP_LAST(3), deadline 200 ms,
# lifespan 500 ms. An empty token_id revokes the named holder.

std_msgs/Header header
string control_session_id
string token_id
string holder_robot_id
builtin_interfaces/Duration lease_duration
uint64 message_sequence
