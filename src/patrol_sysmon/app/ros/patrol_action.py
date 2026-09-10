"""v2 Patrol Action 피드백·상태와 battery_state를 기존 저장 서비스 입력으로 옮기는 추적기.

patrol_interfaces 2.0에는 RobotStatus·PatrolVisit·PatrolReport가 없다. 관제가 호출하는
Patrol Action의 피드백·상태 토픽과 로봇 battery_state를 합쳐 로봇 상태 한 행, 관측점 방문,
순찰 결과를 만든다. ROS 없이 시험할 수 있게 dict만 주고받는다.

- 로봇 상태: 마지막으로 받은 임무 상태·위치·배터리를 합쳐 매번 한 행을 만든다.
- 방문: 피드백이 WAYPOINT_REACHED로 들어설 때 한 번만 기록한다.
- 결과: 목표 상태가 SUCCEEDED·CANCELED·FAILED가 되면 한 번 기록한다. 결과 본문(사유)은
  상태 토픽에 없어 비워 둔다.

같은 방문·결과는 재시작 뒤에도 같은 ID가 나오도록 로봇·목표·관측점에서 ID를 만든다.
"""

from datetime import datetime, timezone
from hashlib import sha256
import uuid


# 배터리만 바뀐 상태 행은 이 간격보다 자주 만들지 않는다. 임무·위치 변화는 바로 반영한다.
BATTERY_MIN_INTERVAL_SECONDS = 1.0
FINISHED_MISSION_STATES = {"SUCCEEDED": "COMPLETED", "FAILED": "FAILED", "CANCELED": "CANCELED"}


def stable_uuid(*parts):
    """같은 입력이면 항상 같은 UUID v4 형식 문자열을 만든다.

    저장 서비스가 ID를 UUID v4 형식으로 검사하므로, 해시로 만든 16바이트에 v4 표시만 붙인다.
    """
    digest = sha256("\x1f".join(parts).encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16], version=4))


def _iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class PatrolActionTracker:
    """로봇별 마지막 상태와 목표별 방문 진행을 기억한다."""

    def __init__(self):
        self._robots = {}
        self._goals = {}

    def _robot(self, robot_id):
        return self._robots.setdefault(robot_id, {
            "battery": None, "mission": "IDLE", "pose_valid": False, "x": None, "y": None,
            "latest_goal": None, "latest_goal_accepted_at": "", "last_emitted_at": None,
        })

    def _goal(self, robot_id, goal_id):
        return self._goals.setdefault((robot_id, goal_id), {
            "last_state": None, "last_waypoint": "", "waypoint_counts": {}, "visits": 0,
            "finished": False,
        })

    def _status(self, robot_id, now):
        state = self._robot(robot_id)
        state["last_emitted_at"] = now
        return {
            "message_id": str(uuid.uuid4()),
            "robot_id": robot_id,
            "battery": state["battery"],
            "x": state["x"],
            "y": state["y"],
            "frame_id": "map",
            "pose_valid": state["pose_valid"],
            "mission_status": state["mission"],
            # 토픽을 지금 받은 사실만 ONLINE으로 적고, 끊김은 저장된 수신 시각으로 판정한다.
            "connection_status": "ONLINE",
            # 피드백과 배터리는 서로 다른 시계를 쓸 수 있어 관제 수신 시각으로 순서를 맞춘다.
            "observed_at": _iso(now),
        }

    def on_battery(self, payload, now=None):
        """배터리 값을 기억하고, 필요하면 상태 행 하나를 돌려준다."""
        current = now or datetime.now(timezone.utc)
        state = self._robot(payload["robot_id"])
        changed = state["battery"] != payload["battery"]
        state["battery"] = payload["battery"]
        last = state["last_emitted_at"]
        if last is not None and not changed and (
            (current - last).total_seconds() < BATTERY_MIN_INTERVAL_SECONDS
        ):
            return []
        return [("status", self._status(payload["robot_id"], current))]

    def on_feedback(self, payload, now=None):
        """피드백으로 임무 상태·위치를 갱신하고 상태 행과 새 방문을 돌려준다."""
        current = now or datetime.now(timezone.utc)
        robot_id = payload["robot_id"]
        state = self._robot(robot_id)
        goal = self._goal(robot_id, payload["goal_id"])
        state["mission"] = payload["task_state"]
        state["latest_goal"] = payload["goal_id"]
        if payload["pose_valid"]:
            state.update(pose_valid=True, x=payload["x"], y=payload["y"])
        outputs = [("status", self._status(robot_id, current))]

        waypoint = payload["waypoint_id"]
        entered = payload["task_state"] == "WAYPOINT_REACHED" and waypoint and (
            goal["last_state"] != "WAYPOINT_REACHED" or goal["last_waypoint"] != waypoint
        )
        goal["last_state"] = payload["task_state"]
        if entered:
            goal["last_waypoint"] = waypoint
            occurrence = goal["waypoint_counts"].get(waypoint, 0)
            goal["waypoint_counts"][waypoint] = occurrence + 1
            goal["visits"] += 1
            key = (robot_id, payload["goal_id"], waypoint, str(occurrence))
            outputs.append(("visit", {
                "visit_id": stable_uuid("visit", *key),
                "message_id": stable_uuid("visit-message", *key),
                "robot_id": robot_id,
                "patrol_id": payload["goal_id"],
                "waypoint_id": waypoint,
                "x": payload["x"],
                "y": payload["y"],
                "frame_id": "map" if payload["pose_valid"] else None,
                "result": "SUCCEEDED",
                "arrived_at": _iso(current),
            }))
        return outputs

    def on_goal_status(self, payload, now=None):
        """목표 상태 목록에서 새로 끝난 목표의 결과와, 최신 목표가 끝났으면 상태 행을 돌려준다."""
        current = now or datetime.now(timezone.utc)
        robot_id = payload["robot_id"]
        state = self._robot(robot_id)
        outputs = []
        # 상태 토픽은 보존 중인 목표를 모두 다시 싣는다. 가장 늦게 수락된 목표만 현재 임무로 본다.
        for item in payload["goals"]:
            if item["accepted_at"] >= state["latest_goal_accepted_at"]:
                state["latest_goal_accepted_at"] = item["accepted_at"]
                state["latest_goal"] = item["goal_id"]
        for item in payload["goals"]:
            if not item["finished"]:
                continue
            goal = self._goal(robot_id, item["goal_id"])
            if goal["finished"]:
                continue
            goal["finished"] = True
            key = (robot_id, item["goal_id"])
            outputs.append(("report", {
                "patrol_id": item["goal_id"],
                "report_id": stable_uuid("report", *key),
                "message_id": stable_uuid("report-message", *key),
                "robot_id": robot_id,
                "result": item["status"],
                "started_at": item["accepted_at"],
                "ended_at": _iso(current),
            }))
            if item["goal_id"] == state["latest_goal"]:
                state["mission"] = FINISHED_MISSION_STATES[item["status"]]
                outputs.append(("status", self._status(robot_id, current)))
        return outputs
