"""
Stylized 2D player character.

Rather than a rigged 3D model (a real asset pipeline, out of scope for a
solo build - see README "Future Expansion"), the character is drawn
procedurally each frame from primitives (circle head, capsule torso, line
limbs) whose angles are animated with simple sinusoidal functions. This
gives every player a distinct, animated, colored character on screen with
idle / running / frozen / eliminated / victory states, without needing any
external art assets.
"""

from __future__ import annotations

import math
from enum import Enum, auto

import pygame


class AnimState(Enum):
    IDLE = auto()
    RUNNING = auto()
    FROZEN = auto()
    FALLING = auto()
    VICTORY = auto()


class Avatar:
    def __init__(self, color: tuple[int, int, int], name: str, scale: float = 1.0):
        self.color = color
        self.name = name
        self.scale = scale
        self.state = AnimState.IDLE
        self._clock = 0.0
        self._fall_progress = 0.0
        self.run_intensity = 0.0  # 0..1, drives how fast limbs swing

    def set_state(self, state: AnimState):
        if state != self.state:
            self.state = state
            self._clock = 0.0
            if state == AnimState.FALLING:
                self._fall_progress = 0.0

    def update(self, dt: float, run_intensity: float = 0.0):
        self._clock += dt
        self.run_intensity = max(0.0, min(1.0, run_intensity))
        if self.state == AnimState.FALLING:
            self._fall_progress = min(1.0, self._fall_progress + dt / 0.6)

    def draw(self, surface: pygame.Surface, center: tuple[int, int]):
        cx, cy = center
        s = self.scale
        head_r = int(14 * s)
        torso_h = int(34 * s)
        limb_len = int(20 * s)

        rotation = 0.0
        if self.state == AnimState.FALLING:
            rotation = self._fall_progress * (math.pi / 2)
            cy += int(self._fall_progress * 10 * s)

        swing = 0.0
        if self.state == AnimState.RUNNING:
            speed = 4.0 + self.run_intensity * 10.0
            swing = math.sin(self._clock * speed) * (0.3 + 0.5 * self.run_intensity)
        elif self.state == AnimState.IDLE:
            swing = math.sin(self._clock * 1.5) * 0.05
        elif self.state == AnimState.VICTORY:
            swing = math.sin(self._clock * 6.0) * 0.6

        def rot(dx, dy):
            """Rotate an (dx, dy) offset around the character's torso for falling."""
            rx = dx * math.cos(rotation) - dy * math.sin(rotation)
            ry = dx * math.sin(rotation) + dy * math.cos(rotation)
            return int(cx + rx), int(cy + ry)

        hip = rot(0, torso_h * 0.5)
        shoulder = rot(0, -torso_h * 0.2)
        head_pos = rot(0, -torso_h * 0.2 - head_r)

        # limbs
        arm_swing = swing
        leg_swing = -swing
        left_arm = rot(-limb_len * math.cos(arm_swing), -torso_h * 0.2 + limb_len * math.sin(arm_swing))
        right_arm = rot(limb_len * math.cos(arm_swing), -torso_h * 0.2 - limb_len * math.sin(arm_swing))
        left_leg = rot(-limb_len * 0.6 * math.cos(leg_swing), torso_h * 0.5 + limb_len * math.sin(leg_swing))
        right_leg = rot(limb_len * 0.6 * math.cos(leg_swing), torso_h * 0.5 - limb_len * math.sin(leg_swing))

        if self.state == AnimState.VICTORY:
            left_arm = rot(-limb_len * 0.8, -torso_h * 0.2 - limb_len * (0.6 + 0.3 * math.sin(self._clock * 6)))
            right_arm = rot(limb_len * 0.8, -torso_h * 0.2 - limb_len * (0.6 + 0.3 * math.cos(self._clock * 6)))

        line_w = max(3, int(4 * s))
        pygame.draw.line(surface, self.color, shoulder, left_arm, line_w)
        pygame.draw.line(surface, self.color, shoulder, right_arm, line_w)
        pygame.draw.line(surface, self.color, hip, left_leg, line_w)
        pygame.draw.line(surface, self.color, hip, right_leg, line_w)
        pygame.draw.line(surface, self.color, shoulder, hip, line_w + 2)
        pygame.draw.circle(surface, self.color, head_pos, head_r)
        pygame.draw.circle(surface, (0, 0, 0), head_pos, head_r, 2)

        if self.state == AnimState.FROZEN:
            # thin red outline pulsing to signal "must not move"
            pulse = 2 + int(2 * abs(math.sin(self._clock * 6)))
            pygame.draw.circle(surface, (230, 40, 50), head_pos, head_r + pulse, 2)

        # name tag
        font = pygame.font.SysFont(None, 16)
        label = font.render(self.name, True, (240, 240, 245))
        surface.blit(label, (cx - label.get_width() // 2, head_pos[1] - head_r - 16))
