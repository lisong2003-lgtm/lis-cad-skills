# Steel Tonnage Takeoff (gangjiegou-suanliang)

**[English](./README.en.md) | [中文](./README.md)**

This skill converts an existing `*.steel.json` contract from the `cad-file-reader` steel-geometry pack into a section spectrum and steel tonnage estimate band. It does not read or interpret drawings.

## What it does

- Consumes `cad-steel-geometry/v1` and emits `cad-steel-tonnage/v0.2` as JSON, Markdown, and CSV.
- Uses geometry formulas for fully dimensioned H sections, tubes, rectangular tubes, angles, C/Z purlins, channels, and plates.
- Uses GB/T 706 theoretical weights for numbered hot-rolled channels `[5`~`[40` and I-beams `I10`~`I63`, including a/b/c variants.
- Reports tonnage by steel grade from `materials[]`; members without grade evidence stay in `unknown_grade`.
- Builds a member-code merge ledger with instance counts, section sets, and explicit length evidence; conflicts go to review.
- Counts high-strength bolts, bolts, anchor bolts, studs, connection plates, and stiffeners from `connections[]`; only connection plates with thickness-width-length or thickness-area evidence enter tonnage.
- Reports primer, topcoat, hot-dip galvanizing, and fireproof-coating areas from `finishes[]`; missing area/range stays `unavailable`, and fire ratings are not inferred.
- Uses explicit member lengths first; otherwise sums steel-layer drawn segments. With no length evidence it emits the section spectrum only.
- Reports a `-15%~+15%` band with `final_quantity=false`.

## What it does not do

- It does not scan DWG, DXF, DWT, or PDF files. Drawing recognition belongs to `cad-file-reader`.
- It is not for deepened design, fabrication detailing, cutting lists, settlement, formal pricing, or completion measurement.
- Not supported yet: tonnage for connections other than connection plates, weld tonnage, exact member-to-section mapping and net quantities, grade-based unit-weight adjustment, curved or multipart geometry length, 3D-model coating areas, and fire-rating inference.

## Quick start

```bash
python3 skills/gangjiegou-suanliang/scripts/steel_tonnage.py \
  --steel path/to/detail.steel.json \
  --out-prefix steel-tonnage
```

Generate the input with the cad-file-reader steel pack first:

```bash
bash skills/cad-file-reader/scripts/cad_scan.sh drawing.dwg \
  --with-mtext --with-insert --with-geom --with-geom-layer \
  --detail-json detail.json --format json -o cad-scan

bash skills/cad-file-reader/scripts/cad_steel_geometry.sh \
  detail.json --out-dir steel-geometry
```

## Dependencies

- Python 3.10+
- `cad-file-reader` with the steel-geometry pack for all drawing interpretation

## Validation

```bash
cd skills/gangjiegou-suanliang/scripts/tests
python3 -m unittest test_steel_tonnage
```

## License

`CC-BY-NC-SA-4.0`. Commercial use requires separate written permission from the author; see `LICENSE.md`.
