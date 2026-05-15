import cv2
import numpy as np
from typing import Optional, Generator
import os


class H264Decoder:
    def __init__(self, input_path: Optional[str] = None):
        self.input_path = input_path
        self.cap = None
        self.frame_count = 0

    def open(self, input_path: Optional[str] = None) -> bool:
        if input_path is not None:
            self.input_path = input_path

        if self.input_path is None:
            raise ValueError("Input path must be specified")

        self.cap = cv2.VideoCapture(self.input_path)
        return self.cap.isOpened()

    def decode_frame(self) -> Optional[np.ndarray]:
        if self.cap is None or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        self.frame_count += 1
        return frame

    def get_frames(self, max_frames: Optional[int] = None) -> Generator[np.ndarray, None, None]:
        count = 0
        while True:
            if max_frames is not None and count >= max_frames:
                break
            frame = self.decode_frame()
            if frame is None:
                break
            yield frame
            count += 1

    def decode_i_frame(self, i_frame_data: bytes) -> Optional[np.ndarray]:
        temp_path = "temp_i_frame.h264"

        with open(temp_path, 'wb') as f:
            f.write(i_frame_data)

        cap = cv2.VideoCapture(temp_path)
        ret, frame = cap.read()
        cap.release()

        if os.path.exists(temp_path):
            os.remove(temp_path)

        return frame if ret else None

    def get_info(self) -> dict:
        if self.cap is None or not self.cap.isOpened():
            return {}

        return {
            "fps": self.cap.get(cv2.CAP_PROP_FPS),
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "total_frames": int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        }

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        if self.input_path:
            self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
