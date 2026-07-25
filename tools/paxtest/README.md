# paxtest — Pax3D graphics test harness

Standalone, seconds-fast graphics tests for the Pax3D rendering program
(Phase R0 of `documents/PAX3D_MASTER_PLAN.md`). Tests real pipelines against
analytic expectations by rendering offscreen and reading pixels back — no
need to launch Pax Abyssi and eyeball the result.

## Quick start

```bash
# Full matrix (any Python that has panda3d):
C:/python/stock-panda-env/Scripts/python.exe tools/paxtest/run.py   # stock engine
C:/python/pax3d-env/Scripts/python.exe tools/paxtest/run.py   # Pax3D engine

# One test, one pipeline:
C:/python/stock-panda-env/Scripts/python.exe tools/paxtest/test_bloom.py --pipeline pax_pbr

# Subset / options:
python tools/paxtest/run.py --tests gamma,bloom --pipelines pax_pbr
python tools/paxtest/run.py --baseline compat     # diagnostic: compat context
```

Exit codes: 0 pass, 1 fail, 77 skip. Each test prints per-check lines and a
machine-readable `PAXTEST_JSON:` line; the runner aggregates into
`output/last_run.json`. Captures land in `output/*.png` — always look at the
pictures when a check fails.

## Pipelines under test

| Name | What it is |
|---|---|
| `none` | Raw Panda3D, no post-processing. Control — validates the harness itself. |
| `simplepbr` | Stock pip simplepbr. Known-good reference for PBR conventions. |
| `pax3d_simplepbr` | The old fork in this repo. Retired — superseded by pax3d_render. |
| `pax_pbr` | The game's local pipeline, imported from `C:/python/sfb2`. |
| `pax3d_render` | **The unified R1 pipeline in this repo** — the successor both of the above merge into. |

`--baseline game` (default) mimics sfb2 PRC: `gl-version 3 2` (the game
sets it in every entry point since 2026-07-23; the GLSL-120 dual path
was deleted the same day, R1.4). `modern` is a legacy alias of `game`.
`compat` is DIAGNOSTIC ONLY (no `gl-version` → compat context; the
pipeline still emits GLSL 330 and warns) — not part of the standard
gate, kept for fixed-function-interplay archaeology (fact #17 class).
The standard gate is now both engines × the ONE `game` baseline.

## Tests

**`test_gamma.py`** — renders bars of known scene-linear values (LDR 0–1 and
HDR 0–4 rows) through the pipeline, compares the framebuffer against the
analytic tonemap curve for every operator. On failure, reports the best-fit
hypothesis (double-gamma / missing gamma / no tonemap). Also reports whether
8-bit textures are sRGB-decoded on sampling (the input half of the color
contract).

**`test_lighting.py`** — game-winding sphere, reversed-winding sphere, and a
GLTF ship from sfb2, lit from each cardinal direction through the pipeline's
native sun mechanism (`update_sun()` uniforms for pax_pbr, a real
`DirectionalLight` + `set_direction()` elsewhere). Asserts the lit hemisphere
faces the sun. Also documents whether a real DirectionalLight is consumed.
For pax3d_render, `--sun-mode directional` runs the same checks through the
real-DirectionalLight sun (R2) — the runner does both variants automatically.

**`test_bloom.py`** — black scene + one small HDR emissive quad, bloom on.
Asserts a halo exists and decays smoothly (max adjacent-pixel step, outward
brightness jumps, symmetry). Runs at 512x512 (divides evenly through the 1/32
mip chain) and 960x540 (doesn't) to localize truncation bugs.

**`test_rebuild.py`** — auxiliary background camera (the sky-camera pattern)
plus a bloom toggle, which rebuilds the FilterManager chain. Asserts the
auxiliary region still renders afterwards. Legacy pipelines attach the
sky_camera.py way and FAIL (that's F4); pax3d_render attaches through
`register_scene_camera()` and passes.

**`test_shadows.py`** — occluder sphere on the sun ray above a larger
sphere, `sun_light_mode='directional'` + `enable_shadows`. Asserts the
occluded pole darkens to ambient, restores on toggle-off, and re-darkens on
toggle-on (the toggle exercises the runtime shader-recompile path, which
once wiped all shader inputs — guarded here). Session D adds the off-origin
extent checks: geometry outside the frustum samples LIT,
`set_shadow_extent(center=...)` recenters onto a far cluster, and
positioning the light node leaves lighting bit-identical. Session E adds
the skinned casters (egg-synthesized sheet: depth texels, ground darkening,
shadow-follows-pose), and a real panda3d-gltf Actor as caster — whose
ground-darkening line was promoted from `[info]` to the hard assertion
`gltf_caster_darkens_ground` in Session G (openworld ask #1). Two traps
are encoded there: `get_anim_names()` ordering is nondeterministic (the
anim is now sorted and the pose pinned), and the "pole" sample pixel is
the sphere's FRONT surface (world y=-0.76), which a thin standing caster
does not shadow — the actor is y-shifted to put its trunk's shadow column
over the sampled point. The `--soft-skin` variant reruns everything on the
CPU-skinning path. Skips pipelines without the directional sun mode.

**`test_shadows_gltf.py`** (Session G, openworld ask #2) — lit-pass
shadows with glTF-material geometry as BOTH caster and receiver, under a
45-degree ANGLED sun. Synthesizes a .gltf scene in-code (textured ground
plane + box, real `baseColorTexture` sampling through panda3d-gltf — the
flat-color scenes demonstrably cannot catch this class), asserts the box
darkens the textured ground, and repeats with the pack-1 openworld
character as caster when the asset is present. Guards
`receiver_is_gltf_material` so the test can't silently degrade to the
flat-color path. Session L: the actor's anim pick is now `sorted()`
(the fact-#12 pin this file had missed — the unsorted pick flaked
run-to-run as the pose wandered around the darkening threshold).

**`test_shadow_quality.py`** (Session E) — angled-sun analytic shadow
placement, the normalized-bias trap (measured record), `shadow_bias_world`,
3×3 PCF widening, and `exclude_from_shadows()` — top-down over a ground
plane so every expected shadow position is computable.

**`test_shadow_grazing.py`** (Session I, openworld P0 addendum) —
grazing-angle self-shadow acne and the slope-scaled bias fix
(`shadow_normal_bias_world`). Low sun over flat ground so grazing is set
purely by altitude; measures the pure shadow term (mode 11) as a
black-fraction. Asserts acne present at `normal_bias=0`, cleared when set,
a real caster's umbra retained (no peter-pan), and — with teeth — that a
too-large value erodes the real umbra. The mechanism gate; the varied-
terrain proof is `probe_openworld_scale.py --normal-bias`.

**`test_shadow_snap.py`** (Session J, planetside package) — shadow-frustum
texel snapping (`shadow_texel_snap`). Measures the shimmer source first
(with snap off, a 0.3-texel `set_shadow_extent` center move re-rasterizes
the depth map), then asserts the anti-shimmer property: with snap on, a
sub-texel center sweep leaves the depth map AND the screen byte-identical,
while a whole-texel move still re-rasterizes (the frustum follows, in
texel steps). Default-off and toggle-off byte-identity are asserted.

**`test_atmosphere.py`** (Session J / R5.1) — aerial perspective / height
haze (`enable_atmosphere`). Analytic checks: a black card at distance d
through a uniform medium renders at exactly
`curve(haze * (1 - exp(-density*d)))` (three distances); a horizontal ray
above the scale height carries almost no inscatter; the inscatter tint
follows the sun (forward-scatter lobe); `density=0` with the feature
compiled in is byte-identical to off; disabling restores the baseline
capture exactly.

**`test_ambient_sh.py`** (Session J / R5.2) — environment-driven ambient
through the shader's existing (previously zeroed) `sh_coeffs` path.
Asserts the hemisphere ambient analytics per channel (up-facing card gets
`base*kd*(avg + 2/3*delta)`, down-facing the ground-bounce mix), that the
coefficients survive a recompile-class toggle, that `clear_ambient_sh()`
restores the baseline byte-identically, and that `sh_from_cubemap()`
reproduces the analytic hemisphere coefficients from a synthetic cubemap
(math-only check, no rendering). Session Q adds the face-table PIN
(closing the orientation question the openworld marker rig validated
in-app): six solid-color face files through `loader.load_cube_map` land
file N on GL face N with content intact, the file → SH → irradiance
chain names every compass marker correctly, and a gradient up-face file
proves the up-face image's TOP row is the SOUTHERN sky.

**`test_glass.py`** (Session K) — specular-preserving glass
(`set_glass()`). A flat card with the sun exactly on the view axis makes
every BRDF dot product 1, so both transparency paths are analytic:
measures the M_alpha defect (the whole result × alpha — the highlight
loses 2.07× at alpha 0.15), asserts the glass path keeps specular at
full strength and matches its curve exactly, that a known-value
background transmits at exactly (1−a) through the premultiplied blend,
that the per-node variant survives a recompile-class toggle, and that
`set_glass(np, False)` restores the M_alpha capture byte-identically.
The `@directional` variant covers the GLASS split in the
p3d_LightSource loop (uniforms mode never enters it).

**`test_doublesided.py`** (Session K) — double-sided lighting
(`double_sided_lighting` / `set_double_sided_lighting()`). The same
analytic sun-on-view-axis card as test_glass, opaque and two-sided,
shown to the camera back-first: measures the defect (backface renders
ambient-only 0.108 where the lit answer is 0.705 — backfaces shaded
with the front normal), asserts the gl_FrontFacing flip lights the
backface to the exact front-face analytic, that front faces are
BIT-identical with the flag on vs off (rms 0 — single-sided content
cannot change), and that toggling off restores the default capture
byte-identically. `@directional` covers the view-space flip consumed by
the p3d_LightSource loop.

**`test_ambient_scale.py`** (Session L) — per-node ambient scale
(`set_ambient_scale(np, k)`, hull interiors). The ambient_sh recipe
(white up-facing card, two-tone hemisphere ambient, sun black) with
per-channel analytics at three states: untouched (root default 1.0 is
an exact no-op), scaled to 0.25 (the interior), and 0.25 + full sun on
the view axis (the sun-shaft case — direct light must NOT be scaled).
Also asserts the scale survives a recompile-class toggle and that
`clear_ambient_scale()` restores the baseline byte-identically.

**`test_env_map.py`** (Session M / R5.3) — specular IBL
(`set_env_map()` + the real BRDF LUT that ships with it). Sun black,
flat metallic card, expected values computed with (A,B) peeked from
the pipeline's own LUT at the texel centers the shader's clamped
bilinear fetch resolves to (material roughness chosen ON a texel
center). Asserts: the real LUT is loaded (the 1×1 white fallback would
add the whole env color as a bias — set_env_map refuses it), constant-
cubemap per-channel analytics, the LOD ladder addresses hand-loaded
per-mip colors (roughness 0 → mip 0, roughness 1 → top mip), mirror
ORIENTATION (normal incidence → -Y face, 45° pitch → +Z face: cube
sampling is GL-standard), glass composition (reflections unattenuated
through alpha), recompile survival, and byte-identical clear. Session Q
adds the GGX prefilter tool checks (`tools/gen_env_prefilter.py`, run as
a real subprocess; requires pip simplepbr, else reported INFO and
skipped): the .txo carries a complete mip chain with mip 0 an exact
identity, a uniform env stays exactly uniform at every level (GGX weight
normalization), the ladder blurs monotonically, and the tool's .txo
drives `textureCubeLod` end to end (mirror reads mip 0, roughness 1
reads the tool's top-mip texel, both to 3-decimal exactness).

**`test_local_lights.py`** (Session O — ship interior lighting) — the
p3d_LightSource point/spot loop, the pipeline's last never-measured
lighting path. Sun black, lamp on the view axis (BRDF dots all 1, same
analytics as test_glass): PointLight exact, quadratic attenuation
exact (1/(1+q·d²)), per-subtree `set_light` scoping (unlit sibling
stays ambient-only), Spotlight in-cone exact / outside-cone dark, and
the full ship-interior recipe measured (lamp at full strength + sky
hemisphere ambient damped by `set_ambient_scale`, composition to
0.002). Session P adds the Blender/glTF-authored lights checks: a
synthesized KHR_lights_punctual asset loads INERT (the classic
simplepbr annoyance, measured at rms 0), `activate_model_lights()`
lights it to the exact analytic through panda3d-gltf's unit chain
(I·4π/683, quadratic attenuation), the authored DirectionalLight stays
excluded (the pipeline owns the sun), and deactivation restores
byte-identically. `@directional` runs the loop with the sun occupying
slot 0.

**`test_skinning.py`** (Session G, openworld P1) — hardware vs CPU
skinning correctness plus the per-node opt-out API. Three layers: the
egg sheet posed and rendered GPU vs `set_hardware_skinning(np, False)`
(images must match, the depth pass must follow the per-node path,
`clear_hardware_skinning()` must restore); a pure-Python simulation of
the GPU palette math (top-4 weighted blend-matrix sum on bind-pose
vertices) against `animate_vertices()` (the CPU truth); and a rendered
GPU/CPU A/B per openworld character pack (the 94-joint Rigify pack 2
included). Session G verdict: the reported concertina does NOT reproduce
on a clean engine — pack 1 pixel-exact across all 50 Walk frames, pack 2
≤0.25% (shading-level), palette math exact, net Rigify compensating-scale
chains compose to 1.000.

**`probe_texturestage.py`** (Session Q, openworld round-4 P2) — NOT a
gate test: a four-mode diagnostic pinning where TextureStage combine
modes actually run. Measures combine-constant / rgb_scale /
CM_interpolate under compat-FFP, compat+auto-shader, core-no-shader,
and core+auto-shader. Diagnosis on file: under `gl-version 3 2` every
shaderless state is drawn by glgsg's minimal built-in default shader
(one stage, no combine machinery — color scale works, everything else
silently inert), and `set_shader_auto` cannot help because the generated
Cg shader fails to compile under core ("The profile is not supported")
and falls back to the same default shader. Identical on stock 1.10.16 —
expected upstream behavior, not a fork regression
(`OPENWORLD_FEEDBACK_RESPONSE_5.md` §1).

**`test_viewmodel.py`** (Session X, the FPS-lane near-plane answer) —
gates `register_viewmodel_camera`: the near-clip defect row (0.12 m
card invisible at world near 0.3), viewmodel drawn over CLOSER world
geometry through the full post chain (tonemap analytic on vm pixels,
hot vm quad feeds bloom), PBR lighting parity vs an identical world
surface, world byte-unchanged outside the vm silhouette, exact
unregister restore (frame + camera mask), rebuild survival
(SSAO/bloom toggles), both depth modes proven by scene-depth
readback ('clear' stomps world depth — documented-limitation row;
'range' preserves it; stock 1.10 exercises the auto-fallback), and
@directional: zero viewmodel texels in the sun depth map.

**`test_gl_clean.py`** (Session X, fact #18) — engine-level, 'none'
pipeline only: offscreen frames must not generate GL errors. Uses the
dt>1 s clock trick to make the engine's 1/s error sweep per-frame.
Currently asserts the KNOWN fork defect (glDrawBuffer(GL_BACK) on the
single-buffered pbuffer, ~1 error/frame) and stock-clean; when
`PATCH_QUEUE_GL_OFFSCREEN.md` lands it fails "the good way" — flip
`EXPECT_DEFECT_ON_1_11` and it becomes the permanent zero-GL-errors
guard. `probe_gl_errors.py` is the diagnostic sibling (phase
attribution, --gl-debug, --empty-only for wheel bisection).

**`test_srgb.py`** (Session R / R1.3) — the INPUT half of the color
contract: `set_srgb_inputs(True)` flags base-color (M_modulate) and
emission (M_emission) stage textures as sRGB formats so the GPU decodes
to linear at sample time; data textures (M_normal, M_selector, ...)
stay linear. Analytic cards (metallic-1/roughness-1 collapses ambient
to `base * A` exactly): an 8-bit 128 texel renders at raw 0.502 with
the flag off and sRGB-decoded 0.216 with it on, emission likewise;
data-texture immunity, recompile survival, and byte-identical opt-out
are asserted. Default-off was the shipped contract until the user
approved the flip (Session AC) — the game now boots `srgb_inputs` ON.

**`test_orbital.py`** (Session R / R5.5) — orbital scattering
(`set_orbital_atmosphere`): planet limb/halo/terminator from space via
pipeline-owned extinction + additive-inscatter billboard passes. The
reference model is an INDEPENDENT high-resolution quadrature of the
same documented math (any model change must land in both places);
planet and backdrop render known constant radiances, so every pixel is
analytic: `curve(source * T_rgb + L_rgb)` — the render matches the
integrator to ≤0.003. Density-0 registration and clears are
byte-identical; `@logdepth` reruns the whole row.

**`test_ssao.py`** (Session S) — depth-only screen-space ambient
obscurance (`enable_ssao`). The defining property gated: FLAT geometry
produces AO exactly 1.0 (a constant-depth wall renders rms 0.0 vs
off — SSAO can only darken real concavities). Wall/floor/ceiling slot
scene: both crease rows darken, far regions unchanged, intensity
monotonic, intensity-0 an exact no-op; `@logdepth` and `@msaa4`
variants prove the depth-source plumbing.

**`test_lens_flare.py`** (Session S — the R5 lens-polish finale) —
pseudo-flare ghosts sourced from the bloom bright extract. Ghost
positions are analytic (`x_k = 0.5 + (p-0.5)/c_k` at the shader's four
pinned constants): all four predicted centers brighten, off-axis
controls don't, a hidden source renders flare-on == flare-off
byte-identical (occlusion is implicit — no bright pixels, no flare),
strength-0 adds exactly 0, and a half-black dirt texture kills exactly
the ghosts under its dark half.

**`test_morph_gltf.py`** (Sessions T/Z/AB — facts #15/#16/#19/#20) —
glTF morph delivery end-to-end, 17 checks. Guards permanently:
`gltf_compat.install()` keeps Blender-default morph exports loadable
(3 upstream panda3d-gltf 1.3.0 bugs); the CPU path reproduces the
Blender ground-truth manifest exactly; the DEFAULT HW-skinning path
still silently drops sliders (`hw_drops_morphs` — set_gpu_morphs is
the opt-in fix, not enabling it is byte-identical); the GPU morph path
matches the CPU valve at rms 0.0000; the Session-AB crowd riders
(zero-copy vertex-major bake == numpy gather == pure Python,
byte-compared; `set_gpu_morphs(clone)` reuses pointer-shared delta
textures with zero re-bake and drives the clone's OWN face).

**`test_data_texture.py`** (Session U, ER-003) — the data-texture
contract, HOSTILE CONFIG LIVE: the whole test runs under
`compressed-textures 1` (the prc that block-compresses every
CM_default texture at prepare time). `data_texture()` /
`load_data_texture()` stamp F_r16/CM_off/ATS_none; the anti-terracing
assertion: a 16-bit gradient spanning 1022 codes survives GPU
round-trip with far more than 8-bit's 4 levels. This is the gate that
keeps the 2025 FPS-loader terracing class of bug dead.

**`test_terrain_splat.py`** (Sessions U/Y/AA, ER-001 + ER-007 — 38
checks) — the TERRAIN_SPLAT variant: 4-layer texture arrays weighted
by an RGBA splat map, replacing only the MATERIAL INPUTS of the PBR
shader. Analytic quadrant purity (`curve(c_i * A)` exact), bilinear
blend, weight renormalization, macro variation, per-layer uv_scale,
normal-map + distance-fade behavior. Session Y adds hex tiling
(periodicity break shift-rms 0.0014→0.2296, anisotropy contract
|dy|/|dx| 0.19 rot0 / 1.14 rot1, byte-identical opt-out); Session AA
adds height blend (softmax analytics exact at k=4/k=8, the ALL-FLAT
palette no-op at rms 2.6e-06 — the contract holds by construction) and
`hex_offset` world-anchoring (UV-window equivalence rms 0.0005).
`@directional` reruns the full row.

**`test_terrain_water.py`** (Session AE, ER-010 — 17 checks) — the
TERRAIN_WATER rider: `set_terrain_water(np, water_z, ...)` renders
fragments below the waterline + band WET (darker/saturated albedo,
much lower roughness). A card spanning world z [-1, 1] under an ortho
camera gives exact per-height analytics: full-wet / below-waterline /
band-midpoint pixels match the wet transform (dark multiplier + chroma
expansion about Rec.709 luminance) through the tonemap curve; the
region above the band computes the water-off arithmetic (rms 0.0
in-compile — every consumer is a `mix()` by wetness); a white env cube
pins `rough_mult` reaching the specular read (0.737→0.827 at 0.12);
five breathing-edge checks (amp-0 exactness, pinned phase 0-vs-π,
reach bounds above AND below, along-shore variation via the world-xy
noise); `set_terrain_splat` re-dress preserves the contract;
`water_z=None` / `clear_terrain_water` / `clear_terrain_splat` all
restore byte-identically. `@directional` reruns the full row.

**`test_instancing.py`** (Session U, ER-002) — hardware instancing
under the pipeline (`set_instanced` over upstream InstancedNode).
Measured contract: an UNFLAGGED InstancedNode still renders every
instance correctly (set_instanced is a perf switch, not a correctness
switch); the flag/shader pairing trap (F_hardware_instancing without
p3d_InstanceMatrix collapses instances onto the origin — doubling as
proof the flagged path is real); instanced vs fallback equivalence;
instanced SHADOWS; and clear_shader keeping flags (the trap
gate-guarded). SKIPs on stock 1.10 (no InstancedNode).

**`test_rigid_clips.py`** (Session V, ER-004 — walkable-ship
doors/ramps/gear) — panda3d-gltf silently drops animation channels
targeting PLAIN nodes (every Unity ship-pack door clip);
`rigid_clips.py` + `get_model_clips()` reads them from the .glb and
plays them onto the loaded nodes. Authors a minimal GLB from scratch:
pins the loader-conjugation axis contract (key-0 pose == the loader's
own rest pose in T, R, and S), analytic seeks (LINEAR lerp/slerp
midpoint, STEP hold, CUBICSPLINE, reverse scrub, reset), and
`RigidClip.from_delta()` (the Minerva prefab script-lerp synthesizer,
validated against the pack's C# source).

**`test_screen.py`** (Session V, ER-005 — powered displays, 19
checks) — `set_screen()` (texture bound as albedo AND emission, the
Unity-pack display convention) + `set_emission_scale/_color` +
`set_uv_transform`/`set_uv_scroll`/`play_flipbook`. Ortho camera, 2×2
quadrant texture, per-channel analytics (`e*t + AMB*(0.96*t + 0.04)`);
power-off keeps albedo lit, HDR emission feeds bloom, clears restore
byte-identically, UV windows map exactly, and gen_flipbook's atlas
drives the flipbook end-to-end. Instrument note: the scroll check pins
the global clock (wall-clock contract — Session X part 2 lesson).

**`test_alpha_mask.py`** (Sessions W/AA — fact #17 + ER-009) — glTF
alphaMode MASK reaches only fixed-function GL_ALPHA_TEST, so under
core every MASK material silently renders opaque (identical on stock —
upstream behavior). `apply_alpha_masks()` composes the in-shader
discard variant per-geom at the same predicate; Session AA adds
`TransparencyAttrib M_binary` detection (geom- or node-level, a ≥ 0.5
= the cull semantic) and `instanced=True` (the origin-collapse pairing
trap, measured 0/4→4/4). Compat legs key on `h.use_330` — the context,
never the baseline name (the Session-AC latent-defect lesson) — and
stay bit-identical (rms 0.0) under `--baseline compat`.

**`test_light_priority.py`** (Session Y, ER-008) — the light-selection
policy pinned mechanically: over max_lights the engine uploads the
highest-`set_priority` head (ties spot > directional > point, then
arbitrary) and SILENTLY DROPS the rest. Overflow drops measured,
priority selects the bound set, re-sort is live mid-session,
`set_light_budget()` (the per-root nearest-N warden) binds the top-N
by attenuated luma, and `@directional` proves the sun-eviction guard
(the priority-1<<20 pin — floods must never evict the sun + shadows).

**`test_effects.py`** (Session AD — 13 checks) — effect sprites:
`spawn_effect()` playing a PREMULTIPLIED-alpha flipbook atlas as pure
emission (set_screen metallic-1-black = analytically unlit + set_glass
premultiplied blending + play_flipbook). Ortho scene over a known
background, synthetic 2×2-cell premultiplied atlas, per-channel
analytics (`e*cell + B*(1-cell.a)`): premultiplied composite, additive
glow (a=0 adds without occluding), opaque core, unlit-under-ambient ×4
(the ambient sweep moves the background but not the effect),
billboard vs rotated static parent, one-shot self-cleanup (every
pipeline registry back to empty — the byte-identical-when-unused
invariant at rms 0.0), shadow-mask exclusion, and gen_flipbook tool
exactness (RGBA atlas assembly exact; alpha-free sources byte-identical
to the pre-alpha tool). `@directional` reruns the row; PASSES
identically on both engines.

**`test_light_halo.py`** (Session AF, ER-013 — nav-light readability)
— `set_light_halo()`: camera-facing additive sprites with a minimum
on-screen size. Perspective camera, black scene (plus a BLACK
AmbientLight — the zero-light white-flood quirk), unlit shader ⇒ every
center pixel is `curve(intensity * color * envelope)` exactly. Checks:
world-size regime (half-max diameter matches the projected size — the
half-max radius is solved THROUGH the tonemap curve by bisection, not
assumed in linear space), the min_px clamp regime (brightness
distance-independent), occlusion == the depth test (halo behind a card
= rms 0 vs baseline, no occluder registered), blink + emission-scale
composition through the inherited `u_emission_factor`, byte-identical
clear, and (@directional) shadow-caster-mask exclusion.

**`test_visibility_query.py`** (Session AF — flare occluder
retirement) — `add_visibility_query()`: depth-tap visibility around a
target's projected position. The wall card's x=0 edge plane contains
the camera, so it covers exactly the left half-screen at every depth —
open/blocked/half-covered are analytic by construction (1.0 / 0.0 /
0.498 measured). Also: geometry behind the target does not occlude,
the `max_occluder_depth` sky-dome valve both ways, the rendered frame
byte-identical with queries active, and the ~2-frame latency measured
as an INFO row. `@logdepth` reruns the row through the log depth
decode.

**`test_spot_exponent.py`** (Session AF — flood lamps) —
`enable_spot_exponent`: the p3d_LightSource spotExponent read. The
local-lights recipe with the spot AIMED 20° off the view axis: every
BRDF dot stays 1 while spotcos = cos(20°), so the exponent factor is
the only new term. Pins: flag-off ignores exponent (shipped behavior),
flag-on exponent-0 = rms 0 vs flag-off (arithmetic no-op through the
runtime recompile), cos²/cos⁸ exact, the Spotlight class-default-50
trap documented (why the flag is opt-in), PointLight immunity (rms 0),
byte-identical toggle-off.

**`test_gvad_churn.py`** (GVAD stability window — field AVs 2026-07-20
+ 2026-07-23) — threaded GeomVertexData churn must not corrupt the
heap. Runs the canonical crash recipe (`tools/repro_gvad_race/
repro_min.py`) as subprocesses: `handle-only` 60 s (the sharpest
distilled trigger — cross-thread handle acquisition vs Geom-class
destruction; AV'd < 60 s every run on the Session-X wheel) and `full`
30 s (the chunk-mesher field workload). Survival = exit 0 +
`SURVIVED`; an AV exits the child nonzero and FAILs the row. Proven
both ways at introduction: FAIL on the Session-X wheel (both rows
0xC0000005), PASS on stock 1.10.16 (1.24M builds) and on the fixed
wheel. Engine-level: `none` pipeline only, no window. Root cause and
forensics: `documents/CRASH_GVAD_HANDLE_RACE.md`.

**`test_thread_bind.py`** (Session AH — the paxcraft field crash,
2026-07-25/26) — `Thread.bind_thread` must PIN the bound
ExternalThread so dropping the returned PT(Thread) (the universal
consumer mistake) can never dangle the TLS current-thread pointer.
Rows: `bind_pinned` (ref count ≥ 2 + dangle survives drop/gc/churn;
deterministic — measured rc=1 UNPINNED on the pre-fix wheel) and
`bound_churn_render` (the paxcraft envelope verbatim: 5 bound workers
sharing one sync name building Geoms against a live offscreen render,
30 s). SKIPs whole on stock 1.10 — no pin contract there, and the
discard-shape churn row AVs on stock (upstream-inherited dangle,
recorded not gated). Engine-level: `none` pipeline; the repro
subprocesses open their own offscreen contexts. Root cause and
forensics: `documents/CRASH_BIND_THREAD_DANGLE.md`.

**`test_ftl_blur.py`** — the FTL warp distortion pass (radial blur +
chromatic aberration in tonemap); asserts zero-strength passthrough and
effect behavior (added alongside the feature, post-Session-D).

**`test_scale.py`** — R4 acceptance tests: `zfight_at_range` (1 IEU
separation at 2500 IEU under the game frustum 0.1/5000 — swept through a
full depth-quantization cell in 6 sub-resolution steps; the rear surface
bleeds through at some step, worst ~89%), and `precision_off_origin`
(identical rotated-camera scene at origin vs 1.2e6/1.2e7 IEU differs by
0.24%/22% of pixels). Near-field depth and origin-determinism controls
must stay green forever. The default runs document the engine baseline
and FAIL by design until R4 completes; the **`--log-depth` variant
(`scale/pax3d_render @logdepth`) must PASS** — it runs the depth checks
with `enable_log_depth=True` under a 0.1/1e9 frustum (R4.1, landed).
Two findings encoded here: the precision defect requires a ROTATED
camera (axis-aligned rigs cancel exactly in float32 and hide it), and
z-fight probing must SWEEP — a single frame can tie-break uniformly in
the correct surface's favor and mimic a working depth buffer.

## Goldens

`--golden` blesses the current captures into `goldens/`; `--check-golden`
adds an RMS-diff check against them on later runs. Analytic checks are the
primary mechanism — goldens are a safety net for refactors (R1).

## Results snapshot (post GVAD build window, 2026-07-24 — measured, gate logs on file)

The standard gate is both engines × the ONE `game` baseline (Session AC
redefinition). Totals: **Pax3D 82 PASS / 7 FAIL / 129 SKIP · stock
1.10.16 80 PASS / 7 FAIL / 131 SKIP** — the FAIL sets are IDENTICAL on
both engines and every one is pre-existing/by-design: `lighting/none`
(fixed-function control under gl 3 2), `bloom` + `rebuild` on the
retired `pax3d_simplepbr`, `rebuild/pax_pbr` (F4, by design of the old
attach pattern), and `scale` on `none` + `pax3d_render` (the documented
R4 baseline; `@logdepth` PASSES). The two-row difference between
engines is `instancing` (needs InstancedNode — SKIPs on stock 1.10).
(Session AE added the 6 terrain_water jobs; Session AF added the 18
light_halo / visibility_query / spot_exponent jobs — +6 PASS +12 SKIP
per engine, identical rows both engines; the GVAD build window added
the 5 gvad_churn jobs — +1 PASS +4 SKIP per engine, and the row is the
permanent heap-corruption guard: it FAILed on the pre-fix Session-X
wheel, gate logs `gate_gvad_*`. Session AH added the 5 thread_bind
jobs — Pax3D +1 PASS +4 SKIP, stock +5 SKIP (whole-test skip: no pin
contract on 1.10, and the discard-shape churn row AVs there —
upstream-inherited, recorded not gated): **totals now Pax3D 83/7/133 ·
stock 80/7/136, FAIL sets unchanged**; bind_pinned FAILed rc=1 on the
pre-fix GVAD wheel, gate logs `gate_bind_*`.)

Note: with the game's `use_pax3d_render` flag flipped (Session D), the
`pax_pbr` adapter routes to pax3d_render — its column mirrors
pax3d_render except for `rebuild` (old attach pattern, fails by design)
and rows whose harness scenes need pax3d_render-only hooks (skip).

| Test | none | simplepbr | pax_pbr (routed) | pax3d_render |
|---|---|---|---|---|
| gamma | PASS | PASS | PASS | PASS |
| lighting | **FAIL (fixed-function control under gl 3 2 — identical both engines, pre-existing)** | PASS | PASS | PASS (+@directional) |
| bloom | skip | skip | PASS | **PASS (F3 fixed, Session D; both resolutions)** |
| rebuild | skip | skip | FAIL (F4, by design of the old pattern) | **PASS** |
| shadows | skip | skip | skip | **PASS (incl. off-origin extent, skinned + glTF casters; +@softskin)** |
| shadows_gltf | skip | skip | skip | **PASS (glTF caster AND receiver, 45° sun)** |
| shadow_quality | skip | skip | skip | **PASS** |
| shadow_grazing | skip | skip | skip | **PASS (grazing acne cleared by slope-scaled bias, umbra kept)** |
| shadow_snap | skip | skip | skip | **PASS (sub-texel sweep depth+screen stable; teeth measured)** |
| ftl_blur | skip | skip | PASS | PASS |
| scale | **FAIL (R4 baseline)** | skip | skip | **FAIL (R4 baseline)**; **@logdepth PASS (R4.1)** |
| skinning | skip | skip | skip | **PASS (opt-out API + both openworld packs)** |
| atmosphere | skip | skip | PASS | **PASS (analytic transmittance exact; opt-out byte-identical)** |
| ambient_sh | skip | skip | PASS | **PASS (hemisphere analytics exact; face table pinned end-to-end)** |
| glass | skip | skip | PASS | **PASS (spec survives alpha; +@directional)** |
| doublesided | skip | skip | PASS | **PASS (backface analytic; front faces bit-identical; +@directional)** |
| ambient_scale | skip | skip | PASS | **PASS (per-channel analytics ×3 states; direct light unscaled)** |
| env_map | skip | skip | PASS | **PASS (23 checks: LUT-peek analytics, LOD ladder, GGX tool end-to-end, Session-Y scale/intensity/rotation)** |
| local_lights | skip | skip | PASS | **PASS (point/spot analytics exact; authored-lights activation; +@directional)** |
| orbital | skip | skip | PASS | **PASS (independent integrator ≤0.003; +@logdepth)** |
| srgb | skip | skip | PASS | **PASS (raw vs decoded texel analytics; data textures immune)** |
| ssao | skip | skip | PASS | **PASS (flat-plane byte-identity; +@logdepth +@msaa4)** |
| lens_flare | skip | skip | PASS | **PASS (analytic ghost positions; implicit occlusion)** |
| morph_gltf | skip | skip | skip | **PASS (17 checks: loader shim, CPU truth, GPU path rms 0.0000, crowd riders)** |
| data_texture | skip | skip | skip | **PASS (13 checks under hostile `compressed-textures 1`)** |
| terrain_splat | skip | skip | skip | **PASS (38 checks: splat/hex/height-blend analytics; +@directional)** |
| terrain_water | skip | skip | skip | **PASS (17 checks: wet analytics, sheen, breathing edge; +@directional)** |
| instancing | skip | skip | skip | **PASS (+@directional; SKIPs entirely on stock 1.10)** |
| rigid_clips | skip | skip | PASS | **PASS (axis contract, analytic seeks, from_delta)** |
| screen | skip | skip | PASS | **PASS (19 checks: display analytics, UV/flipbook, clock-pinned scroll)** |
| alpha_mask | skip | skip | PASS | **PASS (MASK + M_binary variants; instanced pairing trap)** |
| viewmodel | skip | skip | skip | **PASS (+@directional: zero vm texels in the sun depth map)** |
| gl_clean | **PASS (the permanent zero-GL-errors guard, fact #18)** | skip | skip | skip (runs on `none` only) |
| light_priority | skip | skip | skip | **PASS (+@directional: the sun-eviction guard)** |
| effects | skip | skip | PASS | **PASS (13 checks: premult composite, unlit, self-reap, tool exactness; +@directional)** |
| light_halo | skip | skip | skip | **PASS (10+1 checks: tonemapped size analytics, min_px clamp, depth-test occlusion, blink composition; +@directional mask exclusion)** |
| visibility_query | skip | skip | skip | **PASS (7 checks: open/blocked/half exact, sky-dome valve, frame-invisible; +@logdepth)** |
| spot_exponent | skip | skip | skip | **PASS (7 checks: cos^e analytics, exponent-0 no-op, default-50 trap, point immunity; +@directional)** |

`pax3d_simplepbr` (retired) keeps its historical bloom/rebuild failures.
`scale` failing is the DOCUMENTED baseline until R4 lands — see its entry
above. `--baseline compat` remains available as a diagnostic
(fixed-function archaeology); it is not part of the gate.

Key established facts (full analysis:
`documents/PAXTEST_FINDINGS_SESSION_A.md` + master plan session updates):

- **No double gamma** — all tonemap operators match their analytic curves;
  the ACES wash-out is an input-linearization problem (textures sampled
  RAW, content tuned for Hejl-Dawson).
- **No DirectionalLight engine bug** — real lights work on every mesh type;
  pax3d_render's directional sun measures identically to the uniform sun,
  and its shadows are proven (lit 0.79 → shadowed 0.09).
- **Blocky bloom (F3) is FIXED (Session D)** — the root cause was 8-bit
  intermediate FBOs (`render_quad_into` without float fbprops), NOT
  filtering; the banding mimics nearest-neighbor sampling. Guarded by
  `bloom_buffers_float`.
- **Scale defects (R4) are reproduced** — depth resolution ~1.9 IEU at
  2500 IEU under the game frustum; float32 view-matrix precision loss
  needs a rotated camera to manifest.
- **A luminance check is only as good as its sample geometry (Session G)**
  — the glTF-caster assertion initially FAILED on a healthy engine because
  the sampled "pole" pixel is the sphere's front surface, outside a thin
  caster's shadow column, and because the nondeterministic anim pick had
  been silently choosing wide poses. Pin poses; verify the sample point is
  inside the caster's shadow volume (the depth-map diff bbox tells you).
- **The 94-joint Rigify concertina (openworld P1) does not reproduce on a
  clean engine (Session G)** — GPU palette == CPU truth at every layer
  measured (math sim exact, renders ≤0.25% shading-level across the full
  Walk, net compensating-scale chains = 1.000). Guarded permanently by
  test_skinning; field re-verification requested.
