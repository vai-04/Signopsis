import { Camera, Mic, Monitor, Database, EyeOff, Trash2, Check, X } from "lucide-react";
import { PageHeader } from "../components/PageHeader.jsx";

const ROWS = [
  { Icon: Camera, what: "Your camera", sent: "Hand, body and face points (numbers), plus one brightness value.", never: "Video, photos, your face image." },
  { Icon: Mic, what: "Your microphone", sent: "The text your browser's speech service heard.", never: "Audio recordings." },
  { Icon: Monitor, what: "Your screen", sent: "Only when you ask: page structure (headings, items, buttons).", never: "Fields marked private, screenshots." },
  { Icon: Database, what: "Your signs", sent: "Motion prototypes of signs you teach, under your user ID.", never: "Shared with anyone unless you pick “My team”." },
];

export default function Privacy() {
  return (
    <div className="mx-auto max-w-5xl px-4 pb-10 sm:px-6">
      <PageHeader n="S21" eyebrow="Privacy" title="Points, not pictures."
        lead="SIGNOPSIS is built so your video never needs to leave your device. Here is exactly what moves, and what doesn't." />
      <div className="overflow-hidden rounded-[1.8rem] bg-white shadow-(--shadow-card)">
        <div className="hidden grid-cols-[14rem_1fr_1fr] gap-4 border-b border-ink/5 px-6 py-3 text-xs font-bold uppercase tracking-wider text-mute md:grid">
          <span>Source</span><span>Sent to SIGNOPSIS</span><span>Never sent</span>
        </div>
        {ROWS.map(r => (
          <div key={r.what} className="grid gap-3 border-b border-ink/5 px-6 py-5 last:border-0 md:grid-cols-[14rem_1fr_1fr] md:gap-4">
            <span className="flex items-center gap-3 font-extrabold"><span className="grid h-10 w-10 place-items-center rounded-xl bg-light"><r.Icon className="h-5 w-5" aria-hidden="true" /></span>{r.what}</span>
            <p className="flex gap-2"><Check className="mt-1 h-4 w-4 shrink-0 text-moss" aria-label="Sent:" />{r.sent}</p>
            <p className="flex gap-2"><X className="mt-1 h-4 w-4 shrink-0 text-coral-deep" aria-label="Never sent:" />{r.never}</p>
          </div>
        ))}
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <div className="card p-6">
          <EyeOff className="h-6 w-6 text-moss" aria-hidden="true" />
          <h2 className="mt-3 text-xl font-extrabold">When it isn't sure, it says so</h2>
          <p className="mt-2 text-ink-soft">Held phrases are not shown or spoken. Medical and legal contexts raise the bar and show a reminder to confirm with a qualified interpreter.</p>
        </div>
        <div className="card p-6">
          <Trash2 className="h-6 w-6 text-coral-deep" aria-hidden="true" />
          <h2 className="mt-3 text-xl font-extrabold">Forget anything, any time</h2>
          <p className="mt-2 text-ink-soft">Remove a taught sign from the <a className="font-bold underline underline-offset-4" href="#/library">Library</a>, clear camera and microphone permissions in <a className="font-bold underline underline-offset-4" href="#/settings#data">Settings</a>, or clear a conversation from its summary.</p>
        </div>
      </div>
      <p className="mt-6 text-sm text-mute">Prototype notice: this build is a research demo. It is not a certified interpreting service.</p>
    </div>
  );
}
