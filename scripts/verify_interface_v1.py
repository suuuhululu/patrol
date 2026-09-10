#!/usr/bin/env python3
"""Verify the patrol_interfaces 2.0.0 source and optional installed types."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


EXPECTED_VERSION = "2.0.0"
EXPECTED_INTERFACES = {
    "action": ("DetectEvent", "Patrol"),
    "msg": ("CameraState", "DriveToken", "EStop", "PatrolCommand"),
    "srv": ("ReportDetection",),
}
REMOVED_MESSAGES = (
    "AlignmentStatus",
    "CommandCheck",
    "ControlHeartbeat",
    "DetectionCandidate",
    "DetectionEvent",
    "DetectionResult",
    "EvidenceChunk",
    "IngestionAck",
    "KeepoutStatus",
    "MissionCommand",
    "PatrolReport",
    "PatrolVisit",
    "RobotStatus",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _schema_lines(data: bytes) -> list[str]:
    """Return normalized ROS declarations and section delimiters."""
    lines = []
    for raw_line in data.decode("utf-8").splitlines():
        declaration = raw_line.partition("#")[0].strip()
        if declaration:
            lines.append(" ".join(declaration.split()))
    return lines


def _schema_digest(data: bytes) -> str:
    normalized = "\n".join(_schema_lines(data)) + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _schema_sections(data: bytes) -> list[list[str]]:
    sections: list[list[str]] = [[]]
    for declaration in _schema_lines(data):
        if declaration == "---":
            sections.append([])
        else:
            sections[-1].append(declaration)
    return sections


def _declarations(lines: list[str]) -> tuple[dict[str, str], dict[str, object]]:
    fields: dict[str, str] = {}
    constants: dict[str, object] = {}
    for declaration in lines:
        type_name, name_and_value = declaration.split(maxsplit=1)
        if "=" in name_and_value:
            name, value = name_and_value.split("=", maxsplit=1)
            if value.lower() in ("true", "false"):
                parsed: object = value.lower() == "true"
            else:
                parsed = ast.literal_eval(value)
            constants[name] = parsed
            continue
        normalized_type = {
            "bool": "boolean",
            "float32": "float",
            "float64": "double",
        }.get(type_name, type_name)
        if normalized_type.endswith("[]"):
            normalized_type = f"sequence<{normalized_type[:-2]}>"
        fields[name_and_value] = normalized_type
    return fields, constants


def _source_report(root: Path) -> dict[str, object]:
    package = root / "src" / "patrol_interfaces"
    package_version = ET.parse(package / "package.xml").getroot().findtext("version")
    marker_version = (package / "INTERFACE_VERSION").read_text(encoding="utf-8").strip()
    _require(package_version == EXPECTED_VERSION, f"package.xml version={package_version!r}")
    _require(marker_version == EXPECTED_VERSION, f"INTERFACE_VERSION={marker_version!r}")

    cmake = (package / "CMakeLists.txt").read_text(encoding="utf-8")
    hashes: dict[str, str] = {}
    combined = hashlib.sha256()
    extensions = {"action": "action", "msg": "msg", "srv": "srv"}
    expected_section_counts = {"action": 3, "msg": 1, "srv": 2}

    for kind, names in EXPECTED_INTERFACES.items():
        source_dir = package / kind
        extension = extensions[kind]
        actual = tuple(sorted(path.stem for path in source_dir.glob(f"*.{extension}")))
        _require(actual == names, f"{kind} set mismatch: {actual!r}")
        for name in names:
            relative = f"{kind}/{name}.{extension}"
            _require(cmake.count(f'"{relative}"') == 1, f"CMake registration mismatch: {relative}")
            data = (package / relative).read_bytes()
            sections = _schema_sections(data)
            _require(
                len(sections) == expected_section_counts[kind],
                f"section count mismatch: {relative}",
            )
            digest = _schema_digest(data)
            hashes[relative] = digest
            combined.update(f"{relative}:{digest}\n".encode())

    msg_dir = package / "msg"
    for name in REMOVED_MESSAGES:
        _require(not (msg_dir / f"{name}.msg").exists(), f"removed message exists: {name}")

    required_fragments = {
        "action/Patrol.action": (
            "uint8 WAYPOINT_REACHED=11",
            "uint8 outcome",
            "string current_waypoint_id",
        ),
        "action/DetectEvent.action": (
            "string detection_id",
            "bool confirmed",
            "float32 confirm_elapsed",
        ),
        "msg/PatrolCommand.msg": (
            "uint8 MOVE_TO_SAFE_ZONE=1",
            "uint8 RESUME_PATROL=2",
        ),
        "msg/DriveToken.msg": (
            "string token",
            "uint32 sequence",
        ),
        "msg/CameraState.msg": (
            "uint8 STATE_UNKNOWN=0",
            "uint8 STATE_EXITING=4",
        ),
        "srv/ReportDetection.srv": (
            "uint8[] image",
            "uint8 STORED=0",
            "uint8 REJECTED=2",
        ),
    }
    for relative, fragments in required_fragments.items():
        text = (package / relative).read_text(encoding="utf-8")
        for fragment in fragments:
            _require(fragment in text, f"{relative} missing {fragment!r}")

    return {
        "contract_version": "v2.0",
        "package_version": EXPECTED_VERSION,
        "interface_count": sum(len(names) for names in EXPECTED_INTERFACES.values()),
        "hash_scope": "normalized ROS declarations; comments and blank lines excluded",
        "interface_manifest_sha256": combined.hexdigest(),
        "interfaces": hashes,
    }


def _verify_type(source: Path, generated_types: tuple[type, ...]) -> None:
    sections = _schema_sections(source.read_bytes())
    _require(len(sections) == len(generated_types), f"section mismatch: {source.name}")
    for lines, generated_type in zip(sections, generated_types, strict=True):
        expected_fields, expected_constants = _declarations(lines)
        _require(
            generated_type.get_fields_and_field_types() == expected_fields,
            f"installed field mismatch: {generated_type.__name__}",
        )
        for constant, expected in expected_constants.items():
            _require(
                getattr(generated_type, constant, object()) == expected,
                f"installed constant mismatch: {generated_type.__name__}.{constant}",
            )


def _verify_installed(root: Path) -> None:
    package = root / "src" / "patrol_interfaces"
    action_module = importlib.import_module("patrol_interfaces.action")
    msg_module = importlib.import_module("patrol_interfaces.msg")
    srv_module = importlib.import_module("patrol_interfaces.srv")

    for name in EXPECTED_INTERFACES["action"]:
        action_type = getattr(action_module, name)
        _verify_type(
            package / "action" / f"{name}.action",
            (action_type.Goal, action_type.Result, action_type.Feedback),
        )
    for name in EXPECTED_INTERFACES["msg"]:
        _verify_type(package / "msg" / f"{name}.msg", (getattr(msg_module, name),))
    for name in EXPECTED_INTERFACES["srv"]:
        srv_type = getattr(srv_module, name)
        _verify_type(
            package / "srv" / f"{name}.srv",
            (srv_type.Request, srv_type.Response),
        )

    old_installed = [name for name in REMOVED_MESSAGES if hasattr(msg_module, name)]
    _require(not old_installed, f"removed messages still installed: {old_installed}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        report = _source_report(root)
        if args.installed:
            _verify_installed(root)
            report["installed_import"] = "PASS"
    except (AttributeError, ImportError, OSError, ValueError, ET.ParseError) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    report["result"] = "PASS"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
