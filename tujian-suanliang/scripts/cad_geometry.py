#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cad_geometry.py - 把目标楼层图框内图块展开成可复核 DXF/SVG/JSON 几何。

用途：算量前先拿到“真实构件几何”，而不是拿标注短线和尺寸线冒充梁/板/墙柱。
本脚本只展开 LINE/LWPOLYLINE/POLYLINE_2D，按图块引用坐标变换回图面坐标，
保留原图层；随后按图框 bbox 裁剪输出，供人工复核和后续拓扑建模使用。

建议入口：
  cad_scan.sh 图纸.dwg --with-mtext --with-geom --with-geom-layer \
      --detail-json 图纸.detail.json --format json -o 图纸.scan
  cad_geometry.sh 图纸.dwg --scan 图纸.scan.json --detail 图纸.detail.json \
      --floor-label "一层梁平法施工图" --out 一层几何
"""



from __future__ import annotations

try:
    import os as _boot_os, sys as _boot_sys
    _boot_sys.path.insert(0, _boot_os.path.dirname(_boot_os.path.abspath(__file__)))
    import pyboot as _boot_pyboot
    _boot_pyboot.ensure_utf8_io()
except Exception:
    pass


import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
VENDOR_DIR = SKILL_DIR / "vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cad_interpret  # noqa: E402


def _insert_matrix(row: tuple) -> tuple[float, float, float, float, float, float]:
    ix, iy, iz, sx, sy, sz, rot = [float(x) for x in row[1:8]]
    return (
        sx * math.cos(rot),
        -sy * math.sin(rot),
        sx * math.sin(rot),
        sy * math.cos(rot),
        ix,
        iy,
    )


def _compose(a: tuple, b: tuple) -> tuple:
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[0] * b[4] + a[1] * b[5] + a[4],
        a[2] * b[4] + a[3] * b[5] + a[5],
    )


def _apply(pt: tuple, m: tuple) -> tuple:
    return (m[0] * pt[0] + m[1] * pt[1] + m[4],
            m[2] * pt[0] + m[3] * pt[1] + m[5])


def _append_segment(out: list, handle: int, kind: str, a: tuple, b: tuple):
    try:
        if not all(math.isfinite(float(v)) for v in a + b):
            return
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) < 1e-4:
            return
    except (TypeError, ValueError):
        return
    out.append({"handle": int(handle), "kind": kind, "a": a, "b": b})


def expand_drawing_geometry(path: str,
                            max_depth: int = 8) -> list[dict[str, Any]]:
    """递归展开图块引用的线段/多段线几何，不做全图渲染。"""
    import ezdwg
    from ezdwg import raw, read

    doc = read(path)
    lines = list(raw.decode_line_entities(path) or [])
    lwps = list(raw.decode_lwpolyline_entities(path) or [])
    pols = list(raw.decode_polyline_2d_with_vertices(path) or [])
    inserts = list(raw.decode_insert_entities(path) or [])

    block_by_name: dict[str, int] = {}
    for handle, name in raw.decode_block_header_names(path) or []:
        block_by_name.setdefault(str(name or ""), int(handle))

    line_by_owner: dict[int, list] = defaultdict(list)
    lwp_by_owner: dict[int, list] = defaultdict(list)
    pol_by_owner: dict[int, list] = defaultdict(list)
    direct: list[tuple[str, tuple]] = []

    for row in lines:
        placement = doc.entity_placement(int(row[0]))
        if placement is None:
            continue
        if placement[0] == 0 and placement[1] is not None:
            line_by_owner[int(placement[1])].append(row)
        elif placement[0] == 2:
            direct.append(("LINE", row))

    for row in lwps:
        placement = doc.entity_placement(int(row[0]))
        if placement is None:
            continue
        if placement[0] == 0 and placement[1] is not None:
            lwp_by_owner[int(placement[1])].append(row)
        elif placement[0] == 2:
            direct.append(("LWPOLYLINE", row))

    for row in pols:
        placement = doc.entity_placement(int(row[0]))
        if placement is None:
            continue
        if placement[0] == 0 and placement[1] is not None:
            pol_by_owner[int(placement[1])].append(row)
        elif placement[0] == 2:
            direct.append(("POLYLINE_2D", row))

    insert_by_owner: dict[int, list] = defaultdict(list)
    top_inserts: list[tuple[tuple, int]] = []
    for row in inserts:
        placement = doc.entity_placement(int(row[0]))
        if placement is None:
            continue
        if placement[0] == 0 and placement[1] is not None:
            insert_by_owner[int(placement[1])].append(row)
        elif placement[0] == 2:
            name = str(row[-1] or "")
            if name in block_by_name:
                top_inserts.append((row, block_by_name[name]))

    def emit(kind: str, row: tuple, m: tuple, source_block: str = "MODELSPACE"):
        handle = int(row[0])
        if kind == "LINE":
            _append_segment(
                out, handle, kind,
                _apply((float(row[1]), float(row[2])), m),
                _apply((float(row[4]), float(row[5])), m),
            )
            out[-1]["block"] = source_block
            return
        pts = row[2]
        if kind == "POLYLINE_2D":
            pts = [(float(p[0]), float(p[1])) for p in pts]
        for i in range(1, len(pts)):
            a = _apply((float(pts[i - 1][0]), float(pts[i - 1][1])), m)
            b = _apply((float(pts[i][0]), float(pts[i][1])), m)
            _append_segment(out, handle, kind, a, b)
            out[-1]["block"] = source_block

    out: list[dict[str, Any]] = []
    for kind, row in direct:
        emit(kind, row, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))

    for row, block_handle in top_inserts:
        top_name = str(row[-1] or "BLOCK")
        stack = [(block_handle, _insert_matrix(row), 0, top_name)]
        visited: set[int] = set()
        while stack:
            owner, matrix, depth, source_block = stack.pop()
            if owner in visited or depth > max_depth:
                continue
            visited.add(owner)
            for kind, group in (("LINE", line_by_owner), ("LWPOLYLINE", lwp_by_owner),
                                ("POLYLINE_2D", pol_by_owner)):
                for entity_row in group.get(owner, []):
                    emit(kind, entity_row, matrix, source_block)
            for nested in insert_by_owner.get(owner, []):
                name = str(nested[-1] or "")
                if name in block_by_name:
                    stack.append((block_by_name[name],
                                  _compose(matrix, _insert_matrix(nested)),
                                  depth + 1,
                                  f"{source_block}/{name}"))
    return out


def layer_map(path: str, handles: list[int]) -> dict[int, str]:
    import ezdwg
    from ezdwg import raw

    names = dict(raw.decode_layer_names(path) or [])
    result: dict[int, str] = {}
    uniq = list(dict.fromkeys(handles))
    for i in range(0, len(uniq), 5000):
        try:
            rows = raw.decode_object_entity_layer_handles(path, uniq[i:i + 5000]) or []
            for handle, layer_handle in rows:
                result[int(handle)] = names.get(int(layer_handle), "")
        except Exception:
            continue
    return result


def point_in_bbox(pt: tuple, bbox: list[float], margin: float) -> bool:
    x, y = pt
    return (bbox[0] - margin <= x <= bbox[2] + margin and
            bbox[1] - margin <= y <= bbox[3] + margin)


def point_in_polygon(pt: tuple, polygon: list) -> bool:
    """射线法判点在多边形内（凸凹皆可，边界按外处理）。"""
    x, y = float(pt[0]), float(pt[1])
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = float(polygon[index][0]), float(polygon[index][1])
        x2, y2 = float(polygon[(index + 1) % count][0]), float(polygon[(index + 1) % count][1])
        if (y1 > y) != (y2 > y):
            ratio = (y - y1) / (y2 - y1)
            if x < x1 + ratio * (x2 - x1):
                inside = not inside
    return inside


def distance_to_polygon(pt: tuple, polygon: list) -> float:
    """点到多边形边线的最短距离；点在面域内返回 0。"""
    if point_in_polygon(pt, polygon):
        return 0.0
    x, y = float(pt[0]), float(pt[1])
    best = None
    count = len(polygon)
    for index in range(count):
        x1, y1 = float(polygon[index][0]), float(polygon[index][1])
        x2, y2 = float(polygon[(index + 1) % count][0]), float(polygon[(index + 1) % count][1])
        dx, dy = x2 - x1, y2 - y1
        norm = dx * dx + dy * dy
        ratio = 0.0 if norm <= 1e-12 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / norm))
        dist = math.hypot(x - (x1 + ratio * dx), y - (y1 + ratio * dy))
        if best is None or dist < best:
            best = dist
    return best if best is not None else 0.0


def find_sheet_bbox(scan_json: Optional[Path], detail_json: Optional[Path],
                    floor_label: str) -> Optional[list[float]]:
    data = {}
    if scan_json:
        try:
            data.update(json.loads(scan_json.read_text(encoding="utf-8")))
        except Exception:
            pass
    if detail_json and detail_json.exists():
        try:
            data.update(json.loads(detail_json.read_text(encoding="utf-8")))
        except Exception:
            pass
    labels = cad_interpret.detect_sheet_labels(data) if data.get("text_records") or data.get("keyword_rows") else {}
    target = None
    for sheet_id, label in labels.items():
        if floor_label in str(label) or str(label) in floor_label:
            target = str(sheet_id)
            break
    if target is None:
        return None
    for sheet in (data.get("meta") or {}).get("sheets") or []:
        if str(sheet.get("id")) == target and sheet.get("bbox"):
            return [float(v) for v in sheet["bbox"]]
    return None


def color_for_layer(layer: str) -> int:
    text = str(layer or "")
    if re.search(r"梁.*(实线|虚线)|梁-实线|梁-虚线|BEAM", text, re.I):
        return 1
    if re.search(r"板边线|板.*板边线|降板边线|S-SLAB", text, re.I):
        return 5
    if re.search(r"剪力墙|S-柱|COLU|WALL|砼墙", text, re.I):
        return 3
    return 7


def _svg_color(dxf_color: int) -> str:
    palette = {
        1: "#e23b3b",
        3: "#2d9c4a",
        5: "#3974e0",
        6: "#d84fc4",
        7: "#666666",
    }
    return palette.get(dxf_color, "#888888")


def _dxf_layer_name(layer: str) -> str:
    text = str(layer or "").strip()
    text = re.sub(r"[<>\\/:;?\"*|=,\x00-\x1f]", "_", text)
    text = re.sub(r"[^\w\s\u4e00-\u9fff\-()]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip("._ ")
    if not text:
        text = "layer_0"
    return text[:250]


def _svg_escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def write_svg(out_path: Path, bbox: list[float],
              segments: list[dict[str, Any]],
              layers: dict[int, str]) -> None:
    """把保留几何写成可浏览器直接打开的 SVG，供人工复核。"""
    x0, y0, x1, y1 = bbox
    width = 1600
    height = max(600, int(width * max(0.2, (y1 - y0) / max(1e-6, x1 - x0))))
    sx = width / max(1e-6, x1 - x0)
    sy = height / max(1e-6, y1 - y0)

    def to_xy(pt):
        px, py = pt
        return ((px - x0) * sx, height - (py - y0) * sy)

    body: list[str] = []
    for seg in segments:
        original_layer = str(layers.get(int(seg["handle"]), "0") or "0")
        stroke = _svg_color(color_for_layer(original_layer))
        try:
            xa, ya = to_xy(seg["a"])
            xb, yb = to_xy(seg["b"])
        except (TypeError, ValueError, KeyError):
            continue
        body.append(f'<line x1="{xa:.2f}" y1="{ya:.2f}" '
                    f'x2="{xb:.2f}" y2="{yb:.2f}" '
                    f'stroke="{stroke}" stroke-width="1.1" '
                    f'data-layer="{_svg_escape(_dxf_layer_name(original_layer))}"/>')

    defs = ["<style>svg{background:#fff}line{shape-rendering:geometricPrecision}</style>"]
    svg = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        *defs,
        '<g transform="translate(0 0)">',
        *body,
        "</g>",
        f'<text x="18" y="{height - 18}" font-size="15" fill="#333">'
        f'CAD expanded geometry: {_svg_escape(str(x0))}, '
        f'{_svg_escape(str(y0))} - {_svg_escape(str(x1))}, '
        f'{_svg_escape(str(y1))}</text>',
        "</svg>",
    ])
    out_path.write_text(svg, encoding="utf-8")


def write_dxf(out_path: Path, bbox: list[float], margin: float,
              segments: list[dict[str, Any]], layers: dict[int, str]) -> None:
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    seen_layers: set[str] = set()
    safe_names: dict[str, str] = {}
    for seg in segments:
        original_layer = layers.get(int(seg["handle"]), "0")
        safe_layer = safe_names.get(original_layer)
        if safe_layer is None:
            safe_layer = _dxf_layer_name(original_layer)
            safe_names[original_layer] = safe_layer
        if safe_layer not in seen_layers and safe_layer not in doc.layers:
            seen_layers.add(safe_layer)
            doc.layers.add(safe_layer, color=color_for_layer(original_layer))
        msp.add_line(seg["a"], seg["b"], dxfattribs={"layer": safe_layer})
    doc.layers.add("__SHEET_BBOX", color=6)
    p1 = (bbox[0], bbox[1])
    p2 = (bbox[2], bbox[1])
    p3 = (bbox[2], bbox[3])
    p4 = (bbox[0], bbox[3])
    for a, b in ((p1, p2), (p2, p3), (p3, p4), (p4, p1)):
        msp.add_line(a, b, dxfattribs={"layer": "__SHEET_BBOX"})
    doc.saveas(str(out_path))


def write_md(out_path: Path, info: dict[str, Any]) -> None:
    lines = [
        "# CAD 目标楼层图块展开与几何复核",
        "",
        f"- 源文件：{info.get('source')}",
        f"- 目标图框：{info.get('sheet')}",
        f"- 目标图纸名：{info.get('sheet_label') or '-'}",
        f"- 图框范围：{info.get('bbox')}",
        f"- 展开总线段：{info.get('expanded_segments')}",
        f"- 目标范围保留：{info.get('kept_segments')}",
        f"- 实体类型：LINE/LWPOLYLINE/POLYLINE_2D",
        "",
        "## 图层保留",
        "",
        "| 图层 | 线段数 |",
        "|---|---:|",
    ]
    for layer, count in info.get("layer_counts", {}).items():
        lines.append(f"| {layer} | {count} |")
    if info.get("block_counts"):
        lines += ["", "## 展开来源块", "", "| 块/嵌套块 | 保留线段 |", "|---|---:|"]
        for block, count in info.get("block_counts", {}).items():
            lines.append(f"| {block} | {count} |")
    lines += [
        "",
        "## 说明",
        "",
        "该 DXF 用于人工核对，不是最终算量。若目标范围只看到标注线和附加筋线，",
        "说明该 DWG 的真实构件几何仍位于其他图框/视口/未展开块中，需继续排查图框映射。",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="CAD 目标楼层图块展开与几何复核")
    ap.add_argument("dwg")
    ap.add_argument("--scan", default=None)
    ap.add_argument("--detail", default=None)
    ap.add_argument("--floor-label", default=None)
    ap.add_argument("--bbox", default=None,
                    help="x0,y0,x1,y1；未传时从 --scan/--detail + --floor-label 自动取")
    ap.add_argument("--margin", type=float, default=25000.0)
    ap.add_argument("-o", "--out", default="cad_geometry")
    ap.add_argument("--format", default="all",
                    choices=["all", "dxf", "json", "md", "svg"])
    args = ap.parse_args()

    bbox = None
    if args.bbox:
        try:
            vals = [float(v) for v in args.bbox.split(",")]
            if len(vals) == 4:
                bbox = vals
        except ValueError:
            pass
    if bbox is None:
        scan_path = Path(args.scan) if args.scan else None
        detail_path = Path(args.detail) if args.detail else None
        bbox = find_sheet_bbox(scan_path, detail_path, args.floor_label or "")
    if not bbox:
        print("无法确定目标图框；请传 --bbox x0,y0,x1,y1 或 --scan/--detail/--floor-label",
              file=sys.stderr)
        return 2

    print("正在展开图块几何...", file=sys.stderr)
    segments = expand_drawing_geometry(args.dwg)
    handles = [int(seg["handle"]) for seg in segments]
    layers = layer_map(args.dwg, handles)
    kept = [seg for seg in segments if
            point_in_bbox(seg["a"], bbox, args.margin) or
            point_in_bbox(seg["b"], bbox, args.margin)]
    counts = Counter(layers.get(int(seg["handle"]), "") for seg in kept)
    layer_counts = dict(counts.most_common())
    block_counts = Counter(str(seg.get("block") or "MODELSPACE") for seg in kept)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.format in ("svg", "all"):
        svg_path = out.with_suffix(".svg")
        write_svg(svg_path, bbox, kept, layers)
        print(f"已写出 {svg_path}", file=sys.stderr)
    if args.format in ("dxf", "all"):
        dxf_path = out.with_suffix(".dxf")
        write_dxf(dxf_path, bbox, args.margin, kept, layers)
        print(f"已写出 {dxf_path}", file=sys.stderr)

    info = {
        "source": args.dwg,
        "sheet": args.floor_label or "bbox",
        "sheet_label": args.floor_label or "",
        "bbox": bbox,
        "margin": args.margin,
        "expanded_segments": len(segments),
        "kept_segments": len(kept),
        "layer_counts": layer_counts,
        "block_counts": dict(block_counts.most_common()),
    }
    if args.format in ("json", "all"):
        json_path = out.with_suffix(".json")
        json_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写出 {json_path}", file=sys.stderr)
    if args.format in ("md", "all"):
        md_path = out.with_suffix(".md")
        write_md(md_path, info)
        print(f"已写出 {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
