"""
Face registration & face-based login.

Design choice: instead of a heavy deep-embedding stack (InsightFace/dlib,
which need compiled binaries that are painful to install cross-platform),
this project uses OpenCV's built-in Haar cascade for face *detection* and
LBPH (Local Binary Patterns Histograms) for face *recognition*. Both ship
inside opencv-contrib-python with no extra install step, and are more than
accurate enough for a single-user-at-a-time login on a local webcam.

See README "Growing this project" for how to swap this module for
InsightFace/ArcFace embeddings without touching any other file - every
caller only talks to `FaceAuth.register_player(...)` and
`FaceAuth.recognize(frame)`.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

from src import config, database


class FaceAuth:
    def __init__(self, db: database.Database):
        self.db = db
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.detector = cv2.CascadeClassifier(cascade_path)
        if self.detector.empty():
            raise RuntimeError(
                "Could not load OpenCV's Haar cascade file - check your "
                "opencv-contrib-python installation."
            )

        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.labels = database.load_face_labels()  # {int_label: game_id}
        self._trained = False
        if os.path.exists(config.FACE_MODEL_PATH) and self.labels:
            self.recognizer.read(config.FACE_MODEL_PATH)
            self._trained = True

    # ------------------------------------------------------------------ #
    # Detection helpers
    # ------------------------------------------------------------------ #
    def detect_faces(self, frame_bgr: np.ndarray):
        """Returns list of (x, y, w, h) boxes for every face found in frame."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = self.detector.detectMultiScale(
            gray,
            scaleFactor=1.15,
            minNeighbors=6,
            minSize=config.FACE_DETECT_MIN_SIZE,
        )
        return faces, gray

    def largest_face(self, frame_bgr: np.ndarray):
        faces, gray = self.detect_faces(frame_bgr)
        if len(faces) == 0:
            return None, None
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face_crop = cv2.resize(gray[y : y + h, x : x + w], (200, 200))
        return (x, y, w, h), face_crop

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def sample_dir_for(self, game_id: str) -> str:
        path = os.path.join(config.FACES_DIR, game_id)
        os.makedirs(path, exist_ok=True)
        return path

    def save_sample(self, game_id: str, angle: str, index: int, face_crop: np.ndarray):
        path = os.path.join(self.sample_dir_for(game_id), f"{angle}_{index:03d}.png")
        cv2.imwrite(path, face_crop)

    def sample_count(self, game_id: str, angle: str) -> int:
        d = self.sample_dir_for(game_id)
        return len([f for f in os.listdir(d) if f.startswith(f"{angle}_")])

    def retrain(self):
        """Rebuild the LBPH model from every registered player's saved samples."""
        faces, labels, mapping = [], [], {}
        next_label = 0
        for game_id in sorted(os.listdir(config.FACES_DIR)):
            player_dir = os.path.join(config.FACES_DIR, game_id)
            if not os.path.isdir(player_dir):
                continue
            samples = [f for f in os.listdir(player_dir) if f.endswith(".png")]
            if not samples:
                continue
            label = next_label
            next_label += 1
            mapping[label] = game_id
            for fname in samples:
                img = cv2.imread(os.path.join(player_dir, fname), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    faces.append(img)
                    labels.append(label)

        if not faces:
            return False

        self.recognizer.train(faces, np.array(labels))
        self.recognizer.write(config.FACE_MODEL_PATH)
        database.save_face_labels(mapping)
        self.labels = mapping
        self._trained = True
        return True

    # ------------------------------------------------------------------ #
    # Login
    # ------------------------------------------------------------------ #
    def recognize(self, frame_bgr: np.ndarray):
        """
        Returns (game_id, confidence) for the best-matching registered
        player, or (None, None) if no face / no confident match.
        Confidence is an LBPH distance: LOWER means a better match.
        """
        if not self._trained:
            return None, None

        box, face_crop = self.largest_face(frame_bgr)
        if face_crop is None:
            return None, None

        label, confidence = self.recognizer.predict(face_crop)
        # Standard LBPH confidence distance for registered faces is between 45.0 and 70.0
        if confidence <= config.FACE_RECOGNITION_CONFIDENCE_THRESHOLD:
            return self.labels.get(label), confidence
        return None, confidence
