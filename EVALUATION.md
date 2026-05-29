# EVALUATION

## Were the chosen patterns the best fit?
The selected patterns were appropriate for the BitePlate prototype. Singleton was suitable for a globally accessible order audit log. Observer was a strong fit for event-driven updates when kitchen/order status changes needed to notify different actors. Adapter solved integration with legacy kitchen display APIs without modifying existing third-party software. Command improved kitchen workflow by encapsulating status actions and enabling undo functionality. Strategy allowed runtime pricing variations (standard, happy hour, loyalty) without changing billing core logic.

Alternatives considered:
- For notifications, a signal-only approach was considered, but Observer keeps application-level intent explicit and easier to explain in UML.
- For pricing, hardcoded if/else blocks were rejected because they scale poorly and violate Open/Closed Principle.
- For kitchen actions, direct model updates were simpler but lacked undo history and command encapsulation.

## Singleton trade-offs (testability, thread safety)
Singleton improves consistency and discoverability for shared history state, but it can reduce test isolation if not reset per test case. In this project, tests use temporary test DBs, minimizing cross-test leakage. For thread safety, the DB-backed `get_or_create` approach is usually sufficient for this prototype, but under high concurrency, race conditions can occur unless transaction isolation and unique constraints are carefully managed (the unique key helps reduce risk).

## Scaling to 50 restaurants
Several design choices would need evolution:
1. Order history should move from a text blob into normalized analytics tables (or append-only event store) for efficient querying.
2. Command and observer events should be pushed into a message broker (e.g., RabbitMQ/Kafka) for reliable cross-branch async processing.
3. Pricing strategies should be config-driven and branch-aware rather than hardcoded.
4. Authorization should move from simple role models to Django auth groups/permissions with branch scoping.
5. Reporting should use aggregated materialized views or warehouse pipelines for performance.

Overall, the current architecture is correct for a prototype and education portfolio, while remaining extensible toward production-grade scaling.
