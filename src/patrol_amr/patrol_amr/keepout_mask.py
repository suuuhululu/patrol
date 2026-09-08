"""Validate Keepout polygons and rasterize map-aligned Nav2 masks."""

from dataclasses import dataclass
from pathlib import Path
import math
from typing import Tuple

import yaml


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Polygon:
    polygon_id: str
    points: Tuple[Point, ...]


@dataclass(frozen=True)
class KeepoutLayer:
    layer_id: str
    color_reference: str
    activation_policy: str
    polygons: Tuple[Polygon, ...]


@dataclass(frozen=True)
class KeepoutZones:
    map_id: str
    frame_id: str
    layers: Tuple[KeepoutLayer, ...]

    def layer(self, layer_id: str) -> KeepoutLayer:
        for layer in self.layers:
            if layer.layer_id == layer_id:
                return layer
        raise KeyError(layer_id)


@dataclass(frozen=True)
class MapMetadata:
    image: str
    resolution: float
    origin_x: float
    origin_y: float
    origin_yaw: float
    mode: str
    negate: int
    occupied_thresh: float
    free_thresh: float


def load_keepout_zones(path) -> KeepoutZones:
    payload = _yaml_mapping(path, 'keepout zones')
    frame_id = _nonempty(payload.get('frame_id'), 'frame_id')
    if frame_id != 'map':
        raise ValueError('keepout frame_id must be map')
    map_id = _nonempty(payload.get('map_id'), 'map_id')
    raw_layers = payload.get('layers')
    if not isinstance(raw_layers, list) or not raw_layers:
        raise ValueError('layers must be a non-empty list')

    layers = []
    layer_ids = set()
    polygon_ids = set()
    for raw_layer in raw_layers:
        if not isinstance(raw_layer, dict):
            raise ValueError('every layer must be a mapping')
        layer_id = _nonempty(raw_layer.get('id'), 'layer id')
        if layer_id in layer_ids:
            raise ValueError('layer IDs must be unique')
        layer_ids.add(layer_id)
        raw_polygons = raw_layer.get('polygons')
        if not isinstance(raw_polygons, list) or not raw_polygons:
            raise ValueError('polygons must be a non-empty list')
        polygons = []
        for raw_polygon in raw_polygons:
            if not isinstance(raw_polygon, dict):
                raise ValueError('every polygon must be a mapping')
            polygon_id = _nonempty(raw_polygon.get('id'), 'polygon id')
            if polygon_id in polygon_ids:
                raise ValueError('polygon IDs must be globally unique')
            polygon_ids.add(polygon_id)
            raw_points = raw_polygon.get('points')
            if not isinstance(raw_points, list) or len(raw_points) < 3:
                raise ValueError('polygon must contain at least three points')
            points = tuple(_point(value) for value in raw_points)
            if abs(_signed_area(points)) <= 1e-9:
                raise ValueError('polygon area must be non-zero')
            polygons.append(Polygon(polygon_id, points))
        layers.append(
            KeepoutLayer(
                layer_id,
                _nonempty(raw_layer.get('color_reference'), 'color_reference'),
                _activation_policy(raw_layer),
                tuple(polygons),
            )
        )
    return KeepoutZones(map_id, frame_id, tuple(layers))


def load_map_metadata(path) -> MapMetadata:
    payload = _yaml_mapping(path, 'map metadata')
    origin = payload.get('origin')
    if not isinstance(origin, list) or len(origin) != 3:
        raise ValueError('map origin must contain x, y, yaw')
    metadata = MapMetadata(
        image=_nonempty(payload.get('image'), 'image'),
        resolution=_positive(payload.get('resolution'), 'resolution'),
        origin_x=_finite(origin[0], 'origin x'),
        origin_y=_finite(origin[1], 'origin y'),
        origin_yaw=_finite(origin[2], 'origin yaw'),
        mode=_nonempty(payload.get('mode'), 'mode'),
        negate=payload.get('negate'),
        occupied_thresh=_unit(payload.get('occupied_thresh'), 'occupied_thresh'),
        free_thresh=_unit(payload.get('free_thresh'), 'free_thresh'),
    )
    if metadata.origin_yaw != 0.0:
        raise ValueError('costmap filter mask origin yaw must be zero')
    if metadata.mode != 'trinary' or metadata.negate != 0:
        raise ValueError('keepout mask expects trinary mode with negate 0')
    return metadata


def read_pgm_size(path) -> Tuple[int, int]:
    with Path(path).open('rb') as stream:
        tokens = []
        while len(tokens) < 4:
            line = stream.readline()
            if not line:
                raise ValueError('truncated PGM header')
            line = line.split(b'#', 1)[0]
            tokens.extend(line.split())
    if tokens[0] != b'P5':
        raise ValueError('PGM must use raw P5 encoding')
    try:
        width, height, maximum = map(int, tokens[1:4])
    except ValueError as error:
        raise ValueError('invalid PGM dimensions') from error
    if width <= 0 or height <= 0 or maximum != 255:
        raise ValueError('PGM must have positive dimensions and max value 255')
    return width, height


def rasterize_layer(
    layer: KeepoutLayer,
    metadata: MapMetadata,
    width: int,
    height: int,
) -> bytes:
    if not isinstance(layer, KeepoutLayer):
        raise ValueError('layer must be a KeepoutLayer')
    if not isinstance(metadata, MapMetadata):
        raise ValueError('metadata must be MapMetadata')
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError('width must be a positive int')
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise ValueError('height must be a positive int')

    pixels = bytearray([254]) * (width * height)
    for row in range(height):
        world_y = metadata.origin_y + (height - row - 0.5) * metadata.resolution
        for column in range(width):
            world_x = metadata.origin_x + (column + 0.5) * metadata.resolution
            if any(
                point_in_polygon(Point(world_x, world_y), polygon.points)
                for polygon in layer.polygons
            ):
                pixels[row * width + column] = 0
    return bytes(pixels)


def write_layer_mask(path, layer, metadata, width, height) -> None:
    pixels = rasterize_layer(layer, metadata, width, height)
    path = Path(path)
    path.write_bytes(f'P5\n{width} {height}\n255\n'.encode('ascii') + pixels)


def point_in_polygon(point: Point, polygon: Tuple[Point, ...]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if _on_segment(point, previous, current):
            return True
        crosses = (current.y > point.y) != (previous.y > point.y)
        if crosses:
            boundary_x = (
                (previous.x - current.x)
                * (point.y - current.y)
                / (previous.y - current.y)
                + current.x
            )
            if point.x < boundary_x:
                inside = not inside
        previous = current
    return inside


def _yaml_mapping(path, label):
    try:
        payload = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f'{label} could not be read') from error
    if not isinstance(payload, dict):
        raise ValueError(f'{label} root must be a mapping')
    return payload


def _point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('point must contain x and y')
    return Point(_finite(value[0], 'point x'), _finite(value[1], 'point y'))


def _activation_policy(raw_layer):
    policy = _nonempty(raw_layer.get('activation_policy'), 'activation_policy')
    if policy == 'always':
        if 'control_input' in raw_layer or 'active_value' in raw_layer:
            raise ValueError('always layer must not declare a control input')
        return policy
    if policy == 'control_when_patrol_disallowed':
        if raw_layer.get('control_input') != '/vision/cctv/patrol_allowed':
            raise ValueError('corridor control input must be patrol_allowed')
        if raw_layer.get('active_value') is not False:
            raise ValueError('corridor must activate when patrol_allowed=false')
        return policy
    raise ValueError('unsupported activation_policy')


def _signed_area(points):
    return 0.5 * sum(
        first.x * second.y - second.x * first.y
        for first, second in zip(points, points[1:] + points[:1])
    )


def _on_segment(point, first, second):
    cross = (
        (point.x - first.x) * (second.y - first.y)
        - (point.y - first.y) * (second.x - first.x)
    )
    if abs(cross) > 1e-9:
        return False
    return (
        min(first.x, second.x) - 1e-9 <= point.x <= max(first.x, second.x) + 1e-9
        and min(first.y, second.y) - 1e-9 <= point.y <= max(first.y, second.y) + 1e-9
    )


def _nonempty(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{name} must be a non-empty str')
    return value


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be finite')
    return float(value)


def _positive(value, name):
    value = _finite(value, name)
    if value <= 0.0:
        raise ValueError(f'{name} must be positive')
    return value


def _unit(value, name):
    value = _finite(value, name)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f'{name} must be in [0, 1]')
    return value
