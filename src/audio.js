// Karplus-Strong plucked string synthesis via Web Audio.
import { TUNING, noteFreq, BRIDGE_X } from './config.js';

export class GuitarAudio {
  constructor() {
    this.ctx = null;
    this.cache = new Map();
    this.muted = false;
  }

  unlock() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
      this.compressor = this.ctx.createDynamicsCompressor();
      this.compressor.threshold.value = -14;
      this.compressor.knee.value = 24;
      this.compressor.ratio.value = 5;
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.85;
      this.master.connect(this.compressor).connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
  }

  setMuted(m) {
    this.muted = m;
    if (this.master) this.master.gain.value = m ? 0 : 0.85;
  }

  // --- Karplus-Strong buffer ---------------------------------------------
  makeBuffer(freq, stringIdx) {
    const ctx = this.ctx;
    const sr = ctx.sampleRate;
    const t60 = [2.7, 2.5, 2.3, 2.1, 2.0, 1.9][stringIdx] ?? 2.3;
    const dur = Math.min(t60 * 1.15, 4.0);
    const len = Math.floor(sr * dur);
    const buf = ctx.createBuffer(1, len, sr);
    const out = buf.getChannelData(0);

    const Nf = sr / freq;
    const i0 = Math.max(3, Math.ceil(Nf + 0.5)); // first feedback sample, j >= 0

    // noise burst, smoothed per string (wound strings are duller)
    const alpha = 0.25 + stringIdx * 0.13;
    let lp = 0;
    for (let i = 0; i < i0; i++) {
      const w = Math.random() * 2 - 1;
      lp += alpha * (w - lp);
      out[i] = lp;
    }
    // pluck-position comb filter (brightens the attack)
    const pp = Math.max(1, Math.round(i0 * 0.13));
    for (let i = i0 - 1; i >= pp; i--) out[i] -= 0.85 * out[i - pp];

    let peak = 0;
    for (let i = 0; i < i0; i++) peak = Math.max(peak, Math.abs(out[i]));
    if (peak > 0) for (let i = 0; i < i0; i++) out[i] /= peak;

    // fractional delay line: average of two adjacent taps — exact tuning
    // (delay = Nf) plus a guaranteed notch at Nyquist so the loop damps HF
    const damp = Math.exp(Math.log(0.001) / (sr * t60));
    for (let i = i0; i < len; i++) {
      const j = i - Nf - 0.5; // midpoint of the two taps lands at delay Nf
      const j0 = Math.floor(j);
      const fr = j - j0;
      const a = out[j0] * (1 - fr) + out[j0 + 1] * fr;
      const b = out[j0 + 1] * (1 - fr) + out[j0 + 2] * fr;
      out[i] = damp * 0.5 * (a + b);
    }
    // tail fade to avoid a click when the source stops
    const fade = Math.floor(sr * 0.12);
    for (let i = len - fade; i < len; i++) {
      out[i] *= (len - i) / fade;
    }
    return buf;
  }

  bufferFor(freq, stringIdx) {
    const key = `${stringIdx}:${freq.toFixed(2)}`;
    let arr = this.cache.get(key);
    if (!arr) {
      arr = [];
      this.cache.set(key, arr);
    }
    if (arr.length < 2) {
      // two noise variants per note so repeated plucks/strums never sound identical
      arr.push(this.makeBuffer(freq, stringIdx));
    }
    return arr[Math.random() < 0.5 || arr.length === 1 ? 0 : 1];
  }

  pluck(stringIdx, fret = 0, velocity = 1) {
    if (!this.ctx || this.muted) return;
    const ctx = this.ctx;
    if (ctx.state !== 'running') {
      // blocked by autoplay policy: retry once after a (gesture-bound) resume
      ctx.resume().then(() => this.pluck(stringIdx, fret, velocity)).catch(() => {});
      return;
    }
    const freq = noteFreq(stringIdx, fret);
    const src = ctx.createBufferSource();
    src.buffer = this.bufferFor(freq, stringIdx);

    const gain = ctx.createGain();
    const t = ctx.currentTime;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.85 * velocity, t + 0.004);

    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = (2400 + stringIdx * 750) * (0.92 + Math.random() * 0.16);
    lp.Q.value = 0.6;

    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 55;

    // small body resonance
    const body = ctx.createBiquadFilter();
    body.type = 'peaking';
    body.frequency.value = 108;
    body.Q.value = 1.6;
    body.gain.value = 3;

    let tail = gain;
    if (ctx.createStereoPanner) {
      const pan = ctx.createStereoPanner();
      pan.pan.value = Math.max(-0.6, Math.min(0.6, BRIDGE_X[stringIdx] / 0.05));
      gain.connect(pan);
      tail = pan;
    }

    src.connect(gain);
    gain.connect(lp).connect(hp).connect(body).connect(tail).connect(this.master);
    src.start(t);
    src.stop(t + src.buffer.duration);
  }
}
