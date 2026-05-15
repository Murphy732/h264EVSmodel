import cv2
import numpy as np
from typing import Optional, Tuple, Generator
from PIL import Image, ImageDraw, ImageFont


class VideoReader:
    def __init__(self, source: str = "0", target_size: Optional[Tuple[int, int]] = None):
        self.source = source
        self.target_size = target_size
        self.cap = None
        self.fps = 30
        self.frame_count = 0
        self.original_size = None

    def open(self) -> bool:
        if self.source.isdigit():
            self.cap = cv2.VideoCapture(int(self.source))
        else:
            self.cap = cv2.VideoCapture(self.source)

        if not self.cap.isOpened():
            return False

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.original_size = (
            int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        )
        return True

    def read_frame(self) -> Optional[np.ndarray]:
        if self.cap is None or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        return self._preprocess_frame(frame)

    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        if self.target_size is not None:
            frame = cv2.resize(frame, self.target_size)
        return frame

    def get_frames(self, max_frames: Optional[int] = None) -> Generator[np.ndarray, None, None]:
        count = 0
        while True:
            if max_frames is not None and count >= max_frames:
                break
            frame = self.read_frame()
            if frame is None:
                break
            yield frame
            count += 1

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class FramePreprocessor:
    @staticmethod
    def to_grayscale(frame: np.ndarray) -> np.ndarray:
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    @staticmethod
    def to_rgb(frame: np.ndarray) -> np.ndarray:
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return frame

    @staticmethod
    def normalize(frame: np.ndarray) -> np.ndarray:
        return frame.astype(np.float32) / 255.0

    @staticmethod
    def denoise(frame: np.ndarray, method: str = "gaussian", kernel_size: int = 5) -> np.ndarray:
        if method == "gaussian":
            return cv2.GaussianBlur(frame, (kernel_size, kernel_size), 0)
        elif method == "bilateral":
            return cv2.bilateralFilter(frame, kernel_size, 75, 75)
        elif method == "median":
            return cv2.medianBlur(frame, kernel_size)
        return frame

    @staticmethod
    def resize(frame: np.ndarray, size: Tuple[int, int]) -> np.ndarray:
        return cv2.resize(frame, size)


def put_text(frame: np.ndarray, text: str, position: Tuple[int, int], font_size: int = 20, color: Tuple[int, int, int] = (255, 255, 255)):
    try:
        img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        font = ImageFont.truetype("msyh.ttc", font_size, encoding="unic")
        draw.text(position, text, font=font, fill=color)
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    except:
        cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        return frame


def display_frame(frame: np.ndarray, window_name: str = "Frame", wait_time: int = 1) -> bool:
    cv2.imshow(window_name, frame)
    key = cv2.waitKey(wait_time) & 0xFF
    return key != 27


def save_frame(frame: np.ndarray, filepath: str):
    cv2.imwrite(filepath, frame)
