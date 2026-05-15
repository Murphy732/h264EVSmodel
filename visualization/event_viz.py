import cv2
import numpy as np
from typing import Optional, Tuple
from evs.event_detector import EventData, EventRegion


class EventVisualizer:
    @staticmethod
    def draw_regions(
        frame: np.ndarray,
        events: EventData,
        thickness: int = 2
    ) -> np.ndarray:
        result = frame.copy()
        for region in events.regions:
            color = (0, 0, 255) if region.event_type == 'on' else (0, 255, 0)
            cv2.rectangle(
                result,
                (region.x, region.y),
                (region.x + region.width, region.y + region.height),
                color,
                thickness
            )
        return result

    @staticmethod
    def draw_heatmap_overlay(
        frame: np.ndarray,
        events: EventData,
        alpha: float = 0.5
    ) -> np.ndarray:
        from evs.event_detector import EventStats

        heatmap = EventStats.get_heatmap(events.diff_map)

        if len(frame.shape) == 2:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        else:
            frame_rgb = frame.copy()

        if heatmap.shape[:2] != frame_rgb.shape[:2]:
            heatmap = cv2.resize(heatmap, (frame_rgb.shape[1], frame_rgb.shape[0]))

        overlay = cv2.addWeighted(frame_rgb, 1 - alpha, heatmap, alpha, 0)
        return overlay

    @staticmethod
    def draw_event_mask(
        frame: np.ndarray,
        events: EventData,
        alpha: float = 1.0
    ) -> np.ndarray:
        h, w = frame.shape[:2]

        # Create a pure event mask without original frame
        mask_rgb = np.ones((h, w, 3), dtype=np.uint8) * 255
        # White for no events (default)
        
        # Red for on events (brightness increase)
        mask_rgb[events.on_events > 0] = (0, 0, 255)
        # Green for off events (brightness decrease)
        mask_rgb[events.off_events > 0] = (0, 255, 0)

        return mask_rgb

    @staticmethod
    def draw_binary_mask(
        frame: np.ndarray,
        events: EventData,
        color: Tuple[int, int, int] = (0, 0, 255),
        alpha: float = 0.5
    ) -> np.ndarray:
        result = frame.copy()

        if len(result.shape) == 2:
            result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

        mask_rgb = np.zeros_like(result)
        mask_rgb[events.binary_mask > 0] = color

        overlay = cv2.addWeighted(result, 1 - alpha, mask_rgb, alpha, 0)
        return overlay

    @staticmethod
    def add_info_text(
        frame: np.ndarray,
        events: EventData,
        position: Tuple[int, int] = (10, 30),
        font_scale: float = 0.7,
        color: Tuple[int, int, int] = (255, 255, 255)
    ) -> np.ndarray:
        result = frame.copy()

        from evs.event_detector import EventStats
        summary = EventStats.summarize(events)

        # Count DVS events
        on_count = sum(1 for evt in events.events if evt.event_type == 'on')
        off_count = sum(1 for evt in events.events if evt.event_type == 'off')

        texts = [
            f"Frame: {summary['frame_idx']}",
            f"DVS Events: {len(events.events)}",
            f"  ON: {on_count}",
            f"  OFF: {off_count}",
            f"Regions: {summary['num_regions']}"
        ]

        y_offset = 0
        for text in texts:
            cv2.putText(
                result,
                text,
                (position[0], position[1] + y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                color,
                2
            )
            y_offset += 30

        return result

    @staticmethod
    def create_comparison_view(
        original: np.ndarray,
        events: EventData,
        show_heatmap: bool = True,
        show_mask: bool = True
    ) -> np.ndarray:
        h, w = original.shape[:2]

        original_bgr = original.copy()
        if len(original_bgr.shape) == 2:
            original_bgr = cv2.cvtColor(original_bgr, cv2.COLOR_GRAY2BGR)

        regions_view = EventVisualizer.draw_regions(original_bgr, events)
        regions_view = EventVisualizer.add_info_text(regions_view, events)

        views = [original_bgr, regions_view]

        if show_heatmap:
            heatmap_view = EventVisualizer.draw_heatmap_overlay(original_bgr, events)
            views.append(heatmap_view)

        if show_mask:
            mask_view = EventVisualizer.draw_event_mask(original_bgr, events)
            views.append(mask_view)

        num_views = len(views)
        cols = 2
        rows = (num_views + 1) // 2

        target_w = w // cols
        target_h = h // rows

        resized_views = []
        for view in views:
            resized = cv2.resize(view, (target_w, target_h))
            resized_views.append(resized)

        while len(resized_views) < rows * cols:
            resized_views.append(np.zeros((target_h, target_w, 3), dtype=np.uint8))

        grid = []
        for i in range(rows):
            row = np.hstack(resized_views[i*cols:(i+1)*cols])
            grid.append(row)

        return np.vstack(grid)
