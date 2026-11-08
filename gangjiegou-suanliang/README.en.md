# Steel Tonnage Takeoff (gangjiegou-suanliang)

**[English](./README.en.md) | [中文](./README.md)**

**v0.3.0** · Converts an existing `*.steel.json` contract from the `cad-file-reader` steel-geometry pack into a section spectrum, tonnage estimate band, and member ledger. It does not read or interpret drawings.

The formal recognition path is fixed: `cad-file-reader -> cad-contract/v1 -> lis-skill-bus -> gangjiegou-suanliang`. This skill never reads DWG/DXF/PDF and does not provide a second recognition path that bypasses `cad-file-reader` or `lis-skill-bus`.

## Check availability first

Installing this skill alone does **not** install its prerequisites. After a marketplace install, run:

```bash
python3 scripts/steel_tonnage.py --check-deps
```

- Both found: exit 0; the formal recognition path is ready.
- Either missing: exit 1 and an explicit missing-dependency message. Existing `*.steel.json` files can still be calculated, but a DWG cannot be recognized.
- `manifest.json` declares `cad-file-reader>=0.39.2 (with cad-file-reader:packs/steel-geometry)` and `lis-skill-bus>=0.1.9` under `requires.skills`.

## What it does

- Consumes `cad-steel-geometry/v1` and emits `cad-steel-tonnage/v0.2` as JSON, Markdown, and CSV.
- Uses geometry formulas for fully dimensioned H sections, tubes, rectangular tubes, angles, C/Z purlins, channels, and plates.
- Uses GB/T 706 theoretical weights for numbered hot-rolled channels `[5`~`[40` and I-beams `I10`~`I63`, including a/b/c variants.
- Reports tonnage by steel grade from `materials[]`; members without grade evidence stay in `unknown_grade`.
- Builds a member-code merge ledger with instance counts, section sets, explicit lengths, and coordinates; conflicts go to review.
- Counts high-strength bolts, bolts, anchor bolts, studs, connection plates, and stiffeners from `connections[]`; only connection plates with thickness-width-length or thickness-area evidence enter tonnage.
- Reports primer, topcoat, hot-dip galvanizing, and fireproof-coating areas from `finishes[]`; missing area/range stays `unavailable`, and fire ratings are not inferred.
- Uses explicit member lengths first; otherwise sums steel-layer drawn segments. With no length evidence it emits the section spectrum only.
- Prefers the member-level ledger for the headline total; allocation is a draft reference only. The reported band is `-15%~+15%` with `final_quantity=false`.

## Two total-tonnage fields

| Case | `total_t` | `total_t_allocated_estimate` |
|---|---|---|
| Every member code has an explicit length and exactly one weight-bearing section | Sum of `member_merge[].tonnage_t`; `total_basis=member_level` | Still retained for draft comparison |
| Member ledger incomplete (missing length, missing section, or multi-section conflict) | Weighted allocation by `unit weight x label count`; `total_basis=allocated_estimate`; prominent warning at the top of the report | Same as `total_t` |
| No length or no weight-bearing section | Empty array | Empty array, or connection plates only |

`member_level_note` explains why member-level was not used. Only when `total_basis=member_level` do the report and CSV label `total_t` as “recommended”; an allocated fallback is labelled “draft, not an answer” and keeps the `total_t_allocated_estimate` qualifier.

## Quick start

### 1. Formal recognition path

```bash
# Probe prerequisites first; exit 1 when either is missing
python3 scripts/steel_tonnage.py --check-deps

# Reuse a matching contract when available; no second drawing parse
bash scripts/gangjiegou_statesync.sh pull --project PROJECT

# Otherwise cad-file-reader performs the only drawing recognition
bash skills/cad-file-reader/scripts/cad_scan.sh drawing.dwg \
  --with-mtext --with-insert --with-geom --with-geom-layer \
  --detail-json detail.json --format json -o cad-scan

bash skills/cad-file-reader/scripts/cad_steel_geometry.sh \
  detail.json --out-dir steel-geometry

# Publish the recognition contract through the bus
bash skills/cad-file-reader/scripts/cad_statesync.sh push \
  --entry-file steel-geometry/detail.steel.json --project PROJECT --specialty steel

# Validate first; structural errors exit 2 and never produce tonnage
python3 scripts/steel_tonnage.py \
  --validate steel-geometry/detail.steel.json --report contract-health.json

# Calculate JSON/MD/CSV
python3 scripts/steel_tonnage.py \
  --steel steel-geometry/detail.steel.json --out-prefix steel-tonnage
```

### 2. Calculate from an existing contract

```bash
python3 scripts/steel_tonnage.py \
  --steel path/to/detail.steel.json --out-prefix /tmp/steel-tonnage
```

This is a calculation entry, not a second recognition path. The contract must come from the formal chain or from the supported manual template.

### 3. Manual contract (supported fallback)

When the recognition layer is unavailable, constructing `*.steel.json` by hand is supported:

```bash
python3 scripts/steel_tonnage.py --validate examples/minimal.steel.json
python3 scripts/steel_tonnage.py \
  --steel examples/minimal.steel.json --out-prefix /tmp/minimal-ton
```

`examples/minimal.steel.json` is the minimum sample. `examples/README.md` documents required fields, section-to-member matching, millimetre coordinates, and `$`-nested layer names.

### 4. Sensitivity when lengths are missing

```bash
python3 scripts/steel_tonnage.py \
  --steel path/to/detail.steel.json --out-prefix steel-tonnage \
  --length-scenario 4.5 --length-scenario 6 --length-scenario 9
```

`length_scenarios[]` compares uniform member-length assumptions and is explicitly labelled “not a result”.

## Common options

| Option | Purpose | Exit status |
|---|---|---|
| `--check-deps` | Probe `cad-file-reader` / `lis-skill-bus` only | 0 when ready, 1 when missing |
| `--validate <json>` | Contract health check only: fields, unmatched members, count-only sections, length evidence, dependencies | 0 when calculable, 2 on structural errors |
| `--report <json>` | Write the health report as `cad-steel-contract-health/v1` | Follows `--validate` |
| `--steel <json>` | Calculation input | 0 on success |
| `--out-prefix <prefix>` | Output `.json/.md/.csv` prefix | 0 on success |
| `--length-scenario <m>` | Repeatable length-sensitivity scenario | 0 on success |

## Caliber notes

| Item | Current behavior |
|---|---|
| Estimate band | `±15%`, for draft review |
| H sections | 4-part sections use formulas; 2-part H sections are count-only |
| Channels | Fully dimensioned sections use formulas; numbered sections use GB/T 706 |
| I-beams | Numbered `I10`~`I63`, including a/b/c, use GB/T 706 |
| Length | `explicit` first, `drawn` second, `none` produces no tonnage |
| Headline total | `member_level` when the ledger is complete; otherwise `allocated_estimate` draft |
| Grades | Evidence-based Q235/Q345/Q355/Q390/Q420/Q460/S235/S355/A36/16Mn; `unknown_grade` and `mixed_grade` are never defaulted |
| Member merge | Same-code instances merged; category/system conflicts, missing code, or no section go to review |
| Coordinates | `members[].x/y/z/rotation` in mm; missing coordinates set `location_status=missing` |
| Connections | Six categories; explicit quantities first, otherwise label counts with review |
| Finishes | Four area categories; missing area/range is `unavailable`; no fire-rating inference |
| Hoisting allowance | `allowance_advice` suggests 3%/5%/8%, never folded into `total_t` |
| Geometry closure | `geometry_closure` from the recognition layer is passed through as `geometry_closure_check`; this skill does not scan drawings |

## Outputs

Each calculation writes three files:

- `*.json`: `cad-steel-tonnage/v0.2`, with `final_quantity`, length basis, grade bands, member ledger, connection/finish ledgers, review items, section bands, section spectrum, and count-only sections.
- `*.md`: readable review report with recommended total, draft allocation reference, length basis, prerequisite status, and review items at the top.
- `*.csv`: total band, section bands, member ledger, connection/finish summaries, and section spectrum.

Key fields include `length_basis`, `length_used_m`, `rows`, `spec_rows`, `only_count`, `total_t`, `total_basis`, `total_t_member_level`, `total_t_allocated_estimate`, `member_merge`, `length_scenarios`, `allowance_advice`, `geometry_closure_check`, `prerequisites`, `input_evidence`, and `summary`.

When `steel_geometry[]`, `connections[]`, or `finishes[]` is empty, the report says “no evidence in input” so it is not confused with “not implemented”.

## What it does not do

- It does not scan DWG, DXF, DWT, or PDF files. Drawing recognition belongs to `cad-file-reader`.
- It is not for deepened design, fabrication detailing, cutting lists, settlement, formal pricing, or completion measurement.
- It does not fill gaps with defaults: missing length/width/thickness, out-of-table sections, or unknown section types are count-only and remain subject to human review.
- Not supported yet: tonnage for connections other than connection plates, weld tonnage, exact member-to-section mapping and net quantities, grade-based unit-weight adjustment, curved or multipart geometry length, 3D-model coating areas, and fire-rating inference.

## Dependencies

- Python 3.10+; the main calculation entry uses only the standard library.
- Formal recognition: `cad-file-reader>=0.39.2` (with `cad-file-reader:packs/steel-geometry`) and `lis-skill-bus>=0.1.9`.
- Existing or manual contracts: neither skill is required for calculation.

## Validation

```bash
cd scripts/tests
python3 -m unittest test_steel_tonnage
```

v0.3.0 includes **49 synthetic-data unit tests** covering unit-weight formulas, GB/T 706 lookups, both length bases, no-length fallback, contract rejection, duplicate codes, grade bands, `unknown_grade`, connection-plate tonnage and grade residuals, member-merge review, connection categories, finish fallback, member/allocation totals, coordinate passthrough, `--validate`, and length scenarios.

Smoke test:

```bash
cd ../..
python3 scripts/steel_tonnage.py --validate examples/minimal.steel.json
python3 scripts/steel_tonnage.py \
  --steel examples/minimal.steel.json --out-prefix /tmp/minimal-ton
```

## License

`CC-BY-NC-SA-4.0`. Commercial use requires separate written permission from the author; see `LICENSE.md`.
