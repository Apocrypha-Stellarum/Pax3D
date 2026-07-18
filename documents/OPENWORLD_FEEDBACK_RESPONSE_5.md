# Response to the Openworld Engine Feedback, Round 4 addenda (Session Q, 2026-07-18)

**To:** the openworld/planetside devs (`C:\python\sfb2\planetside`, frozen
reference at `C:\python\openworld`)
**From:** Pax3D engine (`C:\python\pax3d`)
**Re:** the three 2026-07-18 additions to `PAX3D_FEEDBACK_2.md` — the
TextureStage retraction + P2 diagnosis ask, the sh_from_cubemap
orientation validation, and the Session J adoption report. Plus one
delivery you asked for by name ("R5 env-derived ambient remains our
biggest quality wish"): the GGX prefilter tool shipped today.

---

## 1. P2 answered: the core-profile combine-mode drop is EXPECTED upstream behavior, not a fork regression

Your probe was right and your instinct ("move the dome to a tiny explicit
GLSL shader") is the correct fix. The full mechanism, verified in source
and by measurement (`tools/paxtest/probe_texturestage.py`, runnable in
your venv — same four-mode matrix as your probe):

**Under `gl-version 3 2` there is no fixed-function pipeline, and the
engine substitutes a MINIMAL built-in GLSL shader for every state that
has no explicit shader** (`glGraphicsStateGuardian_src.cxx:189-303`,
`do_issue_shader` at `:8852`). That default shader implements exactly:

    FragColor = textureProj(Texture0, texcoord) + TexAlphaOnly;
    FragColor *= vertexColor * p3d_ColorScale;

One texture stage. No combine modes, no stage constants, no rgb_scale,
no second stage — and `set_color_scale` rides a shader uniform, which is
why it works live and unclamped there. Your entire observed matrix is
this one shader.

**Why `set_shader_auto()` doesn't rescue it:** the full ShaderGenerator
(which really does implement combine constants, scales, and
CM_interpolate — `shaderGenerator.cxx:1899+`) only runs for states
explicitly carrying the auto-shader flag (`graphicsStateGuardian.cxx:
3998`), and it emits Cg (`shaderGenerator.cxx:777`). Under a core
context the Cg program cannot compile — our probe gets
`Could not load program: created-shader (The profile is not supported.)`
— and `do_issue_shader` falls back to the same default shader
(`:8866`). Measured on both engines, byte-identical behavior on stock
Panda3D 1.10.16 and the Window-3 wheel:

| mode | combine constant | rgb_scale 2 | CM_interpolate |
|---|---|---|---|
| compat, no shader (FFP) | works | works | works |
| compat, set_shader_auto (Cg generator) | works | works | works |
| core, no shader (default shader) | ignored | ignored | ignored |
| core, set_shader_auto | ignored + profile error | ignored | ignored |

So: not a regression, not R6 surgery — the identical logic ships in
stock 1.10.16. It's the known upstream generation gap (their
GLSL-emitting shader-pipeline rewrite lives in the branch that never
reached master; our fork severed before it).

**Your ask (one-line warning) is accepted and queued** as a C++
build-window candidate (CLAUDE.md build queue): when the default shader
is selected for a state whose TextureAttrib carries an M_combine stage /
rgb_scale ≠ 1 / more than one stage, glgsg will warn once per state. It
lands in the next scheduled build window (C++ never lands mid-session
here).

**Recommendation** (matches your plan): a tiny explicit GLSL shader for
the dome — `mix(base, fade, t) * brightness` — is the right tool. FFP
emulation under core is a legacy path with exactly one honest citizen
(the default shader above); anything you shader explicitly is fully
supported and stays HDR/linear-correct through the pipeline.

On your "GL error 0x502 at startup" noise note: acknowledged, still
undiagnosed on our side (it is NOT the Cg profile error above — that
prints its own line, once, only for auto-shader states). On file.

## 2. sh_from_cubemap orientation: your validation is now pinned engine-side — the question is CLOSED

Thank you for the marker rig — it settled the capture-side half. We
closed the remaining half today (how Panda orients faces loaded from
image FILES) and pinned the whole table with gate tests
(`test_ambient_sh` checks 6-8, green on both engines):

- `loader.load_cube_map('sky_#.png')` puts **file N on GL face N with
  content intact**: 0 = +x east, 1 = −x west, 2 = +y north, 3 = −y
  south, 4 = +z up, 5 = −z down — exactly your marker convention
  (RED east / GREEN north / BLUE west / YELLOW south named correctly
  through the file → SH → irradiance chain).
- In-face orientation of a file-loaded UP face, measured: **the top row
  of the up-face image is the SOUTHERN sky** (a top-red/bottom-blue
  face-4 file tilts irradiance red toward −y).
- The `sh_from_cubemap` docstring now carries the pinned table (the
  EXPERIMENTAL caveat is retired) plus your two incidental notes — the
  `saveCubeMap` camera-parenting trap is recorded there verbatim.

With shader sampling (test_env_map mirror proof), captures (your rig),
and files (today's tests) all proven, the skybox → ambient chain is
measured end to end.

## 3. Session J adoption report: recorded, and the guide learned your lesson

Your settled Mars values (texel snap on, hemisphere multipliers, haze
tune at 660 m half-extent) are recorded as the seed presets for the
sfb2 planet-landing work. Two guide updates from your report,
landed in `PLANETSIDE_LOOK_GUIDE.md` §5:

- **Scale haze colors by day-cycle luminance** — your finding that a
  constant haze color paints distant hulls/mountains bright tan against
  the night sky is now a named trap in the guide (uniform-only per-frame
  updates are the blessed mechanism, exactly as you did it).
- Your density experience (0.0025 milked out at 400 m where the guide's
  toy-scale guess said 5-10×) corrected the guide's starting-point
  advice for sub-km worlds.

## 4. Reminder for the planetside team: the west-sun shadow P0 fix has been waiting since Response 4

The planetside unification handover still lists "cast shadows die in the
low-western-sun cone" as an open engine ask. It was root-caused and
fixed in Session I (grazing-angle self-shadow acne; the acne darkens
open ground until real shadows lose contrast and read as "gone"):

    pipeline.set_shadow_normal_bias(0.25)   # world units, opt-in, 0=off
    # or init kwarg: shadow_normal_bias_world=0.25

Start at 0.25, A/B at az 240 low sun; full recipe in
`OPENWORLD_FEEDBACK_RESPONSE_4.md`. Proven on the real village GLB at
az 240 (terracing gone, building/tree shadows kept). We've also updated
`USING_PAX3D_RENDER.md` and the unification handover's known-issues
entry so the next reader connects the dots. What remains is exactly the
A/B you're best placed to run.

## 5. New today, for your R5 wish: the GGX prefilter tool

`tools/gen_env_prefilter.py` (engine repo) bakes a skybox cubemap into a
CORRECT specular-IBL roughness ladder — `set_env_map`'s "mip chain = GGX
ladder" contract is no longer an approximation:

    C:/Python313/python.exe tools/gen_env_prefilter.py sky_#.png sky_ibl.txo
    # then at runtime:
    tex = loader.load_texture('sky_ibl.txo')
    pipeline.set_env_map(tex)                        # reflections
    pipeline.set_ambient_sh(sh_from_cubemap(tex))    # matching ambient

Same borrow-and-verify shape as the BRDF LUT: pip simplepbr's reference
GGX sampling (dev-time dependency only), complete mip chain so the
default `max_lod` just works, 2.6 s at the default 64px/32-sample
quality. Gated by four new `test_env_map` checks (mip-0 identity, energy
preservation, monotone blur, and the .txo driving `textureCubeLod`
end to end — all exact to 3 decimals on both engines). Pair it with the
now-pinned `sh_from_cubemap` and one skybox feeds both halves of the
environment: ambient AND reflections.

---

**Headline:** P2 diagnosed to the exact shader (expected upstream
behavior; warning queued; your explicit-shader plan is right), the
orientation question is closed and gate-pinned on both halves, your
adoption lessons are in the guide, the west-sun P0 fix is one
`set_shadow_normal_bias(0.25)` away from your sunsets, and the specular
half of "env-driven ambient" now has its correct bake tool.
