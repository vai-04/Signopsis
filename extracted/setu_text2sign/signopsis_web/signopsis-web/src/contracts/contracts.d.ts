/**
 * SIGNOPSIS data contracts, mirrored 1:1 from the backend (`setu/schemas/__init__.py`, Pydantic v2).
 * If the backend changes a model, change it here too, then re-export fixtures with
 * `python scripts/export_fixtures.py src/mocks` (run from the backend repo).
 */

// ------------------------------------------------------------------ PerceptEvent (L1 output)
export type LatticeSlot = { slot: number; cands: [string, number][] };
export type NonManual = {
  brow: "neutral" | "raised" | "furrowed";
  head: "neutral" | "nod" | "shake" | "tilt_fwd";
  mouth: "neutral" | "puffed" | "pursed" | "open";
  eyegaze: string;
  conf: number;
};
export type PerceptEvent = {
  id: string; t0: number; t1: number;
  channel: "sign" | "speech" | "screen" | "text";
  source: string; lang_hint: string;
  lattice: LatticeSlot[];
  nonmanual?: NonManual | null;
  quality: Record<string, number>;
  trust?: number | null;
  partial: boolean;
};

// ------------------------------------------------------------------ SemanticFrame (L2/L3 output)
export type Entity = { text: string; type: string; resolved_from: "lexicon" | "lattice" | "context" | "user" | "fingerspell"; alternatives: string[]; margin: number };
export type Prosody = { affect: "neutral" | "happy" | "sad" | "urgent" | "angry"; intensity: number; emphasis: string[]; pace: "slow" | "normal" | "fast"; conf: number };
export type Grounding = { span: [number, number]; percept_ids: string[]; t: [number, number]; gloss_index?: number | null };
export type Unresolved = { slot: number; cands: string[]; reason: "low_margin" | "lexical_ambiguity" | "unknown_word" | "roundtrip_fail"; source_text: string; token_index: number };
export type SemanticFrame = {
  id: string; utterance: string; lang: string;
  speech_act: "statement" | "question" | "request" | "correction" | "backchannel";
  question_type?: "wh" | "yesno" | null;
  negated: boolean;
  entities: Entity[]; prosody: Prosody; grounding: Grounding[]; unresolved: Unresolved[];
  gloss: string[]; high_stakes: boolean; trust: number;
  provenance: { resolver: string; escalated_to_cloud: boolean };
};

// ------------------------------------------------------------------ RenderPlan (L4 output)
export type Gate = "emit" | "repair" | "hold";
export type GlossItem = { g: string; dur_ms: number; fs_fallback?: string | null; fingerspelled: boolean; conf: number; roundtrip?: number | null; source_span?: [number, number] | null };
export type NMKey = { t: number; brow?: string | null; head?: string | null; mouth?: string | null };
export type CaptionTarget = { kind: "caption"; lang: string; text: string; trust_badge: "high" | "medium" | "low"; forced: boolean; speaker_label: string };
export type SignTarget = { kind: "sign"; sign_lang: string; gloss: GlossItem[]; nonmanual: NMKey[]; affect: string; roundtrip_score: number; back_translation: string; total_ms: number };
export type TTSTarget = { kind: "tts"; engine: string; lang: string; text: string; voice: string; emphasis: string[]; rate: number; pitch: number; volume: number };
export type RepairOption = { gloss: string; label: string; clip?: string | null };
export type Repair = { type: "disambiguate" | "confirm" | "resign" | "teach"; slot: number; token_index: number; prompt: string; options: RepairOption[] };
export type RenderPlan = {
  frame_id: string; gate: Gate; gate_reason: string;
  targets: (CaptionTarget | SignTarget | TTSTarget)[];
  repair?: Repair | null; advisory?: string | null;
  timings_ms: Record<string, number>;
};

// ------------------------------------------------------------------ avatar playback frames (/api/text-to-sign, /api/sign/{gloss})
/** hand params: c = 5 finger curls, s = spread, x/y = signing-space position (0..100), r = roll deg, p = palm facing */
export type HandParams = { c: number[]; s: number; x: number; y: number; r: number; p: number };
export type FaceKey = { brow: string; head: string; mouth: string; hx?: number; hy?: number };
export type AvatarFrame = { t?: number; Rq: HandParams; Lq: HandParams; face: FaceKey; gi?: number; ch?: string | null };
export type AvatarClip = { fps: number; total_ms: number; frames: AvatarFrame[]; segments: { start: number; end: number; gi: number; ch?: string | null }[] };

// ------------------------------------------------------------------ REST
export type TextToSignRequest = {
  text: string;
  resolutions?: Record<number, string>;
  seed?: number;
  /** additive fields (ignored by the v1 backend, used by future multilingual packs) */
  src_lang?: string; sign_lang?: string;
};
export type TextToSignResponse = {
  frame: SemanticFrame; plan: RenderPlan;
  readback: { slot: number; cands: [string, number][] }[];
  frames: AvatarClip;
};
export type Lexicon = { signs: string[]; vocab_without_sign: string[]; unlisted_demo_signs: string[]; sign_langs?: string[] };
export type ModeStatus = { mode: string; [k: string]: unknown };

// ------------------------------------------------------------------ WebSocket /ws/sign  (L0 wire contract)
export type WireHand = { lm: [number, number, number][]; label: string; score: number };
export type WireFace = { bs: Record<string, number>; nose?: [number, number] | null };
export type WireFrame = { type: "frame"; t: number; w: number; h: number; hands: WireHand[]; pose?: number[][] | null; face?: WireFace | null; lux?: number | null; mirrored: boolean };

export type ClientMessage =
  | WireFrame
  | { type: "batch"; items: ClientMessage[] }
  | { type: "repair_choice"; frame_id?: string; slot: number; choice: string }   // choice: gloss | "__none__" | "__teach__" | "__accept__"
  | { type: "enroll_start"; label: string; kind?: "name" | "variant" | "jargon"; scope?: "me" | "team" }
  | { type: "enroll_from_unknown"; label: string; kind?: string; scope?: string }
  | { type: "enroll_cancel" }
  | { type: "enroll_undo" }                     // drop the last recorded sample ("Redo last")
  | { type: "forget_sign"; label: string }
  | { type: "list_signs" }
  | { type: "config"; out_lang?: "en" | "hi"; dominant?: "left" | "right" }
  | { type: "flush" } | { type: "reset" } | { type: "hello" };

export type SlotView = {
  gloss: string; display: string; kind: "sign" | "fingerspell" | "unknown"; trust: number; visual_trust: number;
  source: string; post: [string, number][]; ctx_margin: number; visual: [string, number][]; negated: boolean;
  t: [number, number]; signals: Record<string, number>;
};
export type PersonalSign = { label: string; display: string; samples: number; created?: string | number | null };

export type ServerEvent =
  | { type: "hello"; user: string; signs: PersonalSign[]; config: { out_lang: string; dominant: string }; vocabulary: string[] }
  | { type: "live"; t: number; signing: boolean; enrolling: boolean; hands: { R: boolean; L: boolean }; anchor: boolean; lux: number | null; hint: string | null; brow: "raised" | "furrowed" | "neutral" }
  | { type: "phrase_start"; t: number; enrolling: boolean }
  | { type: "partial"; gloss: string[]; t: number }
  | { type: "result"; text: string; draft?: string; gate: Gate; slots: SlotView[]; reason_code?: string; percept: PerceptEvent | null; frame: SemanticFrame | null; plan: RenderPlan }
  | { type: "teach_offer"; samples: number; need: number; prompt: string }
  | { type: "enroll_progress"; label: string | null; display?: string; have: number; need: number; warning?: string; cancelled?: boolean; undone?: boolean }
  | { type: "enrolled"; label: string; display: string; prototypes: number; consistency: number; warning: string | null }
  | { type: "signs"; signs: PersonalSign[]; removed?: number }
  | { type: "repair_done"; frame_id: string; outcome: string }
  | { type: "config"; out_lang: string; dominant: string }
  | { type: "reset" }
  | { type: "error"; message: string };

// ------------------------------------------------------------------ UI trust vocabulary
/** HIGH = backend "emit"; ENHANCED = emit that needed context / personal memory / a repair answer. */
export type TrustState = "high" | "repair" | "hold" | "enhanced";
