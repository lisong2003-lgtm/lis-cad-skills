# Interior Decoration Quantity Takeoff & Material Plan

> zhuangshi-suanliang (zhuangshi-suanliang) v0.9.30 · overseas-friendly lightweight layer. 中文版见 [README.md](README.md).

## What it is
Generates decoration budget quantities and material plans from room type, building notes, architectural/structural drawings, room decoration tables, practice tables and node details. It imports cad-file-reader length/area candidates as review inputs; method mapping, opening deductions, loss, material ledger and BOQ quantities are computed by this skill.

## When to use it
Use for solid/interior (decoration) takeoff and material planning such as gypsum, finishes, waterproofing, tiles and ceilings.

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

Review coordinate and quantity candidates before use. All outputs remain review data, not final engineering decisions.

## Quick start
```bash
bash scripts/decor_qty.sh --input 明细表.csv --out-dir out
bash scripts/decor_qty.sh --input 快速房间表.xlsx --out-dir out --level 一层
```

## Install across the three platforms
- **GitHub**: clone or download the repo, copy the skill folder into `$CODEX_HOME/skills/` (or `<claude-skills-root>/` / your agent's skill directory).
- **SkillHub**: install the SkillHub lightweight package (text-only). The lightweight package removes platform-only launcher files (`.cmd`/`.ps1`, extensionless scripts and binary language models) and documents the Windows usage inside its own README; the GitHub full package keeps all platform launchers and assets.
- **ClawHub**: install the ClawHub full package, which keeps cross-platform launchers and assets.
- All platform packages serve the same canonical logic; platform copies never change the canonical code.

## Dependencies
Python 3.10+; optional cad-file-reader for measurement candidates; openpyxl for XLSX output.

## Privacy
Local only; documents are never uploaded.

## Boundaries / limitations
Budget/material-plan estimates; contracts, local rules, enterprise quotas and current standards take precedence.

## License
CC-BY-NC-SA-4.0

---

## Culture note
- `--lang en|zh` controls UI/help/JSON message language (default `zh`); business algorithms are identical in both languages.
- For image-ocr, `--lang` remains the OCR language; UI language is `--ui-lang en|zh`.
- Local Chinese templates and plant/concept dictionaries are NOT replaced; overseas inputs can select alternatives via parameters (e.g. `--plant-library`, `--project-rules`) so existing Chinese users are unaffected.
- Review flags, confidence tiers and evidence coordinates are language-independent fields.
