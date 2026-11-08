# Bundle contract

## Required metadata

- title
- created_at
- artifact_type
- intended_destination
- source_files
- preview_files
- QA status
- unresolved HITL count
- source/provenance files when applicable
- deployment/import instructions
- SHA-256 for every bundled file

## Acceptance criteria

A handoff is ready when:

- primary editable source opens in its intended editor;
- preview represents the source closely enough for review;
- README names the target app and exact next action;
- no secret-like values or private runtime paths are exposed;
- all manifest-referenced local files exist;
- QA status is included;
- unresolved HITL items are visible;
- recipient can distinguish source of truth from preview/export files.
