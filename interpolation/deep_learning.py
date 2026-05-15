import numpy as np
from .base import Interpolator


class DeepLearningInterpolator(Interpolator):
    def __init__(self, model_name: str = "placeholder"):
        super().__init__(name=f"Deep Learning ({model_name})")
        self.model_name = model_name
        self.model = None
        print(f"注意: {self.name} 是占位实现，需要加载实际模型")

    def _load_model(self):
        print(f"提示: 正在加载深度学习模型 {self.model_name}...")
        print("参考项目: https://github.com/uzh-rpg/rpg_vid2e")
        print("可选模型: SuperSloMo, DAIN, RIFE等")

    def interpolate(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        t: float = 0.5
    ) -> np.ndarray:
        from .linear import LinearInterpolator

        print(f"警告: {self.name} 使用线性插值作为回退方案")

        linear_interp = LinearInterpolator()
        return linear_interp.interpolate(frame1, frame2, t)
