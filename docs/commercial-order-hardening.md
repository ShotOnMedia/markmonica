# Outstanding payment policy

Only pending orders can enter checkout. An awaiting-payment or paid order blocks
new host selections, checkout attempts, and administrator package assignments.
Browser cancellation is advisory and does not cancel an order. Verified successful
notifications remain authoritative. Abandoned payments require reconciliation on the
administrator Orders page; a missing notification is never treated as proof of no charge.

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

## Administrator reconciliation

`/admin/orders` provides immutable order details, filters, required reason fields,
and an order-specific audit trail. Pending orders can be manually approved or
cancelled. Awaiting-payment orders can be cancelled or marked failed only after an
administrator checks Payfast. Paid or quarantined late payments can be activated
after review. A verified COMPLETE notification for a failed or cancelled order is
acknowledged and moved to `payment_review`; it never silently grants entitlements.
