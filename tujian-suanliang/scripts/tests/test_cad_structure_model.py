#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
VENDOR_DIR = SKILL_DIR / "vendor"
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(VENDOR_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_beam_objects  # noqa: E402
import cad_concrete_ledger as ledger  # noqa: E402
import cad_model_code_compare  # noqa: E402
import cad_stair_beam_registry as stair  # noqa: E402
import cad_structure_model as model  # noqa: E402


class IntervalTests(unittest.TestCase):
    def test_merge_intervals(self):
        self.assertEqual(
            model._merge_intervals(
                [(0.0, 500.0), (520.0, 900.0), (2000.0, 2500.0)],
                gap=25.0,
            ),
            [(0.0, 900.0), (2000.0, 2500.0)],
        )


class BeamTests(unittest.TestCase):
    def test_cluster_anchor_is_replaced_by_code_text_position(self):
        instances = [
            {"code": "KL1(1)", "x": 0.0, "y": 0.0, "sheet": 1},
            {"code": "L1(1)", "x": 0.0, "y": 0.0, "sheet": 1},
        ]
        data = {
            "text_records": [
                {"text": "KL1(1) 200x500", "x": 100.0, "y": 200.0, "sheet": 1},
                {"text": "L1(1) 200x400", "x": 300.0, "y": 400.0, "sheet": 1},
            ],
        }
        stats = cad_beam_objects.attach_annotation_text_positions(
            instances, data, 1500.0)
        self.assertEqual(stats["same-cell"], 2)
        self.assertEqual(
            (instances[0]["annotation_x"], instances[0]["annotation_y"]),
            (100.0, 200.0),
        )
        self.assertEqual(
            (instances[1]["annotation_x"], instances[1]["annotation_y"]),
            (300.0, 400.0),
        )

    def test_leader_alias_is_limited_to_same_annotation_point(self):
        rows = [
            {"code": "KL1(1)", "base_code": "KL1",
             "annotation_x": 0.0, "annotation_y": 0.0},
            {"code": "L1(1)", "base_code": "L1",
             "annotation_x": 0.0, "annotation_y": 0.0},
            {"code": "KL2(1)", "base_code": "KL2",
             "annotation_x": 1000.0, "annotation_y": 0.0},
        ]
        leaders = [
            {"a": (0.0, 0.0), "b": (0.0, 1000.0)},
            {"a": (1000.0, 0.0), "b": (1000.0, 1000.0)},
        ]
        aliases = cad_beam_objects.annotate_rows_with_leaders(rows, leaders)
        self.assertEqual(rows[0]["leader_id"], rows[1]["leader_id"])
        self.assertNotEqual(rows[1]["leader_id"], rows[2]["leader_id"])
        self.assertEqual(sorted(next(iter(aliases.values()))), ["KL1", "L1"])
        self.assertEqual(len(aliases), 2)

    def test_leader_target_resolves_to_beam_axis(self):
        leaders = [{
            "id": "L0001", "a": (0.0, 0.0), "b": (0.0, 2500.0),
        }]
        candidates = [
            {"orientation": "V", "center": 0.0, "start": 0.0,
             "end": 5000.0, "width_mm": 200.0},
            {"orientation": "H", "center": 2500.0, "start": 0.0,
             "end": 5000.0, "width_mm": 200.0},
        ]
        targets = cad_beam_objects.resolve_leader_targets(
            leaders, candidates)
        self.assertEqual(targets["L0001"]["orientation"], "V")
        self.assertEqual(targets["L0001"]["axis_mm"], 0.0)

    def test_registry_prefers_leader_target_over_cluster_anchor(self):
        candidates = [{
            "orientation": "V", "center": 0.0, "start": 0.0,
            "end": 5000.0, "width_mm": 200.0,
        }]
        rows = [{
            "code": "KL1(1)", "base_code": "KL1",
            "x": 2500.0, "y": 10000.0,
            "annotation_x": 2500.0, "annotation_y": 10000.0,
            "leader_id": "L0001",
            "section_b_mm": 200, "section_h_mm": 500,
            "detail": {
                "orientation": "H",
                "start": [0.0, 10000.0],
                "end": [5000.0, 10000.0],
            },
        }]
        targets = {
            "L0001": {
                "x": 0.0, "y": 2500.0, "distance_mm": 0.0,
                "orientation": "V", "axis_mm": 0.0,
                "start_mm": 0.0, "end_mm": 5000.0,
            },
        }
        registry = cad_beam_objects.build_beam_run_registry(
            candidates, [], rows, [-1000.0, -1000.0, 1000.0, 6000.0],
            leader_targets=targets,
        )
        run = registry["runs"][0]
        self.assertEqual(run["matched_code"], "KL1(1)")
        self.assertEqual(run["code_assignment_status"], "leader-target")
        self.assertEqual(run["leader_target_distance_mm"], 0.0)

    def test_leader_target_extends_truncated_centerline(self):
        candidates = [{
            "orientation": "V", "center": 0.0, "start": 0.0,
            "end": 1800.0, "width_mm": 200.0,
        }]
        rows = [{
            "code": "KL12(1)", "base_code": "KL12",
            "x": 0.0, "y": 2500.0, "leader_id": "L0012",
            "section_b_mm": 200, "section_h_mm": 500,
            "detail": {
                "orientation": "V",
                "start": [0.0, 0.0],
                "end": [0.0, 5000.0],
            },
        }]
        targets = {
            "L0012": {
                "x": 0.0, "y": 2500.0, "distance_mm": 0.0,
                "orientation": "V", "axis_mm": 0.0,
                "start_mm": 0.0, "end_mm": 5000.0,
            },
        }
        registry = cad_beam_objects.build_beam_run_registry(
            candidates, [], rows, [-1000.0, -1000.0, 1000.0, 6000.0],
            leader_targets=targets,
        )
        run = registry["runs"][0]
        self.assertEqual(run["matched_code"], "KL12(1)")
        self.assertAlmostEqual(run["length_mm"], 5000.0, places=3)
        self.assertEqual(run["leader_extent_candidate_count"], 1)
        self.assertAlmostEqual(run["volume_m3"], 0.5, places=3)

    def test_leader_extent_does_not_bridge_adjacent_runs(self):
        candidates = [
            {
                "orientation": "H", "center": 0.0, "start": 0.0,
                "end": 1800.0, "width_mm": 200.0,
            },
            {
                "orientation": "H", "center": 0.0, "start": 5000.0,
                "end": 8000.0, "width_mm": 200.0,
            },
        ]
        rows = [
            {
                "code": "KL12(1)", "base_code": "KL12",
                "x": 2500.0, "y": 0.0, "leader_id": "L0012",
                "section_b_mm": 200, "section_h_mm": 500,
                "detail": {
                    "orientation": "H",
                    "start": [0.0, 0.0],
                    "end": [5000.0, 0.0],
                },
            },
            {
                "code": "KL13(1)", "base_code": "KL13",
                "x": 6500.0, "y": 0.0, "leader_id": "L0013",
                "section_b_mm": 200, "section_h_mm": 500,
                "detail": {
                    "orientation": "H",
                    "start": [5000.0, 0.0],
                    "end": [8000.0, 0.0],
                },
            },
        ]
        targets = {
            "L0012": {
                "x": 900.0, "y": 0.0, "distance_mm": 0.0,
                "orientation": "H", "axis_mm": 0.0,
                "start_mm": 0.0, "end_mm": 1800.0,
            },
            "L0013": {
                "x": 6500.0, "y": 0.0, "distance_mm": 0.0,
                "orientation": "H", "axis_mm": 0.0,
                "start_mm": 5000.0, "end_mm": 8000.0,
            },
        }
        registry = cad_beam_objects.build_beam_run_registry(
            candidates, [], rows, [-1000.0, -1000.0, 9000.0, 1000.0],
            leader_targets=targets,
        )
        self.assertEqual(registry["quantities"]["run_count"], 2)
        self.assertEqual(
            sorted(run["matched_code"] for run in registry["runs"]),
            ["KL12(1)", "KL13(1)"],
        )
        self.assertEqual(
            sorted(run["length_mm"] for run in registry["runs"]),
            [3000.0, 5000.0],
        )

    def test_leader_target_run_ignores_fallback_competitor(self):
        candidates = [{
            "orientation": "V", "center": 0.0, "start": 0.0,
            "end": 5000.0, "width_mm": 200.0,
        }]
        rows = [
            {
                "code": "KL1(1)", "base_code": "KL1",
                "x": 500.0, "y": 2500.0, "leader_id": "L0001",
                "section_b_mm": 200, "section_h_mm": 500,
                "detail": {
                    "orientation": "V", "start": [0.0, 0.0],
                    "end": [0.0, 5000.0],
                },
            },
            {
                "code": "KL2(1)", "base_code": "KL2",
                "x": 500.0, "y": 2500.0,
                "section_b_mm": 200, "section_h_mm": 500,
                "detail": {
                    "orientation": "V", "start": [0.0, 0.0],
                    "end": [0.0, 5000.0],
                },
            },
        ]
        targets = {
            "L0001": {
                "x": 0.0, "y": 2500.0, "distance_mm": 0.0,
                "orientation": "V", "axis_mm": 0.0,
                "start_mm": 0.0, "end_mm": 5000.0,
            },
        }
        registry = cad_beam_objects.build_beam_run_registry(
            candidates, [], rows, [-1000.0, -1000.0, 1000.0, 6000.0],
            leader_targets=targets,
        )
        self.assertEqual(registry["runs"][0]["matched_code"], "KL1(1)")
        self.assertEqual(registry["runs"][0]["competing_codes"], [])

    def test_clear_nearest_fallback_is_not_reported_as_competitor(self):
        candidates = [{
            "orientation": "H", "center": 0.0, "start": 0.0,
            "end": 5000.0, "width_mm": 200.0,
        }]
        rows = [
            {
                "code": "KL1(1)", "base_code": "KL1",
                "x": 2500.0, "y": 0.0,
                "section_b_mm": 200, "section_h_mm": 500,
                "detail": {
                    "orientation": "H", "start": [0.0, 0.0],
                    "end": [5000.0, 0.0],
                },
            },
            {
                "code": "KL2(1)", "base_code": "KL2",
                "x": 2500.0, "y": 1000.0,
                "section_b_mm": 200, "section_h_mm": 500,
                "detail": {
                    "orientation": "H", "start": [0.0, 0.0],
                    "end": [5000.0, 0.0],
                },
            },
        ]
        registry = cad_beam_objects.build_beam_run_registry(
            candidates, [], rows, [-1000.0, -1000.0, 6000.0, 1000.0])
        self.assertEqual(registry["runs"][0]["matched_code"], "KL1(1)")
        self.assertEqual(registry["runs"][0]["competing_codes"], [])

    def test_run_registry_merges_gap_and_uses_nearest_label(self):
        primary = [{
            "orientation": "H", "center": 0.0, "start": 0.0, "end": 5000.0,
            "width_mm": 200.0,
        }]
        secondary = [
            {
                "orientation": "H", "center": 0.0, "start": 0.0,
                "end": 5000.0, "width_mm": 200.0,
            },
            {
                "orientation": "H", "center": 0.0, "start": 5400.0,
                "end": 10400.0, "width_mm": 200.0,
            },
        ]
        rows = [{
            "code": "KL1(2)", "x": 2500.0, "y": 0.0,
            "section_b_mm": 200, "section_h_mm": 500,
            "detail": {
                "orientation": "H", "start": [0.0, 0.0], "end": [5000.0, 0.0],
            },
        }]
        registry = cad_beam_objects.build_beam_run_registry(
            primary, secondary, rows, [-1000, -1000, 12000, 1000])
        self.assertEqual(registry["quantities"]["run_count"], 1)
        self.assertAlmostEqual(
            registry["runs"][0]["length_mm"], 10400.0, places=3)
        self.assertEqual(registry["runs"][0]["section_status"], "label-overlap")
        self.assertAlmostEqual(registry["runs"][0]["volume_m3"], 1.04, places=3)

    def test_run_registry_propagates_section_across_mirror_axis(self):
        primary = []
        rows = []
        for y, length in ((0.0, 4000.0), (1000.0, 3000.0), (2000.0, 2000.0)):
            primary.append({
                "orientation": "H", "center": y, "start": 0.0,
                "end": length, "width_mm": 200.0,
            })
            primary.append({
                "orientation": "H", "center": y, "start": 10000.0 - length,
                "end": 10000.0, "width_mm": 200.0,
            })
            rows.append({
                "code": f"KL{int(y / 1000) + 1}(1)",
                "x": length / 2.0,
                "y": y,
                "section_b_mm": 200,
                "section_h_mm": 500,
                "detail": {
                    "orientation": "H",
                    "start": [0.0, y],
                    "end": [length, y],
                },
            })
        registry = cad_beam_objects.build_beam_run_registry(
            primary, [], rows, [-1000, -1000, 11000, 3000])
        right_runs = [
            run for run in registry["runs"]
            if float(run["start_mm"]) >= 5000.0
        ]
        self.assertEqual(len(right_runs), 3)
        self.assertTrue(all(
            run["section_status"] == "mirror-label" for run in right_runs))
        self.assertTrue(all(
            abs(float(run["mirror_axis_mm"]) - 5000.0) < 20.0
            for run in right_runs))

    def test_run_registry_tolerates_clipped_mirror_span_and_groups_code(self):
        primary = []
        rows = []
        for y, length in (
                (0.0, 4000.0), (1000.0, 3000.0),
                (2000.0, 2000.0), (3000.0, 4000.0)):
            primary.append({
                "orientation": "H", "center": y, "start": 0.0,
                "end": length, "width_mm": 200.0,
            })
            right_end = (
                10400.0 if y == 3000.0 else 10000.0)
            primary.append({
                "orientation": "H", "center": y,
                "start": 10000.0 - length,
                "end": right_end, "width_mm": 200.0,
            })
            rows.append({
                "code": "KL1(1)",
                "x": length / 2.0,
                "y": y,
                "section_b_mm": 200,
                "section_h_mm": 500,
                "detail": {
                    "orientation": "H",
                    "start": [0.0, y],
                    "end": [length, y],
                },
            })
        registry = cad_beam_objects.build_beam_run_registry(
            primary, [], rows, [-1000, -1000, 11000, 4000])
        clipped = next(
            run for run in registry["runs"]
            if float(run["axis_mm"]) == 3000.0
            and float(run["start_mm"]) >= 5000.0)
        self.assertEqual(clipped["section_status"], "mirror-label")
        self.assertEqual(clipped["matched_code"], "KL1(1)")
        group = registry["code_quantities"]["KL1"]
        self.assertEqual(group["run_count"], 8)
        self.assertEqual(group["source_counts"]["mirror-label"], 4)

    def test_secondary_pair_duplicate_is_dropped(self):
        primary = [{
            "orientation": "H", "center": 0.0, "start": 0.0,
            "end": 5000.0, "width_mm": 200.0,
        }]
        secondary = [{
            "orientation": "H", "center": 400.0, "start": 0.0,
            "end": 5000.0, "width_mm": 600.0,
        }]
        result = cad_beam_objects._dedupe_centerline_candidates(
            primary, secondary)
        self.assertEqual(len(result), 1)

    def test_run_registry_strict_bbox_drops_neighbor_geometry(self):
        primary = [{
            "orientation": "V", "center": 15000.0, "start": 0.0,
            "end": 5000.0, "width_mm": 200.0,
        }]
        registry = cad_beam_objects.build_beam_run_registry(
            primary, [], [], [0.0, -1000.0, 10000.0, 6000.0])
        self.assertEqual(registry["quantities"]["run_count"], 0)

    def test_clear_spans_subtract_support_faces(self):
        row = {
            "code": "KL1(2)",
            "section_b_mm": 200,
            "section_h_mm": 500,
            "length_mm": 10000.0,
            "volume_m3": 1.0,
            "detail": {
                "orientation": "H",
                "start": [0.0, 0.0],
                "end": [10000.0, 0.0],
            },
        }
        supports = [
            {
                "orientation": "H",
                "center": 0.0,
                "start": 0.0,
                "end": 500.0,
                "width_mm": 500.0,
            },
            {
                "orientation": "H",
                "center": 0.0,
                "start": 4800.0,
                "end": 5200.0,
                "width_mm": 400.0,
            },
            {
                "orientation": "H",
                "center": 0.0,
                "start": 9500.0,
                "end": 10000.0,
                "width_mm": 500.0,
            },
        ]
        result = model._clear_span_quantity(
            row, supports, 1200.0, 20.0, 300.0)
        self.assertEqual(result["status"], "clear-span")
        self.assertEqual(result["clear_length_mm"], 8600.0)
        self.assertEqual(len(result["spans"]), 2)

    def test_beam_intersection_can_close_internal_support(self):
        row = {
            "code": "KL1(2)",
            "section_b_mm": 200,
            "section_h_mm": 500,
            "length_mm": 10000.0,
            "volume_m3": 1.0,
            "detail": {
                "orientation": "H",
                "start": [0.0, 0.0],
                "end": [10000.0, 0.0],
            },
        }
        end_supports = [
            {
                "orientation": "H", "center": 0.0,
                "start": 0.0, "end": 250.0, "width_mm": 250.0,
            },
            {
                "orientation": "H", "center": 0.0,
                "start": 9750.0, "end": 10000.0, "width_mm": 250.0,
            },
        ]
        beam_supports = model._beam_intersection_support_runs([{
            "id": "R0002",
            "orientation": "V",
            "axis_mm": 5000.0,
            "start_mm": -500.0,
            "end_mm": 500.0,
            "section_b_mm": 200,
            "matched_code": "KL2(1)",
        }])
        result = model._clear_span_quantity(
            row,
            end_supports,
            1200.0,
            20.0,
            300.0,
            beam_support_runs=beam_supports,
        )
        self.assertEqual(result["status"], "clear-span")
        self.assertEqual(result["support_count"], 3)
        self.assertEqual(result["clear_length_mm"], 9300.0)
        self.assertEqual(result["support_evidence"][-1]["type"],
                         "beam-intersection")
        self.assertEqual(result["support_evidence"][-1]["id"], "R0002")

    def test_beam_intersection_endpoint_tolerance_is_marked_for_review(self):
        row = {
            "code": "KL1(2)",
            "section_b_mm": 200,
            "section_h_mm": 500,
            "length_mm": 10000.0,
            "volume_m3": 1.0,
            "detail": {
                "orientation": "H",
                "start": [0.0, 0.0],
                "end": [10000.0, 0.0],
            },
        }
        end_supports = [
            {
                "orientation": "H", "center": 0.0,
                "start": 0.0, "end": 250.0, "width_mm": 250.0,
            },
            {
                "orientation": "H", "center": 0.0,
                "start": 9750.0, "end": 10000.0, "width_mm": 250.0,
            },
        ]
        beam_supports = model._beam_intersection_support_runs([{
            "id": "R0002",
            "orientation": "V",
            "axis_mm": 5000.0,
            "start_mm": 280.0,
            "end_mm": 2000.0,
            "section_b_mm": 200,
            "matched_code": "KL2(1)",
        }])
        result = model._clear_span_quantity(
            row,
            end_supports,
            1200.0,
            20.0,
            300.0,
            beam_support_runs=beam_supports,
            beam_intersection_end_tolerance_mm=300.0,
        )
        self.assertEqual(result["support_count"], 3)
        support = result["support_evidence"][-1]
        self.assertEqual(support["crossing_status"], "endpoint-tolerance")
        self.assertTrue(support["requires_review"])

    def test_support_count_above_declared_spans_is_flagged(self):
        row = {
            "code": "KL1(1)",
            "section_b_mm": 200,
            "section_h_mm": 500,
            "length_mm": 10000.0,
            "volume_m3": 1.0,
            "detail": {
                "orientation": "H",
                "start": [0.0, 0.0],
                "end": [10000.0, 0.0],
            },
        }
        supports = [
            {
                "orientation": "H", "center": 0.0,
                "start": lo, "end": hi, "width_mm": 200.0,
            }
            for lo, hi in ((0.0, 200.0), (4900.0, 5100.0), (9800.0, 10000.0))
        ]
        result = model._clear_span_quantity(
            row, supports, 1200.0, 20.0, 300.0)
        self.assertEqual(result["support_count_status"], "over")
        self.assertIn("超过编号跨数", result["issue"])

    def test_support_count_arbitration_keeps_endpoints(self):
        row = {
            "code": "KL1(1)",
            "section_b_mm": 200,
            "section_h_mm": 500,
            "length_mm": 10000.0,
            "volume_m3": 1.0,
            "detail": {
                "orientation": "H",
                "start": [0.0, 0.0],
                "end": [10000.0, 0.0],
            },
        }
        supports = [
            {
                "orientation": "H", "center": 0.0,
                "start": lo, "end": hi, "width_mm": 200.0,
            }
            for lo, hi in ((0.0, 200.0), (4900.0, 5100.0), (9800.0, 10000.0))
        ]
        result = model._clear_span_quantity(
            row,
            supports,
            1200.0,
            20.0,
            300.0,
            arbitrate_support_count=True,
        )
        self.assertEqual(result["support_count"], 2)
        self.assertEqual(result["support_count_status"], "exact")
        self.assertEqual(
            result["support_selection"]["status"],
            "expected-count-arbitrated",
        )
        self.assertEqual(
            result["support_selection"]["rejected_cluster_count"], 1)

    def test_endpoint_polygon_support_replaces_assumed_end(self):
        row = {
            "code": "KL1(1)",
            "section_b_mm": 200,
            "section_h_mm": 500,
            "length_mm": 10000.0,
            "volume_m3": 1.0,
            "detail": {
                "orientation": "H",
                "start": [0.0, 0.0],
                "end": [10000.0, 0.0],
            },
        }
        supports = [{
            "orientation": "H",
            "center": 0.0,
            "start": 0.0,
            "end": 200.0,
            "width_mm": 200.0,
        }]
        polygons = [{
            "id": "E0001",
            "source": "edge-member",
            "points": [[9800.0, -500.0], [10100.0, -500.0],
                       [10100.0, 500.0], [9800.0, 500.0]],
        }]
        result = model._clear_span_quantity(
            row,
            supports,
            1200.0,
            20.0,
            300.0,
            assumed_end_support_width=500.0,
            endpoint_support_polygons=polygons,
            endpoint_polygon_search_mm=1000.0,
        )
        self.assertEqual(result["support_count"], 2)
        self.assertEqual(result["status"], "clear-span-review")
        self.assertEqual(result["inferred_end_supports"], [])
        endpoint = [
            support for support in result["support_evidence"]
            if support["type"] == "endpoint-polygon"
        ]
        self.assertEqual(len(endpoint), 1)
        self.assertEqual(endpoint[0]["id"], "E0001")
        self.assertTrue(endpoint[0]["requires_review"])

    def test_beam_endpoint_matches_merged_interval(self):
        detail = cad_beam_objects.beam_run_details(
            [[0.0, 0.0, 6000.0, 0.0]], 3000.0, 0.0)
        self.assertIsNotNone(detail)
        length = math.dist(detail["start"], detail["end"])
        self.assertAlmostEqual(length, detail["length_mm"], places=3)

    def test_axis_chain_joins_support_gap(self):
        detail = cad_beam_objects.beam_run_details(
            [
                [0.0, 0.0, 5000.0, 0.0],
                [5400.0, 0.0, 10400.0, 0.0],
            ],
            1000.0,
            0.0,
            expected_spans=2,
        )
        self.assertEqual(detail["length_basis"], "axis-chain")
        self.assertAlmostEqual(detail["length_mm"], 10400.0, places=3)

    def test_assumed_end_supports_are_marked_as_inferred(self):
        row = {
            "code": "L1(1)",
            "section_b_mm": 200,
            "section_h_mm": 400,
            "length_mm": 6000.0,
            "volume_m3": 0.48,
            "detail": {
                "orientation": "H",
                "start": [0.0, 0.0],
                "end": [6000.0, 0.0],
            },
        }
        result = model._clear_span_quantity(
            row, [], 1200.0, 300.0, 300.0,
            assumed_end_support_width=500.0)
        self.assertEqual(result["status"], "clear-span-inferred")
        self.assertEqual(result["clear_length_mm"], 5000.0)
        self.assertEqual(len(result["inferred_end_supports"]), 2)

    def test_axis_chain_joins_short_multi_span_gaps(self):
        lines = [
            [0.0, 0.0, 3000.0, 0.0],
            [3300.0, 0.0, 6300.0, 0.0],
            [6600.0, 0.0, 9600.0, 0.0],
        ]
        result = cad_beam_objects.axis_chain_details(
            lines, 1500.0, 200.0, "H",
            join_gap_mm=400.0,
            max_perpendicular_mm=500.0,
            max_annotation_distance_mm=1000.0,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["length_mm"], 9600.0)
        self.assertEqual(result["axis_chain_components"], 3)

    def test_multi_span_run_uses_axis_chain(self):
        lines = [
            [0.0, 0.0, 3000.0, 0.0],
            [3300.0, 0.0, 6300.0, 0.0],
            [6600.0, 0.0, 9600.0, 0.0],
        ]
        result = cad_beam_objects.beam_run_details(
            lines, 1500.0, 200.0,
            run_mode="axis-chain",
            chain_gap_mm=400.0,
            max_perpendicular_mm=500.0,
            max_annotation_distance_mm=1000.0,
            expected_spans=3,
        )
        self.assertEqual(result["length_basis"], "axis-chain")
        self.assertEqual(result["length_mm"], 9600.0)


class StairBeamTests(unittest.TestCase):
    def test_extract_stair_labels_filters_bbox_and_merges_same_point(self):
        data = {
            "text_records": [
                {"text": "TL2", "x": 100.0, "y": 200.0,
                 "sheet": 1, "layer": "S-楼梯-文字"},
                {"text": "TL2  260X16=4160", "x": 101.0, "y": 201.0,
                 "sheet": 1, "layer": "S-楼梯-文字"},
                {"text": "TL3", "x": 9000.0, "y": 9000.0,
                 "sheet": 1, "layer": "S-楼梯-文字"},
            ],
        }
        labels = stair.extract_stair_labels(
            data, [0.0, 0.0, 1000.0, 1000.0], ["TL2", "TL3"])
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["code"], "TL2")
        self.assertEqual(len(labels[0]["texts"]), 2)

    def test_association_prefers_long_landing_beam_over_near_short_run(self):
        label = {"code": "TL2", "x": 0.0, "y": 1000.0}
        candidates = [
            {
                "orientation": "H", "center": 0.0, "start": -1000.0,
                "end": 1000.0, "width_mm": 200.0,
            },
            {
                "orientation": "H", "center": 1600.0, "start": -3000.0,
                "end": 3000.0, "width_mm": 200.0,
            },
        ]
        rows = stair.associate_labels_to_candidates(
            [label], candidates)
        self.assertEqual(rows[0]["match_status"], "matched")
        self.assertEqual(
            rows[0]["matched_candidate"]["length_mm"], 6000.0)

    def test_association_prefers_near_beam_when_it_is_within_text_tolerance(self):
        label = {"code": "TL3", "x": 0.0, "y": 1000.0}
        candidates = [
            {
                "orientation": "V", "center": 50.0, "start": 0.0,
                "end": 1800.0, "width_mm": 200.0,
            },
            {
                "orientation": "H", "center": 1200.0, "start": -3000.0,
                "end": 3000.0, "width_mm": 200.0,
            },
        ]
        rows = stair.associate_labels_to_candidates([label], candidates)
        self.assertEqual(
            rows[0]["matched_candidate"]["orientation"], "V")

    def test_expand_match_absorbs_same_axis_short_gap(self):
        instances = [{
            "code": "TL3", "x": 0.0, "y": 0.0, "texts": ["TL3"],
            "matched_candidate": {
                "orientation": "V", "axis_mm": 0.0,
                "start_mm": 0.0, "end_mm": 1190.0,
                "length_mm": 1190.0, "width_mm": 200.0,
                "perpendicular_mm": 0.0, "along_gap_mm": 0.0,
                "layers": ["S-梁-虚线"],
            },
        }]
        candidates = [{
            "orientation": "V", "center": 0.0,
            "start": 1310.0, "end": 2500.0, "width_mm": 200.0,
        }]
        rows = stair.expand_matched_candidates(instances, candidates)
        self.assertEqual(rows[0]["matched_candidate"]["length_mm"], 2500.0)
        self.assertEqual(rows[0]["matched_candidate"]["component_count"], 2)

    def test_expand_match_does_not_bridge_offset_axis_across_gap(self):
        instances = [{
            "code": "TL3", "x": 0.0, "y": 0.0, "texts": ["TL3"],
            "matched_candidate": {
                "orientation": "V", "axis_mm": 0.0,
                "start_mm": 600.0, "end_mm": 3100.0,
                "length_mm": 2500.0, "width_mm": 200.0,
                "perpendicular_mm": 0.0, "along_gap_mm": 0.0,
                "layers": ["S-梁-虚线"],
            },
        }]
        candidates = [{
            "orientation": "V", "center": 10.0,
            "start": 0.0, "end": 400.0, "width_mm": 200.0,
        }]
        rows = stair.expand_matched_candidates(instances, candidates)
        self.assertEqual(rows[0]["matched_candidate"]["start_mm"], 600.0)
        self.assertEqual(rows[0]["matched_candidate"]["length_mm"], 2500.0)

    def test_stair_registry_merges_split_beam_at_short_gap(self):
        base = {
            "code": "TL3", "x": 0.0, "y": 0.0, "texts": ["TL3"],
        }
        instances = []
        for start, end in ((0.0, 1190.0), (1310.0, 2500.0)):
            row = dict(base)
            row["matched_candidate"] = {
                "orientation": "V", "axis_mm": 0.0,
                "start_mm": start, "end_mm": end,
                "length_mm": end - start, "width_mm": 200.0,
                "perpendicular_mm": 0.0, "along_gap_mm": 0.0,
                "layers": ["S-梁-虚线"],
            }
            instances.append(row)
        registry = stair.build_stair_beam_registry(instances)
        group = registry["codes"]["TL3"]
        self.assertEqual(group["run_count"], 1)
        self.assertEqual(group["runs"][0]["component_count"], 2)
        self.assertEqual(group["runs"][0]["length_mm"], 2500.0)

    def test_stair_registry_keeps_run_separate_from_main_beams(self):
        instances = [
            {
                "code": "TL3", "x": 0.0, "y": 0.0,
                "texts": ["TL3"],
                "matched_candidate": {
                    "orientation": "V", "axis_mm": 0.0,
                    "start_mm": 0.0, "end_mm": 2500.0,
                    "length_mm": 2500.0, "width_mm": 200.0,
                    "perpendicular_mm": 0.0, "along_gap_mm": 0.0,
                    "layers": ["S-梁-虚线"],
                },
            },
        ]
        registry = stair.build_stair_beam_registry(
            instances,
            {"TL3": {"b_mm": 200, "h_mm": 400, "status": "provided"}},
        )
        self.assertEqual(registry["quantities"]["code_count"], 1)
        self.assertEqual(registry["quantities"]["run_count"], 1)
        self.assertAlmostEqual(
            registry["codes"]["TL3"]["gross_volume_m3"], 0.2, places=4)

    def test_stair_registry_applies_explicit_instance_multipliers(self):
        instances = []
        for code in ("TL2", "TL3"):
            instances.append({
                "code": code, "x": 0.0, "y": 0.0,
                "texts": [code],
                "matched_candidate": {
                    "orientation": "V", "axis_mm": 0.0,
                    "start_mm": 0.0, "end_mm": 2500.0,
                    "length_mm": 2500.0, "width_mm": 200.0,
                    "perpendicular_mm": 0.0, "along_gap_mm": 0.0,
                    "layers": ["S-梁-虚线"],
                },
            })
        registry = stair.build_stair_beam_registry(
            instances,
            {
                "TL2": {"b_mm": 200, "h_mm": 260, "status": "provided"},
                "TL3": {"b_mm": 200, "h_mm": 400, "status": "provided"},
            },
            instance_multiplier=2,
            code_multipliers={"TL3": 3},
            multiplier_basis="两跑楼梯叠合绘制",
        )
        tl2 = registry["codes"]["TL2"]
        tl3 = registry["codes"]["TL3"]
        self.assertEqual(tl2["instance_multiplier"], 2)
        self.assertEqual(tl3["instance_multiplier"], 3)
        self.assertEqual(tl2["quantity_centerline_length_mm"], 5000.0)
        self.assertEqual(tl3["quantity_centerline_length_mm"], 7500.0)
        self.assertAlmostEqual(tl2["gross_volume_m3"], 0.26, places=4)
        self.assertAlmostEqual(tl3["gross_volume_m3"], 0.6, places=4)
        self.assertEqual(
            registry["parameters"]["multiplier_basis"],
            "两跑楼梯叠合绘制",
        )

    def test_parse_stair_code_multipliers_rejects_bad_value(self):
        self.assertEqual(
            stair.parse_code_multipliers("TL2=2, TL3=2"),
            {"TL2": 2, "TL3": 2},
        )
        with self.assertRaises(SystemExit):
            stair.parse_code_multipliers("TL2")
        with self.assertRaises(SystemExit):
            stair.parse_code_multipliers("TL2=0")


class ColumnTests(unittest.TestCase):
    def test_orthogonal_runs_form_column_candidate(self):
        horizontal = [{
            "orientation": "H",
            "center": 500.0,
            "start": 0.0,
            "end": 1000.0,
            "width_mm": 500.0,
            "layers": ["S-柱"],
        }]
        vertical = [{
            "orientation": "V",
            "center": 500.0,
            "start": 0.0,
            "end": 1000.0,
            "width_mm": 500.0,
            "layers": ["S-柱"],
        }]
        columns = model._rectangles_from_runs(horizontal, vertical)
        self.assertEqual(len(columns), 1)
        self.assertAlmostEqual(columns[0]["b_mm"], 500.0)
        self.assertAlmostEqual(columns[0]["h_mm"], 500.0)


class ContourTests(unittest.TestCase):
    def test_open_chain_closes_edge_member_polygon(self):
        segments = [
            {
                "a": (0.0, 0.0), "b": (0.0, 200.0),
                "orientation": "V", "const": 0.0, "lo": 0.0, "hi": 200.0,
            },
            {
                "a": (0.0, 200.0), "b": (400.0, 200.0),
                "orientation": "H", "const": 200.0, "lo": 0.0, "hi": 400.0,
            },
            {
                "a": (400.0, 200.0), "b": (400.0, 0.0),
                "orientation": "V", "const": 400.0, "lo": 0.0, "hi": 200.0,
            },
        ]
        polygons = model._open_chain_polygons(
            segments, min_area_m2=0.01, max_area_m2=1.0)
        self.assertEqual(len(polygons), 1)
        self.assertAlmostEqual(polygons[0]["area_m2"], 0.08, places=4)
        self.assertAlmostEqual(polygons[0]["gap_mm"], 400.0, places=1)

    def test_closed_contour_is_kept_without_gap(self):
        segments = []
        for a, b in (
                ((0.0, 0.0), (0.0, 500.0)),
                ((0.0, 500.0), (500.0, 500.0)),
                ((500.0, 500.0), (500.0, 0.0)),
                ((500.0, 0.0), (0.0, 0.0))):
            x1, y1 = a
            x2, y2 = b
            if abs(y2 - y1) < 1e-6:
                orientation = "H"
                segments.append({
                    "a": a, "b": b, "orientation": orientation,
                    "const": y1, "lo": min(x1, x2), "hi": max(x1, x2),
                })
            else:
                orientation = "V"
                segments.append({
                    "a": a, "b": b, "orientation": orientation,
                    "const": x1, "lo": min(y1, y2), "hi": max(y1, y2),
                })
        polygons = model._open_chain_polygons(
            segments, min_area_m2=0.01, max_area_m2=1.0)
        self.assertEqual(len(polygons), 1)
        self.assertAlmostEqual(polygons[0]["area_m2"], 0.25, places=4)
        self.assertEqual(polygons[0]["gap_mm"], 0.0)

    def test_wall_run_subtracts_edge_polygon(self):
        run = {
            "orientation": "H",
            "center": 100.0,
            "start": 0.0,
            "end": 1000.0,
            "width_mm": 200.0,
            "layers": ["S-剪力墙"],
        }
        polygon = {
            "points": [[300.0, 0.0], [500.0, 0.0],
                       [500.0, 200.0], [300.0, 200.0]],
        }
        rows = model._clip_wall_runs([run], [polygon], 100.0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [(row["start"], row["end"]) for row in rows],
            [(0.0, 300.0), (500.0, 1000.0)],
        )


class AlignmentTests(unittest.TestCase):
    def test_translation_vote_recovers_shift(self):
        import ezdxf

        with tempfile.TemporaryDirectory() as tmp:
            anchor_path = Path(tmp) / "anchor.dxf"
            source_path = Path(tmp) / "source.dxf"
            for path, dx, dy in (
                    (anchor_path, 0.0, 0.0),
                    (source_path, 10000.0, 5000.0)):
                doc = ezdxf.new("R2010")
                msp = doc.modelspace()
                msp.add_line((dx, dy), (dx + 8000, dy),
                             dxfattribs={"layer": "S-梁-虚线"})
                msp.add_line((dx, dy), (dx, dy + 6000),
                             dxfattribs={"layer": "S-梁-虚线"})
                doc.saveas(str(path))
            result = model.estimate_translation(
                anchor_path,
                source_path,
                model.DEFAULT_AUTO_ALIGN_LAYERS,
                [0.0, 0.0, 10000.0, 7000.0],
            )
        self.assertEqual(result["transform"], [-10000.0, -5000.0])

    def test_same_layer_shape_alignment_beats_cross_layer_noise(self):
        import ezdxf

        with tempfile.TemporaryDirectory() as tmp:
            anchor_path = Path(tmp) / "anchor.dxf"
            source_path = Path(tmp) / "source.dxf"
            doc = ezdxf.new("R2010")
            msp = doc.modelspace()
            for a, b in (
                    ((0, 0), (0, 500)),
                    ((0, 500), (500, 500)),
                    ((500, 500), (500, 0))):
                msp.add_line(a, b, dxfattribs={"layer": "S-柱"})
            doc.saveas(str(anchor_path))

            doc = ezdxf.new("R2010")
            msp = doc.modelspace()
            for a, b in (
                    ((1000, 2000), (1000, 2500)),
                    ((1000, 2500), (1500, 2500)),
                    ((1500, 2500), (1500, 2000))):
                msp.add_line(a, b, dxfattribs={"layer": "S-柱"})
            msp.add_line((0, 0), (500, 0), dxfattribs={"layer": "S-剪力墙"})
            msp.add_line((500, 0), (500, 500),
                         dxfattribs={"layer": "S-剪力墙"})
            doc.saveas(str(source_path))

            result = model.estimate_translation(
                anchor_path,
                source_path,
                model.DEFAULT_AUTO_ALIGN_LAYERS,
                [-1000.0, 1000.0, 2000.0, 3000.0],
            )
        self.assertEqual(result["mode"], "same-layer-shape")
        self.assertEqual(result["transform"], [-1000.0, -2000.0])


class ModelCompareTests(unittest.TestCase):
    def test_structure_members_are_accepted_as_cad_rows(self):
        data = {
            "floor": {"label": "三层~五层"},
            "members": {
                "beams": [
                    {"code": "KL1(1)", "base_code": "KL1",
                     "volume_m3": 1.0, "clear_volume_m3": 0.8},
                ],
            },
        }
        rows = cad_model_code_compare.extract_auto_rows(data)
        values = cad_model_code_compare.load_auto(rows, "clear_volume_m3")
        self.assertEqual(values, {"kl1": 0.8})

    def test_topology_code_quantities_are_loaded(self):
        data = {
            "run_registry": {
                "code_quantities": {
                    "KL1": {"code": "KL1", "estimated_volume_m3": 1.2},
                    "__unassigned__": {
                        "code": "", "estimated_volume_m3": 0.1},
                },
            },
        }
        values = cad_model_code_compare.load_auto_topology(data)
        self.assertEqual(values, {"kl1": 1.2, "__unassigned__": 0.1})


class ComponentAttributeTests(unittest.TestCase):
    def test_component_label_is_propagated_across_mirror_axis(self):
        objects = [
            {
                "id": "E0001",
                "points": [[-1200, -200], [-800, -200],
                           [-800, 200], [-1200, 200]],
            },
            {
                "id": "E0002",
                "points": [[800, -200], [1200, -200],
                           [1200, 200], [800, 200]],
            },
        ]
        records = [{
            "sheet": 1,
            "layer": "S-剪力墙-构件文字",
            "text": "YBZ1",
            "x": -1300,
            "y": 0,
        }]
        summary = model.assign_object_labels(
            objects,
            records,
            (0.0, 0.0),
            model.DEFAULT_COMPONENT_TEXT_LAYER,
            model.DEFAULT_EDGE_MEMBER_LABEL_PATTERN,
            mirror_min_votes=1,
        )
        self.assertEqual(summary["direct_count"], 1)
        self.assertEqual(summary["mirror_count"], 1)
        self.assertEqual(objects[0]["label"], "YBZ1")
        self.assertEqual(objects[1]["label"], "YBZ1")
        self.assertEqual(objects[1]["label_status"], "mirror-propagated")

    def test_truncated_edge_member_mirror_is_marked_for_review(self):
        objects = [
            {
                "id": "E0001",
                "points": [[-1200, -200], [-800, -200],
                           [-800, 200], [-1200, 200]],
            },
            {
                "id": "E0002",
                "points": [[1550, -200], [1850, -200],
                           [1850, 200], [1550, 200]],
            },
            {
                "id": "E0003",
                "points": [[2200, -200], [2600, -200],
                           [2600, 200], [2200, 200]],
            },
        ]
        records = [{
            "sheet": 1,
            "layer": "S-剪力墙-构件文字",
            "text": "YBZ1",
            "x": -1300,
            "y": 0,
        }]
        summary = model.assign_object_labels(
            objects,
            records,
            (0.0, 0.0),
            model.DEFAULT_COMPONENT_TEXT_LAYER,
            model.DEFAULT_EDGE_MEMBER_LABEL_PATTERN,
            mirror_min_votes=1,
            mirror_axis_x_mm=0.0,
            mirror_review_tolerance_mm=800.0,
            mirror_review_shape_tolerance_mm=600.0,
        )
        self.assertEqual(summary["mirror_strict_count"], 0)
        self.assertEqual(summary["mirror_review_count"], 1)
        self.assertEqual(objects[1]["label_status"], "mirror-propagated-review")
        self.assertTrue(objects[1]["mirror_requires_review"])
        self.assertEqual(
            objects[1]["mirror_review_reason"],
            "review-truncated-or-resized-shape",
        )
        self.assertEqual(objects[2]["label_status"], "unlabeled")

    def test_column_label_mirror_allows_changed_candidate_width(self):
        objects = [
            {
                "id": "C0001",
                "points": [[-1250, -250], [-750, -250],
                           [-750, 250], [-1250, 250]],
            },
            {
                "id": "C0002",
                "points": [[750, -250], [1490, -250],
                           [1490, 250], [750, 250]],
            },
            {
                "id": "C0003",
                "points": [[-4250, -250], [-3750, -250],
                           [-3750, 250], [-4250, 250]],
            },
            {
                "id": "C0004",
                "points": [[3750, -250], [4250, -250],
                           [4250, 250], [3750, 250]],
            },
        ]
        records = [{
            "sheet": 1,
            "layer": "S-剪力墙-构件文字",
            "text": "KZ1",
            "x": -1350,
            "y": 0,
        }]
        summary = model.assign_object_labels(
            objects,
            records,
            (0.0, 0.0),
            model.DEFAULT_COMPONENT_TEXT_LAYER,
            model.DEFAULT_COLUMN_LABEL_PATTERN,
            require_mirror_shape=False,
            mirror_min_votes=1,
            mirror_match_tolerance_mm=300.0,
            mirror_axis_x_mm=0.0,
        )
        self.assertEqual(summary["mirror_count"], 1)
        self.assertEqual(objects[1]["label"], "KZ1")

    def test_hatch_rule_parser_and_slab_attributes(self):
        self.assertEqual(
            model._parse_hatch_rule_map(
                "H1,H2=drop-30;H3=140;H4=120"),
            {"H1": "drop-30", "H2": "drop-30", "H3": "140",
             "H4": "120"},
        )
        panels = [{
            "id": "P0001",
            "area_m2": 2.0,
            "points": [[0, 0], [2000, 0], [2000, 1000], [0, 1000]],
        }]
        hatches = [{
            "id": "H0001",
            "handle": "H1",
            "fill_rule": "140",
            "area_m2": 2.0,
            "points": [[0, 0], [2000, 0],
                       [2000, 1000], [0, 1000]],
        }]
        opening_line = {
            "handle": "L1",
            "layer": "S-板-开洞",
            "a": (100.0, 100.0),
            "b": (1900.0, 900.0),
        }
        summary = model.assign_slab_attributes(
            panels,
            hatches,
            [],
            [opening_line],
            [],
            (0.0, 0.0),
            default_thickness_mm=130.0,
        )
        self.assertEqual(panels[0]["thickness_mm"], 140)
        self.assertEqual(panels[0]["thickness_source"], "hatch-rule")
        self.assertEqual(
            panels[0]["thickness_verification"], "legend-review-required")
        self.assertEqual(summary["thickness_review_required_count"], 1)
        self.assertEqual(panels[0]["opening_status"], "opening-candidate")
        self.assertEqual(
            summary["thickness_area_m2"], {"140": 2.0})

    def test_structure_csv_rows_have_stable_width(self):
        rows = model.csv_rows({
            "members": {
                "beams": [],
                "slabs": [{"id": "S0001", "area_m2": 31.395}],
                "slab_panels": [],
            },
            "quantities": {"members": []},
        })
        self.assertTrue(rows)
        self.assertEqual({len(row) for row in rows}, {len(rows[0])})

    def test_dxf_overlay_keeps_support_geometry_after_beam_supports(self):
        import ezdxf

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overlay.dxf"
            model.write_dxf_overlay(
                path,
                [{
                    "code": "KL1(1)",
                    "quantity_status": "clear-span-inferred",
                    "centerline": {
                        "orientation": "H",
                        "start": [0.0, 0.0],
                        "end": [5000.0, 0.0],
                    },
                    "support_evidence": [{
                        "type": "wall-column",
                        "start_mm": 0.0,
                        "end_mm": 200.0,
                        "width_mm": 200.0,
                        "selection_status": "selected",
                    }],
                }],
                [],
                {
                    "walls": [{
                        "orientation": "V",
                        "center": 1000.0,
                        "start": 0.0,
                        "end": 1000.0,
                        "width_mm": 200.0,
                    }],
                    "edge_members": [],
                    "columns": [],
                },
                {},
            )
            doc = ezdxf.readfile(path)
            layers = [entity.dxf.layer for entity in doc.modelspace()]
        self.assertIn("AUTO_MODEL_BEAM_NET", layers)
        self.assertIn("AUTO_MODEL_SUPPORT_SELECTED", layers)
        self.assertIn("AUTO_MODEL_WALL", layers)

    def test_dimension_label_overrides_hatch_thickness(self):
        panels = [{
            "id": "P0001",
            "area_m2": 1.0,
            "points": [[0, 0], [1000, 0], [1000, 1000], [0, 1000]],
        }]
        hatches = [{
            "id": "H0001",
            "fill_rule": "140",
            "area_m2": 1.0,
            "points": [[0, 0], [1000, 0],
                       [1000, 1000], [0, 1000]],
        }]
        model.assign_slab_attributes(
            panels,
            hatches,
            [{
                "text": "h=130",
                "x": 200.0,
                "y": 200.0,
                "layer": "S-板-板厚",
            }],
            [],
            [],
            (0.0, 0.0),
            default_thickness_mm=130.0,
        )
        self.assertEqual(panels[0]["thickness_mm"], 130)
        self.assertEqual(panels[0]["thickness_source"], "dimension-label")


class ConcreteLedgerTests(unittest.TestCase):
    def _model(self):
        return {
            "schema": "cad-structure-model/v0.5",
            "floor": {"label": "二层", "concrete_grade": "C30"},
            "quantities": {
                "beam": {
                    "count": 1,
                    "topology_volume_m3": 2.0,
                    "clear_span_volume_m3": 1.0,
                    "review_clear_span_volume_m3": 0.5,
                    "inferred_clear_span_volume_m3": 0.25,
                    "clear_span_count": 1,
                    "review_clear_span_count": 0,
                    "inferred_clear_span_count": 0,
                    "topology_assigned_run_count": 1,
                    "topology_run_count": 1,
                    "topology_ambiguous_run_count": 0,
                    "topology_unassigned_run_count": 0,
                    "topology_status_counts": {},
                },
                "wall": {"count": 1, "candidate_volume_m3": 3.0},
                "edge_member": {
                    "count": 1,
                    "candidate_volume_m3": 4.0,
                    "label_summary": {
                        "mirror_review_count": 0,
                        "unlabeled_count": 0,
                    },
                },
                "column": {
                    "count": 1,
                    "candidate_volume_m3": 5.0,
                    "label_summary": {"unlabeled_count": 0},
                },
                "slab": {
                    "attribute_summary": {
                        "direct_thickness_count": 1,
                        "thickness_review_required_count": 0,
                        "thickness_default_count": 0,
                        "opening_candidate_count": 0,
                    },
                },
            },
            "members": {
                "beams": [{
                    "quantity_status": "clear-span",
                    "inferred_end_supports": [],
                }],
                "slab_panels": [{
                    "id": "P0001",
                    "area_m2": 10.0,
                    "thickness_mm": 100.0,
                    "points": [[0, 0], [10, 0], [10, 1], [0, 1]],
                }],
            },
        }

    def test_build_ledger_keeps_formal_use_blocked(self):
        result = ledger.build_ledger(
            self._model(),
            {"梁及连梁": 2.2, "剪力墙": 6.0, "板体系": 1.0},
            "第2层",
            "图纸楼层映射待确认",
            None,
            "S-PC-叠合板轮廓",
            (0.0, 0.0),
            5000.0,
            None,
        )
        self.assertFalse(result["formal_ready"])
        self.assertEqual(
            result["gate_summary"], {"warn": 1, "pass": 5, "fail": 1})
        self.assertEqual(result["quantities"]["candidate_total_volume_m3"], 15.0)

    def test_prefab_analysis_assigns_observed_panel(self):
        panel = {
            "id": "P0001",
            "area_m2": 100.0,
            "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
        }
        prefab = [{
            "area_m2": 4.0,
            "points": [[1, 1], [3, 1], [3, 3], [1, 3]],
            "bbox": [1, 1, 3, 3],
        }]
        result = ledger._prefab_analysis([panel], prefab, 4.0)
        self.assertEqual(result["polygon_count"], 1)
        self.assertEqual(result["assigned_area_m2"], 4.0)
        self.assertEqual(result["assigned_panel_count"], 1)
        self.assertEqual(result["reference_coverage_pct"], 100.0)
        self.assertEqual(panel["material_observation"], "prefab-observed")

    def test_prefab_loader_reads_closed_lwpolyline_and_label(self):
        import ezdxf

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefab.dxf"
            doc = ezdxf.new("R2010")
            msp = doc.modelspace()
            msp.add_lwpolyline(
                [(0, 0), (2000, 0), (2000, 1000), (0, 1000)],
                close=True,
                dxfattribs={"layer": "S-PC-叠合板轮廓"},
            )
            msp.add_text(
                "YDB-01",
                dxfattribs={
                    "layer": "S-PC-编号",
                    "insert": (1000, 500),
                },
            )
            doc.saveas(str(path))
            polygons = ledger._load_prefab_polygons(
                path,
                "S-PC-叠合板轮廓",
                (0.0, 0.0),
                5000.0,
                analysis_bbox=[-1000, -1000, 3000, 2000],
            )
        self.assertEqual(len(polygons), 1)
        self.assertEqual(polygons[0]["source_type"], "LWPOLYLINE")
        self.assertEqual(polygons[0]["component_code"], "YDB-1")
        self.assertAlmostEqual(polygons[0]["area_m2"], 2.0, places=4)

    def test_prefab_analysis_resolves_same_code_repetition(self):
        panel = {
            "id": "P0001",
            "area_m2": 100.0,
            "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
        }
        prefab = [{
            "component_code": "YDB-1",
            "source_handle": "A1",
            "area_m2": 4.0,
            "points": [[1, 1], [3, 1], [3, 3], [1, 3]],
            "bbox": [1, 1, 3, 3],
        }]
        model = {
            "components": {
                "YDB-01": {
                    "count": 2,
                    "projection_area_m2": 8.0,
                    "volume_m3": 0.48,
                },
            },
        }
        result = ledger._prefab_analysis(
            [panel], prefab, 16.0, model_components=model)
        self.assertEqual(result["reference_area_m2"], 8.0)
        self.assertEqual(result["reference_coverage_pct"], 50.0)
        self.assertEqual(result["model_component_match_pct"], 100.0)
        self.assertEqual(result["components"][0]["repetition_factor"], 2)
        self.assertEqual(
            result["components"][0]["reconstructed_projection_area_m2"],
            8.0,
        )

    def test_prefab_analysis_assigns_near_boundary_piece(self):
        panel = {
            "id": "P0001",
            "area_m2": 100.0,
            "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
        }
        prefab = [{
            "component_code": "YDB-1",
            "area_m2": 2.0,
            "points": [
                [10.01, 1], [12, 1], [12, 3], [10.01, 3],
            ],
            "bbox": [10.01, 1, 12, 3],
        }]
        result = ledger._prefab_analysis([panel], prefab, 2.0)
        self.assertEqual(result["assigned_polygon_count"], 1)
        self.assertEqual(result["unassigned_polygon_count"], 0)
        self.assertEqual(result["assigned_by_boundary_count"], 1)
        self.assertEqual(
            result["assignments"][0]["assignment_status"],
            "nearest-boundary-review",
        )


class SlabTests(unittest.TestCase):
    def _write_rectangles(self, path: Path):
        import ezdxf

        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        for points, layer in (
            ([(0, 0), (10000, 0), (10000, 5000), (0, 5000)], "S-板-板边线"),
            ([(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)],
             "S-板-开洞"),
        ):
            for a, b in zip(points, points[1:] + points[:1]):
                msp.add_line(a, b, dxfattribs={"layer": layer})
        doc.saveas(str(path))

    def test_closed_slab_deducts_contained_opening(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slab.dxf"
            self._write_rectangles(path)
            slabs, summary = model.build_slabs(
                path,
                path,
                model.DEFAULT_SLAB_LAYERS,
                model.DEFAULT_OPENING_LAYERS,
                (0.0, 0.0),
                10.0,
                100.0,
            )
        self.assertEqual(summary["closed_count"], 1)
        self.assertEqual(len(slabs), 1)
        self.assertAlmostEqual(slabs[0]["area_m2"], 49.0, places=3)
        self.assertAlmostEqual(slabs[0]["volume_m3"], 4.9, places=3)

    def test_planar_face_graph_splits_slab_into_two_panels(self):
        segments = []
        for points in (
                [(0, 0), (10000, 0), (10000, 5000), (0, 5000)],
                [(5000, 0), (5000, 5000)]):
            for a, b in zip(points, points[1:] + points[:1]):
                x1, y1 = a
                x2, y2 = b
                if abs(y2 - y1) < 1e-6:
                    orientation = "H"
                    segments.append({
                        "a": a, "b": b, "orientation": orientation,
                        "const": y1, "lo": min(x1, x2), "hi": max(x1, x2),
                    })
                else:
                    orientation = "V"
                    segments.append({
                        "a": a, "b": b, "orientation": orientation,
                        "const": x1, "lo": min(y1, y2), "hi": max(y1, y2),
                    })
        panels = model._planar_face_polygons(segments, min_area_m2=1.0)
        self.assertEqual(len(panels), 2)
        self.assertAlmostEqual(
            sum(panel["area_m2"] for panel in panels), 50.0, places=3)


if __name__ == "__main__":
    unittest.main()
