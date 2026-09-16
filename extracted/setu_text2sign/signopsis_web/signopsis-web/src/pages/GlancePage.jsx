import { ScreenGlance } from "../components/ScreenGlance.jsx";
import { PageHeader } from "../components/PageHeader.jsx";

export default function GlancePage() {
  return (
    <div className="mx-auto max-w-7xl px-4 pb-10 sm:px-6">
      <PageHeader n="S15" eyebrow="Screen Glance" title="What's on this screen? Ask, and get it signed."
        lead="Short answers, in order, with where things are. SIGNOPSIS describes; you decide what to press." />
      <ScreenGlance />
    </div>
  );
}
