std_msgs/Header header

string robot_id
string candidate_id

# Vision team proposal - final enum values require interface approval
uint8 FIRE=0
uint8 LEAK=1
uint8 OBSTACLE=2
uint8 event_type

float32 confidence

# Vision team proposal - AMR agreement required
# negative : target is left
# 0.0      : target is center
# positive : target is right
# normalized range approximately -1.0 ~ +1.0
float32 horizontal_error
