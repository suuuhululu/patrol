import rclpy
from rclpy import action, executors
from nav2_msgs.action import NavigateToPose
from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TurtleBot4Directions, TaskResult
WP = {1: (-0.206, -1.038, 90.8), 2: (-1.147, 0.500, 175.4), 3: (-2.029, -0.916, 266.3),
      4: (-2.751, -2.422, 182.4), 5: (-4.389, -1.122, 94.3), 6: (-2.909, 0.575, 358.3), 7: (-1.374, -2.439, 359.8)}
def execute(goal, ns):
    navigator = TurtleBot4Navigator(namespace=ns)
    if not navigator.getDockedStatus():
        navigator.info('Docking before intialising pose')
        navigator.dock()
    try:
        navigator.undock()
        initial_pose = navigator.getPoseStamped([0.0, 0.0], TurtleBot4Directions.NORTH)
        navigator.setInitialPose(initial_pose)
        navigator.waitUntilNav2Active()
        n = 1
        goal_pose = navigator.getPoseStamped(WP[n][:2], WP[n][2], TurtleBot4Directions.NORTH)
        navigator.startToPose(goal_pose)
        if navigator.getResult() == TaskResult.SUCCEEDED:
            goal.succeed()
        else:
            goal.abort()
        return NavigateToPose.Result()
    finally:
        navigator.destroy_node()
def main():
    rclpy.init()
    node = rclpy.create_node('genius_patrol', namespace='robot1')
    ns = node.get_namespace().strip('/')
    try:
        node.server = action.ActionServer(
            node, NavigateToPose, 'patrol_start', lambda goal: execute(goal, ns))
        rclpy.spin(node, executor=executors.SingleThreadedExecutor())
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
