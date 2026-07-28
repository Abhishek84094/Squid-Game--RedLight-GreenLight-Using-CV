/**
 * auth.js — Registration, face login, guest login
 */

const ANGLES = ['front', 'left', 'right'];
const SAMPLES_PER_ANGLE = 15;  // slightly less than desktop (20) for web UX

const Auth = {
  _regName: '',
  _regAngleIdx: 0,
  _regCounts: { front: 0, left: 0, right: 0 },
  _regStream: null,
  _regCapturing: false,

  // ── Registration ────────────────────────────────────────────────────
  async startRegistration(name) {
    this._regName = name.trim();
    this._regAngleIdx = 0;
    this._regCounts = { front: 0, left: 0, right: 0 };

    const res = await apiPost('/api/register/start', { name: this._regName });
    if (!res.ok) throw new Error(res.detail || 'Name taken or server error');

    await this._startRegCam();
    this._updateAngleUI();
  },

  async _startRegCam() {
    const video = el('reg-video');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      video.srcObject = stream;
      this._regStream = stream;
    } catch (e) {
      throw new Error('Webcam access denied: ' + e.message);
    }
  },

  stopRegCam() {
    if (this._regStream) {
      this._regStream.getTracks().forEach(t => t.stop());
      this._regStream = null;
      el('reg-video').srcObject = null;
    }
  },

  _updateAngleUI() {
    const angle = ANGLES[this._regAngleIdx];
    el('reg-angle-badge').textContent = angle.toUpperCase();

    const msgs = {
      front: 'Look straight into the camera.',
      left:  'Slowly turn your head to the LEFT.',
      right: 'Slowly turn your head to the RIGHT.',
    };
    el('reg-instructions').textContent = msgs[angle];

    // Update progress fills
    for (const a of ANGLES) {
      const pct = Math.min(100, (this._regCounts[a] / SAMPLES_PER_ANGLE) * 100);
      el('fill-' + a).style.width = pct + '%';
      if (this._regCounts[a] >= SAMPLES_PER_ANGLE) {
        el('angle-' + a).classList.add('done');
      }
    }
  },

  async captureOneSample() {
    if (this._regCapturing) return;
    this._regCapturing = true;

    const angle = ANGLES[this._regAngleIdx];
    const video = el('reg-video');
    const frame = captureFrameBase64(video);
    const status = el('reg-status');
    status.textContent = 'Capturing…';
    status.className = 'status-msg';

    try {
      const res = await apiPost('/api/register/sample', {
        name: this._regName,
        angle,
        frame_b64: frame,
      });

      if (!res.ok) {
        if (res.reason === 'no_face' && ANGLES[this._regAngleIdx] !== 'front') {
          // Side angles are hard to detect — silently retry with centre-crop
          status.textContent = '⚠️ Side face hard to detect — keep your face visible and try again.';
          status.className = 'status-msg';
        } else {
          status.textContent = res.reason === 'no_face' ? 'No face detected – look at the camera.' : 'Error saving sample.';
          status.className = 'status-msg error';
        }
        this._regCapturing = false;
        return;
      }

      this._regCounts[angle]++;
      this._updateAngleUI();

      const remaining = SAMPLES_PER_ANGLE - this._regCounts[angle];
      if (remaining > 0) {
        status.textContent = `✓ Captured! ${remaining} more needed for ${angle}.`;
        status.className = 'status-msg success';
        el('btn-next-angle').style.display = 'none';
      } else {
        status.textContent = `✓ ${angle} complete!`;
        status.className = 'status-msg success';

        if (this._regAngleIdx < ANGLES.length - 1) {
          el('btn-next-angle').style.display = '';
        } else {
          // All angles done — complete registration
          await this.completeRegistration();
        }
      }
    } catch (e) {
      status.textContent = 'Error: ' + e.message;
      status.className = 'status-msg error';
    }

    this._regCapturing = false;
  },

  nextAngle() {
    this._regAngleIdx++;
    el('btn-next-angle').style.display = 'none';
    el('reg-status').textContent = '';
    this._updateAngleUI();
  },

  async completeRegistration() {
    el('reg-status').textContent = 'Training face model…';
    try {
      const res = await apiPost('/api/register/complete', { name: this._regName });
      if (!res.ok) throw new Error(res.detail || 'Registration failed');
      this.stopRegCam();
      App.onLogin(res.session_id, res.player);
      showToast('Welcome, ' + res.player.name + '! 🎉');
    } catch (e) {
      el('reg-status').textContent = 'Error: ' + e.message;
      el('reg-status').className = 'status-msg error';
    }
  },

  // ── Face Login ───────────────────────────────────────────────────────
  _loginStream: null,

  async startLoginCam() {
    const video = el('login-video');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      video.srcObject = stream;
      this._loginStream = stream;
    } catch (e) {
      setStatus('login-status', 'Webcam access denied: ' + e.message, true);
    }
  },

  stopLoginCam() {
    if (this._loginStream) {
      this._loginStream.getTracks().forEach(t => t.stop());
      this._loginStream = null;
      el('login-video').srcObject = null;
    }
  },

  async scanFace() {
    const video = el('login-video');
    const frame = captureFrameBase64(video);
    setStatus('login-status', 'Scanning…');

    try {
      const res = await apiPost('/api/login/face', { frame_b64: frame });
      if (res.ok) {
        this.stopLoginCam();
        App.onLogin(res.session_id, res.player);
        showToast('Welcome back, ' + res.player.name + '!');
      } else {
        setStatus('login-status', res.reason === 'no_match'
          ? 'Face not recognised. Try again or register first.'
          : 'Login failed. Try again.', true);
      }
    } catch (e) {
      setStatus('login-status', 'Error: ' + e.message, true);
    }
  },

  // ── Guest Login ──────────────────────────────────────────────────────
  async guestLogin(name) {
    if (!name.trim()) { setStatus('guest-status', 'Please enter a name.', true); return; }
    setStatus('guest-status', 'Logging in…');
    try {
      const res = await apiPost('/api/login/guest', { name: name.trim() });
      if (res.ok) {
        App.onLogin(res.session_id, res.player);
        showToast('Welcome, ' + res.player.name + '!');
      } else {
        setStatus('guest-status', 'Login failed.', true);
      }
    } catch (e) {
      setStatus('guest-status', 'Error: ' + e.message, true);
    }
  },
};
