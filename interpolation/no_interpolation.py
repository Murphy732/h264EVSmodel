import numpy as np
from .base import Interpolator


class NoInterpolator(Interpolator):
    def __init__(self):
        super().__init__(name="No Interpolation")

    def interpolate(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        t: float = 0.5
    ) -> np.ndarray:
        if t < 0.5:
            return frame1.copy()
        else:
            return frame2.copy()
