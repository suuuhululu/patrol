"use strict";

const eventsPanel = document.getElementById("event-log");

if (eventsPanel) {
    const rows = eventsPanel.querySelector("[data-event-rows]");
    const empty = eventsPanel.querySelector("[data-events-empty]");
    const count = eventsPanel.querySelector("[data-event-count]");
    const waitLabel = eventsPanel.querySelector(".event-wait");
    const dialog = document.querySelector("[data-event-dialog]");
    const canUpdate = eventsPanel.dataset.canUpdate === "true";
    const clearButton = eventsPanel.querySelector("[data-clear-events]");
    let currentEventId = null;
    let lastSignature = "";

    const endpoint = (template, eventId) => template.replace("__EVENT_ID__", encodeURIComponent(eventId));

    const addTextCell = (row, text) => {
        const cell = document.createElement("td");
        cell.textContent = text;
        row.appendChild(cell);
        return cell;
    };

    const openDetail = async (eventId) => {
        currentEventId = eventId;
        const message = dialog.querySelector("[data-status-message]");
        message.textContent = "";
        try {
            // [8단계: 상세 조회] 로그인 세션으로 선택한 이벤트와 처리 이력을 가져온다.
            const response = await fetch(
                endpoint(eventsPanel.dataset.detailUrlTemplate, eventId),
                {headers: {"Accept": "application/json"}, cache: "no-store"},
            );
            if (!response.ok) throw new Error(`event detail ${response.status}`);
            renderDetail((await response.json()).event);
            if (!dialog.open) dialog.showModal();
        } catch (error) {
            waitLabel.textContent = "이벤트 상세 조회 실패";
        }
    };

    const renderEventRow = (event) => {
        const row = document.createElement("tr");
        row.dataset.eventId = event.event_id;
        const timeCell = addTextCell(row, "");
        const time = document.createElement("time");
        time.dateTime = event.occurred_at;
        time.textContent = event.occurred_label;
        timeCell.appendChild(time);
        const typeCell = addTextCell(row, "");
        const type = document.createElement("button");
        type.type = "button";
        type.className = "compact-event-button";
        type.dataset.eventDetail = event.event_id;
        type.textContent = event.event_label;
        type.addEventListener("click", () => openDetail(event.event_id));
        typeCell.appendChild(type);
        addTextCell(row, `${event.robot_name} ${event.robot_id}`);
        addTextCell(row, event.location_label);
        // [증적 상태] 지연·누락은 주황으로 구분해 조치가 필요한 사건을 놓치지 않게 한다.
        if (["DELAYED", "MISSING"].includes(event.evidence_state)) {
            const warning = document.createElement("span");
            warning.className = `evidence-warning evidence-${event.evidence_state.toLowerCase()}`;
            warning.textContent = ` 증적 ${event.evidence_state_label}`;
            timeCell.appendChild(warning);
        }
        const riskCell = addTextCell(row, "");
        const risk = document.createElement("span");
        // 서비스로 받은 사건은 위험도가 없어 risk_level이 null이다.
        risk.className = `risk-badge risk-${(event.risk_level || "none").toLowerCase()}`;
        risk.textContent = event.risk_label;
        riskCell.appendChild(risk);
        const statusCell = addTextCell(row, "");
        const status = document.createElement("span");
        status.className = `event-status status-${event.status.toLowerCase()}`;
        status.textContent = event.status_label;
        statusCell.appendChild(status);
        const evidenceCell = addTextCell(row, "");
        if (event.evidence_url) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "evidence-button";
            button.dataset.eventDetail = event.event_id;
            const image = document.createElement("img");
            image.src = event.evidence_url;
            image.alt = `${event.robot_name} ${event.event_label} 증거 이미지`;
            image.loading = "lazy";
            const label = document.createElement("span");
            label.textContent = "상세 보기";
            button.append(image, label);
            button.addEventListener("click", () => openDetail(event.event_id));
            evidenceCell.appendChild(button);
        } else {
            evidenceCell.textContent = "없음";
        }
        return row;
    };

    const renderEvents = (events) => {
        rows.replaceChildren(...events.map(renderEventRow));
        empty.hidden = events.length > 0;
        count.textContent = events.length;
        waitLabel.replaceChildren(count, document.createTextNode("건 표시"));
    };

    const renderHistory = (changes) => {
        const history = dialog.querySelector("[data-change-history]");
        if (!changes.length) {
            const item = document.createElement("li");
            item.className = "history-empty";
            item.textContent = "아직 처리 이력이 없습니다.";
            history.replaceChildren(item);
            return;
        }
        const items = changes.map((change) => {
            const item = document.createElement("li");
            const summary = document.createElement("strong");
            summary.textContent = `${change.previous_label} → ${change.new_label}`;
            const actor = document.createElement("span");
            actor.textContent = `${change.username} · ${change.changed_label}`;
            item.append(summary, actor);
            if (change.memo) {
                const memo = document.createElement("p");
                memo.textContent = change.memo;
                item.appendChild(memo);
            }
            return item;
        });
        history.replaceChildren(...items);
    };

    const renderDetail = (event) => {
        dialog.querySelector("[data-detail-title]").textContent = `${event.event_label} 이벤트 상세`;
        dialog.querySelector("[data-detail-event-id]").textContent = event.event_id;
        dialog.querySelector("[data-detail-occurred]").textContent = event.occurred_label;
        dialog.querySelector("[data-detail-robot]").textContent = `${event.robot_name} (${event.robot_id})`;
        dialog.querySelector("[data-detail-location]").textContent = event.location_label;
        dialog.querySelector("[data-detail-risk]").textContent = `위험도 ${event.risk_label}`;
        dialog.querySelector("[data-detail-status]").textContent = event.status_label;
        dialog.querySelector("[data-detail-captured]").textContent = `촬영 시각 ${event.captured_label}`;
        const image = dialog.querySelector("[data-detail-image]");
        image.src = event.evidence_url || "";
        image.alt = `${event.robot_name} ${event.event_label} 증거 이미지`;
        image.hidden = !event.evidence_url;
        const action = dialog.querySelector("[data-event-action]");
        const button = dialog.querySelector("[data-status-action]");
        action.hidden = !canUpdate || !event.next_status;
        if (event.next_status) {
            button.dataset.nextStatus = event.next_status;
            button.textContent = event.next_status === "WORK_REQUESTED"
                ? "작업요청 상태 기록" : `${event.next_status_label}으로 변경`;
            button.disabled = false;
        }
        dialog.querySelector("[data-event-memo]").value = "";
        renderHistory(event.changes);
    };

    const refreshEvents = async (force = false) => {
        try {
            // [8단계: 목록 갱신] 새 이벤트와 상태 변경을 3초마다 반영한다.
            const response = await fetch(eventsPanel.dataset.eventsUrl, {
                headers: {"Accept": "application/json"}, cache: "no-store",
            });
            if (!response.ok) throw new Error(`events ${response.status}`);
            const data = await response.json();
            const signature = JSON.stringify(data.events.map((event) => [
                event.event_id, event.status, event.risk_level, event.occurred_at,
            ]));
            if (force || signature !== lastSignature) {
                renderEvents(data.events);
                lastSignature = signature;
            }
        } catch (error) {
            waitLabel.textContent = "이벤트 목록 조회 실패";
        }
    };

    rows.querySelectorAll("[data-event-detail]").forEach((button) => {
        button.addEventListener("click", () => openDetail(button.dataset.eventDetail));
    });
    dialog.querySelector("[data-dialog-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
    });
    dialog.querySelector("[data-status-action]").addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const message = dialog.querySelector("[data-status-message]");
        button.disabled = true;
        message.textContent = "저장 중…";
        try {
            // [관제 기록] 상태와 메모만 저장하며 로봇 제어 endpoint는 호출하지 않는다.
            const response = await fetch(
                endpoint(eventsPanel.dataset.statusUrlTemplate, currentEventId),
                {
                    method: "POST",
                    headers: {
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "X-CSRF-Token": eventsPanel.dataset.csrfToken,
                    },
                    body: JSON.stringify({
                        status: button.dataset.nextStatus,
                        memo: dialog.querySelector("[data-event-memo]").value,
                    }),
                },
            );
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || `status ${response.status}`);
            await refreshEvents(true);
            await openDetail(currentEventId);
            dialog.querySelector("[data-status-message]").textContent = "처리 상태를 기록했습니다.";
        } catch (error) {
            message.textContent = error.message;
            button.disabled = false;
        }
    });

    clearButton.addEventListener("click", async () => {
        clearButton.disabled = true;
        try {
            // [표시 초기화] DB 이벤트는 삭제하지 않고 사용자별 목록 기준 시각만 저장한다.
            const response = await fetch(eventsPanel.dataset.clearUrl, {
                method: "POST",
                headers: {"Accept": "application/json", "X-CSRF-Token": eventsPanel.dataset.csrfToken},
            });
            if (!response.ok) throw new Error(`clear events ${response.status}`);
            renderEvents([]);
            lastSignature = JSON.stringify([]);
            if (dialog.open) dialog.close();
        } catch (error) {
            waitLabel.textContent = "표시 초기화 실패";
        } finally {
            clearButton.disabled = false;
        }
    });

    refreshEvents(true);
    window.setInterval(refreshEvents, 3000);
}
