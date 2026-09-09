#!/usr/bin/env python3
"""Verify the patrol_interfaces v1.0 source and print its portable fingerprint."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


EXPECTED_VERSION = "1.0.0"
EXPECTED_MESSAGES = (
    "AlignmentStatus",
    "CameraState",
    "CommandCheck",
    "ControlHeartbeat",
    "DetectionCandidate",
    "DetectionEvent",
    "DriveToken",
    "EStop",
    "EvidenceChunk",
    "IngestionAck",
    "KeepoutStatus",
    "MissionCommand",
    "PatrolReport",
    "PatrolVisit",
    "RobotStatus",
)
REMOVED_MESSAGES = ("EStopState", "MissionCommandAck")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _schema_lines(data: bytes) -> list[str]:
    """Return normalized ROS declarations, excluding comments and blank lines."""
    lines = []
    for raw_line in data.decode("utf-8").splitlines():
        declaration = raw_line.partition("#")[0].strip()
        if declaration:
            lines.append(" ".join(declaration.split()))
    return lines


def _schema_digest(data: bytes) -> str:
    normalized = "\n".join(_schema_lines(data)) + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _source_declarations(data: bytes) -> tuple[dict[str, str], dict[str, object]]:
    fields: dict[str, str] = {}
    constants: dict[str, object] = {}
    for declaration in _schema_lines(data):
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
    msg_dir = package / "msg"
    package_version = ET.parse(package / "package.xml").getroot().findtext("version")
    marker_version = (package / "INTERFACE_VERSION").read_text(encoding="utf-8").strip()
    _require(package_version == EXPECTED_VERSION, f"package.xml version={package_version!r}")
    _require(marker_version == EXPECTED_VERSION, f"INTERFACE_VERSION={marker_version!r}")

    actual = tuple(sorted(path.stem for path in msg_dir.glob("*.msg")))
    _require(actual == EXPECTED_MESSAGES, f"message set mismatch: {actual!r}")
    for removed in REMOVED_MESSAGES:
        _require(not (msg_dir / f"{removed}.msg").exists(), f"removed message exists: {removed}")

    cmake = (package / "CMakeLists.txt").read_text(encoding="utf-8")
    for name in EXPECTED_MESSAGES:
        _require(cmake.count(f'"msg/{name}.msg"') == 1, f"CMake registration mismatch: {name}")

    required_fragments = {
        "CommandCheck": ("uint8 CHECK_UNKNOWN=0", "uint8 CHECK_REJECTED=3"),
        "ControlHeartbeat": ("string control_session_id", "uint64 sequence"),
        "EStop": ("string TARGET_ALL=\"all\"", "uint8 ESTOP_REASON_SYSTEM_FAULT=6"),
        "MissionCommand": ("geometry_msgs/PoseStamped target_pose",),
        "RobotStatus": ("uint8 SAFETY_UNKNOWN=0", "uint8 SAFETY_ERROR=5"),
        "CameraState": ("uint8 STATE_UNKNOWN=0", "uint8 STATE_EXITING=4"),
    }
    forbidden_fragments = {
        "EStop": ("bool latched", "manual_reset_required"),
        "MissionCommand": ("string parameters_json",),
    }
    hashes: dict[str, str] = {}
    combined = hashlib.sha256()
    for name in EXPECTED_MESSAGES:
        data = (msg_dir / f"{name}.msg").read_bytes()
        text = data.decode("utf-8")
        for fragment in required_fragments.get(name, ()):
            _require(fragment in text, f"{name} missing {fragment!r}")
        for fragment in forbidden_fragments.get(name, ()):
            _require(fragment not in text, f"{name} contains removed {fragment!r}")
        digest = _schema_digest(data)
        hashes[name] = digest
        combined.update(f"{name}:{digest}\n".encode())

    return {
        "contract_version": "v1.0",
        "package_version": EXPECTED_VERSION,
        "message_count": len(EXPECTED_MESSAGES),
        "hash_scope": "normalized ROS declarations; comments and blank lines excluded",
        "message_manifest_sha256": combined.hexdigest(),
        "messages": hashes,
    }


def _verify_installed(report: dict[str, object], root: Path) -> None:
    module = importlib.import_module("patrol_interfaces.msg")
    missing = [name for name in EXPECTED_MESSAGES if not hasattr(module, name)]
    removed = [name for name in REMOVED_MESSAGES if hasattr(module, name)]
    _require(not missing, f"installed messages missing: {missing}")
    _require(not removed, f"removed messages still installed: {removed}")
    source_dir = root / "src" / "patrol_interfaces" / "msg"
    for name in EXPECTED_MESSAGES:
        source_data = (source_dir / f"{name}.msg").read_bytes()
        expected_fields, expected_constants = _source_declarations(source_data)
        installed_type = getattr(module, name)
        actual_fields = installed_type.get_fields_and_field_types()
        _require(actual_fields == expected_fields, f"installed field mismatch: {name}")
        for constant, expected in expected_constants.items():
            _require(
                getattr(installed_type, constant, object()) == expected,
                f"installed constant mismatch: {name}.{constant}",
            )
    _require(isinstance(report.get("messages"), dict), "source hash report missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        report = _source_report(root)
        if args.installed:
            _verify_installed(report, root)
            report["installed_import"] = "PASS"
    except (OSError, ValueError, ET.ParseError, ImportError) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    report["result"] = "PASS"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
