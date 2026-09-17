# Internal design notes

These documents are the project's engineering record. They are **not** user
documentation: they describe designs, decisions, and measurements at the time
they were written, and parts of them are already superseded by the code.

Start with [`AIVOICE_ARCHITECTURE.md`](AIVOICE_ARCHITECTURE.md) for the overall
shape of the system, and with [`docs/MODEL_GUIDE.md`](../MODEL_GUIDE.md) /
[`README.md`](../../README.md) if you want to *run* the project instead.

Everything here is de-identified: example paths use portable placeholders such
as `C:/path/to/repo`, and example voices are synthetic (`example_voice`,
`example_voice_b`) rather than any real artist or private voice id.

## Architecture

| Document | Scope |
| --- | --- |
| [`AIVOICE_ARCHITECTURE.md`](AIVOICE_ARCHITECTURE.md) | Layer-by-layer architecture analysis |
| [`architecture_review.md`](architecture_review.md) | Cover-layer review notes |
| [`AIVOICE_SKILL_SPEC.md`](AIVOICE_SKILL_SPEC.md) | Skill specification (pre-Hermes) |
| [`skill_readiness_review.md`](skill_readiness_review.md) | Readiness review for the skill entry point |

## Voice registry

| Document | Scope |
| --- | --- |
| [`voice_registry_design.md`](voice_registry_design.md) | Registry schema, resolution, aliases |
| [`migration_plan.md`](migration_plan.md) | Voice Registry migration plan |
| [`cover_skill/`](cover_skill/) | Cover-skill design package (three-layer architecture, protocol contracts, migration plan) |

## Music source

| Document | Scope |
| --- | --- |
| [`music_source_design.md`](music_source_design.md) | Local file / URL / search resolution |

## Async worker

| Document | Scope |
| --- | --- |
| [`v1.3_worker_architecture_options.md`](v1.3_worker_architecture_options.md) | Where the worker should run |
| [`aivoice_v1.3_async_worker_phase1_analysis.md`](aivoice_v1.3_async_worker_phase1_analysis.md) | Phase 1 current-state analysis |
| [`aivoice_v1.3_worker_interface_contract.md`](aivoice_v1.3_worker_interface_contract.md) | Queue/job interface contract |
| [`aivoice_v1.3_worker_job_lifecycle_design.md`](aivoice_v1.3_worker_job_lifecycle_design.md) | Job lifecycle |
| [`aivoice_v1.3_worker_runtime_design.md`](aivoice_v1.3_worker_runtime_design.md) | Worker runtime, lock, drain |
| [`aivoice_v1.3_worker_minimal_execution_design.md`](aivoice_v1.3_worker_minimal_execution_design.md) | Minimal execution path |
| [`aivoice_v1.3_worker_coverservice_integration_analysis.md`](aivoice_v1.3_worker_coverservice_integration_analysis.md) | CoverService integration |
| [`aivoice_v1.3_worker_e2e_smoke_design.md`](aivoice_v1.3_worker_e2e_smoke_design.md) | End-to-end smoke design |
| [`worker_evolution.md`](worker_evolution.md) | Worker roadmap |
| [`job_system_design.md`](job_system_design.md) | Job system design |
| [`cache_strategy.md`](cache_strategy.md) | Cache strategy |

## Hermes / Feishu integration

| Document | Scope |
| --- | --- |
| [`hermes_integration_design.md`](hermes_integration_design.md) | Integration options |
| [`hermes_messaging_design.md`](hermes_messaging_design.md) | Messaging gateway design |
| [`aivoice_v1.3_hermes_skill_enqueue_migration_design.md`](aivoice_v1.3_hermes_skill_enqueue_migration_design.md) | Move the skill to enqueue-only |
| [`aivoice_v1.3_outbox_notification_design.md`](aivoice_v1.3_outbox_notification_design.md) | Outbox + notifier design |
| [`aivoice_v1.3_feishu_client_design.md`](aivoice_v1.3_feishu_client_design.md) | Feishu client integration |
| [`aivoice_v1.3_feishu_notifier_implementation_plan.md`](aivoice_v1.3_feishu_notifier_implementation_plan.md) | Notifier implementation plan |

## Service API and GUI

| Document | Scope |
| --- | --- |
| [`service_api_v2_design.md`](service_api_v2_design.md) | CoverService API v2 |
| [`gui_call_flow.md`](gui_call_flow.md) | GUI call flow |
| [`gui_migration_checklist.md`](gui_migration_checklist.md) | GUI migration checklist |

## Operations

| Document | Scope |
| --- | --- |
| [`profiling_protocol.md`](profiling_protocol.md) | Profiling marker protocol |
| [`post_migration_profiling.md`](post_migration_profiling.md) | Profiling measurements after the migration |

## About superseded reports

The design documents above are cross-referenced with a set of dated one-off
reports (`*_report.md`, `*_validation_report.md`, and similar) that were written
during development. Those reports recorded real runs on the maintainer's
machine, including local absolute paths, personal voice ids, and commercial
song names, so they are **not shipped in this repository**.

If you are auditing the project's history, note that the commit history still
contains them. See the "Historical assets" section of the release report, and
`git log` for the commit that introduced this directory.
