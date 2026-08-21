/**
 * multiplayer.js — Multiplayer lobby + game via WebSocket
 */

const Multi = {
  ws: null,
  pose: null,
  canvas: null,
  ctx: null,
  animFrame: null,
  lastTime: 0,
  roomCode: '',
  isHost: false,
  myGameId: '',
  matchState: null,
  avatars: {},
  _latestScore: 0,
  _wasEliminated: false,
  _lastPhase: null,

  // ─── Lobby ──────────────────────────────────────────────────────────
  async createRoom() {
    await this._connect('create');
  },

  async joinRoom(code) {
    await this._connect('join', code.toUpperCase().trim());
  },

  async _connect(action, code = '') {
    const sid = App.sessionId;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = code
      ? `${proto}://${location.host}/ws/multi/${sid}?action=${action}&room_code=${code}`
      : `${proto}://${location.host}/ws/multi/${sid}?action=${action}`;

    this.ws = new WebSocket(url);

    this.ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      this._handleMsg(msg);
    };

    this.ws.onerror = () => showToast('Connection error');
    this.ws.onclose = () => {
      if (!this.matchState?.over) showToast('Disconnected from room');
    };
  },

  _handleMsg(msg) {
    switch (msg.type) {
      case 'room_created':
        this.roomCode = msg.room_code;
        this.myGameId = msg.game_id;
        this.isHost = true;
        this._showLobby();
        break;

      case 'joined':
        this.roomCode = msg.room_code;
        this.myGameId = msg.game_id;
        this.isHost = false;
        this._showLobby();
        break;

      case 'lobby':
        this._updateLobbyUI(msg.players);
        break;

      case 'match_starting':
        showToast('Match starting!');
        this._startGame();
        break;

      case 'match_state':
        this.matchState = msg;
        this._updateMultiHUD(msg);
        break;

      case 'match_over':
        this.matchState = msg;
        this._showMultiResult(msg);
        break;

      case 'player_disconnected':
        showToast('A player disconnected');
        break;

      case 'error':
        showToast('Error: ' + msg.reason);
        break;
    }
  },

  _showLobby() {
    el('multi-choose').classList.add('hidden');
    el('multi-lobby').classList.remove('hidden');
    el('lobby-room-code').textContent = this.roomCode;
    if (this.isHost) {
      el('btn-start-match').classList.remove('hidden');
    }
  },

  _updateLobbyUI(players) {
    const container = el('lobby-players');
    container.innerHTML = '';
    for (const p of players) {
      const isMe = p.game_id === this.myGameId;
      const row = document.createElement('div');
      row.className = 'lobby-player-row';
      row.innerHTML = `
        <div class="lobby-player-dot ${p.ready ? 'ready' : ''}"></div>
        <div class="lobby-player-name">${p.name}${isMe ? ' (you)' : ''}</div>
        <div class="lobby-player-status">${p.ready ? '✅ Ready' : 'Waiting…'}</div>
      `;
      container.appendChild(row);
    }
  },

  sendReady() {
    this.ws?.send(JSON.stringify({ type: 'ready' }));
  },

  sendStart() {
    this.ws?.send(JSON.stringify({ type: 'start' }));
  },

  // ─── Multi Game ─────────────────────────────────────────────────────
  _startGame() {
    this.avatars = {};
    const myNum = (App.player?.game_id || this.myGameId || 'P-456').replace(/\D/g, '').slice(-3).padStart(3, '0') || '456';
    this.avatars[this.myGameId] = new SquidPlayer(myNum);
    this.doll = new YoungheeDoll();
    this._latestScore = 0;
    this._wasEliminated = false;
    this._lastPhase = null;

    showView('view-multi-game');
    this._setupCanvas();
    this._startPose();
    this._startRenderLoop();
  },

  _setupCanvas() {
    this.canvas = el('multi-game-canvas');
    this.ctx = this.canvas.getContext('2d');
    const resize = () => {
      this.canvas.width = window.innerWidth;
      this.canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);
  },

  _startPose() {
    const video = el('multi-game-video');
    const overlay = el('multi-pose-canvas');
    this.pose = new PoseController(video, overlay, (score) => {
      this._latestScore = score;
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'movement', score }));
      }
    });
    this.pose.start();
  },

  _updateMultiHUD(s) {
    const phase = s.phase;

    // Timer
    const tl = Math.max(0, s.phase_duration - s.phase_timer);
    const elapsed = s.elapsed_sec || 0;
    const timeLeft = Math.max(0, 90 - elapsed);
    const mins = Math.floor(timeLeft / 60);
    const secs = Math.floor(timeLeft % 60);
    el('multi-hud-timer').textContent = `${mins}:${secs.toString().padStart(2, '0')}`;

    const dot = el('multi-light-dot');
    const label = el('multi-light-label');
    dot.className = 'light-dot';
    if (phase === 'GREEN') {
      dot.classList.add('green');
      label.textContent = '🟢 GREEN LIGHT';
      label.style.color = 'var(--green)';
    } else if (phase === 'RED') {
      dot.classList.add('red');
      label.textContent = '🔴 RED LIGHT';
      label.style.color = 'var(--red)';
    } else if (phase === 'COUNTDOWN') {
      label.textContent = 'GET READY';
      label.style.color = '';
    } else {
      label.textContent = phase;
      label.style.color = '';
    }

    // Phase change audio & countdown UI
    if (this._lastPhase !== phase) {
      this._lastPhase = phase;
      if (phase === 'GREEN') {
        Sound.startSong(s.chant_speed || 1.0);
      } else if (phase === 'RED') {
        Sound.stopSong();
        Sound.dollTurnSound();
      } else if (phase === 'COUNTDOWN') {
        Sound.beep(false);
      }
    }

    // Countdown overlay
    const cdOverlay = el('multi-countdown-overlay');
    if (phase === 'COUNTDOWN') {
      cdOverlay.classList.remove('hidden');
      const rem = Math.ceil(Math.max(0, s.phase_duration - s.phase_timer));
      el('multi-countdown-num').textContent = rem > 0 ? rem : 'RUN!';
    } else {
      cdOverlay.classList.add('hidden');
    }

    // My progress
    const me = s.players?.[this.myGameId];
    if (me) {
      const distanceToWin = s.distance_to_win || 200.0;
      const pct = Math.min(100, Math.round((me.distance / distanceToWin) * 100));
      el('multi-progress-bar').style.width = pct + '%';
      el('multi-hud-score').textContent = me.score + ' pts';
    }

    // Flash & gunshot on elimination
    if (me && !me.alive) {
      if (!this._wasEliminated) {
        this._wasEliminated = true;
        Sound.gunshot();
      }
      el('multi-flash-overlay').classList.remove('hidden');
    }
  },

  _startRenderLoop() {
    const loop = (ts) => {
      const dt = Math.min((ts - this.lastTime) / 1000, 0.05);
      this.lastTime = ts;

      // Update all player avatar animations
      for (const av of Object.values(this.avatars)) {
        if (av && av.update) av.update(dt);
      }

      // Update doll
      const phase = this.matchState?.phase || 'WAITING';
      const isRed = phase === 'RED' || (this.matchState?.players?.[this.myGameId] && !this.matchState.players[this.myGameId].alive);
      const isAngry = this.matchState?.players?.[this.myGameId] && !this.matchState.players[this.myGameId].alive;
      if (this.doll) this.doll.update(dt, isRed, isAngry);

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
    const s = this.matchState;
    const phase = s?.phase || 'WAITING';

    const groundY = h * 0.58;
    const grassW = w * 0.11;
    const dollX = w * 0.82;
    const finishX = dollX - 80;
    const dollScale = Math.max(0.9, h / 700);

    // Background
    drawBackground(ctx, w, h, phase === 'GREEN' ? 'GREEN_LIGHT' : phase === 'RED' ? 'RED_LIGHT' : 'WAITING');

    // Tree (behind doll)
    ctx.fillStyle = '#5a3818';
    ctx.fillRect(dollX - 16, h * 0.08, 32, groundY - h * 0.08);
    [[dollX, h * 0.08, 65], [dollX - 18, h * 0.04, 48], [dollX + 12, h * 0.01, 40]].forEach(([x, y, r]) => {
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, '#4a9035'); g.addColorStop(1, '#2a6020');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    });

    // Guards standing right next to doll
    drawGuard(ctx, dollX - 125, groundY, 1.0, 'square');
    drawGuard(ctx, dollX + 125, groundY, 1.0, 'circle');

    // Giant Young-hee Doll
    if (this.doll) {
      this.doll.draw(ctx, dollX, groundY, dollScale);
    }

    // Finish line (red stripe)
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

    if (!s?.players) return;

    const entries = Object.entries(s.players);
    const count = entries.length;
    const startX = grassW + 20;
    const endX = finishX - 12;
    const distanceToWin = s.distance_to_win || 200.0;
    const laneSpacing = Math.min(80, Math.max(50, (h * 0.32) / Math.max(1, count)));

    // Draw each player's lane and avatar
    entries.forEach(([gid, p], i) => {
      const isMe = (gid === this.myGameId) || (p.game_id === this.myGameId);
      const laneY = groundY + (i - (count - 1) / 2) * laneSpacing;

      // Ensure avatar instance exists in map
      if (!this.avatars[gid]) {
        const num = (gid || '000').replace(/\D/g, '').slice(-3).padStart(3, '0') || '456';
        this.avatars[gid] = new SquidPlayer(num);
      }
      const av = this.avatars[gid];

      // Progress calculation
      const progress = Math.min(1, Math.max(0, (p.distance || 0) / distanceToWin));
      const avX = startX + (endX - startX) * progress;

      // Lane line
      ctx.strokeStyle = isMe ? 'rgba(35,220,130,0.3)' : 'rgba(255,255,255,0.08)';
      ctx.lineWidth = isMe ? 2 : 1;
      ctx.setLineDash([6, 6]);
      ctx.beginPath();
      ctx.moveTo(startX - 10, laneY + 22);
      ctx.lineTo(finishX, laneY + 22);
      ctx.stroke();
      ctx.setLineDash([]);

      // Player name and ID tag
      ctx.font = isMe ? 'bold 12px Outfit' : '11px Outfit';
      ctx.fillStyle = !p.alive ? 'rgba(230,45,55,0.9)' : isMe ? 'rgba(35,220,130,0.95)' : 'rgba(255,255,255,0.75)';
      ctx.textAlign = 'left';
      const tag = !p.alive ? '💀 ELIMINATED' : p.finished ? '🏆 FINISHED' : isMe ? '⭐ YOU' : '';
      ctx.fillText(`${p.name} #${av.number} ${tag}`, startX - 8, laneY - 45);

      // State determination:
      // Local player uses tracked _latestScore; other players use server-reported is_moving!
      if (!p.alive) {
        av.setState(ANIM.FALL);
      } else if (p.finished) {
        av.setState(ANIM.VICTORY);
      } else if (phase === 'RED') {
        av.setState(ANIM.FREEZE);
      } else if (phase === 'GREEN') {
        if (isMe) {
          av.setState(this._latestScore > 2.0 ? ANIM.RUN : ANIM.IDLE);
        } else {
          av.setState(p.is_moving ? ANIM.RUN : ANIM.IDLE);
        }
      } else {
        av.setState(ANIM.IDLE);
      }

      // Draw Avatar
      const pScale = (1.15 - progress * 0.3) * (count > 2 ? 0.8 : 0.95);
      av.draw(ctx, avX, laneY, pScale);

      // Elimination X crosshair
      if (!p.alive) {
        const r = 26 * pScale;
        ctx.strokeStyle = '#e62d37';
        ctx.lineWidth = 3;
        ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(avX - r, laneY - 80 * pScale); ctx.lineTo(avX + r, laneY - 5 * pScale); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(avX + r, laneY - 80 * pScale); ctx.lineTo(avX - r, laneY - 5 * pScale); ctx.stroke();
      }
    });

    // Movement meter for local player
    if (phase === 'RED' || phase === 'GREEN') {
      this._drawMoveMeter(ctx, w, h);
    }

    // RED LIGHT dramatic vignette
    if (phase === 'RED') {
      const vignette = ctx.createRadialGradient(w / 2, h / 2, h * 0.2, w / 2, h / 2, h * 0.8);
      vignette.addColorStop(0, 'rgba(0,0,0,0)');
      vignette.addColorStop(1, 'rgba(180,20,20,0.2)');
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, w, h);
    }
  },

  _drawMoveMeter(ctx, w, h) {
    const isRed = this.matchState?.phase === 'RED';
    const score = this._latestScore || 0;
    const threshold = isRed ? 3.0 : 2.0;
    const danger = isRed ? Math.min(1, score / 6) : 0;
    const activity = Math.min(1, score / 8);

    const mx = 24, my = h - 80, mw = 160, mh = 14;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.beginPath(); ctx.roundRect(mx - 4, my - 22, mw + 8, mh + 28, 8); ctx.fill();

    ctx.font = 'bold 10px Outfit';
    ctx.fillStyle = 'rgba(255,255,255,0.6)';
    ctx.textAlign = 'left';
    ctx.fillText(isRed ? '⚠ YOUR MOVEMENT' : '🏃 YOUR MOVEMENT', mx, my - 6);

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

  _showMultiResult(s) {
    if (this.pose) { this.pose.stop(); this.pose = null; }
    if (this.animFrame) { cancelAnimationFrame(this.animFrame); this.animFrame = null; }
    Sound.stopSong();

    const winner = s.winner_game_id;
    const me = s.players?.[this.myGameId];
    const isWinner = winner && winner === this.myGameId;

    if (isWinner) {
      setTimeout(() => Sound.victory(), 200);
    } else if (me && !me.alive) {
      setTimeout(() => Sound.gunshot(), 100);
    }

    el('result-icon').textContent = isWinner ? '🏆' : me?.finished ? '✅' : '💀';
    el('result-title').textContent = isWinner ? 'YOU WIN!' : me?.finished ? 'FINISHED' : 'ELIMINATED';
    el('result-title').className = 'result-title ' + (isWinner ? 'victory' : me?.finished ? '' : 'eliminated');
    el('result-score').textContent = (me?.score || 0) + ' pts';
    el('res-distance').textContent = (me?.distance || 0).toFixed(1) + ' / ' + (s.distance_to_win || 200.0).toFixed(1);
    el('res-time').textContent = '—';
    el('res-freeze').textContent = (me?.longest_freeze_sec || 0).toFixed(1) + 's';

    el('btn-play-again').onclick = () => {
      showView('view-multi');
      this._showLobby();
    };
    el('btn-result-menu').onclick = () => {
      this.leave();
      showView('view-menu');
    };
    showView('view-result');
  },

  leave() {
    Sound.stopSong();
    if (this.ws) { this.ws.close(); this.ws = null; }
    if (this.pose) { this.pose.stop(); this.pose = null; }
    if (this.animFrame) { cancelAnimationFrame(this.animFrame); this.animFrame = null; }
    this.avatars = {};
    this.matchState = null;
    el('multi-choose').classList.remove('hidden');
    el('multi-lobby').classList.add('hidden');
    showView('view-menu');
  },
};
