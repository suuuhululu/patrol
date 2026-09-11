#!/usr/bin/env python3

# Copyright 2022 Clearpath Robotics, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# @author Roni Kreinin (rkreinin@clearpathrobotics.com)

import math
import sys
import threading

import rclpy
from nav2_simple_commander.robot_navigator import TaskResult
from nav2_msgs.action import NavigateToPose
from rclpy import action, executors
from rclpy.executors import ExternalShutdownException

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Directions, TurtleBot4Navigator
if __package__:
    from .move_to_safetyzone import Evacuation, arguments
    from .event_check import EventCheck
else:
    from move_to_safetyzone import Evacuation, arguments
    from event_check import EventCheck
# WP = {1: (-0.206, -1.038, 90.8), 2: (-1.147, 0.500, 175.4), 3: (-2.029, -0.916, 266.3),
#       4: (-2.751, -2.422, 182.4), 5: (-4.389, -1.122, 94.3), 6: (-2.909, 0.575, 358.3), 7: (-1.374, -2.439, 359.8)}
# n = 1

SPIN = 'spin'   # goal_pose 목록에 넣으면 그 자리에서 360도 회전


def startSpin(navigator, angle=2 * math.pi, time_allowance=20, evacuation=None):
    """
    Perform spin action and wait until done.
    (turtlebot4_navigator의 startToPose와 같은 방식으로 Nav2 spin 액션을 감싼 함수)

    :param angle: 회전량(라디안). 기본 2*pi = 360도. 양수 반시계, 음수 시계.
    :param time_allowance: 제한 시간(초, 정수).
    """
    if not navigator.spin(spin_dist=angle, time_allowance=time_allowance):
        navigator.error('Spin request was rejected!')
        return False

    if evacuation is not None:
        return evacuation.wait_for_task()
    while not navigator.isTaskComplete():
        pass

    result = navigator.getResult()
    if result == TaskResult.SUCCEEDED:
        navigator.info('Spin succeeded!')
        return True
    elif result == TaskResult.CANCELED:
        navigator.info('Spin was canceled!')
    elif result == TaskResult.FAILED:
        navigator.info('Spin failed!')
    else:
        navigator.info('Spin has an invalid return status!')
    return False


def run_patrol(navigator, evacuation):
    # Start on dock
    if not navigator.getDockedStatus():
        navigator.info('Docking before intialising pose')
        navigator.dock()
        if not navigator.getDockedStatus():
            navigator.error('Initial docking failed!')
            return False

    # Undock
    navigator.undock()
    if navigator.getDockedStatus():
        navigator.error('Undocking failed!')
        return False

    # Set initial pose
    initial_pose = navigator.getPoseStamped([0.0, 0.0], TurtleBot4Directions.SOUTH)
    navigator.setInitialPose(initial_pose)

    # Wait for Nav2
    navigator.waitUntilNav2Active()

    # Set goal poses  (웨이포인트 = 이동, SPIN = 그 자리에서 360도 회전)
    goal_pose = []

    goal_pose.append(navigator.getPoseStamped([-0.206, -1.038], TurtleBot4Directions.WEST))
    goal_pose.append(SPIN)
    goal_pose.append(navigator.getPoseStamped([-1.147, 0.500], TurtleBot4Directions.SOUTH))
    goal_pose.append(SPIN)
    goal_pose.append(navigator.getPoseStamped([-2.029, -0.916], TurtleBot4Directions.EAST))
    goal_pose.append(SPIN)
    goal_pose.append(navigator.getPoseStamped([-2.751, -2.422], TurtleBot4Directions.SOUTH))
    goal_pose.append(SPIN)
    goal_pose.append(navigator.getPoseStamped([-4.389, -1.122], TurtleBot4Directions.WEST))
    goal_pose.append(SPIN)
    goal_pose.append(navigator.getPoseStamped([-2.909, 0.575], TurtleBot4Directions.NORTH))
    goal_pose.append(SPIN)
    goal_pose.append(navigator.getPoseStamped([-2.029, -0.916], TurtleBot4Directions.EAST))
    goal_pose.append(SPIN)
    goal_pose.append(navigator.getPoseStamped([-1.374, -2.439], TurtleBot4Directions.NORTH))
    goal_pose.append(SPIN)
    goal_pose.append(navigator.getPoseStamped([0.0, 0.0], TurtleBot4Directions.NORTH))

    # 순찰 중 정지 서비스 처리 후 같은 단계부터 재개한다.
    evacuation.set_active(True)
    index = 0
    while index < len(goal_pose):
        evacuation.tick()
        if not evacuation.evacuate:
            step = goal_pose[index]
            if step == SPIN:
                succeeded = startSpin(navigator, evacuation=evacuation)
            else:
                if not navigator.goToPose(step):
                    navigator.error('Navigation request was rejected!')
                    return False
                succeeded = evacuation.wait_for_task()
        if evacuation.evacuate:
            if evacuation.event_check is not None:
                evacuation.event_check.pause_and_wait(evacuation, index)
            else:
                evacuation.escape_and_wait(goal_pose, index)
            continue
        if not succeeded:
            navigator.error('Patrol movement/spin failed!')
            return False
        index += 1
    evacuation.set_active(False)

    # Finished navigating, dock
    navigator.dock()
    if not navigator.getDockedStatus():
        navigator.error('Final docking failed!')
        return False

    return True


def execute(goal, ns, settings, event_check=None):
    # The incoming pose is unused: a goal starts the fixed patrol route.
    navigator = None
    evacuation = None
    try:
        navigator = TurtleBot4Navigator(namespace=ns)
        evacuation = Evacuation(navigator, settings, event_check)
        if run_patrol(navigator, evacuation):
            goal.succeed()
        else:
            raise RuntimeError('Patrol failed')
        return NavigateToPose.Result()
    except Exception as exc:
        if navigator is not None:
            navigator.error(f'Patrol error: {exc}')
        # ── 7. 실패 시 다음 목표 금지·현재 이동 취소 및 정지 확인 ──
        if evacuation is not None:
            if event_check is not None:
                event_check.fail(f'Patrol failed: {exc}')
            evacuation.set_active(False)
            try:
                evacuation.stop()
            except Exception as stop_error:
                navigator.error(f'STOP NOT CONFIRMED: {stop_error}')
        goal.abort()
        return NavigateToPose.Result()
    finally:
        if evacuation is not None:
            evacuation.set_active(False)
        if navigator is not None:
            navigator.destroy_node()


def main():
    settings = arguments()
    # TransformListener의 절대 TF 토픽을 각 navigator의 namespace에 연결한다.
    rclpy.init(args=[
        *sys.argv, '--ros-args',
        '-r', '/tf:=tf', '-r', '/tf_static:=tf_static',
    ])
    node = rclpy.create_node('follow_waypoints_server', namespace=settings.namespace)
    event_check = EventCheck(settings)
    event_executor = executors.SingleThreadedExecutor()
    event_executor.add_node(event_check)

    def spin_events():
        try:
            event_executor.spin()
        except ExternalShutdownException:
            pass

    event_thread = threading.Thread(target=spin_events, name='patrol-events')
    event_thread.start()
    ns = node.get_namespace().strip('/')
    server = action.ActionServer(
        node,
        NavigateToPose,
        'patrol_action',
        execute_callback=lambda goal: execute(goal, ns, settings, event_check),
    )
    executor = executors.SingleThreadedExecutor()

    try:
        node.get_logger().info(
            f'Waiting for a goal on {node.get_namespace()}/patrol_action'
        )
        rclpy.spin(node, executor=executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        event_check.set_active(False)
        server.destroy()
        executor.shutdown()
        event_executor.shutdown()
        event_thread.join()
        event_check.destroy_node()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
