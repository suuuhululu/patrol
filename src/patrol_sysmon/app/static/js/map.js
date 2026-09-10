"use strict";

const mapPanel = document.getElementById("parking-map");

if (mapPanel) {
    const svgNamespace = "http://www.w3.org/2000/svg";
    const viewport = mapPanel.querySelector("[data-map-viewport]");
    const canvas = mapPanel.querySelector("[data-map-canvas]");
    const layer = mapPanel.querySelector("[data-map-layer]");
    const image = mapPanel.querySelector("[data-map-image]");
    const pathsLayer = mapPanel.querySelector("[data-map-paths]");
    const robotsLayer = mapPanel.querySelector("[data-map-robots]");
    const empty = mapPanel.querySelector("[data-map-empty]");
    const alert = mapPanel.querySelector("[data-map-alert]");
    const sourceButtons = [...mapPanel.querySelectorAll("[data-map-source]")];
    // 사용자가 버튼을 누르기 전에는 서버가 가장 최근에 받은 로봇을 고른다.
    let selectedRobot = null;
    let requestSequence = 0;
    let lastMap = null;
    let rotated = false;

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
        // 지도를 돌려도 이름표는 화면 기준으로 원 위에 똑바로 선다.
        label.setAttribute("transform", rotated
            ? `translate(${-(radius * 1.5)} 0) rotate(-90)`
            : `translate(0 ${-(radius * 1.5)})`);
        label.setAttribute("font-size", radius * 1.45);
        label.textContent = robot.pose_label || robot.id;
        group.append(circle, label);
        robotsLayer.appendChild(group);
    };

    const renderSources = (mapData) => {
        const available = new Set(mapData.sources.filter((source) => source.available).map((source) => source.robot_id));
        sourceButtons.forEach((button) => {
            button.disabled = !available.has(button.dataset.mapSource);
            button.setAttribute("aria-pressed", String(button.dataset.mapSource === mapData.source_robot));
        });
    };

    const swapImage = (url) => {
        if (image.getAttribute("href") === url) return;
        // [깜빡임 방지] costmap PNG는 새 격자가 오면 지워지므로, 새 이미지를 다 받은 뒤에만 바꾼다.
        const preload = new Image();
        preload.onload = () => image.setAttribute("href", url);
        preload.src = url;
    };

    const shouldRotate = (width, height) => {
        // 패널에 더 크게 들어가는 방향을 고른다. 5% 여유는 경계에서 방향이 흔들리지 않게 한다.
        const boxWidth = viewport.clientWidth;
        const boxHeight = viewport.clientHeight;
        if (!boxWidth || !boxHeight) return rotated;
        const upright = Math.min(boxWidth / width, boxHeight / height);
        const turned = Math.min(boxWidth / height, boxHeight / width);
        return turned > upright * 1.05;
    };

    const applyOrientation = (mapData) => {
        const {width, height} = mapData;
        rotated = shouldRotate(width, height);
        if (rotated) {
            // 시계 방향 90°: 격자 (x, y) -> 화면 (height - y, x)
            canvas.setAttribute("viewBox", `0 0 ${height} ${width}`);
            layer.setAttribute("transform", `translate(${height} 0) rotate(90)`);
        } else {
            canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
            layer.removeAttribute("transform");
        }
        image.setAttribute("width", width);
        image.setAttribute("height", height);
    };

    const renderMap = (mapData) => {
        renderSources(mapData);
        lastMap = mapData;
        if (!mapData.available) {
            canvas.hidden = true;
            empty.hidden = false;
            alert.textContent = "";
            return;
        }
        canvas.hidden = false;
        empty.hidden = true;
        applyOrientation(mapData);
        swapImage(mapData.image_url);
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
        const sequence = ++requestSequence;
        const url = new URL(mapPanel.dataset.mapUrl, window.location.origin);
        if (selectedRobot) url.searchParams.set("robot", selectedRobot);
        try {
            // [6단계: 지도 갱신] 장치 토큰 없이 로그인 세션으로 웹 표시 데이터만 조회한다.
            const response = await fetch(url, {headers: {"Accept": "application/json"}, cache: "no-store"});
            if (!response.ok) throw new Error(`map status ${response.status}`);
            const mapData = await response.json();
            // 버튼을 누르기 전에 보낸 늦은 응답이 방금 고른 로봇 화면을 덮지 않게 한다.
            if (sequence === requestSequence) renderMap(mapData);
        } catch (error) {
            // [조회 실패] 마지막 정상 지도는 유지하고 연결 실패만 표시한다.
            if (sequence === requestSequence) alert.textContent = "지도 조회 실패";
        }
    };

    sourceButtons.forEach((button) => button.addEventListener("click", () => {
        selectedRobot = button.dataset.mapSource;
        sourceButtons.forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
        refreshMap();
    }));

    // 패널 크기가 바뀌면(창 크기·레이아웃 변경) 회전 방향을 다시 고른다.
    new ResizeObserver(() => {
        if (lastMap && lastMap.available && shouldRotate(lastMap.width, lastMap.height) !== rotated) {
            renderMap(lastMap);
        }
    }).observe(viewport);

    refreshMap();
    window.setInterval(refreshMap, 2000);
}
