 Here is Claude's plan:                                                                                     ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ Bloom + HDR Tonemapping for Pax3D

## Session 459 — Bloom + HDR Tonemapping Integration (2026-03-03)

### What We Tried
Ported the Kawase bloom chain and multi-operator tonemapping (ACES, Reinhard, Uncharted2, Hejl-Dawson) from pax3d_simplepbr into the existing graphics/pax_pbr/ pipeline in the game (C:\python\sfb2). The PBR shader itself was NOT changed — sun lighting still uses custom u_sun_dir_world / u_sun_color uniforms. No DirectionalLight was added to the scene.

Created 3 new bloom shaders (bloom_extract.frag, bloom_downsample.frag, bloom_upsample.frag) and replaced tonemap.frag with a multi-operator version. Extended pipeline.py with the full bloom chain (extract → 5 downsample → 5 upsample → tonemap composite). Added runtime tuning controls (Ctrl+F12) and config support in settings.json.

Also adjusted PBR brightness compensations on additive-blended nodes (sun glow, weapons, exhaust) which bypass the PBR shader via setShaderOff() but still pass through the tonemapping pass.

### Results

**Tonemapping:**
- ACES, Reinhard, and Uncharted2 all looked wrong — washed out / incorrect colors. Root cause: these operators apply explicit sRGB gamma (pow 1/2.2) but our GLSL 120 pipeline (gl-version not set) may already be doing sRGB conversion in the framebuffer, causing double-gamma. Only Hejl-Dawson looked correct — it bakes in its own sRGB curve and was the previous default.
- **Reverted to Hejl-Dawson as default.** The other operators remain in the shader code but need the double-gamma issue investigated before they can be used.

**Bloom:**
- Bloom produced blocky artifacts visible on/near planets. Possibly specular highlight artifacts or downsampling kernel issues. Did not produce any useful visual glow effect.
- Toggling bloom off at runtime (via _rebuild_tonemapping) destroyed the FilterManager buffers, which killed the sky camera's display region (skybox disappeared and never came back). This is because the sky camera finds its render target by searching for base.cam's DR on the FilterManager buffer — rebuilding the FilterManager creates new buffers that the sky camera doesn't know about.
- **Reverted bloom to OFF by default.** Bloom toggle in tuning controls disabled to prevent skybox death. Bloom on/off currently requires settings.json change + restart.

**Brightness compensations:**
- With Hejl-Dawson restored, all compensations reverted to original values: sun glow 0.45x, distant sun 0.45x (3 locations), weapons 0.25x/0.6x, exhaust 0.35x.

### What's Still In Place
- The bloom chain code is all there in pipeline.py (extract/downsample/upsample with render_quad_into), just gated behind enable_bloom=false
- tonemap.frag has all 4 operators + ENABLE_BLOOM define guard + dither (user added interleaved gradient noise dithering)
- Runtime tuning controls (Ctrl+F12) work for exposure, tonemap cycling, bloom strength/intensity — just bloom on/off toggle is disabled
- settings.json has all the bloom/tonemap config keys ready

### Key Lessons
1. **Cannot switch tonemap operators without understanding the sRGB pipeline.** GLSL 120 without gl-version set may have implicit sRGB handling. Need to verify whether the framebuffer is sRGB or linear before applying explicit gamma correction.
2. **FilterManager rebuild kills sky camera.** Any feature that calls _rebuild_tonemapping() (bloom toggle, bloom_levels change) will destroy the sky camera's display region. The sky camera setup (graphics/sky_camera.py) finds the render target once at init via _find_render_target(). A rebuild would need to re-run sky camera setup.
3. **Bloom needs proper directional lighting to be useful.** Without a DirectionalLight, there are no specular highlights on ships/models — nothing bright enough for bloom to meaningfully amplify. The only bright elements are additive-blended nodes (sun glow, exhaust) which bypass the PBR shader entirely.
4. **Ships look flat because they have no directional lighting.** The custom u_sun_dir_world uniforms only work with our custom pax_pbr.frag shader. Ships/stations using stock PBR materials get no directional light — only ambient. This is the real issue to fix.

### Next Steps
The next session should plan restoring a real DirectionalLight to the scene. The sphere tangent/winding issues that originally forced the custom uniform approach were fixed in Session 424 (handover_pax_pbr_sun_lighting.md). Three options identified:
- Option A: Add DirectionalLight alongside custom uniforms (incremental)
- Option B: Switch entirely to pax3d_simplepbr (cleanest but needs tangent bypass)
- Option C: Keep pax_pbr but read p3d_LightSource[0] instead of custom uniforms

---                                                                          
 Context

 Pax Abyssi is a space simulation with extreme dynamic range — stars range from faint pinpoints to blinding
  nearby suns, engines pulse, weapons flash. Without bloom, the game compensates with fragile per-effect
 magic numbers (0.45x sun RGB, 0.25x weapon RGB, 1.8x corona scale). Without proper tonemapping, there's no
  control over the HDR-to-display mapping across scenes that range from deep black interstellar space to
 close planetary approach.

 This plan adds Kawase dual-filter bloom and ACES tonemapping to the rendering pipeline by forking
 simplepbr into the Pax3D repo and extending its post-process chain using FilterManager passes.

 Phase 1 (directional lighting) is resolved — the planet mesh winding was the root cause.

 ---
 Architecture

 Current simplepbr pipeline

 Scene (PBR shader) --> RGBA16F HDR buffer --> Tonemap quad (Hejl-Dawson) --> Window

 New Pax3D pipeline

 Scene (PBR shader) --> RGBA16F HDR buffer
     |
     v
  [Bloom Extract] ---- full-res, threshold + scale bright pixels
     |
     v
  [Downsample x5] ---- half-res cascade: 1/2, 1/4, 1/8, 1/16, 1/32
     |
     v
  [Upsample x5] ------ tent filter back up, accumulating per-mip tint
     |
     v
  [Tonemap + Composite] -- bloom_tex + scene_tex --> ACES tonemap --> Window

 Total new passes: 1 extract + 5 downsample + 5 upsample = 11 intermediate buffers via
 FilterManager.renderQuadInto(), plus the modified tonemap pass.

 ---
 Step 1: Fork simplepbr into Pax3D repo

 Copy the simplepbr 0.13.1 package into the engine repo as a first-party module.

 Source: C:/python/pax3d-env/Lib/site-packages/simplepbr/

 Destination: C:/python/pax3d/pax3d_simplepbr/

 Files to copy:
 - __init__.py (Pipeline class — the main file we'll modify)
 - shaders.py (embedded GLSL — we'll add bloom shaders here)
 - _shaderutils.py (shader compilation helper)
 - envmap.py, envpool.py, hdr2env.py (IBL support)
 - _ibl_funcs_cpu.py (CPU-side IBL)
 - textures.py, utils.py, logging.py

 Changes to make in the fork:
 - Update all internal imports from simplepbr to pax3d_simplepbr
 - Add a top-level __init__.py comment: # Pax3D fork of simplepbr 0.13.1 (Moguri) — adds bloom, ACES
 tonemapping
 - The game code (sfb2) will change its import from import simplepbr to import pax3d_simplepbr as simplepbr
  (one-line change)

 ---
 Step 2: Write bloom GLSL shaders

 Add 3 new fragment shaders to the shaders dict in shaders.py. All use the existing post.vert vertex
 shader.

 2a. bloom_extract.frag (~20 lines)

 Reads HDR scene texture, scales by bloom strength. No hard threshold (physically correct — everything
 blooms proportionally to its luminance).

 // Inputs: scene_tex (sampler2D), bloom_strength (float)
 // Output: scaled bright color
 vec3 color = texture2D(scene_tex, v_texcoord).rgb;
 color *= bloom_strength * 0.005;
 color = clamp(color, vec3(0.0), vec3(25000.0));  // firefly clamp
 gl_FragColor = vec4(color, 1.0);

 2b. bloom_downsample.frag (~40 lines)

 13-tap Kawase downsample (CoD:AW / Jimenez 2014). Five overlapping 2x2 box sub-kernels weighted: center
 0.5, corners 0.125 each. 1.3x energy boost per level.

 // Inputs: src_tex (sampler2D), texel_size (vec2)
 // 13 texture samples, weighted sum, * 1.3 energy compensation

 2c. bloom_upsample.frag (~35 lines)

 9-tap tent filter (weights: center 4, edges 2, corners 1, /16). Adds to previous accumulated result.
 Per-mip color tinting for warm-cool bloom fringe (artistic, tunable).

 // Inputs: src_tex (sampler2D), bloom_accum_tex (sampler2D), texel_size (vec2), mip_tint (vec3)
 // 9 tent samples from src, tint, add to accumulated bloom

 No separate apply_bloom.frag — the composite happens in the modified tonemap shader (Step 3).

 ---
 Step 3: Modify tonemap shader — ACES + bloom composite

 Replace the existing tonemap.frag in shaders.py. Key changes:

 1. Add bloom composite — sample bloom_tex and add to scene color before tonemapping
 2. Replace Hejl-Dawson with ACES — the industry-standard filmic tonemap for games
 3. Add sRGB gamma — ACES outputs linear; we need explicit gamma (Hejl-Dawson baked it in)

 uniform sampler2D tex;           // HDR scene
 uniform sampler2D bloom_tex;     // bloom result (mip 0 after upsample chain)
 uniform float exposure;
 uniform float bloom_intensity;   // default 1.0
 uniform int tonemap_operator;    // 0=ACES, 1=Reinhard, 2=Uncharted2, 3=HejlDawson(legacy)

 void main() {
     vec3 color = texture2D(tex, v_texcoord).rgb;

     // Bloom composite (additive, before tonemap)
     vec3 bloom = texture2D(bloom_tex, v_texcoord).rgb;
     color += bloom * bloom_intensity;

     // Exposure
     color *= exposure;

     // Tonemap (default: ACES)
     color = aces_tonemap(color);  // or selected operator

     // Linear -> sRGB gamma
     color = pow(color, vec3(1.0 / 2.2));

     gl_FragColor = vec4(color, texture2D(tex, v_texcoord).a);
 }

 ACES function (~10 lines, Stephen Hill's fitted approximation):
 vec3 aces_tonemap(vec3 x) {
     float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
     return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
 }

 Also include Reinhard and Uncharted2 as alternatives selectable via uniform, for comparison/tuning.

 ---
 Step 4: Modify _setup_tonemapping() in __init__.py

 This is the core integration point. Currently (line 298-343), it creates one scene buffer and one tonemap
 quad. We extend it to create the full bloom chain.

 New flow inside _setup_tonemapping():

 def _setup_tonemapping(self):
     # 1. Scene renders to RGBA16F (existing code, unchanged)
     scene_tex = Texture(); scene_tex.set_format(F_rgba16); ...
     postquad = self._filtermgr.render_scene_into(colortex=scene_tex, fbprops=fbprops)

     if self.enable_bloom:
         # 2. Bloom extract pass (full resolution)
         bloom_extract_tex = Texture('bloom_extract')
         bloom_extract_tex.set_format(Texture.F_rgba16)
         bloom_extract_tex.set_component_type(Texture.T_float)
         extract_quad = self._filtermgr.render_quad_into(colortex=bloom_extract_tex)
         extract_quad.set_shader(make_shader('bloom_extract', 'post.vert', 'bloom_extract.frag', defines))
         extract_quad.set_shader_input('scene_tex', scene_tex)
         extract_quad.set_shader_input('bloom_strength', self.bloom_strength)

         # 3. Downsample chain (5 levels: 1/2 -> 1/4 -> 1/8 -> 1/16 -> 1/32)
         down_textures = [bloom_extract_tex]
         for i in range(5):
             div = 2 ** (i + 1)
             tex = Texture(f'bloom_down_{i}')
             tex.set_format(Texture.F_rgba16)
             tex.set_component_type(Texture.T_float)
             quad = self._filtermgr.render_quad_into(colortex=tex, div=div)
             quad.set_shader(make_shader('bloom_down', 'post.vert', 'bloom_downsample.frag', defines))
             quad.set_shader_input('src_tex', down_textures[-1])
             quad.set_shader_input('texel_size', Vec2(1.0 / (win_x / div), 1.0 / (win_y / div)))
             down_textures.append(tex)

         # 4. Upsample chain (5 levels: 1/32 -> 1/16 -> 1/8 -> 1/4 -> 1/2 -> full)
         MIP_TINTS = [
             Vec3(0.214, 0.429, 0.497),  # fine detail, cool
             Vec3(0.964, 0.947, 0.991),  # near-white
             Vec3(0.982, 0.542, 0.542),  # warm
             Vec3(0.301, 0.493, 1.000),  # blue halo
             Vec3(0.456, 0.209, 0.167),  # deep warm outer
         ]
         up_tex = down_textures[-1]  # start from smallest
         for i in range(5):
             src_idx = len(down_textures) - 2 - i  # work back up
             div = 2 ** (4 - i) if i < 4 else 1  # 16, 8, 4, 2, 1
             tex = Texture(f'bloom_up_{i}')
             tex.set_format(Texture.F_rgba16)
             tex.set_component_type(Texture.T_float)
             if div > 1:
                 quad = self._filtermgr.render_quad_into(colortex=tex, div=div)
             else:
                 quad = self._filtermgr.render_quad_into(colortex=tex)
             quad.set_shader(make_shader('bloom_up', 'post.vert', 'bloom_upsample.frag', defines))
             quad.set_shader_input('src_tex', down_textures[src_idx])
             quad.set_shader_input('bloom_accum_tex', up_tex)
             quad.set_shader_input('texel_size', ...)
             quad.set_shader_input('mip_tint', MIP_TINTS[i])
             up_tex = tex

         bloom_result_tex = up_tex
     else:
         bloom_result_tex = None

     # 5. Final tonemap + composite pass (existing quad, modified shader)
     postquad.set_shader(make_shader('tonemap', 'post.vert', 'tonemap.frag', defines))
     postquad.set_shader_input('tex', scene_tex)
     postquad.set_shader_input('exposure', 2 ** self.exposure)
     postquad.set_shader_input('tonemap_operator', self._tonemap_operator_index)
     if bloom_result_tex:
         postquad.set_shader_input('bloom_tex', bloom_result_tex)
         postquad.set_shader_input('bloom_intensity', self.bloom_intensity)

 ---
 Step 5: Add Python API parameters

 Add new dataclass fields to Pipeline in __init__.py:

 # Bloom
 enable_bloom: bool = False
 bloom_strength: float = 1.0       # extract multiplier (how much scene luminance feeds bloom)
 bloom_intensity: float = 1.0      # final composite multiplier (overall bloom brightness)
 bloom_levels: int = 5             # mip chain depth (2-8)

 # Tonemapping
 tonemap_operator: str = 'aces'    # 'aces', 'reinhard', 'uncharted2', 'hejl_dawson'

 Wire these into __setattr__ for runtime changes:
 - Changing bloom_strength / bloom_intensity updates uniforms directly (no buffer rebuild)
 - Changing enable_bloom / bloom_levels triggers _setup_tonemapping() rebuild
 - Changing tonemap_operator updates the uniform integer

 ---
 Step 6: Game-side integration

 In sfb2 (the game), minimal changes:

 1. Import change: import pax3d_simplepbr as simplepbr (or conditional import for dual-engine support)
 2. Init change:
 simplepbr.init(enable_bloom=True, bloom_strength=1.0, bloom_intensity=1.0, tonemap_operator='aces')
 3. Remove magic numbers: Delete the 0.45x/0.25x/1.8x RGB reduction factors from sun, weapon, and corona
 rendering code (these compensated for the lack of bloom)
 4. Keep setShaderOff() on additive-blended nodes — bloom naturally captures bright fragments regardless

 ---
 Files to create/modify

 ┌───────────────────────────────────┬───────────┬─────────────────────────────────────────────────────┐
 │               File                │  Action   │                        What                         │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/__init__.py       │ Create    │ Pipeline class with bloom chain in                  │
 │                                   │ (fork)    │ _setup_tonemapping()                                │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/shaders.py        │ Create    │ Add bloom_extract.frag, bloom_downsample.frag,      │
 │                                   │ (fork)    │ bloom_upsample.frag; replace tonemap.frag           │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/_shaderutils.py   │ Create    │ Unchanged from simplepbr                            │
 │                                   │ (fork)    │                                                     │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/envmap.py         │ Create    │ Unchanged from simplepbr                            │
 │                                   │ (fork)    │                                                     │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/envpool.py        │ Create    │ Unchanged from simplepbr                            │
 │                                   │ (fork)    │                                                     │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/hdr2env.py        │ Create    │ Unchanged from simplepbr                            │
 │                                   │ (fork)    │                                                     │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/_ibl_funcs_cpu.py │ Create    │ Unchanged from simplepbr                            │
 │                                   │ (fork)    │                                                     │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/textures.py       │ Create    │ Unchanged from simplepbr                            │
 │                                   │ (fork)    │                                                     │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/utils.py          │ Create    │ Unchanged from simplepbr                            │
 │                                   │ (fork)    │                                                     │
 ├───────────────────────────────────┼───────────┼─────────────────────────────────────────────────────┤
 │ pax3d_simplepbr/logging.py        │ Create    │ Unchanged from simplepbr                            │
 │                                   │ (fork)    │                                                     │
 └───────────────────────────────────┴───────────┴─────────────────────────────────────────────────────┘

 ---
 Verification

 1. Basic rendering: Import pax3d_simplepbr, init with enable_bloom=False. Confirm the game renders
 identically to stock simplepbr (the fork works).
 2. ACES tonemapping: Enable ACES without bloom. Compare to Hejl-Dawson — ACES should look slightly more
 saturated with better highlight rolloff.
 3. Bloom on: Enable bloom with default params. Stars, engines, weapon bolts should show natural glow
 halos. No threshold popping — dim things barely bloom, bright things bloom strongly.
 4. Remove compensations: Delete RGB reduction factors from game code. Verify that bloom produces
 equivalent or better visual results without the manual hacks.
 5. Performance: Measure frame time with bloom off vs on. The 11 extra FilterManager passes (most at
 reduced resolution) should add < 2ms on a modern GPU.
 6. Parameter tuning: Adjust bloom_strength, bloom_intensity, exposure at runtime to find good defaults for
  space scenes.
 7. Edge cases: Test interstellar (nearly black), close solar approach (extremely bright), planet surface
 lighting, weapon fire bursts.