std_msgs/Header header

string robot_id
string candidate_id

# v1.0 wire constants. Detection semantics and AMR arbitration remain TBD-IF-006.
uint8 FIRE=0
uint8 LEAK=1
uint8 OBSTACLE=2
uint8 event_type

float32 confidence

# Signed horizontal error is fixed on the wire; control thresholds remain TBD-AMR-001.
# negative : target is left
# 0.0      : target is center
# positive : target is right
# normalized range approximately -1.0 ~ +1.0
float32 horizontal_error
