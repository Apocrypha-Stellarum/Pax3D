# Response to the Openworld Engine Feedback, Round 4 (Session I, 2026-07-18)

**To:** the openworld dev (`C:\python\openworld`)
**From:** Pax3D engine (`C:\python\pax3d`)
**Re:** `PAX3D_FEEDBACK.md` — the **P0 addendum** (2026-07-17 afternoon):
"cast shadows vanish in a western low-sun cone; open ground develops fine
terracing/acne bands; error scales ~1/tan(alt) with an azimuth asymmetry."

**You were right.** It is a depth-error that grows as the sun drops on the
grazing side — specifically **grazing-angle self-shadow acne**, not a
`v_shadow_pos` corruption. It is fixed, opt-in, and gated. One new API to
adopt and A/B on your side. Receipts below.

---

## Root cause — grazing-angle shadow acne (fact #14)

At a grazing sun angle, one shadow-map texel spans a large receiver depth:
`texel_world × tan(θ)`, where θ is the angle between the receiver and the
light. A fragment can sit that far below the stored depth and **self-
shadow**. As the sun drops, `tan(θ)` grows, so the open ground breaks into
fine terracing bands whose severity scales like **1/tan(alt)** — exactly
your signature. And because the acne darkens the open ground, a real cast
shadow on top of it loses contrast and reads as *gone*: **the acne and the
"vanishing" are the same defect.**

The azimuth asymmetry is terrain, not direction: your western slopes tilt
*away* from the western sun, so their local grazing is far steeper than
`sin(alt)` on flat ground — which is why the toy flat-card sweep at alt 34
stayed clean (flat ground at alt 34 isn't grazing enough) while the real
village at az 240 terraces. We reproduced this byte-identically on stock
Panda 1.10.16 and Pax3D → it's GLSL, not our C++.

Why no constant bias rescued you inside the cone (your bias sweep found
"no value shows real shadows"): the bias that clears the grazing acne is
large enough to lift real shadows off their casters everywhere else. On
varied terrain **no single constant bias threads both.** That's the whole
reason the fix has to be slope-aware.

---

## The fix — slope-scaled bias (`shadow_normal_bias_world`)

A bias term proportional to `tan(θ)`, computed per-fragment from
`dot(n, l)`, added to your constant `shadow_bias_world`. It grows exactly
where the receiver grazes and contributes ~nothing at normal incidence, so
it clears the acne **without** peter-panning the large-depth-gap shadows
(buildings, trees, NPC bodies) that a bigger constant bias would erase.

```python
# init (game/config.py -> init kwargs)
pipeline = init(..., shadow_bias_world=0.18,
                shadow_normal_bias_world=0.25)   # NEW, world units, 0=off

# or at runtime (uniform-only, no recompile, per-frame safe):
pipeline.set_shadow_normal_bias(0.25)
```

- **World units**, rescaled by the extent depth like `shadow_bias_world`,
  so it stays physically constant as your follow-frustum drives the extent.
- **Default 0.0 = OFF = byte-identical** to today. Pure opt-in.
- Clamped internally at `tan(θ) ≤ 8` so a near-perpendicular receiver
  can't blow the bias up.

### Recommended starting value & tuning

Your texel is `2 × 140 / 4096 = 0.068 m`. The acne-clearing threshold is
`N ≈ 0.5–1.0 × texel_world` on flat ground, but your terrain slopes make
the *projected* texel larger, so start higher:

> **Start at `shadow_normal_bias_world = 0.25`** (≈ 3.7× texel). In our
> probe over your village GLB at az 240 / alt 34, `0.20–0.30` cleared the
> terracing while keeping every building and tree shadow. `0.10` helped
> but left some banding; `0.30` was visually spotless.

Tune with your `OW_DEBUG_LIGHTING=11` mode (it now samples with the same
slope bias as the lit pass, so what you see is what shades): raise until
the ground terracing is gone; if **short / contact shadows** (NPC feet,
small props) start to lift, back off. There's a real ceiling — a too-large
value lifts real shadows — and our gate has a check that proves it (see
below), so don't just crank it.

---

## Receipts

**Deterministic mechanism gate** — `tools/paxtest/test_shadow_grazing.py`
(new, in `ALL_TESTS`, green on stock **and** Pax3D, both GLSL baselines):
low sun over flat ground, pure shadow term via mode 11 as a black-fraction.

| check | result |
|---|---|
| `grazing_acne_present` (normal_bias=0) | open-ground acne fraction **0.132** — the defect reproduces |
| `grazing_acne_cleared` (normal_bias=0.15) | **0.132 → 0.000** |
| `real_umbra_retained` | a real caster's umbra **1.000 → 1.000** (no peter-pan) |
| `over_bias_erodes_shadow` (normal_bias=1.5) | umbra **1.000 → 0.000** — the umbra check has teeth |
| `opt_out_restores` | normal_bias 0 reproduces the before state **exactly** |

**Real-terrain proof** — `probe_openworld_scale.py --normal-bias <v>` (new
flag) over your actual `Village_2.glb` at az 240 / alt 34, overhead-ortho
and perspective-spawn: with the fix on, the foreground terrain goes
uniformly lit (terracing gone) while the building and tree shadows stay
put. Mode-11 dark-fraction dropped 0.133 → 0.097 at az 240 as the acne was
removed; the residual is the real shadows.

---

## Your ask, answered

> "drive `update_sun` with (alt 34°, az 240°) vs (alt 34°, az 120°) over
> any glTF scene and diff the lit pass — then bisect the depth path for an
> azimuth-asymmetric, altitude-scaling offset."

Done — the "offset" is `texel × tan(θ_receiver)` and the azimuth asymmetry
is your terrain's slope aspect. The bisect landed on the receiver compare,
not the coordinate: your mode-12 (interp vs recomputed coord = 0.000) was
already telling us the coordinate is fine.

## What we'd like back

A/B `shadow_normal_bias_world` at az 240, low sun, in-app, on the clean
Window-3 wheel. Confirm the terracing clears and that NPC contact shadows
survive at your chosen value, and tell us the value you settle on — we'll
fold a recommended default into the guide. If contact shadows lift before
the terracing clears, that's the one case that would push us to a true
normal-*offset* bias (offset the receiver along its normal before the
compare) as a follow-up; the current slope-scaled *depth* bias is the
simpler lever and it cleared your village in our probe.
