"use strict";

// [4단계: 관제 시계] 한국 시간을 표시한다. 장비의 데이터 수신 시각과는 별개다.
const clock = document.getElementById("dashboard-clock");
if (clock) {
    const formatter = new Intl.DateTimeFormat("ko-KR", {
        timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
    });
    const updateClock = () => {
        const now = new Date();
        clock.dateTime = now.toISOString();
        clock.textContent = formatter.format(now);
    };
    updateClock();
    window.setInterval(updateClock, 1000);
}

const statusArea = document.getElementById("robot-status");

const setConnection = (container, robot) => {
    const badge = container.querySelector(".robot-connection");
    if (!badge) return;
    badge.classList.remove("online", "offline", "unknown");
    badge.classList.add(robot.connection_status.toLowerCase());
    const label = badge.querySelector('[data-field="connection-label"]');
    if (label) label.textContent = robot.connection_label;
};

const renderRobot = (robot) => {
    const card = statusArea.querySelector(`[data-robot-id="${robot.id}"]`);
    const sidebar = document.querySelector(`[data-sidebar-robot-id="${robot.id}"]`);
    if (!card) return;
    setConnection(card, robot);
    if (sidebar) setConnection(sidebar, robot);
    card.querySelector('[data-field="battery"]').textContent = robot.battery === null ? "—" : Math.round(robot.battery);
    card.querySelector('[data-field="battery-fill"]').style.width = `${robot.battery === null ? 0 : robot.battery}%`;
    card.querySelector('[data-field="mission"]').textContent = robot.mission_label;
    card.querySelector('[data-field="location"]').textContent = robot.location_label;
    card.querySelector('[data-field="received"]').textContent = robot.received_label;
};

const refreshRobotStatus = async () => {
    try {
        // [5단계: 화면 갱신] 로그인 세션으로 최신 상태만 조회하며 장치 수신 토큰은 브라우저에 노출하지 않는다.
        const response = await fetch(statusArea.dataset.statusUrl, {headers: {"Accept": "application/json"}, cache: "no-store"});
        if (!response.ok) throw new Error(`status ${response.status}`);
        const data = await response.json();
        data.robots.forEach(renderRobot);
        // [상단 상태 동기화] 헤더와 상태 요약 카드에 같은 최신 값을 표시한다.
        document.querySelectorAll('[data-fleet-connection]').forEach((element) => {
            element.textContent = data.fleet_status;
        });
        const mode = data.robots.some((robot) => robot.has_status)
            ? "로봇 상태 수신 중" : "로봇 상태 수신 대기";
        document.querySelectorAll('[data-dashboard-mode]').forEach((element) => {
            element.textContent = mode;
        });
    } catch (error) {
        // [조회 실패] 마지막 정상 표시값은 유지하고 화면 갱신 실패만 구분해 알린다.
        document.querySelectorAll('[data-dashboard-mode]').forEach((element) => {
            element.textContent = "로봇 상태 조회 실패";
        });
    }
};

if (statusArea) {
    refreshRobotStatus();
    window.setInterval(refreshRobotStatus, 2000);
}
