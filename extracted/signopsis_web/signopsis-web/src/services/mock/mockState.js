// Shared in-memory state for mock mode (the "server" side of the mock).
import MODES from "../../mocks/modes.json";

const BUDGET = 8.0;

export const mockState = {
  mode: "SPEAK",
  signs: [],                  // personal signs taught in this browser session
  scenarios: [],              // what the simulated signer is about to sign (FIFO)

  queueScenario(s) {
    const now = Date.now();
    this.scenarios = this.scenarios.filter(x => now - x.at < 15000);
    this.scenarios.push({ ...s, at: now });
    if (this.scenarios.length > 8) this.scenarios.shift();
  },
  nextScenario() {
    const now = Date.now();
    const s = this.scenarios.shift();
    if (s) { this.lastScenario = { s, at: now }; return s; }
    // a stream that splits into several phrases keeps its scenario for a few seconds
    if (this.lastScenario && now - this.lastScenario.at < 4000) return this.lastScenario.s;
    return null;
  },

  modeStatus() {
    const set = new Set([...(MODES.modes[this.mode] || []), ...MODES.pinned]);
    const planned = [...set].reduce((a, n) => a + (MODES.components[n]?.vram_gb || 0), 0);
    return {
      mode: this.mode,
      resident: [...set],
      planned_vram_gb: +planned.toFixed(2),
      budget_gb: BUDGET,
      fits: planned <= BUDGET,
      components: Object.fromEntries(Object.entries(MODES.components).map(([n, c]) => [n, { ...c, loaded: set.has(n), load_ms: set.has(n) ? 40 : 0 }])),
    };
  },
  setMode(mode) {
    if (!MODES.modes[mode]) throw new Error(`unknown mode ${mode}`);
    this.mode = mode;
    return this.modeStatus();
  },
  modeList: Object.keys(MODES.modes),
};
