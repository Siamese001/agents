# Excalidraw Format Notes

Use this minimal root structure:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [],
  "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
  "files": {}
}
```

## Required element practices

- Give every element a unique non-empty string `id`.
- Use finite numeric values for `x`, `y`, `width`, and `height` where applicable.
- Use descriptive IDs such as `phase_discover`, `arrow_to_build`, or `control_gate`.
- Keep text in readable text fields; do not encode formatting markup inside visible labels.
- Bind arrows only to existing element IDs.
- Use deterministic seeds when generating many elements so edits remain stable.
- Keep section coordinates separated enough to prevent accidental overlap.

## Recommended element types

Use `rectangle`, `ellipse`, `diamond`, `text`, `line`, and `arrow` as the core vocabulary. Introduce other Excalidraw types only when they add real meaning.
