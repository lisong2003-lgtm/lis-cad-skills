#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SKILL_DIR / "vendor"))
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_quantity_pipeline as pipeline  # noqa: E402
import cad_quantity_report as report  # noqa: E402
import cad_member_intersection_audit as intersection  # noqa: E402
import cad_slab_opening_audit as slab_opening  # noqa: E402
import cad_beam_gap_attribution as beam_gap  # noqa: E402
import cad_beam_coverage_audit as beam_coverage  # noqa: E402
import cad_beam_candidate_attribution as beam_attribution  # noqa: E402
import cad_beam_frame_label_index as frame_index  # noqa: E402
import cad_beam_span_closure as span_closure  # noqa: E402
import cad_beam_multispan_closure as multispan  # noqa: E402
import cad_beam_instance_dedup as dedup  # noqa: E402
import cad_beam_attribution_conflict as attribution_conflict  # noqa: E402
import cad_concrete_grade as grade  # noqa: E402


def sample_scan() -> dict:
    return {
        "members": {
            "梁": {
                "KL1(2)": {
                    "count": 3,
                    "est": 2,
                    "b": "200",
                    "h": "500",
                    "stirrup": "C8@100/200(2)",
                    "l_txt": "2C18",
                    "rebar": ["C8@100/200(2)", "2C18"],
                    "span": "2",
                },
            },
            "柱": {
                "KZ1": {
                    "count": 8,
                    "est": 8,
                },
            },
            "板": {
                "B1": {
                    "count": 4,
                    "est": 2,
                    "sizes": ["h=120"],
                    "rebar": ["C8@200"],
                },
            },
        },
        "rebar_summary": {
            "箍筋": [{
                "型号": "C8@100/200(2)",
                "构件型数": 1,
                "估算根数": 20,
                "构件编号": "KL1(2)",
            }],
            "纵筋": [{
                "型号": "2C18",
                "构件型数": 1,
                "估算根数": 4,
                "构件编号": "KL1(2)",
            }],
        },
        "slab_thk": {"120": 4},
        "spec": {"混凝土等级": {"C30": 2}},
        "notes": ["柱表需要回图复核"],
    }


def sample_model() -> dict:
    return {
        "schema": "cad-structure-model/v0.5",
        "floor": {"label": "二层梁平法施工图"},
        "members": {
            "beams": [{
                "id": "B0001",
                "code": "KL1(2)",
                "section": "200x500",
                "centerline_length_mm": 6000.0,
                "clear_length_mm": 5200.0,
                "gross_volume_m3": 0.6,
                "clear_volume_m3": 0.52,
                "support_count": 2,
                "quantity_status": "clear-span-review",
                "position": {"x": 100.0, "y": 200.0},
            }],
            "slabs": [{
                "id": "S0001",
                "area_m2": 20.0,
                "gross_area_m2": 20.0,
                "opening_count": 0,
                "opening_area_m2": 0.0,
                "thickness_mm": 120.0,
                "volume_m3": 2.4,
                "status": "closed",
            }],
            "columns": [{
                "label": "KZ1",
                "b_mm": 500.0,
                "h_mm": 500.0,
                "status": "geometry",
            }],
        },
        "quantities": {
            "beam": {"topology_volume_m3": 0.6},
        },
        "issues": [{
            "member_type": "beam",
            "member_id": "B0001",
            "code": "KL1(2)",
            "issue": "支座待复核",
        }],
    }


def sample_ledger() -> dict:
    return {
        "schema": "cad-concrete-ledger/v0.1",
        "formal_ready": False,
        "reference_values": {"梁及连梁": 0.55},
        "quantities": {
            "beam_topology_volume_m3": 0.6,
            "candidate_total_volume_m3": 0.52,
        },
        "comparisons": [{
            "component": "梁及连梁",
            "scope": "净跨候选",
            "candidate_value_m3": 0.52,
            "reference_value_m3": 0.55,
            "difference_m3": -0.03,
            "difference_pct": -5.45,
            "status": "candidate",
        }],
        "gate_summary": {"fail": 1},
        "gates": [{
            "id": "beam-support",
            "title": "梁支座",
            "status": "fail",
            "evidence": "仍有推定支座",
            "action": "回原图复核",
        }],
    }


class QuantityReportTests(unittest.TestCase):
    def test_builds_direct_schedules_and_anomalies(self):
        result = report.build_report(
            sample_model(),
            sample_ledger(),
            sample_scan(),
            floor_label="二层梁平法施工图",
        )
        self.assertFalse(result["formal_ready"])
        self.assertEqual(result["direct_outputs"]["component_schedule_count"], 3)
        self.assertEqual(result["direct_outputs"]["rebar_type_count"], 2)
        self.assertEqual(result["direct_outputs"]["column_schedule_count"], 2)
        self.assertEqual(result["direct_outputs"]["slab_schedule_count"], 1)
        self.assertEqual(result["direct_outputs"]["beam_schedule_count"], 1)
        self.assertEqual(
            result["direct_outputs"]["gate_status_counts"],
            {"fail": 1},
        )
        self.assertTrue(any(
            row["status"] == "beam-support"
            and row["severity"] == "blocking"
            for row in result["anomalies"]
        ))
        self.assertIn("formal_ready", report.render_markdown(result))
        self.assertGreater(len(report.csv_rows(result)), 5)

    def test_closure_dashboard_groups_blockers_and_actions(self):
        result = report.build_report(
            sample_model(),
            sample_ledger(),
            sample_scan(),
            supplements={
                "梁实例": {
                    "schema": "cad-beam-reference-reconciliation/v0.1",
                    "summary": {
                        "reference_main_instance_count": 2,
                        "selected_equivalent_instance_count": 1,
                        "missing_equivalent_instance_count": 1,
                    },
                    "beam_code_reconciliation": [{
                        "code": "KL1(1)",
                        "missing_equivalent_instance_count": 1,
                        "status": "missing-repeat-or-truncated-geometry",
                    }],
                },
                "板材料": {
                    "schema": "cad-composite-slab-material-ledger/v0.1",
                    "remaining_blockers": ["YDB-4/YDB-5 编码归属复核"],
                },
            },
        )
        dashboard = result["closure_dashboard"]
        self.assertEqual(
            dashboard["gate_status_counts"], {"fail": 1})
        self.assertTrue(any(
            row["area"] == "beam"
            and row["status"] == "missing-equivalent-instance"
            and row["count"] == 1
            for row in dashboard["blocking_groups"]
        ))
        self.assertTrue(any(
            row["component"] == "梁等效实例"
            and row["remaining_count"] == 1
            for row in dashboard["component_gaps"]
        ))
        self.assertIn("YDB-4/YDB-5 编码归属复核", dashboard["next_actions"])
        self.assertIn("闭合门槛与阻断分组", report.render_markdown(result))

    def test_phase15_openings_are_exposed_without_faking_closure(self):
        model = sample_model()
        model["slab"] = {}
        model["members"]["slabs"][0].update({
            "opening_count": 1,
            "opening_area_m2": 2.0,
            "opening_status": "confirmed-opening",
        })
        model["phase15"] = {
            "openings": [{
                "panel_id": "S0001",
                "area_m2": 2.0,
                "panel_match_status": "matched",
            }],
            "summary": {
                "panel_area_m2": 20.0,
                "opening_count": 1,
                "opening_area_m2": 2.0,
                "net_panel_area_m2": 18.0,
                "thickness_area_m2": {"120": 20.0},
                "slab_rough_volume_m3": 2.16,
            },
        }
        supplement = {
            "schema": "cad-composite-slab-material-ledger/v0.1",
            "phase15": {
                "net_panel_area_m2": 18.0,
                "slab_rough_volume_m3": 2.16,
            },
        }
        result = report.build_report(
            model,
            sample_ledger(),
            sample_scan(),
            supplements={"材料分账": supplement},
        )
        direct = result["direct_outputs"]
        self.assertEqual(direct["slab_phase15_gross_area_m2"], 20.0)
        self.assertEqual(direct["slab_phase15_opening_count"], 1)
        self.assertEqual(direct["slab_phase15_opening_area_m2"], 2.0)
        self.assertEqual(direct["slab_phase15_net_area_m2"], 18.0)
        self.assertEqual(direct["slab_phase15_rough_volume_m3"], 2.16)
        slab = result["slab_schedule"][0]
        self.assertEqual(slab["gross_area_m2"], 20.0)
        self.assertEqual(slab["net_area_m2"], 18.0)
        self.assertEqual(slab["opening_status"], "confirmed-opening")
        self.assertEqual(result["formal_ready"], False)
        material = result["supplemental_breakdown"]["材料分账"]
        self.assertEqual(
            material["phase15_summary"]["slab_rough_volume_m3"], 2.16)
        markdown = report.render_markdown(result)
        self.assertIn("板拓扑净面积m2", markdown)
        self.assertIn("板厚粗折候选m3", markdown)

    def test_supplement_model_is_normalized(self):
        supplement = {
            "schema": "cad-special-member-and-wall-attribution/v0.1",
            "floor": "首层",
            "status": "component-attributed-not-closed",
            "edge_member_spatial_attribution": {
                "status": "component-attributed-not-closed",
                "outside_total_m2": 1.451,
                "significant_member_count": 16,
                "members": [{
                    "id": "EM0011",
                    "label": "YBZ1",
                    "outside_area_m2": 0.0799,
                    "bbox_mm": [1, 2, 3, 4],
                    "review_required": True,
                }],
            },
            "special_member_localization": {
                "TL2": {
                    "status": "reference-compatible-plan-geometry-localized",
                    "reference_volume_m3": 1.2,
                },
            },
        }
        result = report.build_report(
            sample_model(),
            sample_ledger(),
            sample_scan(),
            supplements={"特殊构件": supplement},
        )
        normalized = result["supplemental_breakdown"]["特殊构件"]
        self.assertEqual(
            normalized["edge_member_spatial"]["outside_total_m2"], 1.451)
        self.assertIn("TL2", normalized["special_members"])
        self.assertTrue(any(
            row["member_id"] == "EM0011"
            for row in result["anomalies"]
        ))

    def test_beam_reference_reconciliation_is_normalized(self):
        supplement = {
            "schema": "cad-beam-reference-reconciliation/v0.1",
            "floor": "首层",
            "status": "research-only-reference-constrained",
            "summary": {
                "reference_main_instance_count": 3,
                "selected_equivalent_instance_count": 2,
                "missing_equivalent_instance_count": 1,
                "raw_topology_volume_m3": 0.4,
            },
            "transfer_projection": {
                "grade_a_absolute_code_error_m3": 0.18,
                "grade_ab_absolute_code_error_m3": 0.12,
                "transfers": [{
                    "run_id": "R0002",
                    "from": "KL1",
                    "to": "WKL1",
                    "grade": "B",
                    "applied": False,
                    "basis": "无直接引线，仅复核",
                }],
            },
            "beam_code_reconciliation": [{
                "code": "KL1(1)",
                "reference_instance_count": 2,
                "selected_equivalent_instance_count": 1,
                "missing_equivalent_instance_count": 1,
                "current_code_volume_m3": 0.10,
                "reference_volume_m3": 0.20,
                "status": "missing-repeat-or-truncated-geometry",
            }],
        }
        result = report.build_report(
            sample_model(),
            sample_ledger(),
            sample_scan(),
            supplements={"梁实例": supplement},
        )
        normalized = result["supplemental_breakdown"]["梁实例"]
        self.assertEqual(len(normalized["missing_by_code"]), 1)
        self.assertEqual(
            normalized["missing_by_code"][0]["code"], "KL1(1)")
        self.assertEqual(
            result["direct_outputs"]["beam_reference_instance_count"], 3)
        self.assertEqual(
            result["direct_outputs"]["beam_missing_equivalent_instance_count"],
            1,
        )
        self.assertTrue(any(
            row["code"] == "KL1(1)"
            and row["status"] == "missing-equivalent-instance"
            for row in result["anomalies"]
        ))
        self.assertTrue(any(
            row["status"] == "transfer-review-only"
            for row in result["anomalies"]
        ))
        self.assertIn("梁实例对账", report.render_markdown(result))

    def test_embedded_concrete_ledger_is_normalized(self):
        ledger = {
            "schema": "cad-special-member-and-wall-attribution/v0.1",
            "formal_ready": False,
            "status": "component-attributed-not-closed",
            "concrete_ledger": {
                "main_beam_cad_m3": 25.7983,
                "located_beam_total_m3": 32.6986,
                "beam_reference_m3": 33.7613,
                "beam_remaining_m3": 1.0627,
                "vertical_candidate_m3": 126.5772,
                "vertical_reference_m3": 126.7169,
                "vertical_remaining_m3": 0.1397,
                "slab_m3": 113.9678,
                "located_total_m3": 273.2436,
                "reference_total_m3": 274.446,
                "remaining_total_m3": 1.2024,
                "beam_coverage_ratio": 0.968523,
            },
        }
        result = report.build_report(
            sample_model(),
            ledger,
            sample_scan(),
        )
        self.assertEqual(
            result["direct_outputs"]["concrete_candidate_total_m3"],
            273.2436,
        )
        self.assertEqual(
            result["direct_outputs"]["concrete_reference_total_m3"],
            274.446,
        )


class QuantityPipelineTests(unittest.TestCase):
    def test_label_suffix_is_deterministic(self):
        self.assertEqual(
            pipeline._label_suffix("标高-1.060~2.810墙柱平法施工图"),
            pipeline._label_suffix("标高-1.060~2.810墙柱平法施工图"),
        )
        self.assertNotEqual(
            pipeline._label_suffix("一层"),
            pipeline._label_suffix("二层"),
        )

    def test_plan_only_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dwg"
            scan = root / "scan.json"
            dwg.write_bytes(b"DWG")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py",
                "--dwg", str(dwg),
                "--scan", str(scan),
                "--floor-label", "二层梁平法施工图",
                "--out", str(out),
                "--plan-only",
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(manifest["status"], "planned")
            self.assertEqual(manifest["floor"]["beam_label"], "二层梁平法施工图")

    def test_pipeline_runs_intersection_audit_and_supplies_unified_report(self):
        def fake_run(name, script, arguments, **_kwargs):
            if "-o" in arguments:
                output = Path(arguments[arguments.index("-o") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                if name == "structure-model":
                    output.with_suffix(".json").write_text(json.dumps({
                        "floor": {"story_height_mm": 3870},
                        "quantities": {"beam": {"topology_volume_m3": 1}},
                    }), encoding="utf-8")
                elif name == "concrete-ledger":
                    output.with_suffix(".json").write_text(json.dumps({
                        "quantities": {"candidate_total_volume_m3": 1},
                        "formal_ready": False,
                    }), encoding="utf-8")
                elif name == "quantity-report":
                    output.with_suffix(".json").write_text(json.dumps({
                        "direct_outputs": {"concrete_candidate_total_m3": 1},
                    }), encoding="utf-8")
                else:
                    output.with_suffix(".json").write_text("{}", encoding="utf-8")
            return {
                "name": name,
                "status": "ok",
                "command": [script, *arguments],
                "elapsed_seconds": 0.0,
                "attempts": [],
            }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            dwg.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py",
                "--dwg", str(dwg),
                "--scan", str(scan),
                "--floor-label", "二层梁平法施工图",
                "--out", str(out),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake_run):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(encoding="utf-8"))
            steps = {row["name"]: row for row in manifest["steps"]}
            self.assertIn("member-intersection-audit", steps)
            report_command = steps["quantity-report"]["command"]
            self.assertTrue(any(
                item.startswith("构件相交=") for item in report_command))
            self.assertIn(
                "member_intersection_audit.json",
                manifest["artifacts"]["member_intersection_json"],
            )

    def test_pipeline_runs_slab_opening_audit_when_slab_dxf_exists(self):
        def fake_run(name, script, arguments, **_kwargs):
            if "-o" not in arguments:
                return {
                    "name": name, "status": "ok",
                    "command": [script, *arguments],
                    "elapsed_seconds": 0.0, "attempts": [],
                }
            output = Path(arguments[arguments.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            if name == "structure-model":
                output.with_suffix(".json").write_text(json.dumps({
                    "floor": {"story_height_mm": 3870},
                    "quantities": {"beam": {"topology_volume_m3": 1}},
                }), encoding="utf-8")
            elif name == "concrete-ledger":
                output.with_suffix(".json").write_text(json.dumps({
                    "quantities": {"candidate_total_volume_m3": 1},
                    "formal_ready": False,
                }), encoding="utf-8")
            elif name == "quantity-report":
                output.with_suffix(".json").write_text(json.dumps({
                    "direct_outputs": {"concrete_candidate_total_m3": 1},
                }), encoding="utf-8")
            elif name == "slab-opening-audit":
                output.with_suffix(".json").write_text(json.dumps({
                    "schema": slab_opening.SCHEMA,
                    "summary": {"source_entity_count": 3},
                }), encoding="utf-8")
                output.with_suffix(".dxf").write_text("DXF", encoding="utf-8")
            else:
                output.with_suffix(".json").write_text("{}", encoding="utf-8")
                if name.endswith("geometry"):
                    output.with_suffix(".dxf").write_text("DXF", encoding="utf-8")
            return {
                "name": name,
                "status": "ok",
                "command": [script, *arguments],
                "elapsed_seconds": 0.0,
                "attempts": [],
            }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            dwg.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py",
                "--dwg", str(dwg),
                "--scan", str(scan),
                "--floor-label", "二层梁平法施工图",
                "--slab-floor-label", "二层板结构施工图",
                "--out", str(out),
                "--reference-gap-m3", "1.2024",
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake_run):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(encoding="utf-8"))
            steps = {row["name"]: row for row in manifest["steps"]}
            self.assertEqual(steps["slab-opening-audit"]["status"], "ok")
            command = steps["slab-opening-audit"]["command"]
            self.assertIn("--reference-gap-m3", command)
            report_command = steps["quantity-report"]["command"]
            self.assertTrue(any(
                item.startswith("板洞口=") for item in report_command))
            self.assertIn(
                "slab_opening_audit.json",
                manifest["artifacts"]["slab_opening_json"],
            )

    def test_pipeline_skips_slab_opening_audit_when_switch_given(self):
        def fake_run(name, script, arguments, **_kwargs):
            if name == "structure-model":
                output = Path(arguments[arguments.index("-o") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.with_suffix(".json").write_text(json.dumps({
                    "floor": {}, "quantities": {}}), encoding="utf-8")
            elif name == "concrete-ledger":
                output = Path(arguments[arguments.index("-o") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.with_suffix(".json").write_text(json.dumps({
                    "quantities": {}, "formal_ready": False}), encoding="utf-8")
            elif name == "quantity-report":
                output = Path(arguments[arguments.index("-o") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.with_suffix(".json").write_text(
                    json.dumps({"direct_outputs": {}}), encoding="utf-8")
            return {
                "name": name, "status": "ok",
                "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": [],
            }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            dwg.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py",
                "--dwg", str(dwg),
                "--scan", str(scan),
                "--floor-label", "二层梁平法施工图",
                "--out", str(out),
                "--no-slab-opening-audit",
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake_run):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(encoding="utf-8"))
            steps = {row["name"]: row for row in manifest["steps"]}
            self.assertEqual(steps["slab-opening-audit"]["status"], "skipped")
            self.assertEqual(manifest["artifacts"]["slab_opening_json"], "")


    def test_pipeline_runs_beam_gap_when_reconciliation_given(self):
        def fake_run(name, script, arguments, **_kwargs):
            output = Path(arguments[arguments.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            if name == "structure-model":
                payload = {"floor": {}, "quantities": {}}
            elif name == "concrete-ledger":
                payload = {"quantities": {}, "formal_ready": False}
            elif name == "quantity-report":
                payload = {"direct_outputs": {}}
            else:
                payload = {}
            output.with_suffix(".json").write_text(
                json.dumps(payload), encoding="utf-8")
            if name.endswith("geometry"):
                output.with_suffix(".dxf").write_text("DXF", encoding="utf-8")
            return {
                "name": name, "status": "ok",
                "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": [],
            }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            recon = root / "recon.json"
            dwg.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            recon.write_text(json.dumps({
                "schema": "cad-beam-reference-reconciliation/v0.1",
                "beam_code_reconciliation": [],
            }), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py",
                "--dwg", str(dwg),
                "--scan", str(scan),
                "--floor-label", "二层梁平法施工图",
                "--out", str(out),
                "--beam-gap-reconciliation-json", str(recon),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake_run):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(encoding="utf-8"))
            steps = {row["name"]: row for row in manifest["steps"]}
            self.assertEqual(steps["beam-gap-attribution"]["status"], "ok")
            self.assertIn(
                "--reconciliation-json",
                steps["beam-gap-attribution"]["command"])
            self.assertTrue(any(
                item.startswith("梁量差=")
                for item in steps["quantity-report"]["command"]))
            self.assertIn(
                "beam_gap_attribution.json",
                manifest["artifacts"]["beam_gap_json"])

    def test_pipeline_skips_beam_gap_without_reconciliation(self):
        def fake_run(name, script, arguments, **_kwargs):
            output = Path(arguments[arguments.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            if name == "structure-model":
                payload = {"floor": {}, "quantities": {}}
            elif name == "concrete-ledger":
                payload = {"quantities": {}, "formal_ready": False}
            elif name == "quantity-report":
                payload = {"direct_outputs": {}}
            else:
                payload = {}
            output.with_suffix(".json").write_text(
                json.dumps(payload), encoding="utf-8")
            if name.endswith("geometry"):
                output.with_suffix(".dxf").write_text("DXF", encoding="utf-8")
            return {
                "name": name, "status": "ok",
                "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": [],
            }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            dwg.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py",
                "--dwg", str(dwg),
                "--scan", str(scan),
                "--floor-label", "二层梁平法施工图",
                "--out", str(out),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake_run):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(encoding="utf-8"))
            steps = {row["name"]: row for row in manifest["steps"]}
            self.assertEqual(steps["beam-gap-attribution"]["status"], "skipped")
            self.assertEqual(manifest["artifacts"]["beam_gap_json"], "")


    def test_pipeline_runs_beam_coverage_audit_and_supplies_report(self):
        def fake_run(name, script, arguments, **_kwargs):
            output = Path(arguments[arguments.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            if name == "structure-model":
                payload = {"floor": {}, "quantities": {}}
            elif name == "concrete-ledger":
                payload = {"quantities": {}, "formal_ready": False}
            elif name == "beam-gap-attribution":
                payload = {"summary": {"residual_needing_new_geometry_m3": 1.0413}}
            elif name == "quantity-report":
                payload = {"direct_outputs": {}}
            else:
                payload = {}
            output.with_suffix(".json").write_text(
                json.dumps(payload), encoding="utf-8")
            if name.endswith("geometry"):
                output.with_suffix(".dxf").write_text("DXF", encoding="utf-8")
            return {
                "name": name, "status": "ok",
                "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": [],
            }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            recon = root / "recon.json"
            dwg.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            recon.write_text(json.dumps({
                "schema": "cad-beam-reference-reconciliation/v0.1",
                "beam_code_reconciliation": [],
            }), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py",
                "--dwg", str(dwg),
                "--scan", str(scan),
                "--floor-label", "二层梁平法施工图",
                "--out", str(out),
                "--beam-gap-reconciliation-json", str(recon),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake_run):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(encoding="utf-8"))
            steps = {row["name"]: row for row in manifest["steps"]}
            self.assertEqual(steps["beam-coverage-audit"]["status"], "ok")
            command = steps["beam-coverage-audit"]["command"]
            self.assertIn("--residual-gap-m3", command)
            self.assertEqual(
                command[command.index("--residual-gap-m3") + 1], "1.0413")
            self.assertEqual(command[0], "cad_beam_coverage_audit.py")
            self.assertIn("--model-json", command)
            self.assertTrue(any(
                item.startswith("梁覆盖=")
                for item in steps["quantity-report"]["command"]))
            self.assertIn(
                "beam_coverage_audit.json",
                manifest["artifacts"]["beam_coverage_json"])
            self.assertEqual(
                steps["beam-candidate-attribution"]["status"], "ok")
            attribution_command = steps[
                "beam-candidate-attribution"]["command"]
            self.assertEqual(
                attribution_command[0], "cad_beam_candidate_attribution.py")
            self.assertIn("--coverage-json", attribution_command)
            self.assertIn("--gap-json", attribution_command)
            self.assertTrue(any(
                item.startswith("梁候选归属=")
                for item in steps["quantity-report"]["command"]))
            self.assertIn(
                "beam_candidate_attribution.json",
                manifest["artifacts"]["beam_candidate_attribution_json"])
            self.assertEqual(
                steps["beam-frame-label-index"]["status"], "skipped")
            self.assertEqual(steps["beam-span-closure"]["status"], "skipped")
            self.assertEqual(
                manifest["artifacts"]["beam_frame_label_index_json"], "")

    def test_pipeline_runs_frame_index_and_span_closure_with_whole_sheet_dxf(self):
        def fake_run(name, script, arguments, **_kwargs):
            output = Path(arguments[arguments.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_suffix(".json").write_text(
                json.dumps({"summary": {}}), encoding="utf-8")
            return {"name": name, "status": "ok",
                    "command": [script, *arguments],
                    "elapsed_seconds": 0.0, "attempts": []}

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            recon = root / "recon.json"
            whole = root / "whole_sheet.dxf"
            dwg.write_bytes(b"DXF")
            whole.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            recon.write_text(json.dumps({
                "schema": "cad-beam-reference-reconciliation/v0.1",
                "beam_code_reconciliation": []}), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py", "--dwg", str(dwg),
                "--scan", str(scan), "--floor-label", "二层梁平法施工图",
                "--out", str(out),
                "--beam-gap-reconciliation-json", str(recon),
                "--frame-index-dxf", str(whole),
                "--multispan-geometry-dxf", str(whole),
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake_run):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(encoding="utf-8"))
            steps = {row["name"]: row for row in manifest["steps"]}
            self.assertEqual(steps["beam-frame-label-index"]["status"], "ok")
            index_command = steps["beam-frame-label-index"]["command"]
            self.assertEqual(index_command[0], "cad_beam_frame_label_index.py")
            self.assertEqual(
                index_command[index_command.index("--target-frame") + 1],
                "二层梁平法施工图")
            self.assertEqual(steps["beam-span-closure"]["status"], "ok")
            closure_command = steps["beam-span-closure"]["command"]
            self.assertEqual(closure_command[0], "cad_beam_span_closure.py")
            self.assertIn("--frame-index-json", closure_command)
            self.assertIn("--intersection-json", closure_command)
            report_command = steps["quantity-report"]["command"]
            self.assertTrue(any(item.startswith("梁图框索引=")
                                for item in report_command))
            self.assertTrue(any(item.startswith("梁净跨口径=")
                                for item in report_command))
            self.assertEqual(steps["beam-multispan-closure"]["status"], "ok")
            multispan_command = steps["beam-multispan-closure"]["command"]
            self.assertEqual(multispan_command[0],
                             "cad_beam_multispan_closure.py")
            self.assertIn("--geometry-dxf", multispan_command)
            self.assertTrue(any(item.startswith("多跨梁续接=")
                                for item in report_command))
            self.assertIn("beam_frame_label_index.json",
                          manifest["artifacts"]["beam_frame_label_index_json"])
            self.assertIn("beam_span_closure.json",
                          manifest["artifacts"]["beam_span_closure_json"])
            self.assertIn("beam_multispan_closure.json",
                          manifest["artifacts"]["beam_multispan_closure_json"])

    def test_pipeline_skips_beam_coverage_when_switch_given(self):
        def fake_run(name, script, arguments, **_kwargs):
            output = Path(arguments[arguments.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            payload = ({"quantities": {}, "formal_ready": False}
                       if name in ("concrete-ledger", "structure-model")
                       else {"direct_outputs": {}}
                       if name == "quantity-report" else {})
            output.with_suffix(".json").write_text(
                json.dumps(payload), encoding="utf-8")
            if name.endswith("geometry"):
                output.with_suffix(".dxf").write_text("DXF", encoding="utf-8")
            return {
                "name": name, "status": "ok",
                "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": [],
            }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            dwg.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            out = root / "out"
            argv = [
                "cad_quantity_pipeline.py",
                "--dwg", str(dwg),
                "--scan", str(scan),
                "--floor-label", "二层梁平法施工图",
                "--out", str(out),
                "--no-beam-coverage-audit",
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake_run):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (out / "pipeline_manifest.json").read_text(encoding="utf-8"))
            steps = {row["name"]: row for row in manifest["steps"]}
            self.assertEqual(steps["beam-coverage-audit"]["status"], "skipped")
            self.assertFalse(any(
                item.startswith("梁覆盖=")
                for item in steps["quantity-report"]["command"]))
            self.assertEqual(manifest["artifacts"]["beam_coverage_json"], "")


class MemberIntersectionTests(unittest.TestCase):
    def test_build_audit_reports_overlap_without_applying_deduction(self):
        model = {
            "floor": {"label": "测试层"},
            "run_registry": {"runs": [{
                "id": "R1", "matched_code": "KL1", "orientation": "H",
                "axis_mm": 100.0, "start_mm": 0.0, "end_mm": 2000.0,
                "section_b_mm": 200.0, "section_h_mm": 500.0,
            }]},
            "members": {
                "columns": [{
                    "label": "KZ1", "x0": 900.0, "x1": 1100.0,
                    "y0": 0.0, "y1": 200.0,
                }],
                "edge_members": [], "walls": [],
            },
        }
        result = intersection.build_audit(
            model, {}, {"quantities": {"candidate_total_volume_m3": 10.0}},
            3870.0, 500.0, 0.0001)
        group = result["summary"]["groups"]["beam-vertical"]
        self.assertEqual(group["overlap_count"], 1)
        self.assertEqual(group["overlap_area_m2"], 0.04)
        self.assertEqual(group["potential_deduction_volume_m3"], 0.02)
        self.assertFalse(result["closure"]["applied_to_formal_quantity"])
        self.assertIn("重叠", result["status"])
        net = result["net_quantity"]
        self.assertEqual(net["applied_deduction_m3"], 0.02)
        self.assertEqual(net["gross_by_kind"]["beam"], 0.2)
        self.assertEqual(net["net_by_kind"]["beam"], 0.18)
        self.assertFalse(net["applied_to_formal_quantity"])

    def test_multiple_overlaps_at_same_cell_are_deduplicated(self):
        bbox = [900.0, 0.0, 1100.0, 200.0]
        model = {
            "floor": {"label": "测试层"},
            "run_registry": {"runs": [{
                "id": "R1", "matched_code": "KL1", "orientation": "H",
                "axis_mm": 100.0, "start_mm": 0.0, "end_mm": 2000.0,
                "section_b_mm": 200.0, "section_h_mm": 500.0,
            }]},
            "members": {
                "columns": [],
                "edge_members": [{
                    "label": "YBZ1", "bbox": bbox,
                }],
                "walls": [{
                    "orientation": "V", "center": 1000.0,
                    "start": 0.0, "end": 200.0, "width_mm": 200.0,
                }],
            },
        }
        result = intersection.build_audit(
            model, {}, {"quantities": {"candidate_total_volume_m3": 10.0}},
            3870.0, 500.0, 0.0001)
        group = result["summary"]["groups"]["beam-vertical"]
        self.assertEqual(group["overlap_count"], 2)
        self.assertEqual(group["unique_overlap_cell_count"], 1)
        self.assertEqual(group["potential_deduction_volume_m3"], 0.02)
        self.assertEqual(group["pairwise_potential_deduction_volume_m3"], 0.04)
        self.assertEqual(group["deduplication_overcount_m3"], 0.02)

    def test_intersection_audit_enters_unified_report_dashboard(self):
        supplement = {
            "schema": "cad-member-intersection-audit/v0.3",
            "formal_ready": False,
            "status": "构件矩形重叠审计",
            "summary": {
                "overlap_count": 2,
                "overlap_area_m2": 0.06,
                "potential_deduction_volume_m3": 0.03,
                "beam_side_deduction_candidate_m3": 0.02,
                "groups": {
                    "beam-vertical": {
                        "overlap_count": 1,
                        "overlap_area_m2": 0.04,
                        "potential_deduction_volume_m3": 0.02,
                        "top_codes": [{"code": "KZ1", "volume_m3": 0.02}],
                    },
                    "beam-beam": {
                        "overlap_count": 1,
                        "overlap_area_m2": 0.02,
                        "potential_deduction_volume_m3": 0.01,
                        "top_codes": [{"code": "KL1", "volume_m3": 0.01}],
                    },
                },
            },
            "overlaps": [{
                "pair_type": "beam-vertical",
                "member_ids": ["R1", "C1"],
                "codes": ["KL1", "KZ1"],
                "overlap_bbox_mm": [900.0, 0.0, 1100.0, 200.0],
                "overlap_area_m2": 0.04,
                "deduction_height_mm": 500.0,
                "potential_deduction_volume_m3": 0.02,
                "suggested_owner": "vertical",
                "confidence": "potential",
            }],
            "closure": {
                "applied_to_formal_quantity": False,
                "reason": "节点归属未确认",
                "next_gate": "确认归属",
            },
            "net_quantity": {
                "applied_deduction_m3": 0.03,
                "candidate_total_after_beam_deduction_m3": 273.2136,
                "top_affected_members": {
                    "beam": [{
                        "id": "R1", "code": "KL1", "gross_volume_m3": 0.5,
                        "intersection_deduction_m3": 0.03,
                        "net_volume_m3": 0.47,
                    }],
                },
                "unresolved_vertical_overlap_area_m2": 0.01,
                "unresolved_vertical_overlap_volume_m3": 0.02,
            },
        }
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"构件相交": supplement})
        direct = result["direct_outputs"]
        self.assertEqual(direct["intersection_overlap_count"], 2)
        self.assertEqual(direct["intersection_potential_deduction_volume_m3"], 0.03)
        self.assertEqual(direct["intersection_applied_net_deduction_m3"], 0.03)
        self.assertEqual(
            direct["intersection_candidate_net_total_m3"], 273.2136)
        self.assertEqual(
            result["concrete"]["quantities"]["candidate_total_volume_m3"],
            direct["concrete_candidate_total_m3"],
        )
        dashboard = result["closure_dashboard"]
        self.assertTrue(any(
            row.get("id") == "member-intersection-deduction"
            and row.get("status") == "warn"
            for row in dashboard["gates"]))
        self.assertTrue(any(
            row.get("component") == "构件相交重复计量"
            and row.get("remaining_count") == 2
            for row in dashboard["component_gaps"]))
        markdown = report.render_markdown(result)
        self.assertIn("构件相交重复计量", markdown)
        self.assertIn("构件相交潜在重复量m3", markdown)
        self.assertIn("候选构件净量", markdown)
        self.assertIn("规则试算总量m3", markdown)


class SlabOpeningAuditTest(unittest.TestCase):
    """板图层洞口证据审计与报告集成。"""

    @staticmethod
    def _model():
        return {
            "schema": "cad-slab-attribute-audit/v0.1",
            "slab_transform": [0.0, 0.0],
            "members": {"slab_panels": [
                {"id": "P0001", "bbox": [0.0, 0.0, 1000.0, 1500.0],
                 "area_m2": 1.5, "thickness_mm": 130,
                 "opening_status": "confirmed-opening",
                 "opening_area_m2": 1.5},
                {"id": "P0002", "bbox": [3000.0, 0.0, 4900.0, 1900.0],
                 "area_m2": 3.61, "thickness_mm": 130,
                 "opening_status": "opening-candidate",
                 "opening_evidence": [{"handle": "A1"}, {"handle": "A2"}]},
                {"id": "P0003", "bbox": [6000.0, 0.0, 9000.0, 2000.0],
                 "area_m2": 6.0, "thickness_mm": 120,
                 "opening_status": "opening-candidate",
                 "opening_evidence": [{"handle": "B1"}, {"handle": "B2"}]},
            ]},
        }

    @staticmethod
    def _entities():
        return [
            {"handle": "X1", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[0.0, 0.0], [1000.0, 1500.0]]},
            {"handle": "X2", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[0.0, 1500.0], [1000.0, 0.0]]},
            {"handle": "A1", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[3000.0, 0.0], [3300.0, 1500.0]]},
            {"handle": "A2", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[3300.0, 1500.0], [4900.0, 1900.0]]},
            {"handle": "B1", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[6000.0, 0.0], [6100.0, 400.0]]},
            {"handle": "B2", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[6100.0, 400.0], [8800.0, 600.0]]},
            {"handle": "C1", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[20000.0, 20000.0], [21000.0, 21000.0]]},
            {"handle": "E1", "layer": "S-板-板边线", "kind": "LINE",
             "points": [[0.0, 0.0], [9000.0, 0.0]]},
            {"handle": "E2", "layer": "S-板-板边线", "kind": "LINE",
             "points": [[0.0, 0.0], [0.0, 2000.0]]},
        ]

    def test_classifies_confirmed_openings_and_leaders(self):
        result = slab_opening.build_audit(
            self._entities(), self._model(), {}, (0.0, 0.0),
            {"closure_search_margin_mm": 1500.0},
            ("S-板-板边线",), probe_closure=True)
        summary = result["summary"]
        self.assertEqual(summary["source_entity_count"], 7)
        self.assertEqual(summary["confirmed_opening_count"], 1)
        self.assertEqual(summary["confirmed_opening_area_m2"], 1.5)
        self.assertEqual(summary["net_panel_area_m2"], 9.61)
        self.assertTrue(summary["entity_ledger_closed"])
        self.assertFalse(summary["openings_closed"])
        statuses = {
            "+".join(row["handles"]): row["status"]
            for row in result["records"]}
        self.assertEqual(statuses["X1+X2"], "rectangle-x")
        self.assertEqual(statuses["B1+B2"], "annotation-leader")
        self.assertEqual(statuses["A1+A2"], "panel-diagonal-chain")
        self.assertEqual(statuses["C1"], "out-of-frame")
        self.assertEqual(
            summary["review_handles"], ["A1", "A2"])
        self.assertEqual(summary["prior_candidate_panel_count"], 2)
        self.assertEqual(summary["prior_candidate_explained_panel_count"], 1)
        self.assertFalse(result["formal_ready"])
        self.assertFalse(result["applied_to_formal_quantity"])
        for row in result["records"]:
            if row["status"] != "rectangle-x":
                self.assertEqual(row["deduct_area_m2"], 0.0)

    def test_closed_polyline_counts_and_gap_consistency_flags_overdraft(self):
        entities = [
            {"handle": "L1", "layer": "S-板-开洞", "kind": "LWPOLYLINE",
             "closed": True,
             "points": [[0.0, 0.0], [1000.0, 0.0], [1000.0, 1500.0],
                        [0.0, 1500.0]]},
            {"handle": "A1", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[3000.0, 0.0], [3300.0, 1500.0]]},
            {"handle": "A2", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[3300.0, 1500.0], [4900.0, 1900.0]]},
            {"handle": "B1", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[6000.0, 0.0], [6100.0, 400.0]]},
            {"handle": "B2", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[6100.0, 400.0], [8800.0, 600.0]]},
        ]
        result = slab_opening.build_audit(
            entities, self._model(), {}, (0.0, 0.0),
            {"reference_gap_m3": 0.05}, ("S-板-板边线",),
            probe_closure=False)
        summary = result["summary"]
        self.assertEqual(summary["confirmed_opening_count"], 1)
        self.assertEqual(
            [row["status"] for row in result["confirmed_openings"]],
            ["closed-polyline"])
        self.assertFalse(summary["gap_consistency"]["all_residual_are_openings"])
        self.assertIn("超出当前量差", summary["gap_consistency"]["note"])
        self.assertTrue(slab_opening.render_markdown(result))

    def test_empty_opening_layer_does_not_claim_closure(self):
        result = slab_opening.build_audit(
            [{"handle": "E1", "layer": "S-板-板边线", "kind": "LINE",
              "points": [[0.0, 0.0], [1000.0, 0.0]]}],
            self._model(), {}, (0.0, 0.0), {}, (), probe_closure=False)
        self.assertEqual(result["summary"]["source_entity_count"], 0)
        self.assertFalse(result["summary"]["entity_ledger_closed"])
        self.assertFalse(result["summary"]["openings_closed"])

    def test_report_surfaces_slab_opening_gate_and_direct_outputs(self):
        audit = slab_opening.build_audit(
            self._entities(), self._model(), {}, (0.0, 0.0),
            {"closure_search_margin_mm": 1500.0},
            ("S-板-板边线",), probe_closure=True)
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"板洞口": audit})
        direct = result["direct_outputs"]
        self.assertEqual(direct["slab_opening_entity_count"], 7)
        self.assertEqual(direct["slab_opening_confirmed_count"], 1)
        self.assertEqual(direct["slab_opening_confirmed_area_m2"], 1.5)
        self.assertEqual(direct["slab_opening_net_area_m2"], 9.61)
        self.assertEqual(direct["slab_opening_review_count"], 1)
        self.assertFalse(direct["slab_openings_closed"])
        self.assertTrue(any(
            row.get("id") == "slab-opening-evidence"
            and row.get("status") == "warn"
            for row in result["closure_dashboard"]["gates"]))
        self.assertTrue(any(
            row.get("component") == "板洞口证据"
            for row in result["closure_dashboard"]["component_gaps"]))
        markdown = report.render_markdown(result)
        self.assertIn("板洞口证据审计", markdown)
        self.assertIn("待复核体积上限m3", markdown)
        self.assertEqual(
            direct["concrete_candidate_total_m3"],
            result["concrete"]["quantities"]["candidate_total_volume_m3"])
        csv_text = report.csv_rows(result)
        self.assertTrue(any(
            row[0] == "板洞口台账" for row in csv_text))


    def test_attributed_deduction_uses_matched_panel_not_overlap_sum(self):
        entities = self._entities() + [
            {"handle": "D1", "layer": "S-板-开洞", "kind": "LINE",
             "points": [[3000.0, 0.0], [8800.0, 2000.0]]},
        ]
        result = slab_opening.build_audit(
            entities, self._model(), {}, (0.0, 0.0),
            {"closure_search_margin_mm": 1500.0,
             "reference_gap_m3": 0.5},
            ("S-板-板边线",), probe_closure=False)
        row = next(r for r in result["records"] if "D1" in r["handles"])
        self.assertIn(row["status"], ("standalone-line", "open-chain"))
        self.assertTrue(row["review_required"])
        self.assertLess(row["potential_volume_attributed_m3"],
                        row["potential_volume_upper_bound_m3"])
        self.assertAlmostEqual(
            row["potential_volume_attributed_m3"],
            round(min(row["envelope_area_m2"], row["panel_area_m2"])
                  * row["panel_thickness_mm"] / 1000.0, 4), places=4)
        summary = result["summary"]
        self.assertLessEqual(summary["review_volume_attributed_m3"],
                             summary["review_volume_upper_bound_m3"])
        self.assertIn("review_volume_attributed_m3",
                      summary["gap_consistency"])


class BeamGapAttributionTest(unittest.TestCase):
    """梁编号体积缺口归因与报告集成。"""

    @staticmethod
    def _reconciliation():
        return {
            "schema": "cad-beam-reference-reconciliation/v0.1",
            "floor_mapping": {"reference_floor": "首层"},
            "reference_decomposition_rule": {
                "instance_count_formula": "累计宽×累计高÷截面面积"},
            "beam_code_reconciliation": [
                {
                    "code": "KL1(1)", "base_code": "KL1",
                    "reference_single_section": "200x500",
                    "reference_single_axis_length_mm": 6500,
                    "reference_single_net_length_mm": 6200,
                    "reference_instance_count": 4,
                    "reference_volume_m3": 1.8352,
                    "current_code_volume_m3": 1.83,
                    "missing_equivalent_instance_count": 1,
                    "selected_equivalent_instance_count": 3,
                    "cad_run_count": 3, "cad_chain_count": 3,
                    "status": "missing-repeat-or-truncated-geometry",
                    "selected_chains": [{"id": "C1", "run_ids": ["R1"]}],
                    "rejected_chains": [],
                },
                {
                    "code": "WKL4(1)", "base_code": "WKL4",
                    "reference_single_section": "200x500",
                    "reference_single_axis_length_mm": 6600,
                    "reference_single_net_length_mm": 6400,
                    "reference_instance_count": 4,
                    "reference_volume_m3": 1.8023,
                    "current_code_volume_m3": 0.845,
                    "missing_equivalent_instance_count": 3,
                    "selected_equivalent_instance_count": 1,
                    "cad_run_count": 1, "cad_chain_count": 1,
                    "status": "missing-repeat-or-truncated-geometry",
                    "selected_chains": [{"id": "C2", "run_ids": ["R2"]}],
                    "rejected_chains": [],
                },
                {
                    "code": "KL2(1)", "base_code": "KL2",
                    "reference_single_section": "200x400",
                    "reference_single_axis_length_mm": 1200,
                    "reference_single_net_length_mm": 1000,
                    "reference_instance_count": 4,
                    "reference_volume_m3": 0.6364,
                    "current_code_volume_m3": 1.69,
                    "missing_equivalent_instance_count": 0,
                    "selected_equivalent_instance_count": 4,
                    "cad_run_count": 2, "cad_chain_count": 2,
                    "status": "instance-count-matched-length-under",
                    "selected_chains": [{"id": "C3", "run_ids": ["R3"]}],
                    "rejected_chains": [],
                },
            ],
            "concrete_ledger": {
                "main_beam_cad_m3": 4.365,
                "coupling_beam_m3": 3.6591,
                "stair_beam_cad_m3": 2.2864,
                "stair_beam_reference_m3": 2.3078,
                "lb_reference_m3": 0.543,
                "tl2_reference_m3": 0.4118,
                "located_beam_total_m3": 11.2653,
                "beam_reference_m3": 12.3279,
                "beam_remaining_m3": 1.0626,
            },
        }

    @staticmethod
    def _model():
        return {
            "floor": {"label": "二层梁平法施工图"},
            "run_registry": {"runs": [
                {"id": "R1", "section": "200x500", "length_mm": 6100,
                 "volume_m3": 0.61, "orientation": "V", "axis_mm": 1.0},
                {"id": "R2", "section": "200x500", "length_mm": 8450,
                 "volume_m3": 0.845, "orientation": "V", "axis_mm": 2.0},
                {"id": "R3", "section": "200x400", "length_mm": 8450,
                 "volume_m3": 0.676, "orientation": "H", "axis_mm": 3.0},
                {"id": "R9", "section": "200x500", "length_mm": 9000,
                 "volume_m3": 0.9, "orientation": "H", "axis_mm": 4.0},
            ]},
        }

    def test_splits_real_gap_from_count_artifact(self):
        result = beam_gap.build_attribution(
            self._reconciliation(), self._model())
        summary = result["summary"]
        by_code = {row["code"]: row for row in result["code_attribution"]}
        self.assertEqual(by_code["KL1(1)"]["classification"], "volume-matched")
        self.assertEqual(by_code["KL1(1)"]["count_only_missing_instance_count"], 1)
        self.assertEqual(by_code["WKL4(1)"]["classification"], "volume-under")
        self.assertEqual(by_code["KL2(1)"]["classification"], "volume-over")
        self.assertEqual(summary["unassigned_run_count"], 1)
        self.assertEqual(summary["unassigned_run_volume_m3"], 0.9)
        self.assertEqual(
            summary["count_only_missing_instance_count"]
            + summary["volume_explained_missing_instance_count"],
            summary["missing_instance_count"])
        self.assertTrue(summary["gap_decomposition"]["matches_ledger"])
        self.assertTrue(result["closure"]["reconciled"])
        self.assertFalse(result["formal_ready"])
        self.assertFalse(result["applied_to_formal_quantity"])
        target = next(
            row for row in result["search_targets"] if row["code"] == "WKL4(1)")
        self.assertEqual(target["unassigned_candidate_count"], 1)
        self.assertGreater(target["needed_length_mm"], 9000)
        self.assertIn("同截面未归属图线",
                      by_code["WKL4(1)"]["action"])

    def test_unassigned_pool_cannot_be_double_counted_as_gap_free(self):
        reconciliation = self._reconciliation()
        reconciliation["concrete_ledger"]["main_beam_cad_m3"] = 25.7983
        result = beam_gap.build_attribution(reconciliation, self._model())
        summary = result["summary"]
        self.assertEqual(summary["residual_needing_new_geometry_m3"], 0.0)
        self.assertGreater(
            summary["unassigned_run_volume_m3"],
            summary["main_beam_net_unlocated_m3"])
        self.assertFalse(summary["gap_decomposition"]["matches_ledger"])
        self.assertFalse(result["closure"]["reconciled"])
        markdown = beam_gap.render_markdown(result)
        self.assertIn("梁编号体积缺口归因", markdown)
        self.assertIn("未对上", markdown)
        self.assertTrue(beam_gap.csv_rows(result))

    def test_report_surfaces_beam_gap_gate_and_targets(self):
        audit = beam_gap.build_attribution(
            self._reconciliation(), self._model(), {
                "endpoint_classification": {
                    "total": 20,
                    "counts": {"free-end-candidate": 10,
                               "near-support-pending": 4}},
                "gates": {"beam_support_confirmation": "fail"}})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"梁量差": audit})
        direct = result["direct_outputs"]
        self.assertEqual(direct["beam_code_count"], 3)
        self.assertEqual(direct["beam_volume_under_code_count"], 1)
        self.assertEqual(direct["beam_count_only_instance_gap"], 3)
        self.assertTrue(direct["beam_gap_decomposition_matches_ledger"])
        self.assertGreater(direct["beam_net_unlocated_m3"], 0.0)
        self.assertTrue(any(
            row.get("id") == "beam-volume-gap-attribution"
            and row.get("status") == "warn"
            for row in result["closure_dashboard"]["gates"]))
        self.assertTrue(any(
            row.get("component") == "梁体积缺口"
            for row in result["closure_dashboard"]["component_gaps"]))
        markdown = report.render_markdown(result)
        self.assertIn("梁体积缺口归因", markdown)
        self.assertIn("梁真实需补新几何m3", markdown)
        self.assertTrue(any(
            row[0] == "梁检索目标" for row in report.csv_rows(result)))


class BeamCoverageAuditTest(unittest.TestCase):
    """梁图层覆盖审计：区间覆盖、视图归属分桶与报告集成。"""

    @staticmethod
    def _line(handle, layer, x1, y1, x2, y2):
        return {"handle": handle, "layer": layer,
                "points": [[x1, y1], [x2, y2]]}

    @staticmethod
    def _model():
        return {
            "floor": {"label": "二层梁平法施工图"},
            "members": {"slab_panels": [
                {"id": "P1", "bbox": [-20000.0, -20000.0, 20000.0, 20000.0]}]},
            "run_registry": {
                "bbox": [-20000.0, -20000.0, 20000.0, 20000.0],
                "runs": [
                    {"id": "R1", "orientation": "H", "axis_mm": 0.0,
                     "start_mm": -10000.0, "end_mm": 10000.0,
                     "paired_width_mm": 200.0, "section_h_mm": 500.0},
                ],
            },
        }

    @classmethod
    def _entities(cls):
        return [
            cls._line("A", "S-梁-虚线", -10000, 100, 10000, 100),
            cls._line("B", "S-梁-虚线", -10000, -100, 10000, -100),
            cls._line("C", "S-梁-虚线", 1000, 2000, 5000, 2200 - 200),
            cls._line("D", "S-梁-虚线", 1000, 2200, 5000, 2200),
            cls._line("E", "S-梁-虚线", 25000, 100, 35000, 100),
            cls._line("F", "S-梁-虚线", 40000, 30000, 45000, 30000),
            cls._line("G", "S-梁-虚线", 40000, 30200, 45000, 30200),
            cls._line("H", "S-剪力墙-连梁", -10000, 9000, 10000, 9000),
        ]

    def test_splits_missing_candidate_duplicate_view_and_other_view(self):
        result = beam_coverage.build_audit(
            self._entities(), self._model(), {})
        summary = result["summary"]
        self.assertFalse(summary["coverage_closed"])
        self.assertAlmostEqual(summary["in_frame_coverage_ratio"], 0.833333, places=5)
        self.assertEqual(summary["candidate_beam_in_frame_count"], 1)
        self.assertEqual(summary["candidate_volume_in_frame_m3"], 0.4)
        self.assertEqual(summary["duplicate_view_line_count"], 1)
        # 覆盖相同的多个候选偏移取位移最小者，保证重复视图按最近对齐归位。
        self.assertEqual(summary["duplicate_view_offset_mm"], -25000.0)
        # 窗口外图线只作视图归属证据，不得计入本层漏量。
        self.assertEqual(summary["mirrored_line_count"], 0)
        self.assertEqual(summary["candidate_volume_mirror_pair_m3"], 0.0)
        self.assertEqual(summary["candidate_volume_window_out_m3"], 0.0)
        self.assertEqual(summary["candidate_beam_beyond_plan_count"], 1)
        self.assertEqual(summary["candidate_volume_beyond_plan_m3"], 0.5)
        self.assertEqual(summary["coupling_uncovered_count"], 1)
        self.assertFalse(result["formal_ready"])
        self.assertFalse(result["applied_to_formal_quantity"])
        in_frame = next(
            row for row in result["candidates"]
            if row["view_zone"] == "inside-extraction-window")
        self.assertEqual(in_frame["handles"], ["C", "D"])
        self.assertEqual(in_frame["width_mm"], 200.0)
        beyond = next(
            row for row in result["candidates"]
            if row["view_zone"] == "beyond-plan-envelope")
        self.assertIn("相邻视图", beyond["evidence"])

    def test_mirror_axis_offset_is_detected_on_folded_line(self):
        faces = {"H": [("R1", 100.0, -10000.0, 10000.0)], "V": []}
        stub = {"orientation": "H", "start": (25000.0, 100.0),
                "end": (45000.0, 100.0), "length_mm": 20000.0,
                "handle": "M", "layer": "S-梁-虚线"}
        # 轴 17500 把 25000~45000 折到 -10000~10000，正好落在已提取边线上。
        self.assertEqual(
            beam_coverage._mirrored_pair_offset(stub, faces, [17500.0], 60.0),
            17500.0)
        self.assertIsNone(
            beam_coverage._mirrored_pair_offset(stub, faces, [7000.0], 60.0))

    def test_partial_covered_line_counts_by_length_not_whole_line(self):
        entities = self._entities() + [
            self._line("I", "S-梁-虚线", -10000, 5000, 20000, 5000),
            self._line("J", "S-梁-虚线", -10000, 5200, 20000, 5200),
        ]
        # 给 I/J 造一条只覆盖左半的同轴实例边线
        model = self._model()
        model["run_registry"]["runs"].append({
            "id": "R2", "orientation": "H", "axis_mm": 5100.0,
            "start_mm": -10000.0, "end_mm": 4900.0,
            "paired_width_mm": 200.0, "section_h_mm": 500.0})
        result = beam_coverage.build_audit(entities, model, {})
        summary = result["summary"]
        # I/J 各被吃到左半段，只剩右半段未覆盖，必须按实长计而不是整条判覆盖
        self.assertEqual(summary["partial_covered_segment_count"], 2)
        self.assertEqual(summary["uncovered_in_frame_count"], 4)
        self.assertAlmostEqual(
            summary["uncovered_in_frame_length_mm"], 15040.0 * 2 + 4000.0 * 2, 1)

    def test_residual_gap_compares_only_against_window_candidates(self):
        result = beam_coverage.build_audit(
            self._entities(), self._model(),
            {"residual_gap_m3": 1.0, "unexplained_tolerance_m3": 0.05})
        summary = result["summary"]
        self.assertEqual(summary["residual_covered_by_candidates_m3"], 0.4)
        self.assertEqual(summary["residual_still_unexplained_m3"], 0.6)
        self.assertFalse(summary["residual_within_tolerance"])

    def test_mirror_pair_volume_beyond_gap_is_not_countable(self):
        # 镜像对称体量与缺口同量级才可能算漏量，成倍超出只能是对称视图副本。
        self.assertFalse(
            beam_coverage._mirror_pair_countable(8.9108, 1.0413, 0.05))
        self.assertTrue(
            beam_coverage._mirror_pair_countable(0.6000, 1.0413, 0.05))
        self.assertTrue(
            beam_coverage._mirror_pair_countable(1.0800, 1.0413, 0.05))
        self.assertFalse(beam_coverage._mirror_pair_countable(0.5, -1.0, 0.05))

    def test_report_surfaces_beam_coverage_gate_and_direct_outputs(self):
        audit = beam_coverage.build_audit(
            self._entities(), self._model(), {"residual_gap_m3": 1.0413})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"梁覆盖": audit})
        direct = result["direct_outputs"]
        self.assertEqual(direct["beam_candidate_in_frame_count"], 1)
        self.assertEqual(direct["beam_candidate_in_frame_volume_m3"], 0.4)
        self.assertEqual(direct["beam_duplicate_view_offset_mm"], -25000.0)
        self.assertEqual(direct["beam_mirrored_view_count"], 0)
        self.assertEqual(direct["beam_mirror_pair_volume_m3"], 0.0)
        self.assertTrue(direct["beam_mirror_pair_countable"])
        self.assertEqual(direct["beam_residual_still_unexplained_m3"], 0.6413)
        self.assertFalse(direct["beam_coverage_closed"])
        self.assertTrue(any(
            row.get("id") == "beam-coverage-audit" and row.get("status") == "warn"
            for row in result["closure_dashboard"]["gates"]))
        self.assertTrue(any(
            row.get("component") == "梁图层覆盖"
            for row in result["closure_dashboard"]["component_gaps"]))
        markdown = report.render_markdown(result)
        self.assertIn("梁图层覆盖审计", markdown)
        self.assertIn("inside-extraction-window", markdown)
        self.assertTrue(any(
            row[0] == "梁覆盖候选" for row in report.csv_rows(result)))

    def test_report_surfaces_beam_candidate_attribution_gate(self):
        run = {
            "id": "R0031", "orientation": "H", "axis_mm": 771140.5,
            "start_mm": -1412824.5, "end_mm": -1411574.5, "length_mm": 1250.0,
            "paired_width_mm": 200.0, "section_b_mm": 200.0,
            "section_h_mm": 500.0, "section": "200x500",
            "volume_m3": 0.125, "matched_code": "KL13A(1)",
            "code_assignment_status": "mirror-label", "confidence": "medium",
        }
        model = {"run_registry": {"runs": [run], "mirror_axes": []}}
        coverage = {
            "schema": "cad-beam-coverage-audit/v0.1",
            "floor": "二层梁平法施工图",
            "summary": {"residual_gap_m3": 1.0413,
                        "residual_still_unexplained_m3": 0.4344,
                        "candidate_volume_mirror_pair_m3": 0.0,
                        "candidate_volume_translated_view_m3": 0.0},
            "candidates": [{
                "status": "uncovered-beam-candidate",
                "handles": ["271", "272"], "orientation": "H",
                "axis_mm": 771140.5, "start_mm": -1411374.5,
                "end_mm": -1409474.5, "width_mm": 200.0, "length_mm": 1900.0,
                "assumed_height_mm": 510.0, "volume_m3": 0.1938,
                "view_zone": "inside-extraction-window"}],
        }
        reconciliation = {"beam_code_reconciliation": [{
            "code": "KL13a(1)", "reference_single_section": "200x500",
            "selected_chains": [{"id": "CH0001", "span_mm": 1250.0,
                                 "run_ids": ["R0031"]}],
            "current_code_volume_m3": 0.125,
            "current_code_difference_m3": 0.0644}]}
        gap = {"code_attribution": [{
            "code": "KL11(1)", "reference_section": "200x500",
            "difference_m3": -0.3112, "needed_length_mm": 2510.0,
            "missing_instance_count": 1, "unassigned_candidate_count": 0}]}
        audit = beam_attribution.build_attribution(
            model, coverage, reconciliation, gap,
            {"floor_label": "首层"})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"梁候选归属": audit})
        direct = result["direct_outputs"]
        self.assertEqual(direct["beam_section_caliber_delta_m3"], 0.0)
        self.assertEqual(direct["beam_section_mismatch_run_count"], 0)
        self.assertEqual(direct["beam_candidate_attached_m3"], 0.19)
        self.assertEqual(direct["beam_candidate_unattached_m3"], 0.0)
        self.assertEqual(direct["beam_unexplained_in_frame_m3"], 0.8513)
        self.assertTrue(direct["beam_decomposition_identity_closed"])
        self.assertEqual(direct["beam_cross_frame_code_count"], 1)
        self.assertEqual(direct["beam_cross_frame_needed_length_mm"], 2510.0)
        self.assertTrue(any(
            row.get("id") == "beam-candidate-attribution"
            and row.get("status") == "warn"
            for row in result["closure_dashboard"]["gates"]))
        self.assertTrue(any(
            row.get("component") == "梁候选段归属"
            for row in result["closure_dashboard"]["component_gaps"]))
        markdown = report.render_markdown(result)
        self.assertIn("梁候选段归属与截面口径复核", markdown)
        self.assertIn("KL13A(1)", markdown)
        self.assertTrue(any(
            row[0] == "梁候选段" for row in report.csv_rows(result)))
        self.assertTrue(any(
            row[0] == "梁跨图框目标" for row in report.csv_rows(result)))
        beams = [{"id": "B0003", "code": "KL10(1)", "section": "200x500",
                  "section_b_mm": 200.0, "section_h_mm": 500.0,
                  "centerline_length_mm": 5200.0, "clear_length_mm": 4200.0,
                  "gross_volume_m3": 0.52, "clear_volume_m3": 0.42,
                  "support_count": 2, "expected_support_count": 2,
                  "endpoint_polygon_support_count": 2,
                  "beam_intersection_support_count": 0,
                  "support_evidence": [{"type": "wall-column"}],
                  "inferred_end_supports": [],
                  "support_selection": {"rejected_cluster_count": 0},
                  "quantity_status": "clear-span-review",
                  "centerline": {"start": [-1440114.5, 766500.0],
                                 "end": [-1434914.5, 766500.0],
                                 "length_basis": "axis-chain"}}]
        titles = [{"text": "一层梁平法施工图", "layer": "S-图名", "kind": "TEXT",
                   "x": -1426000.0, "y": 672000.0},
                  {"text": "二层梁平法施工图", "layer": "S-图名", "kind": "TEXT",
                   "x": -1426000.0, "y": 746000.0}]
        labels = [{"text": "KL10(1) 200x500", "layer": "S-梁-配筋-集中标注",
                   "kind": "TEXT", "x": -1437000.0, "y": 767000.0,
                   "code": "KL10(1)"}]
        index = frame_index.build_index(
            labels, titles, {"beam_code_reconciliation": [{
                "code": "KL10(1)", "reference_instance_count": 2,
                "selected_equivalent_instance_count": 1,
                "reference_single_axis_length_mm": 5600.0,
                "cad_selected_span_mm": 5200.0,
                "current_code_difference_m3": -0.2362}]},
            {"target_frame": "二层梁平法施工图"})
        closure = span_closure.build_closure(
            {"members": {"beams": beams}},
            {"beam_code_reconciliation": [{
                "code": "KL10(1)", "reference_instance_count": 2,
                "selected_equivalent_instance_count": 1,
                "reference_single_axis_length_mm": 5600.0,
                "cad_selected_span_mm": 5200.0,
                "current_code_difference_m3": -0.2362}]},
            index, {"summary": {"beam_side_deduction_candidate_m3": 0.3211}},
            {"deficit_tolerance_mm": 100.0})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"梁图框索引": index, "梁净跨口径": closure})
        direct = result["direct_outputs"]
        self.assertEqual(direct["beam_frame_count"], 2)
        self.assertEqual(direct["beam_target_frame_under_code_count"], 1)
        self.assertEqual(direct["beam_length_not_closed_code_count"], 1)
        self.assertEqual(direct["beam_length_not_closed_volume_m3"], 0.2362)
        self.assertEqual(direct["beam_no_label_in_target_frame_count"], 0)
        self.assertEqual(direct["beam_support_deduction_length_mm"], 1000.0)
        self.assertEqual(direct["beam_span_caliber_difference_m3"], 0.1)
        self.assertEqual(direct["beam_deficit_caliber_volume_m3"], 0.2362)
        self.assertEqual(direct["beam_verdict_total_m3"], 0.2362)
        ids = {row["id"] for row in result["closure_dashboard"]["gates"]}
        self.assertIn("beam-frame-label-index", ids)
        self.assertIn("beam-span-caliber", ids)
        markdown = report.render_markdown(result)
        self.assertIn("梁编号图框标签索引", markdown)
        self.assertIn("梁净跨口径与支座扣减", markdown)
        self.assertIn("deficit-within-support-deduction", markdown)
        sections = {row[0] for row in report.csv_rows(result)}
        self.assertIn("梁图框归属", sections)
        self.assertIn("梁长度定责", sections)
        beams_model = {"floor": "首层", "members": {"beams": [
            {"id": "B0037", "code": "WKL1(2)", "section": "200x510",
             "section_b_mm": 200.0, "section_h_mm": 510.0,
             "centerline_length_mm": 5650.0, "quantity_status": "clear-span-review",
             "centerline": {"start": [-1450914.5, 773940.5],
                            "end": [-1445264.5, 773940.5],
                            "orientation": "H", "length_basis": "local"}}]}}
        buckets = {
            "beam": [
                {"handle": "1AA", "layer": "S-梁-虚线", "orientation": "H",
                 "cross_mm": 773940.5, "lo_mm": -1450914.5,
                 "hi_mm": -1445264.5, "length_mm": 5650.0},
                {"handle": "1AC", "layer": "S-梁-虚线", "orientation": "H",
                 "cross_mm": 773940.5, "lo_mm": -1444764.5,
                 "hi_mm": -1441064.5, "length_mm": 3700.0}],
            "support": [
                {"handle": "260", "layer": "S-柱", "orientation": "H",
                 "cross_mm": 773940.5, "lo_mm": -1445264.5,
                 "hi_mm": -1444764.5, "length_mm": 500.0}]}
        continuation = multispan.build_closure(
            beams_model, buckets,
            {"beam_code_reconciliation": [{
                "code": "WKL1(2)", "reference_single_axis_length_mm": 10350.0,
                "selected_equivalent_instance_count": 1,
                "current_code_difference_m3": -0.8823}]},
            {"axis_tolerance_mm": 400.0, "gap_tolerance_mm": 200.0})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"多跨梁续接": continuation})
        direct = result["direct_outputs"]
        self.assertEqual(direct["beam_multispan_beam_count"], 1)
        self.assertEqual(direct["beam_multispan_continued_count"], 1)
        self.assertEqual(direct["beam_multispan_added_axis_length_mm"], 4200.0)
        self.assertEqual(direct["beam_multispan_candidate_volume_m3"], 0.4284)
        self.assertEqual(direct["beam_multispan_deficit_after_mm"], 500.0)
        self.assertFalse(direct["beam_multispan_applied_to_formal"])
        self.assertTrue(any(
            row["id"] == "beam-multispan-continuation" and row["status"] == "warn"
            for row in result["closure_dashboard"]["gates"]))
        self.assertTrue(any(
            row.get("component") == "多跨梁续接候选"
            for row in result["closure_dashboard"]["component_gaps"]))
        markdown = report.render_markdown(result)
        self.assertIn("多跨梁跨支座续接候选", markdown)
        self.assertIn("#1AC", markdown)
        self.assertIn("多跨梁续接段",
                      {row[0] for row in report.csv_rows(result)})




DEDUP_OPTIONS = {"code_axis_tolerance_mm": 5000.0,
                 "geometry_axis_tolerance_mm": 400.0,
                 "min_overlap_ratio": 0.5, "length_tolerance_mm": 200.0,
                 "gap_tolerance_mm": 400.0,
                 "self_overlap_axis_tolerance_mm": 400.0,
                 "conflict_tolerance_m3": 0.05}


class BeamInstanceDedupReportTest(unittest.TestCase):
    """梁实例双口径去重并入统一报告，且不得改动混凝土量。"""

    @staticmethod
    def _dedup():
        def run(run_id, code, orientation, axis, lo, hi, evidence="leader-target"):
            return {"id": run_id, "matched_code": code, "orientation": orientation,
                    "axis_mm": axis, "start_mm": lo, "end_mm": hi,
                    "length_mm": hi - lo, "section": "200x500",
                    "volume_m3": round((hi - lo) * 0.1, 4),
                    "code_assignment_status": evidence, "confidence": "high"}

        def beam(beam_id, code, orientation, axis, lo, hi):
            start = [lo, axis] if orientation == "H" else [axis, lo]
            end = [hi, axis] if orientation == "H" else [axis, hi]
            return {"id": beam_id, "code": code, "section": "200x500",
                    "gross_volume_m3": round((hi - lo) * 0.1, 4),
                    "quantity_status": "clear-span-review",
                    "centerline": {"start": start, "end": end,
                                   "orientation": orientation}}
        model = {
            "run_registry": {"runs": [
                run("R0001", "KL1(1)", "V", -1448314.5, 760940.5, 767040.5),
                run("R0002", "KL11(1)", "H", 768440.5, -1438964.5, -1435664.5),
                run("R0003", "KL9(1)", "H", 759040.5, -1420174.5, -1417074.5,
                    evidence="mirror-label")]},
            "members": {"beams": [
                beam("B0001", "KL1(1)", "V", -1450500.0, 760940.5, 767040.5),
                beam("B0002", "KL11(1)", "H", 766500.0, -1443714.5, -1441064.5),
                beam("B0003", "L5(1)", "V", -1443495.5, 769640.5, 773440.5)]}}
        return dedup.build_dedup(model, DEDUP_OPTIONS)

    def test_dedup_enters_report_without_changing_quantity(self):
        ledger = self._dedup()
        base = report.build_report(
            sample_model(), sample_ledger(), sample_scan(), supplements={})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"梁实例去重": ledger})
        self.assertEqual(base["concrete"]["quantities"],
                         result["concrete"]["quantities"])
        self.assertEqual(base["direct_outputs"]["concrete_candidate_total_m3"],
                         result["direct_outputs"]["concrete_candidate_total_m3"])
        direct = result["direct_outputs"]
        summary = ledger["summary"]
        self.assertEqual(direct["beam_dedup_net_new_volume_m3"],
                         summary["model_beam_net_new_volume_m3"])
        self.assertEqual(direct["beam_dedup_double_count_volume_m3"],
                         summary["double_count_volume_m3"])
        self.assertEqual(direct["beam_dedup_run_self_overlap_pairs"], 0)
        self.assertFalse(direct["beam_dedup_applied_to_formal"])
        self.assertTrue(any(
            row.get("id") == "beam-instance-dedup" and row.get("status") == "warn"
            for row in result["closure_dashboard"]["gates"]))
        self.assertTrue(any(
            row.get("component") == "梁实例双口径去重"
            for row in result["closure_dashboard"]["component_gaps"]))
        markdown = report.render_markdown(result)
        self.assertIn("梁实例双口径去重", markdown)
        self.assertIn("不得把模型梁并入混凝土分账", markdown)
        self.assertIn("梁实例去重", {row[0] for row in report.csv_rows(result)})


class BeamInstanceDedupPipelineTest(unittest.TestCase):
    """单入口流水线默认跑梁实例双口径去重，并能用开关关闭。"""

    @staticmethod
    def _fake_run(name, script, arguments, **_kwargs):
        output = Path(arguments[arguments.index("-o") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".json").write_text(
            json.dumps({"summary": {}}), encoding="utf-8")
        return {"name": name, "status": "ok", "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": []}

    def _manifest(self, root, extra):
        dwg = root / "drawing.dxf"
        scan = root / "scan.json"
        dwg.write_bytes(b"DXF")
        scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
        out = root / "out"
        argv = ["cad_quantity_pipeline.py", "--dwg", str(dwg), "--scan", str(scan),
                "--floor-label", "首层", "--out", str(out), *extra]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(pipeline, "_run", self._fake_run):
            self.assertEqual(pipeline.main(), 0)
        return json.loads((out / "pipeline_manifest.json").read_text(
            encoding="utf-8")), argv

    def test_pipeline_runs_dedup_and_supplies_report(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest, _argv = self._manifest(Path(temp), [])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["beam-instance-dedup"]["status"], "ok")
        command = steps["beam-instance-dedup"]["command"]
        self.assertEqual(command[0], "cad_beam_instance_dedup.py")
        self.assertIn("--model-json", command)
        report_command = steps["quantity-report"]["command"]
        self.assertTrue(any(item.startswith("梁实例去重=")
                            for item in report_command))
        self.assertIn("beam_instance_dedup.json",
                      manifest["artifacts"]["beam_instance_dedup_json"])

    def test_pipeline_skips_dedup_when_switch_given(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest, _argv = self._manifest(
                Path(temp), ["--no-beam-instance-dedup"])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["beam-instance-dedup"]["status"], "skipped")
        self.assertEqual(manifest["artifacts"]["beam_instance_dedup_json"], "")
        report_command = steps["quantity-report"]["command"]
        self.assertFalse(any(item.startswith("梁实例去重=")
                             for item in report_command))



CONFLICT_OPTIONS = {"conflict_axis_tolerance_mm": 2500.0,
                    "min_overlap_ratio": 0.5, "require_same_section": True,
                    "strong_label_axis_tolerance_mm": 1000.0}


class BeamAttributionConflictTest(unittest.TestCase):
    """梁编号归属冲突定责接入统一报告与单入口流水线。"""

    @staticmethod
    def _ledger(dual: bool = False):
        run = {"id": "R0001", "matched_code": "WKL4(1)", "orientation": "V",
               "axis_mm": -1445014.5, "start_mm": 764990.5, "end_mm": 773440.5,
               "section": "200x500", "volume_m3": 0.845,
               "matched_leader_id": "L0008",
               "code_assignment_status": "leader-target"}
        beam = {"id": "B0001", "code": "KL12(2)", "base_code": "KL12",
                "section": "200x500", "gross_volume_m3": 0.845,
                "quantity_status": "clear-span-review",
                "centerline": {"start": [-1445014.5, 764990.5],
                               "end": [-1445014.5, 773440.5],
                               "orientation": "V", "axis_offset_mm": 0.0}}
        codes = {"L0008": ["WKL4"]}
        targets = {"L0008": {"orientation": "V", "axis_mm": -1445014.5,
                             "x": -1445014.5, "y": 771269.8,
                             "start_mm": 769640.5, "end_mm": 773440.5}}
        if dual:
            codes["L0009"] = ["KL12"]
            targets["L0009"] = {"orientation": "V", "axis_mm": -1445014.5,
                                "x": -1445014.5, "y": 766501.6,
                                "start_mm": 764990.5, "end_mm": 771000.0}
        model = {"run_registry": {"runs": [run], "leader_codes": codes,
                                  "leader_targets": targets},
                 "members": {"beams": [beam]}}
        return attribution_conflict.adjudicate(model, CONFLICT_OPTIONS)

    def test_conflict_enters_report_without_changing_quantity(self):
        ledger = self._ledger()
        base = report.build_report(
            sample_model(), sample_ledger(), sample_scan(), supplements={})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"梁编号冲突": ledger})
        self.assertEqual(base["concrete"]["quantities"],
                         result["concrete"]["quantities"])
        direct = result["direct_outputs"]
        self.assertEqual(direct["beam_conflict_pair_count"], 1)
        self.assertEqual(direct["beam_conflict_run_holds_pairs"], 1)
        self.assertEqual(direct["beam_conflict_double_count_risk_m3"],
                         ledger["summary"]["double_count_risk_m3"])
        self.assertFalse(direct["beam_conflict_applied_to_formal"])
        self.assertTrue(any(
            row.get("id") == "beam-attribution-conflict"
            and row.get("status") == "pass"
            for row in result["closure_dashboard"]["gates"]))
        dual = self._ledger(dual=True)
        dual_result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"梁编号冲突": dual})
        self.assertEqual(dual["summary"]["verdicts"]["dual-label-same-line"]
                         ["pair_count"], 1)
        self.assertTrue(any(
            row.get("id") == "beam-attribution-conflict"
            and row.get("status") == "warn"
            for row in dual_result["closure_dashboard"]["gates"]))
        self.assertTrue(any(
            row.get("component") == "梁编号归属冲突"
            for row in result["closure_dashboard"]["component_gaps"]))
        markdown = report.render_markdown(result)
        self.assertIn("梁编号归属冲突定责", markdown)
        self.assertIn("定主只搬编号归属、不搬几何", markdown)
        self.assertIn("逐对定主：已定", markdown)
        self.assertIn("梁编号归属冲突对", {row[0] for row in report.csv_rows(result)})

    @staticmethod
    def _fake_run(name, script, arguments, **_kwargs):
        output = Path(arguments[arguments.index("-o") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".json").write_text(
            json.dumps({"summary": {}}), encoding="utf-8")
        return {"name": name, "status": "ok", "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": []}

    def _manifest(self, root, extra):
        dwg = root / "drawing.dxf"
        scan = root / "scan.json"
        dwg.write_bytes(b"DXF")
        scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
        out = root / "out"
        argv = ["cad_quantity_pipeline.py", "--dwg", str(dwg), "--scan", str(scan),
                "--floor-label", "首层", "--out", str(out), *extra]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(pipeline, "_run", self._fake_run):
            self.assertEqual(pipeline.main(), 0)
        return json.loads((out / "pipeline_manifest.json").read_text(
            encoding="utf-8"))

    def test_pipeline_runs_conflict_closeout(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = self._manifest(Path(temp), [])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["beam-attribution-conflict"]["status"], "ok")
        self.assertEqual(
            steps["beam-attribution-conflict"]["command"][0],
            "cad_beam_attribution_conflict.py")
        self.assertTrue(any(item.startswith("梁编号冲突=")
                            for item in steps["quantity-report"]["command"]))
        self.assertIn("beam_attribution_conflict.json",
                      manifest["artifacts"]["beam_attribution_conflict_json"])

    def test_pipeline_skips_conflict_closeout_when_switch_given(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = self._manifest(
                Path(temp), ["--no-beam-attribution-conflict"])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["beam-attribution-conflict"]["status"], "skipped")
        self.assertEqual(
            manifest["artifacts"]["beam_attribution_conflict_json"], "")
        self.assertFalse(any(item.startswith("梁编号冲突=")
                             for item in steps["quantity-report"]["command"]))




class EvidenceLayerPipelineTest(unittest.TestCase):
    """证据层（中心线/墙身/板厚分档/统一扣减/预制展开）并入单入口流水线。"""

    @staticmethod
    def _fake_run(name, script, arguments, **_kwargs):
        output = Path(arguments[arguments.index("-o") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".json").write_text(
            json.dumps({"summary": {}}), encoding="utf-8")
        return {"name": name, "status": "ok", "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": []}

    def _manifest(self, root, extra):
        dwg = root / "drawing.dxf"
        scan = root / "scan.json"
        dwg.write_bytes(b"DXF")
        scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
        out = root / "out"
        argv = ["cad_quantity_pipeline.py", "--dwg", str(dwg), "--scan", str(scan),
                "--floor-label", "首层", "--out", str(out), *extra]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(pipeline, "_run", self._fake_run):
            self.assertEqual(pipeline.main(), 0)
        return json.loads((out / "pipeline_manifest.json").read_text(encoding="utf-8"))

    def test_optional_evidence_steps_record_reasons_when_inputs_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = self._manifest(Path(temp), [])
        steps = {row["name"]: row for row in manifest["steps"]}
        report_command = steps["quantity-report"]["command"]
        self.assertEqual(steps["slab-thickness-partition"]["status"], "ok")
        for name, why in (("beam-centerline-support", "缺实测梁线"),
                          ("wall-edge-closeout", "缺墙身面域几何"),
                          ("deduction-ledger", "缺构件相交审计"),
                          ("prefab-instance-expansion", "缺叠合板材料分账")):
            self.assertEqual(steps[name]["status"], "skipped", name)
            self.assertIn(why, steps[name]["reason"])
        for label in ("墙身闭合=", "统一扣减=", "预制展开="):
            self.assertFalse(any(item.startswith(label) for item in report_command))
        skipped = {row["name"] for row in manifest["skipped_steps"]}
        self.assertIn("prefab-instance-expansion", skipped)

    def test_evidence_steps_enter_the_single_report_when_inputs_given(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "beam.dxf").write_bytes(b"DXF")
            (root / "wall.json").write_text(json.dumps({
                "planar_faces": [], "wall_strip_rectangles": [],
                "edge_member_polygons": []}), encoding="utf-8")
            (root / "prefab.json").write_text(json.dumps({
                "component_reconciliation": []}), encoding="utf-8")
            manifest = self._manifest(root, [
                "--centerline-geometry-dxf", str(root / "beam.dxf"),
                "--slab-opening-dxf", str(root / "beam.dxf"),
                "--wall-geometry-json", str(root / "wall.json"),
                "--prefab-material-ledger-json", str(root / "prefab.json"),
                "--prefab-expanded-dxf", str(root / "beam.dxf")])
        steps = {row["name"]: row for row in manifest["steps"]}
        report_command = steps["quantity-report"]["command"]
        for name, label in (("beam-centerline-support", "中心线支撑="),
                            ("wall-edge-closeout", "墙身闭合="),
                            ("slab-thickness-partition", "板厚分档="),
                            ("deduction-ledger", "统一扣减="),
                            ("prefab-instance-expansion", "预制展开=")):
            self.assertEqual(steps[name]["status"], "ok", name)
            self.assertTrue(any(item.startswith(label) for item in report_command),
                            label)
        self.assertEqual(manifest["skipped_steps"], [])
        for key in ("beam_centerline_support.json", "wall_edge_closeout.json",
                    "slab_thickness_partition.json", "deduction_ledger.json",
                    "prefab_instance_expansion.json"):
            self.assertTrue(manifest["artifacts"][key], key)

    def test_switches_turn_every_evidence_step_off(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = self._manifest(Path(temp), [
                "--no-beam-centerline-support", "--no-wall-edge-closeout",
                "--no-slab-thickness-partition", "--no-deduction-ledger",
                "--no-prefab-expansion"])
        steps = {row["name"]: row for row in manifest["steps"]}
        report_command = steps["quantity-report"]["command"]
        for name in ("beam-centerline-support", "wall-edge-closeout",
                     "slab-thickness-partition", "deduction-ledger",
                     "prefab-instance-expansion"):
            self.assertEqual(steps[name]["status"], "skipped", name)
            self.assertIn("开关", steps[name]["reason"])
        self.assertFalse(any(item.split("=")[0] in (
            "中心线支撑", "墙身闭合", "板厚分档", "统一扣减", "预制展开")
            for item in report_command))
        self.assertEqual(len(manifest["skipped_steps"]), 5)




class S6RobustnessTest(unittest.TestCase):
    """单入口的三条硬要求：口径声明进报告、配准失败降级、图框 bbox 可显式覆盖。"""

    def test_caveat_lands_in_report_without_changing_quantity(self):
        base = report.build_report(sample_model(), sample_ledger(), sample_scan())
        noted = report.build_report(sample_model(), sample_ledger(), sample_scan(),
                                    caveats=["跨图框配准失败，已退回单图框模式"])
        self.assertEqual(base["concrete"]["quantities"], noted["concrete"]["quantities"])
        self.assertEqual(noted["caveats"], ["跨图框配准失败，已退回单图框模式"])
        self.assertIn("口径声明", report.render_markdown(noted))
        self.assertEqual(base.get("caveats"), [])

    def test_geometry_step_passes_explicit_bbox_with_equals_sign(self):
        captured = {}

        def spy(name, script, arguments, **_kwargs):
            captured["args"] = list(arguments)
            return {"name": name, "status": "ok", "command": [script, *arguments],
                    "elapsed_seconds": 0.0, "attempts": []}

        with mock.patch.object(pipeline, "_run", spy):
            pipeline._geometry_step(
                "support-geometry", Path("a.dxf"), Path("scan.json"), None,
                "标高-1.060~2.810墙柱平法施工图", Path("out/support"),
                60.0, 0, "-80000,730000,140000,790000")
        self.assertIn("--bbox=-80000,730000,140000,790000", captured["args"])
        self.assertNotIn("--bbox", captured["args"])

    def test_registration_failure_falls_back_to_single_sheet(self):
        calls = []

        def fake(name, script, arguments, **_kwargs):
            calls.append(name)
            output = Path(arguments[arguments.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            payload = {"summary": {}}
            if name == "structure-model":
                return {"name": name, "status": "failed",
                        "command": [script, *arguments], "elapsed_seconds": 0.0,
                        "attempts": [{"stderr_tail": "自动配准失败：锚点图或来源图没有匹配图层线段"}]}
            if name == "structure-model-single-sheet":
                payload = {"quantities": {}, "members": {}, "issues": []}
            output.with_suffix(".json").write_text(json.dumps(payload), encoding="utf-8")
            return {"name": name, "status": "ok", "command": [script, *arguments],
                    "elapsed_seconds": 0.0, "attempts": []}

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "d.dxf").write_bytes(b"DXF")
            (root / "scan.json").write_text(json.dumps({"members": {}}), encoding="utf-8")
            (root / "slab.dxf").write_bytes(b"DXF")
            argv = ["p", "--dwg", str(root / "d.dxf"), "--scan", str(root / "scan.json"),
                    "--floor-label", "首层梁", "--support-floor-label", "首层墙柱",
                    "--slab-floor-label", "首层板", "--slab-transform", "1,1",
                    "--out", str(root / "out")]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pipeline, "_run", fake):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads((root / "out" / "pipeline_manifest.json").read_text(
                encoding="utf-8"))
        self.assertIn("structure-model-single-sheet", calls)
        self.assertIn("单图框", manifest["degraded_mode"])
        report_step = next(row for row in manifest["steps"]
                           if row["name"] == "quantity-report")
        self.assertTrue(any(item == "--caveat" for item in report_step["command"]))


class GlodonIndicatorScopePipelineTest(unittest.TestCase):
    """广联达清单口径分解按成对参数触发，默认不进单入口流水线。"""

    @staticmethod
    def _fake_run(name, script, arguments, **_kwargs):
        output = Path(arguments[arguments.index("-o") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".json").write_text(
            json.dumps({"summary": {}}), encoding="utf-8")
        return {"name": name, "status": "ok", "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": []}

    def _manifest(self, root, extra):
        dwg = root / "drawing.dxf"
        scan = root / "scan.json"
        dwg.write_bytes(b"DXF")
        scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
        out = root / "out"
        argv = ["cad_quantity_pipeline.py", "--dwg", str(dwg), "--scan", str(scan),
                "--floor-label", "首层", "--out", str(out), *extra]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(pipeline, "_run", self._fake_run):
            self.assertEqual(pipeline.main(), 0)
        return json.loads((out / "pipeline_manifest.json").read_text(
            encoding="utf-8"))

    def test_pipeline_skips_scope_without_indicator(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = self._manifest(Path(temp), [])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["glodon-indicator-scope"]["status"], "skipped")
        self.assertEqual(
            manifest["artifacts"]["glodon_indicator_scope_json"], "")
        self.assertFalse(any(item.startswith("广联达口径=")
                             for item in steps["quantity-report"]["command"]))

    def test_pipeline_requires_both_indicator_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self._manifest(
                root, ["--glodon-indicator-xlsx", str(root / "指标.xlsx")])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["glodon-indicator-scope"]["status"], "skipped")
        self.assertIn("成对", steps["glodon-indicator-scope"]["reason"])

    def test_pipeline_runs_scope_and_supplies_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self._manifest(root, [
                "--glodon-indicator-xlsx", str(root / "指标.xlsx"),
                "--glodon-component-export-json", str(root / "按构件.json")])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["glodon-indicator-scope"]["status"], "ok")
        command = steps["glodon-indicator-scope"]["command"]
        self.assertEqual(command[0], "cad_glb_indicator_scope.py")
        self.assertIn("--reference-total-m3", command)
        self.assertIn("--cad-vertical-candidate-m3", command)
        self.assertTrue(any(item.startswith("广联达口径=")
                            for item in steps["quantity-report"]["command"]))
        self.assertIn("glodon_indicator_scope.json",
                      manifest["artifacts"]["glodon_indicator_scope_json"])



class SlabBinReconciliationReportTest(unittest.TestCase):
    """板面域分层与板缝归属接入统一报告，不改动混凝土量值。"""

    @staticmethod
    def _payload():
        return {
            "schema": "cad-slab-bin-reconciliation/v0.1",
            "floor": "首层",
            "summary": {
                "cad_cast_only_area_m2": 381.3001,
                "cad_seam_band_area_m2": 33.0651,
                "cad_on_prefab_area_m2": 145.185,
                "cad_cast_only_volume_m3": 48.6068,
                "cad_seam_band_volume_m3": 4.2468,
                "glodon_cast_in_place_volume_m3": 51.077,
                "glodon_seam_area_m2": 46.6992,
                "seam_band_inside_cast_ratio": 0.708,
                "cast_only_minus_glodon_cast_volume_m3": -2.4702},
            "thickness_evidence": [
                {"key": "130|drawing-note-rule|undetermined", "panel_count": 30,
                 "area_m2": 217.4},
                {"key": "130|dimension-label|cast-candidate", "panel_count": 17,
                 "area_m2": 167.42}],
            "thickness_evidence_summary": {
                "panel_count": 69, "panel_area_m2": 560.5251,
                "default_note_area_m2": 274.8975,
                "default_note_area_ratio": 0.4904,
                "direct_label_area_m2": 167.42},
            "closure": {"seam-band-deduplicated": False,
                        "thickness-evidence-chain-closed": False,
                        "applied-to-formal-quantity": False},
            "gates": [
                {"id": "slab-seam-band", "title": "板缝条带重复计量",
                 "status": "warn", "evidence": "条带 33.0651 m2 占板缝 70.8%"},
                {"id": "slab-thickness-evidence", "title": "板厚证据链",
                 "status": "fail", "evidence": "49.0% 板厚取自说明默认 130 mm"}],
            "formal_ready": False,
        }

    def test_slab_bins_enter_report_without_changing_quantity(self):
        base = report.build_report(
            sample_model(), sample_ledger(), sample_scan(), supplements={})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"板面域分层": self._payload()})
        self.assertEqual(base["concrete"]["quantities"],
                         result["concrete"]["quantities"])
        direct = result["direct_outputs"]
        self.assertEqual(direct["slab_cast_only_area_m2"], 381.3001)
        self.assertEqual(direct["slab_seam_band_volume_m3"], 4.2468)
        self.assertEqual(direct["slab_seam_band_vs_glodon_seam_ratio"], 0.708)
        self.assertEqual(direct["slab_thickness_default_note_area_ratio"],
                         0.4904)
        gates = {row["id"]: row for row in result["closure_dashboard"]["gates"]}
        self.assertEqual(gates["slab-seam-band"]["status"], "warn")
        gaps = result["closure_dashboard"]["component_gaps"]
        self.assertTrue(any(row.get("component") == "板面域分层与板缝归属"
                            for row in gaps))
        markdown = report.render_markdown(result)
        self.assertIn("板面域拆分：纯现浇/板缝条带/压预制m2", markdown)
        self.assertIn("板厚取自说明默认值面积m2", markdown)


class SlabThicknessEvidenceReportTest(unittest.TestCase):
    """板厚图例冲突与体积敏感性接入统一报告。"""

    @staticmethod
    def _payload():
        return {
            "schema": "cad-slab-thickness-evidence/v0.1",
            "floor": "首层",
            "summary": {
                "panel_count": 69, "panel_area_m2": 560.5251,
                "conflict_count": 10, "conflict_area_m2": 145.245,
                "conflict_area_ratio": 0.2591,
                "conflict_volume_current_m3": 18.8819,
                "volume_swing_m3": 1.4524,
                "direct_h_equals_labels": 4,
                "direct_labels_bound_to_panel": 2,
                "direct_labels_agreeing": 2, "note_defaults": [130.0, 140.0]},
            "conflicts": [
                {"id": "P0002", "assigned_thickness_mm": 130.0,
                 "hatch_thickness_mm": [140.0], "area_m2": 47.4525,
                 "hatch_area_m2": 38.525,
                 "thickness_source": "dimension-label"},
                {"id": "P0031", "assigned_thickness_mm": 130.0,
                 "hatch_thickness_mm": [120.0], "area_m2": 30.1,
                 "hatch_area_m2": 28.0, "thickness_source": "drawing-note-rule"}],
            "closure": {"thickness-conflict-resolved": False,
                        "sub-region-split-needed": True,
                        "applied-to-formal-quantity": False},
            "gates": [{"id": "slab-thickness-conflict",
                       "title": "板厚图例与归档冲突", "status": "warn",
                       "evidence": "10 块冲突 / 145.245 m2，摆动 1.4524 m3"}],
            "formal_ready": False,
        }

    def test_thickness_evidence_enters_report_without_changing_quantity(self):
        base = report.build_report(
            sample_model(), sample_ledger(), sample_scan(), supplements={})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"板厚证据": self._payload()})
        self.assertEqual(base["concrete"]["quantities"],
                         result["concrete"]["quantities"])
        direct = result["direct_outputs"]
        self.assertEqual(direct["slab_thickness_conflict_count"], 10)
        self.assertEqual(direct["slab_thickness_conflict_area_m2"], 145.245)
        self.assertEqual(direct["slab_thickness_volume_swing_m3"], 1.4524)
        self.assertEqual(direct["slab_thickness_direct_labels_agreeing"], 2)
        gates = {row["id"]: row for row in result["closure_dashboard"]["gates"]}
        self.assertEqual(gates["slab-thickness-conflict"]["status"], "warn")
        gaps = result["closure_dashboard"]["component_gaps"]
        gap = next(row for row in gaps
                   if row.get("component") == "板厚证据冲突")
        self.assertEqual(len(gap["blockers"]), 2)
        self.assertIn("子面域拆分", gap["action"])
        markdown = report.render_markdown(result)
        self.assertIn("板厚图例冲突面积m2 / 体积摆动m3", markdown)


class PrefabBookletEvidenceReportTest(unittest.TestCase):
    """装配式计算书设计锚点接入统一报告：只加证据与门槛，不动任何量值。"""

    @staticmethod
    def _payload():
        return {
            "schema": "cad-prefab-booklet-evidence/v0.1",
            "floor": "首层",
            "summary": {
                "identity_checks_total": 9, "identity_checks_passed": 9,
                "design_plate_area_m2": 566.61, "design_prefab_area_m2": 385.12,
                "cad_plate_area_m2": 560.5251, "cad_prefab_outline_area_m2": 183.747,
                "cad_prefab_expanded_area_m2": 356.8862,
                "glodon_prefab_area_m2": 356.877,
                "prefab_expansion_multiplier_design": 2.0959,
                "prefab_expansion_multiplier_glodon": 1.9422,
                "prefab_area_gap_m2": 28.2338,
                "prefab_gap_volume_at_design_thickness_m3": 3.6704,
                "cad_vs_design_plate_area_pct": -1.07,
                "cad_vs_design_prefab_area_pct": -7.33,
                "cad_outline_vs_design_prefab_area_pct": -52.29,
                "drawing_copies_identical": True,
                "design_agrees_with_glodon": True,
                "version_verdict": "版本差假设不成立"},
            "design_facts": {
                "design_vertical_and_beam_width_mm": 200,
                "design_composite_slab_thickness_mm": 130,
                "design_slab_thickness_default_share_pct": 95.0,
                "design_composite_seam_width_mm": 350,
                "design_std_vertical_area_m2": 31.24,
                "design_std_vertical_volume_m3": 90.6,
                "design_precast_wall_from_m": 11.51,
                "design_assembly_ratio_pct": 51},
            "comparisons": [
                {"item": "水平构件投影面积 m2/层", "design": 566.61,
                 "cad": 560.5251, "glodon": None, "cad_vs_design_pct": -1.07,
                 "note": "CAD 板面域总量首次获得设计侧独立锚点"},
                {"item": "预制叠合板面积 m2/层", "design": 385.12,
                 "cad": 183.747, "glodon": 356.877, "cad_vs_design_pct": -52.29,
                 "note": "CAD 只到设计值的 47.7%，缺口 201.4 m2/层"},
                {"item": "竖向构件截面积 m2/层", "design": 31.24,
                 "cad": 32.7073, "glodon": None, "cad_vs_design_pct": 4.7,
                 "note": "层高口径不同，只作量级校核"}],
            "identity_checks": [
                {"id": "A1a_合计=A1a*24", "left": 9242.88, "right": 9242.88,
                 "tolerance": 0.5, "ok": True}],
            "sheet_internal_notes": ["V 行机房层格 19.68 与公式行 13.68 不同"],
            "version_self_proof": {
                "struct_dwg_md5": "35a1519576792ec46bdbb4711cd1a0eb",
                "copies_identical": True,
                "design_agrees_with_glodon": True,
                "verdict": "版本差假设不成立"},
            "closure": {
                "cad_prefab_outline_area_m2": 183.747,
                "design_prefab_area_m2": 385.12,
                "prefab_area_gap_m2": 28.2338,
                "prefab_gap_volume_at_design_thickness_m3": 3.6704,
                "prefab_gap_volume_basis": "整厚口径",
                "instance-count-cad-independent-evidence": False},
            "frame_label_probe": {"labels": 82, "rings": 62, "ring_area_m2": 265.848,
                                  "w_series_labels": 26, "labels_without_ring": 20},
            "gates": [
                {"id": "drawing-model-version-consistency", "title": "图纸与模型版本自证",
                 "status": "pass", "evidence": "两处副本 md5 相同",
                 "action": "不得再用版本差解释板差。"},
                {"id": "slab-plate-area-independent-anchor", "title": "板面域设计锚点",
                 "status": "pass", "evidence": "566.61 vs 560.5251",
                 "action": "剩余争议只在厚度分档。"},
                {"id": "prefab-instance-expansion-anchor", "title": "预制板实例倍率锚点",
                 "status": "warn", "evidence": "设计倍率 2.0959 对广联达 1.9422",
                 "action": "用 CAD 编号数量与 (W) 系列自证实例数。"},
                {"id": "prefab-booklet-arithmetic-selfcheck", "title": "计算书口径自证",
                 "status": "pass", "evidence": "9/9 恒等式成立",
                 "action": "未命中符号按口径待定。"}],
            "formal_ready": False,
        }

    def test_design_anchor_enters_report_without_changing_quantity(self):
        base = report.build_report(
            sample_model(), sample_ledger(), sample_scan(), supplements={})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"设计指标": self._payload()})
        self.assertEqual(base["concrete"]["quantities"],
                         result["concrete"]["quantities"])
        direct = result["direct_outputs"]
        self.assertEqual(direct["design_plate_area_anchor_m2"], 566.61)
        self.assertEqual(direct["design_prefab_area_anchor_m2"], 385.12)
        self.assertEqual(direct["prefab_area_gap_vs_design_m2"], 28.2338)
        self.assertEqual(direct["cad_prefab_expanded_area_m2"], 356.8862)
        self.assertEqual(direct["prefab_expansion_multiplier_design"], 2.0959)
        self.assertEqual(direct["prefab_frame_w_series_label_count"], 26)
        self.assertEqual(
            direct["prefab_gap_volume_at_design_thickness_m3"], 3.6704)
        self.assertEqual(direct["design_slab_thickness_mm"], 130.0)
        self.assertEqual(direct["design_beam_and_wall_width_mm"], 200.0)
        self.assertTrue(direct["drawing_version_copies_identical"])
        self.assertEqual(direct["prefab_booklet_identity_checks"], "9/9")
        gates = {row["id"]: row for row in result["closure_dashboard"]["gates"]}
        self.assertEqual(gates["prefab-instance-expansion-anchor"]["status"], "warn")
        self.assertEqual(gates["drawing-model-version-consistency"]["status"], "pass")
        gap = next(row for row in result["closure_dashboard"]["component_gaps"]
                   if row.get("component") == "设计指标锚点与预制覆盖")
        self.assertEqual(gap["remaining_count"], 1)
        self.assertIn("按编号展开", gap["evidence"])
        self.assertTrue(any("预制叠合板面积" in text for text in gap["blockers"]))
        markdown = report.render_markdown(result)
        self.assertIn("装配式计算书设计锚点", markdown)
        self.assertIn("整厚 130 mm 口径", markdown)
        self.assertIn("(W) 镜像系列", markdown)




class ConcreteGradeLedgerTest(unittest.TestCase):
    """分标号内核：恒等式、来源分级与子层剔除；并接入统一报告。"""

    @staticmethod
    def _rules():
        return {
            "schema": "cad-concrete-grade-rules/v0.1",
            "floor": "首层",
            "expected_total_m3": 100.0,
            "rows": [
                {"component": "竖向", "member_group": "vertical", "volume_m3": 60.0,
                 "grade": "C40", "source_type": "design-booklet-table",
                 "source_ref": "层高表", "treatment": "vertical", "needs_review": True},
                {"component": "梁", "member_group": "beam", "volume_m3": 20.0,
                 "grade": "C30", "source_type": "drawing-table",
                 "source_ref": "表5.1", "treatment": "beam"},
                {"component": "板", "member_group": "slab-cast", "volume_m3": 20.0,
                 "grade": "C30", "source_type": "drawing-table",
                 "source_ref": "表5.1", "treatment": "slab-cast"},
                {"component": "预制底板", "member_group": "prefab-sublayer",
                 "volume_m3": 12.0, "grade": "未定", "source_type": "unknown",
                 "source_ref": "图面未标注", "treatment": "excluded-sublayer",
                 "needs_review": True}],
        }

    def test_ledger_identity_and_sources(self):
        payload = grade.build_ledger(self._rules(), {}, 100.0)
        self.assertEqual(payload["summary"]["counted_total_m3"], 100.0)
        self.assertEqual(payload["summary"]["excluded_sublayer_m3"], 12.0)
        self.assertEqual(payload["by_grade"], {"C30": 40.0, "C40": 60.0})
        self.assertEqual(payload["summary"]["identity_residual_m3"], 0.0)
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["grade-ledger-identity"], "pass")
        self.assertEqual(gates["grade-sublayer-double-count"], "pass")
        self.assertEqual(payload["summary"]["needs_review_m3"], 60.0)

    def test_joint_zone_row_uses_user_rule_and_keeps_total(self):
        rules = self._rules()
        rules["rows"].append(
            {"component": "梁柱节点区梁端500", "member_group": "joint-zone",
             "volume_m3": 4.63, "grade": "C40", "source_type": "user-rule",
             "source_ref": "用户确认：柱混凝土浇至梁端500mm",
             "treatment": "joint-zone-column-grade"})
        rules["rule_notes"] = {"joint_zone": "只改等级归属不改总量"}
        payload = grade.build_ledger(rules, {}, 104.63)
        summary = payload["summary"]
        self.assertEqual(summary["counted_total_m3"], 104.63)
        self.assertEqual(summary["joint_zone_m3"], 4.63)
        self.assertEqual(payload["by_grade"]["C40"], 64.63)
        self.assertEqual(summary["unconfirmed_m3"], 0.0)
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"分标号": payload})
        self.assertEqual(result["direct_outputs"]["grade_joint_zone_m3"], 4.63)
        self.assertIn("梁柱节点区按柱等级浇筑（梁端 500 mm）换算", report.render_markdown(result))

    def test_grade_ledger_enters_report_without_changing_quantity(self):
        built = grade.build_ledger(self._rules(), {}, 100.0)
        base = report.build_report(
            sample_model(), sample_ledger(), sample_scan(), supplements={})
        result = report.build_report(
            sample_model(), sample_ledger(), sample_scan(),
            supplements={"分标号": built})
        self.assertEqual(base["concrete"]["quantities"],
                         result["concrete"]["quantities"])
        direct = result["direct_outputs"]
        self.assertEqual(direct["grade_ledger_total_m3"], 100.0)
        self.assertEqual(direct["grade_volume_C30_m3"], 40.0)
        self.assertEqual(direct["grade_volume_C40_m3"], 60.0)
        self.assertEqual(direct["grade_ledger_excluded_sublayer_m3"], 12.0)
        gates = {row["id"]: row for row in result["closure_dashboard"]["gates"]}
        self.assertEqual(gates["grade-ledger-identity"]["status"], "pass")
        gap = next(row for row in result["closure_dashboard"]["component_gaps"]
                   if row.get("component") == "混凝土分标号台账")
        self.assertIn("C30=40.0 m3", gap["evidence"])
        self.assertTrue(any("竖向" in text for text in gap["blockers"]))
        markdown = report.render_markdown(result)
        self.assertIn("混凝土分标号台账", markdown)
        self.assertIn("剔除预制子层", markdown)



if __name__ == "__main__":
    unittest.main()


class ConcreteGradeLedgerPipelineTest(unittest.TestCase):
    """分标号台账按等级规则文件触发，接入单入口流水线与统一报告。"""

    @staticmethod
    def _fake_run(name, script, arguments, **_kwargs):
        output = Path(arguments[arguments.index("-o") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".json").write_text(json.dumps({
            "schema": "cad-concrete-grade-ledger/v0.1",
            "summary": {"counted_total_m3": 100.0,
                        "identity_baseline_source": "rules-json"},
        }), encoding="utf-8")
        return {"name": name, "status": "ok", "command": [script, *arguments],
                "elapsed_seconds": 0.0, "attempts": []}

    def _manifest(self, root, extra):
        dwg = root / "drawing.dxf"
        scan = root / "scan.json"
        dwg.write_bytes(b"DXF")
        scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
        out = root / "out"
        argv = ["cad_quantity_pipeline.py", "--dwg", str(dwg), "--scan", str(scan),
                "--floor-label", "首层", "--out", str(out), *extra]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(pipeline, "_run", self._fake_run):
            self.assertEqual(pipeline.main(), 0)
        return json.loads((out / "pipeline_manifest.json").read_text(
            encoding="utf-8"))

    def test_pipeline_skips_grade_without_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = self._manifest(Path(temp), [])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["concrete-grade-ledger"]["status"], "skipped")
        self.assertIn("--grade-rules-json",
                      steps["concrete-grade-ledger"]["reason"])
        self.assertEqual(manifest["artifacts"]["concrete_grade_ledger_json"], "")
        self.assertFalse(any(item.startswith("分标号=")
                             for item in steps["quantity-report"]["command"]))

    def test_pipeline_runs_grade_and_supplies_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rules = root / "等级规则.json"
            rules.write_text(json.dumps({"rows": []}), encoding="utf-8")
            manifest = self._manifest(root, ["--grade-rules-json", str(rules)])
        steps = {row["name"]: row for row in manifest["steps"]}
        grade_step = steps["concrete-grade-ledger"]
        self.assertEqual(grade_step["status"], "ok")
        self.assertEqual(grade_step["command"][0], "cad_concrete_grade.py")
        self.assertIn("--ledger-report-json", grade_step["command"])
        self.assertTrue(any(item.startswith("分标号=")
                            for item in steps["quantity-report"]["command"]))
        self.assertIn("concrete_grade_ledger.json",
                      manifest["artifacts"]["concrete_grade_ledger_json"])
        self.assertEqual(
            manifest["metrics"]["grade_ledger"]["counted_total_m3"], 100.0)

    def test_pipeline_skips_grade_when_rules_file_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self._manifest(
                root, ["--grade-rules-json", str(root / "不存在.json")])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["concrete-grade-ledger"]["status"], "skipped")
        self.assertIn("不存在", steps["concrete-grade-ledger"]["reason"])

    def test_pipeline_skips_grade_when_switch_given(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rules = root / "等级规则.json"
            rules.write_text(json.dumps({"rows": []}), encoding="utf-8")
            manifest = self._manifest(
                root, ["--grade-rules-json", str(rules), "--no-grade-ledger"])
        steps = {row["name"]: row for row in manifest["steps"]}
        self.assertEqual(steps["concrete-grade-ledger"]["status"], "skipped")
        self.assertEqual(manifest["artifacts"]["concrete_grade_ledger_json"], "")


class ConcreteGradeBaselineSourceTest(unittest.TestCase):
    """分账基准可以从规则文件、命令行或分账报告自动取，取不到才用自身合计。"""

    RULES = {
        "schema": "cad-concrete-grade-rules/v0.1",
        "floor": "首层",
        "rows": [{"component": "柱", "member_group": "vertical",
                  "volume_m3": 60.0, "grade": "C40",
                  "source_type": "drawing-table"},
                 {"component": "梁", "member_group": "beam",
                  "volume_m3": 40.0, "grade": "C30",
                  "source_type": "drawing-table"}],
    }

    def test_report_supplies_candidate_total_baseline(self):
        payload = grade.build_ledger(
            self.RULES,
            {"concrete_ledger": {"quantities":
                                 {"candidate_total_volume_m3": 100.0}}},
            100.0, "ledger-report")
        self.assertEqual(payload["summary"]["identity_baseline_source"],
                         "ledger-report")
        self.assertEqual(payload["summary"]["identity_residual_m3"], 0.0)

    def test_report_fallback_uses_self_when_no_number(self):
        payload = grade.build_ledger(self.RULES, {}, None, "self")
        self.assertEqual(payload["summary"]["identity_baseline_source"], "self")
        self.assertEqual(payload["summary"]["identity_residual_m3"], 0.0)

    def test_report_candidate_total_extractor(self):
        self.assertEqual(
            grade.report_candidate_total(
                {"concrete_candidate_total_m3": 273.2436}), 273.2436)
        self.assertEqual(
            grade.report_candidate_total(
                {"quantities": {"candidate_total_volume_m3": 99.5}}), 99.5)
        self.assertIsNone(grade.report_candidate_total({}))

    def test_main_backfills_floor_from_report(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rules = dict(self.RULES)
            rules.pop("floor")
            rules_path = root / "rules.json"
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            report_path = root / "report.json"
            report_path.write_text(json.dumps(
                {"floor_label": "首层",
                 "quantities": {"candidate_total_volume_m3": 100.0}}),
                encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "cad_concrete_grade.py"),
                 "--rules-json", str(rules_path),
                 "--ledger-report-json", str(report_path),
                 "-o", str(root / "out" / "grade")],
                capture_output=True, text=True, check=True)
            payload = json.loads(
                (root / "out" / "grade.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["floor"], "首层")
        self.assertEqual(payload["summary"]["identity_baseline_source"],
                         "ledger-report")
        self.assertEqual(payload["summary"]["counted_total_m3"], 100.0)


class SpecialMemberCloseoutGateTest(unittest.TestCase):
    """门槛要说清"还差什么"，不能拿 formal_ready 当理由。"""

    @staticmethod
    def _ledger():
        return {
            "special_member_localization": {
                "TL2": {"status": "plan-geometry-localized",
                        "volume_status": "independent-cad-quantity"}},
            "edge_member_spatial_attribution": {
                "outside_total_m2": 0.0005,
                "outside_review_tolerance_m2": 0.001,
                "fully_outside_member_count": 0},
        }

    def test_closed_when_special_independent_and_area_within_tolerance(self):
        gate = report._special_member_closeout_gate(self._ledger())
        self.assertEqual(gate["status"], "pass")
        self.assertIn("未定档 0 个", gate["evidence"])

    def test_reference_only_special_member_blocks(self):
        ledger = self._ledger()
        ledger["special_member_localization"]["TL2"]["volume_status"] = (
            "reference-only-not-independent-cad-quantity")
        gate = report._special_member_closeout_gate(ledger)
        self.assertEqual(gate["status"], "fail")
        self.assertIn("TL2", gate["evidence"])
        self.assertIn("回图", gate["action"])

    def test_outside_area_above_tolerance_reports_numbers(self):
        ledger = self._ledger()
        ledger["edge_member_spatial_attribution"]["outside_total_m2"] = 1.451
        ledger["edge_member_spatial_attribution"][
            "fully_outside_member_count"] = 14
        gate = report._special_member_closeout_gate(ledger)
        self.assertEqual(gate["status"], "fail")
        self.assertIn("1.4510 m2", gate["evidence"])
        self.assertIn("14 个", gate["evidence"])

    def test_missing_fields_do_not_claim_closure(self):
        gate = report._special_member_closeout_gate({
            "formal_ready": True,
            "special_member_localization": {
                "Lb-1": {"status": "partially-localized"}}})
        self.assertEqual(gate["status"], "fail")
        self.assertIn("Lb-1", gate["evidence"])


class ProjectProfileTest(unittest.TestCase):
    """项目配置只填命令行没显式给的值，避免两套口径打架。"""

    def _parse(self, argv, profile):
        parser = pipeline.build_parser()
        args = parser.parse_args(argv)
        applied = pipeline.apply_profile(args, parser, profile)
        return args, applied

    def test_profile_fills_unset_arguments(self):
        args, applied = self._parse(
            ["--dwg", "图.dwg", "--out", "out", "--floor-label", "二层梁平法施工图"],
            {"support_floor_label": "墙柱图", "story_height_mm": 3870.0,
             "concrete_grade": "C30", "component_sheet": 34})
        self.assertEqual(args.support_floor_label, "墙柱图")
        self.assertEqual(args.story_height_mm, 3870.0)
        self.assertEqual(args.concrete_grade, "C30")
        self.assertEqual(args.component_sheet, 34)
        self.assertEqual(args.floor_label, "二层梁平法施工图")
        self.assertEqual(sorted(applied),
                         ["component_sheet", "concrete_grade",
                          "story_height_mm", "support_floor_label"])

    def test_command_line_beats_profile(self):
        args, applied = self._parse(
            ["--dwg", "图.dwg", "--out", "out", "--story-height-mm", "2900"],
            {"story_height_mm": 3870.0})
        self.assertEqual(args.story_height_mm, 2900.0)
        self.assertEqual(applied, [])

    def test_unknown_profile_keys_are_ignored(self):
        args, applied = self._parse(
            ["--dwg", "图.dwg", "--out", "out"],
            {"not_an_argument": 1, "notes": "说明", "schema": "x"})
        self.assertEqual(applied, [])
        self.assertFalse(hasattr(args, "not_an_argument"))

    def test_load_profile_drops_meta_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            path.write_text(json.dumps({
                "schema": "cad-project-profile/v0.1", "notes": "x",
                "grade_regions": [{"name": "层高表"}],
                "floor_label": "梁平法", "concrete_grade": "C30"}),
                encoding="utf-8")
            data = pipeline.load_profile(str(path))
        self.assertEqual(data, {"floor_label": "梁平法", "concrete_grade": "C30"})

    def test_manifest_records_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dwg = root / "drawing.dxf"
            scan = root / "scan.json"
            dwg.write_bytes(b"DXF")
            scan.write_text(json.dumps({"members": {}}), encoding="utf-8")
            profile = root / "profile.json"
            profile.write_text(json.dumps({"concrete_grade": "C35",
                                           "story_height_mm": 3870.0}),
                               encoding="utf-8")
            argv = ["cad_quantity_pipeline.py", "--dwg", str(dwg),
                    "--scan", str(scan), "--floor-label", "首层",
                    "--out", str(root / "out"), "--profile", str(profile),
                    "--plan-only"]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(pipeline.main(), 0)
            manifest = json.loads(
                (root / "out" / "pipeline_manifest.json").read_text(
                    encoding="utf-8"))
        self.assertEqual(manifest["inputs"]["profile"], str(profile))
        self.assertEqual(sorted(manifest["inputs"]["profile_applied_keys"]),
                         ["concrete_grade", "story_height_mm"])
