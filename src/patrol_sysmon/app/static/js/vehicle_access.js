"use strict";

const vehicleAccessPanel = document.getElementById("vehicle-access-log");

if (vehicleAccessPanel) {
    const rows = vehicleAccessPanel.querySelector("[data-vehicle-access-rows]");
    const empty = vehicleAccessPanel.querySelector("[data-vehicle-access-empty]");
    const count = vehicleAccessPanel.querySelector("[data-vehicle-access-count]");
    const state = vehicleAccessPanel.querySelector(".event-wait");
    const clearButton = vehicleAccessPanel.querySelector("[data-clear-vehicle-access]");
    let lastSignature = "";

    const addCell = (row, text) => {
        const cell = document.createElement("td");
        cell.textContent = text;
        row.appendChild(cell);
        return cell;
    };

    const renderRow = (item) => {
        const row = document.createElement("tr");
        row.dataset.accessId = item.access_id;
        const timeCell = addCell(row, "");
        const time = document.createElement("time");
        time.dateTime = item.detected_at;
        time.textContent = item.detected_label;
        timeCell.appendChild(time);
        const directionCell = addCell(row, "");
        const direction = document.createElement("span");
        direction.className = `access-direction direction-${item.direction.toLowerCase()}`;
        direction.textContent = item.direction_label;
        directionCell.appendChild(direction);
        addCell(row, `${item.camera_name} ${item.camera_id}`);
        return row;
    };

    const refresh = async () => {
        try {
            // [차량 로그 갱신] 입출차 인식 결과를 3초마다 조회하고 변경된 경우만 다시 그린다.
            const response = await fetch(vehicleAccessPanel.dataset.vehicleAccessUrl, {
                headers: {"Accept": "application/json"}, cache: "no-store",
            });
            if (!response.ok) throw new Error(`vehicle access ${response.status}`);
            const data = await response.json();
            const signature = JSON.stringify(data.accesses.map((item) => [
                item.access_id, item.direction, item.detected_at,
            ]));
            if (signature !== lastSignature) {
                rows.replaceChildren(...data.accesses.map(renderRow));
                empty.hidden = data.accesses.length > 0;
                count.textContent = data.accesses.length;
                state.replaceChildren(count, document.createTextNode("건 표시"));
                lastSignature = signature;
            }
        } catch (error) {
            state.textContent = "입출차 목록 조회 실패";
        }
    };

    clearButton.addEventListener("click", async () => {
        clearButton.disabled = true;
        try {
            // [표시 초기화] 입출차 DB 이력은 유지하고 현재 사용자 목록만 비운다.
            const response = await fetch(vehicleAccessPanel.dataset.clearUrl, {
                method: "POST",
                headers: {"Accept": "application/json", "X-CSRF-Token": vehicleAccessPanel.dataset.csrfToken},
            });
            if (!response.ok) throw new Error(`clear vehicle access ${response.status}`);
            rows.replaceChildren();
            empty.hidden = false;
            count.textContent = "0";
            state.replaceChildren(count, document.createTextNode("건 표시"));
            lastSignature = JSON.stringify([]);
        } catch (error) {
            state.textContent = "표시 초기화 실패";
        } finally {
            clearButton.disabled = false;
        }
    });

    refresh();
    window.setInterval(refresh, 3000);
}
