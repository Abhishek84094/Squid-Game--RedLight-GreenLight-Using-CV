"""
Central configuration for Red Light, Green Light.

Every tunable number in the game lives here so the game can be balanced
without hunting through gameplay code.
"""

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FACES_DIR = os.path.join(DATA_DIR, "faces")
DB_DIR = os.path.join(DATA_DIR, "db")
DB_PATH = os.path.join(DB_DIR, "game.sqlite3")
FACE_MODEL_PATH = os.path.join(FACES_DIR, "lbph_model.yml")
FACE_LABELS_PATH = os.path.join(FACES_DIR, "labels.json")
SOUNDS_DIR = os.path.join(BASE_DIR, "assets", "sounds")

for _d in (DATA_DIR, FACES_DIR, DB_DIR, SOUNDS_DIR):
    os.makedirs(_d, exist_ok=True)

# ---------------------------------------------------------------------------
# Window / display
# ---------------------------------------------------------------------------
SCREEN_WIDTH = 1100
SCREEN_HEIGHT = 720
FPS = 30
WINDOW_TITLE = "Red Light, Green Light"

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# ---------------------------------------------------------------------------
# Face registration / recognition
# ---------------------------------------------------------------------------
FACE_SAMPLES_PER_ANGLE = 20           # frames captured per angle during registration
FACE_ANGLES = ["front", "left", "right"]
FACE_RECOGNITION_CONFIDENCE_THRESHOLD = 80.0  # LBPH distance; LOWER = more confident match
FACE_DETECT_MIN_SIZE = (60, 60)

# ---------------------------------------------------------------------------
# Pose / movement detection
# ---------------------------------------------------------------------------
POSE_MIN_DETECTION_CONFIDENCE = 0.5
POSE_MIN_TRACKING_CONFIDENCE = 0.5
POSE_LANDMARK_VISIBILITY_THRESHOLD = 0.5
MOVEMENT_SMOOTHING_WINDOW = 5          # frames averaged to smooth jitter

# Movement score thresholds (normalized 0-1 coordinate space, scaled x1000
# for readability in the HUD / debug overlay).
GREEN_LIGHT_MIN_SCORE_TO_MOVE = 2.0    # requires active full-body running/marching
RED_LIGHT_MOVEMENT_THRESHOLD = 3.0     # above this during red light -> flagged
RED_LIGHT_CONSECUTIVE_FRAMES = 4       # frames over threshold before elimination (prevents false 1-frame triggers)
RED_LIGHT_GRACE_PERIOD_SEC = 0.65      # reaction grace window after light turns red and music cuts off

# ---------------------------------------------------------------------------
# Anti-cheat
# ---------------------------------------------------------------------------
NO_FACE_TIMEOUT_SEC = 6.0              # player considered "gone" after this long
MULTI_FACE_CHECK_ENABLED = True

# ---------------------------------------------------------------------------
# Match rules
# ---------------------------------------------------------------------------
MULTIPLAYER_MAX_PLAYERS = 5            # maximum concurrent players per room
DISTANCE_TO_WIN = 200.0                # progress units from start line to doll (longer race!)
MATCH_TIME_LIMIT_SEC = 120             # 2 minutes to complete
GREEN_LIGHT_MIN_SEC, GREEN_LIGHT_MAX_SEC = 2.5, 5.0
RED_LIGHT_MIN_SEC, RED_LIGHT_MAX_SEC = 2.0, 4.5
COUNTDOWN_SEC = 3
MOVEMENT_TO_DISTANCE_SCALE = 0.45      # at score 8 -> 3.6 units/sec -> ~55s total active running across 10-15 cycles

# ---------------------------------------------------------------------------
# Squid-Game-inspired UI palette (original design, not licensed assets)
# ---------------------------------------------------------------------------
COLOR_BG = (15, 16, 20)
COLOR_BG_ALT = (24, 26, 32)
COLOR_PINK = (255, 45, 130)
COLOR_PINK_DIM = (140, 30, 80)
COLOR_GREEN = (35, 220, 130)
COLOR_RED = (230, 45, 55)
COLOR_WHITE = (240, 240, 245)
COLOR_GREY = (120, 122, 130)
COLOR_GOLD = (255, 200, 60)

FONT_NAME = None  # None = pygame default font; swap for a bundled .ttf later
