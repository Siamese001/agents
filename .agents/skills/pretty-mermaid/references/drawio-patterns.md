# Draw.io Authoring Patterns

A basic file uses:

```xml
<mxfile host="app.diagrams.net">
  <diagram name="Page-1">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" page="1" pageWidth="1169" pageHeight="827">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

## Vertices

Use `vertex="1"` and `parent="1"`. Include an `mxGeometry` child with `x`, `y`, `width`, and `height` plus `as="geometry"`.

## Edges

Use `edge="1"`, `source`, `target`, and `parent="1"`. Prefer `edgeStyle=orthogonalEdgeStyle;rounded=0;` unless a different relationship requires another style.

## Semantic styles

- Actor: rounded rectangle, light fill.
- Service/component: rounded rectangle, medium stroke.
- Data store: cylinder or database shape.
- Decision: rhombus.
- External system: dashed boundary or distinct fill.
- Control/gate: strong stroke with concise label.

## IDs

Use stable descriptive IDs. Never reuse an ID.
