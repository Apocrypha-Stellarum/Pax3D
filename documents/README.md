# Pax3D Documents Index

Status legend: **CURRENT** = maintained, trust it · **REFERENCE** = valid,
rarely changes · **HISTORICAL** = kept for context; findings may be
superseded — check the banner at the top of each file.

| Document | Status | What it is |
|---|---|---|
| `PAX3D_MASTER_PLAN.md` | **CURRENT** | The phased rendering program (R0–R6), root-cause register, session updates. Start here. |
| `PAX3D_RENDER_ARCHITECTURE.md` | **CURRENT** | Maintainer's guide to the pax3d_render pipeline: passes, sun modes, shadows, invariants, defect analysis, API. |
| `PAXTEST_FINDINGS_SESSION_A.md` | **CURRENT** | The harness findings that rebooted the program (double-gamma disproven, DirectionalLight exonerated, bloom defect cornered). |
| `../tools/paxtest/README.md` | **CURRENT** | Test harness usage and results snapshot. |
| `BUILDING_PAX3D.md` | REFERENCE | Building the engine wheel from source — thirdparty setup, every pitfall. |
| `SWITCHING_ENGINES.md` | REFERENCE | The two-environment setup (stock Panda3D vs Pax3D venv). |
| `TOBSPR_SHADER_CATALOGUE.md` | REFERENCE | Salvageable shaders from tobspr's RenderPipeline (feeds R3–R5). |
| `RENDERING_ROADMAP.md` | HISTORICAL | The Feb 2026 five-phase plan. Superseded by the master plan. |
| `DIRECTIONAL_LIGHTING_PLAN.md` | HISTORICAL | Deep analysis of the 2025-26 lighting saga (Formula B/C). The API analysis (§2) is still educational; the "engine bug" framing is disproven. |
| `LIGHTING_AND_BLOOM_SYSTEM.md` | HISTORICAL | March 2026 description of pax3d_simplepbr — a package now retired. |
| `HOW_TO_USE_PAX3D_LIGHTING.md` | HISTORICAL | March 2026 usage guide for pax3d_simplepbr. Superseded by the game repo's `USING_PAX3D_RENDER.md`. |
| `LIGHTING_CHANGE_PLAN.md` | HISTORICAL | Session 459 plan + retrospective (the effort that taught us to build the harness). |
| `lighting mods discussion.txt` | HISTORICAL | Raw Session 459 transcript. |

Game-side documentation lives in the game repo:
`C:\python\sfb2\documents\PAX_3D_ENGINE_AND_GRAPHICS\` — most importantly
`USING_PAX3D_RENDER.md` (how the game uses this engine's pipeline).
