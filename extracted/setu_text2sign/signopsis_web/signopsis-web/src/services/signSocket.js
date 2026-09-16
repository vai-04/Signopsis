// Live client for WS /ws/sign (backend SignSession). Same interface as MockSignSocket:
//   const s = new SignSocket({user, lang, dominant}).connect();
//   s.on("result", ev => ...); s.on("*", ev => ...); s.on("status", ({status}) => ...);
//   s.send({type:"frame", ...WireFrame}); s.close();
// Frames are batched (one WS message per animation tick) and dropped if the socket is backed up.
import { wsUrlFor } from "../config.js";

const MAX_BUFFERED = 256 * 1024;

export class SignSocket {
  constructor({ user = "demo", lang = "en", dominant = "right", reconnect = true } = {}) {
    this.params = { user, lang, dominant };
    this.reconnect = reconnect;
    this.listeners = new Map();
    this.status = "idle";
    this.queue = [];
    this.retries = 0;
    this.closedByUser = false;
    this.dropped = 0;
  }

  on(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(fn);
    return () => this.listeners.get(type)?.delete(fn);
  }

  _dispatch(ev) {
    this.listeners.get(ev.type)?.forEach(f => f(ev));
    this.listeners.get("*")?.forEach(f => f(ev));
  }

  _setStatus(status, extra = {}) {
    this.status = status;
    this.listeners.get("status")?.forEach(f => f({ type: "status", status, ...extra }));
  }

  connect() {
    this.closedByUser = false;
    this._setStatus("connecting");
    let ws;
    try {
      ws = new WebSocket(wsUrlFor("/ws/sign", this.params));
    } catch (e) {
      this._setStatus("error", { message: e.message });
      return this;
    }
    this.ws = ws;
    ws.onopen = () => { this.retries = 0; this._setStatus("open"); };
    ws.onmessage = e => {
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; }
      this._dispatch(ev);
    };
    ws.onerror = () => this._setStatus("error", { message: "connection error" });
    ws.onclose = () => {
      this._setStatus("closed");
      if (this.reconnect && !this.closedByUser && this.retries < 6) {
        const delay = Math.min(8000, 500 * 2 ** this.retries++);
        this.retryTimer = setTimeout(() => this.connect(), delay);
      }
    };
    return this;
  }

  close() {
    this.closedByUser = true;
    clearTimeout(this.retryTimer);
    cancelAnimationFrame(this.flushRaf);
    const ws = this.ws;
    if (!ws) return;
    // closing a socket that is still connecting logs a browser warning (React StrictMode mounts twice): wait for open
    if (ws.readyState === WebSocket.CONNECTING) ws.onopen = () => ws.close();
    else ws.close();
  }

  send(msg) {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    if (msg.type !== "frame") {
      this._flush();
      ws.send(JSON.stringify(msg));
      return true;
    }
    if (ws.bufferedAmount > MAX_BUFFERED) { this.dropped++; return false; }
    this.queue.push(msg);
    if (!this.flushRaf) this.flushRaf = requestAnimationFrame(() => this._flush());
    return true;
  }

  _flush() {
    this.flushRaf = null;
    if (!this.queue.length || this.ws?.readyState !== WebSocket.OPEN) return;
    const items = this.queue;
    this.queue = [];
    this.ws.send(JSON.stringify(items.length === 1 ? items[0] : { type: "batch", items }));
  }
}
