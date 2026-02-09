"""
P&ID Pipeline Prototype — Четыре вкладки для демонстрации руководству:
1. CVAT — валидация Bbox/Полигонов
2. Редактор масок (квадраты) — для нод/оборудования  
3. Редактор полилиний — для труб/линий
4. Валидатор графа — добавление/удаление рёбер
"""

import sys
import json
import math
from pathlib import Path
from collections import deque
from enum import Enum, auto
from typing import Tuple, List, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QTabWidget, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsPathItem,
    QGraphicsEllipseItem, QGraphicsLineItem, QLabel, QFileDialog,
    QSlider, QButtonGroup
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush,
    QPainterPath, QWheelEvent, QMouseEvent, QKeyEvent
)
from PySide6.QtCore import Qt, QUrl, QRectF, QPointF


SQUARE_SIZE = 15
MAX_UNDO_STEPS = 50


# =====================================================================
# GEOMETRY HELPERS: Перпендикулярное соединение узлов
# =====================================================================

def _segments_overlap_1d(a1: float, a2: float, b1: float, b2: float) -> Tuple[bool, float, float]:
    """Проверить перекрытие двух отрезков на одной оси."""
    start = max(min(a1, a2), min(b1, b2))
    end = min(max(a1, a2), max(b1, b2))
    if start <= end:
        return True, start, end
    return False, 0, 0


def _point_to_segment_closest(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> Tuple[float, float, float]:
    """Ближайшая точка на отрезке ab к точке p. Returns: (x, y, distance)"""
    dx, dy = bx - ax, by - ay
    length_sq = dx*dx + dy*dy
    if length_sq < 1e-9:
        return ax, ay, math.sqrt((px-ax)**2 + (py-ay)**2)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return cx, cy, math.sqrt((px - cx)**2 + (py - cy)**2)


def _edge_normal(p1: Tuple[float, float], p2: Tuple[float, float]) -> Tuple[float, float]:
    """Нормаль к ребру (единичный вектор)."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.sqrt(dx*dx + dy*dy)
    if length < 1e-9:
        return (0, 0)
    return (-dy / length, dx / length)


def _polygon_to_edges(polygon: List[float]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Конвертировать плоский список [x1,y1,x2,y2,...] в список рёбер."""
    n = len(polygon) // 2
    edges = []
    for i in range(n):
        x1, y1 = polygon[i * 2], polygon[i * 2 + 1]
        x2, y2 = polygon[((i + 1) % n) * 2], polygon[((i + 1) % n) * 2 + 1]
        edges.append(((x1, y1), (x2, y2)))
    return edges


def _closest_points_between_segments(a1, a2, b1, b2) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """Найти ближайшие точки между двумя отрезками."""
    candidates = []
    for p in [a1, a2]:
        cx, cy, d = _point_to_segment_closest(p[0], p[1], b1[0], b1[1], b2[0], b2[1])
        candidates.append((p, (cx, cy), d))
    for p in [b1, b2]:
        cx, cy, d = _point_to_segment_closest(p[0], p[1], a1[0], a1[1], a2[0], a2[1])
        candidates.append(((cx, cy), p, d))
    return min(candidates, key=lambda x: x[2])


def connect_bbox_bbox(bbox_a: List[float], bbox_b: List[float], required_axis: str = None) -> Tuple[Tuple[float, float], Tuple[float, float], str]:
    """
    Соединить два bbox. Приоритет: строго перпендикулярно (вертикаль/горизонталь).

    Args:
        bbox_a, bbox_b: координаты боксов [x1, y1, x2, y2]
        required_axis: 'vertical'/'horizontal'/None — если задано, искать только эту ось

    Логика приоритетов:
    1. Перпендикуляр из центра A попадает на стенку B
    2. Перпендикуляр из центра B попадает на стенку A
    3. Перпендикуляр через overlap (не через центр)
    4. Наименее диагональное соединение стенка-стенка

    Returns: (point_a, point_b, connection_type)
    """
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
    bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2

    candidates = []  # [(point_a, point_b, distance, priority, connection_type)]

    # === ПРИОРИТЕТ 1: Перпендикуляр из центра A ===

    # Вертикаль x = acx: попадает на верхнюю/нижнюю стенку B?
    if (required_axis is None or required_axis == 'vertical') and bx1 <= acx <= bx2:
        if acy < by1:  # A выше B
            pa = (acx, ay2)  # нижняя стенка A
            pb = (acx, by1)  # верхняя стенка B
            dist = by1 - ay2
            if dist >= 0:
                candidates.append((pa, pb, dist, 1, "vertical_center_a"))
        elif acy > by2:  # A ниже B
            pa = (acx, ay1)  # верхняя стенка A
            pb = (acx, by2)  # нижняя стенка B
            dist = ay1 - by2
            if dist >= 0:
                candidates.append((pa, pb, dist, 1, "vertical_center_a"))

    # Горизонталь y = acy: попадает на левую/правую стенку B?
    if (required_axis is None or required_axis == 'horizontal') and by1 <= acy <= by2:
        if acx < bx1:  # A левее B
            pa = (ax2, acy)  # правая стенка A
            pb = (bx1, acy)  # левая стенка B
            dist = bx1 - ax2
            if dist >= 0:
                candidates.append((pa, pb, dist, 1, "horizontal_center_a"))
        elif acx > bx2:  # A правее B
            pa = (ax1, acy)  # левая стенка A
            pb = (bx2, acy)  # правая стенка B
            dist = ax1 - bx2
            if dist >= 0:
                candidates.append((pa, pb, dist, 1, "horizontal_center_a"))

    # === ПРИОРИТЕТ 2: Перпендикуляр из центра B ===

    # Вертикаль x = bcx: попадает на верхнюю/нижнюю стенку A?
    if (required_axis is None or required_axis == 'vertical') and ax1 <= bcx <= ax2:
        if bcy < ay1:  # B выше A
            pb = (bcx, by2)  # нижняя стенка B
            pa = (bcx, ay1)  # верхняя стенка A
            dist = ay1 - by2
            if dist >= 0:
                candidates.append((pa, pb, dist, 2, "vertical_center_b"))
        elif bcy > ay2:  # B ниже A
            pb = (bcx, by1)  # верхняя стенка B
            pa = (bcx, ay2)  # нижняя стенка A
            dist = by1 - ay2
            if dist >= 0:
                candidates.append((pa, pb, dist, 2, "vertical_center_b"))

    # Горизонталь y = bcy: попадает на левую/правую стенку A?
    if (required_axis is None or required_axis == 'horizontal') and ay1 <= bcy <= ay2:
        if bcx < ax1:  # B левее A
            pb = (bx2, bcy)  # правая стенка B
            pa = (ax1, bcy)  # левая стенка A
            dist = ax1 - bx2
            if dist >= 0:
                candidates.append((pa, pb, dist, 2, "horizontal_center_b"))
        elif bcx > ax2:  # B правее A
            pb = (bx1, bcy)  # левая стенка B
            pa = (ax2, bcy)  # правая стенка A
            dist = bx2 - ax1
            if dist >= 0:
                candidates.append((pa, pb, dist, 2, "horizontal_center_b"))

    # === ПРИОРИТЕТ 3: Перпендикуляр через overlap (не через центр) ===

    overlap_x, ox_start, ox_end = _segments_overlap_1d(ax1, ax2, bx1, bx2)
    overlap_y, oy_start, oy_end = _segments_overlap_1d(ay1, ay2, by1, by2)

    if (required_axis is None or required_axis == 'vertical') and overlap_x and not overlap_y:
        # Вертикальная линия через середину overlap
        x = (ox_start + ox_end) / 2
        if acy < bcy:
            pa = (x, ay2)
            pb = (x, by1)
            dist = by1 - ay2
        else:
            pa = (x, ay1)
            pb = (x, by2)
            dist = ay1 - by2
        if dist >= 0:
            candidates.append((pa, pb, abs(dist), 3, "vertical_overlap"))

    if (required_axis is None or required_axis == 'horizontal') and overlap_y and not overlap_x:
        # Горизонтальная линия через середину overlap
        y = (oy_start + oy_end) / 2
        if acx < bcx:
            pa = (ax2, y)
            pb = (bx1, y)
            dist = bx1 - ax2
        else:
            pa = (ax1, y)
            pb = (bx2, y)
            dist = ax1 - bx2
        if dist >= 0:
            candidates.append((pa, pb, abs(dist), 3, "horizontal_overlap"))

    # Если overlap по обеим осям — боксы пересекаются
    if overlap_x and overlap_y:
        return ((acx, acy), (bcx, bcy), "overlapping")

    # === Выбираем лучшего кандидата из приоритетов 1-3 ===
    if candidates:
        # Сортируем: сначала по приоритету, потом по расстоянию
        candidates.sort(key=lambda c: (c[3], c[2]))
        best = candidates[0]
        return (best[0], best[1], best[4])

    # === ПРИОРИТЕТ 4: Наименее диагональное стенка-стенка ===
    sides_a = [
        ((ax1, ay1), (ax2, ay1), 'top'),     # верх
        ((ax1, ay2), (ax2, ay2), 'bottom'),  # низ
        ((ax1, ay1), (ax1, ay2), 'left'),    # лево
        ((ax2, ay1), (ax2, ay2), 'right'),   # право
    ]
    sides_b = [
        ((bx1, by1), (bx2, by1), 'top'),
        ((bx1, by2), (bx2, by2), 'bottom'),
        ((bx1, by1), (bx1, by2), 'left'),
        ((bx2, by1), (bx2, by2), 'right'),
    ]

    best_score = -1.0
    best_dist = float('inf')
    best_pa, best_pb = (acx, acy), (bcx, bcy)
    best_type = "diagonal"

    for (a1, a2, a_side) in sides_a:
        for (b1, b2, b_side) in sides_b:
            pa, pb, dist = _closest_points_between_segments(a1, a2, b1, b2)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            score, axis = global_axis_perpendicularity(dx, dy)

            # Если задана required_axis, учитываем только совпадающие
            if required_axis is not None and axis != required_axis:
                continue

            # Приоритет: перпендикулярность, при равной — меньшее расстояние
            if score > best_score or (abs(score - best_score) < 1e-9 and dist < best_dist):
                best_score = score
                best_pa, best_pb = pa, pb
                best_dist = dist
                best_type = f"diagonal_{axis}"

    return (best_pa, best_pb, best_type)


def connect_bbox_polygon(bbox: List[float], polygon: List[float], required_axis: str = None) -> Tuple[Tuple[float, float], Tuple[float, float], dict]:
    """
    Соединить bbox с полигоном. Приоритет: глобальная перпендикулярность (к осям).

    Args:
        bbox: координаты бокса [x1, y1, x2, y2]
        polygon: плоский список координат полигона [x1,y1,x2,y2,...]
        required_axis: 'vertical'/'horizontal'/None — если задано, искать только эту ось

    Логика приоритетов:
    1. Перпендикуляр из центра bbox попадает на ребро полигона
    2. Перпендикуляр из центра полигона попадает на стенку bbox
    3. Наименее диагональное соединение стенка-ребро

    Returns: (point_on_bbox, point_on_polygon, info)
    """
    bx1, by1, bx2, by2 = bbox
    bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2

    edges = _polygon_to_edges(polygon)
    n_verts = len(polygon) // 2
    poly_cx = sum(polygon[::2]) / n_verts
    poly_cy = sum(polygon[1::2]) / n_verts

    candidates = []  # [(bbox_point, poly_point, distance, priority, info)]

    # === ПРИОРИТЕТ 1: Перпендикуляр из центра bbox ===

    # Вертикаль x = bcx
    if required_axis is None or required_axis == 'vertical':
        for p1, p2 in edges:
            if min(p1[0], p2[0]) <= bcx <= max(p1[0], p2[0]):
                if abs(p2[0] - p1[0]) > 1e-9:
                    t = (bcx - p1[0]) / (p2[0] - p1[0])
                    if 0 <= t <= 1:
                        py = p1[1] + t * (p2[1] - p1[1])
                        poly_point = (bcx, py)

                        if py < by1:
                            bbox_point = (bcx, by1)
                            dist = by1 - py
                        elif py > by2:
                            bbox_point = (bcx, by2)
                            dist = py - by2
                        else:
                            continue

                        if dist >= 0:
                            candidates.append((bbox_point, poly_point, dist, 1,
                                              {'perpendicularity': 1.0, 'axis': 'vertical'}))

    # Горизонталь y = bcy
    if required_axis is None or required_axis == 'horizontal':
        for p1, p2 in edges:
            if min(p1[1], p2[1]) <= bcy <= max(p1[1], p2[1]):
                if abs(p2[1] - p1[1]) > 1e-9:
                    t = (bcy - p1[1]) / (p2[1] - p1[1])
                    if 0 <= t <= 1:
                        px = p1[0] + t * (p2[0] - p1[0])
                        poly_point = (px, bcy)

                        if px < bx1:
                            bbox_point = (bx1, bcy)
                            dist = bx1 - px
                        elif px > bx2:
                            bbox_point = (bx2, bcy)
                            dist = px - bx2
                        else:
                            continue

                        if dist >= 0:
                            candidates.append((bbox_point, poly_point, dist, 1,
                                              {'perpendicularity': 1.0, 'axis': 'horizontal'}))

    # === ПРИОРИТЕТ 2: Перпендикуляр из центра полигона ===

    # Вертикаль x = poly_cx попадает на bbox?
    if (required_axis is None or required_axis == 'vertical') and bx1 <= poly_cx <= bx2:
        if poly_cy < by1:
            poly_point = (poly_cx, poly_cy)
            bbox_point = (poly_cx, by1)
            dist = by1 - poly_cy
            candidates.append((bbox_point, poly_point, dist, 2,
                              {'perpendicularity': 1.0, 'axis': 'vertical'}))
        elif poly_cy > by2:
            poly_point = (poly_cx, poly_cy)
            bbox_point = (poly_cx, by2)
            dist = poly_cy - by2
            candidates.append((bbox_point, poly_point, dist, 2,
                              {'perpendicularity': 1.0, 'axis': 'vertical'}))

    # Горизонталь y = poly_cy попадает на bbox?
    if (required_axis is None or required_axis == 'horizontal') and by1 <= poly_cy <= by2:
        if poly_cx < bx1:
            poly_point = (poly_cx, poly_cy)
            bbox_point = (bx1, poly_cy)
            dist = bx1 - poly_cx
            candidates.append((bbox_point, poly_point, dist, 2,
                              {'perpendicularity': 1.0, 'axis': 'horizontal'}))
        elif poly_cx > bx2:
            poly_point = (poly_cx, poly_cy)
            bbox_point = (bx2, poly_cy)
            dist = poly_cx - bx2
            candidates.append((bbox_point, poly_point, dist, 2,
                              {'perpendicularity': 1.0, 'axis': 'horizontal'}))

    # === Выбираем лучшего кандидата из приоритетов 1-2 ===
    if candidates:
        candidates.sort(key=lambda c: (c[3], c[2]))
        best = candidates[0]
        return (best[0], best[1], best[4])

    # === ПРИОРИТЕТ 3: Наименее диагональное стенка-ребро ===
    sides_bbox = [
        ((bx1, by1), (bx2, by1)),  # верх
        ((bx1, by2), (bx2, by2)),  # низ
        ((bx1, by1), (bx1, by2)),  # лево
        ((bx2, by1), (bx2, by2)),  # право
    ]

    best_score = -1.0
    best_result = None
    best_dist = float('inf')

    for b1, b2 in sides_bbox:
        for p1, p2 in edges:
            pa, pb, dist = _closest_points_between_segments(b1, b2, p1, p2)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            score, axis = global_axis_perpendicularity(dx, dy)

            # Если задана required_axis, учитываем только совпадающие
            if required_axis is not None and axis != required_axis:
                continue

            if score > best_score or (abs(score - best_score) < 1e-9 and dist < best_dist):
                best_score = score
                best_dist = dist
                best_result = {
                    'bbox_point': pa,
                    'poly_point': pb,
                    'perpendicularity': score,
                    'axis': axis
                }

    if best_result:
        return (best_result['bbox_point'], best_result['poly_point'], best_result)

    # Fallback
    return ((bcx, bcy), (poly_cx, poly_cy), {'fallback': True})


def _closest_point_on_bbox_to_direction(bbox: List[float], from_point: Tuple[float, float],
                                         direction: Tuple[float, float]) -> Tuple[float, float]:
    """Найти точку на bbox на луче из from_point в направлении direction."""
    x1, y1, x2, y2 = bbox
    dx, dy = direction
    length = math.sqrt(dx*dx + dy*dy)
    if length < 1e-9:
        return ((x1+x2)/2, (y1+y2)/2)
    dx, dy = dx / length, dy / length

    sides = [((x1, y1), (x1, y2)), ((x2, y1), (x2, y2)),
             ((x1, y1), (x2, y1)), ((x1, y2), (x2, y2))]

    best_t = float('inf')
    best_point = ((x1+x2)/2, (y1+y2)/2)

    for (sx1, sy1), (sx2, sy2) in sides:
        sdx, sdy = sx2 - sx1, sy2 - sy1
        denom = dx * sdy - dy * sdx
        if abs(denom) < 1e-9:
            continue
        t = ((sx1 - from_point[0]) * sdy - (sy1 - from_point[1]) * sdx) / denom
        s = ((sx1 - from_point[0]) * dy - (sy1 - from_point[1]) * dx) / denom
        if t > 0 and 0 <= s <= 1 and t < best_t:
            best_t = t
            best_point = (from_point[0] + t * dx, from_point[1] + t * dy)

    return best_point


def connect_polygon_polygon(polygon_a: List[float], polygon_b: List[float], required_axis: str = None) -> Tuple[Tuple[float, float], Tuple[float, float], dict]:
    """
    Соединить два полигона. Приоритет: глобальная перпендикулярность (к осям).

    Args:
        polygon_a, polygon_b: плоские списки координат [x1,y1,x2,y2,...]
        required_axis: 'vertical'/'horizontal'/None — если задано, искать только эту ось

    Логика приоритетов:
    1. Перпендикуляр из центра A попадает на ребро B
    2. Перпендикуляр из центра B попадает на ребро A
    3. Наименее диагональное соединение ребро-ребро

    Returns: (point_a, point_b, info)
    """
    edges_a = _polygon_to_edges(polygon_a)
    edges_b = _polygon_to_edges(polygon_b)

    n_a = len(polygon_a) // 2
    n_b = len(polygon_b) // 2
    ca_x = sum(polygon_a[::2]) / n_a
    ca_y = sum(polygon_a[1::2]) / n_a
    cb_x = sum(polygon_b[::2]) / n_b
    cb_y = sum(polygon_b[1::2]) / n_b

    candidates = []  # [(point_a, point_b, distance, priority, info)]

    # === ПРИОРИТЕТ 1: Перпендикуляр из центра A ===

    # Вертикаль x = ca_x
    if required_axis is None or required_axis == 'vertical':
        for p1, p2 in edges_b:
            if min(p1[0], p2[0]) <= ca_x <= max(p1[0], p2[0]):
                if abs(p2[0] - p1[0]) > 1e-9:
                    t = (ca_x - p1[0]) / (p2[0] - p1[0])
                    if 0 <= t <= 1:
                        py = p1[1] + t * (p2[1] - p1[1])
                        point_b = (ca_x, py)
                        point_a = (ca_x, ca_y)
                        dist = abs(py - ca_y)
                        candidates.append((point_a, point_b, dist, 1,
                                          {'perpendicularity': 1.0, 'axis': 'vertical'}))

    # Горизонталь y = ca_y
    if required_axis is None or required_axis == 'horizontal':
        for p1, p2 in edges_b:
            if min(p1[1], p2[1]) <= ca_y <= max(p1[1], p2[1]):
                if abs(p2[1] - p1[1]) > 1e-9:
                    t = (ca_y - p1[1]) / (p2[1] - p1[1])
                    if 0 <= t <= 1:
                        px = p1[0] + t * (p2[0] - p1[0])
                        point_b = (px, ca_y)
                        point_a = (ca_x, ca_y)
                        dist = abs(px - ca_x)
                        candidates.append((point_a, point_b, dist, 1,
                                          {'perpendicularity': 1.0, 'axis': 'horizontal'}))

    # === ПРИОРИТЕТ 2: Перпендикуляр из центра B ===

    # Вертикаль x = cb_x
    if required_axis is None or required_axis == 'vertical':
        for p1, p2 in edges_a:
            if min(p1[0], p2[0]) <= cb_x <= max(p1[0], p2[0]):
                if abs(p2[0] - p1[0]) > 1e-9:
                    t = (cb_x - p1[0]) / (p2[0] - p1[0])
                    if 0 <= t <= 1:
                        py = p1[1] + t * (p2[1] - p1[1])
                        point_a = (cb_x, py)
                        point_b = (cb_x, cb_y)
                        dist = abs(py - cb_y)
                        candidates.append((point_a, point_b, dist, 2,
                                          {'perpendicularity': 1.0, 'axis': 'vertical'}))

    # Горизонталь y = cb_y
    if required_axis is None or required_axis == 'horizontal':
        for p1, p2 in edges_a:
            if min(p1[1], p2[1]) <= cb_y <= max(p1[1], p2[1]):
                if abs(p2[1] - p1[1]) > 1e-9:
                    t = (cb_y - p1[1]) / (p2[1] - p1[1])
                    if 0 <= t <= 1:
                        px = p1[0] + t * (p2[0] - p1[0])
                        point_a = (px, cb_y)
                        point_b = (cb_x, cb_y)
                        dist = abs(px - cb_x)
                        candidates.append((point_a, point_b, dist, 2,
                                          {'perpendicularity': 1.0, 'axis': 'horizontal'}))

    # === Выбираем лучшего кандидата из приоритетов 1-2 ===
    if candidates:
        candidates.sort(key=lambda c: (c[3], c[2]))
        best = candidates[0]
        return (best[0], best[1], best[4])

    # === ПРИОРИТЕТ 3: Наименее диагональное ребро-ребро ===
    best_score = -1.0
    best_result = None
    best_dist = float('inf')

    for a1, a2 in edges_a:
        for b1, b2 in edges_b:
            pa, pb, dist = _closest_points_between_segments(a1, a2, b1, b2)
            if dist < 1e-9:
                continue

            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            score, axis = global_axis_perpendicularity(dx, dy)

            # Если задана required_axis, учитываем только совпадающие
            if required_axis is not None and axis != required_axis:
                continue

            if score > best_score or (abs(score - best_score) < 1e-9 and dist < best_dist):
                best_score = score
                best_dist = dist
                best_result = {
                    'point_a': pa,
                    'point_b': pb,
                    'perpendicularity': score,
                    'axis': axis
                }

    if best_result:
        return (best_result['point_a'], best_result['point_b'], best_result)

    # Fallback
    return ((ca_x, ca_y), (cb_x, cb_y), {'fallback': True})


def connect_point_bbox(point: Tuple[float, float], bbox: List[float], required_axis: str = None) -> Tuple[Tuple[float, float], Tuple[float, float], str]:
    """
    Соединить точку (коннектор) с bbox.
    Приоритет: строгий перпендикуляр (вертикаль/горизонталь) от точки к стенке.

    Args:
        point: координаты точки (x, y)
        bbox: координаты бокса [x1, y1, x2, y2]
        required_axis: 'vertical'/'horizontal'/None — если задано, искать только эту ось

    Логика приоритетов:
    1. Вертикаль x = px попадает на горизонтальную стенку bbox
    2. Горизонталь y = py попадает на вертикальную стенку bbox
    3. Наименее диагональное соединение

    Returns: (point, point_on_bbox, connection_type)
    """
    px, py = point
    x1, y1, x2, y2 = bbox

    candidates = []  # [(point, bbox_point, distance, priority, connection_type)]

    # === ПРИОРИТЕТ 1: Вертикаль x = px ===
    if (required_axis is None or required_axis == 'vertical') and x1 <= px <= x2:
        if py < y1:
            bbox_point = (px, y1)
            dist = y1 - py
            candidates.append((point, bbox_point, dist, 1, "vertical_to_top"))
        elif py > y2:
            bbox_point = (px, y2)
            dist = py - y2
            candidates.append((point, bbox_point, dist, 1, "vertical_to_bottom"))

    # === ПРИОРИТЕТ 2: Горизонталь y = py ===
    if (required_axis is None or required_axis == 'horizontal') and y1 <= py <= y2:
        if px < x1:
            bbox_point = (x1, py)
            dist = x1 - px
            candidates.append((point, bbox_point, dist, 2, "horizontal_to_left"))
        elif px > x2:
            bbox_point = (x2, py)
            dist = px - x2
            candidates.append((point, bbox_point, dist, 2, "horizontal_to_right"))

    # === Выбираем лучшего кандидата из приоритетов 1-2 ===
    if candidates:
        candidates.sort(key=lambda c: (c[3], c[2]))
        best = candidates[0]
        return (best[0], best[1], best[4])

    # === ПРИОРИТЕТ 3: Наименее диагональное ===
    sides = [
        ((x1, y1), (x2, y1), 'top'),
        ((x1, y2), (x2, y2), 'bottom'),
        ((x1, y1), (x1, y2), 'left'),
        ((x2, y1), (x2, y2), 'right'),
    ]

    best_score = -1.0
    best_dist = float('inf')
    best_point = ((x1 + x2) / 2, (y1 + y2) / 2)
    best_type = "diagonal"

    for p1, p2, side_name in sides:
        cx, cy, dist = _point_to_segment_closest(px, py, p1[0], p1[1], p2[0], p2[1])
        dx, dy = cx - px, cy - py
        score, axis = global_axis_perpendicularity(dx, dy)

        # Если задана required_axis, учитываем только совпадающие
        if required_axis is not None and axis != required_axis:
            continue

        if score > best_score or (abs(score - best_score) < 1e-9 and dist < best_dist):
            best_score = score
            best_dist = dist
            best_point = (cx, cy)
            best_type = f"diagonal_{axis}_to_{side_name}"

    return (point, best_point, best_type)


def connect_point_polygon(point: Tuple[float, float], polygon: List[float], required_axis: str = None) -> Tuple[Tuple[float, float], Tuple[float, float], dict]:
    """
    Соединить точку (коннектор) с полигоном.
    Приоритет: строгий перпендикуляр (вертикаль/горизонталь) от точки к ребру.

    Args:
        point: координаты точки (x, y)
        polygon: плоский список координат [x1,y1,x2,y2,...]
        required_axis: 'vertical'/'horizontal'/None — если задано, искать только эту ось

    Логика приоритетов:
    1. Вертикаль x = px пересекает ребро полигона
    2. Горизонталь y = py пересекает ребро полигона
    3. Наименее диагональное соединение

    Returns: (point, point_on_polygon, info)
    """
    px, py = point
    n = len(polygon) // 2
    edges = _polygon_to_edges(polygon)

    candidates = []  # [(point, poly_point, distance, priority, info)]

    # === ПРИОРИТЕТ 1: Вертикаль x = px ===
    if required_axis is None or required_axis == 'vertical':
        for i, (p1, p2) in enumerate(edges):
            if min(p1[0], p2[0]) <= px <= max(p1[0], p2[0]):
                if abs(p2[0] - p1[0]) > 1e-9:
                    t = (px - p1[0]) / (p2[0] - p1[0])
                    if 0 <= t <= 1:
                        poly_y = p1[1] + t * (p2[1] - p1[1])
                        poly_point = (px, poly_y)
                        dist = abs(poly_y - py)
                        candidates.append((point, poly_point, dist, 1,
                                          {'perpendicularity': 1.0, 'axis': 'vertical', 'edge_idx': i}))

    # === ПРИОРИТЕТ 2: Горизонталь y = py ===
    if required_axis is None or required_axis == 'horizontal':
        for i, (p1, p2) in enumerate(edges):
            if min(p1[1], p2[1]) <= py <= max(p1[1], p2[1]):
                if abs(p2[1] - p1[1]) > 1e-9:
                    t = (py - p1[1]) / (p2[1] - p1[1])
                    if 0 <= t <= 1:
                        poly_x = p1[0] + t * (p2[0] - p1[0])
                        poly_point = (poly_x, py)
                        dist = abs(poly_x - px)
                        candidates.append((point, poly_point, dist, 2,
                                          {'perpendicularity': 1.0, 'axis': 'horizontal', 'edge_idx': i}))

    # === Выбираем лучшего кандидата из приоритетов 1-2 ===
    if candidates:
        candidates.sort(key=lambda c: (c[3], c[2]))
        best = candidates[0]
        return (best[0], best[1], best[4])

    # === ПРИОРИТЕТ 3: Наименее диагональное ===
    best_score = -1.0
    best_dist = float('inf')
    best_result = None

    for i, (p1, p2) in enumerate(edges):
        cx, cy, dist = _point_to_segment_closest(px, py, p1[0], p1[1], p2[0], p2[1])
        if dist < 1e-9:
            continue

        dx, dy = cx - px, cy - py
        score, axis = global_axis_perpendicularity(dx, dy)

        # Если задана required_axis, учитываем только совпадающие
        if required_axis is not None and axis != required_axis:
            continue

        if score > best_score or (abs(score - best_score) < 1e-9 and dist < best_dist):
            best_score = score
            best_dist = dist
            best_result = {
                'poly_point': (cx, cy),
                'edge_idx': i,
                'perpendicularity': score,
                'axis': axis,
            }

    if best_result:
        return (point, best_result['poly_point'], best_result)

    # Fallback: центроид полигона
    poly_cx = sum(polygon[::2]) / n
    poly_cy = sum(polygon[1::2]) / n
    return (point, (poly_cx, poly_cy), {'fallback': True})


# =====================================================================
# EDGE PERPENDICULARITY ANALYSIS
# =====================================================================

# Порог "хорошей" перпендикулярности: 1° от оси
# score = 1 - sin(угол), для 1°: 1 - sin(1°) ≈ 0.983
PERPENDICULARITY_THRESHOLD = 1.0


def global_axis_perpendicularity(dx: float, dy: float) -> Tuple[float, str]:
    """
    Вычислить глобальную перпендикулярность — близость к осям координат.

    Args:
        dx, dy: направление (не обязательно нормализованное)

    Returns:
        (score, axis): score 0-1, axis = 'horizontal'/'vertical'/'diagonal'
    """
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return 1.0, 'point'

    dx_norm = abs(dx / length)
    dy_norm = abs(dy / length)

    # Близость к горизонтали: |dy| → 0
    horiz_score = 1.0 - dy_norm
    # Близость к вертикали: |dx| → 0
    vert_score = 1.0 - dx_norm

    if horiz_score >= vert_score:
        return horiz_score, 'horizontal'
    else:
        return vert_score, 'vertical'


def compute_edge_perpendicularity(
    edge_start: Tuple[float, float],
    edge_end: Tuple[float, float],
    source_geometry: dict,
    target_geometry: dict
) -> dict:
    """
    Вычислить перпендикулярность ребра — близость к глобальным осям (вертикаль/горизонталь).

    Args:
        edge_start: (x, y) начало ребра
        edge_end: (x, y) конец ребра
        source_geometry: {'type': 'bbox'/'polygon'/'point', 'data': ...} (не используется в новой логике)
        target_geometry: аналогично (не используется в новой логике)

    Returns:
        {
            'score': float 0-1 (близость к оси),
            'axis': 'horizontal'/'vertical'/'point',
            'angle': float (градусы отклонения от оси),
            'is_good': bool (score > threshold)
        }
    """
    sx, sy = edge_start
    tx, ty = edge_end

    dx, dy = tx - sx, ty - sy

    score, axis = global_axis_perpendicularity(dx, dy)

    # Угол отклонения от идеальной оси
    # score = 1 - |sin(angle)|, поэтому angle = arcsin(1 - score)
    angle = math.degrees(math.asin(min(1.0, 1.0 - score)))

    return {
        'score': score,
        'axis': axis,
        'angle': angle,
        'is_good': score >= PERPENDICULARITY_THRESHOLD,
        # Для обратной совместимости
        'source_perp': score,
        'target_perp': score,
        'source_angle': angle,
        'target_angle': angle,
    }


def _compute_perp_to_geometry(px: float, py: float, dx: float, dy: float,
                               geometry: dict) -> float:
    """
    Вычислить перпендикулярность направления — теперь просто глобальная метрика.
    (Оставлено для обратной совместимости, но геометрия не используется)
    """
    score, _ = global_axis_perpendicularity(dx, dy)
    return score


def _perp_to_bbox(px: float, py: float, dx: float, dy: float, bbox: List[float]) -> float:
    """Перпендикулярность — глобальная метрика (bbox не используется)."""
    score, _ = global_axis_perpendicularity(dx, dy)
    return score


def _perp_to_polygon(px: float, py: float, dx: float, dy: float, polygon: List[float]) -> float:
    """Перпендикулярность — глобальная метрика (polygon не используется)."""
    score, _ = global_axis_perpendicularity(dx, dy)
    return score


# =====================================================================
# TAB 2: MASK EDITOR (SQUARES) — для нод/оборудования
# =====================================================================

class SquareMaskEditor(QGraphicsView):
    """Редактор масок с квадратами (из combined_prototype.py)"""

    def __init__(self):
        super().__init__()

        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # Images
        self.original_image = None
        self.skeleton_image = None
        self.mask1_image = None
        self.mask2_image = None
        self.img_width = 0
        self.img_height = 0

        # Current class (1 = white, 2 = red)
        self.current_class = 1

        # Squares overlay
        self.squares_white = []
        self.squares_red = []

        # Undo
        self.undo_stack = deque(maxlen=MAX_UNDO_STEPS)

        # Setup view
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

        self.ctrl_pressed = False
        self.status_callback = None

        # Placeholder
        self.show_placeholder()

    def show_placeholder(self):
        self.scene.clear()
        text = self.scene.addText("Загрузите изображение и маски")
        text.setDefaultTextColor(QColor(150, 150, 150))

    def load_images(self, original_path: str, mask1_path: str, mask2_path: str = "", skeleton_path: str = ""):
        """Load images"""
        self.original_image = QImage(original_path)
        if self.original_image.isNull():
            return False

        self.img_width = self.original_image.width()
        self.img_height = self.original_image.height()

        # Skeleton — GREEN (optional, displayed under masks)
        if skeleton_path and Path(skeleton_path).exists():
            skeleton_raw = QImage(skeleton_path)
            self.skeleton_image = self._make_mask_rgba(skeleton_raw, QColor(0, 255, 0))
        else:
            self.skeleton_image = None

        # Mask1 — WHITE
        mask1_raw = QImage(mask1_path)
        if mask1_raw.isNull():
            return False
        self.mask1_image = self._make_mask_rgba(mask1_raw, QColor(255, 255, 255))

        # Mask2 — RED
        if mask2_path and Path(mask2_path).exists():
            mask2_raw = QImage(mask2_path)
            self.mask2_image = self._make_mask_rgba(mask2_raw, QColor(255, 0, 0))
        else:
            self.mask2_image = QImage(self.img_width, self.img_height, QImage.Format.Format_ARGB32)
            self.mask2_image.fill(QColor(0, 0, 0, 0))

        self.setup_scene()
        return True

    def _make_mask_rgba(self, img, color: QColor):
        """Convert binary mask to RGBA: black→transparent, white→color"""
        result = QImage(img.width(), img.height(), QImage.Format.Format_ARGB32)
        result.fill(QColor(0, 0, 0, 0))

        src = img.convertToFormat(QImage.Format.Format_ARGB32)
        src_ptr = src.bits()
        dst_ptr = result.bits()
        bpl = src.bytesPerLine()

        r, g, b = color.red(), color.green(), color.blue()

        for y in range(img.height()):
            for x in range(img.width()):
                idx = y * bpl + x * 4
                brightness = (src_ptr[idx] + src_ptr[idx + 1] + src_ptr[idx + 2]) // 3

                if brightness >= 128:
                    dst_ptr[idx] = b
                    dst_ptr[idx + 1] = g
                    dst_ptr[idx + 2] = r
                    dst_ptr[idx + 3] = 255

        return result

    def setup_scene(self):
        self.scene.clear()
        self.squares_white.clear()
        self.squares_red.clear()
        self.undo_stack.clear()

        # Z=0: Original (darkened)
        darkened = self.original_image.copy().convertToFormat(QImage.Format.Format_ARGB32)
        painter = QPainter(darkened)
        painter.fillRect(darkened.rect(), QColor(0, 0, 0, 153))
        painter.end()

        item = QGraphicsPixmapItem(QPixmap.fromImage(darkened))
        item.setZValue(0)
        self.scene.addItem(item)

        # Z=1: Skeleton (green, 50% opacity) — under masks
        if self.skeleton_image:
            self.skeleton_item = QGraphicsPixmapItem(QPixmap.fromImage(self.skeleton_image))
            self.skeleton_item.setZValue(1)
            self.skeleton_item.setOpacity(0.5)
            self.scene.addItem(self.skeleton_item)

        # Z=2: Mask 1 (white, 50% opacity)
        self.mask1_item = QGraphicsPixmapItem(QPixmap.fromImage(self.mask1_image))
        self.mask1_item.setZValue(2)
        self.mask1_item.setOpacity(0.5)
        self.scene.addItem(self.mask1_item)

        # Z=3: Mask 2 (red, 50% opacity)
        self.mask2_item = QGraphicsPixmapItem(QPixmap.fromImage(self.mask2_image))
        self.mask2_item.setZValue(3)
        self.mask2_item.setOpacity(0.5)
        self.scene.addItem(self.mask2_item)

        self.setSceneRect(QRectF(0, 0, self.img_width, self.img_height))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def update_mask1_display(self):
        self.mask1_item.setPixmap(QPixmap.fromImage(self.mask1_image))

    def update_mask2_display(self):
        self.mask2_item.setPixmap(QPixmap.fromImage(self.mask2_image))

    def add_square(self, x, y):
        half = SQUARE_SIZE // 2
        if self.current_class == 1:
            color = QColor(255, 255, 255, 127)  # 50% opacity
            squares_list = self.squares_white
        else:
            color = QColor(255, 0, 0, 127)  # 50% opacity
            squares_list = self.squares_red

        rect = QGraphicsRectItem(x - half, y - half, SQUARE_SIZE, SQUARE_SIZE)
        rect.setBrush(QBrush(color))
        rect.setPen(QPen(Qt.PenStyle.NoPen))
        rect.setZValue(4)  # Above masks and skeleton
        self.scene.addItem(rect)
        squares_list.append(rect)
        self.undo_stack.append(('add_square', self.current_class, rect))
        self.update_status(f"Квадрат ({x}, {y})")

    def flood_fill_delete(self, x, y, threshold=128):
        # First check squares
        for squares_list, cls in [(self.squares_white, 1), (self.squares_red, 2)]:
            for rect in squares_list:
                if rect.rect().contains(x, y):
                    self.scene.removeItem(rect)
                    squares_list.remove(rect)
                    self.undo_stack.append(('remove_square', cls, rect))
                    self.update_status("Квадрат удалён")
                    return True

        # Then check mask
        mask = self.mask1_image if self.current_class == 1 else self.mask2_image

        if x < 0 or x >= self.img_width or y < 0 or y >= self.img_height:
            return False

        pixel = mask.pixelColor(x, y)
        if pixel.alpha() < threshold:
            self.update_status("Пустая область")
            return False

        self.undo_stack.append(('flood_fill', self.current_class, mask.copy()))

        visited = set()
        queue = [(x, y)]
        ptr = mask.bits()
        bpl = mask.bytesPerLine()

        while queue:
            cx, cy = queue.pop()
            if (cx, cy) in visited or cx < 0 or cx >= self.img_width or cy < 0 or cy >= self.img_height:
                continue

            idx = cy * bpl + cx * 4
            if ptr[idx + 3] < threshold:
                continue

            visited.add((cx, cy))
            ptr[idx] = ptr[idx + 1] = ptr[idx + 2] = ptr[idx + 3] = 0
            queue.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

        if self.current_class == 1:
            self.update_mask1_display()
        else:
            self.update_mask2_display()

        self.update_status(f"Удалено {len(visited)} px")
        return True

    def undo(self):
        if not self.undo_stack:
            self.update_status("Нечего отменять")
            return

        action = self.undo_stack.pop()
        if action[0] == 'add_square':
            _, cls, rect = action
            self.scene.removeItem(rect)
            (self.squares_white if cls == 1 else self.squares_red).remove(rect)
            self.update_status("Undo: квадрат удалён")
        elif action[0] == 'remove_square':
            _, cls, rect = action
            self.scene.addItem(rect)
            (self.squares_white if cls == 1 else self.squares_red).append(rect)
            self.update_status("Undo: квадрат восстановлен")
        elif action[0] == 'flood_fill':
            _, cls, old_mask = action
            if cls == 1:
                self.mask1_image = old_mask
                self.update_mask1_display()
            else:
                self.mask2_image = old_mask
                self.update_mask2_display()
            self.update_status("Undo: маска восстановлена")

    def save_masks(self):
        """Save masks with squares merged"""
        if not self.original_image:
            self.update_status("Нечего сохранять")
            return

        # Merge squares into masks
        for rect in self.squares_white:
            painter = QPainter(self.mask1_image)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
            r = rect.rect()
            painter.drawRect(int(r.x()), int(r.y()), int(r.width()), int(r.height()))
            painter.end()

        for rect in self.squares_red:
            painter = QPainter(self.mask2_image)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
            r = rect.rect()
            painter.drawRect(int(r.x()), int(r.y()), int(r.width()), int(r.height()))
            painter.end()

        # Convert to binary and save
        self._save_binary_mask(self.mask1_image, "mask1_edited.png")
        self._save_binary_mask(self.mask2_image, "mask2_edited.png")
        self.update_status("Сохранено: mask1_edited.png, mask2_edited.png")

    def _save_binary_mask(self, mask: QImage, filename: str):
        output = QImage(mask.width(), mask.height(), QImage.Format.Format_RGB32)
        output.fill(QColor(0, 0, 0))

        for y in range(mask.height()):
            for x in range(mask.width()):
                if mask.pixelColor(x, y).alpha() > 128:
                    output.setPixelColor(x, y, QColor(255, 255, 255))

        output.save(filename)

    def update_status(self, msg):
        if self.status_callback:
            self.status_callback(msg)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = True
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif event.key() == Qt.Key.Key_1:
            self.current_class = 1
            self.update_status("Класс: белая")
        elif event.key() == Qt.Key.Key_2:
            self.current_class = 2
            self.update_status("Класс: красная")
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
        elif event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.save_masks()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = False
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if self.ctrl_pressed and self.original_image:
            pos = self.mapToScene(event.pos())
            x, y = int(pos.x()), int(pos.y())
            if 0 <= x < self.img_width and 0 <= y < self.img_height:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.add_square(x, y)
                elif event.button() == Qt.MouseButton.RightButton:
                    self.flood_fill_delete(x, y)
        else:
            super().mousePressEvent(event)


# =====================================================================
# TAB 3: POLYLINE MASK EDITOR — для труб/линий
# =====================================================================

class PolylineTool(Enum):
    POLYLINE = auto()
    ERASER = auto()


class PolylineMaskEditor(QGraphicsView):
    """Редактор масок с полилиниями (из polyline_mask_editor.py)"""

    def __init__(self):
        super().__init__()

        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # Images
        self.original_image = None
        self.mask_image = None
        self.img_width = 0
        self.img_height = 0

        # Current tool
        self.current_tool = PolylineTool.POLYLINE
        self.line_width = 3

        # Polyline state
        self.current_polyline_points: list[QPointF] = []
        self.current_path_item: QGraphicsPathItem | None = None
        self.preview_line_item: QGraphicsPathItem | None = None

        # Completed polylines
        self.polylines: list[QGraphicsPathItem] = []

        # Undo stack
        self.undo_stack: deque = deque(maxlen=MAX_UNDO_STEPS)

        # Eraser cursor
        self.eraser_cursor: QGraphicsEllipseItem | None = None

        # COCO bounding boxes for node visualization
        self.coco_annotations: list[dict] = []
        self.bbox_frames_item: QGraphicsPixmapItem | None = None

        # Setup view
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setMouseTracking(True)

        self.ctrl_pressed = False
        self._erasing = False
        self.status_callback = None

        # Placeholder
        self.show_placeholder()

    def show_placeholder(self):
        self.scene.clear()
        text = self.scene.addText("Загрузите изображение и маску")
        text.setDefaultTextColor(QColor(150, 150, 150))

    def load_images(self, original_path: str, mask_path: str):
        """Load images"""
        self.original_image = QImage(original_path)
        if self.original_image.isNull():
            return False

        self.img_width = self.original_image.width()
        self.img_height = self.original_image.height()

        # Mask
        if mask_path and Path(mask_path).exists():
            mask_raw = QImage(mask_path)
            if mask_raw.isNull():
                return False
            self.mask_image = self._make_black_transparent(mask_raw)
        else:
            self.mask_image = QImage(self.img_width, self.img_height, QImage.Format.Format_ARGB32)
            self.mask_image.fill(QColor(0, 0, 0, 0))

        self.setup_scene()
        return True

    def load_images_with_coco(self, original_path: str, mask_path: str, coco_path: str = "") -> bool:
        """Load images with optional COCO annotations for bbox frames"""
        # Load COCO first (before setup_scene)
        if coco_path and Path(coco_path).exists():
            self.load_coco_annotations(coco_path)
        else:
            self.coco_annotations = []

        return self.load_images(original_path, mask_path)

    def _make_black_transparent(self, img: QImage) -> QImage:
        """Convert black pixels to transparent"""
        result = img.convertToFormat(QImage.Format.Format_ARGB32)
        ptr = result.bits()
        bpl = result.bytesPerLine()
        threshold = 128

        for y in range(result.height()):
            for x in range(result.width()):
                idx = y * bpl + x * 4
                b, g, r, a = ptr[idx], ptr[idx + 1], ptr[idx + 2], ptr[idx + 3]
                brightness = (r + g + b) // 3

                if brightness < threshold:
                    ptr[idx + 3] = 0
                else:
                    ptr[idx], ptr[idx + 1], ptr[idx + 2] = 255, 255, 255
                    ptr[idx + 3] = 255

        return result

    def load_coco_annotations(self, coco_path: str) -> bool:
        """Load COCO annotations for bbox frames"""
        try:
            with open(coco_path, 'r', encoding='utf-8') as f:
                coco_data = json.load(f)
            self.coco_annotations = coco_data.get('annotations', [])
            return True
        except Exception as e:
            print(f"COCO load error: {e}")
            self.coco_annotations = []
            return False

    def _render_bbox_frames(self) -> QImage:
        """Render all bbox/polygon frames as red 2px outlines into single QImage"""
        frames_img = QImage(self.img_width, self.img_height, QImage.Format.Format_ARGB32)
        frames_img.fill(QColor(0, 0, 0, 0))  # Transparent background

        if not self.coco_annotations:
            return frames_img

        painter = QPainter(frames_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # Crisp lines

        pen = QPen(QColor(255, 0, 0, 255))  # Red, fully opaque
        pen.setWidth(2)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)  # No fill, only outline

        drawn_count = 0
        for ann in self.coco_annotations:
            drawn = False

            # Priority 1: segmentation polygon (if non-empty)
            if 'segmentation' in ann and ann['segmentation']:
                seg = ann['segmentation']
                for poly_coords in seg:
                    if len(poly_coords) >= 6:  # Minimum 3 points (6 values)
                        polygon = []
                        for i in range(0, len(poly_coords), 2):
                            polygon.append(QPointF(poly_coords[i], poly_coords[i + 1]))

                        path = QPainterPath()
                        path.moveTo(polygon[0])
                        for pt in polygon[1:]:
                            path.lineTo(pt)
                        path.closeSubpath()
                        painter.drawPath(path)
                        drawn = True

            # Priority 2: bbox rectangle (fallback if no segmentation)
            if not drawn and 'bbox' in ann and ann['bbox']:
                x, y, w, h = ann['bbox']
                painter.drawRect(round(x), round(y), round(w), round(h))
                drawn = True

            if drawn:
                drawn_count += 1

        painter.end()

        skipped = len(self.coco_annotations) - drawn_count
        if skipped > 0:
            print(f"⚠️ {skipped} annotations without bbox/segmentation skipped")

        return frames_img

    def setup_scene(self):
        self.scene.clear()
        self.polylines.clear()
        self.current_polyline_points.clear()
        self.current_path_item = None
        self.preview_line_item = None
        self.undo_stack.clear()

        # Layer 0: Original (darkened)
        darkened = self.original_image.copy().convertToFormat(QImage.Format.Format_ARGB32)
        painter = QPainter(darkened)
        painter.fillRect(darkened.rect(), QColor(0, 0, 0, 153))
        painter.end()

        self.original_item = QGraphicsPixmapItem(QPixmap.fromImage(darkened))
        self.original_item.setZValue(0)
        self.scene.addItem(self.original_item)

        # Layer 0.5: COCO bbox frames (red outlines)
        if self.coco_annotations:
            bbox_frames_img = self._render_bbox_frames()
            self.bbox_frames_item = QGraphicsPixmapItem(QPixmap.fromImage(bbox_frames_img))
            self.bbox_frames_item.setZValue(0.5)
            self.scene.addItem(self.bbox_frames_item)
        else:
            self.bbox_frames_item = None

        # Layer 1: Mask
        self.mask_item = QGraphicsPixmapItem(QPixmap.fromImage(self.mask_image))
        self.mask_item.setZValue(1)
        self.mask_item.setOpacity(0.9)
        self.scene.addItem(self.mask_item)

        # Eraser cursor
        self.eraser_cursor = QGraphicsEllipseItem()
        self.eraser_cursor.setPen(QPen(QColor(255, 100, 100), 1, Qt.PenStyle.DashLine))
        self.eraser_cursor.setBrush(QBrush(QColor(255, 0, 0, 50)))
        self.eraser_cursor.setZValue(100)
        self.eraser_cursor.hide()
        self.scene.addItem(self.eraser_cursor)

        self.setSceneRect(QRectF(0, 0, self.img_width, self.img_height))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def update_mask_display(self):
        self.mask_item.setPixmap(QPixmap.fromImage(self.mask_image))

    def set_tool(self, tool: PolylineTool):
        if self.current_tool == PolylineTool.POLYLINE and tool != PolylineTool.POLYLINE:
            self._finish_polyline()

        self.current_tool = tool

        if tool == PolylineTool.ERASER:
            if self.eraser_cursor:
                self.eraser_cursor.show()
            self._update_eraser_cursor_size()
        else:
            if self.eraser_cursor:
                self.eraser_cursor.hide()

        self.update_status(f"Инструмент: {'Полилиния' if tool == PolylineTool.POLYLINE else 'Ластик'}")

    def set_line_width(self, width: int):
        self.line_width = width
        self._update_eraser_cursor_size()

        if self.current_path_item:
            pen = self.current_path_item.pen()
            pen.setWidth(width)
            self.current_path_item.setPen(pen)

    def _update_eraser_cursor_size(self):
        if self.eraser_cursor:
            r = self.line_width / 2
            self.eraser_cursor.setRect(-r, -r, self.line_width, self.line_width)

    # ==================== POLYLINE ====================

    def _add_polyline_point(self, pos: QPointF):
        self.current_polyline_points.append(pos)

        if len(self.current_polyline_points) == 1:
            self.current_path_item = QGraphicsPathItem()
            pen = QPen(QColor(0, 255, 0), self.line_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self.current_path_item.setPen(pen)
            self.current_path_item.setZValue(2)
            self.scene.addItem(self.current_path_item)

        self._update_polyline_path()
        self.update_status(f"Точка {len(self.current_polyline_points)}. 2×клик/ПКМ/Enter — завершить")

    def _update_polyline_path(self):
        if not self.current_path_item or len(self.current_polyline_points) < 1:
            return

        path = QPainterPath()
        path.moveTo(self.current_polyline_points[0])
        for pt in self.current_polyline_points[1:]:
            path.lineTo(pt)

        self.current_path_item.setPath(path)

    def _update_preview_line(self, mouse_pos: QPointF):
        if not self.current_polyline_points:
            return

        last_pt = self.current_polyline_points[-1]

        if not self.preview_line_item:
            self.preview_line_item = QGraphicsPathItem()
            pen = QPen(QColor(0, 255, 0, 128), self.line_width)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self.preview_line_item.setPen(pen)
            self.preview_line_item.setZValue(3)
            self.scene.addItem(self.preview_line_item)

        path = QPainterPath()
        path.moveTo(last_pt)
        path.lineTo(mouse_pos)
        self.preview_line_item.setPath(path)

    def _finish_polyline(self):
        if self.preview_line_item:
            self.scene.removeItem(self.preview_line_item)
            self.preview_line_item = None

        if not self.current_path_item or len(self.current_polyline_points) < 2:
            if self.current_path_item:
                self.scene.removeItem(self.current_path_item)
                self.current_path_item = None
            self.current_polyline_points.clear()
            self.update_status("Полилиния отменена (нужно минимум 2 точки)")
            return

        pen = QPen(QColor(255, 255, 255), self.line_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.current_path_item.setPen(pen)

        self.polylines.append(self.current_path_item)
        self.undo_stack.append(('polyline', self.current_path_item))

        self.update_status(f"Полилиния завершена ({len(self.current_polyline_points)} точек)")

        self.current_path_item = None
        self.current_polyline_points.clear()

    def _cancel_polyline(self):
        if self.preview_line_item:
            self.scene.removeItem(self.preview_line_item)
            self.preview_line_item = None

        if self.current_path_item:
            self.scene.removeItem(self.current_path_item)
            self.current_path_item = None

        self.current_polyline_points.clear()
        self.update_status("Полилиния отменена")

    # ==================== ERASER ====================

    def _bake_polylines_to_mask(self):
        if not self.polylines:
            return

        count = len(self.polylines)

        painter = QPainter(self.mask_image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for item in self.polylines:
            pen = QPen(QColor(255, 255, 255, 255), item.pen().width())
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(item.path())

        painter.end()

        for item in self.polylines:
            self.scene.removeItem(item)
        self.polylines.clear()

        self.undo_stack = deque(
            [a for a in self.undo_stack if a[0] != 'polyline'],
            maxlen=MAX_UNDO_STEPS
        )

        self.update_mask_display()
        self.update_status(f"⚠️ {count} полилиний объединены с маской")

    def _erase_at(self, pos: QPointF):
        x, y = int(pos.x()), int(pos.y())
        radius = self.line_width // 2

        if not self._erasing:
            if self.polylines:
                self._bake_polylines_to_mask()
            self.undo_stack.append(('erase', self.mask_image.copy()))
            self._erasing = True

        painter = QPainter(self.mask_image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(x, y), radius, radius)
        painter.end()

        self.update_mask_display()

    def _stop_erasing(self):
        self._erasing = False

    # ==================== UNDO ====================

    def undo(self):
        if not self.undo_stack:
            self.update_status("Нечего отменять")
            return

        action = self.undo_stack.pop()

        if action[0] == 'polyline':
            item = action[1]
            self.scene.removeItem(item)
            if item in self.polylines:
                self.polylines.remove(item)
            self.update_status("Undo: полилиния удалена")

        elif action[0] == 'erase':
            old_mask = action[1]
            self.mask_image = old_mask
            self.update_mask_display()
            self.update_status("Undo: ластик отменён")

    # ==================== SAVE ====================

    def save_mask(self):
        if not self.original_image:
            self.update_status("Нечего сохранять")
            return

        painter = QPainter(self.mask_image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for item in self.polylines:
            pen = QPen(QColor(255, 255, 255), item.pen().width())
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(item.path())

        painter.end()

        output = QImage(self.img_width, self.img_height, QImage.Format.Format_RGB32)
        output.fill(QColor(0, 0, 0))

        for y in range(self.img_height):
            for x in range(self.img_width):
                if self.mask_image.pixelColor(x, y).alpha() > 128:
                    output.setPixelColor(x, y, QColor(255, 255, 255))

        output.save("polyline_mask_edited.png")
        self.update_status("Сохранено: polyline_mask_edited.png")

    def update_status(self, msg: str):
        if self.status_callback:
            self.status_callback(msg)

    # ==================== EVENTS ====================

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = True
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.current_tool == PolylineTool.POLYLINE:
                self._finish_polyline()
        elif event.key() == Qt.Key.Key_Escape:
            if self.current_tool == PolylineTool.POLYLINE:
                self._cancel_polyline()
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
        elif event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.save_mask()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = False
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if self.ctrl_pressed and self.original_image:
            pos = self.mapToScene(event.pos())

            if 0 <= pos.x() < self.img_width and 0 <= pos.y() < self.img_height:
                if event.button() == Qt.MouseButton.LeftButton:
                    if self.current_tool == PolylineTool.POLYLINE:
                        self._add_polyline_point(pos)
                    elif self.current_tool == PolylineTool.ERASER:
                        self._erase_at(pos)
                elif event.button() == Qt.MouseButton.RightButton:
                    if self.current_tool == PolylineTool.POLYLINE:
                        self._finish_polyline()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.ctrl_pressed and self.current_tool == PolylineTool.POLYLINE:
            if event.button() == Qt.MouseButton.LeftButton:
                self._finish_polyline()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = self.mapToScene(event.pos())

        if self.current_tool == PolylineTool.ERASER and self.eraser_cursor:
            self.eraser_cursor.setPos(pos)

        if self.ctrl_pressed:
            if self.current_tool == PolylineTool.POLYLINE and self.current_polyline_points:
                self._update_preview_line(pos)

            if self.current_tool == PolylineTool.ERASER and event.buttons() & Qt.MouseButton.LeftButton:
                if 0 <= pos.x() < self.img_width and 0 <= pos.y() < self.img_height:
                    self._erase_at(pos)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.current_tool == PolylineTool.ERASER:
            self._stop_erasing()
        super().mouseReleaseEvent(event)


# =====================================================================
# TAB 4: GRAPH VALIDATOR — добавление/удаление рёбер
# =====================================================================

class GraphEditorMode(Enum):
    ADD_EDGE = auto()
    DELETE_EDGE = auto()
    ADD_CONNECTOR = auto()
    DELETE_NODE = auto()
    OPTIMIZE_EDGE = auto()  # Клик на ребро → оптимизировать перпендикулярность
    DRAG_NODE = auto()  # Перетаскивание узлов


class GraphValidatorEditor(QGraphicsView):
    """Редактор графа для валидации рёбер между узлами P&ID"""

    # Цвета
    COLOR_EQUIPMENT = QColor("#3498db")       # Синий
    COLOR_CONNECTOR = QColor("#2ecc71")       # Зелёный
    COLOR_ISOLATED = QColor("#e74c3c")        # Красный — изолированные узлы
    COLOR_EDGE = QColor(255, 255, 255, 150)   # Белый 60%
    COLOR_EDGE_BAD = QColor("#e67e22")        # Оранжевый — неперпендикулярные рёбра
    COLOR_SELECTION = QColor("#f1c40f")       # Жёлтый
    COLOR_HOVER = QColor("#9b59b6")           # Фиолетовый
    COLOR_PREVIEW_OK = QColor("#2ecc71")      # Зелёный (можно выполнить)
    COLOR_PREVIEW_NO = QColor("#7f8c8d")      # Серый (нельзя)
    COLOR_PREVIEW_DELETE = QColor("#e74c3c")  # Красный (удаление)
    COLOR_EDGE_HIGHLIGHT = QColor("#f39c12")  # Оранжевый — подсветка ребра
    COLOR_CONNECTOR_PREVIEW = QColor("#f1c40f")  # Жёлтый — preview точки

    # Размеры
    EQUIPMENT_MARKER_RADIUS = 6
    CONNECTOR_MARKER_RADIUS = 8
    CLICK_THRESHOLD = 20
    SELECTION_RING_WIDTH = 3
    EDGE_WIDTH = 2

    def __init__(self):
        super().__init__()

        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # === DATA ===
        self.graph_data: dict = {}
        self.nodes: dict[str, dict] = {}
        self.edges: set[tuple[str, str]] = set()
        self.edges_data: list[dict] = []
        self.manual_node_counter = 0  # Счётчик для ID новых узлов
        self.coco_annotations: dict[int, dict] = {}  # yolo_idx → annotation

        # === PERPENDICULARITY DATA ===
        self.edge_perp_scores: dict[tuple[str, str], dict] = {}  # key → perp info
        self.show_bad_edges: bool = True  # Подсвечивать неперпендикулярные

        # === IMAGE DATA ===
        self.original_image: QImage | None = None
        self.img_width = 0
        self.img_height = 0

        # === GRAPHICS ITEMS ===
        self.node_items: dict[str, QGraphicsEllipseItem] = {}
        self.edge_items: dict[tuple[str, str], QGraphicsLineItem] = {}
        self.bbox_items: dict[str, QGraphicsRectItem] = {}
        self.polygon_items: dict[str, QGraphicsPathItem] = {}  # Полигоны из COCO

        # === STATE ===
        self.mode: GraphEditorMode = GraphEditorMode.ADD_EDGE
        self.selected_node: str | None = None
        self.hovered_node: str | None = None
        self.hovered_edge: tuple[str, str] | None = None  # Для режима ADD_CONNECTOR

        # === UI ITEMS ===
        self.selection_ring: QGraphicsEllipseItem | None = None
        self.hover_ring: QGraphicsEllipseItem | None = None
        self.preview_line: QGraphicsLineItem | None = None
        self.edge_highlight: QGraphicsLineItem | None = None  # Подсветка ребра
        self.connector_preview: QGraphicsEllipseItem | None = None  # Preview точки коннектора

        # === UNDO ===
        self.undo_stack: deque = deque(maxlen=MAX_UNDO_STEPS)

        # === DRAG STATE ===
        self.dragging_node: str | None = None
        self.drag_start_centroid: list | None = None
        self.drag_start_edge_points: dict = {}  # edge_key → {'source_point', 'target_point'}

        # Setup view
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setMouseTracking(True)

        self.ctrl_pressed = False
        self.status_callback = None
        self.stats_callback = None

        self.show_placeholder()

    def show_placeholder(self):
        self.scene.clear()
        text = self.scene.addText("Загрузите изображение и граф")
        text.setDefaultTextColor(QColor(150, 150, 150))

    def load_data(self, image_path: str, graph_path: str, coco_path: str = "") -> bool:
        """Загрузка изображения, графа и опционально COCO аннотаций"""

        # 1. Original image
        self.original_image = QImage(image_path)
        if self.original_image.isNull():
            self.update_status("Ошибка загрузки изображения")
            return False

        self.img_width = self.original_image.width()
        self.img_height = self.original_image.height()

        # 2. Graph JSON
        try:
            with open(graph_path, 'r', encoding='utf-8') as f:
                self.graph_data = json.load(f)
        except Exception as e:
            self.update_status(f"Ошибка загрузки графа: {e}")
            return False

        # 3. COCO annotations (optional)
        self.coco_annotations.clear()
        if coco_path and Path(coco_path).exists():
            try:
                with open(coco_path, 'r', encoding='utf-8') as f:
                    coco_data = json.load(f)
                # Индексируем по id аннотации
                for ann in coco_data.get('annotations', []):
                    ann_id = ann.get('id')
                    if ann_id is not None:
                        self.coco_annotations[ann_id] = ann
                print(f"[DEBUG] Loaded {len(self.coco_annotations)} COCO annotations")
            except Exception as e:
                print(f"[DEBUG] Failed to load COCO: {e}")

        # 4. Parse nodes
        self.nodes.clear()
        self.manual_node_counter = 0
        for node in self.graph_data.get('nodes', []):
            node_id = node['id']
            self.nodes[node_id] = node

        print(f"[DEBUG] Loaded {len(self.nodes)} nodes")

        # 5. Parse edges (ключ 'links' в формате NetworkX)
        self.edges.clear()
        raw_edges = self.graph_data.get('links', [])

        # Фильтруем рёбра с None source/target
        self.edges_data = [e for e in raw_edges if e.get('source') and e.get('target')]
        print(f"[DEBUG] Loaded {len(self.edges_data)} valid edges from {len(raw_edges)} total")

        for edge in self.edges_data:
            a, b = edge['source'], edge['target']
            self.edges.add(self._edge_key(a, b))

        self.setup_scene()
        self.update_statistics()
        return True

    def _edge_key(self, a: str, b: str) -> tuple[str, str]:
        """Создаёт отсортированный ключ для ребра"""
        return (min(a, b), max(a, b))

    def get_connection_point(self, node_id: str, target_x: float, target_y: float) -> tuple[float, float]:
        """
        Вычислить точку соединения на границе узла, ближайшую к целевой точке.
        Приоритет: segmentation (полигон) > bbox (прямоугольник) > circle (окружность).
        """
        node = self.nodes[node_id]
        cx, cy = node['centroid'][1], node['centroid'][0]
        node_type = node.get('type', 'connector')

        if node_type == 'equipment':
            # Приоритет 1: segmentation (точный полигон)
            segmentation = node.get('segmentation')
            if segmentation and len(segmentation) >= 6:
                return self._closest_point_on_polygon(segmentation, cx, cy, target_x, target_y)

            # Приоритет 2: bbox (прямоугольник)
            bbox = node.get('bbox')
            if bbox and len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                return self._closest_point_on_rect(x1, y1, x2, y2, target_x, target_y)

        # Для connector — точка на окружности
        area = node.get('area', 225)
        radius = (area / 3.14159) ** 0.5
        return self._closest_point_on_circle(cx, cy, radius, target_x, target_y)

    def _closest_point_on_polygon(self, polygon: list, cx: float, cy: float,
                                   px: float, py: float) -> tuple[float, float]:
        """
        Найти точку на границе полигона, где луч из центра к целевой точке пересекает границу.
        polygon: [x1, y1, x2, y2, ...] — плоский список координат.
        """
        n = len(polygon) // 2
        if n < 3:
            return (cx, cy)

        # Вектор направления от центра к цели
        dx = px - cx
        dy = py - cy

        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            # Цель в центре — возвращаем первую вершину
            return (polygon[0], polygon[1])

        best_point = None
        best_t = float('inf')

        # Проверяем пересечение луча с каждым ребром полигона
        for i in range(n):
            # Текущее ребро: (x1, y1) — (x2, y2)
            x1 = polygon[i * 2]
            y1 = polygon[i * 2 + 1]
            x2 = polygon[((i + 1) % n) * 2]
            y2 = polygon[((i + 1) % n) * 2 + 1]

            # Вектор ребра
            ex = x2 - x1
            ey = y2 - y1

            # Решаем систему: center + t * direction = edge_start + s * edge_direction
            # cx + t * dx = x1 + s * ex
            # cy + t * dy = y1 + s * ey

            denom = dx * ey - dy * ex
            if abs(denom) < 1e-9:
                continue  # Параллельные линии

            t = ((x1 - cx) * ey - (y1 - cy) * ex) / denom
            s = ((x1 - cx) * dy - (y1 - cy) * dx) / denom

            # t > 0 (в направлении цели), 0 <= s <= 1 (на ребре)
            if t > 0 and 0 <= s <= 1:
                if t < best_t:
                    best_t = t
                    best_point = (cx + t * dx, cy + t * dy)

        if best_point:
            return best_point

        # Fallback: ближайшая точка на любом ребре
        return self._closest_point_on_polygon_edge(polygon, px, py)

    def _closest_point_on_rect(self, x1: float, y1: float, x2: float, y2: float,
                                px: float, py: float) -> tuple[float, float]:
        """Найти ближайшую точку на границе прямоугольника к точке (px, py)"""
        # Центр прямоугольника
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # Вектор от центра к целевой точке
        dx = px - cx
        dy = py - cy

        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return (x1, cy)  # Точка в центре — возвращаем левую сторону

        # Полуразмеры
        half_w = (x2 - x1) / 2
        half_h = (y2 - y1) / 2

        # Находим пересечение луча из центра с границей
        if abs(dx) > 1e-6:
            # Пересечение с вертикальными сторонами
            t_left = -half_w / dx if dx != 0 else float('inf')
            t_right = half_w / dx if dx != 0 else float('inf')
        else:
            t_left = t_right = float('inf')

        if abs(dy) > 1e-6:
            # Пересечение с горизонтальными сторонами
            t_top = -half_h / dy if dy != 0 else float('inf')
            t_bottom = half_h / dy if dy != 0 else float('inf')
        else:
            t_top = t_bottom = float('inf')

        # Берём минимальный положительный t
        t_values = [t for t in [t_left, t_right, t_top, t_bottom] if t > 0]
        if not t_values:
            return (cx, cy)

        t = min(t_values)

        # Точка на границе
        bx = cx + dx * t
        by = cy + dy * t

        # Ограничиваем в пределах bbox (на случай погрешностей)
        bx = max(x1, min(x2, bx))
        by = max(y1, min(y2, by))

        return (bx, by)

    def _closest_point_on_circle(self, cx: float, cy: float, radius: float,
                                  px: float, py: float) -> tuple[float, float]:
        """Найти ближайшую точку на окружности к точке (px, py)"""
        dx = px - cx
        dy = py - cy
        dist = (dx * dx + dy * dy) ** 0.5

        if dist < 1e-6:
            return (cx + radius, cy)  # Точка в центре — возвращаем правую точку

        # Нормализуем и масштабируем на радиус
        return (cx + dx / dist * radius, cy + dy / dist * radius)

    def _closest_point_on_polygon_edge(self, polygon: list, px: float, py: float) -> tuple[float, float]:
        """
        Найти ближайшую точку на границе полигона к заданной точке.
        Используется как fallback когда луч не пересекает полигон.
        """
        n = len(polygon) // 2
        if n < 2:
            return (polygon[0], polygon[1]) if n >= 1 else (px, py)

        best_point = None
        best_dist_sq = float('inf')

        for i in range(n):
            # Ребро: (x1, y1) — (x2, y2)
            x1 = polygon[i * 2]
            y1 = polygon[i * 2 + 1]
            x2 = polygon[((i + 1) % n) * 2]
            y2 = polygon[((i + 1) % n) * 2 + 1]

            # Проекция точки на отрезок
            ex, ey = x2 - x1, y2 - y1
            length_sq = ex * ex + ey * ey

            if length_sq < 1e-9:
                # Вырожденное ребро
                proj_x, proj_y = x1, y1
            else:
                t = max(0, min(1, ((px - x1) * ex + (py - y1) * ey) / length_sq))
                proj_x = x1 + t * ex
                proj_y = y1 + t * ey

            dist_sq = (px - proj_x) ** 2 + (py - proj_y) ** 2
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_point = (proj_x, proj_y)

        return best_point if best_point else (px, py)

    def setup_scene(self):
        """Настройка сцены со всеми слоями"""
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self.bbox_items.clear()
        self.polygon_items.clear()
        self.selection_ring = None
        self.hover_ring = None
        self.preview_line = None
        self.edge_highlight = None
        self.connector_preview = None
        self.selected_node = None
        self.hovered_node = None
        self.hovered_edge = None

        # Z=0: Original image (darkened)
        darkened = self.original_image.copy().convertToFormat(QImage.Format.Format_ARGB32)
        painter = QPainter(darkened)
        painter.fillRect(darkened.rect(), QColor(0, 0, 0, 153))
        painter.end()

        bg_item = QGraphicsPixmapItem(QPixmap.fromImage(darkened))
        bg_item.setZValue(0)
        self.scene.addItem(bg_item)

        # Z=1: Edges
        self._draw_all_edges()

        # Z=2: Polygons/Bbox frames (equipment only)
        # Z=3: Node markers
        self._draw_all_nodes()

        self.setSceneRect(QRectF(0, 0, self.img_width, self.img_height))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _draw_all_edges(self):
        """Отрисовка всех рёбер с подсветкой неперпендикулярных"""
        pen_good = QPen(self.COLOR_EDGE, self.EDGE_WIDTH)
        pen_bad = QPen(self.COLOR_EDGE_BAD, self.EDGE_WIDTH + 1)
        drawn_count = 0
        bad_count = 0

        self.edge_perp_scores.clear()

        for edge in self.edges_data:
            source_id = edge['source']
            target_id = edge['target']

            if source_id not in self.nodes or target_id not in self.nodes:
                continue

            # Используем точные точки контакта из edge
            source_point = edge.get('source_point')
            target_point = edge.get('target_point')

            if source_point and target_point:
                # source_point/target_point: [y, x] → swap
                x1, y1 = source_point[1], source_point[0]
                x2, y2 = target_point[1], target_point[0]
            else:
                # Fallback на centroid если точек нет
                source = self.nodes[source_id]
                target = self.nodes[target_id]
                x1, y1 = source['centroid'][1], source['centroid'][0]
                x2, y2 = target['centroid'][1], target['centroid'][0]

            key = self._edge_key(source_id, target_id)

            # Вычисляем перпендикулярность
            source_geom = self._get_node_geometry(source_id)
            target_geom = self._get_node_geometry(target_id)
            perp_info = compute_edge_perpendicularity((x1, y1), (x2, y2), source_geom, target_geom)
            self.edge_perp_scores[key] = perp_info

            # Выбираем цвет
            if self.show_bad_edges and not perp_info['is_good']:
                pen = pen_bad
                bad_count += 1
            else:
                pen = pen_good

            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setZValue(1)
            self.scene.addItem(line)

            self.edge_items[key] = line
            drawn_count += 1

        print(f"[DEBUG] Drawn {drawn_count} edges ({bad_count} non-perpendicular)")

    def _get_node_geometry(self, node_id: str) -> dict:
        """Получить геометрию узла для расчёта перпендикулярности."""
        node = self.nodes.get(node_id)
        if not node:
            return {'type': 'point', 'data': None}

        node_type = node.get('type', 'connector')
        bbox = node.get('bbox')
        poly = node.get('segmentation')

        # Приоритет: polygon > bbox > point
        if poly and isinstance(poly, list) and len(poly) >= 6:
            return {'type': 'polygon', 'data': poly}
        if bbox and len(bbox) == 4:
            return {'type': 'bbox', 'data': bbox}
        return {'type': 'point', 'data': None}

    def _draw_all_nodes(self):
        """Отрисовка всех узлов с визуальным различием подключенных/изолированных"""
        print(f"[DEBUG] === _draw_all_nodes called ===")

        # Строим множество подключенных узлов
        connected_nodes = set()
        for a, b in self.edges:
            connected_nodes.add(a)
            connected_nodes.add(b)

        # Отслеживаем bbox для которых уже нарисован полигон (чтобы избежать дубликатов)
        drawn_bboxes: set[tuple] = set()

        # Первый проход: собираем все bbox у которых есть полигон
        for node_id, node in self.nodes.items():
            node_type = node.get('type', 'connector')
            if node_type != 'equipment':
                continue
            segmentation = node.get('segmentation')
            bbox = node.get('bbox')
            has_polygon = segmentation and isinstance(segmentation, list) and len(segmentation) >= 6
            if has_polygon and bbox:
                drawn_bboxes.add(tuple(bbox))

        print(f"[DEBUG] Found {len(drawn_bboxes)} bboxes with polygons (will skip duplicates)")

        # Второй проход: рисуем все узлы
        for node_id, node in self.nodes.items():
            cx, cy = node['centroid'][1], node['centroid'][0]
            node_type = node.get('type', 'connector')
            is_isolated = node_id not in connected_nodes

            # Выбираем цвет
            if is_isolated:
                color = self.COLOR_ISOLATED
            elif node_type == 'equipment':
                color = self.COLOR_EQUIPMENT
            else:
                color = self.COLOR_CONNECTOR

            if node_type == 'equipment':
                segmentation = node.get('segmentation')
                bbox = node.get('bbox')
                has_polygon = segmentation and isinstance(segmentation, list) and len(segmentation) >= 6

                if has_polygon:
                    # Рисуем полигон
                    print(f"[DEBUG] >>> POLYGON for {node_id}")
                    path = QPainterPath()
                    path.moveTo(segmentation[0], segmentation[1])
                    for i in range(2, len(segmentation), 2):
                        path.lineTo(segmentation[i], segmentation[i + 1])
                    path.closeSubpath()

                    poly_item = QGraphicsPathItem(path)
                    poly_item.setPen(QPen(color, 2))
                    poly_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                    poly_item.setZValue(2)
                    self.scene.addItem(poly_item)
                    self.polygon_items[node_id] = poly_item
                else:
                    # bbox только если НЕТ полигона И этот bbox не дубликат
                    if bbox and len(bbox) == 4:
                        bbox_key = tuple(bbox)
                        if bbox_key in drawn_bboxes:
                            # Пропускаем дубликат - для этого bbox уже нарисован полигон
                            print(f"[DEBUG] >>> SKIP DUPLICATE BBOX for {node_id} (polygon exists)")
                        else:
                            print(f"[DEBUG] >>> BBOX for {node_id}")
                            x1, y1, x2, y2 = bbox
                            rect = QGraphicsRectItem(x1, y1, x2 - x1, y2 - y1)
                            rect.setPen(QPen(color, 2))
                            rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            rect.setZValue(2)
                            self.scene.addItem(rect)
                            self.bbox_items[node_id] = rect

                # Center marker
                r = self.EQUIPMENT_MARKER_RADIUS
                marker = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
                marker.setPen(QPen(color, 2))
                marker.setBrush(QBrush(color.lighter(150)))
                marker.setZValue(3)
            else:
                # Connector — just circle
                r = self.CONNECTOR_MARKER_RADIUS
                marker = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
                marker.setPen(QPen(color, 2))
                marker.setBrush(QBrush(color.lighter(150)))
                marker.setZValue(3)

            self.scene.addItem(marker)
            self.node_items[node_id] = marker

        print(f"[DEBUG] Drawn {len(self.polygon_items)} polygons, {len(self.bbox_items)} bboxes")

    def _update_node_color(self, node_id: str):
        """Обновить цвет узла в зависимости от его подключенности"""
        if node_id not in self.node_items:
            return

        node = self.nodes[node_id]
        node_type = node.get('type', 'connector')

        # Проверяем, подключен ли узел
        is_isolated = True
        for a, b in self.edges:
            if node_id == a or node_id == b:
                is_isolated = False
                break

        # Выбираем цвет
        if is_isolated:
            color = self.COLOR_ISOLATED
        elif node_type == 'equipment':
            color = self.COLOR_EQUIPMENT
        else:
            color = self.COLOR_CONNECTOR

        # Обновляем маркер
        marker = self.node_items[node_id]
        marker.setPen(QPen(color, 2))
        marker.setBrush(QBrush(color.lighter(150)))

        # Обновляем polygon рамку если есть
        if node_id in self.polygon_items:
            self.polygon_items[node_id].setPen(QPen(color, 2))
        # Обновляем bbox рамку если есть
        elif node_id in self.bbox_items:
            self.bbox_items[node_id].setPen(QPen(color, 2))

    def find_node_at(self, x: float, y: float) -> str | None:
        """Найти узел по координатам (threshold = CLICK_THRESHOLD)"""
        best_node = None
        best_dist = self.CLICK_THRESHOLD

        for node_id, node in self.nodes.items():
            # centroid: [y, x]
            cx, cy = node['centroid'][1], node['centroid'][0]
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5

            if dist < best_dist:
                best_dist = dist
                best_node = node_id

        return best_node

    def edge_exists(self, a: str, b: str) -> bool:
        """Проверка существования ребра"""
        return self._edge_key(a, b) in self.edges

    def find_nearest_edge(self, x: float, y: float, threshold: float = 15.0) -> tuple[tuple[str, str] | None, tuple[float, float] | None]:
        """
        Найти ближайшее ребро к точке (x, y).
        Возвращает (edge_key, projection_point) или (None, None)
        """
        best_edge = None
        best_point = None
        best_dist = threshold

        for key, line_item in self.edge_items.items():
            line = line_item.line()
            x1, y1 = line.x1(), line.y1()
            x2, y2 = line.x2(), line.y2()

            # Вектор ребра
            dx, dy = x2 - x1, y2 - y1
            length_sq = dx * dx + dy * dy

            if length_sq < 1e-6:
                continue

            # Проекция точки на линию (параметр t от 0 до 1)
            t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / length_sq))

            # Точка проекции
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy

            # Расстояние до проекции
            dist = ((x - proj_x) ** 2 + (y - proj_y) ** 2) ** 0.5

            if dist < best_dist:
                best_dist = dist
                best_edge = key
                best_point = (proj_x, proj_y)

        return best_edge, best_point

    def add_connector_on_edge(self, edge_key: tuple[str, str], pos_x: float, pos_y: float) -> str | None:
        """
        Добавить коннектор на ребро, разбив его на два.
        Сохраняем оригинальные точки контакта с узлами.
        Возвращает ID нового коннектора или None при ошибке.
        """
        if edge_key not in self.edges:
            return None

        node_a, node_b = edge_key

        # Находим и сохраняем данные старого ребра для undo
        old_edge_data = None
        for i, edge in enumerate(self.edges_data):
            if self._edge_key(edge['source'], edge['target']) == edge_key:
                old_edge_data = self.edges_data.pop(i)
                break

        # Определяем оригинальные точки контакта
        # Важно: source/target в edge могут быть в любом порядке относительно edge_key
        if old_edge_data:
            if old_edge_data['source'] == node_a:
                # source = node_a, target = node_b
                original_point_a = old_edge_data.get('source_point')
                original_point_b = old_edge_data.get('target_point')
            else:
                # source = node_b, target = node_a
                original_point_a = old_edge_data.get('target_point')
                original_point_b = old_edge_data.get('source_point')
        else:
            original_point_a = None
            original_point_b = None

        # Создаём новый коннектор
        self.manual_node_counter += 1
        new_node_id = f"node_manual_{self.manual_node_counter}"

        new_node = {
            "id": new_node_id,
            "type": "connector",
            "centroid": [pos_y, pos_x],  # [y, x] формат
            "area": 225,
            "bbox": None,
            "degree": 2,
            "class_id": -1,
            "class_name": "connector",
            "yolo_idx": None,
            "manual": True
        }

        # Удаляем старое ребро из set и scene
        self.edges.remove(edge_key)
        if edge_key in self.edge_items:
            self.scene.removeItem(self.edge_items[edge_key])
            del self.edge_items[edge_key]

        # Добавляем новый узел
        self.nodes[new_node_id] = new_node
        self.graph_data.setdefault('nodes', []).append(new_node)

        # Создаём два новых ребра с сохранением оригинальных точек контакта
        # Ребро A—connector: точка на A = оригинальная, точка на connector = позиция коннектора
        self._create_edge_with_points(
            node_a, new_node_id,
            source_point=original_point_a,  # Оригинальная точка на A
            target_point=[pos_y, pos_x]      # Позиция коннектора
        )

        # Ребро connector—B: точка на connector = позиция коннектора, точка на B = оригинальная
        self._create_edge_with_points(
            new_node_id, node_b,
            source_point=[pos_y, pos_x],     # Позиция коннектора
            target_point=original_point_b    # Оригинальная точка на B
        )

        # Рисуем новый узел
        self._draw_single_node(new_node_id)

        # Undo: сохраняем всю операцию
        self.undo_stack.append(('add_connector_on_edge', new_node_id, node_a, node_b, old_edge_data))

        self.update_status(f"Создан коннектор {new_node_id} на ребре {node_a}—{node_b}")
        self.update_statistics()
        return new_node_id

    def add_connector_isolated(self, pos_x: float, pos_y: float) -> str:
        """Добавить изолированный коннектор в произвольной точке."""
        self.manual_node_counter += 1
        new_node_id = f"node_manual_{self.manual_node_counter}"

        new_node = {
            "id": new_node_id,
            "type": "connector",
            "centroid": [pos_y, pos_x],  # [y, x] формат
            "area": 225,
            "bbox": None,
            "degree": 0,
            "class_id": -1,
            "class_name": "connector",
            "yolo_idx": None,
            "manual": True
        }

        # Добавляем узел
        self.nodes[new_node_id] = new_node
        self.graph_data.setdefault('nodes', []).append(new_node)

        # Рисуем узел
        self._draw_single_node(new_node_id)

        # Undo
        self.undo_stack.append(('add_connector_isolated', new_node_id))

        self.update_status(f"Создан изолированный коннектор {new_node_id}")
        self.update_statistics()
        return new_node_id

    def _create_edge_with_points(self, node_a: str, node_b: str,
                                   source_point: list | None = None,
                                   target_point: list | None = None):
        """
        Создать ребро с заданными точками контакта.
        Если точки не заданы, вычисляются на границе узла.
        source_point/target_point в формате [y, x].
        """
        key = self._edge_key(node_a, node_b)
        self.edges.add(key)

        # Вычисляем точки соединения если не заданы
        if source_point is None:
            # Вычисляем точку на границе node_a в направлении node_b
            tgt = self.nodes[node_b]
            tgt_cx, tgt_cy = tgt['centroid'][1], tgt['centroid'][0]
            src_x, src_y = self.get_connection_point(node_a, tgt_cx, tgt_cy)
            source_point = [src_y, src_x]

        if target_point is None:
            # Вычисляем точку на границе node_b в направлении node_a
            src = self.nodes[node_a]
            src_cx, src_cy = src['centroid'][1], src['centroid'][0]
            tgt_x, tgt_y = self.get_connection_point(node_b, src_cx, src_cy)
            target_point = [tgt_y, tgt_x]

        # Координаты для отрисовки: [y, x] → (x, y)
        x1, y1 = source_point[1], source_point[0]
        x2, y2 = target_point[1], target_point[0]

        new_edge = {
            "id": f"edge_manual_{len(self.edges_data)}",
            "source": node_a,
            "target": node_b,
            "source_point": source_point,
            "target_point": target_point,
            "length": 0,
            "is_terminal": False,
            "color": None,
            "straight_line_distance": 0,
            "manual": True
        }
        self.edges_data.append(new_edge)

        # Рисуем линию
        line = QGraphicsLineItem(x1, y1, x2, y2)
        line.setPen(QPen(self.COLOR_EDGE, self.EDGE_WIDTH))
        line.setZValue(1)
        self.scene.addItem(line)
        self.edge_items[key] = line

    def _create_edge_internal(self, node_a: str, node_b: str, conn_x: float = 0, conn_y: float = 0):
        """Внутренний метод создания ребра с вычислением точек на границах (без undo)"""
        self._create_edge_with_points(node_a, node_b, None, None)

    def _draw_single_node(self, node_id: str):
        """Отрисовать один узел"""
        node = self.nodes[node_id]
        cx, cy = node['centroid'][1], node['centroid'][0]
        node_type = node.get('type', 'connector')

        # Проверяем подключенность
        is_isolated = True
        for a, b in self.edges:
            if node_id == a or node_id == b:
                is_isolated = False
                break

        if is_isolated:
            color = self.COLOR_ISOLATED
        elif node_type == 'equipment':
            color = self.COLOR_EQUIPMENT
        else:
            color = self.COLOR_CONNECTOR

        r = self.EQUIPMENT_MARKER_RADIUS if node_type == 'equipment' else self.CONNECTOR_MARKER_RADIUS
        marker = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
        marker.setPen(QPen(color, 2))
        marker.setBrush(QBrush(color.lighter(150)))
        marker.setZValue(3)
        self.scene.addItem(marker)
        self.node_items[node_id] = marker

    def delete_node(self, node_id: str) -> bool:
        """
        Удалить узел. Если это connector с degree=2, склеить соседей.
        """
        if node_id not in self.nodes:
            self.update_status(f"Узел не найден: {node_id}")
            return False

        node = self.nodes[node_id]
        node_type = node.get('type', 'connector')

        # Находим все рёбра, связанные с этим узлом
        connected_edges = []
        neighbors = []
        for key in list(self.edges):
            if node_id in key:
                connected_edges.append(key)
                other = key[0] if key[1] == node_id else key[1]
                neighbors.append(other)

        # Сохраняем данные для undo
        edges_data_backup = []
        for key in connected_edges:
            for edge in self.edges_data:
                if self._edge_key(edge['source'], edge['target']) == key:
                    edges_data_backup.append(edge.copy())
                    break

        # Определяем, нужно ли склеивание
        should_merge = (node_type == 'connector' and len(neighbors) == 2)

        # Удаляем все связанные рёбра
        for key in connected_edges:
            self.edges.discard(key)
            if key in self.edge_items:
                self.scene.removeItem(self.edge_items[key])
                del self.edge_items[key]
            # Удаляем из edges_data
            self.edges_data = [e for e in self.edges_data
                              if self._edge_key(e['source'], e['target']) != key]

        # Удаляем узел
        if node_id in self.node_items:
            self.scene.removeItem(self.node_items[node_id])
            del self.node_items[node_id]
        if node_id in self.bbox_items:
            self.scene.removeItem(self.bbox_items[node_id])
            del self.bbox_items[node_id]
        if node_id in self.polygon_items:
            self.scene.removeItem(self.polygon_items[node_id])
            del self.polygon_items[node_id]

        node_backup = self.nodes.pop(node_id)
        # Удаляем из graph_data
        self.graph_data['nodes'] = [n for n in self.graph_data.get('nodes', []) if n['id'] != node_id]

        # Если нужно склеить — создаём новое ребро между соседями
        new_edge_data = None
        if should_merge and len(neighbors) == 2:
            n1, n2 = neighbors
            self._create_edge_internal(n1, n2, 0, 0)  # conn_x, conn_y не используются
            # Находим только что созданное ребро для undo
            key = self._edge_key(n1, n2)
            for edge in self.edges_data:
                if self._edge_key(edge['source'], edge['target']) == key:
                    new_edge_data = edge
                    break
            self.update_status(f"Удалён коннектор {node_id}, рёбра склеены: {n1}—{n2}")
        else:
            self.update_status(f"Удалён узел {node_id}")

        # Обновляем цвета соседей
        for neighbor in neighbors:
            self._update_node_color(neighbor)

        # Undo
        self.undo_stack.append(('delete_node', node_id, node_backup, edges_data_backup,
                               neighbors if should_merge else [], new_edge_data))

        self.update_statistics()
        return True

    def add_edge(self, node_a: str, node_b: str) -> bool:
        """
        Добавить ребро между узлами с ПЕРПЕНДИКУЛЯРНЫМ соединением.

        Логика:
        - Bbox + Bbox: строго вертикальная/горизонтальная линия если возможно
        - Bbox + Polygon: перпендикулярно боксу и максимально перпендикулярно ребру полигона
        - Polygon + Polygon: максимально перпендикулярно обоим рёбрам
        - Connector (точка) + Bbox/Polygon: перпендикуляр от точки к стенке
        """
        if node_a == node_b:
            self.update_status("Нельзя соединить узел с самим собой")
            return False

        key = self._edge_key(node_a, node_b)
        if key in self.edges:
            self.update_status(f"Ребро уже существует: {node_a} — {node_b}")
            return False

        # Add to data
        self.edges.add(key)

        # Получаем данные узлов
        src = self.nodes[node_a]
        tgt = self.nodes[node_b]

        # Определяем тип каждого узла
        src_type = src.get('type', 'connector')
        tgt_type = tgt.get('type', 'connector')

        # Получаем геометрию (bbox или segmentation)
        src_bbox = src.get('bbox')
        tgt_bbox = tgt.get('bbox')
        src_poly = src.get('segmentation')
        tgt_poly = tgt.get('segmentation')

        # Центроиды (для коннекторов это основная геометрия)
        src_cx, src_cy = src['centroid'][1], src['centroid'][0]
        tgt_cx, tgt_cy = tgt['centroid'][1], tgt['centroid'][0]

        # Проверяем валидность геометрии
        src_has_bbox = src_bbox and len(src_bbox) == 4
        tgt_has_bbox = tgt_bbox and len(tgt_bbox) == 4
        src_has_poly = src_poly and isinstance(src_poly, list) and len(src_poly) >= 6
        tgt_has_poly = tgt_poly and isinstance(tgt_poly, list) and len(tgt_poly) >= 6

        # Определяем что есть "геометрия" (не просто точка)
        src_is_point = src_type == 'connector' and not src_has_bbox and not src_has_poly
        tgt_is_point = tgt_type == 'connector' and not tgt_has_bbox and not tgt_has_poly

        # Выбираем стратегию соединения
        src_x, src_y, tgt_x, tgt_y = None, None, None, None
        connection_type = "centroid"  # fallback

        # === СЛУЧАЙ 1: Оба — точки (connector без геометрии) ===
        if src_is_point and tgt_is_point:
            src_x, src_y = src_cx, src_cy
            tgt_x, tgt_y = tgt_cx, tgt_cy
            connection_type = "point_point"

        # === СЛУЧАЙ 2: Source — точка, Target — геометрия ===
        elif src_is_point:
            src_point = (src_cx, src_cy)
            if tgt_has_poly:
                (src_x, src_y), (tgt_x, tgt_y), _ = connect_point_polygon(src_point, tgt_poly)
                connection_type = "point_poly"
            elif tgt_has_bbox:
                (src_x, src_y), (tgt_x, tgt_y), connection_type = connect_point_bbox(src_point, tgt_bbox)
            else:
                src_x, src_y = src_cx, src_cy
                tgt_x, tgt_y = tgt_cx, tgt_cy
                connection_type = "point_point_fallback"

        # === СЛУЧАЙ 3: Target — точка, Source — геометрия ===
        elif tgt_is_point:
            tgt_point = (tgt_cx, tgt_cy)
            if src_has_poly:
                (tgt_x, tgt_y), (src_x, src_y), _ = connect_point_polygon(tgt_point, src_poly)
                connection_type = "poly_point"
            elif src_has_bbox:
                (tgt_x, tgt_y), (src_x, src_y), connection_type = connect_point_bbox(tgt_point, src_bbox)
                connection_type = connection_type.replace("point_bbox", "bbox_point")
            else:
                src_x, src_y = src_cx, src_cy
                tgt_x, tgt_y = tgt_cx, tgt_cy
                connection_type = "point_point_fallback"

        # === СЛУЧАЙ 4: Оба имеют геометрию ===
        elif src_has_bbox and tgt_has_bbox and not src_has_poly and not tgt_has_poly:
            # Оба узла — bbox без полигона
            (src_x, src_y), (tgt_x, tgt_y), connection_type = connect_bbox_bbox(src_bbox, tgt_bbox)

        elif src_has_bbox and tgt_has_poly:
            # Source — bbox, Target — polygon
            (src_x, src_y), (tgt_x, tgt_y), _ = connect_bbox_polygon(src_bbox, tgt_poly)
            connection_type = "bbox_poly"

        elif src_has_poly and tgt_has_bbox:
            # Source — polygon, Target — bbox
            (tgt_x, tgt_y), (src_x, src_y), _ = connect_bbox_polygon(tgt_bbox, src_poly)
            connection_type = "poly_bbox"

        elif src_has_poly and tgt_has_poly:
            # Оба — polygon
            (src_x, src_y), (tgt_x, tgt_y), _ = connect_polygon_polygon(src_poly, tgt_poly)
            connection_type = "poly_poly"

        elif src_has_bbox and tgt_has_bbox:
            # Оба — bbox (возможно с полигонами, но используем bbox)
            (src_x, src_y), (tgt_x, tgt_y), connection_type = connect_bbox_bbox(src_bbox, tgt_bbox)

        # Fallback на старую логику через центроиды
        if src_x is None or src_y is None or tgt_x is None or tgt_y is None:
            src_x, src_y = self.get_connection_point(node_a, tgt_cx, tgt_cy)
            tgt_x, tgt_y = self.get_connection_point(node_b, src_cx, src_cy)
            connection_type = "centroid_fallback"

        new_edge = {
            "id": f"edge_manual_{len(self.edges_data)}",
            "source": node_a,
            "target": node_b,
            "source_point": [src_y, src_x],  # [y, x] формат
            "target_point": [tgt_y, tgt_x],
            "length": 0,
            "is_terminal": False,
            "color": None,
            "straight_line_distance": math.sqrt((tgt_x - src_x)**2 + (tgt_y - src_y)**2),
            "manual": True,
            "connection_type": connection_type  # для отладки
        }
        self.edges_data.append(new_edge)

        # Draw line
        line = QGraphicsLineItem(src_x, src_y, tgt_x, tgt_y)
        line.setPen(QPen(self.COLOR_EDGE, self.EDGE_WIDTH))
        line.setZValue(1)
        self.scene.addItem(line)
        self.edge_items[key] = line

        # Undo
        self.undo_stack.append(('add_edge', node_a, node_b, new_edge))

        # Обновляем цвета узлов (могли стать подключенными)
        self._update_node_color(node_a)
        self._update_node_color(node_b)

        self.update_status(f"Добавлено ребро: {node_a} — {node_b} [{connection_type}]")
        self.update_statistics()
        return True

    def remove_edge(self, node_a: str, node_b: str) -> bool:
        """Удалить ребро между узлами"""
        key = self._edge_key(node_a, node_b)
        if key not in self.edges:
            self.update_status(f"Ребро не существует: {node_a} — {node_b}")
            return False

        # Remove from set
        self.edges.remove(key)

        # Find and remove from edges_data
        removed_edge = None
        for i, edge in enumerate(self.edges_data):
            if self._edge_key(edge['source'], edge['target']) == key:
                removed_edge = self.edges_data.pop(i)
                break

        # Remove line from scene
        if key in self.edge_items:
            self.scene.removeItem(self.edge_items[key])
            del self.edge_items[key]

        # Undo
        self.undo_stack.append(('remove_edge', node_a, node_b, removed_edge))

        # Обновляем цвета узлов (могли стать изолированными)
        self._update_node_color(node_a)
        self._update_node_color(node_b)

        self.update_status(f"Удалено ребро: {node_a} — {node_b}")
        self.update_statistics()
        return True

    def optimize_edge(self, node_a: str, node_b: str) -> bool:
        """
        Оптимизировать ребро — пересчитать точки соединения по перпендикулярной логике.
        ВАЖНО: Сохраняет направленность (вертикаль/горизонталь) — не меняет ось.
        """
        key = self._edge_key(node_a, node_b)
        if key not in self.edges:
            self.update_status(f"Ребро не существует: {node_a} — {node_b}")
            return False

        # Находим edge_data
        edge_data = None
        edge_idx = None
        for i, e in enumerate(self.edges_data):
            if self._edge_key(e['source'], e['target']) == key:
                edge_data = e
                edge_idx = i
                break

        if edge_data is None:
            return False

        # ИСПРАВЛЕНИЕ: Используем оригинальные source/target из edge_data!
        # _edge_key сортирует узлы, поэтому node_a/node_b могут не соответствовать source/target
        original_source_id = edge_data['source']
        original_target_id = edge_data['target']

        # Сохраняем старые точки для undo
        old_source_point = edge_data.get('source_point', []).copy() if edge_data.get('source_point') else None
        old_target_point = edge_data.get('target_point', []).copy() if edge_data.get('target_point') else None

        # === Определяем текущую ось ребра ===
        required_axis = None
        if old_source_point and old_target_point:
            old_dx = old_target_point[1] - old_source_point[1]  # [y, x] формат
            old_dy = old_target_point[0] - old_source_point[0]
            _, required_axis = global_axis_perpendicularity(old_dx, old_dy)

        # Вычисляем новые точки (используем логику из add_edge)
        # ИСПРАВЛЕНО: используем original_source_id/original_target_id вместо node_a/node_b
        src = self.nodes[original_source_id]
        tgt = self.nodes[original_target_id]

        src_cx, src_cy = src['centroid'][1], src['centroid'][0]
        tgt_cx, tgt_cy = tgt['centroid'][1], tgt['centroid'][0]

        src_bbox = src.get('bbox')
        tgt_bbox = tgt.get('bbox')
        src_poly = src.get('segmentation')
        tgt_poly = tgt.get('segmentation')

        src_has_bbox = src_bbox and len(src_bbox) == 4
        tgt_has_bbox = tgt_bbox and len(tgt_bbox) == 4
        src_has_poly = src_poly and isinstance(src_poly, list) and len(src_poly) >= 6
        tgt_has_poly = tgt_poly and isinstance(tgt_poly, list) and len(tgt_poly) >= 6

        src_type = src.get('type', 'connector')
        tgt_type = tgt.get('type', 'connector')
        src_is_point = src_type == 'connector' and not src_has_bbox and not src_has_poly
        tgt_is_point = tgt_type == 'connector' and not tgt_has_bbox and not tgt_has_poly

        src_x, src_y, tgt_x, tgt_y = None, None, None, None

        # Аналогичная логика как в add_edge, но с required_axis
        if src_is_point and tgt_is_point:
            src_x, src_y = src_cx, src_cy
            tgt_x, tgt_y = tgt_cx, tgt_cy
        elif src_is_point:
            if tgt_has_poly:
                (src_x, src_y), (tgt_x, tgt_y), _ = connect_point_polygon((src_cx, src_cy), tgt_poly, required_axis)
            elif tgt_has_bbox:
                (src_x, src_y), (tgt_x, tgt_y), _ = connect_point_bbox((src_cx, src_cy), tgt_bbox, required_axis)
        elif tgt_is_point:
            if src_has_poly:
                (tgt_x, tgt_y), (src_x, src_y), _ = connect_point_polygon((tgt_cx, tgt_cy), src_poly, required_axis)
            elif src_has_bbox:
                (tgt_x, tgt_y), (src_x, src_y), _ = connect_point_bbox((tgt_cx, tgt_cy), src_bbox, required_axis)
        elif src_has_bbox and tgt_has_bbox and not src_has_poly and not tgt_has_poly:
            (src_x, src_y), (tgt_x, tgt_y), _ = connect_bbox_bbox(src_bbox, tgt_bbox, required_axis)
        elif src_has_bbox and tgt_has_poly:
            (src_x, src_y), (tgt_x, tgt_y), _ = connect_bbox_polygon(src_bbox, tgt_poly, required_axis)
        elif src_has_poly and tgt_has_bbox:
            (tgt_x, tgt_y), (src_x, src_y), _ = connect_bbox_polygon(tgt_bbox, src_poly, required_axis)
        elif src_has_poly and tgt_has_poly:
            (src_x, src_y), (tgt_x, tgt_y), _ = connect_polygon_polygon(src_poly, tgt_poly, required_axis)
        elif src_has_bbox and tgt_has_bbox:
            (src_x, src_y), (tgt_x, tgt_y), _ = connect_bbox_bbox(src_bbox, tgt_bbox, required_axis)

        if src_x is None:
            # ИСПРАВЛЕНО: используем original_source_id/original_target_id
            src_x, src_y = self.get_connection_point(original_source_id, tgt_cx, tgt_cy)
            tgt_x, tgt_y = self.get_connection_point(original_target_id, src_cx, src_cy)

        # Обновляем данные
        edge_data['source_point'] = [src_y, src_x]
        edge_data['target_point'] = [tgt_y, tgt_x]

        # Перерисовываем линию
        if key in self.edge_items:
            self.scene.removeItem(self.edge_items[key])

        # Пересчитываем перпендикулярность
        # ИСПРАВЛЕНО: используем original_source_id/original_target_id
        source_geom = self._get_node_geometry(original_source_id)
        target_geom = self._get_node_geometry(original_target_id)
        perp_info = compute_edge_perpendicularity((src_x, src_y), (tgt_x, tgt_y), source_geom, target_geom)
        self.edge_perp_scores[key] = perp_info

        # Выбираем цвет
        if self.show_bad_edges and not perp_info['is_good']:
            pen = QPen(self.COLOR_EDGE_BAD, self.EDGE_WIDTH + 1)
        else:
            pen = QPen(self.COLOR_EDGE, self.EDGE_WIDTH)

        line = QGraphicsLineItem(src_x, src_y, tgt_x, tgt_y)
        line.setPen(pen)
        line.setZValue(1)
        self.scene.addItem(line)
        self.edge_items[key] = line

        # Undo - ИСПРАВЛЕНО: сохраняем original_source_id/original_target_id
        self.undo_stack.append(('optimize_edge', original_source_id, original_target_id, old_source_point, old_target_point))

        axis_str = f" [{required_axis}]" if required_axis else ""
        self.update_status(f"Оптимизировано: {original_source_id} — {original_target_id} (score: {perp_info['score']:.2f}){axis_str}")
        return True

    def optimize_all_edges(self) -> int:
        """
        Оптимизировать все неперпендикулярные рёбра.
        Returns: количество оптимизированных рёбер
        """
        optimized = 0
        edges_to_optimize = []

        # Собираем список плохих рёбер
        for key, perp_info in self.edge_perp_scores.items():
            if not perp_info['is_good']:
                edges_to_optimize.append(key)

        # Оптимизируем
        for node_a, node_b in edges_to_optimize:
            if self.optimize_edge(node_a, node_b):
                optimized += 1

        self.update_status(f"Оптимизировано {optimized} рёбер из {len(edges_to_optimize)}")
        self.update_statistics()
        return optimized

    def get_perpendicularity_stats(self) -> dict:
        """Получить статистику перпендикулярности."""
        total = len(self.edge_perp_scores)
        good = sum(1 for info in self.edge_perp_scores.values() if info['is_good'])
        bad = total - good

        if total > 0:
            avg_score = sum(info['score'] for info in self.edge_perp_scores.values()) / total
        else:
            avg_score = 1.0

        return {
            'total': total,
            'good': good,
            'bad': bad,
            'avg_score': avg_score
        }

    def undo(self):
        """Отмена последнего действия"""
        if not self.undo_stack:
            self.update_status("Нечего отменять")
            return

        action = self.undo_stack.pop()

        if action[0] == 'add_edge':
            _, node_a, node_b, edge_data = action
            key = self._edge_key(node_a, node_b)

            # Remove edge
            self.edges.discard(key)
            if edge_data in self.edges_data:
                self.edges_data.remove(edge_data)

            if key in self.edge_items:
                self.scene.removeItem(self.edge_items[key])
                del self.edge_items[key]

            # Обновляем цвета узлов
            self._update_node_color(node_a)
            self._update_node_color(node_b)

            self.update_status(f"Undo: удалено ребро {node_a} — {node_b}")

        elif action[0] == 'remove_edge':
            _, node_a, node_b, edge_data = action
            key = self._edge_key(node_a, node_b)

            # Restore edge
            self.edges.add(key)
            if edge_data:
                self.edges_data.append(edge_data)

            # Redraw line using saved points
            sp = edge_data.get('source_point') if edge_data else None
            tp = edge_data.get('target_point') if edge_data else None

            if sp and tp:
                x1, y1 = sp[1], sp[0]
                x2, y2 = tp[1], tp[0]
            else:
                # Fallback: вычисляем на границах
                src = self.nodes[node_a]
                tgt = self.nodes[node_b]
                tgt_cx, tgt_cy = tgt['centroid'][1], tgt['centroid'][0]
                x1, y1 = self.get_connection_point(node_a, tgt_cx, tgt_cy)
                src_cx, src_cy = src['centroid'][1], src['centroid'][0]
                x2, y2 = self.get_connection_point(node_b, src_cx, src_cy)

            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(QPen(self.COLOR_EDGE, self.EDGE_WIDTH))
            line.setZValue(1)
            self.scene.addItem(line)
            self.edge_items[key] = line

            # Обновляем цвета узлов
            self._update_node_color(node_a)
            self._update_node_color(node_b)

            self.update_status(f"Undo: восстановлено ребро {node_a} — {node_b}")

        elif action[0] == 'add_connector_on_edge':
            # Undo: удаляем коннектор и восстанавливаем исходное ребро
            _, new_node_id, node_a, node_b, old_edge_data = action

            # Удаляем два новых ребра
            for other in [node_a, node_b]:
                key = self._edge_key(new_node_id, other)
                self.edges.discard(key)
                if key in self.edge_items:
                    self.scene.removeItem(self.edge_items[key])
                    del self.edge_items[key]
                self.edges_data = [e for e in self.edges_data
                                  if self._edge_key(e['source'], e['target']) != key]

            # Удаляем коннектор
            if new_node_id in self.node_items:
                self.scene.removeItem(self.node_items[new_node_id])
                del self.node_items[new_node_id]
            self.nodes.pop(new_node_id, None)
            self.graph_data['nodes'] = [n for n in self.graph_data.get('nodes', [])
                                        if n['id'] != new_node_id]

            # Восстанавливаем исходное ребро
            if old_edge_data:
                key = self._edge_key(node_a, node_b)
                self.edges.add(key)
                self.edges_data.append(old_edge_data)

                # Рисуем восстановленное ребро
                sp = old_edge_data.get('source_point')
                tp = old_edge_data.get('target_point')
                if sp and tp:
                    x1, y1 = sp[1], sp[0]
                    x2, y2 = tp[1], tp[0]
                else:
                    # Fallback: вычисляем на границах
                    src = self.nodes[node_a]
                    tgt = self.nodes[node_b]
                    tgt_cx, tgt_cy = tgt['centroid'][1], tgt['centroid'][0]
                    x1, y1 = self.get_connection_point(node_a, tgt_cx, tgt_cy)
                    src_cx, src_cy = src['centroid'][1], src['centroid'][0]
                    x2, y2 = self.get_connection_point(node_b, src_cx, src_cy)

                line = QGraphicsLineItem(x1, y1, x2, y2)
                line.setPen(QPen(self.COLOR_EDGE, self.EDGE_WIDTH))
                line.setZValue(1)
                self.scene.addItem(line)
                self.edge_items[key] = line

            self.update_status(f"Undo: удалён коннектор {new_node_id}")

        elif action[0] == 'add_connector_isolated':
            _, new_node_id = action

            # Удаляем коннектор
            if new_node_id in self.node_items:
                self.scene.removeItem(self.node_items[new_node_id])
                del self.node_items[new_node_id]
            self.nodes.pop(new_node_id, None)
            self.graph_data['nodes'] = [n for n in self.graph_data.get('nodes', [])
                                        if n['id'] != new_node_id]

            self.update_status(f"Undo: удалён изолированный коннектор {new_node_id}")

        elif action[0] == 'delete_node':
            _, node_id, node_backup, edges_data_backup, merged_neighbors, new_edge_data = action

            # Если было склеивание — удаляем созданное ребро
            if merged_neighbors and len(merged_neighbors) == 2 and new_edge_data:
                n1, n2 = merged_neighbors
                key = self._edge_key(n1, n2)
                self.edges.discard(key)
                if key in self.edge_items:
                    self.scene.removeItem(self.edge_items[key])
                    del self.edge_items[key]
                self.edges_data = [e for e in self.edges_data
                                  if self._edge_key(e['source'], e['target']) != key]

            # Восстанавливаем узел
            self.nodes[node_id] = node_backup
            self.graph_data.setdefault('nodes', []).append(node_backup)
            self._draw_single_node(node_id)

            # Восстанавливаем рёбра
            for edge_data in edges_data_backup:
                key = self._edge_key(edge_data['source'], edge_data['target'])
                self.edges.add(key)
                self.edges_data.append(edge_data)

                sp = edge_data.get('source_point')
                tp = edge_data.get('target_point')
                if sp and tp:
                    x1, y1 = sp[1], sp[0]
                    x2, y2 = tp[1], tp[0]
                else:
                    # Fallback: вычисляем на границах
                    src_id = edge_data['source']
                    tgt_id = edge_data['target']
                    src = self.nodes[src_id]
                    tgt = self.nodes[tgt_id]
                    tgt_cx, tgt_cy = tgt['centroid'][1], tgt['centroid'][0]
                    x1, y1 = self.get_connection_point(src_id, tgt_cx, tgt_cy)
                    src_cx, src_cy = src['centroid'][1], src['centroid'][0]
                    x2, y2 = self.get_connection_point(tgt_id, src_cx, src_cy)

                line = QGraphicsLineItem(x1, y1, x2, y2)
                line.setPen(QPen(self.COLOR_EDGE, self.EDGE_WIDTH))
                line.setZValue(1)
                self.scene.addItem(line)
                self.edge_items[key] = line

            # Обновляем цвета
            self._update_node_color(node_id)
            for edge_data in edges_data_backup:
                other = edge_data['source'] if edge_data['target'] == node_id else edge_data['target']
                if other in self.nodes:
                    self._update_node_color(other)

            self.update_status(f"Undo: восстановлен узел {node_id}")

        elif action[0] == 'optimize_edge':
            _, node_a, node_b, old_source_point, old_target_point = action
            key = self._edge_key(node_a, node_b)

            # Восстанавливаем старые точки
            for e in self.edges_data:
                if self._edge_key(e['source'], e['target']) == key:
                    if old_source_point:
                        e['source_point'] = old_source_point
                    if old_target_point:
                        e['target_point'] = old_target_point
                    break

            # Перерисовываем
            if key in self.edge_items:
                self.scene.removeItem(self.edge_items[key])

            if old_source_point and old_target_point:
                x1, y1 = old_source_point[1], old_source_point[0]
                x2, y2 = old_target_point[1], old_target_point[0]
            else:
                src = self.nodes[node_a]
                tgt = self.nodes[node_b]
                x1, y1 = src['centroid'][1], src['centroid'][0]
                x2, y2 = tgt['centroid'][1], tgt['centroid'][0]

            # Пересчитываем перпендикулярность
            source_geom = self._get_node_geometry(node_a)
            target_geom = self._get_node_geometry(node_b)
            perp_info = compute_edge_perpendicularity((x1, y1), (x2, y2), source_geom, target_geom)
            self.edge_perp_scores[key] = perp_info

            if self.show_bad_edges and not perp_info['is_good']:
                pen = QPen(self.COLOR_EDGE_BAD, self.EDGE_WIDTH + 1)
            else:
                pen = QPen(self.COLOR_EDGE, self.EDGE_WIDTH)

            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setZValue(1)
            self.scene.addItem(line)
            self.edge_items[key] = line

            self.update_status(f"Undo: восстановлено ребро {node_a} — {node_b}")

        elif action[0] == 'drag_node':
            _, node_id, old_centroid, old_edge_points = action

            # Восстанавливаем позицию узла
            if node_id in self.nodes:
                node_data = self.nodes[node_id]
                node_data['centroid'] = old_centroid

                old_cx, old_cy = old_centroid[1], old_centroid[0]

                # Перерисовываем узел
                if node_id in self.node_items:
                    self.scene.removeItem(self.node_items[node_id])

                    node_type = node_data.get('type', 'connector')
                    if node_type == 'connector':
                        radius = 8
                        color = self.COLOR_CONNECTOR
                    else:
                        radius = 10
                        color = self.COLOR_EQUIPMENT

                    ellipse = QGraphicsEllipseItem(old_cx - radius, old_cy - radius, radius * 2, radius * 2)
                    ellipse.setBrush(QBrush(color))
                    ellipse.setPen(QPen(Qt.GlobalColor.black, 1))
                    ellipse.setZValue(10)
                    self.scene.addItem(ellipse)
                    self.node_items[node_id] = ellipse

                # Восстанавливаем точки рёбер
                for edge_key, points in old_edge_points.items():
                    na, nb = edge_key
                    key = self._edge_key(na, nb)

                    # Обновляем edge_data
                    for e in self.edges_data:
                        if self._edge_key(e['source'], e['target']) == key:
                            if points.get('source_point'):
                                e['source_point'] = points['source_point']
                            if points.get('target_point'):
                                e['target_point'] = points['target_point']
                            break

                    # Перерисовываем ребро
                    if key in self.edge_items:
                        self.scene.removeItem(self.edge_items[key])

                    sp = points.get('source_point')
                    tp = points.get('target_point')
                    if sp and tp:
                        x1, y1 = sp[1], sp[0]
                        x2, y2 = tp[1], tp[0]

                        # Пересчитываем перпендикулярность
                        source_geom = self._get_node_geometry(na)
                        target_geom = self._get_node_geometry(nb)
                        perp_info = compute_edge_perpendicularity((x1, y1), (x2, y2), source_geom, target_geom)
                        self.edge_perp_scores[key] = perp_info

                        if self.show_bad_edges and not perp_info['is_good']:
                            pen = QPen(self.COLOR_EDGE_BAD, self.EDGE_WIDTH + 1)
                        else:
                            pen = QPen(self.COLOR_EDGE, self.EDGE_WIDTH)

                        line = QGraphicsLineItem(x1, y1, x2, y2)
                        line.setPen(pen)
                        line.setZValue(1)
                        self.scene.addItem(line)
                        self.edge_items[key] = line

                self.update_status(f"Undo: восстановлена позиция {node_id}")

        self.update_statistics()

    def compute_statistics(self) -> dict:
        """Подсчёт статистики графа"""
        if not self.nodes:
            return {'total_nodes': 0, 'total_edges': 0, 'connected': 0, 'isolated': 0}

        # Build adjacency
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        for a, b in self.edges:
            adjacency[a].add(b)
            adjacency[b].add(a)

        # Count isolated (degree = 0)
        isolated = sum(1 for node_id in self.nodes if len(adjacency[node_id]) == 0)
        connected = len(self.nodes) - isolated

        return {
            'total_nodes': len(self.nodes),
            'total_edges': len(self.edges),
            'connected': connected,
            'isolated': isolated
        }

    def update_statistics(self):
        """Обновить отображение статистики"""
        if self.stats_callback:
            stats = self.compute_statistics()
            self.stats_callback(stats)

    def save_graph(self, path: str = "") -> bool:
        """Сохранить изменённый граф"""
        if not self.graph_data:
            self.update_status("Нет данных для сохранения")
            return False

        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить граф", "graph_edited.json", "JSON (*.json)"
            )
            if not path:
                return False

        # Update graph data
        self.graph_data['links'] = self.edges_data
        self.graph_data['graph']['num_edges'] = len(self.edges)

        stats = self.compute_statistics()
        self.graph_data['graph']['num_isolated_nodes'] = stats['isolated']

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.graph_data, f, indent=2, ensure_ascii=False)
            self.update_status(f"Сохранено: {path}")
            return True
        except Exception as e:
            self.update_status(f"Ошибка сохранения: {e}")
            return False

    def set_mode(self, mode: GraphEditorMode):
        """Установить режим редактирования"""
        self.mode = mode
        self.clear_selection()
        mode_names = {
            GraphEditorMode.ADD_EDGE: "Добавление рёбер",
            GraphEditorMode.DELETE_EDGE: "Удаление рёбер",
            GraphEditorMode.ADD_CONNECTOR: "Добавление коннектора",
            GraphEditorMode.DELETE_NODE: "Удаление узла"
        }
        self.update_status(f"Режим: {mode_names.get(mode, str(mode))}")

    def clear_selection(self):
        """Сбросить выбор и все preview элементы"""
        self.selected_node = None
        self.hovered_edge = None

        if self.selection_ring:
            self.scene.removeItem(self.selection_ring)
            self.selection_ring = None
        if self.preview_line:
            self.scene.removeItem(self.preview_line)
            self.preview_line = None
        if self.edge_highlight:
            self.scene.removeItem(self.edge_highlight)
            self.edge_highlight = None
        if self.connector_preview:
            self.scene.removeItem(self.connector_preview)
            self.connector_preview = None

    def select_node(self, node_id: str):
        """Выбрать узел"""
        self.clear_selection()
        self.selected_node = node_id

        node = self.nodes[node_id]
        cx, cy = node['centroid'][1], node['centroid'][0]
        r = self.CLICK_THRESHOLD

        self.selection_ring = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
        self.selection_ring.setPen(QPen(self.COLOR_SELECTION, self.SELECTION_RING_WIDTH))
        self.selection_ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.selection_ring.setZValue(7)
        self.scene.addItem(self.selection_ring)

        self.update_status(f"Выбран: {node_id} ({node.get('class_name', node.get('type'))})")

    def update_hover(self, node_id: str | None):
        """Обновить подсветку при наведении"""
        if node_id == self.hovered_node:
            return

        # Remove old hover
        if self.hover_ring:
            self.scene.removeItem(self.hover_ring)
            self.hover_ring = None

        self.hovered_node = node_id

        if node_id and node_id != self.selected_node:
            node = self.nodes[node_id]
            cx, cy = node['centroid'][1], node['centroid'][0]
            r = self.CLICK_THRESHOLD - 5

            self.hover_ring = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
            self.hover_ring.setPen(QPen(self.COLOR_HOVER, 2, Qt.PenStyle.DashLine))
            self.hover_ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.hover_ring.setZValue(6)
            self.scene.addItem(self.hover_ring)

    def update_preview_line(self, mouse_x: float, mouse_y: float):
        """Обновить preview линию"""
        if not self.selected_node:
            if self.preview_line:
                self.scene.removeItem(self.preview_line)
                self.preview_line = None
            return

        src = self.nodes[self.selected_node]
        x1, y1 = src['centroid'][1], src['centroid'][0]

        # Определяем цвет в зависимости от режима и наличия ребра
        if self.hovered_node and self.hovered_node != self.selected_node:
            tgt = self.nodes[self.hovered_node]
            x2, y2 = tgt['centroid'][1], tgt['centroid'][0]
            edge_exists = self.edge_exists(self.selected_node, self.hovered_node)

            if self.mode == GraphEditorMode.ADD_EDGE:
                color = self.COLOR_PREVIEW_NO if edge_exists else self.COLOR_PREVIEW_OK
            else:  # DELETE
                color = self.COLOR_PREVIEW_DELETE if edge_exists else self.COLOR_PREVIEW_NO

            pen = QPen(color, 3)
        else:
            # Просто тянется к курсору — пунктир
            x2, y2 = mouse_x, mouse_y
            pen = QPen(self.COLOR_SELECTION, 2, Qt.PenStyle.DashLine)

        if self.preview_line:
            self.scene.removeItem(self.preview_line)

        self.preview_line = QGraphicsLineItem(x1, y1, x2, y2)
        self.preview_line.setPen(pen)
        self.preview_line.setZValue(8)
        self.scene.addItem(self.preview_line)

    def update_connector_preview(self, mouse_x: float, mouse_y: float):
        """Обновить preview для режима ADD_CONNECTOR"""
        # Удаляем старые preview элементы
        if self.edge_highlight:
            self.scene.removeItem(self.edge_highlight)
            self.edge_highlight = None
        if self.connector_preview:
            self.scene.removeItem(self.connector_preview)
            self.connector_preview = None

        # Ищем ближайшее ребро
        edge_key, proj_point = self.find_nearest_edge(mouse_x, mouse_y)
        self.hovered_edge = edge_key

        if edge_key and proj_point:
            # Подсвечиваем ребро
            line_item = self.edge_items.get(edge_key)
            if line_item:
                line = line_item.line()
                self.edge_highlight = QGraphicsLineItem(line.x1(), line.y1(), line.x2(), line.y2())
                self.edge_highlight.setPen(QPen(self.COLOR_EDGE_HIGHLIGHT, 4))
                self.edge_highlight.setZValue(4)
                self.scene.addItem(self.edge_highlight)

            # Показываем точку где появится коннектор
            px, py = proj_point
            r = 6
            self.connector_preview = QGraphicsEllipseItem(px - r, py - r, r * 2, r * 2)
            self.connector_preview.setPen(QPen(self.COLOR_CONNECTOR_PREVIEW, 2))
            self.connector_preview.setBrush(QBrush(self.COLOR_CONNECTOR_PREVIEW))
            self.connector_preview.setZValue(5)
            self.scene.addItem(self.connector_preview)
        else:
            # Показываем preview изолированного коннектора
            r = 6
            self.connector_preview = QGraphicsEllipseItem(mouse_x - r, mouse_y - r, r * 2, r * 2)
            self.connector_preview.setPen(QPen(self.COLOR_ISOLATED, 2, Qt.PenStyle.DashLine))
            self.connector_preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.connector_preview.setZValue(5)
            self.scene.addItem(self.connector_preview)

    def update_status(self, msg: str):
        if self.status_callback:
            self.status_callback(msg)

    # === EVENTS ===

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = True
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif event.key() == Qt.Key.Key_Escape:
            self.clear_selection()
            self.update_status("Выбор сброшен")
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
        elif event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.save_graph()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = False
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if self.ctrl_pressed and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.pos())
            x, y = pos.x(), pos.y()

            if self.mode == GraphEditorMode.ADD_CONNECTOR:
                # Режим добавления коннектора
                if self.hovered_edge:
                    # Клик на ребро — разбиваем его
                    _, proj_point = self.find_nearest_edge(x, y)
                    if proj_point:
                        self.add_connector_on_edge(self.hovered_edge, proj_point[0], proj_point[1])
                else:
                    # Клик в пустоту — создаём изолированный коннектор
                    self.add_connector_isolated(x, y)
                self.clear_selection()

            elif self.mode == GraphEditorMode.DELETE_NODE:
                # Режим удаления узла
                clicked_node = self.find_node_at(x, y)
                if clicked_node:
                    self.delete_node(clicked_node)
                else:
                    self.update_status("Узел не найден")

            elif self.mode == GraphEditorMode.OPTIMIZE_EDGE:
                # Режим оптимизации ребра — клик на ребро
                edge_key, _ = self.find_nearest_edge(x, y)
                if edge_key:
                    node_a, node_b = edge_key
                    self.optimize_edge(node_a, node_b)
                else:
                    self.update_status("Ребро не найдено. Кликните на оранжевое ребро.")

            elif self.mode == GraphEditorMode.DRAG_NODE:
                # Режим перетаскивания узла — начинаем drag
                clicked_node = self.find_node_at(x, y)
                if clicked_node:
                    self.start_drag_node(clicked_node)
                else:
                    self.update_status("Узел не найден. Кликните на узел для перетаскивания.")

            elif self.mode in (GraphEditorMode.ADD_EDGE, GraphEditorMode.DELETE_EDGE):
                # Режимы работы с рёбрами
                clicked_node = self.find_node_at(x, y)

                if clicked_node:
                    if self.selected_node is None:
                        # Первый клик — выбираем узел
                        self.select_node(clicked_node)
                    else:
                        # Второй клик — выполняем действие
                        if clicked_node != self.selected_node:
                            if self.mode == GraphEditorMode.ADD_EDGE:
                                self.add_edge(self.selected_node, clicked_node)
                            else:
                                self.remove_edge(self.selected_node, clicked_node)
                        self.clear_selection()
                else:
                    # Клик в пустоту — сброс
                    self.clear_selection()
                    self.update_status("Узел не найден")
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.pos())
        x, y = pos.x(), pos.y()

        # Обработка drag в любом случае если тащим узел
        if self.dragging_node:
            self.drag_node_to(x, y)
            super().mouseMoveEvent(event)
            return

        if self.mode == GraphEditorMode.ADD_CONNECTOR:
            # В режиме добавления коннектора показываем preview
            self.update_connector_preview(x, y)
        elif self.mode == GraphEditorMode.OPTIMIZE_EDGE:
            # В режиме оптимизации подсвечиваем ближайшее ребро
            self.update_optimize_preview(x, y)
        elif self.mode == GraphEditorMode.DRAG_NODE:
            # В режиме drag подсвечиваем узел под курсором
            self.update_drag_preview(x, y)
        else:
            # Очищаем preview коннектора если он был
            if self.edge_highlight:
                self.scene.removeItem(self.edge_highlight)
                self.edge_highlight = None
            if self.connector_preview:
                self.scene.removeItem(self.connector_preview)
                self.connector_preview = None

            # Hover detection для узлов
            hovered = self.find_node_at(x, y)
            self.update_hover(hovered)

            # Preview line для режимов с рёбрами
            if self.selected_node and self.mode in (GraphEditorMode.ADD_EDGE, GraphEditorMode.DELETE_EDGE):
                self.update_preview_line(x, y)

        super().mouseMoveEvent(event)

    def update_optimize_preview(self, mouse_x: float, mouse_y: float):
        """Подсветка ребра для оптимизации."""
        # Очищаем старую подсветку
        if self.edge_highlight:
            self.scene.removeItem(self.edge_highlight)
            self.edge_highlight = None

        edge_key, _ = self.find_nearest_edge(mouse_x, mouse_y, threshold=20.0)

        if edge_key and edge_key in self.edge_items:
            line = self.edge_items[edge_key]
            l = line.line()

            self.edge_highlight = QGraphicsLineItem(l.x1(), l.y1(), l.x2(), l.y2())

            # Цвет зависит от перпендикулярности
            perp_info = self.edge_perp_scores.get(edge_key, {})
            if perp_info.get('is_good', True):
                self.edge_highlight.setPen(QPen(self.COLOR_EDGE, 4))  # Уже хорошее
            else:
                self.edge_highlight.setPen(QPen(self.COLOR_EDGE_HIGHLIGHT, 4))  # Можно оптимизировать

            self.edge_highlight.setZValue(10)
            self.scene.addItem(self.edge_highlight)

            # Показываем информацию
            score = perp_info.get('score', 1.0)
            angle = perp_info.get('source_angle', 0)
            self.update_status(f"Ребро {edge_key[0]}—{edge_key[1]}: ⊥={score:.0%}, отклонение {angle:.1f}°")

    def update_drag_preview(self, mouse_x: float, mouse_y: float):
        """Подсветка узла для перетаскивания."""
        # Очищаем старую подсветку
        if self.connector_preview:
            self.scene.removeItem(self.connector_preview)
            self.connector_preview = None

        hovered = self.find_node_at(mouse_x, mouse_y)

        if hovered:
            node_data = self.nodes.get(hovered)
            if node_data:
                cy, cx = node_data['centroid']

                # Рисуем подсветку
                radius = 15
                self.connector_preview = QGraphicsEllipseItem(
                    cx - radius, cy - radius, radius * 2, radius * 2
                )
                self.connector_preview.setPen(QPen(self.COLOR_EDGE_HIGHLIGHT, 3))
                self.connector_preview.setBrush(QBrush(Qt.GlobalColor.transparent))
                self.connector_preview.setZValue(15)
                self.scene.addItem(self.connector_preview)

                # Показываем информацию
                degree = sum(1 for (a, b) in self.edges if a == hovered or b == hovered)
                node_type = node_data.get('type', 'node')
                self.update_status(f"{node_type} {hovered}: {degree} рёбер. Ctrl+Click и тащите.")
        else:
            self.update_status("Наведите на узел для перетаскивания")

    def start_drag_node(self, node_id: str):
        """Начать перетаскивание узла."""
        if node_id not in self.nodes:
            return

        node_data = self.nodes[node_id]
        self.dragging_node = node_id
        self.drag_start_centroid = node_data['centroid'].copy()

        # Сохраняем точки всех связанных рёбер для undo
        self.drag_start_edge_points = {}
        for (na, nb) in self.edges:
            if na == node_id or nb == node_id:
                key = self._edge_key(na, nb)
                for e in self.edges_data:
                    if self._edge_key(e['source'], e['target']) == key:
                        self.drag_start_edge_points[key] = {
                            'source_point': e.get('source_point', []).copy() if e.get('source_point') else None,
                            'target_point': e.get('target_point', []).copy() if e.get('target_point') else None
                        }
                        break

        self.update_status(f"Перетаскивание: {node_id}")

    def drag_node_to(self, x: float, y: float):
        """Переместить узел в новую позицию и обновить рёбра через connect_* функции."""
        if not self.dragging_node:
            return

        node_id = self.dragging_node
        node_data = self.nodes[node_id]

        # Обновляем centroid
        node_data['centroid'] = [y, x]  # [row, col] формат

        # Перерисовываем узел
        if node_id in self.node_items:
            old_item = self.node_items[node_id]
            self.scene.removeItem(old_item)

            node_type = node_data.get('type', 'connector')
            if node_type == 'connector':
                radius = 8
                color = self.COLOR_CONNECTOR
            else:
                radius = 10
                color = self.COLOR_EQUIPMENT

            ellipse = QGraphicsEllipseItem(x - radius, y - radius, radius * 2, radius * 2)
            ellipse.setBrush(QBrush(color))
            ellipse.setPen(QPen(Qt.GlobalColor.black, 1))
            ellipse.setZValue(10)
            self.scene.addItem(ellipse)
            self.node_items[node_id] = ellipse

        # Обновляем все связанные рёбра через connect_* функции
        for e in self.edges_data:
            edge_src_id = e['source']
            edge_tgt_id = e['target']

            # Проверяем что это ребро связано с перетаскиваемым узлом
            if edge_src_id != node_id and edge_tgt_id != node_id:
                continue

            key = self._edge_key(edge_src_id, edge_tgt_id)

            # Получаем данные обоих узлов (используем порядок из edges_data!)
            src = self.nodes[edge_src_id]
            tgt = self.nodes[edge_tgt_id]

            src_cx, src_cy = src['centroid'][1], src['centroid'][0]
            tgt_cx, tgt_cy = tgt['centroid'][1], tgt['centroid'][0]

            src_bbox = src.get('bbox')
            tgt_bbox = tgt.get('bbox')
            src_poly = src.get('segmentation')
            tgt_poly = tgt.get('segmentation')

            src_has_bbox = src_bbox and len(src_bbox) == 4
            tgt_has_bbox = tgt_bbox and len(tgt_bbox) == 4
            src_has_poly = src_poly and isinstance(src_poly, list) and len(src_poly) >= 6
            tgt_has_poly = tgt_poly and isinstance(tgt_poly, list) and len(tgt_poly) >= 6

            # Коннектор — всегда точка (используем центроид)
            src_type = src.get('type', 'connector')
            tgt_type = tgt.get('type', 'connector')
            src_is_connector = src_type == 'connector'
            tgt_is_connector = tgt_type == 'connector'

            src_x, src_y, tgt_x, tgt_y = None, None, None, None

            # Вызываем соответствующую connect_* функцию
            if src_is_connector and tgt_is_connector:
                # Оба коннектора — просто соединяем центроиды
                src_x, src_y = src_cx, src_cy
                tgt_x, tgt_y = tgt_cx, tgt_cy
            elif src_is_connector:
                # Source — коннектор, target — оборудование
                if tgt_has_poly:
                    (src_x, src_y), (tgt_x, tgt_y), _ = connect_point_polygon((src_cx, src_cy), tgt_poly)
                elif tgt_has_bbox:
                    (src_x, src_y), (tgt_x, tgt_y), _ = connect_point_bbox((src_cx, src_cy), tgt_bbox)
                else:
                    src_x, src_y = src_cx, src_cy
                    tgt_x, tgt_y = tgt_cx, tgt_cy
            elif tgt_is_connector:
                # Target — коннектор, source — оборудование
                if src_has_poly:
                    (tgt_x, tgt_y), (src_x, src_y), _ = connect_point_polygon((tgt_cx, tgt_cy), src_poly)
                elif src_has_bbox:
                    (tgt_x, tgt_y), (src_x, src_y), _ = connect_point_bbox((tgt_cx, tgt_cy), src_bbox)
                else:
                    src_x, src_y = src_cx, src_cy
                    tgt_x, tgt_y = tgt_cx, tgt_cy
            elif src_has_poly and tgt_has_poly:
                (src_x, src_y), (tgt_x, tgt_y), _ = connect_polygon_polygon(src_poly, tgt_poly)
            elif src_has_poly and tgt_has_bbox:
                (tgt_x, tgt_y), (src_x, src_y), _ = connect_bbox_polygon(tgt_bbox, src_poly)
            elif src_has_bbox and tgt_has_poly:
                (src_x, src_y), (tgt_x, tgt_y), _ = connect_bbox_polygon(src_bbox, tgt_poly)
            elif src_has_bbox and tgt_has_bbox:
                (src_x, src_y), (tgt_x, tgt_y), _ = connect_bbox_bbox(src_bbox, tgt_bbox)

            if src_x is None:
                src_x, src_y = src_cx, src_cy
                tgt_x, tgt_y = tgt_cx, tgt_cy

            # Обновляем edge_data
            e['source_point'] = [src_y, src_x]
            e['target_point'] = [tgt_y, tgt_x]

            # Перерисовываем ребро
            if key in self.edge_items:
                self.scene.removeItem(self.edge_items[key])

            # Пересчитываем перпендикулярность
            source_geom = self._get_node_geometry(edge_src_id)
            target_geom = self._get_node_geometry(edge_tgt_id)
            perp_info = compute_edge_perpendicularity((src_x, src_y), (tgt_x, tgt_y), source_geom, target_geom)
            self.edge_perp_scores[key] = perp_info

            # Цвет по перпендикулярности
            if self.show_bad_edges and not perp_info['is_good']:
                pen = QPen(self.COLOR_EDGE_BAD, self.EDGE_WIDTH + 1)
            else:
                pen = QPen(self.COLOR_EDGE, self.EDGE_WIDTH)

            line = QGraphicsLineItem(src_x, src_y, tgt_x, tgt_y)
            line.setPen(pen)
            line.setZValue(1)
            self.scene.addItem(line)
            self.edge_items[key] = line

        # Показываем статус
        self.update_statistics()

    def end_drag_node(self):
        """Завершить перетаскивание и сохранить для undo."""
        if not self.dragging_node:
            return

        node_id = self.dragging_node
        node_data = self.nodes.get(node_id)

        if node_data and self.drag_start_centroid:
            new_centroid = node_data['centroid']
            dx = new_centroid[1] - self.drag_start_centroid[1]
            dy = new_centroid[0] - self.drag_start_centroid[0]

            # Сохраняем для undo
            self.undo_stack.append(('drag_node', node_id, self.drag_start_centroid,
                                   self.drag_start_edge_points.copy()))

            self.update_status(f"Перемещён: {node_id} (Δx={dx:.1f}, Δy={dy:.1f})")

        self.dragging_node = None
        self.drag_start_centroid = None
        self.drag_start_edge_points = {}

    def mouseReleaseEvent(self, event):
        """Обработка отпускания кнопки мыши."""
        if self.dragging_node:
            self.end_drag_node()
        super().mouseReleaseEvent(event)


# =====================================================================
# MAIN WINDOW WITH TABS
# =====================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("P&ID Pipeline Prototype")
        self.setMinimumSize(1400, 900)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # === TAB 1: CVAT ===
        self.setup_cvat_tab()

        # === TAB 2: Square Mask Editor ===
        self.setup_square_editor_tab()

        # === TAB 3: Polyline Mask Editor ===
        self.setup_polyline_editor_tab()

        # === TAB 4: Graph Validator ===
        self.setup_graph_validator_tab()

        # Status bar
        self.statusBar().showMessage("Готово")

    # ==================== TAB 1: CVAT ====================

    def setup_cvat_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        btn_refresh = QPushButton("🔄 Обновить")
        btn_refresh.clicked.connect(lambda: self.browser.reload())
        toolbar.addWidget(btn_refresh)

        btn_open_external = QPushButton("🌐 Открыть в браузере")
        btn_open_external.clicked.connect(self.open_cvat_external)
        toolbar.addWidget(btn_open_external)

        self.cvat_url_label = QLabel("URL: http://localhost:8080")
        toolbar.addWidget(self.cvat_url_label)

        toolbar.addStretch()

        btn_done = QPushButton("✅ Валидация завершена")
        btn_done.clicked.connect(lambda: self.statusBar().showMessage("Валидация CVAT завершена"))
        toolbar.addWidget(btn_done)

        layout.addLayout(toolbar)

        # Browser with optimizations
        from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile

        self.browser = QWebEngineView()

        # Optimize WebEngine settings
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, False)  # Disable smooth scroll
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)

        # Use separate profile with cache
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        profile.setHttpCacheMaximumSize(500 * 1024 * 1024)  # 500MB cache

        self.browser.setUrl(QUrl("http://localhost:8080"))
        layout.addWidget(self.browser)

        self.tabs.addTab(tab, "📦 CVAT — Bbox/Полигоны")

    def open_cvat_external(self):
        """Open CVAT in system browser for better performance"""
        import webbrowser
        webbrowser.open("http://localhost:8080")
        self.statusBar().showMessage("CVAT открыт в системном браузере")

    # ==================== TAB 2: Square Editor ====================

    def setup_square_editor_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        btn_load = QPushButton("📂 Загрузить")
        btn_load.clicked.connect(self.load_square_images)
        toolbar.addWidget(btn_load)

        self.btn_sq_white = QPushButton("⬜ Белая (1)")
        self.btn_sq_white.setCheckable(True)
        self.btn_sq_white.setChecked(True)
        self.btn_sq_white.clicked.connect(lambda: self.set_square_class(1))
        toolbar.addWidget(self.btn_sq_white)

        self.btn_sq_red = QPushButton("🟥 Красная (2)")
        self.btn_sq_red.setCheckable(True)
        self.btn_sq_red.clicked.connect(lambda: self.set_square_class(2))
        toolbar.addWidget(self.btn_sq_red)

        toolbar.addStretch()

        btn_undo = QPushButton("↶ Undo (Ctrl+Z)")
        btn_undo.clicked.connect(lambda: self.square_editor.undo())
        toolbar.addWidget(btn_undo)

        btn_save = QPushButton("💾 Сохранить (Ctrl+S)")
        btn_save.clicked.connect(lambda: self.square_editor.save_masks())
        toolbar.addWidget(btn_save)

        layout.addLayout(toolbar)

        # Editor
        self.square_editor = SquareMaskEditor()
        self.square_editor.status_callback = self.update_square_status
        layout.addWidget(self.square_editor)

        # Status
        self.square_status = QLabel("Ctrl+клик: ЛКМ=добавить квадрат, ПКМ=удалить | Колесо=зум")
        layout.addWidget(self.square_status)

        self.tabs.addTab(tab, "🎨 Редактор масок (квадраты)")

    def set_square_class(self, cls):
        self.square_editor.current_class = cls
        self.btn_sq_white.setChecked(cls == 1)
        self.btn_sq_red.setChecked(cls == 2)

    def update_square_status(self, msg):
        self.square_status.setText(msg)

    def load_square_images(self):
        original, _ = QFileDialog.getOpenFileName(self, "Original", "", "Images (*.png *.jpg)")
        if not original:
            return

        mask1, _ = QFileDialog.getOpenFileName(self, "Mask 1 (white)", "", "Images (*.png)")
        if not mask1:
            return

        mask2, _ = QFileDialog.getOpenFileName(self, "Mask 2 (red, optional)", "", "Images (*.png)")

        skeleton, _ = QFileDialog.getOpenFileName(self, "Skeleton (green, optional)", "", "Images (*.png)")

        if self.square_editor.load_images(original, mask1, mask2 or "", skeleton or ""):
            self.statusBar().showMessage(f"Загружено: {Path(original).name}")
        else:
            self.statusBar().showMessage("Ошибка загрузки")

    # ==================== TAB 3: Polyline Editor ====================

    def setup_polyline_editor_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        btn_load = QPushButton("📂 Загрузить")
        btn_load.clicked.connect(self.load_polyline_images)
        toolbar.addWidget(btn_load)

        self.btn_poly_polyline = QPushButton("✏️ Полилиния")
        self.btn_poly_polyline.setCheckable(True)
        self.btn_poly_polyline.setChecked(True)
        self.btn_poly_polyline.clicked.connect(lambda: self.set_polyline_tool(PolylineTool.POLYLINE))
        toolbar.addWidget(self.btn_poly_polyline)

        self.btn_poly_eraser = QPushButton("🧹 Ластик")
        self.btn_poly_eraser.setCheckable(True)
        self.btn_poly_eraser.clicked.connect(lambda: self.set_polyline_tool(PolylineTool.ERASER))
        toolbar.addWidget(self.btn_poly_eraser)

        # Button group
        self.poly_tool_group = QButtonGroup()
        self.poly_tool_group.addButton(self.btn_poly_polyline)
        self.poly_tool_group.addButton(self.btn_poly_eraser)

        toolbar.addSpacing(20)

        # Width slider
        toolbar.addWidget(QLabel("Толщина:"))

        self.poly_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.poly_width_slider.setRange(1, 50)
        self.poly_width_slider.setValue(3)
        self.poly_width_slider.setFixedWidth(150)
        self.poly_width_slider.valueChanged.connect(self.on_poly_width_changed)
        toolbar.addWidget(self.poly_width_slider)

        self.poly_width_label = QLabel("3px")
        self.poly_width_label.setFixedWidth(40)
        toolbar.addWidget(self.poly_width_label)

        toolbar.addStretch()

        btn_undo = QPushButton("↶ Undo (Ctrl+Z)")
        btn_undo.clicked.connect(lambda: self.polyline_editor.undo())
        toolbar.addWidget(btn_undo)

        btn_save = QPushButton("💾 Сохранить (Ctrl+S)")
        btn_save.clicked.connect(lambda: self.polyline_editor.save_mask())
        toolbar.addWidget(btn_save)

        layout.addLayout(toolbar)

        # Editor
        self.polyline_editor = PolylineMaskEditor()
        self.polyline_editor.status_callback = self.update_polyline_status
        layout.addWidget(self.polyline_editor)

        # Status
        self.polyline_status = QLabel("Ctrl+ЛКМ: добавить точку | 2×ЛКМ/ПКМ/Enter: завершить | Escape: отмена")
        layout.addWidget(self.polyline_status)

        self.tabs.addTab(tab, "✏️ Редактор полилиний (трубы)")

    def set_polyline_tool(self, tool: PolylineTool):
        self.polyline_editor.set_tool(tool)
        self.btn_poly_polyline.setChecked(tool == PolylineTool.POLYLINE)
        self.btn_poly_eraser.setChecked(tool == PolylineTool.ERASER)

    def on_poly_width_changed(self, value: int):
        self.poly_width_label.setText(f"{value}px")
        self.polyline_editor.set_line_width(value)

    def update_polyline_status(self, msg):
        self.polyline_status.setText(msg)

    def load_polyline_images(self):
        original, _ = QFileDialog.getOpenFileName(self, "Original", "", "Images (*.png *.jpg)")
        if not original:
            return

        mask, _ = QFileDialog.getOpenFileName(self, "Mask (optional)", "", "Images (*.png)")

        coco, _ = QFileDialog.getOpenFileName(self, "COCO annotations (optional, for bbox frames)", "", "JSON (*.json)")

        if self.polyline_editor.load_images_with_coco(original, mask or "", coco or ""):
            coco_info = f" + {len(self.polyline_editor.coco_annotations)} bbox" if self.polyline_editor.coco_annotations else ""
            self.statusBar().showMessage(f"Загружено: {Path(original).name}{coco_info}")
        else:
            self.statusBar().showMessage("Ошибка загрузки")

    # ==================== TAB 4: Graph Validator ====================

    def setup_graph_validator_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        btn_load = QPushButton("📂 Загрузить")
        btn_load.clicked.connect(self.load_graph_data)
        toolbar.addWidget(btn_load)

        toolbar.addSpacing(20)

        self.btn_add_edge = QPushButton("➕ Ребро")
        self.btn_add_edge.setCheckable(True)
        self.btn_add_edge.setChecked(True)
        self.btn_add_edge.clicked.connect(lambda: self.set_graph_mode(GraphEditorMode.ADD_EDGE))
        toolbar.addWidget(self.btn_add_edge)

        self.btn_del_edge = QPushButton("➖ Ребро")
        self.btn_del_edge.setCheckable(True)
        self.btn_del_edge.clicked.connect(lambda: self.set_graph_mode(GraphEditorMode.DELETE_EDGE))
        toolbar.addWidget(self.btn_del_edge)

        self.btn_add_connector = QPushButton("⊕ Коннектор")
        self.btn_add_connector.setCheckable(True)
        self.btn_add_connector.clicked.connect(lambda: self.set_graph_mode(GraphEditorMode.ADD_CONNECTOR))
        toolbar.addWidget(self.btn_add_connector)

        self.btn_del_node = QPushButton("⊖ Узел")
        self.btn_del_node.setCheckable(True)
        self.btn_del_node.clicked.connect(lambda: self.set_graph_mode(GraphEditorMode.DELETE_NODE))
        toolbar.addWidget(self.btn_del_node)

        toolbar.addSpacing(20)

        # === ОПТИМИЗАЦИЯ ПЕРПЕНДИКУЛЯРНОСТИ ===
        self.btn_optimize_edge = QPushButton("📐 Оптимизировать")
        self.btn_optimize_edge.setCheckable(True)
        self.btn_optimize_edge.setToolTip("Клик на оранжевое ребро → оптимизировать перпендикулярность")
        self.btn_optimize_edge.clicked.connect(lambda: self.set_graph_mode(GraphEditorMode.OPTIMIZE_EDGE))
        toolbar.addWidget(self.btn_optimize_edge)

        btn_optimize_all = QPushButton("📐 Все")
        btn_optimize_all.setToolTip("Оптимизировать все неперпендикулярные рёбра")
        btn_optimize_all.clicked.connect(self.optimize_all_edges)
        toolbar.addWidget(btn_optimize_all)

        toolbar.addSpacing(10)

        # === ВЫРАВНИВАНИЕ КОННЕКТОРОВ ===
        self.btn_drag_node = QPushButton("✋ Двигать")
        self.btn_drag_node.setCheckable(True)
        self.btn_drag_node.setToolTip("Перетаскивание узлов. Рёбра станут белыми когда выровняются.")
        self.btn_drag_node.clicked.connect(lambda: self.set_graph_mode(GraphEditorMode.DRAG_NODE))
        toolbar.addWidget(self.btn_drag_node)

        # Button group for exclusive selection
        self.graph_mode_group = QButtonGroup()
        self.graph_mode_group.addButton(self.btn_add_edge)
        self.graph_mode_group.addButton(self.btn_del_edge)
        self.graph_mode_group.addButton(self.btn_add_connector)
        self.graph_mode_group.addButton(self.btn_del_node)
        self.graph_mode_group.addButton(self.btn_optimize_edge)
        self.graph_mode_group.addButton(self.btn_drag_node)

        toolbar.addStretch()

        btn_undo = QPushButton("↶ Undo")
        btn_undo.clicked.connect(lambda: self.graph_editor.undo())
        toolbar.addWidget(btn_undo)

        btn_save = QPushButton("💾 Сохранить")
        btn_save.clicked.connect(lambda: self.graph_editor.save_graph())
        toolbar.addWidget(btn_save)

        layout.addLayout(toolbar)

        # Editor
        self.graph_editor = GraphValidatorEditor()
        self.graph_editor.status_callback = self.update_graph_status
        self.graph_editor.stats_callback = self.update_graph_stats
        layout.addWidget(self.graph_editor)

        # Stats bar
        stats_layout = QHBoxLayout()

        self.graph_stats_label = QLabel("Nodes: — | Edges: — | Connected: — | Isolated: —")
        stats_layout.addWidget(self.graph_stats_label)

        # Статистика перпендикулярности
        self.perp_stats_label = QLabel("⊥: —")
        stats_layout.addWidget(self.perp_stats_label)

        stats_layout.addStretch()

        layout.addLayout(stats_layout)

        # Status
        self.graph_status = QLabel("Ctrl+клик: действие | Escape: сброс | Колесо: зум")
        layout.addWidget(self.graph_status)

        self.tabs.addTab(tab, "🔗 Валидатор графа")

    def set_graph_mode(self, mode: GraphEditorMode):
        self.graph_editor.set_mode(mode)
        self.btn_add_edge.setChecked(mode == GraphEditorMode.ADD_EDGE)
        self.btn_del_edge.setChecked(mode == GraphEditorMode.DELETE_EDGE)
        self.btn_add_connector.setChecked(mode == GraphEditorMode.ADD_CONNECTOR)
        self.btn_del_node.setChecked(mode == GraphEditorMode.DELETE_NODE)
        self.btn_optimize_edge.setChecked(mode == GraphEditorMode.OPTIMIZE_EDGE)
        self.btn_drag_node.setChecked(mode == GraphEditorMode.DRAG_NODE)

    def optimize_all_edges(self):
        """Оптимизировать все неперпендикулярные рёбра."""
        count = self.graph_editor.optimize_all_edges()
        self.update_perp_stats()
        self.statusBar().showMessage(f"Оптимизировано {count} рёбер")

    def update_perp_stats(self):
        """Обновить статистику перпендикулярности."""
        stats = self.graph_editor.get_perpendicularity_stats()
        self.perp_stats_label.setText(
            f"⊥: {stats['good']}/{stats['total']} ({stats['avg_score']:.0%})"
        )

    def update_graph_status(self, msg: str):
        self.graph_status.setText(msg)

    def update_graph_stats(self, stats: dict):
        self.graph_stats_label.setText(
            f"Nodes: {stats['total_nodes']} | "
            f"Edges: {stats['total_edges']} | "
            f"Connected: {stats['connected']} | "
            f"Isolated: {stats['isolated']}"
        )
        # Обновляем статистику перпендикулярности
        self.update_perp_stats()

    def load_graph_data(self):
        # 1. Image
        image_path, _ = QFileDialog.getOpenFileName(
            self, "Изображение P&ID", "", "Images (*.png *.jpg)"
        )
        if not image_path:
            return

        # 2. Graph JSON
        graph_path, _ = QFileDialog.getOpenFileName(
            self, "Граф (JSON)", "", "JSON (*.json)"
        )
        if not graph_path:
            return

        if self.graph_editor.load_data(image_path, graph_path):
            stats = self.graph_editor.compute_statistics()
            self.statusBar().showMessage(
                f"Загружено: {Path(image_path).name} | "
                f"{stats['total_nodes']} узлов, {stats['total_edges']} рёбер"
            )
        else:
            self.statusBar().showMessage("Ошибка загрузки")


# =====================================================================
# MAIN
# =====================================================================

def main():
    # Enable GPU acceleration for WebEngine
    import os
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--enable-gpu-rasterization "
        "--enable-native-gpu-memory-buffers "
        "--enable-accelerated-video-decode "
        "--enable-features=VaapiVideoDecoder "
        "--ignore-gpu-blocklist "
        "--disable-software-rasterizer"
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow, QWidget { background-color: #2b2b2b; color: #fff; }
        QPushButton { 
            background: #3c3c3c; 
            border: 1px solid #555; 
            padding: 6px 12px; 
            border-radius: 4px; 
        }
        QPushButton:hover { background: #4a4a4a; }
        QPushButton:checked { background: #0d6efd; }
        QTabWidget::pane { border: 1px solid #555; }
        QTabBar::tab { 
            background: #3c3c3c; 
            padding: 8px 16px; 
            margin-right: 2px; 
        }
        QTabBar::tab:selected { background: #0d6efd; }
        QLabel { padding: 4px; }
        QSlider::groove:horizontal {
            height: 6px;
            background: #555;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #0d6efd;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()