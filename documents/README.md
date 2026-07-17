# Pax3D Documents Index

Status legend: **CURRENT** = maintained, trust it · **REFERENCE** = valid,
rarely changes · **HISTORICAL** = kept for context; findings may be
superseded — check the banner at the top of each file.

| Document | Status | What it is |
|---|---|---|
| `PAX3D_MASTER_PLAN.md` | **CURRENT** | **v3 (2026-07-17):** verified state, policies in force (sovereignty, Language Canon, build windows), established facts, the road forward. Start here. |
| `SESSION_LOG.md` | **CURRENT** | Session-by-session narrative (extracted from Master Plan v2), newest at the bottom. |
| `PAX3D_RENDER_ARCHITECTURE.md` | **CURRENT** | Maintainer's guide to the pax3d_render pipeline: passes, sun modes, shadows (incl. the bias trap §5.1), invariants, defect analysis, API. |
| `ENGINE_SURGERY_PLAN.md` | **CURRENT** | The deletion program. **Windows 2+3 executed 2026-07-17** (DX9 + dead backends gone, −35k lines); Window 4 (mobile-target extraction) queued. |
| `BUILD_WINDOW_1_CATCHUP.md` | HISTORICAL — completed | Window 1 procedure. Built, fully validated and signed off 2026-07-17; kept for reference. |
| `OPENWORLD_FEEDBACK_RESPONSE.md` | **CURRENT** | Round 1 (Session E): P0 root cause (bias trap + contaminated instrument), landed APIs, backlog. |
| `OPENWORLD_FEEDBACK_RESPONSE_2.md` | **CURRENT** | Round 2 (Session F): the evening P0 verdict (contaminated engine tree, not a regression), the real skinning P1 queued, planetary-track policy. |
| `OPENWORLD_FEEDBACK_RESPONSE_3.md` | **CURRENT** | Round 3 (Session G): both asks landed (assertion + glTF caster/receiver test), P1 concertina not reproducible on the clean engine (re-measurement requested), per-node `set_hardware_skinning()` delivered. |
| `OPENWORLD_FEEDBACK_RESPONSE_4.md` | **CURRENT** | Round 4 (Session I): the P0 addendum (direction-gated vanishing shadows) root-caused as grazing-angle acne (fact 14); slope-scaled bias (`shadow_normal_bias_world`) landed opt-in, gated, proven on the village GLB; in-app A/B requested. |
| `HANDOVERS/handover_session_f_windows_1-3.md` | HISTORICAL — superseded | Session F handover: builds/validation/deletions, machine migration. |
| `HANDOVERS/handover_session_g_hardening_skinning.md` | **CURRENT** | Session G handover: paxtest hardening, the P1 verdict, per-node skinning API, next-session priorities. |
| `PAXTEST_FINDINGS_SESSION_A.md` | **CURRENT** | The harness findings that rebooted the program (double-gamma disproven, DirectionalLight exonerated, bloom defect cornered). |
| `../tools/paxtest/README.md` | **CURRENT** | Test harness usage and results snapshot. |
| `BUILDING_PAX3D.md` | REFERENCE | Building the engine wheel from source — thirdparty setup, every pitfall, build-window policy note. |
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
