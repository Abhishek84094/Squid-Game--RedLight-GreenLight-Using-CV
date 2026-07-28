"""Minimal screen-stack manager. Each Screen implements handle_event/update/draw."""

from __future__ import annotations


class Screen:
    def __init__(self, app):
        self.app = app

    def on_enter(self):
        """Called once when this screen becomes active."""

    def handle_event(self, event):
        pass

    def update(self, dt: float):
        pass

    def draw(self, surface):
        pass


class ScreenManager:
    def __init__(self):
        self._current: Screen | None = None

    def goto(self, screen: Screen):
        self._current = screen
        screen.on_enter()

    @property
    def current(self) -> Screen | None:
        return self._current
