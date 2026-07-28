/**
 * game.js — Authentic Squid Game: Pose-Controlled Single Player
 *
 * YOUR BODY IS THE CONTROLLER:
 *   GREEN LIGHT  →  Run in place → character moves forward
 *   RED LIGHT    →  Freeze! Any body movement = ELIMINATED 💀
 *
 * Visuals: Sandy Squid Game courtyard, Giant Young-hee doll (stationary body, 180° head turn on red),
 *          Square & Circle guards (square_clean.png, circle_clean.png) standing next to doll,
 *          Green tracksuit player (person-1-back-walk-spritesheet.png).
 * Audio:   Authentic chant audio (/squid-music/squid_chant.mp3), dynamic tempo,
 *          abrupt stop + doll-turn sound on red, gunshot SFX on elimination.
 */

// ─── Sprite Loader (with cache-busting URLs) ──────────────────────────────────
const Sprites = {
  youngheeBack: new Image(),
  youngheeFront: new Image(),
  youngheeAngry: new Image(),
  player3DFront: new Image(),
  player3DBack: new Image(),
  dollHead: new Image(),
  dollHeadBack: new Image(),
  dollBody: new Image(),
  squareGuard: new Image(),
  circleGuard: new Image(),
  loaded: false,

  init() {
    if (this.loaded) return;
    const v = '?v=' + Date.now();
    this.youngheeBack.src = '/images/younghee-turn-back-spritesheet.png' + v;
    this.youngheeFront.src = '/images/younghee-turn-front-spritesheet.png' + v;
    this.youngheeAngry.src = '/images/younghee-angry-spritesheet.png' + v;
    this.player3DFront.src = '/images/player456_clean.png' + v;
    this.player3DBack.src = '/images/player456_back_clean.png' + v;
    this.dollHead.src = '/images/doll_head.png' + v;
    this.dollHeadBack.src = '/images/doll_head_back.png' + v;
    this.dollBody.src = '/images/doll_body.png' + v;
    this.squareGuard.src = '/images/square_clean.png' + v;
    this.circleGuard.src = '/images/circle_clean.png' + v;
    this.loaded = true;
  }
};
Sprites.init();


// ─── Player (green tracksuit) ────────────────────────────────────────────────
const ANIM = { IDLE: 'idle', RUN: 'run', FREEZE: 'freeze', FALL: 'fall', VICTORY: 'victory' };

class SquidPlayer {
  constructor(number = '456') {
    this.number = number;
    this.t = 0;
    this.state = ANIM.IDLE;
    this.fallProgress = 0;
    this.victoryT = 0;
    this.frameIdx = 0;
  }

  setState(s) {
    if (this.state !== s) {
      if (s === ANIM.FALL) this.fallProgress = 0;
      this.state = s;
    }
  }

  update(dt) {
    this.t += dt;
    if (this.state === ANIM.RUN) {
      this.frameIdx = (this.frameIdx + dt * 10) % 8;
    } else {
      this.frameIdx = 0;
    }
    if (this.state === ANIM.FALL) this.fallProgress = Math.min(1, this.fallProgress + dt * 2.5);
    if (this.state === ANIM.VICTORY) this.victoryT += dt;
  }

  draw(ctx, cx, cy, scale = 1) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(scale, scale);

    const s = this.state;
    let tilt = 0, bob = 0;
    let lArm = 0, rArm = 0, lLeg = 0, rLeg = 0;

    if (s === ANIM.RUN) {
      const sp = this.t * 11;
      lArm = Math.sin(sp) * 0.65; rArm = -lArm;
      lLeg = Math.sin(sp) * 0.7;  rLeg = -lLeg;
      tilt = Math.sin(sp * 2) * 0.04;
      bob = Math.abs(Math.sin(sp * 2)) * 4;
    } else if (s === ANIM.IDLE) {
      bob = Math.sin(this.t * 1.5) * 2;
    } else if (s === ANIM.FALL) {
      tilt = this.fallProgress * (Math.PI / 2);
    }
    ctx.rotate(tilt);

    // Shadow
    ctx.fillStyle = 'rgba(0,0,0,0.2)';
    ctx.beginPath();
    ctx.ellipse(0, 62, 18 * (1 - this.fallProgress * 0.4), 4, 0, 0, Math.PI * 2);
    ctx.fill();

    // Legs
    this._limb(ctx, -8, 24, 30, lLeg, '#3a7d44', 11);
    this._limb(ctx, 8, 24, 30, rLeg, '#3a7d44', 11);

    // Torso (Green tracksuit jacket)
    ctx.fillStyle = '#3a7d44';
    ctx.beginPath(); ctx.roundRect(-15, -22, 30, 48, 7); ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.beginPath(); ctx.arc(0, 2, 10, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#1a4a25';
    ctx.font = `bold 8px Outfit, monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(this.number, 0, 5);

    // Arms
    this._limb(ctx, -15, -10, 26, -Math.PI / 8 + lArm, '#3a7d44', 10);
    this._limb(ctx, 15, -10, 26, Math.PI / 8 + rArm, '#3a7d44', 10);

    // Head
    ctx.fillStyle = '#f0c8a0';
    ctx.beginPath(); ctx.arc(0, -38 + bob, 17, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#2a1408';
    ctx.beginPath(); ctx.arc(0, -48 + bob, 14, Math.PI, 0); ctx.fill();

    ctx.restore();
  }

  _limb(ctx, x, y, len, angle, col, w) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(angle);
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.roundRect(-w / 2, 0, w, len, w / 2); ctx.fill();
    ctx.restore();
  }
}


// ─── Giant Young-hee Doll (Stationary Body, 180° Head Turning Animation) ──────
class YoungheeDoll {
  constructor() {
    this.turnProgress = 0;   // 0 = back (green light), 1 = front (red light)
    this.t = 0;
    this.isRed = false;
    this.isAngry = false;
    this.animFrame = 0;
  }

  update(dt, isRed, isAngry = false) {
    this.t += dt;
    this.isRed = isRed;
    this.isAngry = isAngry;
    const target = isRed ? 1 : 0;
    const speed = 4.0;
    const diff = target - this.turnProgress;
    this.turnProgress += Math.sign(diff) * Math.min(Math.abs(diff), dt * speed);
    this.animFrame += dt * 8;
  }

  draw(ctx, cx, cy, scale = 1.35) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(scale, scale);

    const tp = this.turnProgress;
    // 3D rotation flip for HEAD ONLY: headScaleX goes from 1.0 (back facing) -> 0.0 -> -1.0 (front facing)
    const headScaleX = Math.cos(tp * Math.PI);

    // Tree post behind doll
    ctx.fillStyle = '#7a5c1a';
    ctx.fillRect(-8, -340, 16, 340);

    const bodyImg = Sprites.dollBody;
    const headImg = Sprites.dollHead;

    if (bodyImg.complete && bodyImg.naturalWidth > 0 && headImg.complete && headImg.naturalWidth > 0) {
      const bodyH = 160;
      const bodyW = 160 * (bodyImg.naturalWidth / bodyImg.naturalHeight);
      const headH = 88;
      const headW = 88 * (headImg.naturalWidth / headImg.naturalHeight);

      // Shadow on ground
      ctx.fillStyle = 'rgba(0,0,0,0.3)';
      ctx.beginPath();
      ctx.ellipse(0, 8, 38, 8, 0, 0, Math.PI * 2);
      ctx.fill();

      // 1. RENDER STATIONARY BODY (Body NEVER turns, stays stationary facing field)
      ctx.drawImage(
        bodyImg,
        -bodyW / 2, -bodyH, bodyW, bodyH
      );

      // 2. RENDER HEAD (ONLY HEAD TURNS 180 DEGREES ON NECK)
      ctx.save();
      // Move pivot to neck joint
      ctx.translate(0, -bodyH + 24);
      // Apply 180° X-scale rotation ONLY to head!
      ctx.scale(headScaleX === 0 ? 0.001 : headScaleX, 1);

      if (headScaleX > 0) {
        // Back of head (Green Light — hair facing tree)
        const headBackImg = Sprites.dollHeadBack;
        if (headBackImg && headBackImg.complete && headBackImg.naturalWidth > 0) {
          ctx.drawImage(
            headBackImg,
            -headW / 2, -headH, headW, headH
          );
        } else {
          ctx.fillStyle = '#1a0c04';
          ctx.beginPath(); ctx.arc(0, -headH * 0.45, 34, 0, Math.PI * 2); ctx.fill();
        }
      } else {
        // Front of head (Red Light — facing players) -> render doll_head.png!
        ctx.drawImage(
          headImg,
          -headW / 2, -headH, headW, headH
        );

        // Add terrifying red eye glow during Red Light scanning
        if (this.isRed) {
          const glow = ctx.createRadialGradient(0, -headH * 0.55, 5, 0, -headH * 0.55, 50);
          glow.addColorStop(0, 'rgba(230,20,20,0.45)');
          glow.addColorStop(1, 'rgba(230,20,20,0)');
          ctx.fillStyle = glow;
          ctx.beginPath(); ctx.arc(0, -headH * 0.55, 50, 0, Math.PI * 2); ctx.fill();
        }
      }

      ctx.restore(); // Head transform
      ctx.restore(); // Main transform
      return;
    }

    // Vector fallback if image loading
    ctx.fillStyle = '#e87020';
    ctx.fillRect(-30, -140, 60, 110);
    ctx.fillStyle = '#f5c518';
    ctx.fillRect(-26, -168, 52, 26);
    ctx.save();
    ctx.translate(0, -215);
    ctx.scale(headScaleX === 0 ? 0.001 : headScaleX, 1);
    ctx.fillStyle = '#f0d0a0';
    ctx.beginPath(); ctx.arc(0, 0, 32, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    ctx.restore();
  }
}


// ─── Square & Circle Guards (square_clean.png & circle_clean.png) ──────────────
function drawGuard(ctx, cx, cy, scale, guardType = 'square') {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(scale, scale);

  const img = (guardType === 'square') ? Sprites.squareGuard : Sprites.circleGuard;

  if (img.complete && img.naturalWidth > 0) {
    const targetH = 145;
    const aspect = img.naturalWidth / img.naturalHeight;
    const targetW = targetH * aspect;

    // Shadow
    ctx.fillStyle = 'rgba(0,0,0,0.25)';
    ctx.beginPath();
    ctx.ellipse(0, 10, targetW * 0.45, 6, 0, 0, Math.PI * 2);
    ctx.fill();

    // Render uploaded guard image (square_clean.png or circle_clean.png)
    ctx.drawImage(
      img,
      -targetW / 2, -targetH, targetW, targetH
    );

    ctx.restore();
    return;
  }

  // Vector fallback if image loading
  ctx.fillStyle = '#111';
  ctx.beginPath(); ctx.ellipse(-8, 22, 11, 5, 0, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.ellipse(8, 22, 11, 5, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#d93075';
  ctx.fillRect(-13, -10, 11, 33);
  ctx.fillRect(2, -10, 11, 33);
  ctx.beginPath(); ctx.roundRect(-15, -90, 30, 84, 5); ctx.fill();
  ctx.fillStyle = '#111';
  ctx.beginPath(); ctx.arc(0, -105, 20, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  ctx.beginPath();
  if (guardType === 'square') {
    ctx.strokeRect(-8, -113, 16, 16);
  } else {
    ctx.arc(0, -105, 8, 0, Math.PI * 2); ctx.fill();
  }

  ctx.restore();
}


// ─── Squid Game Background ────────────────────────────────────────────────────
function drawBackground(ctx, w, h, phase) {
  // Sky (blue gradient)
  const sky = ctx.createLinearGradient(0, 0, 0, h * 0.45);
  sky.addColorStop(0, '#4a7ab8');
  sky.addColorStop(1, '#b8d0e8');
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, w, h * 0.45);

  // Clouds
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  [[w * 0.2, h * 0.08, 60], [w * 0.6, h * 0.06, 45], [w * 0.8, h * 0.1, 35]].forEach(([x, y, r]) => {
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(x + r * 0.6, y + 5, r * 0.7, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(x - r * 0.5, y + 8, r * 0.6, 0, Math.PI * 2); ctx.fill();
  });

  // Pink/magenta back wall (the iconic Squid Game colour)
  ctx.fillStyle = '#c83068';
  ctx.fillRect(0, h * 0.18, w, h * 0.42);
  // Brick texture on the wall
  ctx.strokeStyle = 'rgba(0,0,0,0.07)';
  ctx.lineWidth = 1;
  const brickH = (h * 0.42) / 10;
  for (let row = 0; row < 11; row++) {
    const y = h * 0.18 + row * brickH;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    const offset = (row % 2) * (w / 20);
    for (let col = 0; col <= 20; col++) {
      ctx.beginPath(); ctx.moveTo(col * (w / 10) + offset, y); ctx.lineTo(col * (w / 10) + offset, y + brickH); ctx.stroke();
    }
  }

  // Sandy dirt courtyard (the play area)
  const groundY = h * 0.58;
  const dirt = ctx.createLinearGradient(0, groundY, 0, h);
  dirt.addColorStop(0, '#c8a060');
  dirt.addColorStop(0.4, '#b89048');
  dirt.addColorStop(1, '#907530');
  ctx.fillStyle = dirt;
  ctx.fillRect(0, groundY, w, h - groundY);

  // Dirt texture dots
  ctx.fillStyle = 'rgba(0,0,0,0.06)';
  for (let i = 0; i < 60; i++) {
    const dx = (i * 137.5) % w;
    const dy = groundY + ((i * 73.1) % (h - groundY));
    ctx.beginPath(); ctx.arc(dx, dy, 1.5, 0, Math.PI * 2); ctx.fill();
  }

  // Green grass strips (left and right of courtyard)
  const grassW = w * 0.11;
  ctx.fillStyle = '#4a8a38';
  ctx.fillRect(0, groundY - 12, grassW, h - groundY + 12);
  ctx.fillRect(w - grassW, groundY - 12, grassW, h - groundY + 12);
  // Darker grass top edge
  ctx.fillStyle = '#388028';
  ctx.fillRect(0, groundY - 12, grassW, 12);
  ctx.fillRect(w - grassW, groundY - 12, grassW, 12);

  // Lane divider lines on dirt
  ctx.setLineDash([16, 10]);
  ctx.strokeStyle = 'rgba(255,255,255,0.1)';
  ctx.lineWidth = 2;
  const laneStart = grassW;
  const laneEnd = w - grassW;
  for (let i = 1; i < 5; i++) {
    const lx = laneStart + (laneEnd - laneStart) * (i / 5);
    ctx.beginPath(); ctx.moveTo(lx, groundY); ctx.lineTo(lx + w * 0.03, h); ctx.stroke();
  }
  ctx.setLineDash([]);

  // Start line (solid white)
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(laneStart + 5, groundY - 5);
  ctx.lineTo(laneStart + 5, h);
  ctx.stroke();

  // Phase color overlay
  if (phase === 'RED_LIGHT' || phase === 'ELIMINATED') {
    ctx.fillStyle = 'rgba(200,20,20,0.07)';
    ctx.fillRect(0, 0, w, h);
  }
}


// ─── Main Game Controller ─────────────────────────────────────────────────────
const Game = {
  ws: null,
  pose: null,
  player: null,
  doll: null,
  canvas: null,
  ctx: null,
  animFrame: null,
  lastTime: 0,
  state: null,
  mode: 'challenge',
  _poseScore: 0,
  _prevPhase: null,
  _lastCountdownNum: -1,

  start(mode) {
    this.mode = mode;
    this.state = null;
    this._poseScore = 0;
    this._prevPhase = null;
    this._lastCountdownNum = -1;

    const num = (App.player?.game_id || 'P-456').replace(/\D/g, '').slice(-3).padStart(3, '0');
    this.player = new SquidPlayer(num);
    this.doll = new YoungheeDoll();

    showView('view-game');
    this._setupCanvas();
    this._connectWS();
    this._startPose();
    this._startRenderLoop();
  },

  stop() {
    Sound.stopSong();
    if (this.ws) { this.ws.close(); this.ws = null; }
    if (this.pose) { this.pose.stop(); this.pose = null; }
    if (this.animFrame) { cancelAnimationFrame(this.animFrame); this.animFrame = null; }
  },

  _setupCanvas() {
    this.canvas = el('game-canvas');
    this.ctx = this.canvas.getContext('2d');
    const resize = () => {
      this.canvas.width = window.innerWidth;
      this.canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);
  },

  _connectWS() {
    const sid = App.sessionId;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws/game/${sid}?mode=${this.mode}`);

    this.ws.onopen = () => {
      setTimeout(() => this.ws?.send(JSON.stringify({ type: 'start' })), 600);
    };
    this.ws.onmessage = (e) => this._handleMsg(JSON.parse(e.data));
    this.ws.onerror = () => showToast('Connection error');
  },

  _startPose() {
    const video = el('game-video');
    const overlay = el('pose-canvas');
    this.pose = new PoseController(video, overlay, (score) => {
      this._poseScore = score;
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'movement', score }));
      }
    });
    this.pose.start();
  },

  _handleMsg(msg) {
    if (msg.type === 'state') {
      const prev = this._prevPhase;
      this._prevPhase = msg.phase;
      this.state = msg;

      // ── Phase transition: trigger sounds ──────────────────────────────
      if (prev !== msg.phase) {
        if (msg.phase === 'GREEN_LIGHT') {
          Sound.startSong(msg.tempo || 1.0);
        } else if (msg.phase === 'RED_LIGHT') {
          Sound.stopSong();
          Sound.dollTurnSound();
        } else if (msg.phase === 'COUNTDOWN') {
          Sound.stopSong();
        }
      } else if (msg.phase === 'GREEN_LIGHT' && msg.tempo) {
        Sound.setTempo(msg.tempo);
      }

      // Countdown numbers
      if (msg.phase === 'COUNTDOWN') {
        const num = Math.max(0, Math.ceil(msg.phase_duration - msg.phase_timer));
        if (num !== this._lastCountdownNum) {
          this._lastCountdownNum = num;
          this._showCountdown(num);
          Sound.beep(num === 0);
        }
      } else {
        el('countdown-overlay')?.classList.add('hidden');
      }

      // Flash (movement caught during red)
      if (msg.flash) {
        Sound.warningPulse();
        const flash = el('flash-overlay');
        flash?.classList.remove('hidden');
        clearTimeout(this._flashTimer);
        this._flashTimer = setTimeout(() => flash?.classList.add('hidden'), 200);
      }

      this._updateHUD(msg);
      this._updatePlayerAnim(msg);

    } else if (msg.type === 'result') {
      Sound.stopSong();
      if (msg.outcome === 'eliminated') {
        setTimeout(() => Sound.gunshot(), 100);
      } else if (msg.outcome === 'victory') {
        setTimeout(() => Sound.victory(), 200);
      }
      setTimeout(() => { this.stop(); this._showResult(msg); }, msg.outcome === 'eliminated' ? 800 : 400);

    } else if (msg.type === 'waiting') {
      el('light-label').textContent = 'GET READY';
    }
  },

  _showCountdown(num) {
    const overlay = el('countdown-overlay');
    const numEl = el('countdown-num');
    if (!overlay || !numEl) return;
    overlay.classList.remove('hidden');
    numEl.textContent = num > 0 ? String(num) : 'RUN!';
    numEl.style.animation = 'none';
    void numEl.offsetWidth;
    numEl.style.animation = '';
  },

  _updateHUD(s) {
    // Timer
    const tl = Math.max(0, s.time_left);
    const mins = Math.floor(tl / 60);
    const secs = Math.floor(tl % 60);
    el('hud-timer').textContent = `${mins}:${secs.toString().padStart(2, '0')}`;

    // Score
    el('hud-score').textContent = s.score + ' pts';

    // Progress bar
    const pct = Math.round(s.progress * 100);
    el('progress-bar').style.width = pct + '%';
    el('progress-label').textContent = pct + '%';

    // Light indicator
    const dot = el('light-dot');
    const label = el('light-label');
    dot.className = 'light-dot';
    if (s.phase === 'GREEN_LIGHT') {
      dot.classList.add('green');
      label.textContent = '🟢 GREEN LIGHT';
      label.style.color = 'var(--green)';
    } else if (s.phase === 'RED_LIGHT') {
      dot.classList.add('red');
      label.textContent = '🔴 RED LIGHT';
      label.style.color = 'var(--red)';
    } else if (s.phase === 'COUNTDOWN') {
      label.textContent = 'GET READY';
      label.style.color = '';
    } else {
      label.textContent = s.phase.replace('_', ' ');
      label.style.color = '';
    }
  },

  _updatePlayerAnim(s) {
    const p = this.player;
    switch (s.phase) {
      case 'GREEN_LIGHT':
        p.setState(this._poseScore > 2.0 ? ANIM.RUN : ANIM.IDLE);
        break;
      case 'RED_LIGHT':
        p.setState(ANIM.FREEZE);
        break;
      case 'ELIMINATED':
        p.setState(ANIM.FALL);
        break;
      case 'VICTORY':
        p.setState(ANIM.VICTORY);
        break;
      default:
        p.setState(ANIM.IDLE);
    }
  },

  _startRenderLoop() {
    const loop = (ts) => {
      const dt = Math.min((ts - this.lastTime) / 1000, 0.05);
      this.lastTime = ts;
      if (this.player) this.player.update(dt);
      if (this.doll) {
        const isRed = this.state?.phase === 'RED_LIGHT' || this.state?.phase === 'ELIMINATED';
        const isAngry = this.state?.phase === 'ELIMINATED';
        this.doll.update(dt, isRed, isAngry);
      }
      this._render();
      this.animFrame = requestAnimationFrame(loop);
    };
    this.lastTime = performance.now();
    this.animFrame = requestAnimationFrame(loop);
  },

  _render() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const s = this.state;
    const phase = s?.phase || 'WAITING';
    const groundY = h * 0.58;
    const grassW = w * 0.11;

    // Background
    drawBackground(ctx, w, h, phase);

    // Doll position
    const dollX = w * 0.82;

    // Tree (behind doll)
    ctx.fillStyle = '#5a3818';
    ctx.fillRect(dollX - 16, h * 0.08, 32, groundY - h * 0.08);
    [[dollX, h * 0.08, 65], [dollX - 18, h * 0.04, 48], [dollX + 12, h * 0.01, 40]].forEach(([x, y, r]) => {
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, '#4a9035'); g.addColorStop(1, '#2a6020');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    });

    // Guards standing right next to the doll (Square on left, Circle on right)
    drawGuard(ctx, dollX - 125, groundY, 1.0, 'square');
    drawGuard(ctx, dollX + 125, groundY, 1.0, 'circle');

    // Giant Young-hee Doll (stationary body, ONLY head turns 180°)
    const dollScale = Math.max(0.9, h / 700);
    this.doll.draw(ctx, dollX, groundY, dollScale);

    // Finish line (red stripe)
    const finishX = dollX - 80;
    ctx.strokeStyle = '#e62d37';
    ctx.lineWidth = 5;
    ctx.beginPath(); ctx.moveTo(finishX, groundY - 110 * dollScale); ctx.lineTo(finishX, h); ctx.stroke();
    ctx.save();
    ctx.translate(finishX - 12, groundY - 120 * dollScale);
    ctx.rotate(-Math.PI / 2);
    ctx.font = 'bold 13px Outfit';
    ctx.fillStyle = '#e62d37';
    ctx.textAlign = 'center';
    ctx.fillText('FINISH', 0, 0);
    ctx.restore();

    // Player avatar
    const startX = grassW + 20;
    const endX = finishX - 12;
    const progress = s?.progress || 0;
    const playerX = startX + (endX - startX) * progress;
    const pScale = 1.15 - progress * 0.3;
    this.player.draw(ctx, playerX, groundY, pScale);

    // Elimination X crosshair
    if (phase === 'ELIMINATED') {
      const r = 28 * pScale;
      ctx.strokeStyle = '#e62d37';
      ctx.lineWidth = 4;
      ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(playerX - r, groundY - 85 * pScale); ctx.lineTo(playerX + r, groundY - 10 * pScale); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(playerX + r, groundY - 85 * pScale); ctx.lineTo(playerX - r, groundY - 10 * pScale); ctx.stroke();
    }

    // Movement meter
    if (phase === 'RED_LIGHT' || phase === 'GREEN_LIGHT') {
      this._drawMoveMeter(ctx, w, h);
    }

    // RED LIGHT dramatic vignette
    if (phase === 'RED_LIGHT') {
      const vignette = ctx.createRadialGradient(w / 2, h / 2, h * 0.2, w / 2, h / 2, h * 0.8);
      vignette.addColorStop(0, 'rgba(0,0,0,0)');
      vignette.addColorStop(1, 'rgba(180,20,20,0.2)');
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, w, h);
    }
  },

  _drawMoveMeter(ctx, w, h) {
    const isRed = this.state?.phase === 'RED_LIGHT';
    const score = this._poseScore;
    const threshold = isRed ? 3.0 : 2.0;
    const danger = isRed ? Math.min(1, score / 6) : 0;
    const activity = Math.min(1, score / 8);

    const mx = 24, my = h - 80, mw = 160, mh = 14;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.beginPath(); ctx.roundRect(mx - 4, my - 22, mw + 8, mh + 28, 8); ctx.fill();

    ctx.font = 'bold 10px Outfit';
    ctx.fillStyle = 'rgba(255,255,255,0.6)';
    ctx.textAlign = 'left';
    ctx.fillText(isRed ? '⚠ MOVEMENT' : '🏃 MOVEMENT', mx, my - 6);

    ctx.fillStyle = 'rgba(255,255,255,0.1)';
    ctx.beginPath(); ctx.roundRect(mx, my, mw, mh, mh / 2); ctx.fill();

    const fillColor = isRed
      ? `rgba(${Math.round(200 + 55 * danger)}, ${Math.round(30 * (1 - danger))}, 30, 0.85)`
      : 'rgba(35,220,100,0.85)';
    ctx.fillStyle = fillColor;
    ctx.beginPath(); ctx.roundRect(mx, my, mw * (isRed ? danger : activity), mh, mh / 2); ctx.fill();

    if (isRed) {
      const tx = mx + mw * (threshold / 6);
      ctx.strokeStyle = 'rgba(255,255,100,0.8)';
      ctx.lineWidth = 2;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(tx, my - 3); ctx.lineTo(tx, my + mh + 3); ctx.stroke();
      ctx.setLineDash([]);
    }
  },

  _showResult(res) {
    const icons = { victory: '🏆', eliminated: '💀', timeout: '⏰' };
    const titles = { victory: 'VICTORY!', eliminated: 'ELIMINATED', timeout: 'TIME IS UP' };
    el('result-icon').textContent = icons[res.outcome] || '🎮';
    el('result-title').textContent = titles[res.outcome] || res.outcome.toUpperCase();
    el('result-title').className = 'result-title ' + res.outcome;
    el('result-score').textContent = res.score + ' pts';
    el('res-distance').textContent = res.distance.toFixed(1) + ' / 200.0';
    el('res-time').textContent = res.time_taken_sec.toFixed(1) + 's';
    el('res-freeze').textContent = res.longest_freeze_sec.toFixed(1) + 's';
    el('btn-play-again').onclick = () => Game.start(Game.mode);
    el('btn-result-menu').onclick = () => showView('view-menu');
    showView('view-result');
  },
};
