import type { Metadata } from "next";

import { CONTACT_EMAIL, LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Privacy policy · ReliefMesh" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy policy" updated="October 24, 2026">
      <p>ReliefMesh is an emergency-procurement tool. Coordinators request quotes from suppliers, an independent
        approver authorizes a plan, and purchase orders are issued. This policy explains what ReliefMesh stores and
        how it uses data from connected services such as Google and Slack.</p>
      <section><h2>What we store</h2><ul>
        <li>Account data: your email address and a salted password hash, plus your organization and role.</li>
        <li>Procurement records: missions, requests for quotation, supplier quotes, plans, approvals, purchase orders
          and a tamper-evident audit log of those actions.</li>
        <li>Supplier screening evidence retrieved from public records (for example the U.S. Treasury OFAC list).</li>
        <li>Integration connections: OAuth tokens for the services an administrator connects. Tokens are encrypted at
          rest and are never shown back in the interface.</li>
      </ul></section>
      <section><h2>Google user data</h2>
        <p>An organization administrator can connect a Google account. ReliefMesh requests only these scopes:</p>
        <ul>
          <li><strong>Gmail — send email</strong> (<code>gmail.send</code>): to send requests for quotation, approval
            requests, supply-disruption alerts and purchase orders from the organization&apos;s own address.
            ReliefMesh cannot read, search or delete your email.</li>
          <li><strong>Google Calendar — calendars it creates</strong> (<code>calendar.app.created</code>): to keep a
            dedicated &quot;ReliefMesh Operations&quot; calendar with delivery deadlines, approval windows and supplier
            delivery dates. ReliefMesh cannot see your other calendars.</li>
          <li><strong>Google Drive — files it creates</strong> (<code>drive.file</code>): to archive plan PDFs,
            purchase-order PDFs and audit exports in a ReliefMesh folder. ReliefMesh cannot see your other files.</li>
          <li>Your basic profile email (<code>openid</code>, <code>email</code>), to show which account is connected.</li>
        </ul>
        <p>ReliefMesh&apos;s use and transfer of information received from Google APIs adheres to the{" "}
          <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noreferrer">Google API Services User Data Policy</a>,
          including the Limited Use requirements. Google user data is used only to provide these procurement
          notifications and archives to the organization that connected it. It is not sold, not used for advertising,
          not shared with third parties except as needed to deliver the feature, and not used to train AI or
          machine-learning models. No person reads it except where you ask us to for support, where security requires
          it, or where the law requires it.</p>
      </section>
      <section><h2>Slack</h2>
        <p>If an administrator installs the ReliefMesh Slack app, ReliefMesh posts informational alerts to the chosen
          channel. It does not read messages. Slack messages cannot approve anything; approvals happen only inside
          ReliefMesh.</p>
      </section>
      <section><h2>Your choices and deletion</h2>
        <p>An administrator can disconnect Google or Slack at any time on the Integrations page. Disconnecting revokes
          the grant with the provider and deletes the stored tokens. You can also revoke access from your Google
          Account security settings. To delete an account or organization and its records, email{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Procurement audit records may be kept as long as
          needed to show who approved spending.</p>
      </section>
      <section><h2>Contact</h2><p>Questions about this policy: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.</p></section>
    </LegalPage>
  );
}
