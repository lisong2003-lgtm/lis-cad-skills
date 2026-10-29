# lis-cad-skills

建筑工程识图与算量技能集（6 个），本机运行、不联网、不上传图纸。

| 技能 | 版本 | 许可 | 用途 |
|---|---|---|---|
| `cad-file-reader` | 0.38.1 | CC-BY-NC-SA-4.0 | CAD/PDF 识图与证据提取（DWG/DXF/DWT/PDF） |
| `zhuangshi-suanliang` | 0.9.26 | CC-BY-NC-SA-4.0 | 装饰算量 · 概算与物资计划 |
| `anzhuang-suanliang` | 0.4.25 | CC-BY-NC-SA-4.0 | 安装算量 |
| `tujian-suanliang` | 0.9.27 | CC-BY-NC-SA-4.0 | 土建算量（混凝土/钢筋） |
| `yuanlin-suanliang` | 0.4.29 | CC-BY-NC-SA-4.0 | 园林景观算量 |
| `lis-skill-bus` | 0.1.5 | MIT | 技能间共享识图状态（通信总线） |

## 许可要点

5 个算量/识图技能以 **CC-BY-NC-SA-4.0** 授权：

- ✅ 可自由使用与改造
- ❌ **仅限非商业用途**（个人学习、研究、非营利使用）
- 改造后若公开发布，须以相同条款授权
- **企业、机构用于经营性项目（如承接造价/算量业务）需另行取得作者书面授权**

作者（lis）作为著作权人保留全部商业使用权、再发布权与对外授权权。

`lis-skill-bus` 为 MIT，作为基础设施可自由使用。

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
