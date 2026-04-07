import math
import random
import time
from typing import Sequence

import numpy as np


class HumanKinematics:
    """人类运动学鼠标仿真辅助类。"""

    @staticmethod
    def sample_duration(
        base: float,
        jitter: float = 0.2,
        *,
        minimum: float = 0.0,
        maximum: float | None = None,
    ) -> float:
        base = max(float(base), 0.0)
        minimum = max(float(minimum), 0.0)
        if maximum is not None:
            maximum = max(float(maximum), minimum)

        if base <= 0:
            duration = minimum
        else:
            duration = base * random.uniform(max(0.0, 1.0 - jitter), 1.0 + jitter)
            duration = max(duration, minimum)

        if maximum is not None:
            duration = min(duration, maximum)
        return duration

    @staticmethod
    def human_sleep(
        base: float,
        jitter: float = 0.2,
        *,
        minimum: float = 0.0,
        maximum: float | None = None,
    ) -> None:
        """在基础时长上叠加轻微随机扰动，避免固定节奏特征。"""
        time.sleep(HumanKinematics.sample_duration(base, jitter, minimum=minimum, maximum=maximum))

    @staticmethod
    def get_gaussian_click_point(
        center_x: float,
        center_y: float,
        width: float,
        height: float,
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
        margin: int = 2,
    ) -> tuple[int, int]:
        safe_width = max(float(width), 6.0)
        safe_height = max(float(height), 6.0)
        cov = np.array(
            [
                [max((safe_width / 5.0) ** 2, 1.0), 0.0],
                [0.0, max((safe_height / 5.0) ** 2, 1.0)],
            ]
        )
        min_x = center_x - safe_width / 2.0 + margin
        max_x = center_x + safe_width / 2.0 - margin
        min_y = center_y - safe_height / 2.0 + margin
        max_y = center_y + safe_height / 2.0 - margin

        if screen_width is not None:
            min_x = max(0.0, min_x)
            max_x = min(float(screen_width - 1), max_x)
        if screen_height is not None:
            min_y = max(0.0, min_y)
            max_y = min(float(screen_height - 1), max_y)

        if min_x > max_x:
            min_x = max_x = float(round(center_x))
        if min_y > max_y:
            min_y = max_y = float(round(center_y))

        target_x = center_x
        target_y = center_y
        for _ in range(8):
            point = np.random.multivariate_normal(mean=[center_x, center_y], cov=cov)
            target_x = float(np.clip(point[0], min_x, max_x))
            target_y = float(np.clip(point[1], min_y, max_y))
            if round(target_x) != round(center_x) or round(target_y) != round(center_y):
                break
        else:
            target_x += random.choice((-1, 1)) * min(max(safe_width / 6.0, 1.0), 3.0)
            target_y += random.choice((-1, 1)) * min(max(safe_height / 6.0, 1.0), 3.0)
            target_x = float(np.clip(target_x, min_x, max_x))
            target_y = float(np.clip(target_y, min_y, max_y))

        return int(round(target_x)), int(round(target_y))

    @staticmethod
    def _cubic_bezier(
        start: np.ndarray,
        control1: np.ndarray,
        control2: np.ndarray,
        end: np.ndarray,
        progress: float,
    ) -> np.ndarray:
        inverse = 1.0 - progress
        return (
            (inverse ** 3) * start
            + 3.0 * (inverse ** 2) * progress * control1
            + 3.0 * inverse * (progress ** 2) * control2
            + (progress ** 3) * end
        )

    @staticmethod
    def _deduplicate_points(points: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
        unique_points: list[tuple[int, int]] = []
        for point in points:
            if not unique_points or point != unique_points[-1]:
                unique_points.append(point)
        return unique_points

    @staticmethod
    def generate_human_curve(
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        num_points: int = 50,
        allow_overshoot: bool = True,
        allow_micro_jitter: bool = True,
    ) -> list[tuple[int, int]]:
        start = np.array([float(start_x), float(start_y)])
        end = np.array([float(end_x), float(end_y)])
        delta = end - start
        distance = float(np.linalg.norm(delta))

        if distance == 0:
            return [(int(end_x), int(end_y))]

        direction = delta / distance
        normal = np.array([-direction[1], direction[0]])

        curve_strength = min(max(distance * 0.12, 8.0), 64.0)
        control1 = (
            start
            + delta * random.uniform(0.18, 0.32)
            + normal * curve_strength * random.uniform(-0.65, 0.65)
        )
        control2 = (
            start
            + delta * random.uniform(0.68, 0.84)
            + normal * curve_strength * random.uniform(-0.45, 0.45)
        )

        overshoot = end.copy()
        if allow_overshoot and distance >= 48 and random.random() < 0.7:
            overshoot_distance = min(max(distance * 0.018, 2.0), 14.0)
            overshoot = (
                end
                + direction * overshoot_distance
                + normal * random.uniform(-overshoot_distance * 0.5, overshoot_distance * 0.5)
            )

        points: list[tuple[int, int]] = []
        total_points = max(2, num_points)
        jitter_scale = min(1.6, 0.25 + distance / 500.0)
        for t in np.linspace(0.0, 1.0, total_points):
            eased_t = math.sin(t * math.pi / 2.0)
            point = HumanKinematics._cubic_bezier(start, control1, control2, overshoot, eased_t)
            if allow_micro_jitter and distance >= 24:
                envelope = math.sin(t * math.pi) ** 1.5
                point += np.array(
                    [
                        random.gauss(0.0, jitter_scale * envelope),
                        random.gauss(0.0, jitter_scale * envelope),
                    ]
                )
            points.append((int(round(point[0])), int(round(point[1]))))

        if not np.allclose(overshoot, end):
            correction_steps = max(3, min(7, int(distance / 120.0) + 3))
            for t in np.linspace(0.0, 1.0, correction_steps):
                point = overshoot + (end - overshoot) * t
                points.append((int(round(point[0])), int(round(point[1]))))

        points = HumanKinematics._deduplicate_points(points)
        final_point = (int(end_x), int(end_y))
        if points[-1] != final_point:
            points.append(final_point)
        return points
