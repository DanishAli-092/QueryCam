"""
Central config for QueryCam pipeline test app.
Update paths to match your local setup.
"""

# --- Model paths ---
BASE_YOLO_MODEL = "yolov11n.pt"              # pretrained COCO weights
CUSTOM_YOLO_MODEL = "runs/train/best.pt"     # your fine-tuned weights (guns, bags, violence)

# --- Custom model class names (must match your training config) ---
CUSTOM_CLASSES = ["gun", "abandoned_bag", "violence"]

# --- BLIP model ---
BLIP_MODEL_NAME = "Salesforce/blip-image-captioning-base"

# --- Frame extraction ---
FRAME_INTERVAL_SEC = 1.0     # extract 1 frame every N seconds
MAX_FRAMES = 300             # safety cap for long videos during testing

# --- Detection thresholds ---
CONF_THRESHOLD = 0.35

# --- Device ---
DEVICE = "cuda"   # falls back to "cpu" automatically if cuda unavailable, handled in code

