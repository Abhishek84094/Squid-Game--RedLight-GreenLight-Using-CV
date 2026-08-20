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
  myAvatar: null,
  _latestScore: 0,

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
      const row = document.createElement('div');
      row.className = 'lobby-player-row';
      row.innerHTML = `
        <div class="lobby-player-dot ${p.ready ? 'ready' : ''}"></div>
        <div class="lobby-player-name">${p.name}${p.game_id === this.myGameId ? ' (you)' : ''}</div>
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
    this._playerAvatars = {};
    this.myAvatar = new SquidPlayer((this.myGameId || '456').replace(/\D/g, '').slice(-3) || '456');
    this.doll = new YoungheeDoll();
    this.dt = 0;
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
    const resize = () => { this.canvas.width = window.innerWidth; this.canvas.height = window.innerHeight; };
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
    const timeLeft = Math.max(0, 120 - elapsed);
    const mins = Math.floor(timeLeft / 60);
    const secs = Math.floor(timeLeft % 60);
    el('multi-hud-timer').textContent = `${mins}:${secs.toString().padStart(2, '0')}`;

    const dot = el('multi-light-dot');
    const label = el('multi-light-label');
    dot.className = 'light-dot';
    if (phase === 'GREEN') {
      dot.classList.add('green');
      label.textContent = 'GREEN LIGHT';
      label.style.color = 'var(--green)';
    } else if (phase === 'RED') {
      dot.classList.add('red');
      label.textContent = 'RED LIGHT';
      label.style.color = 'var(--red)';
    } else if (phase === 'COUNTDOWN') {
      label.textContent = 'GET READY';
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
      const pct = Math.min(100, Math.round(((me.distance || 0) / 200.0) * 100));
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
      const dt = Math.min((ts - this.lastTime) / 1000, 0.1);
      this.lastTime = ts;
      this.dt = dt;
      if (this.myAvatar) this.myAvatar.update(dt);
      const phase = this.matchState?.phase || 'WAITING';
      if (this.doll) this.doll.update(dt, phase === 'RED');
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

    // Draw Guards & Younghee Doll
    drawGuard(ctx, dollX - 125, groundY, 1.0, 'square');
    drawGuard(ctx, dollX + 125, groundY, 1.0, 'circle');
    if (this.doll) {
      this.doll.draw(ctx, dollX, groundY, dollScale);
    }

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

    if (!s?.players) return;

    const playerEntries = Object.entries(s.players);
    const count = playerEntries.length;
    this._playerAvatars = this._playerAvatars || {};

    const startX = grassW + 20;
    const endX = finishX - 12;

    // Draw each player lane & character avatar
    playerEntries.forEach(([gid, p], i) => {
      const gameId = p.game_id || gid;
      const isMe = (gameId === this.myGameId);

      // Spaced lanes across the courtyard
      const minY = groundY + 35;
      const maxY = h - 45;
      const laneY = count <= 1 
        ? (groundY + (h - groundY) * 0.5)
        : (minY + i * ((maxY - minY) / (count - 1)));

      // Horizontal progress across field (0.0 to 1.0)
      const progress = Math.min(1.0, Math.max(0.0, (p.distance || 0) / 200.0));
      const playerX = startX + (endX - startX) * progress;
      const pScale = Math.max(0.7, (count > 2 ? 0.85 : 1.0) - progress * 0.2);

      // Lane line
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([8, 6]);
      ctx.beginPath();
      ctx.moveTo(startX - 10, laneY);
      ctx.lineTo(finishX, laneY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Get or create avatar instance
      if (!this._playerAvatars[gameId]) {
        const numStr = (gameId || 'P456').replace(/\D/g, '').slice(-3) || '456';
        this._playerAvatars[gameId] = new SquidPlayer(numStr);
      }
      const av = this._playerAvatars[gameId];
      av.update(this.dt || 0.016);

      // Set animation state
      if (!p.alive) {
        av.setState(ANIM.FALL);
      } else if (p.finished) {
        av.setState(ANIM.VICTORY);
      } else if (phase === 'RED') {
        av.setState(ANIM.FREEZE);
      } else if (phase === 'GREEN') {
        const isMoving = isMe ? (this._latestScore > 1.5) : ((p.distance || 0) > 0);
        av.setState(isMoving ? ANIM.RUN : ANIM.IDLE);
      } else {
        av.setState(ANIM.IDLE);
      }

      // Draw character avatar!
      av.draw(ctx, playerX, laneY, pScale);

      // Draw Name tag pill above avatar
      ctx.save();
      ctx.font = 'bold 12px Outfit, sans-serif';
      ctx.textAlign = 'center';

      const labelText = p.name + (isMe ? ' (YOU)' : '');
      const textMetrics = ctx.measureText(labelText);
      const pillW = textMetrics.width + 16;
      const pillH = 20;
      const pillX = playerX - pillW / 2;
      const pillY = laneY - 78 * pScale;

      ctx.fillStyle = isMe ? 'rgba(255, 45, 130, 0.85)' : (p.alive ? 'rgba(0, 0, 0, 0.65)' : 'rgba(200, 30, 30, 0.85)');
      ctx.beginPath();
      ctx.roundRect(pillX, pillY, pillW, pillH, 10);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.fillText(labelText, playerX, pillY + 14);
      ctx.restore();

      // Elimination X crosshair
      if (!p.alive) {
        const r = 24 * pScale;
        ctx.strokeStyle = '#e62d37';
        ctx.lineWidth = 4;
        ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(playerX - r, laneY - 75 * pScale); ctx.lineTo(playerX + r, laneY - 5 * pScale); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(playerX + r, laneY - 75 * pScale); ctx.lineTo(playerX - r, laneY - 5 * pScale); ctx.stroke();
      }
    });
  },

  _showMultiResult(s) {
    if (this.pose) { this.pose.stop(); this.pose = null; }
    if (this.animFrame) { cancelAnimationFrame(this.animFrame); this.animFrame = null; }

    const winner = s.winner_game_id;
    const me = s.players?.[this.myGameId];
    const isWinner = winner === this.myGameId;

    el('result-icon').textContent = isWinner ? '🏆' : me?.finished ? '✅' : '💀';
    el('result-title').textContent = isWinner ? 'YOU WIN!' : me?.finished ? 'FINISHED' : 'ELIMINATED';
    el('result-title').className = 'result-title ' + (isWinner ? 'victory' : 'eliminated');
    el('result-score').textContent = (me?.score || 0) + ' pts';
    el('res-distance').textContent = (me?.distance || 0).toFixed(1) + ' / 200.0';
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
    if (this.ws) { this.ws.close(); this.ws = null; }
    if (this.pose) { this.pose.stop(); this.pose = null; }
    if (this.animFrame) { cancelAnimationFrame(this.animFrame); this.animFrame = null; }
    el('multi-choose').classList.remove('hidden');
    el('multi-lobby').classList.add('hidden');
    showView('view-menu');
  },
};
