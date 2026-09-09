"use strict";

const cameraArea = document.getElementById("camera-feeds");

if (cameraArea) {
    const versions = new Map();

    const renderCamera = (camera) => {
        const card = cameraArea.querySelector(`[data-camera-id="${camera.id}"]`);
        if (!card) return;
        const state = card.querySelector("[data-camera-state]");
        state.classList.remove("live", "offline", "waiting");
        state.classList.add(camera.live ? "live" : (camera.available ? "offline" : "waiting"));
        state.querySelector("span").textContent = camera.state_label;
        card.querySelector("[data-camera-received]").textContent = camera.received_label;

        const image = card.querySelector("[data-camera-image]");
        const placeholder = card.querySelector("[data-camera-placeholder]");
        const offline = card.querySelector("[data-camera-offline]");
        if (!camera.available || !camera.frame_url) {
            image.hidden = true;
            image.removeAttribute("src");
            placeholder.hidden = false;
            offline.hidden = true;
            versions.delete(camera.id);
            return;
        }
        // [프레임 교체] 내용 해시가 바뀐 경우만 이미지 요청을 보내 네 영상의 불필요한 재전송을 막는다.
        if (versions.get(camera.id) !== camera.version) {
            image.src = camera.frame_url;
            versions.set(camera.id, camera.version);
        }
        image.hidden = false;
        placeholder.hidden = true;
        offline.hidden = camera.live;
    };

    const refreshCameras = async () => {
        try {
            const response = await fetch(cameraArea.dataset.camerasUrl, {
                headers: {"Accept": "application/json"}, cache: "no-store",
            });
            if (!response.ok) throw new Error(`camera status ${response.status}`);
            const data = await response.json();
            data.cameras.forEach(renderCamera);
        } catch (error) {
            // [조회 실패] 마지막 영상은 유지하고 상태 문구로 대시보드 조회 실패를 알린다.
            cameraArea.querySelectorAll("[data-camera-state]").forEach((state) => {
                state.classList.remove("live", "waiting");
                state.classList.add("offline");
                state.querySelector("span").textContent = "조회 실패";
            });
        }
    };

    refreshCameras();
    // [조회 주기] 어댑터 수신 상한 5 Hz와 맞춰 0.2초마다 조회한다. 1초면 화면이 1 fps로 끊겨 보인다.
    window.setInterval(refreshCameras, 200);
}
