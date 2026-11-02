# lis-cad-skills

建筑工程识图、几何提取、跨专业复核与算量技能集（8 个）。本机运行、不联网、不上传图纸；输出是带证据坐标、置信度和复核标记的候选结果，不是最终结算结论。

| 技能 | 版本 | 许可 | 用途 |
|---|---|---|---|
| `cad-file-reader` | 0.39.4 | CC-BY-NC-SA-4.0 | CAD/PDF 识图与证据提取（DWG/DXF/DWT/PDF） |
| `cad-suite` | 0.3.1 | CC-BY-NC-SA-4.0 | 识图、关系推断、聚合与跨专业复核编排 |
| `cad-clash-check` | 0.3.1 | CC-BY-NC-SA-4.0 | 跨专业 2D 碰撞与属性冲突候选 |
| `zhuangshi-suanliang` | 0.9.30 | CC-BY-NC-SA-4.0 | 装饰算量 · 概算与物资计划 |
| `anzhuang-suanliang` | 0.4.32 | CC-BY-NC-SA-4.0 | 安装算量 |
| `tujian-suanliang` | 0.9.38 | CC-BY-NC-SA-4.0 | 土建算量（混凝土/钢筋） |
| `yuanlin-suanliang` | 0.4.34 | CC-BY-NC-SA-4.0 | 园林景观算量 |
| `lis-skill-bus` | 0.1.7 | MIT | 技能间共享识图状态与证据契约 |

## 许可要点

5 个算量/识图技能以 **CC-BY-NC-SA-4.0** 授权：

- ✅ 可自由使用与改造
- ❌ **仅限非商业用途**（个人学习、研究、非营利使用）
- 改造后若公开发布，须以相同条款授权
- **企业、机构用于经营性项目（如承接造价/算量业务）需另行取得作者书面授权**

作者（lis）作为著作权人保留全部商业使用权、再发布权与对外授权权。

`lis-skill-bus` 为 MIT，作为基础设施可自由使用。

## 英文说明

`cad-file-reader`、`cad-suite`、`cad-clash-check` 和四个算量技能提供 `README.en.md`；`lis-skill-bus` 也已补齐英文说明。英文层只覆盖安装、能力边界、输入输出和复核提示，算法层与中文版一致。

## 使用

各技能目录下有 `SKILL.md`，安装到你的 skills 目录即可：

```bash
cp -R cad-file-reader ~/.workbuddy/skills/
```

`cad-file-reader` 在 SkillHub 轻量包下需先装依赖：

```bash
bash scripts/setup.sh
```

## 发布

见 `publish_all.sh`，支持 5 个平台（SkillHub / ClawHub / GitHub / WorkBuddy / Codex）。
其中外部平台需先完成交互式认证。
