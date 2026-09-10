"use strict";

const patrolSafety = document.getElementById("patrol-safety-status");

if (patrolSafety) {
    const latestVisit = patrolSafety.querySelector("[data-patrol-latest]");
    const unreported = patrolSafety.querySelector("[data-patrol-unreported]");
    const estopState = patrolSafety.querySelector("[data-estop-state]");
    const estopReason = patrolSafety.querySelector("[data-estop-reason]");
    const estopReceived = patrolSafety.querySelector("[data-estop-received]");

    const refreshPatrol = async () => {
        const response = await fetch(patrolSafety.dataset.patrolStatusUrl, {
            headers: {"Accept": "application/json"}, cache: "no-store",
        });
        if (!response.ok) throw new Error(`patrol status ${response.status}`);
        const data = await response.json();
        latestVisit.textContent = data.state_label;
        // [보고 누락] 관제는 결과를 대필하지 않고 보고가 없는 순찰 수만 표시한다.
        unreported.textContent = `${data.unreported.length}건`;
    };

    const refreshSafety = async () => {
        const response = await fetch(patrolSafety.dataset.safetyStatusUrl, {
            headers: {"Accept": "application/json"}, cache: "no-store",
        });
        if (!response.ok) throw new Error(`safety status ${response.status}`);
        const data = await response.json();
        // [상태 구분] 미수신·정상·활성 세 가지를 같은 색으로 표시하지 않는다.
        const tone = !data.estop.available ? "wait" : (data.estop.active ? "active" : "clear");
        estopState.className = `estop-state estop-${tone}`;
        estopState.textContent = data.estop.stale
            ? `${data.estop.state_label} · 수신 지연`
            : data.estop.state_label;
        estopReason.textContent = data.estop.reason || "—";
        estopReceived.textContent = data.estop.received_label;
    };

    const refresh = async () => {
        try {
            await Promise.all([refreshPatrol(), refreshSafety()]);
        } catch (error) {
            // [조회 실패] 마지막 정상 표시값은 유지하고 조회 실패만 구분해 알린다.
            estopState.className = "estop-state estop-wait";
            estopState.textContent = "순찰·안전 조회 실패";
        }
    };

    refresh();
    window.setInterval(refresh, 2000);
}
