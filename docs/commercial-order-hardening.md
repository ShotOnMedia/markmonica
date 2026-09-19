# Outstanding payment policy

Only pending orders can enter checkout. An awaiting-payment or paid order blocks
new host selections, checkout attempts, and administrator package assignments.
Browser cancellation is advisory and does not cancel an order. Verified successful
notifications remain authoritative. Abandoned payments require support reconciliation;
this patch deliberately does not guess that a missing notification means no charge.

All commercial mutation paths acquire the event row lock first, then refresh the
order. This serializes request reuse and prevents two checkouts for an event through
these application paths on PostgreSQL. SQLite tests verify state guards, not locks.

## Before deployment

- Reconcile existing duplicate pending/outstanding orders; this patch does not
  rewrite or delete payment history. In particular, multiple pre-existing
  awaiting-payment orders need manual review before notifications are replayed.
- Exercise two concurrent selections and two concurrent checkouts against a
  disposable PostgreSQL instance, and verify exactly one order enters payment.
- Verify a real sandbox COMPLETE notification after a browser cancel return.
- Verify admin approval and a host checkout racing against the same event.

No schema migration is included. A partial unique constraint with a reviewed
legacy-data migration remains a separate defense-in-depth task. Immutable package
versions, financial-history retention, and audited reconciliation tooling remain
follow-up work; this patch does not claim to complete the full commercial review.
