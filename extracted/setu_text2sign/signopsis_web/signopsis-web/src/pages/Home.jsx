import { Hero } from "../components/home/Hero.jsx";
import {
  Marquee, Why, Layers, TryIt, LiveTeaser, TrustSection, ComposeBand, TeachBand, GlanceBand, DiagBand, Connect, FinalCTA,
} from "../components/home/Sections.jsx";

/** S06 Home: hero → why → layers → live demo → live stage → trust → compose → teach → glance → diagnostics → connect → CTA */
export default function Home() {
  return (
    <>
      <Hero />
      <Marquee />
      <Why />
      <Layers />
      <TryIt />
      <LiveTeaser />
      <TrustSection />
      <ComposeBand />
      <TeachBand />
      <GlanceBand />
      <DiagBand />
      <Connect />
      <FinalCTA />
    </>
  );
}
