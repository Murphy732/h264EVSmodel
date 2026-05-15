import numpy as np
import cv2
from .base import Interpolator
from typing import Tuple


class OpticalFlowInterpolator(Interpolator):
    def __init__(self, method: str = "farneback"):
        super().__init__(name=f"Optical Flow ({method})")
        self.method = method

    def _compute_flow_farneback(
        self,
        gray1: np.ndarray,
        gray2: np.ndarray
    ) -> np.ndarray:
        flow = cv2.calcOpticalFlowFarneback(
            gray1, gray2, None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0
        )
        return flow

    def _warp_frame(
        self,
        frame: np.ndarray,
        flow: np.ndarray,
        t: float
    ) -> np.ndarray:
        h, w = flow.shape[:2]
        flow_scaled = flow * t

        x = np.arange(w)
        y = np.arange(h)
        xx, yy = np.meshgrid(x, y)

        map_x = (xx + flow_scaled[..., 0]).astype(np.float32)
        map_y = (yy + flow_scaled[..., 1]).astype(np.float32)

        warped = cv2.remap(
            frame, map_x, map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT
        )

        return warped

    def interpolate(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        t: float = 0.5
    ) -> np.ndarray:
        t = max(0.0, min(1.0, t))

        if t == 0.0:
            return frame1.copy()
        if t == 1.0:
            return frame2.copy()

        if len(frame1.shape) == 3:
            gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        else:
            gray1 = frame1
            gray2 = frame2

        flow_forward = self._compute_flow_farneback(gray1, gray2)
        flow_backward = self._compute_flow_farneback(gray2, gray1)

        warped1 = self._warp_frame(frame1, flow_forward, t)
        warped2 = self._warp_frame(frame2, flow_backward, 1 - t)

        result = warped1 * (1 - t) + warped2 * t

        if np.issubdtype(frame1.dtype, np.integer):
            result = np.clip(result, 0, 255).astype(frame1.dtype)

        return result
