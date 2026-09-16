import { ComposeScreen } from "../components/ComposeScreen.jsx";
import { PageHeader } from "../components/PageHeader.jsx";

export default function ComposePage() {
  return (
    <div className="mx-auto max-w-7xl px-4 pb-10 sm:px-6">
      <PageHeader n="S03" eyebrow="Compose · text to sign" title="Write it. Watch it. Check it. Then sign it."
        lead="SIGNOPSIS turns your words into sign-language gloss, reads its own signing back, and asks before sending anything it isn't sure about." />
      <ComposeScreen />
    </div>
  );
}
