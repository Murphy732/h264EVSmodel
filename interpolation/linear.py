import numpy as np
from .base import Interpolator


class LinearInterpolator(Interpolator):
    def __init__(self):
        super().__init__(name="Linear Interpolation")

    def interpolate(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        t: float = 0.5
    ) -> np.ndarray:
        t = max(0.0, min(1.0, t))

        if frame1.dtype != np.float32:
            f1 = frame1.astype(np.float32)
        else:
            f1 = frame1.copy()

        if frame2.dtype != np.float32:
            f2 = frame2.astype(np.float32)
        else:
            f2 = frame2.copy()

        result = f1 * (1 - t) + f2 * t

        if np.issubdtype(frame1.dtype, np.integer):
            result = np.clip(result, 0, 255).astype(frame1.dtype)

        return result
