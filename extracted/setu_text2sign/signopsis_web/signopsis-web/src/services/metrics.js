// In-memory session metrics for the Diagnostics screen (never sent anywhere).
const listeners = new Set();
export const metrics = {
  started: Date.now(),
  results: [],        // {at, state, channel, latency}
  roundtrips: [],     // {at, text, score, perGloss:[{g, rt}]}
  record(kind, data) {
    const arr = kind === "roundtrip" ? this.roundtrips : this.results;
    arr.push({ at: Date.now(), ...data });
    if (arr.length > 500) arr.shift();
    listeners.forEach(f => f());
  },
  subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
};
