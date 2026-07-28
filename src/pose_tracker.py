"""
Pose estimation + movement scoring.

This is the module that turns "a person standing in front of a webcam"
into "how much did they just move" - the number the whole game is built
around. Pipeline for a single frame:

    frame (BGR) -> MediaPipe Pose -> 33 landmarks -> displacement vs.
    previous frame -> smoothed movement score

No YOLO/person-detector is used here on purpose: MediaPipe Pose already
handles single-person localization internally, which is all a single-
camera, single-player game needs. See README for when you'd add
YOLO + ByteTrack (multi-person-per-frame scenarios).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import mediapipe as mp
import numpy as np

from src import config

mp_pose = mp.solutions.pose


@dataclass
class PoseResult:
    landmarks: np.ndarray | None   # shape (33, 3) -> x, y, visibility ; None if no person found
    raw_result: object


class PoseTracker:
    def __init__(self):
        self._pose = mp_pose.Pose(
            model_complexity=1,
            min_detection_confidence=config.POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=config.POSE_MIN_TRACKING_CONFIDENCE,
        )

    def process(self, frame_rgb: np.ndarray) -> PoseResult:
        result = self._pose.process(frame_rgb)
        if not result.pose_landmarks:
            return PoseResult(landmarks=None, raw_result=result)

        landmarks = np.array(
            [[lm.x, lm.y, lm.visibility] for lm in result.pose_landmarks.landmark]
        )
        return PoseResult(landmarks=landmarks, raw_result=result)

    def close(self):
        self._pose.close()


class MovementScorer:
    """
    Tracks landmark positions frame-to-frame and produces a smoothed
    "how much is this person moving" score.

    The score is intentionally unit-less (average normalized-coordinate
    displacement x 1000) - what matters is its relative size versus the
    thresholds in config.py, not any physical unit.
    """

    def __init__(self):
        self._previous: np.ndarray | None = None
        self._window: deque[float] = deque(maxlen=config.MOVEMENT_SMOOTHING_WINDOW)

    def reset(self):
        self._previous = None
        self._window.clear()

    def update(self, landmarks: np.ndarray | None) -> float:
        """Feed the latest landmarks in; get back the current smoothed score."""
        if landmarks is None:
            # Lost tracking for a frame - don't punish the player for a
            # dropped frame, just carry the last known smoothed score forward.
            return self.smoothed_score

        if self._previous is None or self._previous.shape != landmarks.shape:
            self._previous = landmarks
            self._window.append(0.0)
            return 0.0

        visible = landmarks[:, 2] > config.POSE_LANDMARK_VISIBILITY_THRESHOLD
        if not np.any(visible):
            self._previous = landmarks
            return self.smoothed_score

        displacement = np.linalg.norm(
            landmarks[visible, :2] - self._previous[visible, :2], axis=1
        )
        instantaneous = float(np.mean(displacement) * 1000.0)

        self._previous = landmarks
        self._window.append(instantaneous)
        return float(np.mean(self._window))

    @property
    def smoothed_score(self) -> float:
        return float(np.mean(self._window)) if self._window else 0.0
