// Playback clock for avatar clips ({fps,total_ms,frames}). Framework-free so the 3D render loop can
// call tick() every frame without React re-renders; UI subscribes for ~12 Hz progress updates.
import { lerpParams } from "./avatar/rig.js";

export class SignPlayer {
  constructor() {
    this.clip = null;
    this.meta = null;
    this.t = 0;
    this.playing = false;
    this.speed = 1;
    this.loop = false;
    this.queue = [];
    this.listeners = new Set();
    this.lastEmit = 0;
    this.override = null;           // live frame source (mirror / pose lab)
  }

  subscribe(fn) {
    this.listeners.add(fn);
    fn(this.snapshot());
    return () => this.listeners.delete(fn);
  }

  snapshot() {
    const f = this.clip ? this.frameAt(this.t) : null;
    return {
      hasClip: !!this.clip, playing: this.playing, t: this.t, total: this.clip?.total_ms || 0,
      gi: f?.gi ?? -1, ch: f?.ch ?? null, meta: this.meta, queued: this.queue.length, speed: this.speed, loop: this.loop,
    };
  }

  _emit(force = false) {
    const now = performance.now();
    if (!force && now - this.lastEmit < 80) return;
    this.lastEmit = now;
    const s = this.snapshot();
    this.listeners.forEach(f => f(s));
  }

  load(clip, { autoplay = true, meta = null } = {}) {
    this.clip = clip && clip.frames?.length ? clip : null;
    this.meta = meta;
    this.t = 0;
    this.playing = !!(autoplay && this.clip);
    this._emit(true);
  }

  /** queue a clip to play after the current one (live interpreting) */
  enqueue(clip, meta = null) {
    if (!clip?.frames?.length) return;
    if (!this.clip || (!this.playing && this.t >= (this.clip.total_ms || 0))) this.load(clip, { meta });
    else this.queue.push({ clip, meta });
    this._emit(true);
  }

  clearQueue() { this.queue = []; this._emit(true); }

  play() {
    if (!this.clip) return;
    if (this.t >= this.clip.total_ms) this.t = 0;
    this.playing = true;
    this._emit(true);
  }
  pause() { this.playing = false; this._emit(true); }
  toggle() { this.playing ? this.pause() : this.play(); }
  seek(ms) { if (!this.clip) return; this.t = Math.max(0, Math.min(this.clip.total_ms, ms)); this._emit(true); }
  seekToGloss(gi) {
    const F = this.clip?.frames;
    if (!F) return;
    const j = F.findIndex(f => f.gi === gi);
    if (j >= 0) { this.t = j * (1000 / this.clip.fps); this.play(); }
  }
  setSpeed(s) { this.speed = s; this._emit(true); }
  setLoop(l) { this.loop = l; this._emit(true); }
  stop() { this.clip = null; this.queue = []; this.playing = false; this.t = 0; this._emit(true); }

  frameAt(ms) {
    const F = this.clip?.frames;
    if (!F?.length) return null;
    const x = ms / (1000 / this.clip.fps);
    const i = Math.max(0, Math.min(F.length - 1, Math.floor(x)));
    const j = Math.min(F.length - 1, i + 1);
    const a = F[i], b = F[j], u = Math.min(1, Math.max(0, x - i));
    return { Rq: lerpParams(a.Rq, b.Rq, u), Lq: lerpParams(a.Lq, b.Lq, u), face: u < 0.5 ? a.face : b.face, gi: a.gi, ch: a.ch };
  }

  /** advance by dt seconds; returns the frame to render (or null for idle) */
  tick(dt) {
    if (this.override) return this.override;
    if (!this.clip) return null;
    if (this.playing) {
      this.t += dt * 1000 * this.speed;
      if (this.t >= this.clip.total_ms) {
        if (this.queue.length) {
          const next = this.queue.shift();
          this.clip = next.clip; this.meta = next.meta; this.t = 0;
          this._emit(true);
        } else if (this.loop) {
          this.t = 0;
        } else {
          this.t = this.clip.total_ms;
          this.playing = false;
          this._emit(true);
        }
      }
      this._emit();
    }
    return this.frameAt(this.t);
  }
}
