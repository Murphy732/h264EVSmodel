"""
事件检测器模块 - DVS (Dynamic Vision Sensor) 像素级事件检测

本模块实现事件相机的核心功能：检测像素级亮度变化并生成事件。
事件分为ON事件（亮度增加）和OFF事件（亮度减少）。

主要特点：
- 支持对数空间亮度比较（符合人眼感知特性）
- 支持像素级事件检测（DVS模式）
- 支持与前一帧或固定参考帧比较
- 支持不应期(Refractory Period)模拟真实DVS硬件
- 提供区域级事件统计（用于可视化）

使用示例：
    detector = EventDetector(
        threshold=20.0,           # 对数空间阈值
        use_log_space=True,       # 启用对数空间
        compare_with_previous=True, # 与前一帧比较
        refractory_period=0.005   # 5毫秒不应期
    )
    events = detector.detect(frame, frame_idx=1, current_time=0.0)
"""

import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass


@dataclass
class DVSCoordinate:
    """
    DVS坐标事件 - 单个像素级事件

    属性:
        x: 像素X坐标
        y: 像素Y坐标
        event_type: 事件类型 - 'on'(亮度增加) 或 'off'(亮度减少)
    """
    x: int
    y: int
    event_type: str  # 'on' for brightness increase, 'off' for brightness decrease


@dataclass
class EventRegion:
    """
    事件区域 - 连续的事件像素组成的区域

    用于可视化和大尺度事件分析，不用于核心DVS事件传输。

    属性:
        x, y: 区域左上角坐标
        width, height: 区域宽高
        area: 区域面积（像素数）
        mean_intensity: 平均亮度变化强度
        event_type: 事件类型
    """
    x: int
    y: int
    width: int
    height: int
    area: int
    mean_intensity: float
    event_type: str  # 'on' for brightness increase, 'off' for brightness decrease


@dataclass
class EventData:
    """
    事件数据 - 一帧的完整事件检测结果

    包含像素级事件列表、区域信息、可视化掩码等。

    属性:
        frame_idx: 帧序号
        events: DVS像素级事件列表（核心数据）
        regions: 事件区域列表（用于可视化）
        diff_map: 帧差热图（用于可视化）
        binary_mask: 二值掩码（用于可视化）
        has_events: 是否检测到事件
        on_events: ON事件二值掩码
        off_events: OFF事件二值掩码
    """
    frame_idx: int
    events: List[DVSCoordinate]  # DVS-like pixel-level events
    regions: List[EventRegion]
    diff_map: np.ndarray
    binary_mask: np.ndarray
    has_events: bool
    on_events: np.ndarray  # Brightness increase
    off_events: np.ndarray  # Brightness decrease


class EventDetector:
    """
    事件检测器 - 模拟DVS传感器的行为

    检测像素级亮度变化，生成ON/OFF事件。
    支持对数空间比较，符合人眼感知特性（Weber-Fechner定律）。
    支持不应期(Refractory Period)模拟真实DVS硬件行为。

    核心算法：
    1. 将当前帧和参考帧转换到对数空间（可选）
    2. 计算逐像素差值
    3. 检查不应期约束（仅超过不应期的像素才能触发）
    4. 与阈值比较，生成ON/OFF事件
    5. 更新参考帧和最后触发时间

    参数说明：
        threshold: 亮度变化阈值（对数空间，默认20.0）
            - 值越大，检测到的事件越少（只检测大变化）
            - 值越小，检测到的事件越多（检测微小变化）

        min_area: 区域最小面积（用于区域检测，默认50）

        use_adaptive_threshold: 是否使用自适应阈值（默认False）
            - True: 根据局部亮度调整阈值
            - False: 使用固定阈值（DVS模式推荐）

        blur_kernel: 高斯模糊核大小（默认1，即不模糊）
            - 增大可减少噪声，但会损失细节
            - DVS模式建议保持1（不模糊）

        use_log_space: 是否使用对数空间（默认True，推荐）
            - True: 在对数空间比较，符合人眼感知
            - False: 在线性空间比较

        is_dvs_mode: 是否启用DVS模式（默认True）
            - 影响事件检测的精度和输出格式

        compare_with_previous: 与前一帧还是固定参考帧比较（默认True）
            - True: 与前一帧比较（推荐，符合DVS行为）
            - False: 与固定参考帧比较

        refractory_period: 不应期时间（秒，默认0.0）
            - 真实DVS传感器在触发事件后有几分钟的"死区"
            - 设为0表示不启用不应期
            - 推荐值: 0.001-0.01秒（1-10毫秒）
    """

    def __init__(
        self,
        threshold: float = 30.0,
        min_area: int = 50,
        max_area: Optional[int] = None,
        use_adaptive_threshold: bool = True,
        blur_kernel: int = 5,
        use_log_space: bool = True,
        is_dvs_mode: bool = True,
        compare_with_previous: bool = True,
        refractory_period: float = 0.0  # 新增：不应期参数
    ):
        # 事件检测阈值 - 对数空间中亮度变化的最小值
        # 范围: 0-255，建议值: 15-30
        self.threshold = threshold

        # 区域检测参数 - 用于可视化和大尺度分析
        self.min_area = min_area
        self.max_area = max_area

        # 阈值策略
        self.use_adaptive_threshold = use_adaptive_threshold

        # 预处理参数
        self.blur_kernel = blur_kernel

        # 核心模式开关
        self.use_log_space = use_log_space
        self.is_dvs_mode = is_dvs_mode
        self.compare_with_previous = compare_with_previous

        # 不应期参数 - 模拟真实DVS硬件的"死区"
        # 像素触发事件后，需要等待refractory_period秒才能再次触发
        self.refractory_period = refractory_period

        # 参考帧存储
        self.reference_frame: Optional[np.ndarray] = None
        self.previous_frame: Optional[np.ndarray] = None

        # 不应期跟踪矩阵 - 记录每个像素最后触发事件的时间
        # 初始化为全0（所有像素都可以立即触发）
        self.last_event_time: Optional[np.ndarray] = None

        # 模拟时间（秒）- 用于不应期计算
        self.current_sim_time: float = 0.0

    def set_reference(self, frame: np.ndarray):
        """
        手动设置参考帧

        用于强制刷新参考帧，例如场景切换时。
        同时重置不应期跟踪矩阵。

        参数:
            frame: 新的参考帧
        """
        gray = self._preprocess_frame(frame)
        self.reference_frame = gray

        # 重置不应期跟踪矩阵
        h, w = gray.shape
        self.last_event_time = np.zeros((h, w), dtype=np.float64)

    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        帧预处理 - 灰度转换和可选模糊

        处理流程：
        1. 如果是彩色图像，转换为灰度
        2. 如果启用模糊，应用高斯模糊

        参数:
            frame: 输入帧（彩色或灰度）

        返回:
            预处理后的灰度帧
        """
        # 转换为灰度图 - 事件检测基于亮度，不需要颜色信息
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        # 可选的高斯模糊 - 用于降噪（DVS模式建议关闭）
        if self.blur_kernel > 1:
            gray = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)

        return gray

    def detect(self, frame: np.ndarray, frame_idx: int = 0,
               current_time: float = 0.0) -> EventData:
        """
        检测帧中的事件

        核心算法流程：
        1. 预处理帧（灰度转换）
        2. 如果是第一帧，初始化为参考帧
        3. 选择比较对象（前一帧或参考帧）
        4. 转换到对数空间（如果启用）
        5. 计算逐像素差值
        6. 应用不应期约束（可选）
        7. 阈值比较，生成ON/OFF事件
        8. 生成可视化掩码
        9. 更新前一帧和最后触发时间

        参数:
            frame: 输入帧（彩色或灰度）
            frame_idx: 帧序号，用于标识
            current_time: 当前模拟时间（秒），用于不应期计算

        返回:
            EventData对象，包含所有事件信息
        """
        # 更新模拟时间
        self.current_sim_time = current_time

        # 步骤1: 预处理帧
        current_gray = self._preprocess_frame(frame)

        # 步骤2: 初始化第一帧
        # 第一帧没有前一帧可比较，所以设为参考帧并返回空事件
        if self.reference_frame is None:
            self.reference_frame = current_gray
            self.previous_frame = current_gray
            h, w = current_gray.shape
            # 初始化不应期跟踪矩阵
            self.last_event_time = np.zeros((h, w), dtype=np.float64)
            return EventData(
                frame_idx=frame_idx,
                events=[],
                regions=[],
                diff_map=np.zeros_like(current_gray),
                binary_mask=np.zeros_like(current_gray),
                has_events=False,
                on_events=np.zeros((h, w), dtype=np.uint8),
                off_events=np.zeros((h, w), dtype=np.uint8)
            )

        # 步骤3: 选择比较对象
        # compare_with_previous=True: 与前一帧比较（DVS标准行为）
        # compare_with_previous=False: 与固定参考帧比较
        if self.compare_with_previous and self.previous_frame is not None:
            compare_frame = self.previous_frame
        else:
            compare_frame = self.reference_frame

        # 步骤4: 转换到对数空间（如果启用）
        # 对数空间的优势：
        # - 符合人眼感知（Weber-Fechner定律）
        # - 压缩高亮度区域动态范围
        # - 增强低亮度区域细节
        if self.use_log_space:
            # 加1避免log(0)
            log_current = np.log(current_gray.astype(np.float32) + 1)
            log_compare = np.log(compare_frame.astype(np.float32) + 1)
            current_float = log_current
            compare_float = log_compare
        else:
            # 线性空间（不推荐，除非特殊需求）
            current_float = current_gray.astype(np.float32)
            compare_float = compare_frame.astype(np.float32)

        # 步骤5: 计算差值图
        diff_map = cv2.absdiff(current_float, compare_float)
        # 对数空间的差值需要缩放到0-255范围用于可视化
        diff_map = (diff_map * 255).astype(np.uint8) if self.use_log_space else diff_map.astype(np.uint8)

        # 步骤6: 应用不应期约束（可选）
        # 不应期确保像素不会在同一位置连续快速触发
        # 这模拟了真实DVS传感器的硬件特性
        if self.refractory_period > 0 and self.last_event_time is not None:
            # 计算自上次触发以来经过的时间
            time_since_last = self.current_sim_time - self.last_event_time
            # 仅允许超过不应期的像素触发
            time_mask = time_since_last > self.refractory_period
        else:
            # 不启用不应期，所有像素都可以触发
            time_mask = None

        # 步骤7: DVS像素级事件检测
        h, w = current_gray.shape
        dvs_events = []

        # 归一化阈值到对数空间
        # threshold范围是0-255，需要归一化到对数空间的尺度
        threshold_normalized = self.threshold / 255.0

        # 检测ON事件 - 当前帧亮度 > 参考帧亮度 + 阈值
        # 即：亮度增加（例如物体移入、光源变亮）
        on_mask = (current_float > compare_float + threshold_normalized)

        # 应用不应期约束到ON事件
        if time_mask is not None:
            on_mask = on_mask & time_mask

        on_coords = np.argwhere(on_mask)
        for y, x in on_coords:
            dvs_events.append(DVSCoordinate(x=int(x), y=int(y), event_type='on'))

        # 检测OFF事件 - 当前帧亮度 < 参考帧亮度 - 阈值
        # 即：亮度减少（例如物体移出、光源变暗）
        off_mask = (current_float < compare_float - threshold_normalized)

        # 应用不应期约束到OFF事件
        if time_mask is not None:
            off_mask = off_mask & time_mask

        off_coords = np.argwhere(off_mask)
        for y, x in off_coords:
            dvs_events.append(DVSCoordinate(x=int(x), y=int(y), event_type='off'))

        # 更新不应期跟踪矩阵
        if self.refractory_period > 0 and self.last_event_time is not None:
            # ON事件像素更新最后触发时间
            for y, x in on_coords:
                self.last_event_time[y, x] = self.current_sim_time
            # OFF事件像素更新最后触发时间
            for y, x in off_coords:
                self.last_event_time[y, x] = self.current_sim_time

        # 步骤8: 创建可视化掩码
        # ON事件掩码（白色表示有ON事件）
        on_binary = np.zeros((h, w), dtype=np.uint8)
        # OFF事件掩码（白色表示有OFF事件）
        off_binary = np.zeros((h, w), dtype=np.uint8)
        on_binary[on_mask] = 255
        off_binary[off_mask] = 255

        # 合并掩码（用于显示所有事件区域）
        binary_mask = cv2.bitwise_or(on_binary, off_binary)

        # 步骤9: 区域检测（用于可视化，非核心功能）
        # 将连续的事件像素聚类为区域，便于可视化分析
        regions = []

        # 处理ON事件区域
        on_contours, _ = cv2.findContours(
            on_binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in on_contours:
            area = cv2.contourArea(contour)
            # 过滤小区域（噪声）
            if area < self.min_area:
                continue
            # 过滤大区域（异常）
            if self.max_area is not None and area > self.max_area:
                continue

            # 获取区域边界框
            x, y, w_region, h_region = cv2.boundingRect(contour)
            region_diff = diff_map[y:y+h_region, x:x+w_region]
            mean_intensity = float(np.mean(region_diff))

            regions.append(EventRegion(
                x=x, y=y, width=w_region, height=h_region,
                area=int(area), mean_intensity=mean_intensity,
                event_type='on'
            ))

        # 处理OFF事件区域
        off_contours, _ = cv2.findContours(
            off_binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in off_contours:
            area = cv2.contourArea(contour)
            if area < self.min_area:
                continue
            if self.max_area is not None and area > self.max_area:
                continue

            x, y, w_region, h_region = cv2.boundingRect(contour)
            region_diff = diff_map[y:y+h_region, x:x+w_region]
            mean_intensity = float(np.mean(region_diff))

            regions.append(EventRegion(
                x=x, y=y, width=w_region, height=h_region,
                area=int(area), mean_intensity=mean_intensity,
                event_type='off'
            ))

        # 按面积排序，大的区域在前
        regions.sort(key=lambda r: r.area, reverse=True)

        # 步骤10: 更新前一帧（用于下一次比较）
        self.previous_frame = current_gray.copy()

        # 返回完整的事件数据
        return EventData(
            frame_idx=frame_idx,
            events=dvs_events,
            regions=regions,
            diff_map=diff_map,
            binary_mask=binary_mask,
            has_events=len(dvs_events) > 0,
            on_events=on_binary,
            off_events=off_binary
        )

    def update_reference(self, frame: np.ndarray):
        """
        更新参考帧并重置前一帧

        通常在发送关键帧后调用，确保事件检测基于最新的参考。
        同时重置不应期跟踪矩阵。

        参数:
            frame: 新的参考帧
        """
        self.reference_frame = self._preprocess_frame(frame)
        self.previous_frame = self.reference_frame.copy()
        # 重置不应期跟踪矩阵
        h, w = self.reference_frame.shape
        self.last_event_time = np.zeros((h, w), dtype=np.float64)

    def get_refractory_stats(self) -> Dict:
        """
        获取不应期统计信息

        返回:
            包含不应期相关统计的字典
        """
        if self.last_event_time is None:
            return {'enabled': False}

        return {
            'enabled': self.refractory_period > 0,
            'refractory_period_ms': self.refractory_period * 1000,
            'active_pixels': int(np.sum(self.last_event_time > 0)),
            'total_pixels': self.last_event_time.size if self.last_event_time is not None else 0
        }


class EventStats:
    """
    事件统计工具 - 提供事件数据的可视化和统计功能

    辅助类，用于生成热图、统计信息等，不直接影响核心事件检测。
    """

    @staticmethod
    def calculate_event_mask(events: EventData) -> np.ndarray:
        """
        计算事件掩码 - 将事件区域填充为白色

        参数:
            events: 事件数据

        返回:
            二值掩码图像
        """
        mask = np.zeros_like(events.diff_map, dtype=np.uint8)
        for region in events.regions:
            cv2.rectangle(
                mask,
                (region.x, region.y),
                (region.x + region.width, region.y + region.height),
                255,
                -1
            )
        return mask

    @staticmethod
    def get_heatmap(diff_map: np.ndarray) -> np.ndarray:
        """
        生成差值热图 - 用于可视化亮度变化强度

        使用JET色彩映射：
        - 蓝色：变化小
        - 绿色：变化中等
        - 红色：变化大

        参数:
            diff_map: 差值图

        返回:
            彩色热图
        """
        normalized = cv2.normalize(diff_map, None, 0, 255, cv2.NORM_MINMAX)
        heatmap = cv2.applyColorMap(normalized.astype(np.uint8), cv2.COLORMAP_JET)
        return heatmap

    @staticmethod
    def summarize(events: EventData) -> Dict:
        """
        汇总事件统计信息

        参数:
            events: 事件数据

        返回:
            统计字典，包含帧号、区域数、总面积、平均强度等
        """
        total_area = sum(r.area for r in events.regions)
        avg_intensity = np.mean([r.mean_intensity for r in events.regions]) if events.regions else 0

        return {
            "frame_idx": events.frame_idx,
            "num_regions": len(events.regions),
            "total_area": total_area,
            "avg_intensity": avg_intensity,
            "has_events": events.has_events
        }
