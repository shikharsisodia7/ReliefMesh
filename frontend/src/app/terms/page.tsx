import type { Metadata } from "next";

import { CONTACT_EMAIL, LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Terms of service · ReliefMesh" };

export default function TermsPage() {
  return (
    <LegalPage title="Terms of service" updated="October 24, 2026">
      <p>By using ReliefMesh you agree to these terms. If you use it for an organization, you confirm you may act for
        that organization.</p>
      <section><h2>What ReliefMesh does</h2>
        <p>ReliefMesh helps coordinators collect supplier quotes, screen suppliers against public records, compute a
          purchasing plan and route it to an independent human approver. Purchase orders are issued only after that
          approval. ReliefMesh does not move money for purchases. Any machine-to-machine payment shown in the product
          is a test payment on a developer network.</p>
      </section>
      <section><h2>Your responsibilities</h2><ul>
        <li>Keep your account credentials private and use only accounts and integrations you are authorized to use.</li>
        <li>Suppliers are responsible for the accuracy of the quotes they submit. Coordinators and approvers are
          responsible for their purchasing decisions.</li>
        <li>Do not use ReliefMesh to send unsolicited messages or to break any law.</li>
      </ul></section>
      <section><h2>Connected services</h2>
        <p>Google, Slack and other connected services are governed by their own terms. ReliefMesh uses them only as
          described in the <a href="/privacy">privacy policy</a>, and you can disconnect them at any time.</p>
      </section>
      <section><h2>No warranty</h2>
        <p>ReliefMesh is provided as is, without warranties of any kind. Public-record evidence can be incomplete or
          delayed, so screening results support a human decision and never replace one. To the extent the law allows,
          ReliefMesh is not liable for indirect or consequential losses.</p>
      </section>
      <section><h2>Changes and contact</h2>
        <p>We may update these terms; the date above shows the latest version. Questions:{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.</p>
      </section>
    </LegalPage>
  );
}
