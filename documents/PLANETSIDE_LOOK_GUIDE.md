# Planetside Look Guide — Session J package (2026-07-18)

**Audience:** the openworld dev (Mars colony map) and the sfb2 dev for
future landings. **Engine:** any wheel ≥ Window 3 + this commit; all
three features are pure Python/GLSL in `pax3d_render` — no engine
rebuild needed, they work on stock 1.10.16 too.

**The contract (spaceflight first):** every feature below is opt-in and
byte-identical when off — proven by paxtest with rms-exactly-0 opt-out
checks (`test_atmosphere`, `test_ambient_sh`, `test_shadow_snap`). Your
space segment simply never enables them, or toggles them off on regime
switch: `set_enable_atmosphere(False)`, `clear_ambient_sh()`,
`set_shadow_texel_snap(False)` restore the exact pre-call output.

---

## 1. Aerial perspective / height haze (`enable_atmosphere`)

Distant terrain fades into a haze color with exponential height falloff,
tinted toward a second color when looking sunward (forward-scatter glow).
Evaluated analytically per fragment — a handful of ALU, no ray march, no
extra passes.

```python
pipeline.set_enable_atmosphere(True)        # recompile-class (one hitch)
pipeline.set_atmosphere_params(             # uniform-only, per-frame safe
    haze_color=(0.42, 0.28, 0.18),          # Mars butterscotch horizon
    sun_haze_color=(0.85, 0.55, 0.35),      # warm glow around the sun
    sun_power=10.0,                         # tightness of that glow
    density=0.0012,                         # 1/density = ~63%-haze distance
    scale_height=45.0,                      # haze e-folds every 45 m up
    base_height=0.0,                        # world z of ground datum
)
```

Mars starting values above assume ~metre world units and a map a few km
across; the openworld toy-scale equivalents want density ~5–10× higher.
Tuning loop:

1. Set `density` so the FARTHEST buildings are readably hazed but not
   erased: `density = 1.5 / (farthest interesting distance)` is a good
   first guess (τ=1.5 → 78% haze).
2. Match `haze_color` to your skybox horizon — the shader does not draw
   the sky; if the colors match, geometry appears to dissolve INTO the
   sky and the fake is invisible. Colors are linear HDR (they go through
   the tonemap), so expect to set them brighter than the final screen
   color.
3. `scale_height`: stand on the highest structure — if the world below
   looks like a fog sea, raise it; if the haze reads as screen-space fog
   with no altitude character, lower it.
4. `sun_haze_color`/`sun_power`: look at the low sun through the haze;
   power 6–12 is a soft glow, 30+ a tight halo. Pairs beautifully with
   the low-sun shadow work from Session I.
5. For dust storms: raise density 5–10× and desaturate both colors — it
   is a per-frame-safe uniform, so you can animate weather.

Physics notes: heights are world-z; `density=0` is an exact no-op; the
legacy `enable_fog` path is untouched (if both are on, fog applies
first). Emissive windows/lights haze out correctly (extinction applies
after emission).

## 2. Hemisphere ambient (`set_hemisphere_ambient`)

The single biggest cheap outdoor-shading win. Today both games run a flat
AmbientLight: shadowed surfaces are a uniform gray regardless of facing.
This replaces that with a two-tone environment — sky color from above,
ground bounce from below, smoothly blended by the surface normal — via
the SH irradiance path that has been sitting zeroed in the shader since
R1 (zero new per-fragment cost worth mentioning: the mul-adds were
already executing on zeros).

```python
# Mars: salmon sky, rusty ground bounce (linear, includes ambient level)
pipeline.set_hemisphere_ambient(sky_color=(0.16, 0.10, 0.08),
                                ground_color=(0.10, 0.05, 0.03))
```

Rules:

- **Replace, don't stack.** Drop your AmbientLight to near-black (keep a
  tiny one attached — a scene with NO lights floods the PBR ambient
  white). Put the level you had in the flat ambient into these two
  colors instead.
- Shadow readability is dominated by the sun:ambient ratio (your own
  Session E finding) — after switching, re-check your shadow contrast
  and pull the levels down until shadows read again; the win is that
  shadowed faces now have DIRECTION (sky-lit tops, bounce-lit bottoms).
- A surface facing straight up receives `avg + 2/3 * delta` (avg/delta =
  mean and half-difference of the two colors); straight down gets
  `avg - 2/3 * delta`. So the vertical contrast you see is 4/3 × the
  color difference you author.
- `clear_ambient_sh()` restores the flat-ambient-only look exactly
  (space regime).

For a real skybox-driven ambient there is `pax3d_render.sh_from_cubemap
(tex)` → `pipeline.set_ambient_sh(coeffs)` — EXPERIMENTAL: its up/down
axis and overall level are validated by the harness; sanity-check the
horizontal orientation against your skybox (e.g. sunset side tints the
correct flank) before tuning content to it, and tell us if it is
flipped so we can pin the face table.

## 3. Shadow texel snapping (`shadow_texel_snap`)

You already built exactly this in `app.py:_follow_shadow_frustum` —
snapping the followed shadow center to the texel grid so edges don't
crawl while walking. It is now engine-side and light-space-correct (it
snaps along the light's film axes, which is what actually matters, and
re-derives the grid when the sun moves):

```python
pipeline = pax3d_render.init(..., shadow_texel_snap=True)   # or:
pipeline.set_shadow_texel_snap(True)                        # runtime, free
# keep driving set_shadow_extent(radius, depth, center=player_pos) per frame
```

You can delete your game-side snap and just pass the raw followed center.
Two interactions to know: the center may sit up to half a texel from
what you passed, so keep the half-texel extent margin you already have;
and if you change `radius` on the fly the grid size changes with it
(snap assumes a settled extent — quantize your radius steps).

Measured: a 0.3-texel center move re-rasterizes 24 depth texels with
snap off (the shimmer), 0 across the whole sub-texel sweep with it on,
and a 2-texel move still re-rasterizes 152 (the frustum follows — it is
not frozen). `tools/paxtest/test_shadow_snap.py`.

## 4. The full Mars stack, together

Recommended order of adoption (each step is independently revertible):

1. `shadow_texel_snap=True` — pure win, no tuning, replaces your
   game-side snap.
2. `set_hemisphere_ambient(...)` — retune ambient level + shadow
   contrast once.
3. `set_enable_atmosphere(True)` + params — tune against your skybox.
4. Existing Session E/I knobs still apply on top: `shadow_bias_world`,
   `shadow_normal_bias_world` (az-240 low sun), `shadow_filter_size=3`,
   `exclude_from_shadows()` for any sky/cloud cards.

Report back what values you settle on (and any sh_from_cubemap
orientation surprises) — they seed the sfb2 planet-landing presets.

## 5. Retuning for EXPANDED terrain (surround maps, deep valleys — Session P field note)

The original Mars values were tuned for a 660 m colony map at one
altitude datum. Two things break when the world grows:

1. **Distance:** `density=0.0018` (1/density ≈ 555 m) EATS ~99% at
   2 km by design — an expanded desert is invisible from the ground
   (airborne-only reveal, as MARS_SURROUND_TERRAIN.md observed).
2. **Depth:** the exponential height medium multiplies density by
   `exp(-(z - base_height)/scale_height)` BELOW the datum. With
   `base_height=0, scale_height=50`, a −158 m valley floor runs at
   e^{158/50} ≈ **24× density** — visibility ~23 m, whiteout at your
   feet. (This is the "haze looks centered on the map middle" field
   report: the middle IS the high datum ground; the physics is doing
   exactly what it was configured to do.)

Retune recipe — all three knobs are `set_atmosphere_params` uniforms,
free to tune LIVE in-game:

- `scale_height`: raise to ~3× the terrain's altitude span (e.g. 180
  for ±160 m) so valleys/peaks swing density by ~e^{±1} instead of
  e^{±3}.
- `base_height`: move the datum to mid-terrain (e.g. −80), not the
  highest ground.
- `density`: pick by target visibility — haze fraction at distance d
  is `1 − exp(−density·d·amp)`. Candidate presets for the expanded
  Mars map (amp ≈ 0.64 at the colony with base −80/H 180):

| Intent | density | H | base | Colony ring (600 m) | Surround (2 km) | Valley floor amp |
|---|---|---|---|---|---|---|
| Keep thick colony dust, just fix valleys | 0.0025 | 180 | −80 | ~62% (as tuned) | ~96% (airborne reveal) | 1.5× |
| Balanced (massif emerges from dust) | 0.0012 | 180 | −80 | ~37% | ~79% | 1.5× |
| Ground-visible desert | 0.0008 | 200 | −80 | ~27% | ~64% | 1.5× |

The "which" is aesthetic — the surround author deliberately left it
open. Whatever wins, the valley fix (scale_height + base_height) is
non-negotiable for walkable low ground.
