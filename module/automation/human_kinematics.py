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
    """
    绝对仿生的人类运动学轨迹生成算法 (WindMouse + MinJerk + Perlin)
    1. 引入 Remainder Accumulator，防整形截断截断检测 (FFT 频域对抗)。
    2. 使用 Minimum Jerk 进行理想位置坐标主导，替代受力模型的两段积分失控风险。
    3. 引入深度参数 depth 阻断二次修正带来的无限递归过冲。
    """
    start = np.array([float(start_x), float(start_y)])
    target = np.array([float(end_x), float(end_y)])
    delta = target - start
    dist = float(np.linalg.norm(delta))

    if dist < 1.0:
        return [(int(round(start_x)), int(round(start_y))), (int(round(end_x)), int(round(end_y)))]

    # 1. 动态 Fitts 定时预测
    if duration > 0:
        f_time = duration
    else:
        a = abs(random.gauss(0.1, 0.02))
        b = abs(random.gauss(0.18, 0.05))
        f_time = a + b * math.log2((dist / target_width) + 1.0)
    
    # 2. Logistic 过冲测算 (限制递归层深)
    v_avg = dist / f_time
    is_overshoot = False
    actual_target = target.copy()
    
    if depth == 0 and dist > 24.0:
        p_overshoot = 1.0 / (1.0 + math.exp(-(0.01 * v_avg - 0.15 * target_width)))
        if random.random() < p_overshoot:
            is_overshoot = True
            cov = [[target_width**2, 0.0], [0.0, target_width**2]]
            target_delta = np.clip(np.random.multivariate_normal([0.0, 0.0], cov), -target_width * 1.5, target_width * 1.5)
            actual_target += target_delta

    # 3. 驱动核心 (Minimum Jerk + 分形噪音)
    steps = max(3, int(f_time * 100)) # e.g. 100Hz
    
    noise_x = ValueNoise1D()
    noise_y = ValueNoise1D()
    motor_tremor_scale = random.uniform(0.6, 1.4)
    max_noise = min(dist * 0.08, 12.0) * motor_tremor_scale
    
    points: list[tuple[int, int]] = []
    
    # 二维余数累加器 (Remainder Accumulator)
    acc_x, acc_y = 0.0, 0.0
    pos_int_x, pos_int_y = int(start[0]), int(start[1])
    prev_float = start.copy()
    
    # 3. 计算宏观抛物线偏移 (Wrist/Elbow Pivot Arc)
    # 人类手臂移动必然带着弧度，绝不会是完全两点一线的直线序列
    # 计算路线法向量，随机确定外侧鼓包 (最高可偏离直线的 5% - 25%)
    if dist > 0:
        normal = np.array([-delta[1], delta[0]]) / dist
    else:
        normal = np.array([0.0, 1.0])
        
    bulge = random.choice([-1.0, 1.0]) * random.uniform(0.05, 0.25) * dist
    bulge = np.clip(bulge, -250.0, 250.0)
    
    # 随机化两个非对称的控制点位置，打破死板的对称圆弧
    cp1_t = random.uniform(0.1, 0.4)
    cp2_t = random.uniform(0.6, 0.9)
    ctrl1 = start + delta * cp1_t + normal * bulge * random.uniform(0.5, 1.5)
    ctrl2 = start + delta * cp2_t + normal * bulge * random.uniform(0.5, 1.5)

    noise_freq = random.uniform(2.0, 5.0)

    for step in range(steps + 1):
        tau = step / steps
        # Minimum Jerk 掌控物理加速度廓形 (时间规划)
        s_tau = 10.0 * (tau**3) - 15.0 * (tau**4) + 6.0 * (tau**5)
        
        # 三阶 Bezier 赋予空间弧度，且完全拥抱 Minimum Jerk 的时间映射
        omt = 1.0 - s_tau
        ideal_pos = (omt**3) * start + 3.0 * (omt**2) * s_tau * ctrl1 + \
                    3.0 * omt * (s_tau**2) * ctrl2 + (s_tau**3) * actual_target
        
        envelope = math.sin(tau * math.pi)
        nx = noise_x.fractal(tau * noise_freq, octaves=3) * max_noise * envelope
        ny = noise_y.fractal(tau * noise_freq, octaves=3) * max_noise * envelope
        
        current_float_pos = ideal_pos + np.array([nx, ny])
        
        # [极度关键] 必须是帧与帧之间的 Delta (导数)，绝不能是当前游标与目标的 Error，否则构成积分发散放大器！
        step_delta_x = current_float_pos[0] - prev_float[0]
        step_delta_y = current_float_pos[1] - prev_float[1]
        prev_float = current_float_pos.copy()
        
        acc_x += step_delta_x
        acc_y += step_delta_y
        
        if abs(acc_x) >= 1.0:
            move_x = int(math.trunc(acc_x))
            acc_x -= move_x
            pos_int_x += move_x
            
        if abs(acc_y) >= 1.0:
            move_y = int(math.trunc(acc_y))
            acc_y -= move_y
            pos_int_y += move_y
            
        # 必须帧帧推送（哪怕是重合静止像素），才能让驱动执行层感受到“停顿和极慢速”的时序分布！
        points.append((pos_int_x, pos_int_y))
            
    # 中转点收尾：确保无浮点误差偏移
    final_x_int = int(round(actual_target[0]))
    final_y_int = int(round(actual_target[1]))
    if not points or points[-1] != (final_x_int, final_y_int):
        points.append((final_x_int, final_y_int))

    # 4. 二次修正回落
    if is_overshoot and depth == 0:
        corr_points = generate_bionic_curve(
            final_x_int, final_y_int, target[0], target[1], 
            target_width=max(target_width * 0.4, 2.0),
            depth=depth + 1
        )
        if points and corr_points and points[-1] == corr_points[0]:
            points.extend(corr_points[1:])
        else:
            points.extend(corr_points)

    return points

HumanKinematics.generate_bionic_curve = staticmethod(generate_bionic_curve)
