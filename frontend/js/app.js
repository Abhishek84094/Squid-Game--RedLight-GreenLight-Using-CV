/**
 * app.js — Main application controller: view routing, event wiring, shared utilities
 */

// ─── Utilities ───────────────────────────────────────────────────────────────
function el(id) { return document.getElementById(id); }

// Unlock Web Audio on first user interaction (required by all browsers)
document.addEventListener('click', () => Sound.unlock(), { once: true });
document.addEventListener('keydown', () => Sound.unlock(), { once: true });
document.addEventListener('touchstart', () => Sound.unlock(), { once: true, passive: true });


function showView(id) {
  document.querySelectorAll('.view').forEach(v => {
    v.classList.remove('active');
    v.style.display = 'none';
  });
  const view = el(id);
  if (view) {
    view.style.display = 'flex';
    // Force reflow for transition
    view.getBoundingClientRect();
    view.classList.add('active');
  }
}

function showToast(msg, duration = 3000) {
  const t = el('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), duration);
}

function setStatus(id, msg, isError = false) {
  const el_ = el(id);
  el_.textContent = msg;
  el_.className = 'status-msg' + (isError ? ' error' : ' success');
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function apiGet(path) {
  const res = await fetch(path);
  return res.json();
}


// ─── App state ───────────────────────────────────────────────────────────────
const App = {
  sessionId: null,
  player: null,
  _lastMode: 'challenge',

  onLogin(sessionId, player) {
    this.sessionId = sessionId;
    this.player = player;
    this._updateMenuUI();
    showView('view-menu');
  },

  onLogout() {
    if (this.sessionId) {
      fetch('/api/logout', {
        method: 'DELETE',
        headers: { 'x-session-id': this.sessionId },
      }).catch(() => {});
    }
    this.sessionId = null;
    this.player = null;
    showView('view-welcome');
  },

  _updateMenuUI() {
    const p = this.player;
    if (!p) return;
    el('menu-player-name').textContent = p.name;
    el('menu-player-id').textContent = 'ID: ' + p.game_id;
    el('menu-avatar-dot').style.background = p.avatar_color || 'var(--pink)';
  },
};


// ─── Event wiring ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  showView('view-welcome');

  // ── Welcome ──────────────────────────────────────────────────────────
  el('btn-go-register').onclick = () => {
    el('reg-step-name').classList.remove('hidden');
    el('reg-step-face').classList.add('hidden');
    el('reg-name-input').value = '';
    showView('view-register');
  };

  el('btn-go-login').onclick = async () => {
    showView('view-login');
    await Auth.startLoginCam();
  };

  el('btn-go-guest').onclick = () => {
    el('guest-name-input').value = '';
    showView('view-guest');
  };

  // ── Registration ─────────────────────────────────────────────────────
  el('btn-back-register').onclick = () => {
    Auth.stopRegCam();
    showView('view-welcome');
  };

  el('btn-reg-name-next').onclick = async () => {
    const name = el('reg-name-input').value.trim();
    if (!name) { showToast('Please enter a name'); return; }
    try {
      await Auth.startRegistration(name);
      el('reg-step-name').classList.add('hidden');
      el('reg-step-face').classList.remove('hidden');
    } catch (e) {
      showToast(e.message);
    }
  };

  el('reg-name-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') el('btn-reg-name-next').click();
  });

  el('btn-capture-face').onclick = () => Auth.captureOneSample();

  el('btn-next-angle').onclick = () => Auth.nextAngle();

  // ── Login ────────────────────────────────────────────────────────────
  el('btn-back-login').onclick = () => {
    Auth.stopLoginCam();
    showView('view-welcome');
  };

  el('btn-scan-face').onclick = () => Auth.scanFace();

  // ── Guest ────────────────────────────────────────────────────────────
  el('btn-back-guest').onclick = () => showView('view-welcome');

  el('btn-guest-login').onclick = () => {
    Auth.guestLogin(el('guest-name-input').value);
  };

  el('guest-name-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') el('btn-guest-login').click();
  });

  // ── Menu ─────────────────────────────────────────────────────────────
  el('btn-logout').onclick = () => App.onLogout();

  el('btn-play-practice').onclick = () => { App._lastMode = 'practice'; Game.start('practice'); };
  el('btn-play-challenge').onclick = () => { App._lastMode = 'challenge'; Game.start('challenge'); };

  el('btn-play-multi').onclick = () => {
    el('multi-choose').classList.remove('hidden');
    el('multi-lobby').classList.add('hidden');
    showView('view-multi');
  };

  el('btn-leaderboard').onclick = async () => {
    showView('view-leaderboard');
    const rows = await apiGet('/api/leaderboard');
    const tbody = el('leaderboard-body');
    tbody.innerHTML = '';
    rows.forEach((r, i) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${i + 1}</td>
        <td>${r.name}</td>
        <td>${r.wins}</td>
        <td>${r.games_played}</td>
        <td>${(r.best_distance || 0).toFixed(1)}</td>
        <td>${r.fastest_time_sec ? r.fastest_time_sec.toFixed(1) + 's' : '—'}</td>
      `;
      tbody.appendChild(tr);
    });
  };

  // ── Game ─────────────────────────────────────────────────────────────
  el('btn-game-leave').onclick = () => {
    Game.stop();
    showView('view-menu');
  };

  // Mute / unmute sound
  el('btn-game-mute').onclick = () => {
    Sound.init();
    Game._muted = !Game._muted;
    if (Game._muted) {
      Sound.stopSong();
      el('btn-game-mute').textContent = '🔇 Muted';
    } else {
      el('btn-game-mute').textContent = '🔊 Sound';
      if (Game.state?.phase === 'GREEN_LIGHT') Sound.startSong();
    }
  };


  // ── Multiplayer ───────────────────────────────────────────────────────
  el('btn-back-multi').onclick = () => {
    Multi.leave();
    showView('view-menu');
  };

  el('btn-create-room').onclick = async () => {
    try { await Multi.createRoom(); }
    catch (e) { showToast('Failed to create room: ' + e.message); }
  };

  el('btn-join-room').onclick = async () => {
    const code = el('room-code-input').value.trim().toUpperCase();
    if (!code) { showToast('Enter a room code'); return; }
    try { await Multi.joinRoom(code); }
    catch (e) { showToast('Failed to join: ' + e.message); }
  };

  el('room-code-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') el('btn-join-room').click();
  });

  el('btn-copy-code').onclick = () => {
    navigator.clipboard.writeText(Multi.roomCode).then(() => showToast('Room code copied!'));
  };

  el('btn-ready-up').onclick = () => Multi.sendReady();

  el('btn-start-match').onclick = () => Multi.sendStart();

  el('btn-multi-game-leave').onclick = () => Multi.leave();

  // ── Leaderboard ────────────────────────────────────────────────────────
  el('btn-back-leaderboard').onclick = () => showView('view-menu');

  // ── Result ────────────────────────────────────────────────────────────
  el('btn-play-again').onclick = () => Game.start(App._lastMode);
  el('btn-result-menu').onclick = () => showView('view-menu');
});
