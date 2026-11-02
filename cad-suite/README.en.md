# CAD Suite Review Pipeline

> cad-suite v0.3.1 - evidence-backed routing and review pipeline. 中文版见 [README.md](README.md).

## What it is

Routes drawings, parsed contracts, downstream specialties, aggregation and cross-discipline review into one evidence-backed local pipeline. It preserves source hashes, coordinates, confidence tiers and degradation states, and never upgrades candidates into final quantities.

## Standard data-extraction layer

Canonical positioning: **CAD Drawing Data Extraction: Tables, Points, Coordinates, Notes and Evidence**. Turn CAD drawings into structured, evidence-backed data instead of just viewing them.

### Three standard templates

**A - Structured drawing notes**

```text
Extract material requirements, waterproofing level, fire-rating requirements and referenced standards from the drawing notes. Return a table and JSON with source evidence.
```

| Item | Content | Source text | Drawing | Coordinate |
|---|---|---|---|---|

**B - Equipment / component table extraction**

```text
Extract the equipment or component table from this drawing. Output name, specification, quantity, floor/zone, source drawing, layer and evidence coordinate.
```

| Name | Specification | Quantity | Floor / Zone | Drawing | Layer | Coordinate |
|---|---|---|---|---|---|---|

**C - Area and point extraction**

```text
Extract room names, area candidates, region boundaries and point coordinates. Return both a table and JSON.
```

| Name | Type | Area / Length | Boundary / Point | Drawing | Layer | Coordinate |
|---|---|---|---|---|---|---|

### Output contract

1. **Summary** - one sentence covering what was extracted, its scope and confidence level.
2. **Data table** - a Markdown/CSV/Excel-friendly table for direct review.
3. **Evidence** - drawing name, layer, coordinate, original text, block name and geometry source.
4. **JSON** - machine-readable output with stable fields for downstream processing.

```json
{
  "task": "extract_data",
  "drawing": "",
  "scope": "",
  "items": [],
  "evidence": [],
  "confidence": 0,
  "warnings": []
}
```

## Privacy

Drawing bytes, parsed contracts and reports stay local. No cloud upload.

## License

CC-BY-NC-SA-4.0
