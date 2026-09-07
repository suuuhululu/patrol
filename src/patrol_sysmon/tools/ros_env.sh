# ROS 2와 sysmon을 한 터미널에서 함께 쓰기 위한 환경 설정.
# 실행이 아니라 source 해야 현재 터미널에 남는다.
#   사용법: source tools/ros_env.sh [도메인ID]

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo "이 파일은 실행하지 말고 source 하세요:  source tools/ros_env.sh" >&2
    exit 1
fi

# [venv 해제] rokey_venv 등이 켜져 있으면 flask도 rclpy도 보이지 않는다.
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate 2>/dev/null || true
fi

SYSMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
source /home/hun/rokey_ws/install/setup.bash
# [경로 추가] 덮어쓰면 ROS가 설정한 rclpy 경로가 사라지므로 반드시 뒤에 붙인다.
export PYTHONPATH="$PYTHONPATH:$SYSMON_DIR/.venv/lib/python3.12/site-packages"
export ROS_DOMAIN_ID="${1:-80}"
cd "$SYSMON_DIR" || return 1

python3 - <<'PY'
import importlib.util
import os

missing = [name for name in ("flask", "rclpy", "parking_interfaces.msg")
           if importlib.util.find_spec(name) is None]
print("준비 완료" if not missing else "빠진 모듈: " + ", ".join(missing),
      "· ROS_DOMAIN_ID=" + os.environ.get("ROS_DOMAIN_ID", ""))
PY
