/**
 * sound.js — Authentic Squid Game Audio Engine
 *
 * Uses the uploaded authentic Squid Game chant music (/squid-music/squid_chant.mp3).
 *
 * Dynamic Features:
 *  - Plays real chant during GREEN LIGHT
 *  - Supports dynamic playbackRate (fast 1.6x, slow 0.8x, normal 1.0x) to vary pace
 *  - Abruptly cuts off music the second RED LIGHT starts
 *  - Plays mechanical doll-turn SFX when doll turns
 *  - Plays sharp gunshot SFX on player elimination
 *  - Victory fanfare on win
 */

const Sound = (() => {
  let _ctx = null;
  let _unlocked = false;
  let _masterGain = null;

  // Real Audio Element for authentic Squid Game Chant
  let _chantAudio = null;
  let _currentPlaybackRate = 1.0;

  function _getCtx() {
    if (!_ctx) {
      _ctx = new (window.AudioContext || window.webkitAudioContext)();
      _masterGain = _ctx.createGain();
      _masterGain.gain.value = 0.85;
      _masterGain.connect(_ctx.destination);
    }
    return _ctx;
  }

  function _initChantAudio() {
    if (!_chantAudio) {
      _chantAudio = new Audio('/squid-music/squid_chant.mp3');
      _chantAudio.loop = true;
      _chantAudio.preload = 'auto';
    }
  }

  function unlock() {
    if (_unlocked) return;
    const ctx = _getCtx();
    if (ctx.state === 'suspended') {
      ctx.resume().then(() => { _unlocked = true; });
    } else {
      _unlocked = true;
    }
    _initChantAudio();
    // Warm up audio playback
    const silentBuf = ctx.createBuffer(1, 1, 22050);
    const src = ctx.createBufferSource();
    src.buffer = silentBuf;
    src.connect(_masterGain);
    src.start(0);
  }

  /**
   * Start playing the authentic Squid Game chant music.
   * @param {number} rate - Playback rate / tempo multiplier (e.g. 0.85 = slow, 1.0 = normal, 1.5 = fast)
   */
  function startSong(rate = 1.0) {
    unlock();
    _initChantAudio();

    _currentPlaybackRate = rate;
    _chantAudio.playbackRate = rate;
    _chantAudio.currentTime = 0;

    const playPromise = _chantAudio.play();
    if (playPromise !== undefined) {
      playPromise.catch(err => {
        console.warn('Audio play auto-blocked or interrupted:', err);
      });
    }
  }

  /**
   * Update the tempo dynamically during playback (e.g. accelerating tempo near end of green light)
   */
  function setTempo(rate) {
    if (_chantAudio) {
      _currentPlaybackRate = rate;
      _chantAudio.playbackRate = rate;
    }
  }

  /**
   * Abruptly stop the music (when doll turns / RED LIGHT begins)
   */
  function stopSong() {
    if (_chantAudio) {
      _chantAudio.pause();
      _chantAudio.currentTime = 0;
    }
  }

  /**
   * Doll turn sound: creepy mechanical whirr & clunk
   */
  function dollTurnSound() {
    unlock();
    const ctx = _getCtx();
    const t = ctx.currentTime;

    // Servo whirr
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(90, t);
    osc.frequency.linearRampToValueAtTime(180, t + 0.18);
    osc.frequency.linearRampToValueAtTime(50, t + 0.45);
    gain.gain.setValueAtTime(0.0, t);
    gain.gain.linearRampToValueAtTime(0.3, t + 0.04);
    gain.gain.linearRampToValueAtTime(0.0, t + 0.5);
    osc.connect(gain);
    gain.connect(_masterGain);
    osc.start(t);
    osc.stop(t + 0.52);

    // Mechanical click
    const click = ctx.createOscillator();
    const clickGain = ctx.createGain();
    click.type = 'triangle';
    click.frequency.value = 220;
    clickGain.gain.setValueAtTime(0.35, t + 0.4);
    clickGain.gain.exponentialRampToValueAtTime(0.001, t + 0.55);
    click.connect(clickGain);
    clickGain.connect(_masterGain);
    click.start(t + 0.4);
    click.stop(t + 0.56);
  }

  /**
   * Gunshot SFX: Sharp sniper rifle crack + low impact boom when player is shot down
   */
  function gunshot() {
    unlock();
    const ctx = _getCtx();
    const t = ctx.currentTime;

    // 1. Sharp white noise burst (gunshot crack)
    const bufLen = Math.floor(ctx.sampleRate * 0.45);
    const buf = ctx.createBuffer(1, bufLen, ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < bufLen; i++) {
      const env = i < 300
        ? (i / 300)
        : Math.pow(1 - (i - 300) / (bufLen - 300), 3.5);
      data[i] = (Math.random() * 2 - 1) * env * (i < 500 ? 3.0 : 1.0);
    }
    const noiseSrc = ctx.createBufferSource();
    noiseSrc.buffer = buf;
    const noiseGain = ctx.createGain();
    noiseGain.gain.value = 1.0;
    noiseSrc.connect(noiseGain);
    noiseGain.connect(_masterGain);
    noiseSrc.start(t);

    // 2. Low frequency body hit / cannon boom
    const boom = ctx.createOscillator();
    const boomGain = ctx.createGain();
    boom.type = 'sine';
    boom.frequency.setValueAtTime(140, t);
    boom.frequency.exponentialRampToValueAtTime(25, t + 0.3);
    boomGain.gain.setValueAtTime(0.85, t);
    boomGain.gain.exponentialRampToValueAtTime(0.001, t + 0.35);
    boom.connect(boomGain);
    boomGain.connect(_masterGain);
    boom.start(t);
    boom.stop(t + 0.36);
  }

  /**
   * Countdown tick
   */
  function beep(isGo = false) {
    unlock();
    const ctx = _getCtx();
    const freq = isGo ? 880 : 550;
    const dur  = isGo ? 0.45 : 0.12;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;

    gain.gain.setValueAtTime(0.001, ctx.currentTime);
    gain.gain.linearRampToValueAtTime(isGo ? 0.35 : 0.2, ctx.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + dur);

    osc.connect(gain);
    gain.connect(_masterGain);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + dur + 0.01);
  }

  /**
   * Victory fanfare
   */
  function victory() {
    unlock();
    const ctx = _getCtx();
    const fanfare = [523.25, 659.25, 783.99, 1046.50];
    fanfare.forEach((f, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      const startTime = ctx.currentTime + i * 0.16;
      osc.type = 'sine';
      osc.frequency.value = f;

      gain.gain.setValueAtTime(0.001, startTime);
      gain.gain.linearRampToValueAtTime(0.25, startTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.45);

      osc.connect(gain);
      gain.connect(_masterGain);
      osc.start(startTime);
      osc.stop(startTime + 0.46);
    });
  }

  /**
   * Warning pulse when movement is detected during Red Light
   */
  function warningPulse() {
    unlock();
    const ctx = _getCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = 130;

    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);

    osc.connect(gain);
    gain.connect(_masterGain);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.11);
  }

  return {
    unlock,
    startSong,
    setTempo,
    stopSong,
    dollTurnSound,
    gunshot,
    beep,
    victory,
    warningPulse,
    init: unlock,
    countdownBeep: beep,
  };
})();
