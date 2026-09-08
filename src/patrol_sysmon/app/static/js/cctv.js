"use strict";

const cctvStatus = document.getElementById("cctv-status");

if (cctvStatus) {
    const permit = cctvStatus.querySelector("[data-patrol-permit]");
    const received = cctvStatus.querySelector("[data-patrol-permit-received]");
    const latest = cctvStatus.querySelector("[data-cctv-latest]");

    const refresh = async () => {
        try {
            // [19단계: permit 경고] 1.5초 timeout을 화면에서 놓치지 않도록 0.5초마다 조회한다.
            const response = await fetch(cctvStatus.dataset.cctvStatusUrl, {
                headers: {"Accept": "application/json"}, cache: "no-store",
            });
            if (!response.ok) throw new Error(`cctv status ${response.status}`);
            const data = await response.json();
            permit.className = `permit-state permit-${data.permit.state.toLowerCase()}`;
            permit.textContent = data.permit.status_label;
            received.textContent = data.permit.received_label;
            latest.textContent = data.latest_event
                ? `${data.latest_event.camera_name} · ${data.latest_event.state_label}`
                : "CameraState 수신 대기";
        } catch (error) {
            permit.className = "permit-state permit-stale";
            permit.textContent = "CCTV 상태 조회 실패";
        }
    };

    refresh();
    window.setInterval(refresh, 500);
}
