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
    def pace_inter_chunk() -> None:
        """分块移动间的微步进延迟，模拟真实鼠标 HID 轮询。
        每次 IOCTL 之间插入 0.5–1.5 ms 的硬件 PLL 时钟噪声，
        将 IOCTL 突发打散为均匀事件流——RawInput 时间戳呈对数正态，
        而非固定间隔的 Dirac 峰。延迟极小不影响落地精度。"""
        delay = max(0.00025, random.gauss(0.00085, 0.00022))
        time.sleep(delay)

    @staticmethod
    def generate_step_intervals(
        step_count: int,
        total_duration: float,
        *,
        profile: str = "cursor",
    ) -> list[float]:
        if step_count <= 0:
            return []

        total_duration = max(float(total_duration), 0.0)
        if total_duration <= 0:
            return [0.0] * step_count

        weights: list[float] = []
        for index in range(step_count):
            progress = (index + 0.5) / step_count
            if profile == "drag":
                speed_factor = 1.45 - 0.42 * progress + 0.1 * math.sin(progress * math.pi)
            else:
                speed_factor = 0.7 + 0.95 * math.sin(progress * math.pi)

            speed_factor *= random.uniform(0.94, 1.06)
            weights.append(1.0 / max(speed_factor, 0.18))

        weight_sum = sum(weights)
        if weight_sum <= 0:
            return [total_duration / step_count] * step_count

        unit = total_duration / weight_sum
        return [weight * unit for weight in weights]

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

class ValueNoise1D:
    def __init__(self):
        self.vertices = [random.uniform(-1.0, 1.0) for _ in range(256)]
        
    def _smoothstep(self, t: float) -> float:
        return t * t * (3.0 - 2.0 * t)
        
    def get(self, x: float) -> float:
        xi = int(math.floor(x))
        xf = x - xi
        a = self.vertices[xi % 256]
        b = self.vertices[(xi + 1) % 256]
        return a + self._smoothstep(xf) * (b - a)

    def fractal(self, x: float, octaves: int = 3, persistence: float = 0.5) -> float:
        total = 0.0
        frequency = 1.0
        amplitude = 1.0
        max_value = 0.0
        for _ in range(octaves):
            total += self.get(x * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2.0
        if max_value == 0:
            return 0.0
        return total / max_value

    @staticmethod
    def attach_bionic_curve(kinematics_cls):
        """Helper to inject the bionic curve into HumanKinematics namespace seamlessly."""
        pass

def generate_bionic_curve(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    target_width: float = 30.0,
    duration: float = 0.0,
    *,
    depth: int = 0,
) -> list[tuple[int, int]]:
    """按距离混合直线、弧线、S 形及轴向分段轨迹，使用 Minimum Jerk 时间规划。"""
    start = np.array([float(start_x), float(start_y)])
    target = np.array([float(end_x), float(end_y)])
    delta = target - start
    dist = float(np.linalg.norm(delta))
    if dist < 1.0:
        return [(int(round(start_x)), int(round(start_y))), (int(round(end_x)), int(round(end_y)))]

    if duration > 0:
        f_time = duration
    else:
        a = abs(random.gauss(0.1, 0.02))
        b = abs(random.gauss(0.18, 0.05))
        f_time = a + b * math.log2((dist / target_width) + 1.0)
    actual_target = target.copy()
    is_overshoot = False
    if depth == 0 and dist > 24.0:
        v_avg = dist / f_time
        p_overshoot = 1.0 / (1.0 + math.exp(-(0.008 * v_avg - 0.12 * target_width)))
        if random.random() < p_overshoot:
            is_overshoot = True
            cov = [[target_width**2, 0.0], [0.0, target_width**2]]
            actual_target += np.clip(
                np.random.multivariate_normal([0.0, 0.0], cov), -target_width * 1.2, target_width * 1.2
            )

    if depth > 0:
        weights = (0.7, 0.3, 0.0, 0.0)
    elif dist < 50:
        weights = (0.6, 0.3, 0.1, 0.0)
    elif dist < 150:
        weights = (0.25, 0.45, 0.2, 0.1)
    else:
        weights = (0.15, 0.4, 0.3, 0.15)
    trajectory_type = random.choices(("straight", "arc", "s_curve", "staircase"), weights=weights)[0]
    steps = max(3, int(f_time * 100))
    noise_x, noise_y = ValueNoise1D(), ValueNoise1D()
    max_noise = min(dist * 0.06, 10.0) * random.uniform(0.6, 1.4)
    noise_freq = random.uniform(2.0, 5.0)
    normal = np.array([-delta[1], delta[0]]) / dist

    waypoints = [start, actual_target]
    if trajectory_type == "staircase":
        intermediate = start.copy()
        axis = 0 if random.random() < 0.5 else 1
        intermediate[axis] += (actual_target[axis] - start[axis]) * random.uniform(0.5, 0.9)
        intermediate[1 - axis] += random.uniform(-dist * 0.02, dist * 0.02)
        waypoints.insert(1, intermediate)

    points: list[tuple[int, int]] = []
    for index, (segment_start, segment_end) in enumerate(zip(waypoints, waypoints[1:])):
        segment_delta = segment_end - segment_start
        if trajectory_type == "straight":
            bulge = np.clip(random.uniform(-0.03, 0.03) * dist, -15.0, 15.0)
            ctrl1 = start + delta * random.uniform(0.25, 0.4) + normal * bulge
            ctrl2 = start + delta * random.uniform(0.6, 0.75) + normal * bulge
        elif trajectory_type == "s_curve":
            bulge = min(random.uniform(0.08, 0.18) * dist, 180.0) * random.choice((-1.0, 1.0))
            ctrl1 = start + delta * random.uniform(0.2, 0.4) + normal * bulge
            ctrl2 = start + delta * random.uniform(0.6, 0.8) - normal * bulge * random.uniform(0.6, 1.0)
        elif trajectory_type == "staircase":
            ctrl1 = segment_start + segment_delta * 0.33
            ctrl2 = segment_start + segment_delta * 0.67
        else:
            bulge = np.clip(random.choice((-1.0, 1.0)) * random.uniform(0.05, 0.2) * dist, -200.0, 200.0)
            ctrl1 = start + delta * random.uniform(0.15, 0.4) + normal * bulge * random.uniform(0.6, 1.4)
            ctrl2 = start + delta * random.uniform(0.6, 0.85) + normal * bulge * random.uniform(0.6, 1.4)
        segment_steps = steps if len(waypoints) == 2 else (steps // 2 if index == 0 else steps - steps // 2)
        acc_x, acc_y = 0.0, 0.0
        pos_int_x, pos_int_y = int(segment_start[0]), int(segment_start[1])
        prev_float = segment_start.copy()
        for step in range(segment_steps + 1):
            tau = step / segment_steps
            s_tau = 10.0 * tau**3 - 15.0 * tau**4 + 6.0 * tau**5
            omt = 1.0 - s_tau
            ideal_pos = (
                omt**3 * segment_start + 3.0 * omt**2 * s_tau * ctrl1
                + 3.0 * omt * s_tau**2 * ctrl2 + s_tau**3 * segment_end
            )
            envelope = math.sin(tau * math.pi)
            current_float_pos = ideal_pos + np.array([
                noise_x.fractal(tau * noise_freq, octaves=3) * max_noise * envelope,
                noise_y.fractal(tau * noise_freq, octaves=3) * max_noise * envelope,
            ])
            # 累积相邻浮点坐标的差值，避免逐点截断丢失亚像素位移。
            acc_x += current_float_pos[0] - prev_float[0]
            acc_y += current_float_pos[1] - prev_float[1]
            prev_float = current_float_pos.copy()
            move_x, move_y = math.trunc(acc_x), math.trunc(acc_y)
            acc_x, acc_y = acc_x - move_x, acc_y - move_y
            pos_int_x, pos_int_y = pos_int_x + move_x, pos_int_y + move_y
            points.append((pos_int_x, pos_int_y))

    final_point = (int(round(actual_target[0])), int(round(actual_target[1])))
    if points[-1] != final_point:
        points.append(final_point)
    if is_overshoot:
        correction = generate_bionic_curve(
            *final_point, *target, target_width=max(target_width * 0.4, 2.0), depth=depth + 1
        )
        points.extend(correction[1:] if points[-1] == correction[0] else correction)
    return points


HumanKinematics.generate_bionic_curve = staticmethod(generate_bionic_curve)
