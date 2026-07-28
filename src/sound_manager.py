"""
All game audio is synthesized at runtime from sine/square waves with numpy.

This sidesteps copyright entirely (no licensed Squid Game score, no sample
packs) while still giving the game countdown beeps, a red/green light
stinger, a tension heartbeat loop, an elimination buzzer, and a victory
fanfare. See README for how to swap these for licensed/composed audio
files later - only this file would need to change.
"""

from __future__ import annotations

import numpy as np
import pygame

SAMPLE_RATE = 44100


def _tone(freq: float, duration: float, volume: float = 0.5, wave: str = "sine") -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    if wave == "sine":
        signal = np.sin(2 * np.pi * freq * t)
    elif wave == "square":
        signal = np.sign(np.sin(2 * np.pi * freq * t))
    else:
        raise ValueError(wave)

    # Short fade in/out to avoid audio "clicks" at the edges of the clip.
    fade_len = max(1, int(SAMPLE_RATE * 0.01))
    envelope = np.ones_like(signal)
    envelope[:fade_len] = np.linspace(0, 1, fade_len)
    envelope[-fade_len:] = np.linspace(1, 0, fade_len)

    return (signal * envelope * volume)


def _to_sound(mono: np.ndarray) -> "pygame.mixer.Sound":
    stereo = np.column_stack([mono, mono])
    audio = (stereo * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.ascontiguousarray(audio))


def _sequence(*tones: np.ndarray, gap: float = 0.02) -> np.ndarray:
    silence = np.zeros(int(SAMPLE_RATE * gap))
    parts = []
    for t in tones:
        parts.append(t)
        parts.append(silence)
    return np.concatenate(parts) if parts else np.zeros(1)


class SoundManager:
    def __init__(self):
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2)
        self._sounds = self._build_all()
        self._heartbeat_channel: pygame.mixer.Channel | None = None

    def _build_all(self) -> dict:
        return {
            "countdown_tick": _to_sound(_tone(440, 0.12, 0.4)),
            "countdown_go": _to_sound(_tone(880, 0.3, 0.5)),
            "green_light": _to_sound(
                _sequence(_tone(523, 0.1, 0.4), _tone(659, 0.1, 0.4), _tone(784, 0.15, 0.45))
            ),
            "red_light": _to_sound(_tone(180, 0.35, 0.5, wave="square")),
            "warning_flash": _to_sound(_tone(300, 0.08, 0.6, wave="square")),
            "eliminated": _to_sound(
                _sequence(_tone(200, 0.2, 0.6, wave="square"), _tone(120, 0.4, 0.6, wave="square"))
            ),
            "victory": _to_sound(
                _sequence(
                    _tone(523, 0.15, 0.5), _tone(659, 0.15, 0.5),
                    _tone(784, 0.15, 0.5), _tone(1047, 0.35, 0.55),
                )
            ),
            "menu_select": _to_sound(_tone(600, 0.06, 0.3)),
            "heartbeat": _to_sound(
                _sequence(_tone(90, 0.1, 0.5, wave="sine"), _tone(90, 0.1, 0.35, wave="sine"), gap=0.15)
            ),
        }

    def play(self, name: str, loops: int = 0):
        sound = self._sounds.get(name)
        if sound:
            sound.play(loops=loops)

    def start_heartbeat_loop(self):
        sound = self._sounds.get("heartbeat")
        if sound and self._heartbeat_channel is None:
            self._heartbeat_channel = sound.play(loops=-1)

    def stop_heartbeat_loop(self):
        if self._heartbeat_channel is not None:
            self._heartbeat_channel.stop()
            self._heartbeat_channel = None
