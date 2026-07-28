"""
Auth REST endpoints:
  POST /api/register/start          – init registration, return game_id
  POST /api/register/sample         – upload one face frame
  POST /api/register/complete       – retrain model, auto-login
  POST /api/login/face              – send webcam frame, get session
  POST /api/login/guest             – simple name-only guest login (no face)
  DELETE /api/logout                – clear session
"""
from __future__ import annotations

import base64

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from src import config
from src.database import Database
from src.face_auth import FaceAuth
from server import session as sess

router = APIRouter(prefix="/api")

# Shared singletons (initialised once in main.py and injected via module-level refs)
_db: Database | None = None
_face_auth: FaceAuth | None = None


def init(db: Database, face_auth: FaceAuth) -> None:
    global _db, _face_auth
    _db = db
    _face_auth = face_auth


def _get_db() -> Database:
    if _db is None:
        raise HTTPException(500, "DB not initialised")
    return _db


def _get_fa() -> FaceAuth:
    if _face_auth is None:
        raise HTTPException(500, "FaceAuth not initialised")
    return _face_auth


def _decode_frame(b64: str) -> np.ndarray:
    """Decode a base64-encoded JPEG/PNG frame into a BGR numpy array."""
    try:
        raw = base64.b64decode(b64.split(",")[-1])  # strip data:image/jpeg;base64, prefix
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image")
        return img
    except Exception as exc:
        raise HTTPException(400, f"Bad image data: {exc}") from exc


# Profile face cascade (for left/right angle detection)
_profile_cascade: Optional[cv2.CascadeClassifier] = None


def _get_profile_cascade() -> cv2.CascadeClassifier:
    global _profile_cascade
    if _profile_cascade is None:
        path = cv2.data.haarcascades + "haarcascade_profileface.xml"
        _profile_cascade = cv2.CascadeClassifier(path)
    return _profile_cascade


def _extract_face_crop(fa: FaceAuth, frame: np.ndarray, angle: str) -> np.ndarray:
    """
    Extract a face crop for any angle:
    - Front: standard frontal Haar cascade
    - Left/Right: try frontal → profile cascade → centre-crop fallback
    The fallback always succeeds so registration never hard-blocks on a
    missed detection (LBPH can still learn from partial side-face images).
    """
    # Always try frontal cascade first (works even on slight turns)
    _, face_crop = fa.largest_face(frame)
    if face_crop is not None:
        return face_crop

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    if angle in ("left", "right"):
        profile = _get_profile_cascade()
        # Profile cascade is trained on left profiles; flip for right
        detect_gray = cv2.flip(gray, 1) if angle == "right" else gray
        faces = profile.detectMultiScale(
            detect_gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60)
        )
        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            if angle == "right":
                x = gray.shape[1] - x - w  # un-flip x
            crop = gray[y: y + h, x: x + w]
            return cv2.resize(crop, (200, 200))

    # Fallback: generous centre-crop — always succeeds
    h, w = gray.shape
    cx, cy = w // 2, int(h * 0.38)
    size = min(h, w) // 3
    y1 = max(0, cy - size)
    y2 = min(h, cy + size)
    x1 = max(0, cx - size)
    x2 = min(w, cx + size)
    crop = gray[y1:y2, x1:x2]
    if crop.size > 0:
        return cv2.resize(crop, (200, 200))

    # Absolute last resort — resize entire grey frame
    return cv2.resize(gray, (200, 200))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class StartRegisterRequest(BaseModel):
    name: str


class SampleRequest(BaseModel):
    name: str
    angle: str          # "front" | "left" | "right"
    frame_b64: str      # data:image/jpeg;base64,....


class LoginFaceRequest(BaseModel):
    frame_b64: str


class GuestLoginRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register/start")
async def register_start(req: StartRegisterRequest):
    db = _get_db()
    # Check if name already exists
    players = db.list_players()
    if any(p["name"].lower() == req.name.strip().lower() for p in players):
        raise HTTPException(409, f"Name '{req.name}' is already taken.")
    sess.init_registration(req.name.strip())
    return {"ok": True, "name": req.name.strip()}


@router.post("/register/sample")
async def register_sample(req: SampleRequest):
    fa = _get_fa()
    if req.angle not in config.FACE_ANGLES:
        raise HTTPException(400, f"angle must be one of {config.FACE_ANGLES}")

    frame = _decode_frame(req.frame_b64)
    # Use smart extraction: frontal → profile → centre-crop fallback
    face_crop = _extract_face_crop(fa, frame, req.angle)
    if face_crop is None:
        return {"ok": False, "reason": "no_face"}

    name = req.name.strip()
    count = sess.increment_sample(name, req.angle)
    fa.save_sample(f"__pending_{name}", req.angle, count, face_crop)
    progress = sess.registration_progress(name)
    return {"ok": True, "progress": progress, "count": count}



@router.post("/register/complete")
async def register_complete(req: StartRegisterRequest):
    db = _get_db()
    fa = _get_fa()
    name = req.name.strip()

    progress = sess.registration_progress(name)
    total = sum(progress.values())
    if total < 3:  # need at least 1 sample per angle
        raise HTTPException(400, "Not enough face samples collected.")

    # Create player in DB
    player = db.create_player(name)
    game_id = player["game_id"]

    # Rename face sample dir from __pending_name -> game_id
    import os, shutil
    pending_dir = fa.sample_dir_for(f"__pending_{name}")
    final_dir = fa.sample_dir_for(game_id)
    if os.path.exists(pending_dir):
        if os.path.exists(final_dir):
            shutil.rmtree(final_dir)
        shutil.move(pending_dir, final_dir)

    # Retrain LBPH model with new player
    fa.retrain()
    sess.clear_registration(name)

    # Auto-login
    session_id = sess.create_session(player)
    return {"ok": True, "session_id": session_id, "player": player}


@router.post("/login/face")
async def login_face(req: LoginFaceRequest):
    fa = _get_fa()
    db = _get_db()

    frame = _decode_frame(req.frame_b64)
    game_id, confidence = fa.recognize(frame)
    if game_id is None:
        return {"ok": False, "reason": "no_match"}

    player = db.get_player_by_game_id(game_id)
    if player is None:
        return {"ok": False, "reason": "player_not_found"}

    session_id = sess.create_session(player)
    return {"ok": True, "session_id": session_id, "player": player, "confidence": confidence}


@router.post("/login/guest")
async def login_guest(req: GuestLoginRequest):
    """Simple no-face login by name — useful when face model has no data yet."""
    db = _get_db()
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Name is required")

    players = db.list_players()
    player = next((p for p in players if p["name"].lower() == name.lower()), None)
    if player is None:
        player = db.create_player(name)

    session_id = sess.create_session(player)
    return {"ok": True, "session_id": session_id, "player": player}


@router.delete("/logout")
async def logout(x_session_id: Optional[str] = Header(None)):
    if x_session_id:
        sess.delete_session(x_session_id)
    return {"ok": True}


@router.get("/me")
async def me(x_session_id: Optional[str] = Header(None)):
    if not x_session_id:
        raise HTTPException(401, "No session")
    player = sess.get_player(x_session_id)
    if not player:
        raise HTTPException(401, "Invalid or expired session")
    return player
