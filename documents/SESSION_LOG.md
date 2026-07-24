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

**Session T update 2 (2026-07-19, same day):** the character dev's
Session-626 field report crossed our measurement in transit — their
"next engine session measures the morph head" had already happened.
ENGINE RESPONSE 2 written (PAX3D_FEEDBACK.md, top entry): pointer to
the verdict, the three asks (add `gltf_compat.install()` to the baker
boot unconditionally — no-op on morph-less bakes; re-export the anim
GLB with real weights values + the intended 30 fps; add a
`max(weights) > 0` value check to their presence-only verifier). Their
Lane 2 landed: all four characters re-baked keyed/151,
`max_skinning_bones='auto'` + `refresh_skinning_budget()` live in the
game (resolves 160 Mars / 128 village, 185 fps selftest), and the
81-vs-151 A/B measured ≤0.33 mm vertex deviation on the pack's demo
clips — the correctives are rigid to their parents, so the old
weight-merge was already lossless for these clips. Queue updated on
that evidence (CLAUDE.md): texture-palette skinning DEPRIORITIZED
until richer anim packs; **GPU morph path added as a named
build-window candidate** (Python/GLSL prototype first per canon;
queued behind their re-export A/B). Morph lane confirmed as the
character-quality bottleneck from both sides of the fence.

**Session T update 3 (2026-07-19): BUILD WINDOW 4 EXECUTED.** User
authorized the next C++ window with full conn ("commence the build").
Planning: three explore agents mapped the surgery-plan procedure, the
mobile-glue inventory (coupling map incl. composite-cxx unconditional
includes), and R2.3 scope — R2.3 DROPPED from the window on surgery
ground rule 2 plus a real design conflict found during scoping (queue
row annotated). Pre-window: the character dev's re-export landed
mid-planning, so test_morph_gltf was promoted to a GATE ROW first
(`eb23617239`, new totals 55/6/73) — clip drives sliders at the
authored frames 10/38/68 on both engines. Surgery: `c627e2d0bc`, 72
files, −8,112 lines (android/iphone dirs, express Android mount, prc
androidLogStream, deploy-stub glue, dist _android/_proto + android
branches in commands/installers/FreezeTool, makepanda Android
cross-compile + CompileJava/CompileDalvik, DIRECTCAM incl. gated
DirectShow sources). Two fixups (`84d9fa3f33`, `16321d8894`): the
Java-block excision swallowed adjacent Cxx-cache globals — first build
died at dependency scan, second at the FINAL cache save; the removed-
name audit (all top-level names removed vs still referenced, run on
all four makepanda files) is now the mandatory step before building a
surgery window. Clean build 10m54s; wheel archived `wheels_window4\`
and live in pax3d-env. FULL GAUNTLET GREEN: 134-row paxtest matrix
identical stock vs Pax3D on both baselines (@game 55 PASS / 6
documented FAIL / 73 SKIP — exactly the predicted post-morph-gate
totals; @modern 54/7/73, the extra FAIL = lighting/none, the
fixed-function control pipeline under core profile, pre-existing on
stock); testbed selftest OK; openworld selftest exit 0 (full village);
sfb2 30s boot smoke clean with the Session-R combine warning firing as
documented. x11/glx HOLD maintained, tinydisplay kept. The tree now
ships zero mobile machinery; R6 remaining = Vulkan watch only.
Operational note: background tool tasks get killed at ~10 min — long
builds/gates run detached via Start-Process with a re-armed watcher;
stale wheel copies in the repo root are a trap for the archive step
(delete or compare before Move-Item).

**Session U (2026-07-19): the terrain lane opens — three ERs answered,
ER-003 data-texture contract IMPLEMENTED + GATED same-session.** The
game repo's ENGINE_REQUESTS folder (ER-001 splatting, ER-002 scatter,
ER-003 Unity terrain-asset standard) was read, positions formed by
source measurement, interfaces pinned in a chat with the terrain dev
(no redirects), and all three stamped IN DISCUSSION with engine notes.
Discoveries that shaped the answers: (1) **ER-002's answer is hardware
instancing with zero new C++** — the 1.11 tree already ships upstream
`InstancedNode`/`InstanceList` + GSG instanced draws with a
per-instance `p3d_InstanceMatrix` mat4x3 vertex attrib
(glShaderContext_src.cxx:538); pipeline needs only an INSTANCING
define in pax_pbr.vert AND shadow.vert plus a set_glass-pattern
`set_instanced()`. InstanceList has NO bulk-fill (per-instance appends
+ reserve; get_array_data caches the GPU array in C++) — bulk fill
queued as a C++ candidate on profile evidence only. (2) **ER-003's
"never compressed" clause was one config flag from false**: global
`compressed-textures 1` drives CM_default textures into RGTC1/BC4
(F_r16/F_r32) and DXT1 (F_luminance) — per-texture CM_off is the only
immunity. (3) **the `texture-scale` prc rescales INSIDE
Texture.read()** (gated only by exclude-texture-scale name globs; ATS
does NOT exempt it; no post-hoc stamp can undo it) — but the
tex.load(PNMImage/PfmFile) route never applies it. (4) **Panda's TIFF
writer hard-crashes on 16-bit output** (native, no traceback, BOTH
engines — upstream behavior; reads are fine; intake must write PNG16).
Landed: `pax3d_render.data_texture(tex)` (post-hoc contract stamp:
CM_off + ATS_none + sRGB unflag + single-channel ushort/float
normalized to F_r16/F_r32; multi-channel formats untouched so RGBA8
splat weights ride clauses 1–3 only) and `load_data_texture(path)`
(PNMImage/PfmFile + tex.load route — texture-scale-immune,
VFS/multifile-capable). Gate: test_data_texture, 13 checks, run with
`compressed-textures 1` LIVE — 16-bit PNG + hand-rolled 16-bit TIFF
load at native precision; the anti-terracing probe renders a 1022-code
gradient at 161 distinct levels vs 9 for the 8-bit negative control
(probe proven able to fail); GPU round-trips byte-identical for R16
(file) and R32F (procedural set_ram_image) while an unstamped RGB8
canary comes back DXT1 (threat proven live); set_srgb_inputs leaves
stamped data alone on an M_modulate stage; texture-scale trap measured
real (512→128) with load_data_texture immune (512, byte-identical).
Identical results both engines × both baselines. ER-003 →
IMPLEMENTED ENGINE-SIDE; next: ER-001 TERRAIN_SPLAT variant (texture
arrays, splat-driven, v2 define seam), then ER-002 instancing
prototype + test_instancing.

**Session U part 2 (2026-07-19): ER-001 + ER-002 IMPLEMENTED + GATED —
the terrain lane's engine side is COMPLETE.** ER-001
(`set_terrain_splat`): TERRAIN_SPLAT variant of pax_pbr composed
per-subtree (glass mechanism, recompile-tracked, variants cached per
normals/ORM/macro combo) — 4-layer texture-array splat blend with
in-shader weight renormalization, per-layer uv_scale, splat-UV window
transform, macro brightness variation (mix(1, 2*macro, s) — 0.5 texel
= exact no-op), detail-normal distance fade, and an ANALYTIC world TBN
(u→+world_x, v→+world_y; chunk meshes carry no tangent column — the
NaN trap dodged by construction). sampler2DArray proven working on the
GLSL-120 path via GL_EXT_texture_array. The layer-weight function is
the isolated v2 seam (ratified: hex-tiling/height-blend land there as
defines). Gate test_terrain_splat: 12 EXACT analytic checks
(metallic-1 ambient trick; quadrants/blend/renorm/macro/uv_scale all
to 0.02, faded normals land on the ambient analytic to the third
decimal) + byte-identical opt-out + directional variant; green both
engines × both baselines. One instrument trap found and recorded: an
ortho camera ON the geometry plane has view distance ~0, so a
"force the fade" config needs edges below zero. ER-002
(`set_instanced`): INSTANCING define in pax_pbr.vert AND shadow.vert
+ F_hardware_instancing composed per-node; the global shadow shader
gains the define while any instanced node exists (glShaderContext's
identity fallback keeps other casters behavior-identical; caster
initial states invalidated on flip, the set_max_skinning_bones
pattern). ZERO C++ — upstream InstancedNode machinery did it all.
Three measured facts that beat the predictions: (1) an UNFLAGGED
InstancedNode renders every instance correctly (traverser per-instance
fallback) — set_instanced is a PERF switch (N draws → 1 instanced
draw), not correctness; (2) per-instance frustum culling is upstream
built-in; (3) `clear_shader()` keeps attrib FLAGS — a leftover
F_hardware_instancing with a non-INSTANCING shader collapses all
instances onto the node origin (found as an opt-out bug in the first
gate run, fixed in set_instanced(False), and kept as a deliberate
gate check that doubles as proof the HW path engages). Matrix
convention verified exact: Panda row-major affine memory = GL
column-major mat4x3, translation in column 3 → rms 0.00000 vs
CPU-transformed reference copies (45° roll + 1.5× scale). Instanced
shadow casting measured 4/4 under a 45° sun on both baselines. Gate
test_instancing; SKIPs on stock 1.10 (no InstancedNode — the version
gap documented). InstanceList Python surface pinned: node.instances
write-back property, append(pos,hpr,scale)/append(TransformState),
reserve; get_num_instances NOT published (len(node.instances)).
**Full gates: @game 60/6/85, @modern 59/7/85** — same documented FAIL
sets, four new rows green. NEW DOC: `ENGINE_INTERNALS.md` (user ask)
— the measured-mechanisms reference (texture degradation paths,
ShaderAttrib/multi-pass state resolution, the instancing chain, GLSL
notes, instrument traps), indexed in documents/README.md. All three
ER files stamped IMPLEMENTED ENGINE-SIDE with adoption snippets.
Remaining terrain-lane work is game-side adoption only.

**Session V (2026-07-19): the walkable-ship lane — ER-004 rigid clips +
ER-005 powered displays, both IMPLEMENTED + GATED same-session.**
Trigger: the ship dev's census of both Vattalus .unitypackages (sfb2
session 632, `MINERVA_CENSUS.md`) rewrote both ERs — no .anim files
exist; motion is FBX takes + prefab script-lerps; displays are six mp4
loops on VideoPlayer→RenderTexture Standard materials. ER-004:
`pax3d_render/rigid_clips.py` + `pipeline.get_model_clips()` — a
standalone GLB/glTF animations parser (reusing gltf_compat's accessor
machinery, sparse-densify pre-pass included) for the plain-node TRS
channels panda3d-gltf silently drops (its `animations` consumption
lives only in build_character; ENGINE_INTERNALS §5 born from this dig).
Axis conversion = the loader's own per-node conjugation
(csxform_inv·M·csxform, _converter.py ~224), applied per-component
(pos (x,y,z)→(x,−z,y), quat (x,y,z,w)→(w,x,−z,y), scale swap) and
PINNED in-gate against the loader's rest pose on the same file (0.0
err). Skin-joint/morph channels skipped — complementary to Actor by
construction. RigidClipPlayer: name-resolved targets (.missing/
.duplicates surfaced), seek(u)/apply(t)/reset(), stateless, LINEAR
slerp + STEP + CUBICSPLINE Hermite. RigidClip.from_delta()/add_delta():
the prefab script-lerp source as relative two-key clips (delta
premultiplies = local-frame compose, the Unity convention; game
validates on one door). Gate test_rigid_clips: in-test-authored GLB,
10 checks, green both engines × both baselines. ER-005: set_screen()
(albedo+emission bind at override 1, node texture state cleared first
— set_texture MERGES stages, two same-mode stages would compete for
the semantic sampler binding; byte-identical restore), set_emission_
scale/_color (new u_emission_factor uniform), set_uv_transform/
set_uv_scroll/play_flipbook (new u_uv_transform uniform, mat_uv =
v_texcoord*zw+xy on the standard material samples; scroll/flipbook
stepped by the pipeline task, O(active)/frame). Both uniforms
root-default exact no-ops riding every pax_pbr variant. THE video
fact: the Pax3D wheel builds --no-ffmpeg — MP4 decode does not exist
engine-side; the flipbook atlas is the sanctioned carrier
(tools/gen_flipbook.py, new — works with the machine's 2013-era ffmpeg
CLI, mp4→atlas tested end-to-end), with game-side set_ram_image
decoding as the alternative and "ffmpeg back into the build" queued as
a user decision in ER-005. Gate test_screen: 15 analytic checks
(quadrant-color map), every opt-out rms 0.0, PASSES on the routed
graphics.pax_pbr path too. **Full gates (4 runs, detached sequential
per the Window-4 ops note): @game 64/6/91 Pax3D · 62/6/93 stock,
@modern 63/7/91 · 61/7/93 — FAIL sets identical to the documented
pre-existing ones, zero regressions.** Both ER files stamped with
engine responses + adoption snippets + three questions for the ship
dev (video carrier decision for the user, screen-node split at
conversion, delta-rotation validation). Remaining: game-side adoption
on both ERs; hologram treatment stays deferred.

**Session V part 2 (2026-07-19): all three ship-dev questions RESOLVED
same day (ship-lane Session 634, measured; user sign-off relayed).**
(1) Video carrier = TRIMMED FLIPBOOKS — ffprobe on all six loops showed
three at 1–2.8 min (eDEX-UI 111.9 s, Quantum 59.8 s, EmotionGraphics
166.8 s), but they are ambient FUI dressing: intake trims each to a
10–20 s clean loop, atlases at ~10 fps / ~256×144 (worst case
≈4096×2048; ~100–140 MB RGBA8 for the whole shared six-material set).
**The ffmpeg build-window question is CLOSED — the build stays
`--no-ffmpeg`;** long-form video, if ever content, goes game-side
set_ram_image decode first. (2) Converter granularity confirmed: the
converter never merges geometry, the FBXs already model screens as
dedicated meshes — 49 screen renderer bindings / 6 shared materials
traced (Bridge 29; census's "≥4 rooms" corrected in the ER perf
envelope); interactive screens get named nodes + material clones (the
stacked-glass anti-flatten trick); materials stay shared because
set_emission_scale is per-node. (3) from_delta local-frame compose
VALIDATED AT THE SOURCE: VattalusInteractable.cs:248
`initialRotation * Quaternion.Euler(delta)` (Unity right-first) ==
our `delta * rest` (Panda left-first) exactly; position add likewise.
Axis conversion of delta VALUES stays game-side (ZXY-order quats
passed as quat_delta; Bathroom door + one cupboard as in-scene
validators). Bonus census correction: pack easing is SMOOTHSTEP
(two-key zero-tangent AnimationCurve), not linear — the game
smoothsteps `u`; a zero-tangent CUBICSPLINE channel is the equivalent
already evaluable in-store. Zero new engine work from the response —
the lane is now fully game-side (their handover task 1: the Phobos
console clip on the landed clip store). ER files trued up both repos.

**Session V part 3 (2026-07-19): ship exterior/status lights** (user
direction off the Minerva gold-standard screencaps: fixed hull-wash +
airliner-pattern blinking white/red/green, per-circuit on/off states —
"the 737NG lights panel is the form guide"; every NPC and player ship).
Cap analysis mapped the look to the existing split: top-deck whites +
ramp/underside floods are REAL lights (pool light on hull/ground),
small red/amber dashes are emissive-only markers. ONE engine gap
landed: `set_blink(np, period, pulses, phase, lights=, off_scale=)` /
`clear_blink()` — pulse-train envelope (pure pinned function) on the
node's emission factor, composing with the emission registry (setters
on a blinking node re-base instead of pushing — no one-frame pop),
optional real light nodes gated by the SAME envelope (originals
restored on clear), edge-triggered pushes (~4/s per strobe; a parked
fleet = comparisons only), per-ship phase to de-sync fleets. Gated:
test_screen 9b (envelope math pinned; pulse-ON/gap-OFF renders
byte-identical to the emission-scale states; light-node sync +
restore) — test_screen now 19 checks. Circuits model documented both
repos (position/beacon/strobe/floods as NAMED subtrees; each panel
switch = 2-3 calls, all byte-identical opt-outs; airliner numbers:
beacon 1.33 s/0.20 s, strobe 1 Hz double-flash 0.05+0.05@0.15).
**Light budget MEASURED (probe_maxlights, both baselines): with
shadows, max_lights 16/20/22 link+light correctly; 24 FAILS to link —
the v_shadow_pos[MAX_LIGHTS] varying array vs the ~128-component
varying budget. Recommend 16 (sun + 9 exterior floods + interior
fits); measured ceiling 22.** NPC guidance: emissive markers + bloom,
no real lights (the packs' own convention). Interior + shower-water
recipes = existing APIs (set_uv_scroll water sheet noted). Full gates
re-run green all four combos; totals unchanged except test_screen
19-check rows.

**Session W (2026-07-19): field triage — the alphaMode-MASK
core-profile drop, root-caused and fixed (fact #17).** Adoption watch
came back clean: ER-004 ADOPTED game-side (session 637 — the Phobos
console clip flows through the engine store; contract held in the
field at seek(0)==rest 0.0 err / travel to 1 mm / reset 1e-7),
ER-005/006 fully resolved, no open ship-lane asks. The one real field
defect was the character dev's note (PAX3D_FEEDBACK.md, evening): a
textureless MASK material (baseColorFactor alpha 0) rendered as an
opaque white shell over their hero's eyes. Root cause READ FROM THE
ENGINE SOURCE, then measured: panda3d-gltf expresses alphaMode MASK
as a geom-level `AlphaTestAttrib`, and the GL backend implements that
attrib ONLY behind `has_fixed_function_pipeline()` (glGSG
`do_issue_alpha_test` → `glAlphaFunc`) — under `gl-version 3 2` (the
planetside build) the attrib is SILENTLY IGNORED and every MASK
material renders opaque; pax_pbr.frag had no discard path. Identical
on stock 1.10.16 (upstream behavior, not fork damage — the
core-profile combine drop's sibling). Fix, opt-in per the house rule:
`pipeline.apply_alpha_masks(model_np)` scans the subtree's geom
states for keep-if-greater alpha tests and composes an ALPHA_MASK
compile of the PBR shader (cutoff baked as a define, per-distinct-
cutoff cache, glass-discipline recompile tracking) onto exactly those
geoms; root shader inputs/flags still compose through (ShaderAttrib
compose keeps un-set parent flags — verified in shaderAttrib.cxx),
the shadow camera's override-1 attrib still wins the depth pass, and
on compat the fixed-function test stays active alongside — same
predicate, so compat is BIT-identical (measured rms 0.00e+00).
Gated: test_alpha_mask (11 checks @game / 10 @modern; in-test GLB
with a factor-only shell + an 8x8-alpha-texture cutout through the
real loader; the pre-API defect is asserted per-baseline so a future
engine change forces a true-up; opt-out restores byte-identically).
Sample-geometry lesson re-learned in-test (fact #12): ortho rays are
parallel but v_view_position is not — off-axis specular falloff means
anchor comparisons must be SAME-PIXEL, and red-material checks must
expect gray specular on top (g-collapse vs anchor, not "r >> g").
Depth-pass caveat recorded, NOT fixed (no per-geom shadow-shader
mechanism; compat gets cutout shadows from fixed-function, modern
casts the unmasked silhouette): `exclude_from_shadows()` is the valve
for invisible shells; a cutout-shadow depth path lands only on field
evidence (foliage @modern would be the trigger). Also recorded: the
character dev's production datapoint for the GPU-morph queue item —
the CPU valve costs ~+2 ms on their 10,965-vert head module (185→133
fps), not the ~+0.1 ms of the 2,240-vert test head; ~5 close-up
morphing faces ≈ 10 ms CPU. Sharpened the queue-row evidence, no
reprioritization (still behind field-driven demand). Intermittent
`GL error 0x502` observed ONCE during ShowBase init in paxtest runs
(before pipeline init, either baseline, checks unaffected) — driver
init noise on this machine, noted so nobody chases it as a
regression.

**Session W part 2 (2026-07-19): the eyeball rigs — testbed keys for
the Session-V AND outstanding Session-S features** (the Phase-2
headline from the Session-V handover; sfb2 commit `daaf291`,
test3d_pax.py only, filtered staging). All lazy-built (scene untouched
until the key): **P** cycles the showcase display panel (off →
whole-atlas test card → play_flipbook 8 fps on a procedural 4×4 sweep
atlas (no asset dependency — bar position + frame-counter strip make
fps/looping eyeballable) → set_emission_scale 0 powered-off →
clear_screen restore + stash); **C** toggles nav-light circuits on the
destroyer per the ER-005 addendum airliner grammar (red beacon 45/min
with a REAL PointLight gated by the same envelope, white 1 Hz
double-flash wingtip strobes, steady red/green position markers —
markers are set_screen-emissive billboards so the whole chain is
public API); **Y** toggles a clip-driven door slab
(RigidClip.from_delta + RigidClipPlayer + game-side smoothstep drive —
the exact Minerva prefab-lerp shape); **F/Q** close the Session-S key
gap (set_enable_lens_flare / set_enable_ssao runtime toggles).
Verified headless: full key-path drive (states, stash/restore, door
travel measured moving) + showcase screenshot
(`screencaps/pax_testbed_sessionw_showcase.png` — flipbook mid-sweep,
door mid-travel, markers lit); plain --selftest byte-unchanged boot.
Driver trap worth remembering: Panda resolves relative model paths
against MAIN_DIR (the started script's directory), not cwd — a
scratchpad driver script "loses" the game's GLBs while the direct run
loads them; run drivers via stdin from the game dir.

**Session X (2026-07-19): the viewmodel answer + the offscreen GL
defect — both FPS-lane items closed engine-side, same day they were
written.** (1) The near-plane question (FPS_WEAPONS_KIT.md §5, drafted
but not yet filed): answered by implementation —
`pipeline.register_viewmodel_camera(vm_root, near, far, fov,
depth_mode)` is the blessed foreground display region (own camera and
near/far, drawn after the world into the SAME HDR scene buffer, so
tonemap/bloom/TAA apply identically; PBR lighting parity measured
0.848 == 0.848 against an identical world surface). The five-step
mask/shadow/clear folklore is pipeline-owned: draw bit 29 reserved
(shadow camera always clears it — zero texels in the sun depth map,
gated), main camera mask restored exactly on unregister, region +
depth state auto-reattach across FilterManager rebuilds. Two depth
modes, both measured by scene-depth readback: 'clear' (default;
stomps the buffer's depth — SSAO reads garbage) and 'range'
(glDepthRange [0,0.05] compression; world depth byte-preserved —
SSAO-friendly; needs the fork's DisplayRegion.set_depth_range, falls
back to 'clear' on stock 1.10, and is documented-incompatible with
enable_log_depth: gl_FragDepth is CLAMPED to the region range, not
rescaled). Gated by test_viewmodel (15 checks; 17 @directional incl.
shadow-map texel diff; runner adds the @directional variant), green
both engines × both baselines; defect row pins WHY the API exists
(near 0.3 clips a 0.12 m card). (2) The GL_INVALID_OPERATION field
report root-caused to two upstream one-liners — see fact #18: the
"playing character" attribution was wrong (empty scene errors
identically); real cause `glDrawBuffer(GL_BACK)` on the
single-buffered wgl pbuffer (upstream bd4dc8a379, a DX9 fix,
pre-divergence — in EVERY Pax3D wheel ever built), plus the
`gl-max-errors -1` bare `>=`. C++ fixes queued for a mini window
(`PATCH_QUEUE_GL_OFFSCREEN.md`); probe_gl_errors.py holds the matrix;
test_gl_clean asserts the defect per-engine and flips "the good way"
when the patch lands. TRUE-UP: Session W part 1's "GL error 0x502
once during ShowBase init = driver init noise" note is superseded —
that was this defect (the 1/sec sweep fires once in a short real-time
window; pin the clock to dt>1 s and it is 1/frame, every offscreen
run, since the fork began).

**Session X part 2 (2026-07-19): the GL mini build window LANDED +
same-day viewmodel adoption.** User authorized the window; both
fact-#18 one-liners applied exactly as queued in
PATCH_QUEUE_GL_OFFSCREEN.md (get_buffer_mask single-buffered branch
restored with a PAX3D tag; gl-max-errors -1 honored). Build 1 min 0 s
incremental, exit 0; wheel live in pax3d-env + archived
wheels_session_x\. Verified: probe_gl_errors 0 errors/frame in EVERY
phase both baselines (was ~60/phase); test_gl_clean flipped to its
permanent form — the same zero-GL-errors assertion on both engines;
full gate green, totals unchanged from part 1. ADOPTION: the FPS lane
wired register_viewmodel_camera the same day (sfb2 be4072b / session
643d; field report openworld/PAX3D_FEEDBACK_3.md addendum 3) — scale
fallback deleted, scene-switch register/unregister cycling green,
harness pixels byte-identical to the approved shots; near 0.02/far
8.0/fov world-copy/'clear' recorded; M2 layers sway on reg.camera_np
and runs the 55-65 degree fov taste test. OPERATIONAL: the terrain dev
is sweeping the machine so nothing runs stock Panda3D by accident
(the user had been launching planetside via a command resolving to
system Python = stock 1.10 — re-check pre-fork eyeball feedback on
pax3d-env). Engine-lane constraint filed in PAX3D_FEEDBACK.md: exactly
one deliberately-stock environment must survive the sweep (today:
C:\Python313) or the cross-engine gate loses its upstream reference —
coordinate before converting system Python.

**Session X part 2 addenda (2026-07-19, same evening):** (a) The
machine engine-pinning sweep landed mid-gate (game `ee861db`/643c):
C:\Python313 now carries the FORK machine-wide; the stock reference
moved to `C:\python\stock-panda-env` (1.10.16 + gltf 1.3.0 +
simplepbr 0.13.1, engine-dev-only). All canonical paxtest commands
repointed (CLAUDE.md, README, probe docstrings); the one gate run that
had used converted-C:\Python313 as "stock" was fork-vs-fork and was
re-run against the real testbed. Fact-#11 discipline now explicitly
extends to the INTERPRETER: confirm which python/wheel produced a
field report before reproducing (the user had been eyeballing
planetside on stock 1.10 via the old system-python resolution).
(b) Instrument lesson (fact-#12 class): the GL fix sped offscreen
frames up and test_screen's `uv_scroll_animates` failed rms 0.00000
under gate load @modern — the scroll advances by wall-clock seconds
(the game-facing contract), so 30 fast frames moved the UV sub-pixel.
Fixed by pinning the global clock (M_non_real_time, dt=1/30) at test
start; rms now 0.14060 deterministic on all four configs. Any future
"did it move over N frames" check must pin the clock.

**Session Y (2026-07-20): the game→engine ER queue cleared — hex
tiling, light policy, Round-5 env asks** (master plan §4.11). ER-007
hex-tiling landed at the ratified v2 seam: `set_terrain_splat(...,
hex_tiling=True, hex_cell_size, hex_rotation (per-layer),
hex_contrast)` — Mikkelsen-style 3-tap stochastic retiling whose
per-cell transforms are CONSTANT, so every tap's UV stays continuous
where its weight is nonzero and plain sampling mips correctly on both
GLSL baselines (no textureGrad — the design fact); normals ride the
cells with back-rotated tangent xy. test_terrain_splat +12 checks
(shift-rms 0.0014→0.2296 periodicity break, anisotropy contract,
byte-identical opt-out). ER-008 answered from the C++ then measured:
light overflow uploads the `Light.set_priority()`-sorted head (ties
spot > directional > point, equal ties ARBITRARY), excess silently
dropped — so `_create_sun_light` now pins the directional-mode sun at
priority 1<<20 (default-on guard: overflowing floods would have
evicted the sun and its shadows), and `set_light_budget(root, lights,
budget, ...)` adds the per-root nearest-N warden (budgets LOCAL per
hull; blink-steady scoring, rebind only on membership change). Bonus
fact on record: zero-light draws render with a default WHITE slot-0
light (GSG default fill). Round-5 env asks all three landed:
`set_env_scale(np, s)` (per-node, ibl_spec only), `set_env_intensity(s)`
(global, composes), `set_env_map_rotation(deg)` (specular yaw, skybox
set_h sense); test_env_map +5 exact checks. New test_light_priority
(+@directional). Gate @game 71/6/106 Pax3D · 69/6/108 stock; FAIL sets
unchanged.

**Session Z (2026-07-20): GPU morphs — fact #15 closed opt-in**
(master plan §4.12). The queued GPU morph path landed as pure
Python/GLSL per canon — no build window, works unchanged on stock
1.10. `set_gpu_morphs(np)`: per-vdata RGB32F delta texture (position +
normal deltas per target, the ER-003 data-texture contract), a float32
`morph_index` vertex column for both-baseline addressing (no
gl_VertexID), and a GPU_MORPHS variant composed per-geom at the
alpha-mask seam — morph sliders now render ON the hardware-skinning
path. All 52 ARKit targets addressable, ≤16 live (the character lane's
contract), O(sliders) per-frame push. test_morph_gltf +5 checks: GPU
matches the CPU valve at rms 0.0000 (bar 0.02), opt-out byte-identical.
Perf (hero_wren, 14,684×52, 8 faces × 5 sliders, offscreen 512²):
~0.3 ms morph-attributable (acceptance ≤0.5 ms); the CPU valve on the
same scene is 63.5 ms/frame. Known limits documented and
field-evidence-gated: shadow pass casts the unmorphed silhouette, one
PBR variant per geom, requires the HW-skinning path. Gate totals
unchanged (the row grew internally).

**Session AA (2026-07-21): ER-007 height blend + hex world-anchor,
ER-009 cutout alpha** (master plan §4.13). Both watched-for arrivals
came in together (terrain dev 651/652) and landed same day.
`set_terrain_splat(..., height_blend=True, height_sharpness=8.0)` —
TERRAIN_HEIGHT_BLEND resharpens splat weights by a height softmax
(`w_i · 2^(k · albedo_i.a)`, renormalized): blend borders follow the
height texture instead of crossfading. The FORM is the contract —
equal heights cancel as a common factor, so the terrain dev's pinned
all-flat-palette no-op requirement holds BY CONSTRUCTION (measured rms
2.6e-06), and a flat-128 slice competes at its constant middle
(analytic-exact). `hex_offset=(u, v)` world-anchors the hex cell hash
— the chunk-border motif seam vanishes when each chunk passes its
world offset (UV-window equivalence gated, rms 0.0005). ER-009:
`apply_alpha_masks` now also detects `TransparencyAttrib M_binary`
(geom- or node-level, predicate a ≥ 0.5 = the cull semantic) and takes
`instanced=True` to compose INSTANCING into the mask variant — the
origin-collapse flag/shader pairing trap is now itself a gate check
(0/4→4/4). The ER's "shadow pass already discards" premise did not
survive mechanism review (no depth-path discard exists; fact #17
stands) and was corrected in the response. test_terrain_splat +14 /
test_alpha_mask +10 checks; gate totals unchanged all four configs.
Both riders adopted game-side the same day (sfb2 s663).

**Session AB (2026-07-21): GPU morph crowds — zero-copy bake,
independent clone faces** (master plan §4.14). Probing before building
found fact #20: Panda wrapper `id()` is unstable — two lookups of one
C++ object return different wrappers, so key caches by `.this`; and
`copy_to` on a Character DEEP-COPIES vdata while pointer-sharing
textures (the Session-Z "clones share vdata" claim was a wrapper-id
artifact). The delta texture flipped VERTEX-MAJOR — byte-identical to
the loader's own interleaved morph-column array — so a canonical-order
vdata uploads its raw bytes directly: enable cost 1.17 s → 0.07–0.08 s
per face on all three shipped heroes (~15×; numpy column gather for
non-canonical orders like kade's, pure-Python floor kept, all three
bake paths byte-compared in-gate). `set_gpu_morphs(clone)` on a
copy_to clone now reuses the pointer-shared delta textures (ZERO
re-bake) and registers the clone's OWN sliders + uniform block —
without the call every clone in a plaza wears the template's face.
test_morph_gltf → 17 checks/config. Perf re-measured with an
interleaved min-of-5 A/B (single-run deltas drifted 0.4–0.8 ms under
machine load — the bench trap on record): 8 faces × 5 sliders
= 0.19 ms morph-attributable; 32 independently-driven clones 4.3 ms;
24 clones copy+register in 0.25–0.49 s. Gate totals unchanged.

**Session AC (2026-07-23): R1 CLOSED — sign-offs, one graphics
reality, GLSL-120 deletion** (master plan §4.15; commit `e67c989adb`).
The program's oldest open phase closed in three user-gated steps.
(1) "directional signed off" closed R2 (watch item: planetside shadow
stripes at certain angles, not reproducible in the testbed — capture
sun az/el on recurrence); "sRGB flip approved" closed R1.3 — the
user's "no difference" read was mechanically checked first (the
testbed's ONE sRGB-eligible texture shifted 27.7% of pixels at rms
0.092 — real, subtle, approved), and `srgb_inputs` + the boot re-walk
were wired game-side same day. (2) One graphics reality: the census
found `plan.py` had NO gl-version — the main game had been booting
COMPAT daily; `gl-version 3 2` landed in every entry point, and the
user played a session under core: "core signed off." (3) R1.4
executed: all 16 shader sources baked to native GLSL 330 (the exact
swaps the runtime transform performed — preprocessor-equivalent
compiled text), shaderutils transform + IS_WEBGL machinery deleted;
compat contexts warn loudly and remain diagnostic-only. **Gate
redefined: both engines × ONE `game` baseline (= gl 3 2); totals
Pax3D 70/7/106 · stock 68/7/108 — identical to the historical @modern
column, FAIL sets unchanged (the bake-equivalence proof).** Latent
test defect fixed on the way: test_alpha_mask keyed its compat legs on
the baseline NAME instead of `h.use_330` — key baseline logic on the
context, never the name.

**Session AD (2026-07-23): effect sprites — baked explosion footage,
spawn_effect** (master plan §4.16; field guide
`BAKED_EFFECTS_GUIDE.md`). The VFX lane opened: the user bought the
CGVision "Air and Space Explosions" pack (28 ProRes 4444 MOVs,
alpha+beauty, `C:\python\asset_sources\Explosions\`); intake MEASURED
the footage premultiplied (RGB ≤ alpha everywhere except a deliberate
additive spark tail) — bake as-is, no conversion.
`pipeline.spawn_effect()` landed as a composition of already-gated
parts, zero new shader code: `set_screen(albedo=False, metallic=1)`
makes the quad analytically unlit (black metallic base zeroes
diffuse_color AND spec_color exactly — only emission survives,
HDR-legal for bloom), `set_glass()` gives premultiplied blending with
coverage-weighted fog/atmosphere inscatter, `exclude_from_shadows()`
applies when a caster mask exists (fact #17), and `play_flipbook()`
steps the frames; one-shots self-reap through the public clears so
every registry returns to empty (byte-identical-when-unused held at
rms 0.0 in-gate). `tools/gen_flipbook.py` grew alpha awareness
(ffprobe detection, `-pix_fmt rgba` extraction, RGBA atlas + `alpha`
sidecar field; RGB sources byte-identical to the old tool — both
proven in-gate). The "2013 ffmpeg" note was stale: the machine runs
winget ffmpeg 8.0.1, which decodes ProRes 4444 alpha cleanly. Gate:
NEW test_effects, 13 analytic checks ×@game/@directional, identical
on both engines — **totals now Pax3D 73/7/109 · stock 71/7/111** (+3
PASS +3 SKIP each = the 6 new effects jobs; FAIL sets unchanged).
First adoption same session (sfb2, uncommitted): `5_1.mov` baked to a
51-frame 12.5 fps atlas (0.8 MB, `assets/effects/`) and planetside's
WeaponEffects plays it on NON-ground detonations (grenade airbursts +
map-edge; ground hits keep the corona+dust read; missing pipeline or
atlas ⇒ old behavior untouched). Docs trued up both repos; the
bake→spawn workflow guide `documents/BAKED_EFFECTS_GUIDE.md` born this
session.

**Session AE (2026-07-24): ER-010 wet-sand waterline —
set_terrain_water** (master plan §4.17; arch doc Session AE section).
The water dev's Session-690 water package (depth-alpha shallows, shore
melt, foam) exposed the terrain half of the Sea-of-Thieves shore look:
sand above AND below the contact line rendered bone-dry. ER-010 landed
same-day, the suggested API shape plus the stretch goal:
`set_terrain_water(chunk_np, water_z, band_m, dark, rough_mult, sat,
anim_amp, anim_period, anim_scale, anim_phase)` — a TERRAIN_WATER
rider on the terrain-splat variant (6th cache key; the v2 layer-weight
seam untouched — water modifies the outputs after the weights).
Wetness is by WORLD Z only, all layers alike; submerged terrain is
FULLY wet (the seafloor headline); wet albedo = dark multiplier +
chroma expansion about Rec.709 luminance (commute exactly), wet
roughness = rough_mult ahead of GSAA (the sheen is a specular read —
white-env gate check brightens 0.737→0.827 at rough_mult 0.12). The
breathing edge: `amp·sin(phase + 2π·noise(world_xy/anim_scale))`,
phase driven from _update (zero cost when unused), `anim_phase` pins
it for determinism. Every consumer goes through `mix(dry, wet, w)` so
wet==0 fragments compute the water-off arithmetic bit-exactly;
`set_terrain_splat` re-calls PRESERVE the water contract (re-dressing
must not silently dry the shore). Gate: NEW test_terrain_water, 17
checks ×@game/@directional, identical on both engines — **totals now
Pax3D 75/7/113 · stock 73/7/115** (+2 PASS +4 SKIP each = the 6 new
terrain_water jobs; FAIL sets unchanged). Engine response filed in the
ER file game-side; adoption is one call in materials.py next to
set_terrain_splat (feature-probed, ER-009 pattern).

**Session AE addendum (2026-07-24): ER-012 glTF tangent synthesis —
filed-as-answered, zero engine work** (master plan §4.18). The
ship-intake lane's ask (synthesize tangents for the 158/246 fleet GLBs
whose normal-mapped primitives lack TANGENT — Blender won't export
tangents on n-gon meshes) is ALREADY the shipped behavior:
panda3d-gltf's `calculate_tangents` runs at convert time on every UV'd
primitive without TANGENT, and the model cache stores the result.
Probed on the ER's own meshes (`tools/probe_tangent_synthesis.py`,
new): SR4 and Hermes load with 0 geoms missing the tangent column.
Mechanism correction filed: pax_pbr has NO draw-time derivative
fallback — genuinely missing tangents under USE_NORMAL_MAP go
NaN-black, so black = loader regression, shimmer/seams = tangent
quality (mikktspace exactness + rare degenerate-UV zero tangents; both
watch-gated LOW on the ER's own trigger). Housekeeping: the lane filed
it as "ER-010", colliding with the wet-sand waterline filed the same
morning — renumbered to ER-012 (git mv, staged game-side), index
trued up (ER-009 row was stale-OPEN, ER-011 was missing).

**Post-AE lighting consult (2026-07-24): fleet look, flood lamps,
interiors, flare occlusion — answers on record, ER-013 filed.**
(1) Nav lights at fleet scale: the perf question is already solved —
set_blink is an emission envelope (near-free at any ship count), real
spill is ER-008-warded; adoption recipe delivered game-side
(`ENGINE_UPDATE_2026-07-24_NAV_LIGHTS_FLEET_RECIPE.md`); confirmed
config-side bulb placement (nozzle precedent), no baked GLB anchors —
the Pitbull rebuild proceeds unblocked. **ER-013 `set_light_halo`
FILED** (engine desk, on the ship lane's request): min-screen-size
camera-facing sprites = the km-range readability piece; depth-tested =
free occlusion; composes with the blink registry; accepted in
principle, proposed API + gate plan in the ER, candidate next slice.
(2) Flood lamps: mechanically we HAVE them — Spotlight through the
forward path with smooth cone edge (SPOTSMOOTH), spot shadows, spot >
point in the ER-008 class rank, measured in test_local_lights; gaps =
per-light penumbra control (shader ignores spotExponent — small gated
GLSL item if wanted) and volumetric shafts (separate, evidence-gated;
authored translucent cone is the cheap game-side stand-in).
(3) Interior vs exterior light: adoption contract, not an engine gap —
Session S built the valves for exactly this: `set_light_off(
pipeline.sun_light_np)` on the interior subtree (exact, free; do NOT
rely on shadow maps to darken enclosed spaces — leak-prone),
`set_ambient_scale(interior, ~0)`, per-subtree `set_env_map`/
`set_ambient_sh`, `set_atmosphere_scale(interior, 0)`.
(4) Flare-through-hull: TWO flare systems exist — the engine's
Session-S bright-extract ghosts are occlusion-implicit (wall covers
sun ⇒ no extract energy ⇒ no flare, gated); the through-wall offender
is the game's legacy sprite flare (sun_lens_flare.py) whose
hand-registered ray-sphere occluders can't express "camera is inside a
hull". Proposed engine fix: a depth-tap visibility query
(`query_sun_visibility`-class API — tiny GPU pass sampling scene depth
around the sun's screen position, one-frame-latent readback, no stall)
that retires ALL hand-built occluders; Python/GLSL only, gate:
behind-wall=0 / open-sky=1 / half-covered≈0.5. Clustered-forward
backlog row sharpened (§4.7): direction recorded, evidence-gated,
trigger + ingredients named.

**Session AF (2026-07-24): the lights slice — ER-013 halos,
visibility queries, spot penumbra** (master plan §4.19; arch doc
Session AF section). All three consult items landed + gated same day,
pure Python/GLSL, byte-identical when unused. (1) `set_light_halo`:
view-space-expanded additive quads, `size = max(size_m, min_px /
px_per_world)` from proj[1][1]+clip-w (exact for perspective AND ortho
— one formula), falloff (1-r²)² (center exactly 1 = the analytic
anchor), depth-tested/no-write, OmniBounds (the shader resizes the
card), shadow-mask excluded, LOG_DEPTH gl_FragDepth like pax_pbr
(recompile-tracked); halos inherit u_emission_factor ⇒ blink circuits
drive them for free. (2) `add_visibility_query` + `VisibilityQuery`
handle: K×1 buffer via make_texture_buffer(to_ram) sorted BEFORE every
FilterManager buffer — reads LAST frame's depth so RTM_copy_ram waits
only on the 16×1 quad itself (no mid-frame stall); 16-tap sqrt-spiral;
targets' depths pre-scaled ×0.995 so a depth-writing sun billboard
can't occlude its own query; `max_occluder_depth` = the sky-dome
valve; measured latency exactly 2 frames. Depth target now requested
when `enable_ssao OR enable_visibility_query` (both-on coexistence
probed). (3) `enable_spot_exponent` (SPOT_EXPONENT define +
conditional struct member): GL_SPOT_EXPONENT semantics; opt-in
because Spotlight's class default is exponent 50 (spotlight.I:19 —
measured; Light base returns 0), guard `pow(max(spotcos,1e-4), e)`
inside the cutoff branch only. Gate: 3 NEW tests (light_halo 10+1,
visibility_query 7+INFO, spot_exponent 7) ×@game +@directional/
+@logdepth — **totals now Pax3D 81/7/125 · stock 79/7/127** (+6 PASS
+12 SKIP each; FAIL sets unchanged, identical engines; all three
features PASS on stock 1.10). Two test traps met and encoded: the
half-max size prediction must be solved THROUGH the tonemap curve
(linear-space 0.541 → post-curve 0.728 — the near_size FAIL taught
it), and a lights-free scene needs a BLACK AmbientLight or the
zero-light white-flood quirk lights the occluder card (Session-Y fact,
now in a gate). Docs: arch doc §AF + testing contract, paxtest README
snapshot + 3 entries, master plan §4.19, game-side
ENGINE_UPDATE_2026-07-24_SESSION_AF_LIGHTS.md, ER-013 →
IMPLEMENTED + GATED (same day as filing). Engine work uncommitted.

**Session AG (2026-07-24): the GVAD stability build window — the
handle-race fix lands** (master plan §4.20; fact #21). User go-ahead
on the queued P0 (2026-07-23 "report only" hold lifted). Housekeeping
first: the AD/AE/AF backlog committed (`18a70ea964`) so the wheel maps
to a clean commit. The fix (`d6044b1d8a`), three sites exactly per
CRASH_GVAD_HANDLE_RACE.md §6: makepanda.py keeps `USE_DELETED_CHAIN=
'1'` alongside mimalloc (our wheels were the first EVER to run the
Geom churn on a general-purpose allocator); both cycler stage guards
back to `#ifndef NDEBUG` (compiled out at opt-3 since the upstream
demotion — 1.10.16 release wheels ran them); `set_num_stages` frees
the OLD CycleDataNode array instead of `&_single_data` (upstream
reassigned before the delete[] — an interior pointer of the live
object, plainly visible once read). Crash baseline re-proven on the
Session-X wheel (AV < 60 s, exit 0xC0000005), `built_x64\` deleted
(flag change = mandatory clean build), full build 11 min 54 s / 20
threads. Acceptance ALL GREEN: 9/9 previously-crashing repro rows
survive (0.1–4.1M builds/60 s; deep soak 6.9M/120 s;
`MATRIX_RESULT: ALL_SURVIVED`); full gate both engines FAIL-sets
unchanged — **totals now Pax3D 82/7/129 · stock 80/7/131** (+1 PASS
+4 SKIP each = NEW permanent `test_gvad_churn`, the crashing recipe
promoted into paxtest and proven three ways at introduction: FAIL on
the pre-fix wheel, PASS on stock 1.10.16, PASS on the fix — an
interesting aside: the fixed wheel out-churns stock ~2.8× on the
handle-only row, DeletedChain is also fast); testbed selftests
(test3d_pax, test3d_ftl) green; plan.py boot smoke alive at 75 s with
only pre-existing content warnings (the Session-R combine warning
included, still doing its job). Wheel installed in pax3d-env AND
system Python, archived `wheels_gvad\` (rollback: `wheels_session_x\`).
Game side: ER-011's main-thread mitigation no longer load-bearing;
`ENGINE_UPDATE_2026-07-24_GVAD_STABILITY_WHEEL.md` filed. Docs trued:
CLAUDE.md (queue row DONE, env table, wheels, C++-changes line, gate
totals), crash doc status FIXED+VALIDATED, paxtest README (test entry
+ snapshot), master plan (§4.20 + fact #21). Gate logs
`gate_gvad_pax3d_game.log` / `gate_gvad_stock_game.log`.
