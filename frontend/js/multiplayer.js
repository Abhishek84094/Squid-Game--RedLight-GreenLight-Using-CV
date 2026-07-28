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
    this.myAvatar = new Avatar();
    this.myAvatar.color = App.player?.avatar_color || '#ff2d82';

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
    const timeLeft = Math.max(0, 90 - elapsed);
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
        Sound.playChant(s.chant_speed || 1.0);
      } else if (phase === 'RED') {
        Sound.stopChant();
        Sound.playDollTurn();
      } else if (phase === 'COUNTDOWN') {
        Sound.playBeep(440, 0.2);
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
      const pct = Math.round((me.distance / 100) * 100);
      el('multi-progress-bar').style.width = pct + '%';
      el('multi-hud-score').textContent = me.score + ' pts';
    }

    // Flash & gunshot on elimination
    if (me && !me.alive) {
      if (!this._wasEliminated) {
        this._wasEliminated = true;
        Sound.playGunshot();
      }
      el('multi-flash-overlay').classList.remove('hidden');
    }
  },

  _startRenderLoop() {
    const loop = (ts) => {
      const dt = Math.min((ts - this.lastTime) / 1000, 0.1);
      this.lastTime = ts;
      if (this.myAvatar) this.myAvatar.update(dt);
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

    drawBackground(ctx, w, h, phase === 'GREEN' ? 'GREEN_LIGHT' : phase === 'RED' ? 'RED_LIGHT' : 'WAITING');

    if (!s?.players) return;

    const players = Object.values(s.players);
    const count = players.length;
    const groundY = h * 0.72;
    const dollX = w - 100;

    // Doll
    const facing = phase === 'RED' ? 'front' : 'back';
    drawDoll(ctx, dollX, groundY - 10, 1.2, facing);

    // Draw each player lane
    players.forEach((p, i) => {
      const laneY = groundY + (i - (count - 1) / 2) * 60;
      const avX = 100 + (dollX - 180) * (p.distance / 100);

      ctx.font = '11px Outfit';
      ctx.fillStyle = p.alive ? 'rgba(255,255,255,0.5)' : 'rgba(255,80,80,0.5)';
      ctx.textAlign = 'left';
      ctx.fillText(p.name, 16, laneY - 40);

      // Lane line
      ctx.strokeStyle = 'rgba(255,255,255,0.05)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(80, laneY); ctx.lineTo(dollX - 30, laneY); ctx.stroke();

      const isMe = p.game_id === this.myGameId;
      const av = isMe ? this.myAvatar : new Avatar();
      av.color = p.avatar_color || '#ff2d82';

      if (!p.alive) av.setState(ANIM.FALL);
      else if (p.finished) av.setState(ANIM.VICTORY);
      else if (phase === 'RED') av.setState(ANIM.FREEZE);
      else if (phase === 'GREEN' && (isMe ? this._latestScore > 1.5 : p.distance > 0)) av.setState(ANIM.RUN);
      else av.setState(ANIM.IDLE);

      av.draw(ctx, avX, laneY, count > 2 ? 0.75 : 0.9);
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
    el('res-distance').textContent = (me?.distance || 0).toFixed(1) + ' / 100';
    el('res-time').textContent = '—';
    el('res-freeze').textContent = (me?.longest_freeze_sec || 0).toFixed(1) + 's';

    el('btn-play-again').onclick = () => showView('view-menu');
    el('btn-result-menu').onclick = () => showView('view-menu');
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
