# Red Light, Green Light

A computer-vision-powered recreation of Red Light, Green Light — **your
body is the controller.** A webcam watches you; a pose estimation model
measures how much you move; move too much while the doll's back is turned
and you're eliminated.

This build includes **single-player** (Practice + Challenge) and **private
room multiplayer** — one player creates a room and shares a short code
directly with a friend, who joins with it. There is **no public
matchmaking, no lobby of strangers, and no central server anywhere** in
this build. See [How multiplayer actually works](#how-multiplayer-actually-works)
for exactly what that means technically.

---

## What's actually in this build

| Feature | Status |
|---|---|
| Face registration (name + front/left/right capture) | done |
| Face-recognition login (no passwords) | done |
| Player profiles, Game ID, stats, match history | done |
| Pose-estimation movement detection | done |
| Red Light / Green Light state machine | done |
| Elimination sequence + reason display | done |
| Practice mode (no elimination) & Challenge mode (single-player) | done |
| Private room multiplayer - create a room, get a code, friend joins with it | done |
| Animated 2D stylized avatar (idle/run/freeze/fall/victory) | done |
| Prize-pool ("piggy bank") score visual | done |
| Local leaderboard, profile & stats screen | done |
| Original synthesized sound effects | done |
| Basic anti-cheat (no-face timeout, multi-face detection) | done |
| Public matchmaking / stranger pairing | not included, by request |
| 3D rigged characters | not included (procedural 2D avatar instead - see below) |

---

## Quick start

### 1. Requirements
- Python 3.10-3.12
- A working webcam
- Windows, macOS, or Linux (mediapipe/OpenCV all support these)
- For multiplayer: both players on the same Wi-Fi/LAN is the easy path
  (see multiplayer section below for playing across the internet)

### 2. Install
```bash
cd redlight-greenlight
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> **If `pip install mediapipe` fails on an ARM Mac or Raspberry Pi:**
> mediapipe's official wheels are strongest on x86_64. On ARM, try
> `pip install mediapipe-silicon` (Apple Silicon) or run inside a
> Docker image built for your platform.

### 3. Run
```bash
python main.py
```

A window opens. If your webcam isn't detected, the app still launches (you
see a warning) but registration/login/gameplay need a real camera to do
anything meaningful.

### 4. First time playing
1. **Register New Player** -> type your name -> turn your head front / left /
   right on cue while the camera captures samples for each angle.
2. You're logged in automatically after registering.
3. From the Main Menu -> **Play** -> **Practice** (learn the controls, no
   elimination), **Challenge** (single-player, full rules), or
   **Multiplayer** (private room with a friend - see below).
4. Stand back far enough that your upper body is visible. Move freely on
   **GREEN LIGHT**. Freeze completely on **RED LIGHT**. Reach the doll
   (100% progress) before the clock runs out to win.
5. Next time you launch the game, use **Login (Face Scan)** instead of
   registering again - just look at the camera.

---

## Playing multiplayer

Each player runs their **own copy** of this project on their **own
machine**, with their own registered profile.

**To host:**
1. Main Menu -> Play -> Multiplayer -> **Create Room**.
2. You land in a waiting lobby showing a **room code** (something like
   `YAAAEAVQ7U`). Send that code to your friend however you like - text,
   Discord, voice call. That's the only thing they need.
3. Click **Ready Up**. Once every player in the lobby is marked ready,
   click **Start Match**.

**To join:**
1. Main Menu -> Play -> Multiplayer -> **Join Room**.
2. Type in the code your friend sent you -> **Connect**.
3. You land in the same waiting lobby they're in. Click **Ready Up**
   and wait for the host to start.

**During the match:** everyone's lane is shown side by side, sharing one
red/green light cycle. Movement is measured locally from each player's own
webcam and sent up to the host as just a number (a movement score) - not
video - so it works fine even on a slow connection. Whoever finishes first
wins; if everyone else is eliminated, the last player standing wins;
if time runs out, whoever's furthest along wins.

### Does this need port forwarding?
- **Same Wi-Fi/LAN as your friend:** no extra setup. The room code already
  encodes the host's local IP address and port.
- **Different networks (playing over the actual internet):** the host
  needs to either port-forward the port shown in their room code on their
  router, or both players connect through something like Tailscale/
  Hamachi/ZeroTier first so they're effectively on the same virtual LAN.
  There's no relay/matchmaking server here doing that NAT traversal for
  you - that's the deliberate tradeoff for not standing up any kind of
  public server or stranger-facing service.

---

## How multiplayer actually works

There is **no matchmaking server, no room directory, and no way to
discover other people's rooms.** "Create Room" starts a small TCP server
directly on the host's own machine (`src/multiplayer/server.py`), bound to
whatever free port the OS hands out. The "room code" you see and share is
nothing more than that host's IP address and port, packed into a short
base32 string (`src/multiplayer/protocol.py`):

```
encode_room_code("192.168.1.42", 51234) -> "YAAAEAVQ7U"
```

A friend typing that code into **Join Room** just decodes it back into an
IP + port and connects directly to the host - the same as if they'd typed
the address by hand, just shorter and copy-pasteable. Nothing about this
code is looked up anywhere; there's no server-side table mapping codes to
rooms. That's what makes this "room creation + join by code" rather than
"matchmaking" - the only way to find a room is to be handed its code by
the person hosting it.

Once connected, the server is **authoritative**: it owns the single shared
red/green light timer and decides who's eliminated
(`src/multiplayer/match_state.py`, unit-tested in
`tests/test_multiplayer_match.py`). Each client only ever sends its own
`movement_score` (a small float, computed locally from that player's own
webcam) and receives back the full match state to render.

---

## How the core mechanic works

```
Webcam frame
   |
   v
MediaPipe Pose  ->  33 body landmarks (x, y, visibility)
   |
   v
MovementScorer  ->  average landmark displacement vs. previous frame,
                     smoothed over a short rolling window
   |
   v
GameState / MultiplayerMatch  ->  during GREEN LIGHT: movement -> forward
                     progress. During RED LIGHT: movement above threshold
                     for N consecutive frames -> eliminated.
```

- **No YOLO or person detector is used.** MediaPipe Pose already localizes
  a single person in frame on its own, which is all a single-camera game
  needs (each multiplayer participant still only has one person in front
  of their own webcam). YOLO + ByteTrack only start to matter once you
  need to detect/track *multiple* people sharing *one* camera frame - see
  Growing this project below.
- Movement during Green Light is **not** literal "walk toward the camera"
  - webcams can't reliably measure depth/forward translation. Instead it
  measures overall body-movement intensity (think: jogging in place, arm
  pumping) and maps that intensity to your character's forward speed.
- A short **grace period** (`RED_LIGHT_GRACE_PERIOD_SEC` in `config.py`)
  after the light turns red gives you time to actually stop, rather than
  eliminating you for momentum.

All thresholds (movement sensitivity, grace period, timers, distance-to-win)
live in **`src/config.py`** - tune the game there without touching any
gameplay logic. Both single-player and multiplayer share the exact same
constants, so a balance change applies to both modes at once.

---

## Project structure

```
redlight-greenlight/
|-- main.py                  # entry point
|-- requirements.txt
|-- src/
|   |-- config.py             # every tunable constant
|   |-- database.py           # SQLite: players, stats, match history (per-install, local)
|   |-- face_auth.py          # registration + face-recognition login (OpenCV LBPH)
|   |-- pose_tracker.py       # MediaPipe pose + movement scoring
|   |-- game_state.py         # single-player Red/Green Light rules
|   |-- avatar.py             # procedural 2D character rendering & animation
|   |-- sound_manager.py      # synthesizes all SFX at runtime (numpy)
|   |-- app.py                # camera handling, service wiring, main loop
|   |-- multiplayer/
|   |   |-- protocol.py       # room code encode/decode, JSON-line socket framing
|   |   |-- match_state.py    # server-authoritative multiplayer rules (N players, one light cycle)
|   |   |-- server.py         # RoomServer - what "Create Room" starts
|   |   `-- client.py         # RoomClient - what both host & guest use to talk to the server
|   `-- ui/
|       |-- theme.py          # shared colors/fonts/buttons
|       |-- screen_manager.py # tiny screen-stack controller
|       `-- screens.py        # every screen (menu, registration, single + multiplayer game, etc.)
|-- tests/
|   |-- test_game_state.py           # single-player rules, no camera needed
|   |-- test_movement_scoring.py     # movement scoring math, no camera needed
|   `-- test_multiplayer_match.py    # multiplayer rules, no sockets/camera needed
`-- data/                     # created at runtime: SQLite DB + face samples
```

`game_state.py`, `multiplayer/match_state.py`, and `pose_tracker.py`'s
scoring logic are all kept free of pygame/OpenCV/socket imports on
purpose, which is why they're unit-testable without a webcam or a network:
```bash
pip install pytest
pytest tests/ -v
```

---

## Design decisions worth knowing about

**Why LBPH face recognition instead of InsightFace/ArcFace embeddings?**
Deep embedding models (InsightFace, dlib-based face_recognition) need
compiled binaries that are genuinely painful to install cross-platform
(especially dlib on Windows). OpenCV's Haar cascade (detection) + LBPH
(recognition) ship inside `opencv-contrib-python` with zero extra install
steps and are accurate enough for "one known person logging in on their
own webcam." It is **not** accurate enough for anti-spoofing-grade
security - see Anti-cheat below.

**Why a room-code direct-connect instead of a matchmaking service?**
That's what was asked for: multiplayer without any stranger-pairing or
central server. It also means there's nothing to host, pay for, or keep
running server-side - the "server" only exists for the lifetime of one
match, on the host's own machine.

**Why a procedural 2D avatar instead of a rigged 3D character?**
A fully animated 3D-style human character with idle/run/freeze/eliminate/
victory/fall animations is a real game-art asset pipeline (modeling,
rigging, animating, exporting) - normally a small team's dedicated job.
The current avatar is drawn from primitives (circle head, line limbs) with
sinusoidal animation, and reads clearly as running/frozen/falling/
celebrating. If/when you want true 3D: Three.js/Babylon.js is the right
target, driven by the exact same `AnimState` enum this build already uses.

**Why synthesized sound instead of a licensed soundtrack?**
Every sound effect (countdown, red/green light stinger, heartbeat,
elimination buzzer, victory fanfare) is generated at runtime from sine/
square waves in `sound_manager.py` - original, royalty-free, and instantly
retunable by editing frequencies/durations in that one file.

---

## Anti-cheat (what's actually implemented)

- **No-face timeout**: if pose tracking loses the player for
  `NO_FACE_TIMEOUT_SEC` (default 6s) during an active round, they're
  disqualified as "left the frame."
- **Multiple people detected**: a periodic Haar-cascade face count flags
  more than one face in frame as "multiple people detected" and ends the
  match (single-player mode currently - see Growing this project).
- **Disconnect handling**: if a player drops mid-multiplayer-match, they're
  treated as eliminated rather than silently erased, so the win condition
  for whoever's left stays correct.
- **Not implemented** (flagged honestly rather than faked): frozen/recorded
  video detection, camera-covered detection, and deep anti-spoofing. These
  need either liveness-detection models or multi-frame statistical checks
  that are a project in their own right.

---

## Growing this project further

- **Spectator mode**: an eliminated multiplayer player currently just sees
  the "LEAVE ROOM" results screen at match end - extending
  `MultiplayerGameScreen` to keep receiving `state_update` messages after
  your own elimination (instead of only until match end) would let them
  keep watching live.
- **More than one room per host / room browser**: not needed for the
  "one friend joins with a code" use case this was built for, but
  `RoomServer` could be generalized to manage multiple `MultiplayerMatch`
  instances keyed by a room ID if you wanted a host to run several rooms
  from one machine.
- **YOLOv11 + ByteTrack** become relevant the moment you need multiple
  people in *one* camera frame (local co-op sharing a single webcam, or a
  stronger multi-face anti-cheat check in multiplayer too) - add them as a
  pre-processing step before `PoseTracker`, cropping each detected person
  before running pose estimation on them individually.
- **NAT traversal / internet play without port forwarding** would need
  either a lightweight relay/rendezvous server (a small piece of always-on
  infrastructure) or WebRTC-style hole punching - both bigger asks than
  the direct-connect approach used here, and both would need to be built
  without turning into the public matchmaking this project was
  specifically asked not to have.

---

## Troubleshooting

- **"Could not open camera index 0"** - another app (Zoom, Teams, browser
  tab) may be holding the webcam. Close it and relaunch, or change
  `CAMERA_INDEX` in `src/config.py` if you have multiple cameras.
- **Face login keeps failing** - re-register in better, even lighting;
  LBPH is sensitive to lighting changes between registration and login.
- **Getting eliminated when you didn't move** - your webcam's frame rate
  or lighting may be introducing jitter the pose model reads as movement.
  Raise `RED_LIGHT_MOVEMENT_THRESHOLD` slightly in `src/config.py`.
- **Friend can't join my room** - check you're on the same Wi-Fi network,
  that no firewall is blocking the port, and that the code was copied
  correctly (it's case-insensitive but every character matters). For
  cross-network play, see the port-forwarding note above.
- **mediapipe import errors** - this build pins
  `mediapipe>=0.10.13,<0.10.30` because newer mediapipe releases removed the
  legacy `solutions.pose` API this project uses in favor of a new Task API.
  Stick to the pinned range unless you're ready to port `pose_tracker.py`
  to `mediapipe.tasks.vision.PoseLandmarker`.

---

## Tech stack actually used

- **UI/rendering:** pygame (2D), OpenCV (camera + face detection/recognition)
- **Pose estimation:** MediaPipe Pose
- **Face recognition:** OpenCV Haar cascade + LBPH
- **Networking:** plain TCP sockets + a small JSON-line protocol (stdlib
  `socket`/`threading` only - no extra networking dependency)
- **Storage:** SQLite (stdlib `sqlite3`), one local database per player/
  install - no shared/central database
- **Audio:** numpy-synthesized waveforms via `pygame.sndarray`

No React/Three.js/FastAPI/WebSockets/Redis/cloud infra in this build -
everything runs locally, peer-to-peer, on the players' own machines.
