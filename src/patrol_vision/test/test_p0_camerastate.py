"""patrol_interfaces v1.0과 CCTV CameraState 사용부의 정합성을 확인한다."""

from patrol_interfaces.msg import CameraState

from patrol_vision import cam_master


def test_camerastate_v1_enum_and_topic_rules():
    assert CameraState.STATE_UNKNOWN == 0
    assert CameraState.STATE_ENTERING == 1
    assert CameraState.STATE_EXITED == 2
    assert CameraState.STATE_PARKED == 3
    assert CameraState.STATE_EXITING == 4
    assert cam_master.GATE_CAMERA_ID == 'gate_cam'
    assert cam_master.CENTER_CAMERA_ID == 'center_cam'
    assert cam_master.GATE_ALLOWED_STATES == {
        CameraState.STATE_ENTERING, CameraState.STATE_EXITED,
    }
    assert cam_master.CENTER_ALLOWED_STATES == {
        CameraState.STATE_PARKED, CameraState.STATE_EXITING,
    }


def test_patrol_allowed_mapping_and_rate():
    assert cam_master.PATROL_ALLOWED_BY_STATE == {
        CameraState.STATE_ENTERING: False,
        CameraState.STATE_PARKED: True,
        CameraState.STATE_EXITING: False,
        CameraState.STATE_EXITED: True,
    }
    assert cam_master.PATROL_ALLOWED_PUBLISH_HZ == 5.0
