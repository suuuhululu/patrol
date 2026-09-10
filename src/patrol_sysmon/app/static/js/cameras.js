"use strict";

const cameraArea = document.getElementById("camera-feeds");

if (cameraArea) {
    // [5 Hz 표시] 카메라 목록을 0.2초마다 조회한다. 서버 수신도 CAMERA_MAX_HZ=5로 맞춰져 있다.
    const REFRESH_MS = 200;
    const versions = new Map();
    // 카메라별로 받는 중인 이미지와 그다음에 보여 줄 주소. 받는 중에 새 주소를 넣으면
    // 이전 요청이 취소돼 느린 망에서 영상이 멈추므로, 한 장씩 끝난 뒤 가장 최신 것만 요청한다.
    const loading = new Map();
    const pending = new Map();

    const loadFrame = (cameraId, image, url) => {
        if (loading.get(cameraId)) {
            pending.set(cameraId, url);
            return;
        }
        loading.set(cameraId, true);
        const next = new Image();
        const done = () => {
            loading.set(cameraId, false);
            const queued = pending.get(cameraId);
            pending.delete(cameraId);
            if (queued && queued !== url) loadFrame(cameraId, image, queued);
        };
        // 다 받은 뒤에 바꿔야 교체 순간 빈 화면이 보이지 않는다.
        next.onload = () => {
            image.src = url;
            done();
        };
        next.onerror = done;
        next.src = url;
    };

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
            pending.delete(camera.id);
            return;
        }
        // [프레임 교체] 내용 해시가 바뀐 경우만 이미지 요청을 보내 네 영상의 불필요한 재전송을 막는다.
        if (versions.get(camera.id) !== camera.version) {
            loadFrame(camera.id, image, camera.frame_url);
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

    // setInterval은 이전 조회가 끝나지 않아도 다음 조회를 보내 응답이 밀린다. 끝난 뒤 다음 조회를 예약한다.
    const loop = async () => {
        const started = performance.now();
        await refreshCameras();
        window.setTimeout(loop, Math.max(0, REFRESH_MS - (performance.now() - started)));
    };
    loop();
}
