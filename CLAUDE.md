# Claude Code instructions

Read and follow [AGENTS.md](AGENTS.md) before making changes. It is the canonical working agreement for this repository; keep shared rules there rather than duplicating them here.

Read [ARCHITECTURE.md](documents/ARCHITECTURE.md) for the target design and [DATA_AVAILABILITY.md](documents/data/DATA_AVAILABILITY.md) before making claims about broker tick, news or sentiment history. The target layout in the architecture is not yet implemented. Inspect the current files and available commands before planning code or reporting test results.

For a requested change, identify the owning domain and affected contracts, make the smallest complete change, run relevant verification and report the result. Preserve the execution safety and point-in-time boundaries in `AGENTS.md`. Do not create credentials, fabricated trading data or incomplete production placeholders.
