# Decision matrix

Capture only material dimensions:

- `target_app`: miro, figma, figjam, powerpoint, drawio, browser, none
- `presentation`: slide-like executive storytelling
- `whiteboard`: spatial brainstorming or collaborative mapping
- `technical_truth`: architecture/process precision matters more than visual polish
- `interactive`: browser-based interaction or guided steps required
- `pixel_polish`: executive visual finish matters
- `editable`: source must remain editable
- `portable`: artifact must work without a SaaS connector
- `direct_write_required`: user explicitly requires writing into a named app
- `microsoft_first`: enterprise prefers Microsoft 365
- `mcp_unavailable`: connector cannot be used
- `miro_approved_auth`: approved Miro OAuth/API authority exists
- `figma_plugin_allowed`: local/private organization plugin use is permitted

## Default hierarchy

1. Honor an explicit target app when an approved direct-write path exists.
2. If direct write is blocked, preserve the design intent using an editable portable format.
3. For polished executive visuals, prefer SVG or PowerPoint over whiteboard canvases.
4. For technical maintainability, prefer draw.io or Mermaid over decorative SVG.
5. For workshop-style collaboration, prefer Excalidraw when Miro/FigJam cannot be written.
6. For interactive explanation, prefer self-contained HTML over a static canvas.
7. For Microsoft-first distribution, use PowerPoint plus a governed SharePoint/Teams handoff rather than introducing another external SaaS tool.
