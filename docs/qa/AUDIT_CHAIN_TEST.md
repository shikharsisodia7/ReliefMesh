# Audit-chain validation

`backend/tests/test_release_qa.py::test_audit_chain_rejects_payload_deletion_reordering_link_and_hash_tampering` verifies that `verify_chain()` rejects:

- a changed event payload;
- a deleted middle event (sequence gap);
- a changed canonical sequence slot (persisted reordering);
- a changed `previous_hash`; and
- a changed `event_hash`.

The existing integration test additionally verifies the `/v1/missions/{mission_id}/audit/verify` endpoint against persisted events.

## Result

The chain is tamper-evident for unauthorised, partial record changes: **PASS**.

It is not immutable and must not be described that way. A privileged database attacker who can rewrite every event, recompute hashes, and replace the chain-head record can produce a self-consistent alternate chain. The verifier does not anchor heads to an external append-only system or signature service. For a stronger guarantee, publish signed checkpoint hashes to an independently controlled store and verify the stored head against that checkpoint.
