# Pax3D Session Log

The session-by-session narrative of the rendering program, extracted
verbatim from Master Plan v2's §1.2 update blocks (2026-07-17, when the
plan was rewritten as v3). Newest entries at the bottom. Full handovers
live in `HANDOVERS/`.

---

**Session A update (2026-07-16):** Phase R0 is complete — `tools/paxtest/`
exists and its first run revised this register: F2's double-gamma
hypothesis is disproven (real cause: input linearization), F3 is reproduced
in isolation, F8 is confirmed, and a real DirectionalLight is proven to
work on all current mesh types (de-risking R2). Full analysis in
`PAXTEST_FINDINGS_SESSION_A.md`.

**Session B update (2026-07-16):** R1 core landed — `pax3d_render/` is the
unified pipeline (merge of the game's pax_pbr + pax3d_simplepbr), verified
behavior-identical to pax_pbr by the harness (gamma/lighting match; bloom
shows the same known F3 defect), on both engines and both GL baselines.
New `register_scene_camera()` API fixes F4: paxtest `rebuild` shows the
old sky-camera pattern dying on bloom toggle in both legacy pipelines
while pax3d_render survives. Game side: opt-in
`planetary_shuttle_rendering.use_pax3d_render` flag (default false) routes
`graphics.pax_pbr` to the new package; sky_camera.py auto-uses the
registration API when available. Remaining R1: flip the flag in-game and
eyeball parity; sRGB texture linearization experiment
(`make_base_color_textures_srgb()` helper is ready); drop the GLSL 120
dual-path once the game sets gl-version 3 2.

**Session C update (2026-07-16):** R2 core landed — pax3d_render gains
`sun_light_mode='directional'`: a pipeline-owned real DirectionalLight
processed by the standard p3d_LightSource loop (SUN_FROM_LIGHTSOURCE
define), oriented via HPR so lighting and the shadow camera always agree.
`update_sun()` keeps its signature in both modes; paxtest lighting is
green in directional mode with measurements identical to uniforms mode,
and external DirectionalLights are now CONSUMED. **Sun shadows work**:
new `test_shadows.py` proves occlusion (0.79 lit → 0.09 shadowed),
runtime toggles via `set_sun_light_mode()` / `set_enable_shadows()` /
`set_shadow_extent()`. Fixed a real bug the harness caught: runtime
`_recompile_pbr()` wiped all shader inputs (now preserves the attrib).
Testbed: `--sun-mode/--shadows` flags, N/X hotkeys. Remaining R2:
game-side switch to directional mode + shadow-extent driving from planet
data (R2.4 at scale), planet tangents (only needed for normal maps),
engine C++ conveniences (set_direction_world — optional now that the
pipeline owns orientation).

**Session D update (2026-07-17):** R3.1 done — **F3 (blocky bloom) is
root-caused and fixed**; `test_bloom` is green at both resolutions, both
engines, both GL baselines. The real cause was none of the three
suspects: the bloom intermediates were **8-bit framebuffers**.
`render_quad_into()` without `fbprops` creates a default 8-bit FBO and
the texture bind silently rewrites the declared RGBA16F format to match,
so the extract's `*0.005` scale crushed the halo tail into a handful of
8-bit codes — the tonemap then amplified each 1-code step into a visible
band (texel-aligned plateaus that mimic nearest-neighbor sampling; this
misdirected the investigation toward filter state). Fix: explicit float
fbprops on every bloom `render_quad_into` (pipeline.py), plus two real
but secondary defects found on the way: the 13-tap downsample kernel
used `b`/`c` where the center sample `a` belongs (over-weighted the -y
taps — this was the vertical halo asymmetry), and the 9-tap upsample
tent was applied to the same-res source while the coarser accumulator
got one bilinear tap (Jimenez tents the coarser mip). Also explicit
bilinear+clamp on all bloom textures (was default repeat → edge bleed).
New paxtest check `bloom_buffers_float` guards the root cause. Legacy
pax_pbr/pax3d_simplepbr still fail test_bloom by design (frozen A/B
copies). Remaining R3: content retune (R3.2/R3.3 — strength/intensity/
tints; note the per-mip tint list reads inverted vs its comment labels),
auto-exposure stretch (R3.4), and the game-side bloom-on decision after
the R1/R2 flag flips.

Session D also closed the R2.4 mechanism: `set_shadow_extent` gained a
world-space `center` (light-node positioning, lighting-neutral — three
new paxtest checks in test_shadows prove outside-extent-is-lit,
recenter-shadows, and lighting-unchanged), and the game now recenters
the shadow frustum on the camera every sun update
(`sun_position_manager.py`) with a new
`planetary_shuttle_rendering.sun_light_mode` settings key passed through
`plan_initialization_manager.py`. What's left of R1/R2 needs the user:
flip `use_pax3d_render` → parity eyeball → flip `sun_light_mode` to
'directional' → validate shadows in-game.

**Session D addendum (2026-07-17, cont.):** Flags FLIPPED on user order
(`use_pax3d_render`, `sun_light_mode=directional`, `enable_shadows`) —
game smoke-boots clean on pax3d_render, zero shader errors; visual
parity eyeball still pending. **R4.0 done:** `test_scale.py` reproduces
both scale defects deterministically (Z-fight sweep at 2500 IEU;
off-origin precision loss — which requires a ROTATED camera to
manifest; axis-aligned rigs cancel exactly). **R4.1 core done:**
opt-in `enable_log_depth` in pax3d_render — fragment-level log depth,
`scale/pax3d_render @logdepth` GREEN under both GLSL baselines and both
engines; testbed Z hotkey / `--log-depth`; planet approach clean through
a 0.1/1e9 frustum. Sweep-based z-fight probing was required: single
frames can tie-break uniformly and mimic correct rendering. Parallel
sessions the same day: FTL warp distortion in the tonemap pass (with
test_ftl_blur, green) and the game repo's doubles-build spike (candidate
for the R4.2 precision half). R4.2 decision: camera-relative rendering
chosen; doubles build shelved for CPU cost (revisit at the next break);
the parent-cancel rebasing trap measured into test_scale
(`trap_parent_cancel_quantizes`).

**Session E update (2026-07-17):** R2 shadow hardening, driven by the
openworld build's engine feedback (`PAX3D_FEEDBACK.md` in that repo;
our reply: `OPENWORLD_FEEDBACK_RESPONSE.md`). Their P0 — "skinned
meshes cast no shadows" — was **root-caused as NOT an engine bug**:
(1) the visible symptom was the shadow-bias trap (normalized bias ×
extent depth: the 0.005 default = 3.0 m at their 600-deep frustum ≈ a
standing character's entire light-ray depth gap at a 30° sun, so
characters lost shadows while buildings kept them — reconstructed
exactly in their live build, 0.450→0.450 vs 0.450→0.378); (2) their
0-texel depth-map evidence was contaminated by their own proxy-prism
workaround occupying the same light-space column (proven in their
build: 0 texels with proxy, 60 without). The skinned depth path is
proven green nine ways in paxtest (egg + their glb via Actor, hw+sw
skinning, GLSL 120+330, bam-cache, blend, masks, angled sun, posed
joints 0.321→0.037) — new permanent coverage in test_shadows incl. a
`@softskin` matrix row and a depth-map texel-diff instrument.
**Landed in pax3d_render (opt-in, defaults byte-identical):**
`shadow_bias_world` / `set_shadow_bias(v, world_units=True)` (rescales
with extent depth — kills the trap class), `shadow_filter_size=3`
(3×3 multi-tap PCF, edge 6→16 px, interior unchanged),
`shadow_caster_mask` + `exclude_from_shadows()`/`include_in_shadows()`
(blessed no-cast API), openworld's shadow debug modes 10/11 committed.
New `test_shadow_quality.py`: angled-sun-at-predicted-position,
bias-trap measured record, PCF, no-cast — 9/9 both engines, both GL
baselines. **Space-game exposure:** sfb2 runs extent 500/4000 with the
default bias ⇒ ~20 IEU effective offset — set a world-unit bias
(~0.5 IEU) before the in-game shadow validation.

**Session E addendum — policy day (2026-07-17, cont.):** Three
user decisions, same day: (1) **Upstream SEVERED** — Pax3D is sovereign;
no sync cadence, no compatibility goal; upstream is a read-only
reference for hand cherry-picks (`f6726136`; docs reconciled
`c11e778b`). (2) **Language Canon ratified** — "prototype in
Python/GLSL; promote to C++ on evidence"; KEEP THE SUPERPOWER;
build-window queue established in CLAUDE.md (`1fbaae9d`). (3) **Route A
final catch-up merge** — one-time import of upstream master before the
door closed: `eb685fd003`, conflict-free (our C++ tree had zero
changes), 93 commits (C++17 migration + robustness fixes), divergence
point now July 2026, adjacent to the vulkan/shaderpipeline branch.
Build Window 1 opened: B-computer builds the float wheel (required) +
doubles wheel (optional Build 2) per `BUILD_WINDOW_1_CATCHUP.md`;
pre-merge rollback = `wheels_float/` wheel + `pre-catchup-merge` tag.
Upstream 2026 check: no SDK releases (latest remains 1.10.16,
2025-12-25); vulkan/shaderpipeline branch ACTIVE (July 2–3).
`ENGINE_SURGERY_PLAN.md` written (DX9 removal = Window 2; dead
backends = Window 3; Cg deferred to a shaderpipeline-port decision).
Master plan rewritten as v3; this log extracted.

**Session F update (2026-07-17, the build-window marathon):** All three
build windows executed and validated in one day on the new primary
machine (20 cores, VS Build Tools 2026 — makepanda needs
`--msvc-version=14.5` + `VCINSTALLDIR`, see BUILDING_PAX3D.md pitfall 0).
**Window 1:** float wheel 7m49s, doubles wheel 8m19s (upstream never
CI-built C++17×doubles — it compiles clean); full §6 gauntlet green —
paxtest both engines × both baselines 48/48 identical, testbed eyeball,
sfb2 boot, openworld selftest; doubles spike verified (round-trip
0.000e+00 at station/1 AU/Neptune offsets, `test3d_ftl --selftest`
PASS; finding: stock simplepbr crashes on doubles → wheel quarantined
in `pax3d-double-env`). The merge is SIGNED OFF; severed-upstream policy
fully in force. **Windows 2+3 (R6 surgery):** DX9 excised
(`d29183ce42`, −16,691 lines) then all dead platform display backends +
the DX9 flag machinery (`3912762dd9`, −18,546 lines); each with its own
build and full gate; none/simplepbr canaries never moved. `--no-dx9` no
longer exists. **Incident worth remembering:** the first Window-1 build
failed because ~35 repo files had been silently overwritten with stale
Session-D-era content (xfile C++ reverted to pre-merge string_view-less
signatures; pipeline.py/pax_pbr.frag missing ~140 lines of Session D2/E
work). Forensics: content matched the repo state of commit `2499ecc6c4`
(03:18); the write happened 05:53–05:54 on the A machine, pre-transfer;
the D:\ backup carries the identical dirty state; openworld's vendored
copy and its launcher were ruled out. Fixed by `git restore` of 15 files
(stale diff preserved as a patch). **Consequence:** the openworld
evening "P0 — lit shadows vanish" was measured against that contaminated
tree; on the clean engine `gltf_caster_ground_lum` shows 0.800→0.086
darkening, and the user confirms shadows look good in-game. Established
fact #11 added. **Machine migration:** sfb2 development moved here —
canonical `C:\python\sfb2` (67.5 GB robocopy from the T7), fresh
`pax3d-env` with the current wheel + full game dep stack. Two game-side
bugs found in passing (sfb2): a `→` print crashes under cp1252 redirected
stdout (smoke with `PYTHONUTF8=1`), and a mixed-slash music path breaks
one audio load (reproduces on stock 1.10.16 — pre-existing). Docs
refreshed this session; next-session priorities: paxtest hardening
(openworld asks), the REAL new P1 (94-joint Rigify hardware-skinning
deformation), then the game-side adoption queue.

**Session G update (2026-07-17 evening, harness hardening + the P1
verdict):** Both openworld asks landed. (1) `gltf_caster_ground_lum`
promoted to the hard assertion `gltf_caster_darkens_ground` — and the
promotion immediately earned its keep by FAILING on a healthy engine,
exposing two test-geometry traps: `get_anim_names()` ordering is
nondeterministic (every historical 0.086 reading from this probe was
pose luck — 'Dance' covers the sample point, 'A-poses' doesn't), and
the sampled "pole" pixel is the receiver sphere's FRONT surface
(y=−0.76), outside a thin caster's shadow column (depth maps proved the
caster was written correctly on both engines — 1 texel difference
between stock and Pax3D out of 2,803). Anim sorted + pose pinned +
actor y-shifted; 0.800→0.086 deterministic on both engines. Established
fact #12. (2) New `test_shadows_gltf.py`: synthesized textured-glTF
scene (real baseColorTexture materials through panda3d-gltf), glTF
caster AND receiver, 45° angled sun, optional real-character caster —
green everywhere. **The P1 (94-joint Rigify concertina) does not
reproduce on the clean engine** (fact #13): palette-math simulation ==
`animate_vertices` exactly; rendered GPU/CPU A/B across all 50 Walk
frames — pack 1 0.00% every frame, pack 2 ≤0.25% shading-level only
(worst frames eyeballed side-by-side: identical silhouettes); the
DEF-spine compensating-scale chains compose to net 1.000; the palette
cap was [100] in every shader era. Verdict mirrors the P0:
contaminated-era measurement suspected; re-measurement requested
(`OPENWORLD_FEEDBACK_RESPONSE_3.md`, copied to the openworld root).
**Per-node skinning API landed regardless** (the P1 ask):
`pipeline.set_hardware_skinning(np, enabled)` /
`clear_hardware_skinning(np)` — flag-only ShaderAttrib at override 2,
inherits the shader per-bit, munger CPU-skins the subtree in every pass
including the shadow pass; harness-proven pixel-exact round-trip
(`test_skinning.py`, which also carries the pack probes as permanent
gate coverage). Full gate: 58 jobs × both engines × both baselines,
green in the documented pattern (the only new row-level note:
`lighting/none @modern` fails identically on stock — pre-existing
fixed-function-under-gl3.2 control-pipeline artifact, not ours). Engine
C++ untouched; everything this session is Python/GLSL/tests/docs, per
the Language Canon.
