import { LandingNavbar } from "@/components/sections/landing-navbar";
import { HeroSection } from "@/components/sections/hero";
import { SocialProofSection } from "@/components/sections/social-proof";
import { FeaturesSection } from "@/components/sections/features";
import { WorkflowSection } from "@/components/sections/workflow";
import { PricingSection } from "@/components/sections/pricing";
import { BenefitsSection } from "@/components/sections/benefits";
import { IntegrationsSection } from "@/components/sections/integrations";
import { TestimonialsSection } from "@/components/sections/testimonials";
import { FaqSection, Footer } from "@/components/sections/faq-footer";

export default function LandingPage() {
  return (
    <main>
      <LandingNavbar />
      <HeroSection />
      <SocialProofSection />
      <section id="features">
        <FeaturesSection />
      </section>
      <section id="how-it-works">
        <WorkflowSection />
      </section>
      <section id="pricing">
        <PricingSection />
      </section>
      <BenefitsSection />
      <IntegrationsSection />
      <TestimonialsSection />
      <FaqSection />
      <Footer />
    </main>
  );
}
