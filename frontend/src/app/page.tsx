import { Closing } from "@/components/landing/closing";
import { Hero } from "@/components/landing/hero";
import { HowItWorks } from "@/components/landing/how-it-works";
import { SupplierFails } from "@/components/landing/supplier-fails";

// White hero → sand "How it works" → charcoal "When a supplier fails" → orange closing and footer.
export default function Home() {
  return (
    <>
      <main>
        <Hero />
        <HowItWorks />
        <SupplierFails />
      </main>
      <Closing />
    </>
  );
}
