/**
 * pose.js — MediaPipe Pose wrapper + movement scorer (mirrors Python MovementScorer)
 *
 * Uses the MediaPipe Pose solution via CDN.
 * All pose processing happens in-browser; only the movement score (a float)
 * is sent to the server.
 */

class MovementScorer {
  constructor(windowSize = 3, visibilityThreshold = 0.4) {
    this.windowSize = windowSize;
    this.visThreshold = visibilityThreshold;
    this._prev = null;
    this._window = [];
  }

  reset() {
    this._prev = null;
    this._window = [];
  }

  update(landmarks) {
    if (!landmarks || landmarks.length === 0) {
      this._window = [];
      this._prev = null;
      return 0;
    }

    if (!this._prev) {
      this._prev = landmarks;
      this._window.push(0);
      return 0;
    }

    // Body landmark indices in MediaPipe Pose (EXCLUDING FACE 0..10):
    // 11, 12: Shoulders
    // 13, 14: Elbows
    // 15, 16: Wrists
    // 23, 24: Hips
    // 25, 26: Knees
    // 27, 28: Ankles
    const ARM_INDICES = [13, 14, 15, 16];
    const LEG_INDICES = [25, 26, 27, 28];
    const TORSO_INDICES = [11, 12, 23, 24];

    const getDisp = (indices) => {
      let sum = 0, count = 0;
      for (const i of indices) {
        const lm = landmarks[i];
        const prev = this._prev[i];
        if (lm && prev && lm.visibility > this.visThreshold && prev.visibility > this.visThreshold) {
          const dx = lm.x - prev.x;
          const dy = lm.y - prev.y;
          sum += Math.sqrt(dx * dx + dy * dy);
          count++;
        }
      }
      return count > 0 ? (sum / count) * 1000 : 0;
    };

    const armDisp = getDisp(ARM_INDICES);
    const legDisp = getDisp(LEG_INDICES);
    const torsoDisp = getDisp(TORSO_INDICES);

    // STRICT FULL-BODY RUNNING REQUIREMENT:
    // Arms AND legs/torso MUST move together in coordination.
    // Single-part movement (moving just 1 hand, head tilt, etc.) IS REJECTED.
    const activeArms = armDisp >= 2.0;
    const activeLegs = legDisp >= 2.0;
    const activeTorso = torsoDisp >= 1.5;

    const activeCount = [activeArms, activeLegs, activeTorso].filter(Boolean).length;

    let instantaneous = 0;
    // Require AT LEAST 2 body component groups moving together (full body running/marching)
    if (activeCount >= 2) {
      instantaneous = (armDisp * 0.45) + (legDisp * 0.55) + (torsoDisp * 0.6);
    }

    this._prev = landmarks;

    // CRITICAL: INSTANT ZERO-LAG STOPPING
    // As soon as physical body movement drops below threshold, reset smoothing window
    // so score drops to 0.0 immediately without any trailing moving average!
    if (instantaneous < 1.0) {
      this._window = [0];
      return 0;
    }

    this._window.push(instantaneous);
    if (this._window.length > this.windowSize) this._window.shift();
    return this.smoothedScore;
  }

  get smoothedScore() {
    if (this._window.length === 0) return 0;
    return this._window.reduce((a, b) => a + b, 0) / this._window.length;
  }
}


class PoseController {
  /**
   * @param {HTMLVideoElement} videoEl   - live webcam feed
   * @param {HTMLCanvasElement} overlayEl - optional skeleton overlay
   * @param {function} onScore           - callback(score: number, landmarks: array|null)
   */
  constructor(videoEl, overlayEl, onScore) {
    this.videoEl = videoEl;
    this.overlayEl = overlayEl;
    this.onScore = onScore;
    this.scorer = new MovementScorer();
    this.running = false;
    this._pose = null;
    this._camera = null;
  }

  async start() {
    if (this.running) return;
    this.running = true;
    this.scorer.reset();

    // Access webcam
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      this.videoEl.srcObject = stream;
      this._stream = stream;
    } catch (e) {
      console.error('Webcam access denied:', e);
      this.running = false;
      return;
    }

    // Init MediaPipe Pose
    this._pose = new Pose({
      locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/pose/${file}`,
    });

    this._pose.setOptions({
      modelComplexity: 1,
      smoothLandmarks: true,
      minDetectionConfidence: 0.5,
      minTrackingConfidence: 0.5,
    });

    this._pose.onResults((results) => this._onResults(results));

    this._camera = new Camera(this.videoEl, {
      onFrame: async () => {
        if (this.running && this._pose) {
          await this._pose.send({ image: this.videoEl });
        }
      },
      width: 640,
      height: 480,
    });

    await this._camera.start();
  }

  stop() {
    this.running = false;
    if (this._camera) { this._camera.stop(); this._camera = null; }
    if (this._pose) { this._pose.close(); this._pose = null; }
    if (this._stream) {
      this._stream.getTracks().forEach(t => t.stop());
      this._stream = null;
    }
    this.videoEl.srcObject = null;
    this.scorer.reset();
  }

  _onResults(results) {
    const landmarks = results.poseLandmarks;  // null when no person found
    const score = this.scorer.update(landmarks);
    this.onScore(score, landmarks);

    // Draw skeleton overlay (optional)
    if (this.overlayEl) {
      this._drawOverlay(results);
    }
  }

  _drawOverlay(results) {
    const canvas = this.overlayEl;
    const ctx = canvas.getContext('2d');
    canvas.width = this.videoEl.videoWidth || 640;
    canvas.height = this.videoEl.videoHeight || 480;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!results.poseLandmarks) return;

    const lms = results.poseLandmarks;
    const CONNECTIONS = [
      [11,12],[11,13],[13,15],[12,14],[14,16],   // arms
      [11,23],[12,24],[23,24],                    // torso
      [23,25],[25,27],[24,26],[26,28],            // legs
    ];

    ctx.strokeStyle = 'rgba(35,220,130,0.7)';
    ctx.lineWidth = 2;
    for (const [a, b] of CONNECTIONS) {
      const la = lms[a], lb = lms[b];
      if (la.visibility > 0.3 && lb.visibility > 0.3) {
        ctx.beginPath();
        ctx.moveTo(la.x * canvas.width, la.y * canvas.height);
        ctx.lineTo(lb.x * canvas.width, lb.y * canvas.height);
        ctx.stroke();
      }
    }

    ctx.fillStyle = 'rgba(255,45,130,0.9)';
    for (const lm of lms) {
      if (lm.visibility > 0.3) {
        ctx.beginPath();
        ctx.arc(lm.x * canvas.width, lm.y * canvas.height, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
}


/**
 * captureFrameBase64(videoEl) -> base64 JPEG string
 * Used for face registration and login.
 */
function captureFrameBase64(videoEl, quality = 0.85) {
  const canvas = document.createElement('canvas');
  canvas.width = videoEl.videoWidth || 640;
  canvas.height = videoEl.videoHeight || 480;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(videoEl, 0, 0);
  return canvas.toDataURL('image/jpeg', quality);
}
