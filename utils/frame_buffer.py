import numpy as np
from typing import Optional, List
from collections import deque


class FrameBuffer:
    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self.buffer: deque = deque(maxlen=max_size)
        self.frame_indices: deque = deque(maxlen=max_size)

    def add_frame(self, frame: np.ndarray, frame_idx: int = -1):
        self.buffer.append(frame.copy())
        self.frame_indices.append(frame_idx)

    def get_latest(self) -> Optional[np.ndarray]:
        if not self.buffer:
            return None
        return self.buffer[-1]

    def get_reference(self) -> Optional[np.ndarray]:
        return self.get_latest()

    def get_frame_at(self, index: int) -> Optional[np.ndarray]:
        if 0 <= index < len(self.buffer):
            return self.buffer[index]
        return None

    def get_pair(self) -> tuple:
        if len(self.buffer) < 2:
            return None, None
        return self.buffer[-2], self.buffer[-1]

    def clear(self):
        self.buffer.clear()
        self.frame_indices.clear()

    def __len__(self) -> int:
        return len(self.buffer)
