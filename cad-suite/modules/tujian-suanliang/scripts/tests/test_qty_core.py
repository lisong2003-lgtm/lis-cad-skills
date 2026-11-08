#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成数据单测：不含任何真实图纸数值。"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qty_core as q


def mk(i, txt, x, y, layer="X"):
    return (i, txt, layer, "TEXT", 1, x, y)


class Titles(unittest.TestCase):
    def test_real_title_needs_members_nearby(self):
        rows = [mk(0, "三层梁平法施工图", 0, 0), mk(1, "目录：三层梁平法施工图", 400000, 400000)]
        rows += [mk(i + 2, "KL%d" % i, 900 + i, 0) for i in range(12)]
        titles, info = q.find_titles(rows, min_refs=10, radius=20000)
        self.assertEqual([t["title"] for t in titles], ["三层梁平法施工图"])
        self.assertNotIn("目录：三层梁平法施工图", [t["title"] for t in titles])

    def test_no_title_returns_empty_not_crash(self):
        titles, info = q.find_titles([mk(0, "随便一段文字", 0, 0)], min_refs=10, radius=20000)
        self.assertEqual(titles, [])


class Grid(unittest.TestCase):
    def test_envelope(self):
        g = q.grid_geom("8x8000,6x7500")
        self.assertEqual((g["Lx_m"], g["Ly_m"], g["面积m2"]), (64.0, 45.0, 2880.0))

    def test_mixed_span_envelope(self):
        g = q.grid_geom("3x8400+2x7800,4x7500")
        self.assertEqual((g["Lx_m"], g["Ly_m"], g["面积m2"]), (40.8, 30.0, 1224.0))

    def test_one_direction_is_not_enough(self):
        self.assertIsNone(q.grid_geom("8x8000"))

    def test_auto_grid_keeps_mixed_spans(self):
        segs = []
        for x in (0, 8400, 16800, 24600, 32400):
            segs.append((x, 0, x, 30000, "AXIS"))
        for y in (0, 7500, 15000, 22500):
            segs.append((0, y, 32400, y, "AXIS"))
        grid, info = q.axis_grid(segs, (0, 0, 32400, 30000))
        self.assertEqual(grid, "2x8400+2x7800,3x7500")
        self.assertEqual(info["跨度序列x"], [[2, 8400], [2, 7800]])


class Volumes(unittest.TestCase):
    def test_slab_and_beam_split_by_band(self):
        members = {"柱": {}, "梁": {"KL1": {"code": "KL1", "n": 3, "positions": [(0, 0)], "b": 250, "h": 600,
                                            "thk": None, "spans": 2, "cant": "", "grades": [], "layers": ["L"], "raws": ["KL1 250x600"], "count": 3}},
                   "板": {"LB1": {"code": "LB1", "n": 2, "positions": [(0, 0)], "b": None, "h": None,
                                   "thk": 130, "spans": None, "cant": "", "grades": [], "layers": ["S"], "raws": ["LB1 h=130"], "count": 2}},
                   "墙": {}}
        rows, missing = q.volumes(members, 3800, "8x8000,6x7500")
        slab = [r for r in rows if r["构件类别"] == "板"][0]
        self.assertEqual(slab["混凝土m3"], 374.4)          # 2880㎡ × 0.13
        beam = [r for r in rows if r["构件类别"] == "梁"][0]
        self.assertGreater(beam["混凝土m3"], 0)

    def test_missing_grid_goes_to_clist_not_guessed(self):
        members = {"柱": {}, "梁": {}, "板": {"LB1": {"code": "LB1", "n": 1, "positions": [(0, 0)], "b": None,
                                                    "h": None, "thk": 130, "spans": None, "cant": "", "grades": [],
                                                    "layers": [], "raws": ["LB1 h=130"], "count": 1}}, "墙": {}}
        rows, missing = q.volumes(members, 3800, None)
        self.assertEqual(rows, [])
        self.assertTrue(any("缺轴网参数" in m[2] for m in missing))

    def test_column_uses_section_and_story(self):
        members = {"柱": {"KZ1": {"code": "KZ1", "n": 2, "positions": [(0, 0)], "b": 500, "h": 500, "thk": None,
                                  "spans": None, "cant": "", "grades": ["C35"], "layers": ["C"], "raws": ["KZ1 500x500"], "count": 2}},
                   "梁": {}, "板": {}, "墙": {}}
        rows, _ = q.volumes(members, 3800, "8x8000,6x7500")
        self.assertAlmostEqual(rows[0]["混凝土m3"], 1.9, places=2)   # 0.5×0.5×3.8×2
        self.assertIn("C35", rows[0]["标号"])


class Loss(unittest.TestCase):
    def test_order_qty_applies_loss(self):
        rows = [{"构件类别": "板", "标号": "C30", "混凝土m3": 100.0, "钢筋估算kg带": "8000~11000"}]
        plan = q.plan_rows(rows, loss=0.02)
        self.assertEqual(plan[0]["订货量m3"], 102.0)




class NormChecks(unittest.TestCase):
    """规范校核：只提示，不改量。"""

    def test_normal_column_passes_without_warning(self):
        row = q._row("柱", "KZ1", "500x500", 2, 1.9, "C35", False, "x", "L", "y")
        issues = q.norm_check([row])
        self.assertEqual(issues, [])
        self.assertEqual(row["规范校核"], "通过")

    def test_missing_grade_flags_without_default_C30(self):
        row = q._row("柱", "KZ1", "500x500", 2, 1.9, None, True, "x", "L", "y")
        issues = q.norm_check([row])
        self.assertEqual(row["标号"], "未标注（需核对）")
        self.assertTrue(any("混凝土强度等级未标注" in x["提示"] for x in issues))

    def test_abnormal_slab_thickness_flags(self):
        row = q._row("板", "板厚档 900mm", "900mm", 1, 9.0, "C30", False, "x", "-", "y")
        issues = q.norm_check([row])
        self.assertTrue(any("板厚 900mm" in x["提示"] for x in issues))
        self.assertIn("⚠️", row["规范校核"])

    def test_nonpositive_volume_flags(self):
        row = q._row("梁", "KL1", "250x600", 1, 0.0, "C30", False, "x", "-", "y")
        issues = q.norm_check([row])
        self.assertTrue(any("混凝土体积非正值" in x["提示"] for x in issues))

    def test_rule_references_include_catalogues(self):
        refs = q.RULES["规范引用"]["引用"]
        ids = {x["id"] for x in refs}
        self.assertIn("GB50500-2013", ids)
        self.assertIn("GB50854-2013", ids)
        self.assertIn("16G101-1", ids)
        self.assertIn("22G101-1", ids)
        self.assertTrue(q.RULES["规范校核"]["说明"].startswith("出量后校核"))

    def test_skill_cache_version_bumped(self):
        self.assertEqual(q.CACHE_VERSION, "0.4.0")
        self.assertRegex(q.RULES["version"], r"^\d+\.\d+\.\d+$")


class PourStrip(unittest.TestCase):
    """后浇带：断行拼接 → 说明摘录 → 封闭带拆分（全部合成数据）。"""

    def test_join_lines_reassembles_split_note(self):
        rows = [mk(0, "图", 0, 0, "TEXT"), mk(1, "中", 250, 0, "TEXT"),
                mk(2, "表示沉降后浇带，宽度均为", 500, 0, "TEXT"), mk(3, "800", 4200, 0, "TEXT"),
                mk(4, "无关文字", 0, 9000, "TEXT")]
        joined = q.join_lines(rows)
        hit = [t for t, _l in joined if "后浇带" in t]
        self.assertTrue(hit and "800" in hit[0], hit)

    def test_notes_facts_extracts_four_facts(self):
        rows = [mk(0, "1.图中符号表示沉降后浇带与温度后浇带，宽度均为1000。", 0, 0, "S-25文字附注"),
                mk(1, "2.后浇带采用高一级的微膨胀混凝土浇筑，保留时间不少于三个月。", 0, -500, "S-25文字附注")]
        f = q.notes_facts(rows, [])
        self.assertEqual(f["后浇带宽mm"]["值"], "1000")
        self.assertEqual(f["后浇带类型"]["值"], "沉降后浇带、温度后浇带")
        self.assertEqual(f["封闭用混凝土"]["值"], "高一级")
        self.assertEqual(f["保留时间"]["值"], "三")

    def test_box_hits_win_over_global_notes(self):
        g = [mk(0, "全图说明：伸缩后浇带，宽度均为800。", -9000, -9000, "TEXT"),
             mk(1, "本层标注：后浇带宽1200。", 1000, 1000, "TEXT")]
        self.assertEqual(q.notes_facts(g, [], box=(0, 0, 5000, 5000))["后浇带宽mm"]["值"], "1200")
        self.assertEqual(q.notes_facts(g, [])["后浇带宽mm"]["值"], "800")

    def test_bump_grade(self):
        self.assertEqual(q.bump_grade("C30"), "C35")
        self.assertEqual(q.bump_grade("C30（推定）"), "C35（推定）")
        self.assertEqual(q.bump_grade(""), "高一级（需按说明核对）（推定）")

    @staticmethod
    def _slab_rows():
        return [{"构件类别": "板", "编号/档位": "板厚档 130mm", "截面/尺寸": "130mm", "数量": 2,
                 "混凝土m3": 374.4, "标号": "C30（推定）", "钢筋估算kg带": "29952~41184",
                 "依据": "x", "图层": "-", "原文": "y"},
                {"构件类别": "板", "编号/档位": "板厚档 180mm", "截面/尺寸": "180mm", "数量": 1,
                 "混凝土m3": 180.0, "标号": "C35", "钢筋估算kg带": "14400~19800",
                 "依据": "x", "图层": "-", "原文": "y"}]

    def test_strip_split_conserves_volume(self):
        rows = self._slab_rows()
        before = sum(r["混凝土m3"] for r in rows)
        out, info = q.strip_split(rows, 100.0, 800.0, {"封闭用混凝土": {"原文": "采用高一级微膨胀混凝土"}}, "图面说明原文")
        band = [r for r in out if r["编号/档位"] == "后浇带封闭带"]
        self.assertEqual(len(band), 1)
        self.assertEqual(round(sum(r["混凝土m3"] for r in out), 2), round(before, 2))
        self.assertEqual(band[0]["标号"], "C35（推定）")    # 面积最大档=130mm/C30（推定）→ 高一级仍标推定
        self.assertEqual(info["面积m2"], 80.0)
        self.assertEqual(info["宽来源"], "图面说明原文")

    def test_manual_width_is_not_digit_mangled(self):
        # --strip-width-mm 传的是浮点 1000.0，去掉非数字会把小数点吃掉变成 10000
        self.assertEqual(q.parse_strip_width(1000.0), 1000.0)
        self.assertEqual(q.parse_strip_width("宽度均为800"), 800.0)
        self.assertIsNone(q.parse_strip_width(0))

    def test_no_slab_rows_no_strip(self):
        rows = [{"构件类别": "梁", "编号/档位": "截面档 250x600", "截面/尺寸": "250x600", "混凝土m3": 50.0,
                 "标号": "C30", "数量": 1, "钢筋估算kg带": "6000~9000", "依据": "", "图层": "", "原文": ""}]
        out, info = q.strip_split(rows, 100.0, 800.0, {}, "默认")
        self.assertIsNone(info)
        self.assertEqual(sum(r["混凝土m3"] for r in out), 50.0)


class StoryBasis(unittest.TestCase):
    """层高取段：报本层顶板浇筑 → 取板下面那段柱墙高，不是往上那一段。"""

    ROWS = [(0, "结构层高表", "T", "TEXT", 1, 0, 0),
            (1, "-0.050", "T", "TEXT", 1, 0, -100), (2, "5.40", "T", "TEXT", 1, 600, -100),
            (3, "5.350", "T", "TEXT", 1, 0, -600), (4, "4.20", "T", "TEXT", 1, 600, -600),
            (5, "9.550", "T", "TEXT", 1, 0, -1100), (6, "5.40", "T", "TEXT", 1, 600, -1100),
            (7, "14.950", "T", "TEXT", 1, 0, -1600)]
    TITLES = [{"title": "结构层高表", "x": 0, "y": 0, "refs": 99, "sheet": None}]

    def _story(self, label, basis="below"):
        return q.story_from_tables(self.ROWS, {}, label, self.TITLES, basis)

    def test_floor_at_9550_uses_storey_below(self):
        st, info = self._story("标高9.550梁平法施工图")
        self.assertEqual(st, 4200)                 # 9.550 − 5.350，即下面那段柱
        self.assertNotIn("需核对", info)            # 表注 4.20 与标高差一致 → 不乱报警
        self.assertEqual(info["下层标高"], 5.35)

    def test_top_floor_no_longer_fails(self):
        st, info = self._story("标高14.950板配筋图")
        self.assertEqual(st, 5400)                 # 顶层表内空白，但能与下层标高相减

    def test_label_span_wins_and_cross_checks(self):
        self.assertEqual(q.parse_label_span("标高5.350~9.550墙柱平法施工图"), 4200)
        self.assertEqual(q.parse_label_span("标高-0.050~5.350墙柱平法施工图"), 5400)
        self.assertIsNone(q.parse_label_span("基础顶标高~-0.050墙柱平法施工图"))
        self.assertIsNone(q.parse_label_span("标高9.550板配筋图"))
        st, info = self._story("标高5.350~9.550墙柱平法施工图")
        self.assertEqual(st, 4200)
        self.assertEqual(info["算法"], "图名自标区间差")
        self.assertNotIn("需核对", info)                 # 表内 5.350 行注 4.20 → 一致
        st2, info2 = self._story("标高9.550~14.950墙柱平法施工图")
        self.assertEqual((st2, info2.get("层高表核对")), (5400, 5400))

    def test_above_basis_still_available(self):
        self.assertEqual(self._story("标高9.550梁平法施工图", "above")[0], 5400)

    def test_mixed_zone_table_flags_for_check(self):
        rows = [(0, "层高表", "T", "TEXT", 1, 0, 0),
                (1, "-2.800", "T", "TEXT", 1, 0, -100), (2, "2.66", "T", "TEXT", 1, 600, -100),
                (3, "-0.060", "T", "TEXT", 1, 0, -600), (4, "5.50", "T", "TEXT", 1, 600, -600),
                (5, "-0.050", "T", "TEXT", 1, 0, -1100)]
        st, info = q.story_from_tables(rows, {}, "A区标高-0.050板配筋图",
                                        [{"title": "层高表", "x": 0, "y": 0, "refs": 99, "sheet": None}], "below")
        self.assertEqual(st, 2750)                 # 跳过 -0.06 这种 10mm 小数差
        self.assertIn("需核对", info)               # 2750 与表注 2660 不符 → 必须提示


class OpeningsAndRules(unittest.TestCase):
    """洞口扣减 + 口径指纹（合成数据）。"""

    def test_only_sized_openings_above_threshold_are_counted(self):
        rows = [mk(0, "JD5 720x300", 0, 0, "S-13暖通条件"),        # 0.216㎡ < 0.3 → 不扣
                mk(1, "KB1 1500x1500", 5000, 0, "S-13暖通条件"),   # 2.25㎡ → 扣
                mk(2, "JD6", 9000, 0, "S-13暖通条件"),             # 只编号无尺寸
                mk(3, "KL7 300x600", 12000, 0, "梁原位标注")]      # 不是洞口
        tot, items, naked = q.openings(rows)
        self.assertEqual(tot, 2.25)
        self.assertEqual(items, ["KB11500x1500=2.25㎡"])
        self.assertEqual(naked, 1)

    def test_same_opening_repeated_at_same_spot_once(self):
        rows = [mk(i, "KB1 1500x1500", 5000, 0, "S") for i in range(3)]
        self.assertEqual(q.openings(rows)[0], 2.25)

    def test_volumes_deduct_open_area(self):
        members = {"柱": {}, "梁": {}, "墙": {},
                   "板": {"LB1": {"code": "LB1", "n": 1, "positions": [(0, 0)], "b": None, "h": None,
                                   "thk": 100, "spans": None, "cant": "", "grades": [], "layers": [],
                                   "raws": ["LB1 h=100"], "count": 1}}}
        no_op = q.volumes(members, 3800, "10x8000,10x8000")[0]
        with_op = q.volumes(members, 3800, "10x8000,10x8000", open_area_m2=100.0)[0]
        slab0 = [r for r in no_op if r["构件类别"] == "板"][0]["混凝土m3"]
        slab1 = [r for r in with_op if r["构件类别"] == "板"][0]["混凝土m3"]
        self.assertEqual(round(slab0 - slab1, 2), 10.0)          # 100㎡ × 100mm
        self.assertIn("洞口", [r for r in with_op if r["构件类别"] == "板"][0]["依据"])

    def test_code_touching_size_does_not_swallow_digit(self):
        # 真图常见写法"XL4 600x800"：去空格后是 XL4600x800，旧正则会把截面读成 4600x800
        rows = [mk(0, "XL4 600x800", 0, 0, "梁原位标注"), mk(1, "KL7 300x600(2) 2Φ18", 4000, 0, "梁原位标注")]
        m, _pos = q.parse_members(rows)
        self.assertEqual((m["梁"]["XL4"]["b"], m["梁"]["XL4"]["h"]), (600, 800))
        self.assertEqual((m["梁"]["KL7"]["b"], m["梁"]["KL7"]["h"], m["梁"]["KL7"]["spans"]), (300, 600, 2))
        self.assertEqual(q.openings([mk(0, "JD5 720x300", 0, 0, "S")])[0], 0.0)   # 0.216㎡ 不扣

    def test_multi_annotated_size_takes_majority_and_flags(self):
        rows = [mk(0, "LB1 h=130", 0, 0, "S"), mk(1, "LB1 h=250", 4000, 0, "S"),
                mk(2, "LB1 h=250", 8000, 0, "S"), mk(3, "KL9 250x500", 0, 9000, "L"),
                mk(4, "KL9 300x600", 4000, 9000, "L"), mk(5, "KL9 300x600", 8000, 9000, "L")]
        m, _pos = q.parse_members(rows)
        self.assertEqual(m["板"]["LB1"]["thk"], 250)
        self.assertIn("130", m["板"]["LB1"]["conflict"])
        self.assertEqual((m["梁"]["KL9"]["b"], m["梁"]["KL9"]["h"]), (300, 600))
        self.assertIn("250x500", m["梁"]["KL9"]["conflict"])
        rows_out, _missing = q.volumes(m, 3800, "8x8000,6x8000")
        slab = [r for r in rows_out if r["构件类别"] == "板"][0]
        beam = [r for r in rows_out if r["构件类别"] == "梁"][0]
        self.assertIn("⚠️", slab["依据"])          # 多标注必须写在依据里，不能静默取一个
        self.assertIn("⚠️", beam["依据"])

    def test_rules_version_and_fingerprint_present(self):
        self.assertEqual(len(q.RULES_SHA), 8)
        self.assertRegex(q.RULES["version"], r"^\d+\.\d+\.\d+$")
        self.assertIn("洞口", q.RULES)
        self.assertIsInstance(q.RULES["起扣面积_m2"], float)      # 全表只留一个起扣面积
        refs = q.RULES["规范引用"]
        self.assertIn("知识库根", refs)
        self.assertTrue(any(x["id"].startswith("GB5500") for x in refs["引用"]))
        self.assertIn("22G101-3", [x["id"] for x in refs["引用"]])


class ProfileAndStory(unittest.TestCase):
    def test_profile_roundtrip(self):
        import tempfile, json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            q.save_profile(p, {"axis_grid": "8x8000,6x7500", "story_height_mm": 3800})
            got = q.load_profile(p)
            self.assertEqual(got["axis_grid"], "8x8000,6x7500")
            self.assertEqual(q.load_profile(Path(d) / "none"), {})

    def test_negative_elevation_label_parsed(self):
        rows = [(0, "结构层高表", "T", "TEXT", 1, 0, 0), (1, "-0.050", "T", "TEXT", 1, 0, -100),
                (2, "4.50", "T", "TEXT", 1, 400, -100), (3, "5.350", "T", "TEXT", 1, 0, -600)]
        titles = [{"title": "结构层高表", "x": 0, "y": 0, "refs": 99, "sheet": None}]
        story, info = q.story_from_tables(rows, {}, "A区标高-0.050板配筋图", titles)
        self.assertEqual(story, 4500)

    def test_window_box_clamps(self):
        hits = [{"title": "A", "x": 0, "y": 0}, {"title": "B", "x": 500000, "y": 0}]
        box = q.window_box(hits[:1], hits, lo=20000, hi=60000)
        self.assertEqual(int(box[0]), -60000)

class ScheduleBind(unittest.TestCase):
    """表格绑定：墙身表按表头列名取墙厚；柱表取不到时人工给一次尺寸。合成数据。"""

    def _members(self):
        return {"柱": {"KZ1": {"code": "KZ1", "n": 1, "positions": [(0, 0)], "b": None, "h": None, "thk": None,
                             "spans": None, "cant": "", "grades": [], "layers": ["COLU_NUM"], "raws": ["KZ1"], "count": 4}},
                "梁": {}, "板": {},
                "墙": {"Q2": {"code": "Q2", "n": 1, "positions": [(0, 0)], "b": None, "h": None, "thk": None,
                               "spans": None, "cant": "", "grades": [], "layers": ["墙身名称编号"], "raws": ["Q2"], "count": 2}}}

    def test_parse_member_size(self):
        got = q.parse_member_size("KZ1=500x900, Q2=250；LZ3=600×600 乱写的")
        self.assertEqual(got["KZ1"], (500, 900))
        self.assertEqual(got["Q2"], 250)
        self.assertEqual(got["LZ3"], (600, 600))
        self.assertEqual(q.parse_member_size(""), {})

    def test_apply_member_size_fills_only_what_is_missing(self):
        m = self._members()
        n = q.apply_member_size(m, q.parse_member_size("KZ1=500x900,Q2=250"), "人工参数")
        self.assertEqual((m["柱"]["KZ1"]["b"], m["墙"]["Q2"]["thk"], n), (500, 250, 2))
        self.assertEqual(q.apply_member_size(m, q.parse_member_size("KZ1=999x999"), "人工参数"), 0)  # 已有就不覆盖
        self.assertIn("人工参数", m["柱"]["KZ1"]["src"])

    def test_label_range_and_match(self):
        self.assertEqual(q.label_range("标高5.350~9.550墙柱平法施工图"), "5.350~9.550")
        self.assertIsNone(q.label_range("三层板配筋图"))
        self.assertTrue(q.same_range("5.350~9.550", "5.35~9.55"))
        self.assertFalse(q.same_range("5.350~9.550", "9.550~14.950"))

    def test_wall_table_header_driven_bind(self):
        y0 = 0
        rows = [mk(0, "编 号", 0, y0, "NOTE"), mk(1, "标 高", 4000, y0, "NOTE"), mk(2, "墙 厚", 8000, y0, "NOTE")]
        rows += [mk(3, "Q2", 0, y0 - 800, "NOTE"), mk(4, "5.350~9.550", 4000, y0 - 800, "NOTE"),
                 mk(5, "200", 8000, y0 - 800, "NOTE")]
        rows += [mk(6, "Q3", 0, y0 - 1600, "NOTE"), mk(7, "9.550~14.950", 4000, y0 - 1600, "NOTE"),
                 mk(8, "300", 8000, y0 - 1600, "NOTE")]
        m = self._members()
        m["墙"]["Q3"] = {"code": "Q3", "n": 1, "positions": [(0, 0)], "b": None, "h": None, "thk": None,
                          "spans": None, "cant": "", "grades": [], "layers": ["墙身名称编号"], "raws": ["Q3"], "count": 1}
        n, tbl_ids, notes = q.schedule_bind(m, rows, q.label_range("标高5.350~9.550墙柱平法施工图"))
        self.assertEqual(m["墙"]["Q2"]["thk"], 200)
        self.assertIsNone(m["墙"]["Q3"]["thk"])                 # 本层图名区间之外的那一行不取
        self.assertTrue(n >= 1)
        self.assertIn("表头列名对上", m["墙"]["Q2"]["src"])
        self.assertTrue(any("不符" in x for x in notes))        # 别层的 Q3 行被挡下
        self.assertNotIn(8, tbl_ids)                            # 未取用的行不进排除集


class BaseAndNormative(unittest.TestCase):
    """底座入口与规范辅助只做集成入口，不访问真实图纸。合成数据。"""

    def test_base_script_uses_cad_skill_dir_and_reports_missing(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            script = base / 'scripts' / 'cad_normative.sh'
            script.parent.mkdir()
            script.touch()
            with patch.dict(os.environ, {'CAD_SKILL_DIR': str(base)}):
                self.assertEqual(q.base_script('cad_normative.sh'), script)
                empty = base / 'empty'
                empty.mkdir()
                with patch.dict(os.environ, {'CAD_SKILL_DIR': str(empty)}):
                    with self.assertRaises(SystemExit):
                        q.base_script('cad_normative.sh')

    def test_run_normative_without_scan_returns_false(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(q.run_normative(Path(d)))

    def test_run_measurement_without_detail_returns_false(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(q.run_measurement_candidates(Path(d)))

    def test_measurement_missing_script_does_not_block(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / 'detail.json').write_text('{}', encoding='utf-8')
            base = out / 'base'
            base.mkdir()
            with patch.dict(os.environ, {'CAD_SKILL_DIR': str(base)}):
                self.assertFalse(q.run_measurement_candidates(out))

    def test_run_normative_success_and_failure_do_not_block(self):
        import os
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / 'scan.json').write_text('{}', encoding='utf-8')
            (out / 'detail.json').write_text('{}', encoding='utf-8')
            base = out / 'base'
            script = base / 'scripts' / 'cad_normative.sh'
            script.parent.mkdir(parents=True)
            script.touch()
            with patch.dict(os.environ, {'CAD_SKILL_DIR': str(base)}):
                with patch.object(q.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='')) as run:
                    self.assertTrue(q.run_normative(out))
                    args = run.call_args.args[0]
                    # 通过 bash 启动，不依赖 .sh 的执行位（SkillHub 打包会丢失执行位）
                    self.assertEqual(args[0], "bash")
                    self.assertEqual(args[1], str(script))
                    self.assertIn('--detail', args)
                with patch.object(q.subprocess, 'run', return_value=SimpleNamespace(returncode=2, stderr='line1\n底座辅助不可用')):
                    self.assertFalse(q.run_normative(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
