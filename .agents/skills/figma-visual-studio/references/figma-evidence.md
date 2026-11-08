# Figma Property Evidence Schema

The `figma_evidence.json` artifact must be produced from the live Figma canvas (via Figma Plugin API or Figma MCP) and hash-bound to the released PNG export.

## Required Header Fields
- `origin`: `"FIGMA_PLUGIN_API"` or `"FIGMA_MCP"`
- `file_key`: Plausible Figma file key ($\ge 22$ chars)
- `page_id`: Page identifier (e.g. `"1:10"`)
- `frame_id`: Frame identifier (e.g. `"2:20"`)
- `frame_name`: Visual title of frame
- `canvas`: `[3840, 2160]`
- `candidate_sha256`: SHA-256 of released candidate PNG
- `png_export_sha256`: SHA-256 matching candidate PNG
- `node_inventory_sha256`: Canonical SHA-256 of the `nodes` list

## Required Node Properties
Every node in `nodes` must declare:
- `node_id`: Stable identifier
- `name`: Layer name
- `type`: `TEXT`, `FRAME`, `RECTANGLE`, `VECTOR`, `COMPONENT`, etc.
- `visible`: boolean
- `x`, `y`, `width`, `height`: Numeric coordinates (bounds must be within `0 <= x <= 3840` and `0 <= y <= 2160`)

For `type == "TEXT"` nodes:
- `semantic_role`: Role matching `policy/typography.json` (e.g. `SLIDE_TITLE`, `COMPONENT_HEADING`, `ESSENTIAL_BODY`, `SECONDARY_BODY`)
- `text`: Exact string content
- `font_family`: Must equal `"Inter"`
- `font_style`: Weight (e.g. `"Bold"`, `"SemiBold"`, `"Regular"`)
- `font_size`: Font size in px ($\ge$ role floor)
- `line_height`: Numeric line height
- `rendered_line_count`: Count of lines rendered
- `manual_line_breaks`: Count of hard returns (must be 0 for title)
- `fit_behavior`: Must NOT be `"SHRUNK_TO_FIT"`
- `clips_content`: boolean
- `overflow`: boolean
- `glyph_bounds`: Object with `x`, `y`, `width`, `height`
