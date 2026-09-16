import { EnrollmentScreen } from "../components/EnrollmentScreen.jsx";
import { PageHeader } from "../components/PageHeader.jsx";

export default function EnrollPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 pb-10 sm:px-6">
      <PageHeader n="S09" eyebrow="Teach a sign" title="Your name sign. Your town's word. Four takes."
        lead="Personal signs are added to your own index straight away. Nothing is retrained, nothing is shared unless you choose your team." />
      <EnrollmentScreen />
    </div>
  );
}
