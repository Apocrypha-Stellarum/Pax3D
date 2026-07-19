# ENGINE_INTERNALS — how Pax3D works deep down

**Audience:** engine devs (human or AI) working in `panda/src/` or against
engine behavior from `pax3d_render/`. Every entry cites the source location
and/or the paxtest that proves it — this doc records **mechanisms**, not
program status (that's `PAX3D_MASTER_PLAN.md`; its §3 facts table is
program-level, this is code-path level). Add entries when you dig a
mechanism out of the C++; correct entries the moment a measurement
disagrees.

Started Session U (2026-07-19) from the terrain-lane digs (ER-001/002/003).

---

## 1. Texture pipeline: loads, formats, silent-degradation paths

**Format selection on image load** (`panda/src/gobj/texture.cxx`,
`do_load_one`): a PNMImage with `maxval > 255` becomes `T_unsigned_short`;
a PfmFile always becomes `T_float`; channel count picks the format family —
1-channel images land on `F_luminance` (not `F_red`). This is why
`data_texture()` normalizes single-channel ushort/float to `F_r16`/`F_r32`.

**Driver compression consults a global flag at prepare time**
(`glGraphicsStateGuardian_src.cxx`, `get_internal_image_format`,
~line 11155): a texture at `CM_default` compresses when the
`compressed-textures` prc is set — `F_r16`/`F_r32` → RGTC1/BC4 (lossy 8:1),
`F_luminance` → DXT1, `F_rgb*` → DXT1, `F_rgba*` → DXT5. Render targets are
exempt (`get_render_to_texture()` forces CM_off); file/procedural textures
are NOT. Per-texture `set_compression(CM_off)` is the only immunity —
gated by `test_data_texture` (an unstamped RGB8 canary must come back
DXT1 or the check is vacuous).

**`texture-scale` rescales INSIDE `Texture.read()`** (`texture.cxx`,
`adjust_size` ~2842: the multiply at ~2858 is gated ONLY by
`exclude-texture-scale` name globs; the ATS parameter governs only the
power-2 logic afterwards). It is applied as a decode-size hint in
`do_read_one` (~3304), so no post-hoc stamp can undo it. The
`tex.load(PNMImage/PfmFile)` route (`do_load_one`) never applies it — it
only rescales to the texture's own expected mip size, which for a fresh
texture IS the image size. This is why `load_data_texture()` exists.
Measured both ways in `test_data_texture` (`texture_scale_trap_real` /
`load_data_texture_immune`).

**`set_format()` keeps the RAM image** when the component layout is
unchanged (e.g. `F_luminance` → `F_r16`, both 1×ushort) — but an
already-prepared texture keeps its old GPU internal format until
`release_all()` forces a re-upload (the `set_srgb_inputs` precedent,
Session R).

**Panda's 16-bit TIFF WRITER hard-crashes the process** (native, no
traceback, exit 127; measured 2026-07-19 on the Pax3D wheel AND stock
1.10.16 — upstream behavior). 16-bit TIFF *reads* are fine (gated with a
hand-rolled TIFF in `test_data_texture`). Tools must write PNG16 or
PFM/EXR, never TIFF16, through Panda.

## 2. ShaderAttrib composition and multi-pass state resolution

**Across nodes, a ShaderAttrib's *shader* replaces; its *flags* compose
per-bit when the child attrib carries no shader.** This is the whole
mechanism behind `set_hardware_skinning` (flag-only attrib, shader
inherited) and behind the per-node variant family (`set_glass`,
`set_terrain_splat`, `set_instanced`: shader + state composed via
`prev.set_shader(...)` so existing flags/inputs survive).

**The shadow (depth) pass gets its shader from the light camera's
`initial_state`**, installed by `pipeline._update` with the shadow
ShaderAttrib at **override 1** (`_create_shadow_shader_attrib`). State
resolution per pass:

- Node-level scene variants at override 0 (glass/terrain/instanced) LOSE
  to the initial state in the depth pass — so scene variants never leak
  into shadow rendering; the depth pass renders those nodes with the
  global shadow shader.
- A node attrib at **override 2** beats the initial state — that's how
  `set_hardware_skinning`'s flag reaches the depth pass so shadows track
  the visible pose.
- Consequence: anything the depth pass must know about a node class has
  to be compiled into the GLOBAL shadow shader (e.g. the INSTANCING
  define + `F_hardware_instancing` flag when any instanced node exists),
  and the caster initial states must be invalidated when those defines
  flip (`_invalidate_shadow_caster_states`, the `set_max_skinning_bones`
  pattern — `_update` lazily rebuilds them next frame).

**`NodePath.clear_shader()` keeps the residual attrib's FLAGS (and
inputs).** Measured trap (`test_instancing`
`flag_without_shader_collapses`): after clear_shader() a leftover
`F_hardware_instancing` with the inherited non-INSTANCING shader collapses
every instance onto the node origin. `set_instanced(np, False)` clears the
flag explicitly for exactly this reason.

**Unbound vertex-attrib defaults** (`glShaderContext_src.cxx`,
`update_shader_vertex_arrays` ~2637–2669): when a shader declares an
attrib the vertex data lacks, the GL layer sets a current value instead —
color → scene-graph color, `transform_index` → (0,1,2,3),
`transform_weight` → (0,0,0,1), **`p3d_InstanceMatrix` → identity**. This
is the "identity padding" family (skinning fact #10 is the
TransformTable-side sibling): shaders compiled with these declarations
degrade gracefully on data that lacks the columns, which is what makes ONE
global shadow shader safe for mixed instanced/non-instanced casters.

## 3. Hardware instancing plumbing (upstream 1.11 `InstancedNode`)

The full chain, verified by source + `test_instancing`:

1. `InstancedNode.cull_callback` (`panda/src/pgraph/instancedNode.cxx`)
   composes nested instance lists, does **per-instance frustum culling**
   (upstream, free — better than ER-002 asked for), and passes the
   surviving list down as `CullTraverserData._instances`.
2. `CullableObject` (`cullableObject.cxx` ~177): **with**
   `ShaderAttrib.F_hardware_instancing`, `munge_instances()` appends
   `InstanceList.get_array_data()` (cached C++-side) to the munged vertex
   data as a divisor-1 array and sets `_num_instances = N` → the GSG
   issues one instanced draw (`glDrawElementsInstanced`). **Without** the
   flag, the traverser falls back to one draw per instance — output is
   CORRECT, there's just no draw-call win. `set_instanced` is therefore a
   performance switch, not a correctness switch (measured: unflagged
   4/4 instances render; flagged matches CPU-transformed copies at
   rms 0.00000).
3. `p3d_InstanceMatrix` is enforced `mat4x3` (`glShaderContext_src.cxx`
   :541). **Matrix convention:** Panda's row-major affine matrix memory
   (v·M, translation in row 3) reads as GL column-major `mat4x3` with
   translation in column 3 — so `p3d_InstanceMatrix * vec4(v, 1.0)` is
   the correct application (measured exact).
4. The instance transform applies BETWEEN the node transform and the
   vertex (`p3d_ModelViewMatrix` contains the node's net transform, not
   the instance's) — children under an InstancedNode must be flattened
   or their transforms land on the wrong side (upstream's documented
   contract, now load-bearing in pax_pbr.vert/shadow.vert).
5. Python surface: `node.instances` property (write-back
   `modify_instances`), `append(pos, hpr, scale)` /
   `append(TransformState)`, `reserve(n)`, `len()`/indexing.
   `get_num_instances()` is NOT published — use `len(node.instances)`.
   There is NO bulk fill-from-buffer (queued C++ candidate, profile
   evidence only). Stock 1.10.16 has none of this — `test_instancing`
   SKIPs there, documenting the version gap.

## 4. GLSL version and platform notes (this machine, both wheels)

- `sampler2DArray` works on the GLSL **120** path via
  `#extension GL_EXT_texture_array : require` (+ `texture2DArray()`);
  core GLSL 330 has it natively (measured: `test_terrain_splat` green on
  both baselines).
- `attribute mat4x3` compiles on GLSL 120 (measured: `test_instancing`
  green @game); matrix attribs consume 4 attribute locations.
- The shader "world space" (via `p3d_ModelMatrix`) is **Panda Z-up** in
  this engine configuration — the atmosphere height term
  (`v_world_position.z`) and the terrain analytic TBN (+Z up,
  u→+world_x, v→+world_y) both rely on it (harness-proven:
  test_atmosphere, test_terrain_splat).
- Terrain meshes carry no tangent column, so `v_view_tbn`/`v_world_tbn`
  are NaN there (the long-standing trap noted in pax_pbr.vert) — the
  TERRAIN_SPLAT variant builds its TBN analytically instead of reading
  the varyings.

## 5. Instrument traps (for test authors)

- An ortho camera sitting ON the geometry plane has view distance ≈ 0 —
  a distance-fade "force it on" config needs fade edges BELOW zero
  (`smoothstep(0.0, 0.1, 0.0) == 0`; measured in test_terrain_splat
  development).
- Clear-color-only textures round-trip sRGB format flips unchanged
  (driver clears encode; Session R) — precision/format tests need real
  RAM images.
- Cached bams bypass loaders entirely — disable `BamCache` when
  measuring loader behavior (Session T).
- `grep` on paxtest console output trips on em dashes under cp1252 and
  goes binary-mode silent — assert on the `PAXTEST_JSON` line or use
  `grep -a`.
