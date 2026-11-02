#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross ↔ cad-clash-check 一致性（parity）测试。

钉住一件事：跨专业校对的实现只有一份。
cad-suite/cross 自 0.2.4 起只做转发，唯一实现在 cad-clash-check。
本测试独立加载 clash 侧源码（不经 bridge 缓存），与 cross 侧逐一比对，
任何一侧再长出自己的实现都会在这里红。
"""
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


def _sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

CROSS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CROSS))

import clash_bridge as cb  # noqa: E402
import engine  # noqa: E402
import adapt  # noqa: E402


def _load_independent(name: str):
    """绕开 bridge 缓存，独立加载 clash 侧源码。"""
    d = cb.find_clash_scripts()
    if d is None:
        raise unittest.SkipTest("本机未安装 cad-clash-check")
    path = d / f"{name}.py"
    mod_name = f"_parity_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


DETAIL = {
    "source_file": "t.detail.municipal.json",
    "grids": [{"type": "axis", "value": "A", "x": 100.0, "y": 0.0, "sheet": 1}],
    "members": [],
    "components": [
        {"name": "阀门DN100", "x": 100.0, "y": 200.0, "sheet": 1,
         "system": "water", "pipe_size": "DN100"},
        # 设计说明句：长度>10 且含说明特征 → 必须被剔除（真图教训：千级伪碰撞）
        {"name": "截水暗沟接市政雨水管网做法见详图", "x": 100.0, "y": 200.0,
         "sheet": 1},
    ],
    "municipal_geometry": [
        {"system": "sewage", "category": "pipe",
         "geometry": [0, 0, 1000, 500], "sheet": 1},
    ],
    "entities": [
        {"etype": "CIRCLE", "category": "valve",
         "x": 100.0, "y": 200.0, "sheet": 1},
    ],
}

TYPES = ["members", "components", "municipal_geometry", "entities"]


class TestDiscovery(unittest.TestCase):
    def test_clash_check_discoverable(self):
        d = cb.find_clash_scripts()
        self.assertIsNotNone(d, "本机应能探测到 cad-clash-check")
        self.assertTrue((d / "clash_engine.py").is_file())
        self.assertTrue((d / "clash_adapt.py").is_file())

    def test_missing_dependency_raises_not_silent(self):
        """找不到依赖必须报错，绝不静默回退到自己的副本。"""
        saved = cb.find_clash_scripts
        sys.modules.pop("_clash_bridge_clash_engine", None)
        sys.modules.pop("_clash_bridge_clash_adapt", None)
        cb.find_clash_scripts = lambda: None
        try:
            with self.assertRaises(RuntimeError):
                cb.require_clash_scripts()
        finally:
            cb.find_clash_scripts = saved


class TestEngineParity(unittest.TestCase):
    def test_engine_points_to_single_source(self):
        src = engine.engine_source()
        self.assertEqual(src.name, "clash_engine.py")
        self.assertIn("cad-clash-check", str(src))

    def test_cross_has_no_local_implementation(self):
        """cross/engine.py 必须是转发层，不得再长出自有实现。"""
        txt = (CROSS / "engine.py").read_text(encoding="utf-8")
        self.assertNotIn("class CrossEngine:", txt)
        self.assertNotIn("def norm_grid(", txt)
        txt_a = (CROSS / "adapt.py").read_text(encoding="utf-8")
        self.assertNotIn("def _nearest_axis(", txt_a)

    def test_engine_symbols_identical(self):
        ref = _load_independent("clash_engine")
        # 同源码可被加载两次，类对象身份必然不同 —— 钉源码字节，不钉对象身份
        self.assertEqual(_sha256(engine.engine_source()),
                         _sha256(Path(ref.__file__)),
                         "cross 侧与 clash 侧的实现源码必须逐字节相同")
        self.assertEqual(engine.CrossEngine.PLACE_TOL, ref.CrossEngine.PLACE_TOL)
        a = engine.Member("P", "1", "A-C/1-3", "KL1", "梁", attrs={"截面": "300x600"})
        b = ref.Member("P", "1", "A-C/1-3", "KL1", "梁", attrs={"截面": "300x600"})
        self.assertEqual(a.key, b.key)
        self.assertEqual(engine.norm_grid("a~c／1~3"), ref.norm_grid("a~c／1~3"))

    def test_compare_result_identical(self):
        ref = _load_independent("clash_engine")
        mk = lambda M: [  # noqa: E731
            M("P", "8.600", "A-C/1-3", "KL1", "梁", attrs={"截面": "300x600"},
              bbox=[0, 0, 100, 100]),
            M("P", "8.600", "A-C/1-3", "Z1", "柱", attrs={"截面": "500x500"},
              bbox=[0, 0, 100, 100]),
        ]
        ra = engine.CrossEngine().compare(mk(engine.Member), mk(engine.Member)[:1])
        rb = ref.CrossEngine().compare(mk(ref.Member), mk(ref.Member)[:1])
        self.assertEqual(ra.counts(), rb.counts())
        self.assertEqual([i["key"] for i in ra.items], [i["key"] for i in rb.items])


class TestAdaptParity(unittest.TestCase):
    def test_adapt_output_identical(self):
        ref = _load_independent("clash_adapt")
        got = adapt.adapt(DETAIL, "某项目", TYPES)
        want = ref.adapt(DETAIL, "某项目", TYPES)
        self.assertEqual(json.dumps(got, ensure_ascii=False, sort_keys=True),
                         json.dumps(want, ensure_ascii=False, sort_keys=True))

    def test_entity_channel_reaches_suite(self):
        """0.1.3 的 entity 通道必须已到达 cad-suite 侧（曾经的漂移点）。"""
        cl = adapt.adapt(DETAIL, "某项目", TYPES)
        kinds = {m.get("kind") for m in cl["members"]}
        self.assertIn("entity", kinds)
        self.assertIn("line", kinds)
        self.assertIn("label", kinds)

    def test_geometry_bbox_not_degenerate(self):
        cl = adapt.adapt(DETAIL, "某项目", TYPES)
        line = [m for m in cl["members"] if m.get("kind") == "line"]
        self.assertEqual(len(line), 1)
        self.assertEqual(line[0]["bbox"], [0, 0, 1000, 500])

    def test_note_sentence_filtered(self):
        cl = adapt.adapt(DETAIL, "某项目", TYPES)
        names = [m["name"] for m in cl["members"]]
        self.assertIn("阀门DN100", names)
        self.assertNotIn("截水暗沟接市政雨水管网做法见详图", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
