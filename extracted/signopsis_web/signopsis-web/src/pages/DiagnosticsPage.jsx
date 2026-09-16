import { Diagnostics } from "../components/Diagnostics.jsx";
import { PageHeader } from "../components/PageHeader.jsx";

export default function DiagnosticsPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 pb-10 sm:px-6">
      <PageHeader n="S18" eyebrow="Diagnostics" title="The numbers behind “Clear”."
        lead="This is the one screen with raw numbers: calibration of the trust score, how often it would have been confidently wrong, and what this session looks like." />
      <Diagnostics />
    </div>
  );
}
