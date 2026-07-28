"""All game screens, in the order the player moves through them."""

from __future__ import annotations

import cv2
import pygame

from src import config
from src.app import bgr_to_surface
from src.avatar import Avatar, AnimState
from src.game_state import GameState, Phase
from src.multiplayer.client import RoomClient
from src.multiplayer.match_state import LightPhase
from src.multiplayer.protocol import decode_room_code
from src.multiplayer.server import RoomServer
from src.pose_tracker import MovementScorer
from src.ui import theme
from src.ui.screen_manager import Screen

W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT


# --------------------------------------------------------------------------- #
# Welcome
# --------------------------------------------------------------------------- #
class WelcomeScreen(Screen):
    def on_enter(self):
        self.login_btn = theme.Button((W / 2 - 160, 380, 320, 56), "LOGIN (Face Scan)")
        self.register_btn = theme.Button((W / 2 - 160, 450, 320, 56), "REGISTER NEW PLAYER",
                                          accent=config.COLOR_GREEN)
        self.quit_btn = theme.Button((W / 2 - 160, 520, 320, 56), "QUIT", accent=config.COLOR_GREY)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            if self.login_btn.rect.collidepoint(pos):
                self.app.play_sound("menu_select")
                self.app.screens.goto(LoginScreen(self.app))
            elif self.register_btn.rect.collidepoint(pos):
                self.app.play_sound("menu_select")
                self.app.screens.goto(RegisterScreen(self.app))
            elif self.quit_btn.rect.collidepoint(pos):
                self.app.quit()

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        for b in (self.login_btn, self.register_btn, self.quit_btn):
            b.update(mouse)

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        theme.draw_text(surface, "RED LIGHT, GREEN LIGHT", 52, (W / 2, 180),
                         color=config.COLOR_PINK, bold=True, center=True)
        theme.draw_text(surface, "Move with your body. Freeze when the doll turns.", 20,
                         (W / 2, 240), color=config.COLOR_GREY, center=True)
        if not self.app.camera.available:
            theme.draw_text(surface, f"Camera warning: {self.app.camera.last_error}", 16,
                             (W / 2, 300), color=config.COLOR_RED, center=True)
        for b in (self.login_btn, self.register_btn, self.quit_btn):
            b.draw(surface)


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
class RegisterScreen(Screen):
    """Name entry, then guided capture of front / left / right face samples."""

    STEP_NAME = "name"
    STEP_CAPTURE = "capture"
    STEP_DONE = "done"

    def on_enter(self):
        self.step = self.STEP_NAME
        self.name_buffer = ""
        self.angle_index = 0
        self.capture_count = 0
        self.capture_cooldown = 0.0
        self.error = None
        self.new_player = None
        self.back_btn = theme.Button((30, 30, 120, 44), "< Back", size=20, accent=config.COLOR_GREY)
        self.continue_btn = theme.Button((W / 2 - 140, 500, 280, 54), "CONTINUE")

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and self.back_btn.rect.collidepoint(event.pos):
            self.app.screens.goto(WelcomeScreen(self.app))
            return

        if self.step == self.STEP_NAME:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN and self.name_buffer.strip():
                    self.step = self.STEP_CAPTURE
                elif event.key == pygame.K_BACKSPACE:
                    self.name_buffer = self.name_buffer[:-1]
                elif event.unicode.isprintable() and len(self.name_buffer) < 20:
                    self.name_buffer += event.unicode
            if event.type == pygame.MOUSEBUTTONDOWN and self.continue_btn.rect.collidepoint(event.pos):
                if self.name_buffer.strip():
                    self.step = self.STEP_CAPTURE

        elif self.step == self.STEP_DONE:
            if event.type == pygame.MOUSEBUTTONDOWN and self.continue_btn.rect.collidepoint(event.pos):
                self.app.current_player = self.new_player
                from src.ui.screens import MainMenuScreen
                self.app.screens.goto(MainMenuScreen(self.app))

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        self.back_btn.update(mouse)
        self.continue_btn.update(mouse)

        if self.step != self.STEP_CAPTURE:
            return

        self.capture_cooldown = max(0.0, self.capture_cooldown - dt)
        if not self.app.camera.available:
            return

        frame = self.app.camera.read()
        if frame is None:
            return
        self._last_frame = frame

        angle = config.FACE_ANGLES[self.angle_index]
        box, face_crop = self.app.face_auth.largest_face(frame)
        if face_crop is not None and self.capture_cooldown <= 0.0:
            game_id_tmp = f"tmp_{self.name_buffer.strip().lower().replace(' ', '_')}"
            self.app.face_auth.save_sample(game_id_tmp, angle, self.capture_count, face_crop)
            self.capture_count += 1
            self.capture_cooldown = 0.12
            self._pending_game_id = game_id_tmp

            if self.capture_count >= config.FACE_SAMPLES_PER_ANGLE:
                self.capture_count = 0
                self.angle_index += 1
                if self.angle_index >= len(config.FACE_ANGLES):
                    self._finish_registration(game_id_tmp)

    def _finish_registration(self, tmp_game_id: str):
        import os

        player = self.app.db.create_player(self.name_buffer.strip())
        real_dir = self.app.face_auth.sample_dir_for(player["game_id"])
        tmp_dir = self.app.face_auth.sample_dir_for(tmp_game_id)
        for fname in os.listdir(tmp_dir):
            os.replace(os.path.join(tmp_dir, fname), os.path.join(real_dir, fname))
        os.rmdir(tmp_dir)

        ok = self.app.face_auth.retrain()
        if not ok:
            self.error = "Face model training failed - check camera lighting and try again."
        self.new_player = player
        self.step = self.STEP_DONE

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        theme.draw_text(surface, "PLAYER REGISTRATION", 36, (W / 2, 70),
                         color=config.COLOR_PINK, bold=True, center=True)

        if self.step == self.STEP_NAME:
            theme.draw_text(surface, "Enter your name", 22, (W / 2, 220), center=True)
            box = pygame.Rect(W / 2 - 200, 260, 400, 50)
            theme.draw_panel(surface, box)
            theme.draw_text(surface, self.name_buffer + "|", 26, box.center, center=True)
            theme.draw_text(surface, "Press ENTER to continue", 16, (W / 2, 330),
                             color=config.COLOR_GREY, center=True)
            self.continue_btn.rect.topleft = (W / 2 - 140, 380)
            self.continue_btn.draw(surface)

        elif self.step == self.STEP_CAPTURE:
            angle = config.FACE_ANGLES[self.angle_index] if self.angle_index < 3 else "done"
            theme.draw_text(
                surface, f"Capturing: {angle.upper()} face - turn your head {angle}",
                24, (W / 2, 140), color=config.COLOR_GREEN, center=True,
            )
            frame = getattr(self, "_last_frame", None)
            if frame is not None:
                small = cv2.resize(frame, (480, 360))
                cam_surf = bgr_to_surface(small)
                rect = cam_surf.get_rect(center=(W / 2, 380))
                surface.blit(cam_surf, rect)
                pygame.draw.rect(surface, config.COLOR_PINK, rect, 3)
            else:
                theme.draw_text(surface, "No camera feed available.", 20, (W / 2, 380),
                                 color=config.COLOR_RED, center=True)

            progress = self.angle_index / len(config.FACE_ANGLES) + (
                self.capture_count / config.FACE_SAMPLES_PER_ANGLE
            ) / len(config.FACE_ANGLES)
            bar = pygame.Rect(W / 2 - 200, 600, 400, 24)
            theme.draw_progress_bar(surface, bar, progress, fg=config.COLOR_GREEN)
            theme.draw_text(surface, f"Sample {self.capture_count}/{config.FACE_SAMPLES_PER_ANGLE}",
                             16, (W / 2, 640), center=True, color=config.COLOR_GREY)

        elif self.step == self.STEP_DONE:
            theme.draw_text(surface, "Registration complete!", 30, (W / 2, 250),
                             color=config.COLOR_GREEN, center=True)
            theme.draw_text(surface, f"Welcome, {self.new_player['name']}", 22,
                             (W / 2, 300), center=True)
            theme.draw_text(surface, f"Game ID: {self.new_player['game_id']}", 20,
                             (W / 2, 335), color=config.COLOR_GOLD, center=True)
            if self.error:
                theme.draw_text(surface, self.error, 16, (W / 2, 400), color=config.COLOR_RED, center=True)
            self.continue_btn.rect.topleft = (W / 2 - 140, 500)
            self.continue_btn.text = "ENTER LOBBY"
            self.continue_btn.draw(surface)


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
class LoginScreen(Screen):
    def on_enter(self):
        self.status = "Look into the camera..."
        self.status_color = config.COLOR_GREY
        self.back_btn = theme.Button((30, 30, 120, 44), "< Back", size=20, accent=config.COLOR_GREY)
        self.register_btn = theme.Button((W / 2 - 160, 620, 320, 50), "REGISTER INSTEAD",
                                          accent=config.COLOR_GREEN)
        self._matched_player = None
        self._match_hold = 0.0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.back_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(WelcomeScreen(self.app))
            elif self.register_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(RegisterScreen(self.app))

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        self.back_btn.update(mouse)
        self.register_btn.update(mouse)

        if not self.app.camera.available:
            self.status, self.status_color = "No camera detected.", config.COLOR_RED
            return

        frame = self.app.camera.read()
        if frame is None:
            return
        self._last_frame = frame

        game_id, confidence = self.app.face_auth.recognize(frame)
        if game_id:
            player = self.app.db.get_player_by_game_id(game_id)
            if player:
                self._matched_player = player
                self._match_hold += dt
                self.status = f"Recognized: {player['name']}"
                self.status_color = config.COLOR_GREEN
                if self._match_hold >= 0.6:  # brief hold avoids a false-positive single-frame match
                    self.app.current_player = player
                    self.app.play_sound("menu_select")
                    from src.ui.screens import MainMenuScreen
                    self.app.screens.goto(MainMenuScreen(self.app))
                return
        else:
            self._match_hold = 0.0
            box, crop = self.app.face_auth.largest_face(frame)
            if crop is None:
                self.status, self.status_color = "No face detected...", config.COLOR_GREY
            else:
                self.status, self.status_color = "Face not recognized.", config.COLOR_RED

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        theme.draw_text(surface, "FACE LOGIN", 36, (W / 2, 70), color=config.COLOR_PINK,
                         bold=True, center=True)

        frame = getattr(self, "_last_frame", None)
        if frame is not None:
            small = cv2.resize(frame, (480, 360))
            cam_surf = bgr_to_surface(small)
            rect = cam_surf.get_rect(center=(W / 2, 340))
            surface.blit(cam_surf, rect)
            pygame.draw.rect(surface, self.status_color, rect, 3)
        theme.draw_text(surface, self.status, 22, (W / 2, 550), color=self.status_color, center=True)
        self.register_btn.draw(surface)


# --------------------------------------------------------------------------- #
# Main Menu
# --------------------------------------------------------------------------- #
class MainMenuScreen(Screen):
    def on_enter(self):
        labels = ["PLAY", "LEADERBOARD", "PROFILE & STATS", "SETTINGS", "LOGOUT", "QUIT"]
        self.buttons = []
        top = 260
        for i, label in enumerate(labels):
            accent = config.COLOR_PINK if label == "PLAY" else config.COLOR_BG_ALT
            self.buttons.append(
                theme.Button((W / 2 - 180, top + i * 64, 360, 52), label,
                             accent=config.COLOR_PINK if label == "PLAY" else config.COLOR_GREY)
            )

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            for b in self.buttons:
                if b.rect.collidepoint(event.pos):
                    self.app.play_sound("menu_select")
                    self._select(b.text)

    def _select(self, label):
        if label == "PLAY":
            self.app.screens.goto(ModeSelectScreen(self.app))
        elif label == "LEADERBOARD":
            self.app.screens.goto(LeaderboardScreen(self.app))
        elif label == "PROFILE & STATS":
            self.app.screens.goto(ProfileScreen(self.app))
        elif label == "SETTINGS":
            self.app.screens.goto(SettingsScreen(self.app))
        elif label == "LOGOUT":
            self.app.logout()
            self.app.screens.goto(WelcomeScreen(self.app))
        elif label == "QUIT":
            self.app.quit()

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            b.update(mouse)

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        player = self.app.current_player or {}
        theme.draw_text(surface, "RED LIGHT, GREEN LIGHT", 40, (W / 2, 100),
                         color=config.COLOR_PINK, bold=True, center=True)
        theme.draw_text(surface, f"{player.get('name', '?')}  ·  {player.get('game_id', '?')}",
                         20, (W / 2, 150), color=config.COLOR_GOLD, center=True)
        for b in self.buttons:
            b.draw(surface)


# --------------------------------------------------------------------------- #
# Mode select -> Get ready
# --------------------------------------------------------------------------- #
class ModeSelectScreen(Screen):
    def on_enter(self):
        self.back_btn = theme.Button((30, 30, 120, 44), "< Back", size=20, accent=config.COLOR_GREY)
        col_w, gap = 260, 30
        total_w = col_w * 3 + gap * 2
        start_x = W / 2 - total_w / 2
        self.practice_btn = theme.Button((start_x, 320, col_w, 200), "PRACTICE",
                                          accent=config.COLOR_GREEN)
        self.challenge_btn = theme.Button((start_x + col_w + gap, 320, col_w, 200), "CHALLENGE",
                                           accent=config.COLOR_PINK)
        self.multiplayer_btn = theme.Button((start_x + 2 * (col_w + gap), 320, col_w, 200),
                                             "MULTIPLAYER", accent=config.COLOR_GOLD)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.back_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(MainMenuScreen(self.app))
            elif self.practice_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(GetReadyScreen(self.app, practice=True))
            elif self.challenge_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(GetReadyScreen(self.app, practice=False))
            elif self.multiplayer_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(MultiplayerHomeScreen(self.app))

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        for b in (self.back_btn, self.practice_btn, self.challenge_btn, self.multiplayer_btn):
            b.update(mouse)

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        theme.draw_text(surface, "SELECT MODE", 36, (W / 2, 150), color=config.COLOR_PINK,
                         bold=True, center=True)
        self.practice_btn.draw(surface)
        self.challenge_btn.draw(surface)
        self.multiplayer_btn.draw(surface)
        theme.draw_text(surface, "No elimination - learn the controls", 16,
                         (self.practice_btn.rect.centerx, 540), center=True, color=config.COLOR_GREY)
        theme.draw_text(surface, "Full rules - freeze or you're out", 16,
                         (self.challenge_btn.rect.centerx, 540), center=True, color=config.COLOR_GREY)
        theme.draw_text(surface, "Create or join a room with a code", 16,
                         (self.multiplayer_btn.rect.centerx, 540), center=True, color=config.COLOR_GREY)


class GetReadyScreen(Screen):
    """Short cinematic beat before the arena loads."""

    def __init__(self, app, practice: bool):
        super().__init__(app)
        self.practice = practice
        self.timer = 0.0
        self.start_btn = theme.Button((W / 2 - 140, 560, 280, 54), "ENTER ARENA")

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and self.start_btn.rect.collidepoint(event.pos):
            self.app.screens.goto(GameScreen(self.app, practice=self.practice))
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            self.app.screens.goto(GameScreen(self.app, practice=self.practice))

    def update(self, dt):
        self.timer += dt
        self.start_btn.update(pygame.mouse.get_pos())

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        player = self.app.current_player or {}
        mode = "PRACTICE" if self.practice else "CHALLENGE"
        theme.draw_text(surface, f"{mode} MODE", 34, (W / 2, 160), color=config.COLOR_PINK,
                         bold=True, center=True)
        theme.draw_text(surface, f"Player: {player.get('name', '?')} ({player.get('game_id', '?')})",
                         22, (W / 2, 230), center=True)
        theme.draw_text(surface, "Stand back so your whole upper body is visible.", 18,
                         (W / 2, 320), color=config.COLOR_GREY, center=True)
        theme.draw_text(surface, "Move freely on GREEN. Freeze completely on RED.", 18,
                         (W / 2, 350), color=config.COLOR_GREY, center=True)
        theme.draw_text(surface, "Reach the doll before time runs out to win.", 18,
                         (W / 2, 380), color=config.COLOR_GREY, center=True)
        self.start_btn.draw(surface)


# --------------------------------------------------------------------------- #
# Gameplay
# --------------------------------------------------------------------------- #
class GameScreen(Screen):
    RESULT_DELAY_SEC = 2.2

    def __init__(self, app, practice: bool):
        super().__init__(app)
        self.practice = practice

    def on_enter(self):
        self.state = GameState(practice_mode=self.practice)
        self.state.start_countdown()
        self.scorer = MovementScorer()
        player = self.app.current_player or {"name": "Player", "avatar_color": "#ff2d82"}
        color = _hex_to_rgb(player.get("avatar_color", "#ff2d82"))
        self.avatar = Avatar(color=color, name=player.get("name", "Player"))
        self._prev_phase = self.state.phase
        self.no_face_timer = 0.0
        self.multi_face_timer = 0.0
        self._result_timer = 0.0
        self._recorded = False
        self._last_frame = None
        self.app.play_sound("countdown_tick")

    def handle_event(self, event):
        pass  # gameplay is entirely camera-driven; no keyboard/mouse input

    def update(self, dt):
        if not self.app.camera.available:
            return

        frame = self.app.camera.read()
        movement_score = 0.0
        if frame is not None:
            self._last_frame = frame
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pose_result = self.app.pose_tracker.process(rgb)
            movement_score = self.scorer.update(pose_result.landmarks)

            if pose_result.landmarks is None:
                self.no_face_timer += dt
            else:
                self.no_face_timer = 0.0

            self.multi_face_timer += dt
            if self.multi_face_timer >= 0.6 and config.MULTI_FACE_CHECK_ENABLED:
                self.multi_face_timer = 0.0
                faces, _ = self.app.face_auth.detect_faces(frame)
                if len(faces) > 1 and not self.state.is_over:
                    self.state.elimination_reason = "Multiple people detected in frame"
                    self.state._end_match("eliminated")

        if (
            not self.state.is_over
            and self.state.phase not in (Phase.WAITING, Phase.COUNTDOWN)
            and self.no_face_timer >= config.NO_FACE_TIMEOUT_SEC
        ):
            self.state.elimination_reason = "Player left the camera frame"
            self.state._end_match("eliminated")

        prev_phase = self.state.phase
        self.state.update(dt, movement_score)
        self._handle_phase_transition_sounds(prev_phase, self.state.phase)

        run_intensity = min(1.0, movement_score / (config.RED_LIGHT_MOVEMENT_THRESHOLD * 2))
        if self.state.phase == Phase.GREEN_LIGHT:
            self.avatar.set_state(AnimState.RUNNING if movement_score >= config.GREEN_LIGHT_MIN_SCORE_TO_MOVE
                                   else AnimState.IDLE)
        elif self.state.phase == Phase.RED_LIGHT:
            self.avatar.set_state(AnimState.FROZEN)
        elif self.state.phase == Phase.ELIMINATED:
            self.avatar.set_state(AnimState.FALLING)
        elif self.state.phase == Phase.VICTORY:
            self.avatar.set_state(AnimState.VICTORY)
        else:
            self.avatar.set_state(AnimState.IDLE)
        self.avatar.update(dt, run_intensity=run_intensity)

        if self.state.is_over:
            self._result_timer += dt
            if not self._recorded:
                self._record_result()
            if self._result_timer >= self.RESULT_DELAY_SEC:
                self.app.screens.goto(ResultsScreen(self.app, self.state, self.practice))

    def _handle_phase_transition_sounds(self, prev, new):
        if prev == new:
            return
        if new == Phase.GREEN_LIGHT:
            self.app.play_sound("green_light")
            if self.app.sound:
                self.app.sound.stop_heartbeat_loop()
        elif new == Phase.RED_LIGHT:
            self.app.play_sound("red_light")
            if self.app.sound:
                self.app.sound.start_heartbeat_loop()
        elif new == Phase.ELIMINATED:
            self.app.play_sound("eliminated")
            if self.app.sound:
                self.app.sound.stop_heartbeat_loop()
        elif new == Phase.VICTORY:
            self.app.play_sound("victory")
            if self.app.sound:
                self.app.sound.stop_heartbeat_loop()

    def _record_result(self):
        self._recorded = True
        if self.practice or not self.app.current_player:
            return
        r = self.state.result
        self.app.db.record_match(
            player_id=self.app.current_player["id"],
            mode="challenge",
            result=r.outcome,
            distance=r.distance,
            time_taken_sec=r.time_taken_sec,
            score=r.score,
            freeze_duration_sec=r.longest_freeze_sec,
        )

    # -- drawing ------------------------------------------------------
    def draw(self, surface):
        surface.fill((10, 12, 16))
        self._draw_arena(surface)
        self._draw_hud(surface)
        self._draw_camera_pip(surface)
        if self.state.flash_warning:
            flash = pygame.Surface((W, H), pygame.SRCALPHA)
            flash.fill((230, 40, 50, 60))
            surface.blit(flash, (0, 0))
        if self.state.is_over:
            self._draw_end_overlay(surface)

    def _draw_arena(self, surface):
        lane = pygame.Rect(W / 2 - 160, 140, 320, H - 260)
        pygame.draw.rect(surface, config.COLOR_BG_ALT, lane, border_radius=4)
        pygame.draw.rect(surface, config.COLOR_GREY, lane, width=2, border_radius=4)

        # finish line
        pygame.draw.rect(surface, config.COLOR_GOLD, (lane.x, lane.y, lane.width, 6))

        # doll
        doll_x, doll_y = lane.centerx, lane.y - 60
        is_red = self.state.phase == Phase.RED_LIGHT
        doll_color = config.COLOR_RED if is_red else config.COLOR_WHITE
        pygame.draw.polygon(surface, doll_color, [
            (doll_x - 26, doll_y + 40), (doll_x + 26, doll_y + 40), (doll_x, doll_y - 20)
        ])
        pygame.draw.circle(surface, doll_color, (doll_x, doll_y - 30), 18)
        if is_red:
            pygame.draw.circle(surface, (0, 0, 0), (doll_x - 6, doll_y - 33), 3)
            pygame.draw.circle(surface, (0, 0, 0), (doll_x + 6, doll_y - 33), 3)

        # player avatar position along lane (progress: 0 at bottom, 1 at top/finish)
        progress = self.state.progress_fraction
        avatar_y = lane.bottom - progress * (lane.height - 40) - 20
        self.avatar.draw(surface, (lane.centerx, int(avatar_y)))

    def _draw_hud(self, surface):
        player = self.app.current_player or {}
        theme.draw_text(surface, f"{player.get('name', '?')}  ({player.get('game_id', '?')})",
                         18, (20, 20), color=config.COLOR_WHITE)

        phase_label, color = {
            Phase.WAITING: ("WAITING", config.COLOR_GREY),
            Phase.COUNTDOWN: ("GET READY", config.COLOR_GOLD),
            Phase.GREEN_LIGHT: ("GREEN LIGHT", config.COLOR_GREEN),
            Phase.RED_LIGHT: ("RED LIGHT - FREEZE", config.COLOR_RED),
            Phase.ELIMINATED: ("ELIMINATED", config.COLOR_RED),
            Phase.VICTORY: ("VICTORY", config.COLOR_GOLD),
            Phase.TIMEOUT: ("TIME'S UP", config.COLOR_GREY),
        }[self.state.phase]
        theme.draw_text(surface, phase_label, 30, (W / 2, 40), color=color, bold=True, center=True)

        if self.state.phase == Phase.COUNTDOWN:
            remaining = max(0, self.state.phase_duration - self.state.phase_timer)
            theme.draw_text(surface, str(int(remaining) + 1), 80, (W / 2, 100),
                             color=config.COLOR_GOLD, bold=True, center=True)

        time_left = max(0, config.MATCH_TIME_LIMIT_SEC - self.state.elapsed_sec)
        theme.draw_text(surface, f"Time left: {int(time_left)}s", 18, (W - 20, 20),
                         color=config.COLOR_WHITE, center=False)

        bar = pygame.Rect(20, 60, 220, 18)
        theme.draw_progress_bar(surface, bar, self.state.progress_fraction, fg=config.COLOR_GREEN)
        theme.draw_text(surface, "Progress", 14, (20, 82), color=config.COLOR_GREY)

        # prize pool / piggy bank (fun visual tied to score)
        max_ref_score = 1500
        prize_fraction = min(1.0, self.state.score / max_ref_score) if self.state.score else \
            min(1.0, (self.state.distance * 10) / max_ref_score)
        piggy_rect = pygame.Rect(W - 240, 60, 220, 18)
        theme.draw_progress_bar(surface, piggy_rect, prize_fraction, fg=config.COLOR_GOLD)
        theme.draw_text(surface, "Prize Pool", 14, (W - 240, 82), color=config.COLOR_GREY)

        if not self.app.camera.available:
            theme.draw_text(surface, "No camera - movement cannot be detected.", 18,
                             (W / 2, H - 30), color=config.COLOR_RED, center=True)

    def _draw_camera_pip(self, surface):
        if self._last_frame is None:
            return
        small = cv2.resize(self._last_frame, (200, 150))
        cam_surf = bgr_to_surface(small)
        rect = cam_surf.get_rect(bottomleft=(20, H - 20))
        surface.blit(cam_surf, rect)
        pygame.draw.rect(surface, config.COLOR_PINK_DIM, rect, 2)

    def _draw_end_overlay(self, surface):
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        surface.blit(overlay, (0, 0))

        result = self.state.result
        if result is None:
            return
        if result.outcome == "eliminated":
            theme.draw_text(surface, "ELIMINATED", 60, (W / 2, H / 2 - 60),
                             color=config.COLOR_RED, bold=True, center=True)
            reason = getattr(self.state, "elimination_reason", "Moved during Red Light")
            theme.draw_text(surface, reason, 20, (W / 2, H / 2 + 10), center=True,
                             color=config.COLOR_WHITE)
        elif result.outcome == "victory":
            theme.draw_text(surface, "VICTORY!", 60, (W / 2, H / 2 - 60),
                             color=config.COLOR_GOLD, bold=True, center=True)
            theme.draw_text(surface, f"Score: {result.score}", 24, (W / 2, H / 2 + 10),
                             center=True, color=config.COLOR_WHITE)
        else:
            theme.draw_text(surface, "TIME'S UP", 60, (W / 2, H / 2 - 60),
                             color=config.COLOR_GREY, bold=True, center=True)

        player = self.app.current_player or {}
        theme.draw_text(surface, f"PLAYER {player.get('game_id', '?')} - {player.get('name', '?')}",
                         20, (W / 2, H / 2 + 60), center=True, color=config.COLOR_GREY)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return config.COLOR_PINK
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
class ResultsScreen(Screen):
    def __init__(self, app, state: GameState, practice: bool):
        super().__init__(app)
        self.state = state
        self.practice = practice

    def on_enter(self):
        self.retry_btn = theme.Button((W / 2 - 340, 560, 300, 54), "PLAY AGAIN")
        self.menu_btn = theme.Button((W / 2 + 40, 560, 300, 54), "MAIN MENU", accent=config.COLOR_GREY)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.retry_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(GetReadyScreen(self.app, practice=self.practice))
            elif self.menu_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(MainMenuScreen(self.app))

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        self.retry_btn.update(mouse)
        self.menu_btn.update(mouse)

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        r = self.state.result
        theme.draw_text(surface, "MATCH RESULTS", 36, (W / 2, 90), color=config.COLOR_PINK,
                         bold=True, center=True)

        rows = [
            ("Outcome", r.outcome.upper()),
            ("Distance covered", f"{r.distance:.1f} / {config.DISTANCE_TO_WIN:.0f}"),
            ("Time taken", f"{r.time_taken_sec:.1f}s"),
            ("Longest freeze held", f"{r.longest_freeze_sec:.1f}s"),
            ("Score", str(r.score)),
        ]
        panel = pygame.Rect(W / 2 - 260, 160, 520, len(rows) * 44 + 30)
        theme.draw_panel(surface, panel)
        for i, (label, value) in enumerate(rows):
            y = panel.y + 25 + i * 44
            theme.draw_text(surface, label, 20, (panel.x + 25, y), color=config.COLOR_GREY)
            theme.draw_text(surface, value, 20, (panel.right - 25, y), color=config.COLOR_WHITE)

        if self.practice:
            theme.draw_text(surface, "Practice mode - not saved to your stats or the leaderboard.",
                             16, (W / 2, panel.bottom + 25), color=config.COLOR_GREY, center=True)

        self.retry_btn.draw(surface)
        self.menu_btn.draw(surface)


# --------------------------------------------------------------------------- #
# Leaderboard
# --------------------------------------------------------------------------- #
class LeaderboardScreen(Screen):
    def on_enter(self):
        self.back_btn = theme.Button((30, 30, 120, 44), "< Back", size=20, accent=config.COLOR_GREY)
        self.rows = self.app.db.leaderboard(order_by="wins", limit=10)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and self.back_btn.rect.collidepoint(event.pos):
            self.app.screens.goto(MainMenuScreen(self.app))

    def update(self, dt):
        self.back_btn.update(pygame.mouse.get_pos())

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        theme.draw_text(surface, "LEADERBOARD - MOST WINS", 32, (W / 2, 80),
                         color=config.COLOR_PINK, bold=True, center=True)

        header_y = 150
        theme.draw_text(surface, "#", 18, (W / 2 - 380, header_y), color=config.COLOR_GREY)
        theme.draw_text(surface, "PLAYER", 18, (W / 2 - 330, header_y), color=config.COLOR_GREY)
        theme.draw_text(surface, "WINS", 18, (W / 2 + 80, header_y), color=config.COLOR_GREY)
        theme.draw_text(surface, "GAMES", 18, (W / 2 + 180, header_y), color=config.COLOR_GREY)
        theme.draw_text(surface, "BEST DIST.", 18, (W / 2 + 280, header_y), color=config.COLOR_GREY)

        if not self.rows:
            theme.draw_text(surface, "No challenge matches played yet.", 20, (W / 2, 300),
                             color=config.COLOR_GREY, center=True)

        for i, row in enumerate(self.rows):
            y = header_y + 40 + i * 40
            theme.draw_text(surface, str(i + 1), 18, (W / 2 - 380, y))
            theme.draw_text(surface, f"{row['name']} ({row['game_id']})", 18, (W / 2 - 330, y))
            theme.draw_text(surface, str(row["wins"]), 18, (W / 2 + 90, y))
            theme.draw_text(surface, str(row["games_played"]), 18, (W / 2 + 190, y))
            theme.draw_text(surface, f"{row['best_distance']:.0f}", 18, (W / 2 + 290, y))


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #
class ProfileScreen(Screen):
    def on_enter(self):
        self.back_btn = theme.Button((30, 30, 120, 44), "< Back", size=20, accent=config.COLOR_GREY)
        player = self.app.current_player
        self.stats = self.app.db.get_stats(player["id"]) if player else {}
        self.history = self.app.db.match_history_for(player["id"], limit=8) if player else []

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and self.back_btn.rect.collidepoint(event.pos):
            self.app.screens.goto(MainMenuScreen(self.app))

    def update(self, dt):
        self.back_btn.update(pygame.mouse.get_pos())

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        player = self.app.current_player or {}
        theme.draw_text(surface, f"{player.get('name', '?')}", 34, (W / 2, 80),
                         color=config.COLOR_PINK, bold=True, center=True)
        theme.draw_text(surface, player.get("game_id", ""), 18, (W / 2, 116),
                         color=config.COLOR_GOLD, center=True)

        s = self.stats
        fastest = s.get("fastest_time_sec")
        stat_lines = [
            ("Games played", s.get("games_played", 0)),
            ("Wins", s.get("wins", 0)),
            ("Losses", s.get("losses", 0)),
            ("Eliminations suffered", s.get("eliminations", 0)),
            ("Fastest victory", f"{fastest:.1f}s" if fastest else "-"),
            ("Best distance", f"{s.get('best_distance', 0):.0f}"),
            ("Longest freeze held", f"{s.get('longest_freeze_sec', 0):.1f}s"),
            ("Total distance covered", f"{s.get('total_distance', 0):.0f}"),
        ]
        panel = pygame.Rect(W / 2 - 260, 160, 520, len(stat_lines) * 34 + 20)
        theme.draw_panel(surface, panel)
        for i, (label, value) in enumerate(stat_lines):
            y = panel.y + 15 + i * 34
            theme.draw_text(surface, label, 18, (panel.x + 20, y), color=config.COLOR_GREY)
            theme.draw_text(surface, str(value), 18, (panel.right - 20, y), color=config.COLOR_WHITE)

        theme.draw_text(surface, "RECENT MATCHES", 20, (W / 2, panel.bottom + 30),
                         color=config.COLOR_PINK, center=True)
        for i, match in enumerate(self.history[:6]):
            y = panel.bottom + 60 + i * 26
            line = f"{match['mode'].upper():<10} {match['result']:<11} dist {match['distance']:.0f}  score {match['score']}"
            theme.draw_text(surface, line, 16, (W / 2, y), color=config.COLOR_WHITE, center=True)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class SettingsScreen(Screen):
    def on_enter(self):
        self.back_btn = theme.Button((30, 30, 120, 44), "< Back", size=20, accent=config.COLOR_GREY)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and self.back_btn.rect.collidepoint(event.pos):
            self.app.screens.goto(MainMenuScreen(self.app))

    def update(self, dt):
        self.back_btn.update(pygame.mouse.get_pos())

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        theme.draw_text(surface, "SETTINGS", 34, (W / 2, 80), color=config.COLOR_PINK,
                         bold=True, center=True)

        cam_status = "Connected" if self.app.camera.available else f"Unavailable ({self.app.camera.last_error})"
        lines = [
            f"Camera index: {config.CAMERA_INDEX}  -  Status: {cam_status}",
            f"Red Light movement threshold: {config.RED_LIGHT_MOVEMENT_THRESHOLD}",
            f"Match time limit: {config.MATCH_TIME_LIMIT_SEC}s",
            f"Distance to win: {config.DISTANCE_TO_WIN:.0f} units",
            "",
            "To change these, edit src/config.py and restart the game.",
        ]
        for i, line in enumerate(lines):
            theme.draw_text(surface, line, 18, (W / 2, 180 + i * 34), center=True,
                             color=config.COLOR_WHITE if line else config.COLOR_GREY)


# --------------------------------------------------------------------------- #
# Multiplayer: private rooms (create / join by code, no matchmaking)
# --------------------------------------------------------------------------- #
class MultiplayerHomeScreen(Screen):
    def on_enter(self):
        self.back_btn = theme.Button((30, 30, 120, 44), "< Back", size=20, accent=config.COLOR_GREY)
        self.create_btn = theme.Button((W / 2 - 320, 320, 280, 180), "CREATE ROOM",
                                        accent=config.COLOR_GREEN)
        self.join_btn = theme.Button((W / 2 + 40, 320, 280, 180), "JOIN ROOM",
                                      accent=config.COLOR_PINK)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.back_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(ModeSelectScreen(self.app))
            elif self.create_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(CreateRoomScreen(self.app))
            elif self.join_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(JoinRoomScreen(self.app))

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        for b in (self.back_btn, self.create_btn, self.join_btn):
            b.update(mouse)

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        theme.draw_text(surface, "PRIVATE ROOM MULTIPLAYER", 34, (W / 2, 140),
                         color=config.COLOR_PINK, bold=True, center=True)
        theme.draw_text(surface, "No public matchmaking - only someone with your code can join.",
                         16, (W / 2, 190), color=config.COLOR_GREY, center=True)
        self.create_btn.draw(surface)
        self.join_btn.draw(surface)
        theme.draw_text(surface, "Get a code to share with friends", 15,
                         (self.create_btn.rect.centerx, 520), center=True, color=config.COLOR_GREY)
        theme.draw_text(surface, "Enter a friend's code", 15,
                         (self.join_btn.rect.centerx, 520), center=True, color=config.COLOR_GREY)


class CreateRoomScreen(Screen):
    def on_enter(self):
        self.error = None
        self.back_btn = theme.Button((W / 2 - 140, 420, 280, 54), "BACK", accent=config.COLOR_GREY)
        try:
            server = RoomServer()
            server.start()
        except OSError as exc:
            self.error = f"Could not start room server: {exc}"
            return

        player = self.app.current_player or {
            "game_id": "GUEST", "name": "Player", "avatar_color": "#ff2d82"
        }
        try:
            client = RoomClient("127.0.0.1", server.port)
        except OSError as exc:
            server.stop()
            self.error = f"Could not connect to local room server: {exc}"
            return

        client.join(player["game_id"], player["name"], player.get("avatar_color", "#ff2d82"))
        self.app.screens.goto(MultiplayerLobbyScreen(self.app, client, server=server, is_host=True))

    def handle_event(self, event):
        if self.error and event.type == pygame.MOUSEBUTTONDOWN and self.back_btn.rect.collidepoint(event.pos):
            self.app.screens.goto(MultiplayerHomeScreen(self.app))

    def update(self, dt):
        if self.error:
            self.back_btn.update(pygame.mouse.get_pos())

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        if self.error:
            theme.draw_text(surface, self.error, 18, (W / 2, 300), color=config.COLOR_RED, center=True)
            self.back_btn.draw(surface)
        else:
            theme.draw_text(surface, "Starting room...", 24, (W / 2, H / 2),
                             color=config.COLOR_WHITE, center=True)


class JoinRoomScreen(Screen):
    def on_enter(self):
        self.back_btn = theme.Button((30, 30, 120, 44), "< Back", size=20, accent=config.COLOR_GREY)
        self.connect_btn = theme.Button((W / 2 - 140, 460, 280, 54), "CONNECT")
        self.code_buffer = ""
        self.error = None

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.back_btn.rect.collidepoint(event.pos):
                self.app.screens.goto(MultiplayerHomeScreen(self.app))
            elif self.connect_btn.rect.collidepoint(event.pos):
                self._try_connect()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._try_connect()
            elif event.key == pygame.K_BACKSPACE:
                self.code_buffer = self.code_buffer[:-1]
            elif event.unicode.isprintable() and len(self.code_buffer) < 24:
                self.code_buffer += event.unicode

    def _try_connect(self):
        code = self.code_buffer.strip()
        if not code:
            return
        try:
            ip, port = decode_room_code(code)
            client = RoomClient(ip, port)
        except (ValueError, OSError) as exc:
            self.error = f"Couldn't join: {exc}"
            return

        player = self.app.current_player or {
            "game_id": "GUEST", "name": "Player", "avatar_color": "#23dc82"
        }
        client.join(player["game_id"], player["name"], player.get("avatar_color", "#23dc82"))
        self.app.screens.goto(MultiplayerLobbyScreen(self.app, client, server=None, is_host=False))

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        self.back_btn.update(mouse)
        self.connect_btn.update(mouse)

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        theme.draw_text(surface, "JOIN ROOM", 34, (W / 2, 100), color=config.COLOR_PINK,
                         bold=True, center=True)
        theme.draw_text(surface, "Enter the room code your friend shared with you", 18,
                         (W / 2, 160), color=config.COLOR_GREY, center=True)
        box = pygame.Rect(W / 2 - 220, 260, 440, 54)
        theme.draw_panel(surface, box)
        theme.draw_text(surface, self.code_buffer + "|", 24, box.center, center=True)
        self.connect_btn.draw(surface)
        if self.error:
            theme.draw_text(surface, self.error, 16, (W / 2, 540), color=config.COLOR_RED, center=True)


class MultiplayerLobbyScreen(Screen):
    def __init__(self, app, client: RoomClient, server, is_host: bool):
        super().__init__(app)
        self.client = client
        self.server = server
        self.is_host = is_host

    def on_enter(self):
        self.back_btn = theme.Button((30, 30, 120, 44), "LEAVE", size=20, accent=config.COLOR_RED)
        self.ready_btn = theme.Button((W / 2 - 320, 600, 280, 54), "READY UP", accent=config.COLOR_GREEN)
        self.start_btn = theme.Button((W / 2 + 40, 600, 280, 54), "START MATCH")
        self.is_ready = False
        self.error = None

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.back_btn.rect.collidepoint(event.pos):
                self._leave()
            elif self.ready_btn.rect.collidepoint(event.pos):
                self.is_ready = not self.is_ready
                self.client.set_ready(self.is_ready)
            elif self.is_host and self.start_btn.rect.collidepoint(event.pos):
                self.client.request_start()

    def _leave(self):
        self.client.close()
        if self.server:
            self.server.stop()
        self.app.screens.goto(MainMenuScreen(self.app))

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        for b in (self.back_btn, self.ready_btn, self.start_btn):
            b.update(mouse)

        if not self.client.connected:
            self.error = "Disconnected from host."
            return

        if self.client.start_rejected_reason:
            self.error = self.client.start_rejected_reason

        if self.client.match_starting:
            self.app.screens.goto(
                MultiplayerGameScreen(self.app, self.client, self.server, self.is_host)
            )

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        self.back_btn.draw(surface)
        theme.draw_text(surface, "WAITING LOBBY", 34, (W / 2, 80), color=config.COLOR_PINK,
                         bold=True, center=True)

        lobby = self.client.latest_lobby
        room_code = lobby.get("room_code") if lobby else (self.server.room_code if self.server else "...")
        theme.draw_text(surface, f"ROOM CODE:  {room_code}", 26, (W / 2, 130),
                         color=config.COLOR_GOLD, bold=True, center=True)
        if self.is_host:
            theme.draw_text(surface, "Share this code with a friend on your network to let them join.",
                             15, (W / 2, 165), color=config.COLOR_GREY, center=True)

        players = lobby.get("players", []) if lobby else []
        panel = pygame.Rect(W / 2 - 260, 210, 520, max(160, len(players) * 44 + 30))
        theme.draw_panel(surface, panel)
        if not players:
            theme.draw_text(surface, "Connecting...", 18, panel.center, center=True, color=config.COLOR_GREY)
        for i, p in enumerate(players):
            y = panel.y + 20 + i * 44
            tag = " (HOST)" if p["is_host"] else ""
            theme.draw_text(surface, f"{p['name']}{tag}", 20, (panel.x + 25, y), color=config.COLOR_WHITE)
            ready_color = config.COLOR_GREEN if p["ready"] else config.COLOR_GREY
            theme.draw_text(surface, "READY" if p["ready"] else "NOT READY", 16,
                             (panel.right - 150, y), color=ready_color)

        self.ready_btn.text = "UNREADY" if self.is_ready else "READY UP"
        self.ready_btn.accent = config.COLOR_GREY if self.is_ready else config.COLOR_GREEN
        self.ready_btn.draw(surface)

        if self.is_host:
            self.start_btn.draw(surface)
        else:
            theme.draw_text(surface, "Waiting for the host to start the match...", 16,
                             self.start_btn.rect.center, center=True, color=config.COLOR_GREY)

        if self.error:
            theme.draw_text(surface, self.error, 16, (W / 2, panel.bottom + 70),
                             color=config.COLOR_RED, center=True)


class MultiplayerGameScreen(Screen):
    RESULT_DELAY_SEC = 2.5

    def __init__(self, app, client: RoomClient, server, is_host: bool):
        super().__init__(app)
        self.client = client
        self.server = server
        self.is_host = is_host

    def on_enter(self):
        self.scorer = MovementScorer()
        self.avatars: dict[str, Avatar] = {}
        self._prev_phase = None
        self._last_frame = None
        self._result_timer = 0.0
        self._recorded = False
        player = self.app.current_player or {}
        self.my_game_id = player.get("game_id", "GUEST")
        self._my_last_score = 0.0

    def handle_event(self, event):
        pass  # camera-driven, like single-player GameScreen

    def update(self, dt):
        if not self.client.connected:
            self.app.screens.goto(MainMenuScreen(self.app))
            return

        movement_score = 0.0
        if self.app.camera.available:
            frame = self.app.camera.read()
            if frame is not None:
                self._last_frame = frame
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pose_result = self.app.pose_tracker.process(rgb)
                movement_score = self.scorer.update(pose_result.landmarks)
        self._my_last_score = movement_score
        self.client.send_movement(movement_score)

        state = self.client.latest_state
        if not state:
            return

        phase = state["phase"]
        if phase != self._prev_phase:
            self._handle_phase_transition_sounds(phase)
            self._prev_phase = phase

        winner_id = state.get("winner_game_id")
        for gid, pdata in state["players"].items():
            avatar = self.avatars.get(gid)
            if avatar is None:
                avatar = Avatar(color=_hex_to_rgb(pdata["avatar_color"]), name=pdata["name"])
                self.avatars[gid] = avatar

            if pdata["finished"]:
                anim = AnimState.VICTORY if gid == winner_id else AnimState.IDLE
            elif not pdata["alive"]:
                anim = AnimState.FALLING
            elif phase == "RED":
                anim = AnimState.FROZEN
            elif phase == "GREEN":
                if gid == self.my_game_id:
                    anim = AnimState.RUNNING if movement_score >= config.GREEN_LIGHT_MIN_SCORE_TO_MOVE else AnimState.IDLE
                else:
                    # remote players: we only receive their distance, not a live
                    # per-frame score, so approximate "running" during green light.
                    anim = AnimState.RUNNING
            else:
                anim = AnimState.IDLE
            avatar.set_state(anim)

            run_intensity = (
                min(1.0, movement_score / (config.RED_LIGHT_MOVEMENT_THRESHOLD * 2))
                if gid == self.my_game_id else 0.5
            )
            avatar.update(dt, run_intensity=run_intensity)

        if state.get("over"):
            self._result_timer += dt
            if not self._recorded:
                self._record_result(state)
            if self._result_timer >= self.RESULT_DELAY_SEC:
                self.app.screens.goto(
                    MultiplayerResultsScreen(self.app, state, self.client, self.server, self.is_host)
                )

    def _handle_phase_transition_sounds(self, new_phase):
        if new_phase == "GREEN":
            self.app.play_sound("green_light")
            if self.app.sound:
                self.app.sound.stop_heartbeat_loop()
        elif new_phase == "RED":
            self.app.play_sound("red_light")
            if self.app.sound:
                self.app.sound.start_heartbeat_loop()
        elif new_phase == "FINISHED":
            if self.app.sound:
                self.app.sound.stop_heartbeat_loop()

    def _record_result(self, state):
        self._recorded = True
        if not self.app.current_player:
            return
        me = state["players"].get(self.my_game_id)
        if not me:
            return
        if state.get("winner_game_id") == self.my_game_id:
            outcome = "victory"
        elif not me["alive"]:
            outcome = "eliminated"
        else:
            outcome = "timeout"
        self.app.db.record_match(
            player_id=self.app.current_player["id"],
            mode="multiplayer",
            result=outcome,
            distance=me["distance"],
            time_taken_sec=state["elapsed_sec"],
            score=me["score"],
            freeze_duration_sec=me["longest_freeze_sec"],
        )

    def draw(self, surface):
        surface.fill((10, 12, 16))
        state = self.client.latest_state
        if not state:
            theme.draw_text(surface, "Connecting to match...", 24, (W / 2, H / 2),
                             center=True, color=config.COLOR_WHITE)
            return

        phase = state["phase"]
        players = state["players"]
        n = max(1, len(players))
        lane_w = min(260, (W - 80) // n)
        total_w = lane_w * n
        start_x = W / 2 - total_w / 2

        doll_x, doll_y = W / 2, 90
        is_red = phase == "RED"
        doll_color = config.COLOR_RED if is_red else config.COLOR_WHITE
        pygame.draw.polygon(surface, doll_color, [
            (doll_x - 26, doll_y + 40), (doll_x + 26, doll_y + 40), (doll_x, doll_y - 20)
        ])
        pygame.draw.circle(surface, doll_color, (doll_x, doll_y - 30), 18)

        lane_top, lane_bottom = 170, H - 100
        for i, (gid, pdata) in enumerate(players.items()):
            lane_x = start_x + i * lane_w
            lane = pygame.Rect(lane_x + 10, lane_top, lane_w - 20, lane_bottom - lane_top)
            pygame.draw.rect(surface, config.COLOR_BG_ALT, lane, border_radius=4)
            border_color = config.COLOR_GOLD if gid == self.my_game_id else config.COLOR_GREY
            pygame.draw.rect(surface, border_color, lane, width=2, border_radius=4)
            pygame.draw.rect(surface, config.COLOR_GOLD, (lane.x, lane.y, lane.width, 5))

            progress = min(1.0, pdata["distance"] / config.DISTANCE_TO_WIN)
            avatar_y = lane.bottom - progress * (lane.height - 40) - 20
            avatar = self.avatars.get(gid)
            if avatar:
                avatar.draw(surface, (lane.centerx, int(avatar_y)))

            label = pdata["name"] + (" (YOU)" if gid == self.my_game_id else "")
            theme.draw_text(surface, label, 14, (lane.centerx, lane.bottom + 16),
                             center=True, color=config.COLOR_WHITE)
            if not pdata["alive"] and not pdata["finished"]:
                theme.draw_text(surface, "OUT", 15, (lane.centerx, lane.top - 16),
                                 center=True, color=config.COLOR_RED)
            elif pdata["finished"]:
                theme.draw_text(surface, "FINISHED", 13, (lane.centerx, lane.top - 16),
                                 center=True, color=config.COLOR_GOLD)

        phase_label, color = {
            "WAITING": ("WAITING", config.COLOR_GREY),
            "COUNTDOWN": ("GET READY", config.COLOR_GOLD),
            "GREEN": ("GREEN LIGHT", config.COLOR_GREEN),
            "RED": ("RED LIGHT - FREEZE", config.COLOR_RED),
            "FINISHED": ("MATCH OVER", config.COLOR_GOLD),
        }.get(phase, (phase, config.COLOR_WHITE))
        theme.draw_text(surface, phase_label, 26, (W / 2, 30), color=color, bold=True, center=True)

        if phase == "COUNTDOWN":
            remaining = max(0, state["phase_duration"] - state["phase_timer"])
            theme.draw_text(surface, str(int(remaining) + 1), 56, (W / 2, 120),
                             color=config.COLOR_GOLD, bold=True, center=True)

        time_left = max(0, config.MATCH_TIME_LIMIT_SEC - state["elapsed_sec"])
        theme.draw_text(surface, f"Time left: {int(time_left)}s", 16, (W - 140, 20),
                         color=config.COLOR_WHITE)

        if self._last_frame is not None:
            small = cv2.resize(self._last_frame, (180, 135))
            cam_surf = bgr_to_surface(small)
            rect = cam_surf.get_rect(bottomleft=(20, H - 20))
            surface.blit(cam_surf, rect)
            pygame.draw.rect(surface, config.COLOR_PINK_DIM, rect, 2)
        if not self.app.camera.available:
            theme.draw_text(surface, "No camera - your movement can't be sent.", 16,
                             (W / 2, H - 30), color=config.COLOR_RED, center=True)


class MultiplayerResultsScreen(Screen):
    def __init__(self, app, state: dict, client: RoomClient, server, is_host: bool):
        super().__init__(app)
        self.state = state
        self.client = client
        self.server = server
        self.is_host = is_host

    def on_enter(self):
        self.leave_btn = theme.Button((W / 2 - 140, 600, 280, 54), "LEAVE ROOM")

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and self.leave_btn.rect.collidepoint(event.pos):
            self.client.close()
            if self.server:
                self.server.stop()
            self.app.screens.goto(MainMenuScreen(self.app))

    def update(self, dt):
        self.leave_btn.update(pygame.mouse.get_pos())

    def draw(self, surface):
        surface.fill(config.COLOR_BG)
        theme.draw_text(surface, "MATCH RESULTS", 36, (W / 2, 80), color=config.COLOR_PINK,
                         bold=True, center=True)
        winner_id = self.state.get("winner_game_id")
        players = self.state["players"]
        if winner_id and winner_id in players:
            theme.draw_text(surface, f"WINNER: {players[winner_id]['name']}", 28, (W / 2, 140),
                             color=config.COLOR_GOLD, bold=True, center=True)
        else:
            theme.draw_text(surface, "NO SURVIVORS", 28, (W / 2, 140),
                             color=config.COLOR_RED, bold=True, center=True)

        rows = sorted(players.items(), key=lambda kv: -kv[1]["distance"])
        panel = pygame.Rect(W / 2 - 300, 200, 600, len(rows) * 40 + 30)
        theme.draw_panel(surface, panel)
        for i, (gid, p) in enumerate(rows):
            y = panel.y + 20 + i * 40
            if gid == winner_id:
                status = "WINNER"
            elif p["finished"]:
                status = "FINISHED"
            elif not p["alive"]:
                status = "ELIMINATED"
            else:
                status = "-"
            theme.draw_text(surface, p["name"], 18, (panel.x + 20, y), color=config.COLOR_WHITE)
            theme.draw_text(surface, f"dist {p['distance']:.0f}", 16, (panel.x + 220, y),
                             color=config.COLOR_GREY)
            theme.draw_text(surface, status, 16, (panel.right - 160, y),
                             color=config.COLOR_GOLD if status == "WINNER" else config.COLOR_WHITE)

        self.leave_btn.draw(surface)
