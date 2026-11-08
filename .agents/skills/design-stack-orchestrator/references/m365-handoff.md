# Microsoft 365 handoff pattern

Prefer a governed SharePoint/Teams landing location when the enterprise is Microsoft-first.

Recommended structure:

- SharePoint folder or document library: durable files and version history.
- Teams channel/tab/message: discovery and collaboration entry point.
- PowerPoint: executive/guided visual experience when appropriate.
- Excel/List/structured source: volatile records when available.

When connectors support actual writes, perform them only after validating the target location and user intent. If write actions are unavailable, return the portable bundle and a concise Teams-ready announcement instead of pretending the upload occurred.
