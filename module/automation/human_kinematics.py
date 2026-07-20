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


class _TrajectoryType:
    """轨迹类型枚举"""
    STRAIGHT = "straight"      # 近似直线
    ARC = "arc"                # 弧线（原有行为）
    S_CURVE = "s_curve"        # S形轨迹（中途调整）
    STAIRCASE = "staircase"    # 阶梯形轨迹（轴对齐移动）


def _select_trajectory_type(dist: float, depth: int) -> str:
    """
    根据距离和深度选择轨迹类型。
    短距离更倾向于直线，长距离允许更多样化的轨迹。
    递归深度 > 0 时倾向于直线以避免修正轨迹过于复杂。
    """
    if depth > 0:
        # 修正轨迹倾向于简单
        return _TrajectoryType.STRAIGHT if random.random() < 0.7 else _TrajectoryType.ARC

    rand = random.random()

    if dist < 50:
        # 短距离：60% 直线，30% 弧线，10% S形
        if rand < 0.60:
            return _TrajectoryType.STRAIGHT
        elif rand < 0.90:
            return _TrajectoryType.ARC
        else:
            return _TrajectoryType.S_CURVE
    elif dist < 150:
        # 中距离：25% 直线，45% 弧线，20% S形，10% 阶梯
        if rand < 0.25:
            return _TrajectoryType.STRAIGHT
        elif rand < 0.70:
            return _TrajectoryType.ARC
        elif rand < 0.90:
            return _TrajectoryType.S_CURVE
        else:
            return _TrajectoryType.STAIRCASE
    else:
        # 长距离：15% 直线，40% 弧线，30% S形，15% 阶梯
        if rand < 0.15:
            return _TrajectoryType.STRAIGHT
        elif rand < 0.55:
            return _TrajectoryType.ARC
        elif rand < 0.85:
            return _TrajectoryType.S_CURVE
        else:
            return _TrajectoryType.STAIRCASE


def _compute_arc_controls(
    start: np.ndarray,
    delta: np.ndarray,
    dist: float,
    normal: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """计算弧线轨迹的控制点（优化后的弧度范围）。"""
    # 弧度范围：5%-20%，比原来的 5%-25% 略微收敛
    bulge = random.choice([-1.0, 1.0]) * random.uniform(0.05, 0.20) * dist
    bulge = np.clip(bulge, -200.0, 200.0)

    cp1_t = random.uniform(0.15, 0.40)
    cp2_t = random.uniform(0.60, 0.85)
    ctrl1 = start + delta * cp1_t + normal * bulge * random.uniform(0.6, 1.4)
    ctrl2 = start + delta * cp2_t + normal * bulge * random.uniform(0.6, 1.4)

    return ctrl1, ctrl2


def _compute_straight_controls(
    start: np.ndarray,
    delta: np.ndarray,
    dist: float,
    normal: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """计算近似直线轨迹的控制点（极小弧度模拟自然抖动）。"""
    # 弧度范围：0%-3%，几乎直线但有轻微自然偏移
    bulge = random.uniform(-0.03, 0.03) * dist
    bulge = np.clip(bulge, -15.0, 15.0)

    cp1_t = random.uniform(0.25, 0.40)
    cp2_t = random.uniform(0.60, 0.75)
    ctrl1 = start + delta * cp1_t + normal * bulge
    ctrl2 = start + delta * cp2_t + normal * bulge

    return ctrl1, ctrl2


def _compute_s_curve_controls(
    start: np.ndarray,
    delta: np.ndarray,
    dist: float,
    normal: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    计算 S 形轨迹的控制点。
    通过让两个控制点向相反方向偏移，形成 S 形曲线。
    """
    # S 形弧度：较大但不过分
    bulge_magnitude = random.uniform(0.08, 0.18) * dist
    bulge_magnitude = np.clip(bulge_magnitude, -180.0, 180.0)

    # 两个控制点向相反方向偏移
    sign = random.choice([-1.0, 1.0])
    cp1_t = random.uniform(0.20, 0.40)
    cp2_t = random.uniform(0.60, 0.80)

    ctrl1 = start + delta * cp1_t + normal * bulge_magnitude * sign
    ctrl2 = start + delta * cp2_t - normal * bulge_magnitude * sign * random.uniform(0.6, 1.0)

    return ctrl1, ctrl2


def _compute_staircase_waypoints(
    start: np.ndarray,
    target: np.ndarray,
    dist: float,
) -> list[np.ndarray]:
    """
    生成阶梯形轨迹的中间途径点。
    模拟人类"先水平后垂直"或"先垂直后水平"的移动习惯。
    """
    waypoints = [start.copy()]

    # 随机选择移动顺序
    horizontal_first = random.random() < 0.5

    delta = target - start

    if horizontal_first:
        # 先水平移动，再垂直移动
        mid_x = start[0] + delta[0] * random.uniform(0.5, 0.9)
        mid_y = start[1]
        # 添加轻微随机偏移
        mid_y += random.uniform(-dist * 0.02, dist * 0.02)
        waypoints.append(np.array([mid_x, mid_y]))
    else:
        # 先垂直移动，再水平移动
        mid_x = start[0]
        mid_y = start[1] + delta[1] * random.uniform(0.5, 0.9)
        mid_x += random.uniform(-dist * 0.02, dist * 0.02)
        waypoints.append(np.array([mid_x, mid_y]))

    waypoints.append(target.copy())
    return waypoints


def _generate_segment_points(
    segment_start: np.ndarray,
    segment_end: np.ndarray,
    steps: int,
    noise_x: ValueNoise1D,
    noise_y: ValueNoise1D,
    max_noise: float,
    noise_freq: float,
    is_final_segment: bool = True,
) -> tuple[list[tuple[int, int]], np.ndarray, float, float, int, int]:
    """
    生成单段轨迹的点序列。
    返回: (点列表, 最终浮点位置, 累加器x, 累加器y, 整数位置x, 整数位置y)
    """
    delta = segment_end - segment_start
    dist = float(np.linalg.norm(delta))

    if dist < 1.0:
        return [], segment_start.copy(), 0.0, 0.0, int(segment_start[0]), int(segment_start[1])

    if dist > 0:
        normal = np.array([-delta[1], delta[0]]) / dist
    else:
        normal = np.array([0.0, 1.0])

    # 使用轻微弧度
    bulge = random.uniform(-0.02, 0.02) * dist
    bulge = np.clip(bulge, -10.0, 10.0)

    ctrl1 = segment_start + delta * 0.3 + normal * bulge
    ctrl2 = segment_start + delta * 0.7 + normal * bulge

    points: list[tuple[int, int]] = []
    acc_x, acc_y = 0.0, 0.0
    pos_int_x, pos_int_y = int(segment_start[0]), int(segment_start[1])
    prev_float = segment_start.copy()

    for step in range(1, steps + 1):
        tau = step / steps

        # Minimum Jerk 时间规划
        s_tau = 10.0 * (tau**3) - 15.0 * (tau**4) + 6.0 * (tau**5)

        # 贝塞尔曲线
        omt = 1.0 - s_tau
        ideal_pos = (
            (omt**3) * segment_start
            + 3.0 * (omt**2) * s_tau * ctrl1
            + 3.0 * omt * (s_tau**2) * ctrl2
            + (s_tau**3) * segment_end
        )

        # 噪声
        envelope = math.sin(tau * math.pi)
        nx = noise_x.fractal(tau * noise_freq, octaves=3) * max_noise * envelope
        ny = noise_y.fractal(tau * noise_freq, octaves=3) * max_noise * envelope

        current_float_pos = ideal_pos + np.array([nx, ny])

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

        points.append((pos_int_x, pos_int_y))

    return points, prev_float, acc_x, acc_y, pos_int_x, pos_int_y


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

    v2.0 优化:
    1. 多样化轨迹类型：直线、弧线、S形、阶梯形，根据距离自适应分布。
    2. 距离自适应策略：短距离更倾向直线，长距离允许更复杂的轨迹。
    3. S形轨迹模拟人类中途调整，阶梯形模拟轴对齐移动习惯。
    4. 保持 Minimum Jerk 时间规划和 Perlin 噪声的核心优势。
    5. 引入深度参数 depth 阻断二次修正带来的无限递归过冲。
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
        # 降低过冲概率，使其更自然
        p_overshoot = 1.0 / (1.0 + math.exp(-(0.008 * v_avg - 0.12 * target_width)))
        if random.random() < p_overshoot:
            is_overshoot = True
            cov = [[target_width**2, 0.0], [0.0, target_width**2]]
            target_delta = np.clip(
                np.random.multivariate_normal([0.0, 0.0], cov),
                -target_width * 1.2,
                target_width * 1.2,
            )
            actual_target += target_delta

    # 3. 轨迹类型选择
    traj_type = _select_trajectory_type(dist, depth)

    # 4. 驱动核心 (Minimum Jerk + 分形噪音)
    steps = max(3, int(f_time * 100))  # 100Hz

    noise_x = ValueNoise1D()
    noise_y = ValueNoise1D()
    motor_tremor_scale = random.uniform(0.6, 1.4)
    max_noise = min(dist * 0.06, 10.0) * motor_tremor_scale  # 略微降低噪声幅度

    points: list[tuple[int, int]] = []

    # 计算法向量
    if dist > 0:
        normal = np.array([-delta[1], delta[0]]) / dist
    else:
        normal = np.array([0.0, 1.0])

    noise_freq = random.uniform(2.0, 5.0)

    if traj_type == _TrajectoryType.STAIRCASE:
        # 阶梯形轨迹：分两段生成
        waypoints = _compute_staircase_waypoints(start, actual_target, dist)

        segment_steps = [int(steps * 0.5), int(steps * 0.5)]
        segment_steps[-1] = steps - sum(segment_steps[:-1])  # 确保总步数正确

        # 第一段
        if len(waypoints) >= 2:
            seg_points, prev_float, acc_x, acc_y, pos_int_x, pos_int_y = _generate_segment_points(
                waypoints[0], waypoints[1], segment_steps[0],
                noise_x, noise_y, max_noise, noise_freq, is_final_segment=False
            )
            points.extend(seg_points)

            # 第二段
            if len(waypoints) >= 3:
                seg_points, _, _, _, _, _ = _generate_segment_points(
                    waypoints[1], waypoints[2], segment_steps[1],
                    noise_x, noise_y, max_noise, noise_freq, is_final_segment=True
                )
                points.extend(seg_points)
    else:
        # 其他轨迹类型：单段贝塞尔曲线
        if traj_type == _TrajectoryType.STRAIGHT:
            ctrl1, ctrl2 = _compute_straight_controls(start, delta, dist, normal)
        elif traj_type == _TrajectoryType.S_CURVE:
            ctrl1, ctrl2 = _compute_s_curve_controls(start, delta, dist, normal)
        else:  # ARC
            ctrl1, ctrl2 = _compute_arc_controls(start, delta, dist, normal)

        # 二维余数累加器 (Remainder Accumulator)
        acc_x, acc_y = 0.0, 0.0
        pos_int_x, pos_int_y = int(start[0]), int(start[1])
        prev_float = start.copy()

        for step in range(steps + 1):
            tau = step / steps
            # Minimum Jerk 掌控物理加速度廓形 (时间规划)
            s_tau = 10.0 * (tau**3) - 15.0 * (tau**4) + 6.0 * (tau**5)

            # 三阶 Bezier 赋予空间弧度，且完全拥抱 Minimum Jerk 的时间映射
            omt = 1.0 - s_tau
            ideal_pos = (
                (omt**3) * start
                + 3.0 * (omt**2) * s_tau * ctrl1
                + 3.0 * omt * (s_tau**2) * ctrl2
                + (s_tau**3) * actual_target
            )

            envelope = math.sin(tau * math.pi)
            nx = noise_x.fractal(tau * noise_freq, octaves=3) * max_noise * envelope
            ny = noise_y.fractal(tau * noise_freq, octaves=3) * max_noise * envelope

            current_float_pos = ideal_pos + np.array([nx, ny])

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
