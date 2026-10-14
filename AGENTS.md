# Project Instructions

## Documentation language

All project documentation must be written in English. This includes README files, product specifications, architecture documents, design documentation, implementation guides, operational runbooks, and documentation added or updated in future changes.

When updating existing documentation written in another language, translate it into English while preserving its technical meaning and scope.

This requirement applies to documentation; conversation with the user may follow the user's preferred language.

## Documentation location

Store all project documentation in the root-level `docs/` directory. This includes the project README, product specifications, architecture documents, design documentation, implementation guides, and operational runbooks.

Keep `AGENTS.md` in the project root as the project instruction entry point. It is the exception to the documentation location rule.

When moving or adding documentation, update relative links so they resolve correctly. Use `docs/README.md` as the documentation index.

## Maintained design context

The canonical design and behavior documents are `docs/DESIGN.md` and `docs/UX-CONTRACT.md`. Preserve the documentation location rule when using tools that assume root-level design files.

## Implementation roadmap and project tracking

`docs/IMPLEMENTATION-ROADMAP.md` is the canonical step-by-step implementation and progress tracker. Maintain it throughout the project, not only when the user requests a status report.

Before implementation:

1. Read the roadmap and the relevant product, architecture, design, and UX documents.
2. Identify the phase and stable task IDs being worked on, their dependencies, and their acceptance boundaries.
3. Break missing or vague work into small, independently executable checklist tasks before implementing it. Preserve existing IDs; append new ones rather than renumbering.

During implementation:

- Keep task status accurate. Mark a checkbox complete only after the stated result has been achieved and appropriately verified.
- Keep implementation, automated tests, live-service verification, and operator acceptance as separate checklist tasks.
- Record in-progress work and blockers on the relevant unchecked tasks; do not silently remove unfinished requirements.
- Follow current user authorization and operational confirmation rules. A roadmap checkbox does not authorize unrelated external actions.

Before ending an implementation session:

1. Update affected checkboxes and phase statuses.
2. Update the current focus, next work queue, blockers, and open decisions when they change.
3. Add concise evidence references to `docs/IMPLEMENTATION-REPORT.md` or relevant maintained documentation, including actual checks run and material limitations.
4. If scope or sequence changes, update the roadmap and dependent product/architecture/UX documentation together and record the reason in the roadmap change log.

Keep the roadmap and all related documentation in English under `docs/`. Never store credential values or secrets in progress notes. Do not mark an entire phase complete merely because its code builds or because a scaffold, simulated test, or related feature exists.
