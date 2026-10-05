import { LandingNavbar } from "@/components/sections/landing-navbar";
import { HeroSection } from "@/components/sections/hero";
import { FeaturesSection } from "@/components/sections/features";
import { WorkflowSection } from "@/components/sections/workflow";
import { BenefitsSection } from "@/components/sections/benefits";
import { FaqSection, Footer } from "@/components/sections/faq-footer";

export default function LandingPage() {
  return (
    <main>
      <LandingNavbar />
      <HeroSection />
      <section id="features">
        <FeaturesSection />
      </section>
      <section id="how-it-works">
        <WorkflowSection />
      </section>
      <BenefitsSection />
      <FaqSection />
      <Footer />
    </main>
  );
}
