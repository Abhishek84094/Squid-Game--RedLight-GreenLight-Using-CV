"""
Application controller.

Owns every shared resource (webcam, database, face auth, pose tracker,
sound manager) and the pygame main loop. Screens (in src/ui/*) read from
and call into this object rather than each managing their own camera
handle or DB connection.
"""

from __future__ import annotations

import os
import cv2
import numpy as np
import pygame

# Force the pygame window onto the primary monitor at a fixed position.
os.environ["SDL_VIDEO_WINDOW_POS"] = "100,100"
os.environ["SDL_VIDEO_CENTERED"] = "0"

from src import config, database, face_auth, pose_tracker, sound_manager


class Camera:
    """Thin wrapper around cv2.VideoCapture with graceful failure."""

    def __init__(self, index: int = config.CAMERA_INDEX):
        self.index = index
        self.cap: cv2.VideoCapture | None = None
        self.last_error: str | None = None
        self._try_open()

    def _try_open(self):
        try:
            cap = cv2.VideoCapture(self.index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
            if not cap.isOpened():
                self.last_error = (
                    f"Could not open camera index {self.index}. "
                    "Check that a webcam is connected and not in use by "
                    "another application."
                )
                self.cap = None
                return
            self.cap = cap
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 - surface any camera failure to the UI
            self.last_error = f"Camera error: {exc}"
            self.cap = None

    @property
    def available(self) -> bool:
        return self.cap is not None

    def read(self):
        """Returns a mirrored BGR frame, or None if unavailable/failed."""
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok:
            return None
        return cv2.flip(frame, 1)  # mirror for natural "looking in a mirror" feel

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


def bgr_to_surface(frame_bgr: np.ndarray) -> pygame.Surface:
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    rgb = np.rot90(rgb)
    surf = pygame.surfarray.make_surface(rgb)
    return pygame.transform.flip(surf, False, True)


class App:
    def __init__(self):
        # Ensure window appears on primary display
        os.environ["SDL_VIDEO_CENTERED"] = "1"
        pygame.init()
        try:
            pygame.mixer.init(frequency=sound_manager.SAMPLE_RATE, size=-16, channels=2)
        except pygame.error as exc:
            print(f"[audio] continuing without sound: {exc}")

        self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.clock = pygame.time.Clock()

        self.db = database.Database()
        self.face_auth = face_auth.FaceAuth(self.db)
        self.camera = Camera()
        self.pose_tracker = pose_tracker.PoseTracker()
        self.sound: sound_manager.SoundManager | None
        try:
            self.sound = sound_manager.SoundManager()
        except pygame.error:
            self.sound = None

        self.current_player: dict | None = None

        from src.ui.screen_manager import ScreenManager

        self.screens = ScreenManager()
        self.running = True

    def play_sound(self, name: str, loops: int = 0):
        if self.sound:
            self.sound.play(name, loops=loops)

    def logout(self):
        self.current_player = None

    def quit(self):
        self.running = False

    def run(self):
        from src.ui.screens import WelcomeScreen

        self.screens.goto(WelcomeScreen(self))

        while self.running:
            dt = self.clock.tick(config.FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    if self.screens.current:
                        self.screens.current.handle_event(event)

            if self.screens.current:
                self.screens.current.update(dt)
                self.screens.current.draw(self.screen)

            pygame.display.flip()

        self._shutdown()

    def _shutdown(self):
        self.camera.release()
        self.pose_tracker.close()
        self.db.close()
        pygame.quit()
