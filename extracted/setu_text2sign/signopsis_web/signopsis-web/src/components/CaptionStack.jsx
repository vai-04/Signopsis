import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Volume2 } from "lucide-react";
import { TrustBadge } from "./TrustBadge.jsx";
import { SpeakerDot } from "./Bits.jsx";
import { GlossStrip } from "./GlossStrip.jsx";
import { humanReason } from "./RepairCard.jsx";
import { speak } from "../services/speech.js";
import { cx, fmtTime } from "../utils/cx.js";

/**
 * Conversation captions (newest at the bottom), in their own scroll area so they never cover the stage.
 * Each item: {id, speaker, speakerIndex, channel, text, state, reason, advisory, gloss, lang, answered, dismissed, at}
 */
export function CaptionStack({ items = [], live = null, className = "", big = false, emptyHint = "Captions will appear here." }) {
  const box = useRef(null);
  // scroll only this container (never the page)
  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [items.length, live?.text, live?.gloss?.length]);

  return (
    <div ref={box} className={cx("no-scrollbar overflow-y-auto overscroll-contain", className)} role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation captions">
      {!items.length && !live && (
        <div className="grid h-full min-h-24 place-items-center px-6 text-center text-sm text-mute">{emptyHint}</div>
      )}
      <ol className="flex flex-col gap-2.5">
        <AnimatePresence initial={false}>
          {items.map(c => <CaptionItem key={c.id} c={c} big={big} />)}
          {live && (
            <motion.li key="__live" layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="flex items-start gap-3 rounded-2xl border-2 border-dashed border-ink/15 bg-white/70 p-3">
              <SpeakerDot name={live.speaker} index={live.speakerIndex ?? 0} channel={live.channel} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-bold">{live.speaker}</span>
                  <TrustBadge state="pending" size="sm" />
                  {live.lang && <span className="rounded-full bg-ink/6 px-2 py-0.5 text-[11px] font-semibold text-ink-soft">{live.lang}</span>}
                </div>
                {live.text && <p className={cx("mt-1 text-ink-soft italic", big ? "text-2xl" : "text-base")}>{live.text}…</p>}
                {live.gloss?.length > 0 && <GlossStrip items={live.gloss} size="sm" className="mt-1.5" label="Signs read so far" />}
              </div>
            </motion.li>
          )}
        </AnimatePresence>
      </ol>
    </div>
  );
}

function CaptionItem({ c, big }) {
  const held = c.state === "hold";
  const asking = c.state === "repair" && !c.answered;
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: c.dismissed ? 0.55 : 1, y: 0, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 28 }}
      className={cx("group flex items-start gap-3 rounded-2xl border-2 bg-white p-3",
        held ? "border-ink/80" : asking ? "border-coral" : "border-transparent shadow-(--shadow-card)")}
    >
      <SpeakerDot name={c.speaker} index={c.speakerIndex ?? 0} channel={c.channel} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-sm font-bold">{c.speaker}</span>
          <TrustBadge state={c.state} size="sm" />
          {c.lang && <span className="rounded-full bg-ink/6 px-2 py-0.5 text-[11px] font-semibold text-ink-soft">{c.lang}</span>}
          {c.signLang && <span className="rounded-full bg-sage-soft px-2 py-0.5 text-[11px] font-bold uppercase text-moss-deep">→ {c.signLang}</span>}
          <time className="ml-auto text-[11px] text-mute">{fmtTime(c.at)}</time>
        </div>
        {held ? (
          <p className={cx("mt-1 font-semibold text-ink", big ? "text-xl" : "text-[15px]")}>
            <span className="sr-only">Held: </span>{humanReason(c.repair?.prompt || c.reason) || "Held until it can be read properly."}
          </p>
        ) : (
          <p className={cx("mt-1 font-semibold leading-snug text-ink", big ? "text-2xl sm:text-3xl" : "text-[17px]", asking && "text-ink/60")}>
            {c.text || c.draft}
            {asking && <span className="ml-2 align-middle text-xs font-bold uppercase text-coral-deep">(unconfirmed)</span>}
          </p>
        )}
        {c.answered && <p className="mt-1 text-xs font-semibold text-moss-deep">You answered: {c.answered}</p>}
        {c.advisory && (
          <p className="mt-2 flex items-start gap-1.5 rounded-xl bg-coral-soft px-2.5 py-1.5 text-xs font-semibold text-ink">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-coral-deep" aria-hidden="true" /> {c.advisory}
          </p>
        )}
        {c.gloss?.length > 0 && !held && <GlossStrip items={c.gloss} size="sm" className="mt-2 opacity-70 transition group-hover:opacity-100" />}
      </div>
      {c.tts && c.text && (
        <button type="button" className="btn-icon shrink-0 text-mute hover:text-ink" onClick={() => speak(c.tts)} aria-label={`Read aloud: ${c.text}`}>
          <Volume2 className="h-4 w-4" />
        </button>
      )}
    </motion.li>
  );
}
