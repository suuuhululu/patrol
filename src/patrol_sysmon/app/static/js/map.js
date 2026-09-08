"use strict";

const mapPanel = document.getElementById("parking-map");

if (mapPanel) {
    const svgNamespace = "http://www.w3.org/2000/svg";
    const canvas = mapPanel.querySelector("[data-map-canvas]");
    const image = mapPanel.querySelector("[data-map-image]");
    const pathsLayer = mapPanel.querySelector("[data-map-paths]");
    const robotsLayer = mapPanel.querySelector("[data-map-robots]");
    const empty = mapPanel.querySelector("[data-map-empty]");
    const state = mapPanel.querySelector("[data-map-state]");
    const meta = mapPanel.querySelector("[data-map-meta]");
    const alert = mapPanel.querySelector("[data-map-alert]");

    const clearLayer = (layer) => {
        while (layer.firstChild) layer.removeChild(layer.firstChild);
    };

    const renderPath = (path) => {
        if (path.points.length < 2) return;
        const line = document.createElementNS(svgNamespace, "polyline");
        line.setAttribute("class", `map-path ${path.robot_id.toLowerCase()}`);
        line.setAttribute("points", path.points.map((point) => `${point.x},${point.y}`).join(" "));
        pathsLayer.appendChild(line);
    };

    const renderRobot = (robot, mapData) => {
        if (!robot.inside_map) return;
        const group = document.createElementNS(svgNamespace, "g");
        // [위치 유효성] 마지막 유효 위치는 속이 빈 점선 원과 다른 문구로 구분한다.
        const poseClass = robot.pose_valid === false ? " pose-stale" : "";
        group.setAttribute("class", `map-robot-marker ${robot.id.toLowerCase()} ${robot.connection_status.toLowerCase()}${poseClass}`);
        group.setAttribute("transform", `translate(${robot.x} ${robot.y})`);
        const radius = Math.max(2.2, Math.min(mapData.width, mapData.height) * 0.025);
        const circle = document.createElementNS(svgNamespace, "circle");
        circle.setAttribute("r", radius);
        const label = document.createElementNS(svgNamespace, "text");
        label.setAttribute("y", -(radius * 1.5));
        label.setAttribute("font-size", radius * 1.45);
        label.textContent = robot.pose_label || robot.id;
        group.append(circle, label);
        robotsLayer.appendChild(group);
    };

    const renderMap = (mapData) => {
        if (!mapData.available) {
            canvas.hidden = true;
            empty.hidden = false;
            state.textContent = mapData.state_label;
            meta.textContent = "수신 전";
            alert.textContent = "";
            return;
        }
        canvas.setAttribute("viewBox", `0 0 ${mapData.width} ${mapData.height}`);
        image.setAttribute("href", mapData.image_url);
        canvas.hidden = false;
        empty.hidden = true;
        state.textContent = mapData.state_label;
        meta.textContent = `${mapData.frame_id} · ${mapData.resolution} m/px`;
        clearLayer(pathsLayer);
        clearLayer(robotsLayer);
        mapData.paths.forEach(renderPath);
        mapData.robots.forEach((robot) => renderRobot(robot, mapData));
        const outside = mapData.robots.filter((robot) => !robot.inside_map).map((robot) => robot.id);
        const warnings = [...mapData.coordinate_warnings];
        if (outside.length) warnings.push(`${outside.join(", ")} 좌표가 지도 범위를 벗어났습니다.`);
        alert.textContent = warnings.join(" ");
    };

    const refreshMap = async () => {
        try {
            // [6단계: 지도 갱신] 장치 토큰 없이 로그인 세션으로 웹 표시 데이터만 조회한다.
            const response = await fetch(mapPanel.dataset.mapUrl, {headers: {"Accept": "application/json"}, cache: "no-store"});
            if (!response.ok) throw new Error(`map status ${response.status}`);
            renderMap(await response.json());
        } catch (error) {
            // [조회 실패] 마지막 정상 지도는 유지하고 연결 실패만 표시한다.
            state.textContent = "지도 조회 실패";
        }
    };

    refreshMap();
    window.setInterval(refreshMap, 2000);
}
