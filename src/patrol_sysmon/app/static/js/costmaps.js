"use strict";

const costmapPanel = document.getElementById("parking-map");

if (costmapPanel && costmapPanel.dataset.costmapsUrl) {
    const select = costmapPanel.querySelector("[data-costmap-select]");
    const image = costmapPanel.querySelector("[data-costmap-image]");
    const empty = costmapPanel.querySelector("[data-costmap-empty]");
    const state = costmapPanel.querySelector("[data-costmap-state]");
    const meta = costmapPanel.querySelector("[data-costmap-meta]");
    let latest = [];

    const selectedGrid = () => latest.find(
        (grid) => `${grid.robot_id}:${grid.layer}` === select.value
    );

    const renderSelected = () => {
        const grid = selectedGrid();
        if (!grid || !grid.available) {
            image.hidden = true;
            image.removeAttribute("src");
            empty.hidden = false;
            state.textContent = "수신 대기";
            meta.textContent = "frame · resolution";
            return;
        }
        image.src = grid.image_url;
        image.alt = `${grid.label} 최신 동적 costmap`;
        image.hidden = false;
        empty.hidden = true;
        state.textContent = "수신됨";
        meta.textContent = `${grid.frame_id} · ${grid.resolution} m/cell · ${grid.width}×${grid.height}`;
    };

    const refreshCostmaps = async () => {
        try {
            // [17단계: costmap 갱신] 네 source의 최신 상태만 받아 선택한 격자를 별도 표시한다.
            const response = await fetch(costmapPanel.dataset.costmapsUrl, {
                headers: {"Accept": "application/json"}, cache: "no-store",
            });
            if (!response.ok) throw new Error(`costmap status ${response.status}`);
            latest = (await response.json()).costmaps;
            renderSelected();
        } catch (error) {
            // 마지막 정상 이미지는 유지하고 API 조회 실패 상태만 알린다.
            state.textContent = "조회 실패";
        }
    };

    select.addEventListener("change", renderSelected);
    refreshCostmaps();
    window.setInterval(refreshCostmaps, 2000);
}
