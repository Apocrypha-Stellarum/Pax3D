# CLAUDE.md — Pax3D Engine (Panda3D Fork + Rendering Stack)

Welcome, Claude! This is **Pax3D**: a fork of the Panda3D game engine plus a
first-party rendering stack, built for the Pax Abyssi space simulation.

> **This is an engine project, not a game project.** The game lives at
> `C:\python\sfb2` (it has its own CLAUDE.md). This repo contains:
> 1. The Panda3D C++ engine source (buildable to a wheel),
> 2. **`pax3d_render/`** — the unified Python/GLSL rendering pipeline (the
>    center of gravity of current work),
> 3. **`tools/paxtest/`** — the offscreen graphics test harness that gates
>    all rendering changes.

---

## Games Served (priority order) & Feedback Channels

Pax3D now serves TWO shipping games plus historical testbeds. Engine
devs receive feature requests from all of them — this is by design
(user-ratified 2026-07-27).

| Priority | Game | Where | Channel |
|---|---|---|---|
| 1 | **Pax Abyssi** (space sim — the reason this engine exists) | `C:\python\sfb2` | `sfb2/documents/ENGINE_REQUESTS/` (numbered ERs) + engine-update notes written back into `sfb2/documents/`; per-lane consults in the master plan session log |
| 2 | **Animal Crossfire** (Minecraft-style voxel game, dir/package `paxcraft`) | `C:\python\paxcraft` | **`C:\python\paxcraft\docs\ENGINE_NOTES.md`** — they file asks/reports there; the engine dev REPLIES INLINE in the same file (the bind_thread exchange set the pattern). Engine-side record: master plan session log + this file's status table |
| — | openworld (ITHappy walking sim, historical testbed) | `C:\python\openworld` | `PAX3D_FEEDBACK.md` (repo root) — dormant but the character lane still posts there |

**The voxel game's standing:** started 2026-07 as a proof-of-concept to
stress the engine (chunk streaming, threaded meshing, bulk scene churn)
and it earned its keep immediately — the bind_thread dangle fix, the
GVAD stability envelope, and the Session-AJ trio all came from its
field reports. **Space sim first**, always — but treat voxel asks
seriously: they have consistently played straight into planetside
requirements. That is the **concordance policy**: when either game asks
for a capability, prefer a shape the other gets for free (photo mode ↔
kill-cam; streaming detail maps ↔ terrain chunks; visibility loudness ↔
flare correctness). The user will also relay messages to/from the
paxcraft AI dev team directly on request.

---

## Read These First

| Priority | Document | What it gives you |
|---|---|---|
| 1 | `documents/PAX3D_MASTER_PLAN.md` | The phased program (R0–R6), root-cause register, session log. **The current plan.** |
| 2 | `documents/PAX3D_RENDER_ARCHITECTURE.md` | How pax3d_render works: passes, sun modes, shadows, invariants, API. |
| 3 | `tools/paxtest/README.md` | How to run and extend the test harness. |
| 4 | `documents/README.md` | Index of all docs with current/historical status. |

For using the pipeline from the game side, the guide lives in the game repo:
`C:\python\sfb2\documents\PAX_3D_ENGINE_AND_GRAPHICS\USING_PAX3D_RENDER.md`.

---

## Project Status (July 2026)

The rendering program runs in gated phases (see the master plan):

| Phase | Content | Status |
|---|---|---|
| R0 | paxtest harness | **DONE** — gates everything below |
| R1 | Unified renderer (`pax3d_render`), color contract, camera registration | **Core done; sRGB flip USER-APPROVED + WIRED 2026-07-23** (Session R experiment → approval: testbed A/B mechanically verified, ACES-vs-Hejl judged subtle-not-worse; `srgb_inputs` settings key ON + boot re-walk wired game-side, uncommitted; parity signed off same session). Core flip LANDED 2026-07-23 (every entry point sets `gl-version 3 2`), "core signed off" same day, and **R1.4 EXECUTED (Session AC): the GLSL-120 dual path is DELETED** — all 16 shader sources native GLSL 330, shaderutils transform + IS_WEBGL removed, compat contexts warn loudly (diagnostic only). **Gate redefined: both engines × ONE `game` baseline (= gl 3 2); `modern` = legacy alias, `compat` = diagnostic. Canonical totals at the redefinition Pax3D 70/7/106 · stock 68/7/108 — identical to the historical @modern column, FAIL sets unchanged (current totals: GVAD window 2026-07-24 +gvad_churn → 82/7/129 · 80/7/131).** **R1 IS CLOSED** |
| R2 | Real DirectionalLight sun + shadows | **DONE — user sign-off 2026-07-23** ("directional signed off"; settings have run directional+shadows since the planetside era). Watch item, not blocking: shadow STRIPES at certain angles reported in planetside, not reproducible in testbed — capture sun az/el on recurrence; first levers `shadow_normal_bias_world` (fact 14) + testbed shadow instruments (keys 10–16) |
| R3 | Bloom fixed + HDR polish | **Core done (Session D).** F3 fixed (8-bit intermediate FBOs were the root cause), test_bloom green everywhere. Remaining: content retune (strength/intensity/tints), light units, auto-exposure stretch |
| R4 | Log depth, camera-relative rendering, single camera | **Log depth landed opt-in (Session D)** — `enable_log_depth`, acceptance row `scale @logdepth` green. Remaining: camera-relative/doubles decision (see game repo spike), sky-camera retirement, game frustum flip |
| R5 | Atmospheric scattering, env-driven ambient, signature look | **Planetside slice landed opt-in (Session J, 2026-07-18):** aerial haze (`enable_atmosphere`), hemisphere/SH ambient (`set_hemisphere_ambient`), shadow texel snap (`shadow_texel_snap`) — all default-off = byte-identical, gated by 3 new paxtests. **Sessions K–M (2026-07-18): walkable-ship asset queue (master plan §4.8) COMPLETE on the rendering side** — specular-preserving glass (`set_glass`), double-sided lighting (`double_sided_lighting`), per-node ambient scale (`set_ambient_scale`), and specular IBL (`set_env_map` + real BRDF LUT, R5.3) all landed opt-in, gated by test_glass/test_doublesided/test_ambient_scale/test_env_map. Interior-collision design AGREED Session N (`WALKABLE_INTERIOR_COLLISION_DESIGN.md`, facts measured by `probe_walkmesh.py`; implementation game-side). **Sessions O–P:** local point/spot lights measured (test_local_lights) + Blender/glTF-authored lights activated (`activate_model_lights`); expanded-terrain haze retune recipe in `PLANETSIDE_LOOK_GUIDE.md` §5. **Session Q (2026-07-18): R5.4 GGX prefilter tool** (`tools/gen_env_prefilter.py` — set_env_map's ladder now correct, not approximate) + sh_from_cubemap face table pinned end-to-end incl. file-loaded skyboxes (test_ambient_sh 6-8); openworld round-4 P2 diagnosed (core-profile combine drop = upstream default-shader behavior, `probe_texturestage.py`, response 5). **Session R (2026-07-18): R5.5 orbital scattering LANDED** (`set_orbital_atmosphere` — per-planet limb/halo/terminator from space, test_orbital's independent integrator matches the render to <=0.003; arch doc §9) + the worked skybox example (`gen_equirect_cubemap.py` + shipped 006_Sunset sample, testbed M key) + R1.3 sRGB experiment landed gated. **Session S (2026-07-18): walkable-ship interior package + R5 COMPLETION** — per-node atmosphere scale (`set_atmosphere_scale`), per-subtree environment binding (`set_env_map`/`set_ambient_sh(..., node=np)`), **SSAO first slice** (`enable_ssao`, depth-only, flat-plane byte-identity gated, @msaa4 measured working), **bone-palette knob** (`max_skinning_bones`, 200 measured inert) + **morph verdict fact #15** (HW skinning silently drops sliders; per-node CPU valve renders them), **lens flare/dirt** (`enable_lens_flare`, analytic ghosts from the bright extract, occlusion implicit) — **R5 has NO remaining engine items**; wall-pusher consult answered by measurement (probe_walkmesh 10/10, readback contract, collision doc §9); docs trued up both repos. Gate now 54/6/69. **Testbed keys for the Session-S AND Session-V features landed (Session W, sfb2 `daaf291`): P screens/flipbook, C nav circuits, Y clip door, F lens flare, Q SSAO.** **Session Y (2026-07-20): the three carried-over Round-5 env asks landed** — `set_env_scale(np,s)` (per-node, ibl_spec only), `set_env_intensity(s)` (global, composes), `set_env_map_rotation(deg)` (specular yaw, skybox set_h sense); test_env_map +5 exact checks. Remaining everywhere: content adoption |
| R6 | Engine hygiene (dead-path deletion, Vulkan watch) | **Windows 2+3+4 DONE:** DX9 excised (`d29183ce42`), display backends excised (`3912762dd9`), mobile-target machinery + DIRECTCAM excised (`c627e2d0bc`, 2026-07-19) — −43k lines total, full gate green every time. No mobile code remains; remaining R6 = Vulkan watch only |
| ER (terrain lane) | Game-driven engine requests (`C:\python\sfb2\documents\ENGINE_REQUESTS\`): ER-001 splatting, ER-002 scatter, ER-003 data-texture contract | **ALL THREE IMPLEMENTED ENGINE-SIDE + GATED (Session U, 2026-07-19).** ER-003: `data_texture()` + `load_data_texture()` (test_data_texture, hostile `compressed-textures 1` live). ER-001: `set_terrain_splat()` — TERRAIN_SPLAT PBR variant, splat-driven 4-layer texture arrays, macro variation, analytic-TBN normal maps + distance fade, v2 define seam (test_terrain_splat, 12 exact analytics, works on BOTH GLSL baselines). ER-002: `set_instanced()` over upstream InstancedNode — INSTANCING in pax_pbr.vert AND shadow.vert; measured: unflagged fallback renders correctly (perf switch, not correctness), instanced shadows work, clear_shader keeps flags (trap gate-guarded) (test_instancing; SKIPs on stock 1.10). Deep-dive mechanisms recorded in `documents/ENGINE_INTERNALS.md` (new, Session U). **ER-007 hex-tiling IMPLEMENTED + GATED (Session Y, 2026-07-20):** `set_terrain_splat(..., hex_tiling=True, hex_cell_size, hex_rotation (per-layer), hex_contrast)` — TERRAIN_HEX_TILING at the ratified v2 seam, 3-tap Mikkelsen stochastic tiling, works on BOTH GLSL baselines without textureGrad (per-cell transforms constant ⇒ tap UVs continuous where weighted), normals back-rotated with the motif; +12 test_terrain_splat checks (periodicity shift-rms 0.0014→0.2296, anisotropy contract, byte-identical opt-out). **ER-007 height-blend rider + chunk-seam fix IMPLEMENTED + GATED (Session AA, 2026-07-21, same day as the terrain dev's height8-in-albedo.a delivery):** `set_terrain_splat(..., height_blend=True, height_sharpness=8.0)` — TERRAIN_HEIGHT_BLEND softmax reweight (`w·2^(k·albedo.a)`); the all-flat-palette no-op contract holds BY CONSTRUCTION (equal heights cancel; gated rms 2.6e-06) and flat-128 slices compete at their middle (analytic-exact); plus `hex_offset=(u,v)` world-anchors the hex cell hash (the chunk-border motif seam — UV-window equivalence gated, rms 0.0005). **ER-009 cutout alpha IMPLEMENTED + GATED (Session AA, next-day):** `apply_alpha_masks` now detects `TransparencyAttrib M_binary` (geom- or node-level, predicate a≥0.5 = the cull semantic) and takes `instanced=True` to compose INSTANCING into the mask variant (the origin-collapse pairing trap is now a gate check, 0/4→4/4); grass-understory adoption = `apply_alpha_masks(proto, instanced=True)` after the M_binary rewrite. The ER's "shadow pass already discards" premise was corrected in the response (no depth-path discard exists; fact #17 stands; their scatter is shadow-excluded anyway). +14 terrain / +10 alpha-mask checks; totals unchanged all four configs. **ER-010 wet-sand waterline IMPLEMENTED + GATED (Session AE, 2026-07-24, same-day as filing):** `set_terrain_water(chunk_np, water_z, band_m=1.0, dark=0.55, rough_mult=0.35, sat=1.25, anim_amp/period/scale/phase)` — TERRAIN_WATER rider on the splat variant (v2 seam untouched); wetness by WORLD Z, all layers alike, submerged terrain FULLY wet (the seafloor-under-shallows headline); wet albedo dark+saturate (Rec.709-luminance chroma expansion, commute exactly), wet roughness × rough_mult (the sheen is a specular read — white-env gate check); breathing edge = amp·sin(phase + 2π·noise(world_xy/anim_scale)), phase from _update, `anim_phase` pins for determinism, amp=0 EXACT; every consumer mix()es by wet so wet==0 is bit-exact water-off arithmetic; `set_terrain_splat` re-calls PRESERVE water (re-dress contract); clears byte-identical. NEW test_terrain_water 17 checks ×@game/@directional both engines. Remaining: game-side adoption (one call in materials.py next to set_terrain_splat). See master plan §4.9 + §4.11 + §4.13 + §4.17 |
| ER (ships lane) | Walkable-ship requests (Phobos/Minerva, Vattalus packs): ER-004 rigid clips, ER-005 powered displays | **BOTH IMPLEMENTED ENGINE-SIDE + GATED (Session V, 2026-07-19).** ER-004: `pax3d_render/rigid_clips.py` + `pipeline.get_model_clips()` — parses the plain-node TRS channels panda3d-gltf silently drops (doors/ramps/gear/drawers), loader-conjugation axis contract pinned in-gate, RigidClipPlayer (seek/reset, game owns easing), `RigidClip.from_delta()` for the ~40 Minerva prefab script-lerps (test_rigid_clips). ER-005: `set_screen()` (albedo+emission bind, byte-identical restore), `set_emission_scale/_color`, `set_uv_transform/set_uv_scroll/play_flipbook` + `tools/gen_flipbook.py` (test_screen, 15 analytics). **THE video fact: the wheel builds `--no-ffmpeg` — no MP4 decode engine-side; flipbook atlas is the sanctioned carrier. DECISION CLOSED (ship-lane 634 + user sign-off): trimmed flipbooks, NO ffmpeg build window.** All Session-V questions resolved same day: converter splits per-screen nodes (49 bindings / 6 shared materials measured); from_delta compose validated against VattalusInteractable.cs source; pack easing = smoothstep (census corrected — game smoothsteps `u`). Part 3: `set_blink()` ship nav/strobe/beacon driver (envelope on emission + synced real lights, 737NG circuits model documented); light budget MEASURED: with shadows max_lights 22 = ceiling (24 fails to link, varying budget), recommend 16. **ER-008 light-selection policy ANSWERED + ARMED (Session Y, 2026-07-20):** overflow keeps the `Light.set_priority()`-sorted head (ties: spot > directional > point class rank, then ARBITRARY), excess silently dropped; the directional-mode sun is now pinned at priority 1<<20 (floods would have evicted it + its shadows — default-on guard); `set_light_budget(root, lights, ...)` per-root nearest-N warden makes budgets LOCAL (test_light_priority + @directional). Zero-light draws render with a default WHITE slot-0 light (GSG quirk, on record). **Gate now @game 71/6/106 Pax3D · 69/6/108 stock; @modern 70/7/106 · 68/7/108** (Session Y: +test_light_priority incl. @directional; FAIL sets unchanged). Loader mechanisms in `ENGINE_INTERNALS.md` §5. **ER-004 ADOPTED game-side (session 637: the Phobos console clip live end-to-end — the store contract held in the field at 0.0 err/1 mm/1e-7); ER-006 nav-lights filed-as-answered.** **ER-012 glTF tangent synthesis (filed 2026-07-24 as "ER-010" — renumbered, number collided with wet-sand) FILED-AS-ANSWERED same day, zero engine work: panda3d-gltf ALREADY synthesizes per-vertex tangents at convert time for UV'd primitives lacking TANGENT (probe `tools/probe_tangent_synthesis.py`: SR4 0/5, Hermes 0/14 geoms missing post-load); pax_pbr has NO draw-time derivative fallback — missing tangents = NaN-black, shimmer = tangent quality (mikktspace/degenerate-UV, watch-gated LOW; master plan §4.18).** **Session AF (2026-07-24, the lights slice — all three consult items LANDED + GATED same day, pure Python/GLSL): ER-013 `set_light_halo` IMPLEMENTED (min-screen-size additive halo sprites, depth-tested = free occlusion, inherits the set_blink envelope — the km-range nav-light piece; test_light_halo); `add_visibility_query`/`enable_visibility_query` (depth-tap visibility, ~2-frame latent, NO mid-frame stall — retires the game's ray-sphere flare occluders incl. sun-through-the-Phobos-hull; sky-dome valve `max_occluder_depth`; test_visibility_query +@logdepth); `enable_spot_exponent` (flood lamps — GL spot exponent read, opt-in because Spotlight's class default is 50; test_spot_exponent). Adoption notes `sfb2/documents/ENGINE_UPDATE_2026-07-24_SESSION_AF_LIGHTS.md`; nav-light fleet recipe delivered same day (`ENGINE_UPDATE_2026-07-24_NAV_LIGHTS_FLEET_RECIPE.md`, config-side bulb placement confirmed). Consult answers on record (session log): interior light exclusion = Session-S valves + `set_light_off(sun_light_np)` (adoption, not engine gap); volumetric shafts evidence-gated. Gate totals now Pax3D 81/7/125 · stock 79/7/127 (+18 jobs; FAIL sets unchanged).** Remaining: ER-005 adoption + Minerva conversion + nav-circuit wiring (all game-side). See master plan §4.10 |
| ER (character lane) | NPC visual quality: ER-014 character detail maps | **ER-014 IMPLEMENTED ENGINE-SIDE + GATED (Session AI, 2026-07-26, pure Python/GLSL):** `set_detail_maps(model_np, enabled=, normal=, occlusion=)` — per-geom USE_NORMAL_MAP/USE_OCCLUSION_MAP composition on the apply_alpha_masks pattern (the ER proposal's API verbatim, so the game's s695 hasattr wiring lights up with zero change). NORMAL needs a bound normal-map stage AND a tangent column (NaN-black guard, gate-measured on a tangentless M_normal card); OCCLUSION needs a metal-rough/ORM stage (`.r` = AO, analytic-exact in-gate); variant-carrying geoms (ALPHA_MASK hair, GLASS, GPU_MORPHS) skipped — call it last. **Composes with the face-range CPU valve** (fact #23's override rock-paper-scissors): `set_hardware_skinning` re-stamps covered geoms at the valve override with the flag folded in + shadow casters get a per-camera tag-state rescue (without it the depth pass ASSERTS — falsified in-gate); `clear_hardware_skinning` no longer leaves the empty-attrib blanket behind. NEW test_detail_maps (18 default + 4 shadow checks; @directional and @directional@logdepth legs = the leak detector), green both engines; stock-1.10 import guarded (M_occlusion_metallic_roughness getattr). **ADOPTED GAME-SIDE same day (game s737): boot counts 10/14/12 geoms, juno A/B frames close the promo gap with the CPU valve ON throughout (valve composition field-proven), PS_BENCH unmeasurable per envelope, `PS_NO_DETAIL_MAPS` kill switch game-side — TERMINAL.** Next expected filing from that lane: SSS skin. See master plan §4.22 |
| VFX lane | Baked explosion footage (CGVision air/space pack, 28 ProRes 4444 MOVs at `C:\python\asset_sources\Explosions\`) | **`spawn_effect()` LANDED + GATED (Session AD, 2026-07-23):** premultiplied flipbook quads via set_screen(metallic-1-black = analytically unlit) + set_glass + play_flipbook, one-shot self-reaping; footage MEASURED premultiplied; `gen_flipbook.py` alpha-aware (RGB path byte-identical). test_effects 13 checks ×@directional both engines. **First adoption same day (sfb2, uncommitted): planetside non-ground detonations (launcher/grenade airbursts) play the baked fireball; ground hits keep the corona.** `spawn_effect(fade_out=N)` one-shot end-ramp (coverage + emission to zero over the last N s — non-transparent final frames no longer ghost-then-pop; +3 test_effects checks) built by a prior session, committed + gate-proven Session AI. Slice 2 (evidence-gated): soft-particle depth fade, multi-angle bakes. Master plan §4.16 |

| ER (voxel lane) | Animal Crossfire requests (`C:\python\paxcraft\docs\ENGINE_NOTES.md` — see Games Served above) | **ALL THREE SESSION-AJ ITEMS IMPLEMENTED + GATED (2026-07-27, pure Python, no build window):** (1) **`render_snapshot(pos, hpr, size, ..., shadow_center=)` photo mode** — one-shot full-pipeline render (PBR/shadows/atmosphere/SSAO/bloom/flare/tonemap) from any pose into a RAM-backed texture WITHOUT perturbing the player's view (player chain deactivated for the one engine frame; window keeps its last image, gated rms 0.0); persistent chain in new `pax3d_render/snapshot.py`, repeat shots 3–24 ms (their fallback was ~30 s subprocess boots — the AI-building loop is now interactive); the shadow-extent coupling is a first-class param (`shadow_center=`/`shadow_extent=`, one-frame recentre + exact restore, gated both ways); NEW test_snapshot 8/11 checks ×@directional, green both engines; planetside gets photo mode/kill-cam free (concordance). (2) **Visibility query fails LOUDLY** — `pipeline.visibility_query_valid`, per-query `.valid`, fail-CLOSED 0.0 while a depth stomper is registered (was: confident open-sky garbage, their three-session trap), `register_viewmodel_camera(on_depth_degrade='raise')`, live-flip degrade in set_enable_log_depth; +9 test_visibility_query checks. (3) **`set_detail_maps` append-only registration** — new entries stamp only their own geoms (was O(total registered) per call — their 300-chunk terrain measured gatling 60→32 fps; their 2 s deferred-batch workaround can retire), no-valve removal O(entry); +3 test_detail_maps checks. Reply filed in their ENGINE_NOTES.md. **Session AK (2026-07-28, the monastery far-field consult): all three far-field questions ANSWERED in-channel (no depth problem exists — background display regions clear depth per-region; own-graph ring = zero shadow-cascade cost + no PBR coupling; haze = per-frame `set_atmosphere_params` + the analytic formula reproduced in their ring shader) + `register_scene_camera(follow='pose'|'hpr')` LANDED (pipeline mirrors the main camera per frame; `render_snapshot` re-aims follow cameras per shot and restores — closes the Session-AJ "game-owned transforms" snapshot limit for follow cameras; also fixed: main-region clears now restore when the last background camera unregisters). test_snapshot +6 checks, green both engines. Photo-mode "+1" answered as already-shipped (workaround stack → shipped API map); MSAA edge-on seams triaged (watertightness hypothesis: per-chunk transforms → ulp cracks; game-side single-root world-space-verts A/B prescribed before any engine work; 2× snapshot SSAA = photography workaround today). Their async-readback ask (F9 recorder) QUEUED (build-window row below), not landed — C++/GSG class per the Language Canon. **Session AL (2026-07-28, the water-lane ask, same-day): the shared game-water PROMOTED into the engine** — `pax3d_render/water.py` + `shaders/water_surface.{vert,frag}` via `pipeline.build_water_surface()`: WaterParams uniform block (defaults = the planetside ocean, gate-pinned; every paxcraft deviation is a param), depth PROVIDER contract (`set_seafloor` R32F world-z window or direct `u_seafloor` binds — names match the game copies; uncovered `'deep'`\|`'dry'`), both port findings folded in for every consumer (fragment haze = the EXACT pax_pbr analytic block fed from `pipeline.atmo_*` per update; `water_sun` HDR luminance knee inside `set_environment`). NEW test_water 15 checks ×@game/@directional both engines (haze rows match an independent Python ray-evaluation ≤0.002; dry/rim byte-identical). **Planetside ADOPTED same-day** (default path, `PS_LEGACY_WATER=1` A/B until walk sign-off — their exp fog and raw HDR sun feed retire); paxcraft migration map filed in the reply (~400 of their 658 lines retire; frozen exe waits on the standing AJ/AK re-vendor). Gate Pax3D 92/7/143 · stock 89/7/146 (+2 PASS +4 SKIP each = the test_water jobs; FAIL sets unchanged). **Session AM (2026-07-28, their F9-recorder readback ask — SHIPPED same-day, and the queued build-window row RETIRED with zero C++): the engine already owned the PBO round-robin.** `GraphicsOutput::get_async_screenshot()` — PBO recycle pool → `glReadPixels` → GL fence → map+memcpy on the 2-thread `gl_texture_transfer` chain — arrived with the Window-1 catch-up merge, is published to Python, and had simply never been connected to readback cost here (the ER-012 shape: read the engine before building for it). **Pax3D-only — stock 1.10.16 has no such API** (measured), so their frozen exe gets it with the AJ/AK re-vendor they already owe. What was actually missing was the encoder contract, now `pax3d_render/capture.py` + `pipeline.begin_frame_capture(max_in_flight=3)` → `FrameCapture.poll()` yielding `CapturedFrame` (`.data` zero-copy BGRA bottom-up, `.tobytes()`, `.frame_number`): **ordered delivery** (head-only retire — the 2-worker chain guarantees no completion order; out-of-order ingest scrambles video intermittently), **bounded in-flight + drop accounting** (each readback holds a whole frame — an unpaced requester reached 120 in flight ≈ 690 MB in two seconds), **repeat-poll de-duplication** (the engine caches ONE request per output and clears it at draw time, so polling twice before a draw returns the SAME object — enqueued twice it delivers one frame twice; identity by `.this` per fact #20), and `drain(timeout_frames=, step=)` for the tail latency would eat. Measured paced to 60 fps over a no-readback baseline: sync `RTM_copy_ram` +3.92 ms p50 / +9.91 ms p95 @1600×900 and +13.29 / +22.86 ms @4K, vs async +0.19 / +0.13 ms and +0.56 / +2.26 ms; latency 2 frames; pixels byte-identical to the sync tap (0 of 5,760,000 bytes). NEW test_capture 13 checks @1600×900 (the size their filing measured), skips whole on stock, and green against a REAL window too (`--show`) — which is where the two findings an offscreen gate hides turned up: (a) on a double-buffered window the delivered frame is ONE behind the request (the engine copies after the flip; constant, measured 47/48, never garbage — so the check gates a CONSTANT offset, not zero), and (b) **a readback still in flight at process exit segfaults it** — one is enough; `cancel()`/`remove_all_windows()` do not help, only retiring the fences does, so `stop()` now renders engine frames until nothing is in flight (build-window row added for the C++ fix). **Method fact worth keeping: measure readback PACED** — an unpaced loop renders ~2000 fps, outruns the transfer chain 30×, and reports 34-frame latency and 19/60 delivery, all artifact (two probes and the first cut of the test said exactly that). Planetside replay/photo capture gets it free (concordance) |
**Engine C++ changes so far: a handful of surgical, gate-proven fixes**
(build-system fix; Session-R combine-mode warning; Session-X offscreen GL
fixes; the 2026-07-24 GVAD stability window — DeletedChain restored +
cycler guards + `set_num_stages` interior delete; the 2026-07-26
bind-thread pin — `bind_thread` ref()s the bound ExternalThread so the
TLS pointer can never dangle when callers drop the return value).
Everything else is Python/GLSL in `pax3d_render/`. When to use which language is canon — see
**Language Canon** below: prototype in Python/GLSL, promote to C++ on
evidence; C++ only in build windows the user schedules (never casually
mid-session — every C++ change needs a full rebuild).

### Hard-won facts (do not re-litigate without new evidence)

These were established mechanically by the harness (Session A, 2026-07-16;
full analysis in `documents/PAXTEST_FINDINGS_SESSION_A.md`):

- **There is no Panda3D DirectionalLight engine bug.** A real
  DirectionalLight lights every current mesh type correctly. The 2025-era
  "bug" was mesh winding + NaN tangents + API confusion. Older docs (both
  repos) that say otherwise are wrong.
- **There is no double-gamma bug in the tonemap chain.** All operators match
  their analytic curves exactly. ACES looks washed out because *inputs* are
  not linearized (sRGB textures sampled raw) and content was tuned around
  Hejl-Dawson.
- **The blocky bloom is FIXED (Session D, 2026-07-17).** Root cause: the
  bloom intermediates were 8-bit FBOs (`render_quad_into` without fbprops
  silently downgrades the declared RGBA16F texture) — quantization
  banding, not filtering. Any HDR post pass MUST pass float fbprops;
  `bloom_buffers_float` in test_bloom guards this. Beware the diagnostic
  trap: this banding looks exactly like nearest-neighbor sampling.
- **Verify the engine worktree is clean before trusting field reports
  (2026-07-17).** During Window-1 prep, ~35 repo files were silently
  overwritten with stale Session-D-era content (editor/session artifact;
  forensics in the session log). The openworld "lit shadows vanish" P0
  was measured against that contaminated tree — on a clean engine the
  same harness probe (`gltf_caster_ground_lum`) shows the glTF caster
  darkening ground 0.800→0.086. Before chasing any externally-reported
  rendering regression: `git status`, then reproduce on a pristine
  checkout + current wheel.
- **glTF alphaMode MASK only works in the compat profile (Session W,
  2026-07-19).** The loader's `AlphaTestAttrib` reaches only
  fixed-function `GL_ALPHA_TEST`; under `gl-version 3 2` it is
  silently ignored and ALL MASK content renders opaque (factor-only
  masks = solid shells, foliage = solid cards) — identical on stock
  1.10, upstream behavior. `pipeline.apply_alpha_masks(model_np)` is
  the fix (per-geom shader variant, bit-identical on compat, gated by
  test_alpha_mask; master plan fact #17). Session AA (ER-009):
  `TransparencyAttrib M_binary` is the same defect class (cull
  composes an alpha test at max priority — fixed-function-only) and
  is now detected too; on `set_instanced` nodes pass
  `instanced=True` or the geom-level mask variant collapses every
  instance onto the origin (gate-measured). Depth pass still casts
  the unmasked silhouette @modern — `exclude_from_shadows()` is the
  valve.
- **Panda wrapper `id()` lies — key caches and identity checks by
  `.this` (Session AB, 2026-07-21).** Two lookups of the same C++
  object return different Python wrappers (`id(a) != id(b)`,
  `a.this == b.this`), so `id()`-keyed caches never hit for shared
  objects and can FALSE-hit after a wrapper is collected (its id gets
  reused — wrong data bound). Corollary: `copy_to` on a Character
  pointer-shares RenderStates/textures but deep-copies vdata — the
  Session-Z "clones share vdata" claim was this artifact (fact #20).
- **Pin poses and prove sample points (Session G, 2026-07-17).** A
  luminance check is only as good as its sample geometry:
  `get_anim_names()` ordering is nondeterministic (historical shadow
  readings from the glTF probe were pose luck), and the shadow test's
  "pole" pixel is the sphere's FRONT surface — outside a thin caster's
  shadow column. The promoted assertion failed on a HEALTHY engine until
  both were fixed (master plan fact #12). Also: the 94-joint Rigify
  hardware-skinning "concertina" (openworld P1) does not reproduce on a
  clean engine — GPU==CPU at every measurable layer (fact #13,
  test_skinning guards it); per-node opt-out exists:
  `pipeline.set_hardware_skinning(np, False)`.

---

## The Working Method (non-negotiable)

1. **Verify with the harness, not by launching the game.**
   ```bash
   C:/python/stock-panda-env/Scripts/python.exe tools/paxtest/run.py  # stock engine
   C:/python/pax3d-env/Scripts/python.exe tools/paxtest/run.py  # Pax3D engine
   ```
   Run the relevant tests before AND after any rendering change. If a claim
   about rendering behavior matters, write a paxtest check for it — that is
   how every "mystery bug" here has been killed.

2. **Rendering fixes land in `pax3d_render/` and only there.** The game's
   `graphics/pax_pbr/` is the legacy copy kept for A/B; `pax3d_simplepbr/`
   is retired. Never fork the pipeline again — divergent copies caused the
   failed March 2026 effort.

3. **Eyeball with the testbed, not the full game.**
   `C:\python\sfb2\test3d_pax.py` gives a sun/planet/station/ships scene in
   seconds with hotkeys for every feature (`--pax3d --sun-mode directional
   --shadows`, `--selftest` for automated screenshots).

4. **Respect the phase gates.** Bloom work (R3) was blocked until lighting
   (R2) passed for a reason. Check the master plan before starting work
   that belongs to a later phase.

5. **Keep behavior changes opt-in until proven.** The game adopts new
   pipeline behavior via flags (`use_pax3d_render`, `sun_light_mode`), with
   the old path selectable for A/B until the new one is signed off.

6. **Prototype in Python/GLSL; promote to C++ on evidence.** See the
   Language Canon below — the near-instant iteration loop is this
   project's superpower; C++ is for the classes of work that demand it,
   never a default.

---

## Language Canon (user-ratified 2026-07-17)

**Prototype in Python/GLSL; promote to C++ on evidence.**

The loop — edit → paxtest → seconds → hand to a downstream AI dev →
same-day field report — is this project's superpower and the fuel of the
measure-first method. KEEP THE SUPERPOWER. But Pax3D must stay performant
as the fork deepens, so C++ is used when the class of work demands it:

| Work | Language | Why |
|---|---|---|
| Orchestration, configuration, per-frame O(1) uniform pushes | Python (`pax3d_render/`) | Not in any hot loop (the whole per-frame Python is ~microseconds); iteration speed is worth more than the cycles |
| Per-pixel / per-vertex work | GLSL | The real performance language of a renderer — and it also iterates instantly |
| Per-frame × per-object/per-vertex machinery that can't live on the GPU (cull callbacks, CSM/instancing/light-culling managers, engine data paths) | C++ (`panda/src/`) | The engine's hot loops are already C++; new work of that class joins them |
| Proven, stable Python that a **profile** shows in the hot path | Promote to C++ | Port when the design has stopped moving — never while a feature is still iterating |

Rules:

1. **Never port on faith.** A measurement (profiler or harness number)
   showing the work in a hot path comes first. Performance claims get the
   same discipline as rendering claims — this repo has killed too many
   myths to accept "C++ is faster" without a number.
2. **C++ lands only in user-scheduled build windows** (a full rebuild is
   the 30–60-minute class; failed builds corrupt `built_x64/`). Candidates
   accumulate in the queue below — they are batched, never landed casually
   mid-session.
3. **New engine-adjacent features default to a Python/GLSL prototype even
   when C++ is their eventual home.** Stabilize the design at zero build
   cost, then sink it.

Evidence on file: the bloom root-cause fix, log depth, and the entire
Session E shadow package (root-cause in a downstream game + three APIs +
tests + docs) each landed same-day *because* they were Python/GLSL; the
openworld build measured 103–115 fps at 1600×900 (40 animated NPCs, 4096²
shadows, MSAA 4×, bloom) through the Python pipeline — the frame lives in
the GPU and Panda's C++, not in our orchestration layer.

### Build-window queue (living list — add candidates here)

| Item | Class | Status |
|---|---|---|
| ~~WINDOW 1: final catch-up merge build~~ | Merge + rebuild | **DONE + VALIDATED 2026-07-17** — float wheel built (8 min on this machine, MSVC 14.5), full §6 gauntlet green (paxtest both engines × both baselines identical, testbed, sfb2 + openworld smokes). The merge is signed off; severed-upstream policy fully in force. Wheel: `wheels_window1\float\` |
| ~~Doubles engine build (`STDFLOAT_DOUBLE`)~~ | Build flag | **DONE, spike VERIFIED 2026-07-17** — compiles clean under C++17 (upstream never CI'd this); precision perfect (0.000e+00 round-trip at Neptune offsets); `test3d_ftl --selftest` green. Finding: stock simplepbr crashes on doubles (LVecBase3f/3d) — the wheel stays quarantined in `pax3d-double-env`. Remaining: perf A/B + user flight. Results: game repo `handover_doubles_spike.md` |
| ~~WINDOW 2: DX9 removal~~ | Deletion (R6) | **DONE 2026-07-17** — `d29183ce42`, 65 files, −16,691 lines, gate green |
| ~~WINDOW 3: dead platform display backends~~ | Deletion (R6) | **DONE 2026-07-17** — `3912762dd9`, 132 files, −18,546 lines (GLES/GLES2/EGL/WebGL/Android/iPhone/macOS backends + the DX9 flag machinery), gate green. **`--no-dx9` is no longer a valid makepanda option** |
| ~~WINDOW 4: mobile-target extraction~~ | Deletion (R6) | **DONE 2026-07-19** — `c627e2d0bc` (+2 fixups), 72 files, −8,112 lines (android/iphone glue, Android cross-compile machinery, dist mobile deploy, DIRECTCAM), full gate identical both engines × both baselines. Wheel: `wheels_window4\` |
| R2.3 DirectionalLight conveniences (`set_direction_world`, strip translation in `xform()`, non-zero-pos warning) | New C++ API | Queued, low urgency — the pipeline owns sun orientation |
| **Texture-palette skinning** (joint matrices in a float texture / UBO instead of the uniform array) — removes the bone cap entirely; full 343-bone UE5 rigs verbatim, no reduction pass. User-ratified direction 2026-07-18: maximum UE5/Unity asset compatibility, no artificial caps. Until it lands, `max_skinning_bones='auto'` covers rigs to the ~240 uniform wall (Session S) | New C++ + GLSL | Queued, **deprioritized on field evidence 2026-07-19**: the 81-vs-151 re-bake A/B measured ≤0.33 mm deviation on the pack's demo clips (correctives rigid to parents) — no deformation win until richer anim packs key them; 'auto'+audit guards the gap. Pairs naturally with an 8-influence option |
| ~~GPU morph path~~ (morph deltas + slider uniforms in the skinning vertex shader — HW skinning and morphs coexist) | GLSL + Python | **DONE 2026-07-20 (Session Z) — pure Python/GLSL, NO build window needed, runs on stock 1.10 too.** `set_gpu_morphs(np)`: per-vdata RGB32F delta texture (position AND normal deltas) + float32 `morph_index` column (both-baseline addressing, no gl_VertexID) + per-geom GPU_MORPHS variant; 52 targets addressable, ≤16 live, O(sliders) per-frame push. Gated: test_morph_gltf, GPU-vs-CPU-valve rms 0.0000. Fact #15 closed opt-in (default path byte-identical); fact #19 records the mechanism. Shadow silhouette unmorphed + variant-stacking = documented limits, field-evidence-gated. **Session AB (2026-07-21) crowd/bake riders:** delta texture flipped VERTEX-MAJOR = the loader's own array layout ⇒ zero-copy bake (enable 1.17 s → 0.07–0.08 s/face on all three shipped heroes; numpy gather for non-canonical column orders like kade's pack, pure-Python floor kept, all three byte-compared in-gate); `set_gpu_morphs(clone)` on a copy_to clone reuses the pointer-shared delta textures (zero re-bake) and gives it its OWN face — without it clones wear the template's face (fact #20: copy_to deep-copies vdata, shares textures; wrapper id() is unstable — key caches by `.this`). test_morph_gltf now 17 checks/config. 8-face morph-attributable 0.19 ms (bar ≤0.5); 32 all-driven 4.3 ms. C++ promotion only if a profile ever demands |
| ~~Core-profile combine-mode warning~~ | New C++ warning | **DONE 2026-07-18 (Session R mini-window, user-authorized)** — `857b715086`, once-per-TextureAttrib glgsg warning in both default-shader paths; 1m22s incremental build, full gate identical both engines, wheel live in pax3d-env + archived `wheels_session_r\`. Day-one field value: the warning fired on a real silently-flattened combine state in sfb2's own boot |
| **InstanceList bulk fill** (`set_from_buffer` — fill per-instance transforms from a flat buffer/numpy instead of 1k–10k Python `append()` calls per mesh class per chunk) | New C++ API | Queued Session U on the ER-002 volume envelope, **on profile evidence only** — the game side accepted the append loop on worker threads; `get_array_data()` already caches the GPU-side array in C++, so only the Python fill loop is per-instance. If `test_instancing`/field profiling never shows it hot, it never lands |
| ~~Offscreen GL fixes~~ (restore the single-buffered branch of `FrameBufferProperties::get_buffer_mask()` — upstream DX9-fix regression `bd4dc8a379` made EVERY offscreen frame raise GL_INVALID_OPERATION and panic-deactivate the GSG after ~20 s, in every Pax3D wheel since the fork; + honor `gl-max-errors -1`) | Two one-line C++ fixes | **DONE 2026-07-19 (Session X part 2 mini-window, user-authorized)** — 1-min incremental build, probe 0 errors/frame everywhere (was ~60/phase), `test_gl_clean` now the permanent zero-GL-errors guard on both engines, full gate green, wheel live in pax3d-env + archived `wheels_session_x\`. Fact #18 |
| ~~GVAD handle-race stability fix~~ (restore `USE_DELETED_CHAIN=1` alongside mimalloc, makepanda.py:2327; restore both cycler stage guards to `#ifndef NDEBUG`; fix the `set_num_stages` interior delete, pipelineCyclerTrueImpl.cxx:334) — the reproducible chunk-mesher heap corruption (field crashes 2026-07-20 + 2026-07-23; **any cross-thread Geom construction vs destruction**; `workers=1` does NOT mitigate) | Build flag + 2 small C++ fixes | **DONE 2026-07-24 (GVAD stability window, user go-ahead)** — `d6044b1d8a`, clean 12-min build, full acceptance green: every crashing repro row survives (deep soak 6.9M builds), gate both engines FAIL-sets-unchanged (Pax3D 82/7/129 · stock 80/7/131 incl. NEW permanent `test_gvad_churn` — FAILed on the Session-X wheel, PASSes on the fix + stock), testbeds + plan.py smoke green. Wheel live in pax3d-env AND system Python, archived `wheels_gvad\`. ER-011 mitigation no longer load-bearing. Optional follow-up stays available: poison-on-free diagnostic wheel |
| ~~bind_thread dangling-ExternalThread pin~~ (`thread.cxx` — `bind_thread` ref()s the bound thread for process lifetime; upstream's "caller's responsibility" raw-TLS contract dangled the moment consumers dropped the returned PT — which sfb2 planetside, paxcraft, AND repro_min all did; heap reuse then poisons `get_pipeline_stage()` → `_data[garbage]` → null-CycleData AV. Paxcraft field report 2026-07-25; reproduced at workers=2 = the sfb2 envelope; mechanism proven by keep-the-PT intervention + full-memory minidump (`fetch_add` on 0x8 under GeomPrimitivePipelineReader). DISTINCT from the GVAD bug — same signature family) | 1-line C++ fix | **DONE 2026-07-26 (Session AH mini-window, user "action any necessary changes")** — 1m32s incremental build, bind-pin probe UNPINNED(rc=1)→PINNED(rc=2), the 3-second-AV paxcraft discard shape completes full selftest twice, gvad_churn regression green (2.55M builds), NEW permanent `test_thread_bind` (bind_pinned Pax3D-only + bound_churn_render; SKIPs whole on stock — measured: stock 1.10 AVs on the discard-shape churn row, upstream-inherited, recorded not gated). Root cause + forensics: `documents/CRASH_BIND_THREAD_DANGLE.md`. Stock's foreign-thread `thread != nullptr` assert (threadWin32Impl.cxx:71) confirmed intentional: this fork REQUIRES bind_thread on foreign threads |
| ~~PBO round-robin framebuffer readback~~ (streaming sibling of `render_snapshot` for video capture/replay; filed by Animal Crossfire 2026-07-28, F9 H.264 recorder, sync `RTM_copy_ram` measured **+4.7 ms/frame @1600×900**, 4K ≈ 4×) | ~~New C++ (GSG)~~ + Python API | **DONE 2026-07-28 (Session AM) — NO BUILD WINDOW NEEDED: the engine already had the PBO round-robin.** `GraphicsOutput::get_async_screenshot()` (PBO recycle pool → glReadPixels → GL fence → memcpy on the 2-thread `gl_texture_transfer` chain) came in with the Window-1 catch-up merge and is published; **stock 1.10.16 does NOT have it** (Pax3D-only). What was missing was the recorder contract, now `pax3d_render/capture.py` + `pipeline.begin_frame_capture()`: ordered delivery, bounded in-flight + drop accounting, repeat-poll de-duplication (cached-per-output request, identity by `.this`), `drain()`. Measured paced at 60 fps: sync +3.92 ms p50 @900p / +13.29 ms @4K vs async +0.19 / +0.56 ms, 2-frame latency, pixels byte-identical. Gated by NEW test_capture (12 checks @1600×900, skips on stock). Their two field notes stand and are on record: `RTM_triggered_copy_ram` re-stalls rather than defers; Python's default 8 KB BufferedWriter GIL-convoys a render loop on Windows pipe writes |
| **Async-screenshot shutdown AV** (found Session AM, 2026-07-28): a readback still in flight when the process exits segfaults it — ONE is enough, reproducible on both a real window and an offscreen buffer. Mechanism: the GL GSG's `_fences` deque holds `Fence{GLsync, CompletionToken}`; CompletionToken's documented contract is "destroyed prematurely == complete(false)", and the screenshot fence callback (glGraphicsStateGuardian_src.cxx ~8703) **ignores its success flag**, so premature destruction runs it anyway → `map_read_buffer`/`release_client_buffer` GL calls against a GSG that is already being destroyed. Fix is small: honor `success` in that callback (finish/cancel the request without touching GL), and/or retire `_fences` in the GSG destructor while the context is live. Hits upstream's own `save_async_screenshot()` at app exit too, and the same chain at ~15172. Repros in scratchpad (`probe_shutdown.py`, `probe_mitigate.py`): `cancel()` and `remove_all_windows()` do NOT help; only retiring the fences does | Small C++ (GSG) | Queued 2026-07-28, MEDIUM — **mitigated in Python meanwhile**: `FrameCapture.stop()` renders engine frames until the fences retire, gated by `test_capture`'s `stop_drains_in_flight` row + the child exit code. The mitigation only covers captures the pipeline hands out; a game calling `get_async_screenshot()` raw still needs the C++ fix |
| Vulkan-port evaluation (hand-port from read-only upstream reference) | Port | Only when it can run the paxtest suite. Watch log 2026-07-17: ACTIVE — upstream merged `shaderpipeline` (SPIR-V) into the `vulkan` branch 2026-07-02/03; nowhere near paxtest-ready. The catch-up merge moved our base next to it — a future port got much cheaper |
| Python→C++ promotions | Promotion | **None yet** — nothing Python has profiled hot |

---

## Repository Map

| Path | What | Status |
|---|---|---|
| `pax3d_render/` | **The unified rendering pipeline.** Pipeline class, camera registration, sun modes, shadows. | Active — all rendering work happens here |
| `pax3d_render/shaders/` | GLSL sources (PBR, bloom, tonemap, TAA, shadow) | Active |
| `tools/paxtest/` | Offscreen test harness: gamma, lighting, bloom, rebuild, shadows | Active — extend when adding features |
| `pax3d_simplepbr/` | March-2026 simplepbr fork | **Retired** — reference only, merged into pax3d_render |
| `panda/src/` | Engine C++ (`glstuff/`+`glgsg/` are the GL backend, `wgldisplay/`+`windisplay/` the Windows glue, `pgraphnodes/` has the light classes) | Upstream 1.11.0-dev July-2026 state (merge `eb685fd003`, C++17) **minus R6 surgery**: DX9, all dead display backends, AND all mobile-target machinery/DIRECTCAM deleted (Windows 2+3+4, −43k lines; `panda/src/android`+`iphone` no longer exist). Kept on purpose: `x11display/`+`glxdisplay/` (HOLD — plausible Linux CI future), `tinydisplay/` (software renderer — paxtest on GPU-less machines) |
| `makepanda/` | Build system | oscmd fix + R6 surgery scrubs. Ships one graphics reality: OpenGL core on Windows (+X11/tinydisplay). `--no-dx9`/`--directx-sdk` no longer exist |
| `documents/` | Planning docs, findings, guides — see `documents/README.md` | Mixed current/historical |
| `doc/` | Upstream Panda3D docs (CODING_STYLE, INSTALL) | Upstream |

---

## Building the Engine (only needed for C++ changes)

Python/GLSL work in `pax3d_render/` needs **no engine build** — it runs on
whatever `panda3d` is installed. Build only when touching `panda/src/`.

The canonical command on this machine (PowerShell; ~8 min at 20 threads):

```powershell
cd C:\python\pax3d
$env:VCINSTALLDIR = "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\"
C:\Python313\python.exe makepanda\makepanda.py --everything --no-fmod --no-ffmpeg `
    --no-fftw --no-opencv --windows-sdk 10 --msvc-version=14.5 --threads 20 --wheel

# Install into the Pax3D venv:
C:\python\pax3d-env\Scripts\python.exe -m pip install --force-reinstall --no-deps panda3d-1.11.0-cp313-cp313-win_amd64.whl
```

Critical pitfalls (full detail in `documents/BUILDING_PAX3D.md`):
1. **ALWAYS pass `--windows-sdk 10`** — never rely on the default SDK pick.
2. **This machine has VS Build Tools 2026, not full VS** — makepanda's
   vswhere query cannot see Build Tools editions and it defaults to MSVC
   14.3, hence BOTH `--msvc-version=14.5` AND the `VCINSTALLDIR` env var
   are required (detection falls through to that var).
3. **`--no-dx9` no longer exists** (removed with the DX9 surgery) — old
   docs/scripts that pass it will error out.
4. **Thirdparty libraries are not in the repo** — see the build doc.
5. **Use system Python, never `makepanda.bat`.**
6. **Delete `built_x64/` after failed builds AND between flag changes** —
   the dep cache corrupts/mis-builds silently.

## Environments

| Environment | Python | Engine | Use for |
|---|---|---|---|
| Stock testbed | `C:\python\stock-panda-env\` | Stock Panda3D 1.10.16 + gltf 1.3.0 + simplepbr 0.13.1 | **The ONLY stock env on the machine** — paxtest cross-checks. Do not "fix" it to the fork |
| System Python | `C:\Python313\python.exe` | **Pax3D 1.11.0 fork** (machine-wide engine pinning, game session 643c/ee861db — bare `python x.py` is the fork by construction) | makepanda builds; NO LONGER the stock reference |
| Pax3D venv | `C:\python\pax3d-env\` | Pax3D 1.11.0 (bind-pin wheel 2026-07-26 — bind_thread pins bound threads; supersedes the GVAD wheel, whose fixes it carries) + full game dep stack | **The game's default engine**; engine-build testing |
| Doubles venv | `C:\python\pax3d-double-env\` | Pax3D 1.11.0 `STDFLOAT_DOUBLE` wheel | The doubles experiment ONLY — never wire to launchers (stock simplepbr crashes on it) |

The game (`plan.py`) and testbed run under either; paxtest runs under both —
identical results on both is itself a useful signal (defect is in Python/GLSL,
not C++). See `documents/SWITCHING_ENGINES.md`.

**Machine context (since 2026-07-17):** THIS machine (20 cores, VS Build
Tools 2026) is the primary dev machine — sfb2 development moved here;
`C:\python\sfb2` is the canonical current game copy (`D:\python\sfb2` on
the external T7 is the master backup; `D:\python\pax3d` is the pre-transfer
engine backup). Wheels live in `wheels_window1\{float,double}\`,
`wheels_window2\`, `wheels_window3\`, `wheels_session_r\`,
`wheels_window4\`, `wheels_session_x\`, `wheels_gvad\`,
`wheels_bind_pin\` (current);
`wheels_float\` holds the pre-merge rollback. Smoke-boot the game with `PYTHONUTF8=1` when stdout is
redirected (a game-side `→` print crashes under cp1252 otherwise).

---

## Conventions

- C++: follow upstream (`doc/CODING_STYLE.md`); tag every Pax3D change with
  a `// PAX3D:` comment and list it in this file's change table when it lands.
- Python: the pipeline is plain, dependency-light code — keep it that way
  (no game imports in `pax3d_render/`; debug via `PAX3D_RENDER_DEBUG` env
  var or `debug=True`).
- Don't break the game's API surface: `from graphics.pax_pbr import init`
  must keep working (it routes here via the settings flag). Add, don't rename.
- Focused diffs, no drive-by reformatting of engine code — for reviewability
  and `// PAX3D:` auditability, not for upstream's sake (see below).
- Commit style: one logical change per commit; note the phase (e.g.
  "Session C / R2") in the subject.

## Upstream Relationship — SEVERED (user decision, 2026-07-17)

**Pax3D is a sovereign engine. We do NOT maintain compatibility with future
Panda3D versions, and upstream sync is no longer a goal or a cost to weigh.**
Modify the engine however the game needs: change defaults, rename, delete
legacy paths, add engine-level features. The `// PAX3D:` change tags stay —
they exist so we know our code from inherited code, not to ease merges.

Upstream (`panda3d/panda3d`) remains a read-only *reference*: cherry-pick a
specific fix by hand if one ever matters. There is no sync cadence.

One-time exception, user-ratified (Route A, 2026-07-17): a **final
catch-up merge** of upstream master (`eb685fd003` — C++17 migration + 93
commits of fixes) was taken before the door closed, moving our divergence
point from 2026-02-26 to July 2026. **Built and fully validated
2026-07-17** (`documents/BUILD_WINDOW_1_CATCHUP.md`) — the door is now
closed for good. No further syncs — the policy above is otherwise
unchanged. Sovereignty has since been exercised: R6 surgery Windows 2+3
deleted 35k lines of never-shipped backends.

| | |
|---|---|
| Upstream (reference only) | `panda3d/panda3d` (GitHub) |
| Our engine | `Apocrypha-Stellarum/Pax3D` — **standalone public repo since 2026-07-28** (fork-network link severed; old fork archived as `Pax3D-fork-archive`). The public-repo program (rebrand, gallery, releases, recipes, future queue) lives in `documents/GITHUB_PRESENCE.md`. **Author identity for ALL new commits: `Rob de la Selva <actualhuman2025@proton.me>`** (global git config; old history exempt by user decision) |
| Divergence point | 2026-02-26 (`2d2bdc9a`), upstream 1.11.0-dev |
| Sync cadence | **None — severed 2026-07-17** |

---

## History in One Paragraph

Forked Feb 2026 to fix "the DirectionalLight problem" and add bloom/HDR. The
March effort built post-processing on an unlit, unverified pipeline and was
reverted almost entirely (Session 459 in the game repo). July 2026 rebooted
the program with a test harness first: the harness disproved both founding
myths (engine light bug, double gamma), reproduced the real bloom defect,
and then R1/R2 landed in quick succession — one unified pipeline, a real
DirectionalLight sun with working shadows, all harness-proven. On
2026-07-17 the final upstream catch-up merge was built and signed off, the
doubles spike verified, and R6 surgery removed DX9 and every dead platform
backend — a sovereign, single-reality engine tree, every step gated by the
harness. The lesson that must survive: **measure first, then build.**
