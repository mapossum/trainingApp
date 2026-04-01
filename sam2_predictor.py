import numpy as np
import os

import config

# SAM2 is optional — the app works without it
_sam2_available = False
_sam2_service = None

try:
    import torch
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    _sam2_available = True
except ImportError:
    pass


_CHECKPOINT_TO_CONFIG = {
    "sam2.1_hiera_tiny": "configs/sam2.1/sam2.1_hiera_t.yaml",
    "sam2.1_hiera_small": "configs/sam2.1/sam2.1_hiera_s.yaml",
    "sam2.1_hiera_base_plus": "configs/sam2.1/sam2.1_hiera_b+.yaml",
    "sam2.1_hiera_large": "configs/sam2.1/sam2.1_hiera_l.yaml",
    "sam2_hiera_tiny": "configs/sam2/sam2_hiera_t.yaml",
    "sam2_hiera_small": "configs/sam2/sam2_hiera_s.yaml",
    "sam2_hiera_base_plus": "configs/sam2/sam2_hiera_b+.yaml",
    "sam2_hiera_large": "configs/sam2/sam2_hiera_l.yaml",
}


def _guess_config(checkpoint_path):
    """Guess the model config YAML from the checkpoint filename."""
    stem = os.path.splitext(os.path.basename(checkpoint_path))[0]
    for key, cfg in _CHECKPOINT_TO_CONFIG.items():
        if key in stem:
            return cfg
    return "configs/sam2.1/sam2.1_hiera_s.yaml"


class SAM2Service:
    def __init__(self, checkpoint_path, model_cfg=None):
        if model_cfg is None:
            model_cfg = _guess_config(checkpoint_path)
        print(f"  Using config: {model_cfg}")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = build_sam2(model_cfg, checkpoint_path, device=self.device)
        self.predictor = SAM2ImagePredictor(self.model)
        self._current_area_id = None

    def set_image(self, area_id, image_array):
        """Set the image for prediction. image_array: (H, W, 3) uint8 RGB."""
        if self._current_area_id != area_id:
            self.predictor.set_image(image_array)
            self._current_area_id = area_id

    def predict(self, points, labels):
        """Run SAM2 prediction.
        points: Nx2 numpy array of (x_pixel, y_pixel) = (col, row)
        labels: N numpy array of 1=foreground, 0=background
        Returns: (mask, score) where mask is (H, W) bool array
        """
        masks, scores, logits = self.predictor.predict(
            point_coords=points,
            point_labels=labels,
            multimask_output=True
        )
        best_idx = scores.argmax()
        return masks[best_idx], float(scores[best_idx])


def init_sam2():
    """Initialize SAM2 service. Returns True if successful."""
    global _sam2_service
    if not _sam2_available:
        print("SAM2 not available (missing torch or sam2 package)")
        return False

    # Look for checkpoint in sam2_weights directory
    weights_dir = config.SAM2_WEIGHTS_DIR
    checkpoint = None
    for fname in os.listdir(weights_dir) if os.path.isdir(weights_dir) else []:
        if fname.endswith('.pt') or fname.endswith('.pth'):
            checkpoint = os.path.join(weights_dir, fname)
            break

    if not checkpoint:
        print(f"No SAM2 checkpoint found in {weights_dir}")
        print("Download a checkpoint from https://github.com/facebookresearch/sam2")
        print("and place it in the sam2_weights/ directory.")
        return False

    try:
        print(f"Loading SAM2 from {checkpoint}...")
        _sam2_service = SAM2Service(checkpoint)
        print("SAM2 loaded successfully")
        return True
    except Exception as e:
        print(f"Failed to load SAM2: {e}")
        return False


def is_available():
    return _sam2_service is not None


def get_service():
    return _sam2_service
