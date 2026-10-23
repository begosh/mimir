# Bounded checker batching

See the [execution conclusions](EXECUTION_CONCLUSIONS_2026-10-23.md) for the
implemented contracts, current direct/API routing, measurements and limits.

Ready completed findings coalesce into at most four candidates, bounded by worker concurrency. Partial batches flush after two seconds to avoid dependency deadlock. Each candidate retains its own contract, source references and verdict. Invalid batch output fails closed. Actual call savings depend on completion timing.
