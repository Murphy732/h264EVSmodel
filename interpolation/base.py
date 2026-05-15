import numpy as np
from abc import ABC, abstractmethod
from typing import Optional


class Interpolator(ABC):
    def __init__(self, name: str = "BaseInterpolator"):
        self.name = name

    @abstractmethod
    def interpolate(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        t: float = 0.5
    ) -> np.ndarray:
        pass

    def __call__(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        t: float = 0.5
    ) -> np.ndarray:
        return self.interpolate(frame1, frame2, t)
