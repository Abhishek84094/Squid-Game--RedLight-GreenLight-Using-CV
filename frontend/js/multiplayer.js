/**
 * multiplayer.js — Multiplayer lobby + 5-player game via WebSocket
 */

// Distinct Squid Game player numbers for up to 5 players
const SQUID_NUMBERS = ['456', '218', '067', '001', '199'];

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
  _playerAvatars: {},
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

      case 'player_eliminated':
        this._onPlayerEliminated(msg);
        break;

      case 'match_over':
        this.matchState = msg;
        this._showMultiResult(msg);
        break;

      case 'player_disconnected':
        showToast('A player disconnected');
        break;

      case 'error':
        showToast('Error: ' + (msg.reason || 'Unknown error'));
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
    players.forEach((p, idx) => {
      const isMe = p.game_id === this.myGameId;
      const numTag = SQUID_NUMBERS[idx % SQUID_NUMBERS.length];
      const row = document.createElement('div');
      row.className = 'lobby-player-row';
      row.innerHTML = `
        <div class="lobby-player-dot ${p.ready ? 'ready' : ''}" style="${p.color ? 'background:' + p.color : ''}"></div>
        <div class="lobby-player-name">#${numTag} ${p.name}${isMe ? ' (you)' : ''}</div>
        <div class="lobby-player-status">${p.ready ? '✅ Ready' : 'Waiting…'}</div>
      `;
      container.appendChild(row);
    });
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
    const myNum = (App.player?.game_id || this.myGameId || 'P-456').replace(/\D/g, '').slice(-3).padStart(3, '0') || '456';
    this._playerAvatars[this.myGameId] = new SquidPlayer(myNum);
    this.doll = new YoungheeDoll();
    this.dt = 0;
    this._latestScore = 0;
    this._wasEliminated = false;
    this._lastPhase = null;

    // Clear any previous elimination announcements
    const bannerContainer = el('multi-elim-container');
    if (bannerContainer) bannerContainer.innerHTML = '';

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

  _onPlayerEliminated(msg) {
    // Play gunshot sound cue for all players in room
    Sound.gunshot();

    // Create on-screen elimination announcement banner
    const container = el('multi-elim-container');
    if (container) {
      const banner = document.createElement('div');
      banner.className = 'elimination-banner';
      banner.innerHTML = `
        <span class="elim-icon">💀</span>
        <span><strong class="elim-name">${msg.name || 'A player'}</strong> got eliminated!</span>
      `;
      container.appendChild(banner);
      setTimeout(() => banner.remove(), 4200);
    }
  },

  _updateMultiHUD(s) {
    const phase = s.phase;

    // Timer
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
      const pct = Math.min(100, Math.round(((me.distance || 0) / distanceToWin) * 100));
      el('multi-progress-bar').style.width = pct + '%';
      el('multi-hud-score').textContent = (me.score || 0) + ' pts';
    }

    // Flash on elimination
    if (me && !me.alive) {
      if (!this._wasEliminated) {
        this._wasEliminated = true;
      }
      el('multi-flash-overlay').classList.remove('hidden');
    }
  },

  _startRenderLoop() {
    const loop = (ts) => {
      const dt = Math.min((ts - this.lastTime) / 1000, 0.05);
      this.lastTime = ts;
      this.dt = dt;

      // Update all persistent player avatars
      if (this._playerAvatars) {
        for (const av of Object.values(this._playerAvatars)) {
          if (av && av.update) av.update(dt);
        }
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

    const groundY = h * 0.56;
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

    // Guards standing next to doll
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

    const playerEntries = Object.entries(s.players);
    const count = playerEntries.length;
    this._playerAvatars = this._playerAvatars || {};

    const startX = grassW + 20;
    const endX = finishX - 12;
    const distanceToWin = s.distance_to_win || 200.0;

    // Up to 5 dynamically distributed lanes across courtyard
    const minY = groundY + 30;
    const maxY = h - 45;

    playerEntries.forEach(([gid, p], i) => {
      const gameId = p.game_id || gid;
      const isMe = (gameId === this.myGameId);

      const laneY = count <= 1
        ? (groundY + (h - groundY) * 0.5)
        : (minY + i * ((maxY - minY) / (count - 1)));

      // Horizontal progress across field (0.0 to 1.0)
      const progress = Math.min(1.0, Math.max(0.0, (p.distance || 0) / distanceToWin));
      const playerX = startX + (endX - startX) * progress;
      const pScale = Math.max(0.68, (count > 3 ? 0.78 : (count > 2 ? 0.88 : 1.0)) - progress * 0.18);

      // Lane line
      ctx.strokeStyle = isMe ? 'rgba(35, 220, 130, 0.35)' : 'rgba(255, 255, 255, 0.1)';
      ctx.lineWidth = isMe ? 2 : 1;
      ctx.setLineDash([8, 6]);
      ctx.beginPath();
      ctx.moveTo(startX - 10, laneY);
      ctx.lineTo(finishX, laneY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Get or create persistent avatar instance with unique Squid Game number
      if (!this._playerAvatars[gameId]) {
        const assignedNum = SQUID_NUMBERS[i % SQUID_NUMBERS.length] || '456';
        this._playerAvatars[gameId] = new SquidPlayer(assignedNum);
      }
      const av = this._playerAvatars[gameId];

      // Set animation state:
      // Local player responds to local camera pose score;
      // Other players respond ONLY to server-validated is_moving state!
      if (!p.alive) {
        av.setState(ANIM.FALL);
      } else if (p.finished) {
        av.setState(ANIM.VICTORY);
      } else if (phase === 'RED') {
        av.setState(ANIM.FREEZE);
      } else if (phase === 'GREEN') {
        const isMoving = isMe ? (this._latestScore > 2.0) : Boolean(p.is_moving);
        av.setState(isMoving ? ANIM.RUN : ANIM.IDLE);
      } else {
        av.setState(ANIM.IDLE);
      }

      // Draw character avatar
      av.draw(ctx, playerX, laneY, pScale);

      // Draw Name tag pill above avatar
      ctx.save();
      ctx.font = 'bold 11px Outfit, sans-serif';
      ctx.textAlign = 'center';

      const tagText = !p.alive ? ' 💀 OUT' : (p.finished ? ' 🏆' : (isMe ? ' (YOU)' : ''));
      const labelText = `#${av.number} ${p.name}${tagText}`;
      const textMetrics = ctx.measureText(labelText);
      const pillW = textMetrics.width + 16;
      const pillH = 18;
      const pillX = playerX - pillW / 2;
      const pillY = laneY - 74 * pScale;

      ctx.fillStyle = isMe
        ? 'rgba(255, 45, 130, 0.9)'
        : (!p.alive ? 'rgba(200, 30, 30, 0.9)' : (p.finished ? 'rgba(35, 220, 130, 0.9)' : 'rgba(15, 16, 20, 0.75)'));
      ctx.beginPath();
      ctx.roundRect(pillX, pillY, pillW, pillH, 9);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.fillText(labelText, playerX, pillY + 13);
      ctx.restore();

      // Elimination X crosshair on eliminated avatars
      if (!p.alive) {
        const r = 22 * pScale;
        ctx.strokeStyle = '#e62d37';
        ctx.lineWidth = 3.5;
        ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(playerX - r, laneY - 72 * pScale); ctx.lineTo(playerX + r, laneY - 4 * pScale); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(playerX + r, laneY - 72 * pScale); ctx.lineTo(playerX - r, laneY - 4 * pScale); ctx.stroke();
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
    const isWinner = winner && (winner === this.myGameId);

    if (isWinner) {
      setTimeout(() => Sound.victory(), 200);
    } else if (me && !me.alive) {
      setTimeout(() => Sound.gunshot(), 100);
    }

    el('result-card-box').classList.add('panel-wide');
    el('single-result-stats').classList.add('hidden');
    el('multi-rankings-wrap').classList.remove('hidden');

    el('result-icon').textContent = isWinner ? '🏆' : (me?.finished ? '✅' : '💀');
    el('result-title').textContent = isWinner ? 'YOU WIN!' : (me?.finished ? 'FINISHED' : 'ELIMINATED');
    el('result-title').className = 'result-title ' + (isWinner ? 'victory' : (me?.finished ? '' : 'eliminated'));
    el('result-score').textContent = (me?.score || 0) + ' pts';

    // Populate full multiplayer match rankings
    const tbody = el('multi-rankings-tbody');
    tbody.innerHTML = '';
    const rankings = s.rankings || [];

    rankings.forEach((r) => {
      const isMe = r.game_id === this.myGameId;
      const statusClass = r.status.toLowerCase();
      const tr = document.createElement('tr');
      if (isMe) tr.className = 'is-me';

      const rankBadge = r.rank === 1 ? '🥇 1' : (r.rank === 2 ? '🥈 2' : (r.rank === 3 ? '🥉 3' : r.rank));

      tr.innerHTML = `
        <td><strong>${rankBadge}</strong></td>
        <td>${r.name}${isMe ? ' <strong>(YOU)</strong>' : ''}</td>
        <td><span class="status-badge ${statusClass}">${r.status}</span></td>
        <td>${(r.distance || 0).toFixed(1)}m</td>
        <td>${r.score || 0}</td>
      `;
      tbody.appendChild(tr);
    });

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
    this._playerAvatars = {};
    this.matchState = null;
    el('result-card-box').classList.remove('panel-wide');
    el('single-result-stats').classList.remove('hidden');
    el('multi-rankings-wrap').classList.add('hidden');
    el('multi-choose').classList.remove('hidden');
    el('multi-lobby').classList.add('hidden');
    showView('view-menu');
  },
};
