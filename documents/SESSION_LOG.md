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

**Session G postscript (same evening):** openworld updated
`PAX3D_FEEDBACK.md` with a P0 ADDENDUM — the lit-shadow failure is
**sun-direction-gated** (perfect at eastern/high sun, dead inside a
western low-sun cone, alt ≤~40° az ~240, depth-error signature
~1/tan(alt), azimuth-asymmetric; `OW_SUN_OVERRIDE` makes it
deterministic and clock-independent) — and their reinterpretation of
the 03:36/04:29 window (sun-arc mapping change, not contamination) is
credible now that fact #12 showed the forensic counter-evidence was
pose luck. Immediate probe (`tools/paxtest/probe_azimuth_sweep.py`):
at toy scale the glTF caster+receiver scene casts perfect shadows at
ALL 4 azimuths × alt 34/45/60, identical stock vs Pax3D — the trigger
needs openworld scale and/or their exact daynight sun vectors. Plan
for Session H is in the (updated) Session G handover: scale-faithful
sweep → their exact vectors → `set_shadow_extent` depth-window
placement audit → mode-10/11 decode. Their addendum also confirms
skinned NPC shadows in-game (0.604× darkening at noon).

**Session J update (2026-07-18):** The **planetside package** — R5's
planetside slice pulled forward by user direction after the openworld
Mars colony map proved the use-case. Spaceflight stays first priority,
so every feature is opt-in, default-off, byte-identical when off, and
toggleable off for space scenes (each test asserts the opt-out restores
the baseline capture with rms exactly 0.0). Three features, all
Python/GLSL per the Language Canon, no engine build:
**R5.1 aerial perspective / height haze** (`enable_atmosphere`,
recompile-class + uniform-only `set_atmosphere_params`) — analytic
exponential-height medium in the PBR shader with a sun-forward scatter
tint; test_atmosphere matches the transmittance curve to 3 decimals at
three distances, proves the altitude falloff and the sunward tint, and
proves `density=0` is an exact no-op even when compiled in.
**R5.2 environment ambient** — the sh_coeffs IBL path that shipped
zeroed since R1 is now fed by `set_hemisphere_ambient(sky, ground)`
(exact SH bands 0–1), raw `set_ambient_sh()`, `clear_ambient_sh()`, and
EXPERIMENTAL `sh_from_cubemap()`; test_ambient_sh matches the analytic
per-channel expectations exactly, proves coefficients survive
recompile-class toggles (the §3 invariant extended to
`_set_env_map_uniforms`), and validates the cubemap projection against
the analytic hemisphere at 0.0% error.
**Shadow texel snapping** (backlog item) — `shadow_texel_snap` quantizes
the frustum center to the texel grid along the light's film axes;
test_shadow_snap measures the shimmer source (0.3-texel move flips 24
depth texels unsnapped), the anti-shimmer property (0 changed texels and
rms 0.0 screens across a snapped sub-texel sweep), and that whole-texel
steps still follow (152 texels). Full gate: both engines × both
baselines green in the documented pattern; the three new tests also run
green through the game's routed `pax_pbr` import path. Field handover:
`PLANETSIDE_LOOK_GUIDE.md` (API + Mars starting values for the openworld
dev). Open: in-app tuning, sh_from_cubemap horizontal-orientation check
on a real skybox, orbital scattering (the spaceflight half of R5).

**Session K update (2026-07-18):** The **glass package** — first slice
of asset enablement for walkable ships (§4.8 of the master plan, new):
the game is integrating the CGTrader Phobos Starhopper (fully modelled
interior), and its cockpit canopy is the motivating asset. The defect,
measured before fixing: standard M_alpha blending multiplies the ENTIRE
shaded result by alpha, so a canopy at alpha 0.15 keeps 15% of its
specular highlight — test_glass puts the loss at 2.07× at the analytic
highlight. The fix, opt-in per the byte-identical contract:
`pipeline.set_glass(np)` composes a GLASS-defined compile of the SAME
PBR shader onto the node (the render-root compile is textually
unchanged — default byte-identity by construction) plus
TransparencyAttrib M_premultiplied_alpha at override 1 (outranks the
geom-level M_alpha panda3d-gltf stamps on BLEND materials). In the
variant, alpha attenuates only transmission-class terms (diffuse,
flat+SH ambient; fog/atmosphere inscatter coverage-weighted); specular
— sun, local lights, IBL — and emission add at full strength (the
glTF-viewer BLEND semantic). The variant is compiled lazily, re-pushed
after every recompile-class toggle (`_reapply_glass_shaders` — the §3
input-preservation invariant extended to per-node variants), and
opt-out restores the node's saved blend state exactly. The depth pass
is untouched (the shadow camera's override-1 initial state outranks the
node shader) — glass casts an opaque shadow unless paired with
`exclude_from_shadows(np)`, which is the documented intent for
canopies. Evidence: test_glass 6 checks, analytics exact on the first
run (legacy 0.289 vs analytic 0.290, glass 0.599 vs 0.599, transmission
0.753 vs 0.753), green both engines × both baselines × both sun modes
(@directional exercises the light-loop split) and through the routed
pax_pbr path; full 15-test suite green on both engines, documented
baselines unchanged. Queued next in §4.8: gl_FrontFacing double-sided
fix, specular IBL first slice (canopy reflections + the sh_from_cubemap
orientation check), per-node ambient scale for hull interiors.

**Session K update 2 (2026-07-18):** **Double-sided lighting** — second
slice of the §4.8 walkable-ship queue. The defect, measured: the shader
shaded backfaces with the FRONT face's normal, so glTF doubleSided
materials seen from behind rendered ambient-only (test_doublesided:
0.108 where the lit answer is 0.705). Fix: `double_sided_lighting`
(init kwarg) / `set_double_sided_lighting()` (recompile-class) compiles
in the Khronos sample-viewer semantic — `if (!gl_FrontFacing) flip
n/world_normal` right after normal derivation, so both sun paths, the
light loop, IBL, and the slope-scaled shadow bias all see the flipped
normal; glass variants inherit the define automatically. Front faces
take the no-op path and are BIT-identical to the flag-off compile
(asserted, rms 0). Deliberately opt-in rather than always-on: existing
two-sided content with visible backfaces (foliage cards, FX quads)
WOULD change appearance, so the games eyeball first. Evidence:
test_doublesided 6 checks, analytics exact on first run, green both
engines × both baselines × both sun modes + the routed pax_pbr path;
full 16-test suite green both engines, documented baselines unchanged.
Remaining in §4.8: specular IBL first slice, per-node ambient scale.

**Session L update (2026-07-18):** **Per-node ambient scale** — third
§4.8 slice, moved to the front of the queue by the ship dev's ranking
("the interior is unlit without it"; their #2, the double-sided fix,
had already landed in Session K update 2). `set_ambient_scale(np, k)` /
`clear_ambient_scale(np)`: an inherited `u_ambient_scale` shader input
(root default 1.0 — an EXACT no-op, IEEE x*1.0, asserted) folded into
the shader's ambient-occlusion factor, which multiplies precisely the
indirect terms — SH/IBL and flat AmbientLight ambient, including their
GLASS-variant splits — and nothing else: direct sun through a canopy
still lights the deck, local lights work normally, emissive screens
still glow. Uniform-cost, no recompile, composes with set_glass and
use_occlusion_maps. Evidence: test_ambient_scale — per-channel
analytics exact (max err 0.000) at scale 1.0, 0.25, and 0.25 + full
sun (the sun-shaft case proving direct light is unscaled), recompile
survival and byte-identical opt-out both rms 0.0; green both engines ×
both baselines + the routed pax_pbr path; full 17-test suite green
both engines, documented baselines unchanged. Also this session: the
ship dev's ask for an **interior collision / local walkable-mesh
story** is registered in §4.8 as a design-with-game-dev item (walk
mode is heightfield-only; a ship interior is a floor above terrain
with walls and a ceiling) with the engine-side position written out:
no new engine code expected — dedicated low-poly collision subtree
emitted at GLB conversion, walk mode swaps heightfield sampling for a
downward CollisionSegment via a scene-local traverser inside the
ship's bounds, door collision rides the animated joints. §4.8
remaining rendering item: specular IBL (ship-dev-ranked last, "pure
polish"). Also root-caused mid-gate: a PRE-EXISTING harness flake —
test_shadows_gltf's actor check still picked `get_anim_names()[0]`
UNSORTED (the fact-#12 trap; Session G sorted only test_shadows.py),
so the pose wandered between runs (height 1.82 → lum 0.239 PASS vs
height 1.84 → 0.415 FAIL against the 0.373 threshold). Fixed with the
same sorted() pin; 5/5 reruns now read exactly 0.254 on both engines.

**Session M update (2026-07-18):** **Specular IBL first slice (R5.3)**
— the walkable-ship queue's last rendering item and the R5 "specular
env maps" remainder in one: glass canopies finally have something to
reflect. Two pieces. (1) The REAL split-sum BRDF LUT now ships:
`pax3d_render/textures/brdf_lut.txo` (128², generated by the new
`tools/gen_brdf_lut.py` via pip simplepbr's reference integrator — the
library this shader forked from). The old 1×1 WHITE fallback made
env_brdf=(1,1): harmless only while the env map was black, but it
would ADD the whole env color as a bias the moment a real cubemap
bound — set_env_map REFUSES to run on the fallback. Defaults stay
byte-identical (black env × any LUT = 0; gate confirms). (2)
`set_env_map(cubemap, max_lod=None)` / `clear_env_map()` feed the
shader's until-now-black filtered_env_map/max_reflection_lod path.
First-slice contract: the cubemap's own mip chain IS the roughness
ladder — GGX-prefiltered input is the correct feed; ordinary cubemaps
get mipmap filtering enforced and box mips as the documented
approximation. Pairs with set_ambient_sh(sh_from_cubemap(tex)) for
the diffuse half; reflections ride FULL strength on set_glass nodes
and damp per-node under set_ambient_scale. Evidence: test_env_map —
10 checks, per-channel analytics exact (max err 0.000) with (A,B)
peeked from the pipeline's own LUT at texel centers: constant env,
the LOD ladder (hand-loaded per-mip colors: rough 0 → mip 0, rough 1
→ top mip), mirror ORIENTATION (normal incidence → -Y face, 45° pitch
→ +Z face — the shader's cube sampling is GL-standard, evidence toward
the Session J sh_from_cubemap orientation question on the sampling
side; the loaded-skybox file-orientation half stays open), glass
composition (env term unattenuated through alpha 0.15), recompile
survival + byte-identical opt-out. Green both engines × both
baselines + routed pax_pbr; full 18-test gate green. The §4.8
walkable-ship queue is now COMPLETE on the rendering side — remaining
there: the interior-collision joint design. R5 remainder: orbital
scattering, lens polish, GGX prefilter tool.

**Session N update (2026-07-18):** **Interior-collision design session
CONCLUDED** — the ship dev accepted the §4.8 engine position and
supplied their opening shape (converter emits a `phobos_collision`
subtree; walk mode swaps to CollisionSegment + pusher sphere inside
ship bounds; ramp-foot handoff; their walk mode is plain heightfield +
eye height, no controller library). The joint design is written up in
`WALKABLE_INTERIOR_COLLISION_DESIGN.md`, and — per the house method —
every load-bearing engine mechanic was MEASURED first by the new
`tools/paxtest/probe_walkmesh.py` (headless, no window; 7/7 both
engines, identical numbers), which doubles as the reference
implementation (`geom_np_to_collision` recipe + the ground-query and
pusher rigs). The probe corrected two design assumptions en route:
(1) segment-vs-polygon intersection is DOUBLE-SIDED — the "one-sided
CollisionPolygon" folklore does not apply to the ground query, so the
converter needs no floor-winding fixups (winding only sets the
pusher's push direction: keep wall normals inward); (2) plain
`Character.update()` short-circuits when no animation has marked the
bundle modified — same-frame procedural joint reads need
`force_update()` (in-game, playing door/ramp animations marks the
bundle and updates flow normally). Collision-rides-the-animated-part
is proven on the egg Character machinery (expose-joint pattern,
control_joint-posed panel read back at the exact moved height). The
`max(walkmesh, heightfield)` rule makes the ramp handoff automatic.
No engine code needed; implementation + field report are game-side
(§4.8 open items). Relay note: the dev's message predated Session M —
specular IBL is already landed for their "after" list.

**Session O update (2026-07-18):** **Local lights measured** — the ship
dev needs interior lighting ("dark at night, sun-side-lit by day"),
and the answer is the engine already has everything: point/spot lights
through the p3d_LightSource loop, per-subtree scoping via set_light,
composing with the Session L ambient scale. But that loop was the
pipeline's LAST never-measured lighting path (inherited simplepbr
"correct path", exercised by nothing), so per the working method it
got the analytic treatment before being handed over:
`test_local_lights.py` — PointLight exact at the all-dots-1 geometry,
quadratic attenuation exact (1/(1+q*d^2), the falloff knob; note
Panda's DEFAULT attenuation is (1,0,0) = no falloff), per-room scoping
(unlit sibling stays ambient-only), Spotlight in-cone exact /
outside-cone dark (smoothstep cutoff), and the exact ship-interior
recipe measured: lamp at FULL strength + hemisphere sky ambient damped
by set_ambient_scale, per-channel composition to 0.002 (one test-side
formula error caught en route: this card's normal is HORIZONTAL, so
the hemisphere delta term vanishes — the engine had it right). 6/6
green: both engines × both baselines × both sun modes (the
@directional variant runs the loop with the sun occupying light slot
0). No engine changes — verification + recipe only. Interior-lighting
guidance for the ship dev: lamps parented under the ship fly with it;
scope per room to stay under MAX_LIGHTS (8 per state, init kwarg);
local lights cast NO shadows (point-light shadows are explicitly
disabled — cube maps unsupported; acceptable for cabins); emissive
strips glow but do not illuminate (they are not light sources); values
are linear HDR through the tonemap.

**Session P update (2026-07-18):** Three field asks answered in one
session. (1) **Blender/glTF-authored lights work now** — the classic
simplepbr annoyance root-caused: panda3d-gltf DOES convert
KHR_lights_punctual into real PointLight/Spotlight nodes (with
physical units: color * I*4pi/683, attenuation (1,0,1)), but a light
node is INERT until something calls set_light() with it. New
`activate_model_lights(model_np, root=None, scale=1.0,
include_directional=False)` / `deactivate_model_lights()`:
DirectionalLights excluded by default (the pipeline owns the sun),
`scale` is the physical-to-scene brightness knob (~0.05-0.3),
deactivation restores colors/scopes byte-identically. Gated by
test_local_lights checks 7-9: a synthesized KHR asset loads inert
(rms 0), activates to the exact analytic through the converter's unit
chain (0.219 vs 0.220), restores at rms 0 — green both engines x
baselines x sun modes. (2) **"Hard wall" at the expanded map edge**:
game-side by design — the player is clamped to SceneConfig.half_extent
(planetside controller), and the expanded surround terrain is
deliberately non-walkable backdrop; growing the playfield means
raising half_extent (the heightfield rasterizer follows it). (3)
**"Haze centered on the map middle"**: NOT origin-centered and NOT an
engine defect — both haze systems are camera-relative by construction
(fog: |v_view_position|; atmosphere: fragment-camera ray). Root cause
is the exponential HEIGHT medium doing what it was configured to do:
mars_colony runs base_height=0/scale_height=50 while the expanded
terrain descends to -158 m valley floors -> e^{158/50} ~ 24x density
at the low ground (whiteout at your feet), colony at the z=0 datum
stays clear from anywhere -> reads as "centered on the middle" because
the middle IS the datum ground; plus density=0.0018 eats ~99% at 2 km
by original design (555 m visibility target for a 660 m map — the
surround author's own caveat). Fix is scene tuning, live-tunable
(set_atmosphere_params is uniform-only): retune recipe + three
candidate presets added to PLANETSIDE_LOOK_GUIDE.md §5 (raise
scale_height to ~3x the terrain span, re-datum base_height to
mid-terrain, pick density by target visibility). Engine offer on file:
an optional density-amplification clamp if varied terrain keeps
fighting the exponential — not needed if the retune lands.

**Session Q update (2026-07-18):** Field-response session — the round-4
dossier addenda answered, plus the R5.4 prefilter gap closed. (1)
**Openworld P2 (TextureStage combine drop under core profile) DIAGNOSED:
expected upstream behavior, not a fork regression.** Under gl-version
3 2 every state without an explicit shader is drawn by glgsg's minimal
built-in default GLSL shader (glGraphicsStateGuardian_src.cxx:189-303 —
one texture stage, textureProj x vertexColor x colorScale; no combine
constants/scales/interpolate, which is why set_color_scale works live
and unclamped while everything else is silently inert). The full
ShaderGenerator only runs for set_shader_auto states
(graphicsStateGuardian.cxx:3998) and emits Cg (shaderGenerator.cxx:777),
which cannot compile under core ("The profile is not supported") ->
falls back to the same default shader (:8866). Probe:
tools/paxtest/probe_texturestage.py, four-mode matrix, byte-identical
verdicts on stock 1.10.16 and the Window-3 wheel. Their one-line-warning
ask queued as a C++ build-window candidate (CLAUDE.md queue).
Recommendation to the game stands: explicit GLSL for the dome. (2)
**sh_from_cubemap orientation CLOSED end to end** — the game's marker
rig validated captures in-app (NOT FLIPPED); we pinned the remaining
half (image FILES): test_ambient_sh checks 6-8 prove
loader.load_cube_map puts file N on GL face N content-intact, the
file -> SH -> irradiance chain names every compass marker, and a
gradient up-face proves the up-face image's TOP row is the SOUTHERN
sky. EXPERIMENTAL caveat retired from the docstring; face table now
documented as PINNED (three legs: shader sampling / captures / files).
(3) **R5.4 GGX prefilter tool landed:** tools/gen_env_prefilter.py
bakes any cubemap into the correct complete GGX roughness ladder
(perceptual roughness i/(levels-1), default max_lod addresses it
seamlessly). Borrow-and-verify like the BRDF LUT: simplepbr 0.13.1's
filter_sample/calc_vector verbatim; only the mip loop is ours — the
reference's own loop ZeroDivisionErrors at the 1x1 level (dim-1
division; their 4-level default never reaches it). Inherited quirks
documented (-z-pole tangent degeneracy, corner-stretched texel
directions). 2.6 s at 64px/32 samples. Gated by test_env_map checks
8-11 (subprocess-run tool: mip-0 identity exact, uniform env exactly
preserved at every level, monotone ladder 0.700->0.450, .txo drives
textureCubeLod at max err 0.000). (4) **Response 5 shipped**
(OPENWORLD_FEEDBACK_RESPONSE_5.md) + game-side doc loop closed: the
west-sun P0 fix (Session I set_shadow_normal_bias) finally wired into
USING_PAX3D_RENDER.md and the planetside unification handover — the
planetside team still listed it as an open engine ask; adoption lessons
from their Mars report (day-cycle-scaled haze colors, sub-km density
starting points) added to PLANETSIDE_LOOK_GUIDE.md §5. Full 19-test
matrix green on both engines after every change (43 PASS / 6 documented
FAILs / 57 SKIP, identical stock vs Pax3D).

**Session R update (2026-07-18):** R5.5 orbital scattering landed — the
spaceflight half of the signature look. Phase 0/1 first: field quiet
(FEEDBACK_2 latest entries all pre-answered by Response 5; planetside
handover carries no engine asks; their sky dome moved to an explicit
GLSL shader with "no engine surprises"), baseline gate re-verified at
43/6/57. Then the build: `set_orbital_atmosphere(planet_np, ...)` /
`clear_orbital_atmosphere()` — per-planet registration (GLASS-family
shape, no global flag, no PBR recompile). Renders as a camera-facing
quad pair placed per frame at the shell near surface: extinction pass
(blend dst *= src.rgb, per-channel transmittance) then additive
inscatter; depth-tested not depth-written; own shader pair
(orbital_atmo.vert/frag) tracking USE_330/LOG_DEPTH recompiles under
the glass rule, log-space gl_FragDepth included. Model: single scatter
through an exponential shell — trapezoid optical depth, inscatter
L = sun * intensity * phase(mu) * T_sun(P*) * (1-T_view), exact given
albedo-1 and the one stated approximation (sun transmittance at the
segment's closest approach); soft terminator via smoothstep of the sun
ray's grazing altitude over 2H, reddened per channel by Rayleigh-tint
T_sun. Defaults derive Earth-like optics from radius alone
(H=0.02R, thickness=6H, density=4/sqrt(2piRH), lambda^-4 tint).
Billboard-vs-shell-mesh-vs-material-variant decision recorded in arch
doc §9: billboard is the only shape that draws the beyond-limb halo
AND keeps the limb polygon-free. Reserved draw-mask bit 30 keeps the
quads out of the sun shadow map (shadow camera mask now always clears
it; a caster mask of exactly bit 30 warns instead of blanking).
Gate: NEW test_orbital (12 checks + @logdepth variant) — shader limb
profile vs an independent 2048-step reference integrator matches to
<=0.003 display-space at every measured impact parameter; halo 0.000;
terminator lum 0.000 with >5x asymmetry; density=0 and opt-out rms
exactly 0.0. Full matrix now 20 tests: 46 PASS / 6 documented FAILs /
60 SKIP, identical stock vs Pax3D (orbital adds pax_pbr PASS rows too —
the game shim routes to pax3d_render). Testbed: O / Shift+O hotkeys +
--orbital flag (earth/mars presets), selftest screenshots verified by
eye — limb halo, disk haze, terminator all read correctly at defaults.

**Session R, continued (2026-07-18):** three more phases landed after
R5.5. (1) **Worked skybox example (the proven-but-unused chain closed):**
NEW `tools/gen_equirect_cubemap.py` — equirect panorama -> cubemap .txo
front end (pip simplepbr 0.13.1 has no equirect support; its
from_file_path just calls load_cube_map, so the borrow target did not
exist — the converter is ours with simplepbr calc_vector face directions
verbatim; --selftest proves the pinned face table 8/8 on a synthetic
compass panorama; measured fact baked in: TexturePeeker rows are
bottom-up). The openworld 006_Sunset HDRI (4096x2048) baked in 5s+2s
through convert+prefilter and SHIPPED as tools/samples/
sky006_sunset_ibl.txo (393 KB); testbed M key cycles off/spec/spec+SH
(--env flag for scripted A/B; sfb2 gitignores env/, so the canonical
sample lives engine-side with a testbed fallback path). A/B on file:
shadowed hulls go black -> warm sunset fill. Recipes in
USING_PAX3D_RENDER 8 + look guide 7. (2) **R1.3 sRGB experiment landed
gated:** pipeline.set_srgb_inputs() flips M_modulate+M_emission stage
textures to sRGB formats; two measured traps: release_all() required
(prepared textures keep the old internal format — silently inert
without it) and clear-color-only textures round-trip undecoded (no RAM
image). NEW test_srgb (15 checks): metallic-1 cards collapse ambient to
base*A -> the 128 texel lands on the exact decoded analytic through all
four tonemap curves; opt-out rms 0.0; green both engines x baselines.
Testbed --tonemap/--srgb A/B: THE SESSION A ACES PREDICTION VERIFIED —
wash-out gone with linear inputs, overall brightness drops (content
authored raw) -> default stays off pending game retune. (3) **C++
mini-window (user-authorized in-session):** the queued core-profile
combine-mode warning landed (857b715086) — once-per-TextureAttrib glgsg
warning when the default shader flattens combine/scale/multi-stage
states, both default-shader paths. 1m22s incremental build; gate
identical both engines (48/6/63 with the two new tests); probe verdicts
byte-identical; wheel live in pax3d-env, archived wheels_session_r.
Day-one field catch: the warning fired on a REAL flattened combine
state during a plain sfb2 boot smoke — the game team has a lead to
chase. Window 4 mobile-glue deletion deliberately NOT taken (themed
window deserves its own fresh session). Concurrent-session note:
sfb2 Session 617 landed "Phobos walkable" mid-session — the
walkable-ship adoption wave has begun game-side.

**Session S update (2026-07-18):** Docs-first adoption support + the
walkable-ship interior package, user-directed ("make things easy for
the Phobos/weapons/terrain/NPC devs, then Phobos-priority items").
(1) **Doc true-up both repos:** stale status markers fixed engine-side
(combine warning "queued"→landed, sh_from_cubemap EXPERIMENTAL→pinned,
in RESPONSE_5 / look guide / master plan / index); game-side
USING_PAX3D_RENDER corrected (bloom-is-broken advice retracted — F3
fixed Session D; sRGB section now teaches set_srgb_inputs) and gained
§10 per-role routes: interior env-lighting workflow (Phobos), the
black-metal-viewmodel fix (weapons — "no IBL" predates Session M), the
character/skinned-asset engine contract (NPC — 100-bone
p3d_TransformTable, 4 influences, NO morph targets, per-node CPU
valve), terrain pointers; PAX3D_PITFALLS +6 measured traps;
GRAPHICS_ROADMAP status banner. (2) **Phobos wall-pusher consult
answered by measurement** (probe_walkmesh 7-8, now 10/10 both
engines; design doc §9): THE READBACK CONTRACT — a directly-positioned
walker must adopt the pusher's corrected pos after traverse or a held
key escapes through any wall ~7 frames past contact (measured at their
r 0.35 / 0.10-per-frame numbers; with readback: pinned, zero spread,
z untouched); chunked wall nodes traverse 6.3-6.7x faster than one
3200-poly node (bounds culling) — loader chunks right for Phobos v1,
converter block_room_* groups recommended for the Fenris. (3) **Field
ask landed — per-node atmosphere scale** (`set_atmosphere_scale(np,k)`,
inherited u_atmo_scale multiplying the R5.1 optical depth; k=0 ⇒ tau
exactly 0 = no cabin wash, windows keep hazed terrain; test_atmosphere
atmo_scale_* all exact). (4) **Consult ask landed — per-subtree
environment binding** (`set_env_map(tex, node=np)`,
`set_ambient_sh`/`set_hemisphere_ambient(..., node=np)` + node-form
clears): inherited-input overrides incl. max_reflection_lod so a node
chain addresses its own ladder (test_env_map pernode_* — a leaked
global lod would miss by ~0.25, measured exact; test_ambient_sh
pernode_sh_* — swapped-hemisphere override renders the down-face
analytic exactly). Full gate 48/6/63 both engines, identical, the six
FAILs the documented set. Rig lesson encoded: the harness lens is
fov 30 — project sample points, x=8 at dist 30 is already off the
sampling window.

**Session S update 2 (2026-07-18, same session — the user's "proceed
on all three" mandate):** (1) **SSAO first slice (the first
PaxPBR-native feature):** `enable_ssao` — depth-only Alchemy/SAO
obscurance (normals from derivatives, zero scene-shader changes),
3×3 blur, applied to scene HDR in tonemap; AO buffers deliberately
8-bit; knobs ao_radius/ao_intensity/ao_bias uniform, ao_samples init;
LOG_DEPTH-aware. Defining gate: flat geometry = AO exactly 1.0 →
plane scenes byte-identical with the feature ON. test_ssao green both
engines × baselines × @logdepth × **@msaa4 — measured: the
multisampled depth resolve works** (game default msaa 4 fine). MSAA
shifts crease lines sub-pixel → crease samples scan ±3 rows (fact
#12 discipline). (2) **Bone-palette knob:** `max_skinning_bones`
(default 100; runtime setter recompiles PBR + shadow shaders and
invalidates caster states) — [200] measured INERT for small rigs (rms
exactly 0.0, identity padding); the UE5-Manny 352→81 cut no longer
must merge corrective bones. (3) **Morph verdict → FACT #15**
(probe_morph.py, identical both engines = upstream): hardware
skinning SILENTLY DROPS egg <Dxyz> sliders (loader makes the slider,
animate_vertices applies it, the render doesn't move);
`set_hardware_skinning(np, False)` renders morphs correctly — the
working path today. (4) **Lens flare/dirt — R5 COMPLETE:**
`enable_lens_flare` (needs bloom; inert+warn otherwise) — four ghosts
sourced from the bright extract at analytic positions x_k = 0.5 +
(p−0.5)/c_k (occlusion implicit: hidden sun → no flare, measured
byte-identical), `set_flare_strength` (0 = exact), `set_lens_dirt`
(half-mask dirt kills exactly the predicted ghosts). test_lens_flare
7/7 both engines × baselines. Gate totals now **54 PASS / 6
documented FAILs / 69 SKIP** per engine, identical, verified
sequentially. The known startup GL 0x502 noise (response-5) also
prints here — still noise-class.

**Session S update 3 (2026-07-18, same session):** two mid-close-out
inputs. (a) The character dev's field report landed in
PAX3D_FEEDBACK.md: measured bone sets (full 352 / clip-animated 151 /
shipped 81) put the useful target at ≥192 — already covered by the
landed knob; their 151-bone re-bake A/B is unblocked. (b) USER
DIRECTIVE: no artificial caps — maximum UE5/Unity asset
compatibility. Landed in response: `max_skinning_bones='auto'`
(palette sized by the largest Character under render, bucket 32,
clamp at the ~240 uniform wall) + `refresh_skinning_budget()` /
`audit_skinning_budget()` (the dev's warning ask — a too-big rig now
NAMES itself instead of rendering silently-exploded skin). Measured
on a synthetic 120-joint chain (test_skinning 1c, 17/17 both engines
× baselines): at [100] the GPU cannot render the posed chain (rms
0.1045 vs CPU truth), the audit flags it, 'auto' resolves 128 and
matches CPU truth at rms 0.0000. The TRUE uncap — texture-palette
skinning (full 343-bone rigs, no uniform limit, natural pairing with
an 8-influence option) — is now a named C++ build-queue item
(CLAUDE.md). Their glTF morph asset offer: ACCEPTED, next session
(panda3d-gltf morph delivery is the unmeasured half of fact #15).

**Session T update (2026-07-19):** the accepted glTF morph measurement
ran — the character dev delivered SK_SFM_Head1 (3 GLB variants +
ground-truth manifest) and probe_morph_gltf.py measured the whole
chain: 26 facts, identical stock 1.10.16 vs Pax3D (= everything lives
in the Python loader layer). VERDICT: panda3d-gltf's morph machinery
is complete and correct, but pip 1.3.0 cannot LOAD a real Blender
morph export — three loader defects, now fact #16: sparse-accessor
crash (upstream Moguri#103; Blender's default shape-key encoding),
short-anim-channel IndexError, and a max-vs-min clamp that snaps every
LINEAR sample to the next key (joints too). All three shimmed in the
new `pax3d_render/gltf_compat.py` (`install()`, opt-in, pure JSON-level
densify + two function replacements; no-op on files without sparse
data). With the shim: sliders/slider-tables/morph-columns delivered,
CPU truth matches the Blender manifest to 4 decimals on both variants,
and a byte-patched weights ramp drives the sliders analytically
(0.554 at frame 56 vs 0.5545 expected; short-channel hold exact).
Fact #15 extends to glTF and to JOINT-LESS meshes (scene-wide
F_hardware_skinning drops static-mesh morphs too; per-node opt-out
renders them, ~+0.1 ms/frame per 2240-vert head). The shipped anim
variant's OWN weights channel is all-zero (2 keys, 24 fps timeline vs
the manifest's declared 30) — asset-side export defect; re-export
requested in the PAX3D_FEEDBACK.md response. Instrument trap logged:
cached bams bypass the loader — probe disables BamCache. test_skinning
still 17/17 (no interference; the shim is opt-in and nothing in the
pipeline calls it).
