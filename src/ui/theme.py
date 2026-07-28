"""Shared drawing helpers so every screen looks consistent."""

from __future__ import annotations

import pygame

from src import config

pygame.font.init()

_FONT_CACHE: dict[tuple[int, bool], pygame.font.Font] = {}


def font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _FONT_CACHE:
        f = pygame.font.SysFont("arial", size, bold=bold)
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]


def draw_text(surface, text, size, pos, color=config.COLOR_WHITE, bold=False, center=False):
    f = font(size, bold)
    label = f.render(text, True, color)
    rect = label.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    surface.blit(label, rect)
    return rect


class Button:
    """A simple rectangular button with hover highlight, used across menus."""

    def __init__(self, rect, text, size=28, accent=config.COLOR_PINK):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.size = size
        self.accent = accent
        self.hovered = False

    def update(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def clicked(self, mouse_pos, mouse_click) -> bool:
        return mouse_click and self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        bg = self.accent if self.hovered else config.COLOR_BG_ALT
        border_color = self.accent
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, border_color, self.rect, width=2, border_radius=8)
        text_color = config.COLOR_BG if self.hovered else config.COLOR_WHITE
        draw_text(surface, self.text, self.size, self.rect.center, color=text_color, center=True)


def draw_panel(surface, rect, border_color=config.COLOR_PINK_DIM):
    pygame.draw.rect(surface, config.COLOR_BG_ALT, rect, border_radius=10)
    pygame.draw.rect(surface, border_color, rect, width=2, border_radius=10)


def draw_progress_bar(surface, rect, fraction, fg=config.COLOR_GREEN, bg=config.COLOR_BG_ALT):
    pygame.draw.rect(surface, bg, rect, border_radius=6)
    fill_rect = pygame.Rect(rect.x, rect.y, int(rect.width * max(0, min(1, fraction))), rect.height)
    if fill_rect.width > 0:
        pygame.draw.rect(surface, fg, fill_rect, border_radius=6)
    pygame.draw.rect(surface, config.COLOR_WHITE, rect, width=1, border_radius=6)
