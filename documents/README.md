# Pax3D Documents Index

Status legend: **CURRENT** = maintained, trust it · **REFERENCE** = valid,
rarely changes · **HISTORICAL** = kept for context; findings may be
superseded — check the banner at the top of each file.

| Document | Status | What it is |
|---|---|---|
| `PAX3D_MASTER_PLAN.md` | **CURRENT** | **v3 (2026-07-17):** verified state, policies in force (sovereignty, Language Canon, build windows), established facts, the road forward. Start here. |
| `SESSION_LOG.md` | **CURRENT** | Session-by-session narrative (extracted from Master Plan v2), newest at the bottom. |
| `PAX3D_RENDER_ARCHITECTURE.md` | **CURRENT** | Maintainer's guide to the pax3d_render pipeline: passes, sun modes, shadows (incl. the bias trap §5.1), invariants, defect analysis, API. |
| `ENGINE_INTERNALS.md` | **CURRENT** | **How the engine works deep down, measured** (started Session U): texture-pipeline degradation paths, ShaderAttrib/multi-pass state resolution, the full hardware-instancing chain, GLSL version notes, instrument traps. Every entry cites source lines and/or the gating paxtest. Add to it whenever you dig a mechanism out of the C++. |
| `ENGINE_SURGERY_PLAN.md` | **CURRENT** | The deletion program. **Windows 2+3+4 executed** (DX9 + dead backends + mobile machinery gone, −43k lines; Window 4 `c627e2d0bc`, 2026-07-19); remaining R6 = Vulkan watch only. |
| `PAX3D_VR_PLAN.md` | **CURRENT — lane PARKED 2026-07-27** | The VR lane: Quest 2 seated PCVR via OpenXR + SteamVR runtime (only runtime with GL — verified live). Direction + dev-machine bring-up done; VR0 spike not started. §0 = resume checklist. |
| `BUILD_WINDOW_1_CATCHUP.md` | HISTORICAL — completed | Window 1 procedure. Built, fully validated and signed off 2026-07-17; kept for reference. |
| `OPENWORLD_FEEDBACK_RESPONSE.md` | **CURRENT** | Round 1 (Session E): P0 root cause (bias trap + contaminated instrument), landed APIs, backlog. |
| `OPENWORLD_FEEDBACK_RESPONSE_2.md` | **CURRENT** | Round 2 (Session F): the evening P0 verdict (contaminated engine tree, not a regression), the real skinning P1 queued, planetary-track policy. |
| `OPENWORLD_FEEDBACK_RESPONSE_3.md` | **CURRENT** | Round 3 (Session G): both asks landed (assertion + glTF caster/receiver test), P1 concertina not reproducible on the clean engine (re-measurement requested), per-node `set_hardware_skinning()` delivered. |
| `OPENWORLD_FEEDBACK_RESPONSE_4.md` | **CURRENT** | Round 4 (Session I): the P0 addendum (direction-gated vanishing shadows) root-caused as grazing-angle acne (fact 14); slope-scaled bias (`shadow_normal_bias_world`) landed opt-in, gated, proven on the village GLB; in-app A/B requested. |
| `OPENWORLD_FEEDBACK_RESPONSE_5.md` | **CURRENT** | Round 4 addenda (Session Q): P2 core-profile combine drop diagnosed (expected upstream default-shader behavior; probe_texturestage; the requested warning LANDED in Session R, `857b715086`); sh_from_cubemap face table pinned end-to-end; Mars adoption lessons folded into the look guide; west-sun P0 fix re-pointed at the planetside team; GGX prefilter tool announced. |
| `PLANETSIDE_LOOK_GUIDE.md` | **CURRENT** | Session J planetside package field guide: aerial haze, hemisphere/SH ambient, shadow texel snapping — APIs, Mars starting values, tuning loops, the opt-out contract for spaceflight. |
| `BAKED_EFFECTS_GUIDE.md` | **CURRENT** | Session AD VFX-lane field guide: baked explosion footage end-to-end — pack intake facts (premultiplied, measured), gen_flipbook baking levers, `spawn_effect()` API + guarantees, the planetside adoption pattern, retune levers and watch list. |
| `WALKABLE_INTERIOR_COLLISION_DESIGN.md` | **CURRENT** | Session N joint design (engine × ship dev), AGREED: hidden collision subtree + traverser contract for walking inside ships; 7 measured engine facts (probe_walkmesh.py), ramp/door collision-on-animated-parts pattern, walk-mode loop. Implementation game-side. |
| `HANDOVERS/handover_session_s_adoption_wave.md` | **CURRENT** | **The live handover.** R5 is COMPLETE (lens flare landed Session S) and the walkable-ship interior package + character-class spikes are in — the engine is ahead of its content. Next session = field triage (pusher/interior/character adoption), testbed keys for the Session-S features, watches. Gate totals now 54/6/69. |
| `HANDOVERS/handover_session_r_adoption_and_polish.md` | HISTORICAL — executed | Session R handover, fully executed by Session S: field quiet, docs trued up, the Phobos dev's four asks answered (two by measurement, two by landed features), lens flare/dirt landed (R5 finale), plus SSAO and the character-class spikes from the user's expanded mandate. |
| `HANDOVERS/handover_session_q_field_and_spaceflight.md` | HISTORICAL — executed | Session Q handover, fully executed by Session R: field quiet, R5.5 orbital scattering landed (test_orbital), worked skybox example shipped (gen_equirect_cubemap + 006_Sunset sample), sRGB experiment landed gated (test_srgb, ACES verdict verified), plus the queued combine-mode C++ warning in a user-authorized mini-window. Its Stream-A field-triage list remains the live reference for adoption reports. |
| `HANDOVERS/handover_sessions_k_p_walkable_ship.md` | HISTORICAL — executed | Sessions K–P: the walkable-ship program — glass, double-sided, ambient scale, specular IBL + real BRDF LUT, collision design + field triage, local + authored lights, expanded-map haze root-cause. Its queue items #2 (GGX prefilter tool) and #3 (sh_from_cubemap file orientation) executed in Session Q; #1 (field follow-ups) is a standing rule carried into the Q handover; #4–#7 carried forward. |
| `HANDOVERS/handover_session_j_planetside.md` | HISTORICAL — executed | Session J handover: planetside package landed; its priorities (field tuning carried forward, sh_from_cubemap orientation half-closed in Session M, specular IBL executed in Session M) are superseded by the K–P handover. |
| `HANDOVERS/handover_session_i_grazing_bias_landed.md` | HISTORICAL — executed | Session I handover: slope-scaled bias landed; its item #3 (texel snapping) executed in Session J; items #1/#2 (openworld A/B, normal-offset contingency) carried forward in the J handover. |
| `HANDOVERS/handover_session_h_shadow_grazing_bias.md` | HISTORICAL — executed | Session H plan for the grazing-angle fix (executed in Session I). |
| `HANDOVERS/handover_session_g_hardening_skinning.md` | HISTORICAL — superseded | Session G handover: paxtest hardening, the P1 verdict, per-node skinning API. |
| `HANDOVERS/handover_session_f_windows_1-3.md` | HISTORICAL — superseded | Session F handover: builds/validation/deletions, machine migration. |
| `HANDOVERS/handover_session_d2_r4_logdepth.md` | HISTORICAL — superseded | Session D2 handover: R4 acceptance tests + log depth. |
| `HANDOVERS/handover_session_d_bloom_fix.md` | HISTORICAL — superseded | Session D handover: the F3 bloom root-cause fix. |
| `HANDOVERS/handover_session_c_directional_sun.md` | HISTORICAL — superseded | Session C handover: the directional sun + shadows landing. |
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
