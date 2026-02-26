# Directional Lighting — Problem Analysis and Engine Fix Plan

**Project:** Pax3D (Panda3D fork)
**Context:** Pax Abyssi space simulation — persistent planet lighting bug
**Date:** 2026-02-26

---

## 1. Problem Statement

Pax Abyssi has one directional light: the local star illuminating planets, moons, ships, and stations. This should be the simplest lighting scenario possible. After months of investigation it is still fragile, poorly understood at the engine level, and surrounded by workaround code.

The immediate symptom is that the lit hemisphere of a planet faces the wrong direction, or changes with camera orientation, depending on which HPR formula is used. Four different formulas were tested live. Three produced visually wrong results. The fourth (Formula B) works empirically but contradicts a clean mathematical analysis that says the opposite formula (Formula C) should be correct. The same simplepbr shader, applied to two different sphere meshes, produces opposite lighting results.

The root cause is a combination of five interacting problems at the engine and API level. This document analyses each one, proposes engine-level fixes in Pax3D, and lays out what the game code needs to do before those fixes are available.

---

## 2. Root Cause Analysis

### 2.1 Two Disconnected Direction Representations

`DirectionalLight` maintains two independent representations of "direction" that are not kept in sync.

**Representation A: the `_direction` CycleData field** (`directionalLight.I` lines 106-111)

```cpp
INLINE void DirectionalLight::
set_direction(const LVector3 &direction) {
  CDWriter cdata(_cycler);
  cdata->_direction = direction;
  mark_viz_stale();
}
```

Default value: `LVector3::forward()` — the +Y axis in Panda3D's Y-forward coordinate system.

This field is what the shader pipeline actually reads. In `graphicsStateGuardian.cxx` line 2224, `fetch_specified_light()` builds `LA_position` from it:

```cpp
LVector3 dir = -(light->get_direction() * light_mat);
into[Shader::LA_position].set(dir[0], dir[1], dir[2], 0);
```

The w=0 flags this as a directional light to GLSL. The xyz is `-(get_direction() * light_mat)`, i.e. the negated direction, world-transformed. simplepbr reads this as the "toward light source" vector.

**Representation B: the NodePath HPR** (what `setHpr()` / `lookAt()` set)

The NodePath transform controls the node's visual orientation and matrix. For all light types other than `DirectionalLight`, the shader reads the lens nodal point from the transform to get light position. For `DirectionalLight`, the shader reads `get_direction()` instead — but `setHpr()` does NOT update `_direction`. They are completely independent.

When `setHpr(H, P, 0)` is called on a DirectionalLight NodePath, `_direction` is unchanged. The shader sees the old `_direction`. The HPR only takes effect if `xform()` is called on the node itself (e.g. via a parent transform), which calls `cdata->_direction = cdata->_direction * mat`.

**This is the core API confusion.** Game code assumes `setHpr()` controls light direction. The shader ignores the NodePath transform entirely and reads `_direction` directly. The two only stay in sync if the light node is attached to a parent that transforms it via `xform()`.

### 2.2 The HPR Formula Confusion

Because the game is using `setHpr()` on the DirectionalLight NodePath (via `sun_light_np.setHpr(heading, pitch, 0)`), and because the planet sphere in `planet_factory.py` appears to be illuminated by the NodePath's forward vector rather than `_direction`, the game's behavior can only be explained if there is a mechanism connecting the two — specifically that the shader reads the node's forward vector rather than `_direction` when a transform matrix is involved.

The observed behavior, confirmed by the debug dump in `debug_modules/lighting_debug.md`:

```
FORMULA: B: atan2(-x,y)
sun_dir  (to sun):     (1.000, -0.009, -0.004)
Light +Y fwd:          (1.000, -0.009, -0.004)   <- forward = sun_dir
VIEW: EAST — Looking down X axis POSITIVE
```

Formula B produces `forward = sun_dir`. The lit hemisphere faces forward. This is correct visually in-game.

The mathematically derived Formula C (which gives `forward = -sun_dir`, with lit side facing -forward) is correct for a clean isolated simplepbr test with a procedural UV sphere. Same engine, same simplepbr version, opposite result.

**The four formulas tested:**

| Formula | Heading expression | Pitch expression | forward relationship | Lit side in-game |
|---------|-------------------|------------------|---------------------|-----------------|
| A | `atan2(sun_dir.x, sun_dir.y)` | `atan2(sun_dir.z, horiz)` | forward ≈ (-x, y, z) — X flipped | Wrong |
| B | `atan2(-sun_dir.x, sun_dir.y)` | `atan2(sun_dir.z, horiz)` | forward = sun_dir | Correct |
| C | `atan2(sun_dir.x, -sun_dir.y)` | `atan2(-sun_dir.z, horiz)` | forward = -sun_dir | Wrong |
| D | `lookAt(-sun_dir)` | same as C | forward = -sun_dir | Wrong |

Formula B is empirically correct. Formula C is algebraically correct for the standard Panda3D/simplepbr convention. The discrepancy is explained by Section 2.3.

### 2.3 Winding-Dependent Lighting Inversion

Triangle winding order determines which face is "front" in OpenGL. If simplepbr's fragment shader uses `gl_FrontFacing` to conditionally flip normals (a common technique for two-sided lighting or to recover from backwards winding), then different winding on the planet mesh versus the test sphere would flip the effective normal direction and therefore invert which hemisphere is lit.

The game's planet sphere winding, from `modules/planet_factory.py` lines 416-423:

```python
tris.addVertices(bottom_left, bottom_right, top_left)
tris.addVertices(bottom_right, top_right, top_left)
```

In Panda3D's Y-forward, Z-up, right-handed coordinate system, this winding produces normals pointing inward (toward the sphere center) for an outward-facing sphere — or the normals are set explicitly as `(x, y, z)` (outward) in the vertex data but the triangle winding is counter-clockwise from outside, meaning front-faces are the outside faces. Whether this is "correct" depends on which face OpenGL considers front.

The test sphere in `tools/lighttest.py` (formerly `test_directional_light.py`) used a different winding that produced the mathematically expected result. The discrepancy in behavior between the two spheres is consistent with one of them having back-faces lit because the effective normal is flipped.

Until simplepbr's fragment shader is inspected for `gl_FrontFacing` usage, this remains a probable-but-unconfirmed cause. It is not blocking for the game since Formula B works empirically, but it is essential context for the engine fix.

### 2.4 lookAt() and setPos() Corrupt Transforms Under simplepbr

`lookAt()` sets both position and rotation on the NodePath. For a DirectionalLight, position is meaningless (infinitely distant), but when simplepbr's FilterManager is active it moves the main camera to an offscreen buffer. The additional matrix components from `setPos()` or `lookAt()` appear to corrupt the transform that the shader pipeline reads, causing the light to flip its effective axis.

This was confirmed empirically in Session 417: removing `setPos()` calls from the position-100 code path fixed an associated lighting artifact. The underlying mechanism is that `setPos()` leaves a non-identity translation in the transform chain; when the `xform()` path is used, this contaminates the `_direction` transformation.

**Safe approach:** use `setHpr()` only on a DirectionalLight NodePath. Never call `setPos()`, `setFluidPos()`, or `lookAt()`.

### 2.5 `_direction` Is Not Updated by `setHpr()`

As established in Section 2.1, `setHpr()` on the NodePath does not call `set_direction()`. This means:

- If the game code relies on `get_direction()` for any purpose (e.g. shadow map orientation), it will get the stale default direction, not the current HPR-derived direction.
- The engine's fixed-function path (`bind_light()` in `glGraphicsStateGuardian_src.cxx` line 9667) reads `light_obj->get_direction()` directly and transforms it: `LVector3 dir = light_obj->get_direction() * transform->get_mat()`. This IS transform-aware. The GLSL path in `graphicsStateGuardian.cxx` line 2224 also multiplies by `light_mat` which is derived from the NodePath's transform. So BOTH paths do apply the NodePath transform to `_direction` — but only if `_direction` starts as the identity forward vector.
- The default `_direction` is `LVector3::forward()` = (0, 1, 0). If the game never calls `set_direction()`, then `_direction` stays at (0,1,0), and the shader derives `LA_position = -(forward * light_mat)`. The light_mat is derived from the NodePath's transform — i.e. from `setHpr()`. So `setHpr()` DOES indirectly control `LA_position` through the matrix multiplication, as long as `_direction` is the identity forward vector.

**This is why the code works at all:** the NodePath transform from `setHpr()` rotates the default `_direction` vector through `light_mat`, giving the correct `LA_position`. But this is fragile — any call to `set_direction()` with a non-identity vector would break the relationship.

---

## 3. Current Game Workarounds

### 3.1 Formula Toggle (Shift+F9)

`modules/sun_position_manager.py` has a live formula toggle cycling four HPR formulas:

```python
# Light formula toggle: 0=A atan2(x,y), 1=B atan2(-x,y), 2=C atan2(x,-y), 3=lookAt
self._light_formula = 2  # default to C (incorrect for game — needs to be 1/B)
```

The default is still set to C (index 2), despite Formula B (index 1) being the confirmed working formula. This is temporary debug code that needs to be cleaned up.

### 3.2 Four-Formula HPR Computation

The HPR block in `sun_position_manager.py` lines 196-218 dispatches through all four formulas:

```python
f = self._light_formula
if f == 0:  # A: atan2(x, y)
    heading = math.degrees(math.atan2(sun_dir.x, sun_dir.y))
    pitch = math.degrees(math.atan2(sun_dir.z, horiz_len))
elif f == 1:  # B: atan2(-x, y)
    heading = math.degrees(math.atan2(-sun_dir.x, sun_dir.y))
    pitch = math.degrees(math.atan2(sun_dir.z, horiz_len))
elif f == 2:  # C: atan2(x, -y)
    heading = math.degrees(math.atan2(sun_dir.x, -sun_dir.y))
    pitch = math.degrees(math.atan2(-sun_dir.z, horiz_len))
else:  # D: lookAt
    tmp = app.render.attachNewNode("tmp_lookat")
    tmp.lookAt(Point3(-sun_dir.x * 10, -sun_dir.y * 10, -sun_dir.z * 10))
    heading = tmp.getH()
    pitch = tmp.getP()
    tmp.removeNode()
```

The Formula D lookAt path creates and destroys a temporary node every frame — a performance hazard.

### 3.3 Debug Overlay (Ctrl+L)

`modules/planetary_debug_tools.py` provides live 3D direction lines and an OSD readout. The angle check and line legend are calibrated for the wrong formula (Formula C: lit = -forward). They need updating for Formula B (lit = +forward). Ctrl+Left/Right cardinal cycling is currently broken.

### 3.4 setPos() Guard

`sun_position_manager.py` line 93-94 has an explicit comment blocking `setPos()` on the DirectionalLight at position 100:

```python
# NOTE: Do NOT setPos() on the DirectionalLight.  DirectionalLights
# are infinitely distant; setPos() corrupts the transform under simplepbr.
```

This is a workaround for the `lookAt()` / `setPos()` corruption described in Section 2.4.

---

## 4. Proposed Engine-Level Fixes

### Fix 1: Clarify and Document the `set_direction()` / `setHpr()` Relationship

**Files:** `panda/src/pgraphnodes/directionalLight.h`, `directionalLight.I`, `directionalLight.cxx`

**The problem to document:** The existing `set_direction()` and `get_direction()` methods operate on the `_direction` CycleData field, which is independent of the NodePath HPR. The shader pipeline builds `LA_position` as `-(get_direction() * light_mat)` where `light_mat` is the NodePath's net transform. This means:

- If you use `set_direction()` to a non-forward vector but leave the NodePath at identity HPR, light_mat = identity and the direction is used as-is.
- If you use `setHpr()` and leave `_direction` at its default `LVector3::forward()`, the HPR rotation is applied to the forward vector via light_mat.
- If you mix both, they interact multiplicatively in an unintuitive way.

**Proposed: add a Python-level `set_direction_from_hpr()` convenience or document the canonical pattern clearly.** The safest game code pattern is to keep `_direction` at its default (never call `set_direction()`) and use only `setHpr()` to control orientation.

Add a docstring to `set_direction()` in `directionalLight.I` that warns:

```cpp
/**
 * Sets the direction in which the light is aimed.  This is local to the
 * coordinate space in which the light is assigned.
 *
 * Note: this field is INDEPENDENT of the NodePath HPR.  The shader
 * pipeline computes the light direction as get_direction() transformed by
 * the NodePath's net transform matrix.  If you use setHpr() on the
 * NodePath to orient the light, leave _direction at its default
 * LVector3::forward() (do not call set_direction()).  Mixing set_direction()
 * with setHpr() produces compounded rotation that is usually not desired.
 *
 * Preferred usage for dynamic orientation: attach to render, keep
 * _direction at default, call setHpr() each frame.
 */
```

### Fix 2: Add `set_direction_world(LVector3)` Method

**Files:** `panda/src/pgraphnodes/directionalLight.h`, `directionalLight.I`

A high-level method that takes a world-space direction vector (the direction light travels, i.e. from source toward scene) and configures the node so the shader produces correct results, without any manual atan2 computation in game code:

```cpp
PUBLISHED:
  void set_direction_world(const LVector3 &travel_direction);
```

Implementation in `directionalLight.cxx`:

```cpp
/**
 * Sets the DirectionalLight to illuminate from the direction opposite to
 * travel_direction.  travel_direction is the vector from light source to
 * scene (the direction photons travel).  The node must be parented to
 * render (or another node at identity transform) for this to be correct.
 *
 * Internally: resets _direction to LVector3::forward() and computes HPR
 * such that forward rotated by the HPR equals travel_direction.  This is
 * equivalent to calling setHpr(H, P, 0) where:
 *   H = atan2(-d.x, d.y)
 *   P = atan2(d.z, sqrt(d.x^2 + d.y^2))
 * with travel_direction normalised to d.
 *
 * After this call, get_direction() returns LVector3::forward() and the
 * NodePath HPR encodes the actual direction.
 */
void DirectionalLight::
set_direction_world(const LVector3 &travel_direction) {
  // Reset CData direction to forward — let the NodePath HPR do the work
  CDWriter cdata(_cycler);
  cdata->_direction = LVector3::forward();
  mark_viz_stale();

  // Compute HPR: setHpr(H, P, 0) such that the rotated forward = travel_direction
  LVector3 d = travel_direction.normalized();
  PN_stdfloat horiz = csqrt(d[0]*d[0] + d[1]*d[1]);
  PN_stdfloat heading = rad_to_deg(catan2(-d[0], d[1]));
  PN_stdfloat pitch   = rad_to_deg(catan2( d[2], horiz));

  // Note: this sets HPR on the NodePath containing this node, not on the
  // node itself.  The caller must hold a NodePath reference.
  // We store heading and pitch for retrieval; the NodePath setHpr must be
  // called by the caller on the containing NodePath.
  // -- Implementation detail: expose as a NodePath extension method instead
  //    (see Fix 2a below)
}
```

**Problem with this approach:** `DirectionalLight` (a `PandaNode`) does not have a reference to its own containing `NodePath`. HPR must be set on the NodePath, not the node.

**Fix 2a: Implement as a Python-level NodePath extension instead.**

In the Python layer (e.g. a Pax3D extension module or monkey-patch at startup), add:

```python
def set_sun_direction(nodepath, travel_direction):
    """
    Orient a DirectionalLight NodePath so it illuminates from the given
    travel_direction (the direction photons travel: from source to scene).

    travel_direction is a Vec3 in world space pointing from the light source
    toward the scene. For a star at +X relative to a planet, travel_direction
    = Vec3(-1, 0, 0) (photons travel from star toward planet).

    Requires: nodepath is parented to render at identity position.
    Never call setPos() on a DirectionalLight; it has no effect and may
    corrupt transforms under simplepbr.
    """
    d = travel_direction.normalized()
    horiz = math.sqrt(d.x**2 + d.y**2)
    heading = math.degrees(math.atan2(-d.x, d.y))
    pitch   = math.degrees(math.atan2( d.z, horiz))
    nodepath.setHpr(heading, pitch, 0)
```

This is the canonical Formula B expressed as a named utility. Game code becomes:

```python
# Before (confusing, formula-index-dependent):
app.lighting.sun_light_np.setHpr(heading, pitch, 0)

# After (clear intent):
set_sun_direction(app.lighting.sun_light_np, sun_dir)
# where sun_dir = planet-to-sun unit vector = direction photons travel
```

The formula `atan2(-d.x, d.y)` for heading is derived from solving:
```
setHpr(H, P, 0) maps +Y forward to:  (-sin(H)*cos(P),  cos(H)*cos(P),  sin(P))
We need forward = d:
  -sin(H)*cos(P) = d.x  →  sin(H) = -d.x / cos(P)
   cos(H)*cos(P) = d.y  →  cos(H) =  d.y / cos(P)
   sin(P)        = d.z
Therefore: H = atan2(-d.x, d.y),  P = atan2(d.z, horiz_len)
```

This produces `light_node.forward = sun_dir`, so the shader's `LA_position = -(forward * identity_mat) = -sun_dir`, which simplepbr reads as the "toward light source" vector. Since the planet sphere winding causes simplepbr to flip the effective normal, the lit side faces forward rather than -forward — which is correct for the game's planet geometry.

### Fix 3: Override `lookAt()` on DirectionalLight NodePath to Block Position Changes

**Files:** `panda/src/pgraph/nodePath.cxx` (or Python-level interception)

The `lookAt()` method on a NodePath sets both position and rotation. For DirectionalLights this is always wrong: the position component corrupts the transform. Pax3D should either:

**Option A (Python-level):** Detect DirectionalLight nodes at `plan_initialization_manager.py` and assert if `setPos()` or `lookAt()` is called:

```python
class ProtectedDirectionalLight:
    """Wraps a DirectionalLight NodePath and blocks position-mutating calls."""
    def __init__(self, np):
        self._np = np

    def setHpr(self, h, p, r):
        self._np.setHpr(h, p, r)

    def setPos(self, *args):
        raise RuntimeError(
            "setPos() on DirectionalLight corrupts transforms under simplepbr. "
            "DirectionalLights are infinitely distant; use setHpr() only."
        )

    def lookAt(self, *args):
        raise RuntimeError(
            "lookAt() on DirectionalLight sets position AND rotation. "
            "Use set_sun_direction() instead."
        )
```

**Option B (engine-level):** In `directionalLight.cxx`, override the `xform()` method to zero out the translation component before applying:

```cpp
void DirectionalLight::
xform(const LMatrix4 &mat) {
  // Strip translation from mat before applying to direction.
  // DirectionalLights are infinitely distant; position is irrelevant and
  // corrupts the direction under simplepbr's FilterManager.
  LMatrix4 rot_only = mat;
  rot_only.set_row(3, LVecBase4(0, 0, 0, 1));
  LightLensNode::xform(rot_only);
  CDWriter cdata(_cycler);
  cdata->_point = cdata->_point * rot_only;
  cdata->_direction = cdata->_direction * rot_only;
  mark_viz_stale();
}
```

Option B is safer engine-wide; Option A is easier to implement in Pax3D today.

### Fix 4: Verify That Position Data Cannot Contaminate `LA_position` for DirectionalLights

**File:** `panda/src/display/graphicsStateGuardian.cxx` lines 2220-2225

The GLSL path correctly sets `w=0` to signal a directional light:

```cpp
LVector3 dir = -(light->get_direction() * light_mat);
into[Shader::LA_position].set(dir[0], dir[1], dir[2], 0);  // w=0 = directional
```

The `light_mat` here is derived from the NodePath's net transform — which includes translation if `setPos()` has been called. The direction transformation `get_direction() * light_mat` uses `xform_vec()` semantics (ignores translation) because `_direction` is an `LVector3` not an `LPoint3`. However, the translation in `light_mat` does not contaminate the direction calculation itself.

The corruption described in Section 2.4 is therefore NOT in the direction calculation but likely in the shadow map or some other component that reads the full transform. For Pax3D, confirm this by adding an assertion:

```cpp
// In fetch_specified_light, after the DirectionalLight branch:
#ifdef NOTIFY_DEBUG
  // Sanity check: translation should be zero for directional lights
  LPoint3 node_pos = np.get_pos(np.get_parent());
  if (!node_pos.almost_equal(LPoint3::zero(), 0.001f)) {
    pgraph_cat.warning()
      << "DirectionalLight " << np.get_name()
      << " has non-zero position " << node_pos
      << " — this has no effect but may corrupt shadow maps.\n";
  }
#endif
```

---

## 5. simplepbr Investigation Plan

simplepbr is an external dependency (not in the Pax3D source tree), but its fragment shader determines whether the winding discrepancy (Section 2.3) causes normal inversion.

### What to look for in simplepbr's fragment shader:

**1. `gl_FrontFacing` usage**

Search the simplepbr fragment shader source for `gl_FrontFacing`. If present, it typically appears as:

```glsl
vec3 n = normalize(v_normal);
if (!gl_FrontFacing) {
    n = -n;
}
```

or

```glsl
vec3 n = normalize(v_normal) * (gl_FrontFacing ? 1.0 : -1.0);
```

If simplepbr flips the normal for back-faces, then a planet sphere with inward winding (back-faces visible from outside) would have its normals flipped relative to a sphere with outward winding. This would explain why Formula C works for the test sphere (outward-wound) and Formula B works for the game sphere (inward-wound or vice versa).

**2. Normal vector sourcing**

Check whether simplepbr reads normals from the vertex attribute directly, from a normal map, or from `dFdx`/`dFdy` (geometry normals). Geometry-derived normals are always correct regardless of the vertex normal direction, and always face the camera, which would make lighting camera-dependent — a separate problem described in Section 2.3 of the cinematic camera handover.

**3. Light vector convention**

Confirm simplepbr's convention for `p3d_LightSource[i].position.xyz`. Per the engine code in Section 2.1, w=0 means directional and xyz is `-(get_direction() * light_mat)` — the "toward light source" vector in view space or world space depending on the transform chain.

In simplepbr the typical pattern is:

```glsl
vec3 l = normalize(p3d_LightSource[i].position.xyz);
float NdotL = max(dot(n, l), 0.0);
```

If `l` is "toward light source" and `n` is the outward surface normal, `NdotL > 0` on the lit side. If the normals are inward, `NdotL` is negative and the lit side is reversed.

### Practical test to confirm the winding hypothesis:

In `modules/planet_factory.py`, reverse the winding of one quad and test whether lighting flips:

```python
# Current winding (produces formula-B correct illumination):
tris.addVertices(bottom_left, bottom_right, top_left)
tris.addVertices(bottom_right, top_right, top_left)

# Reversed winding:
tris.addVertices(top_left, bottom_right, bottom_left)
tris.addVertices(top_left, top_right, bottom_right)
```

If reversing the winding makes Formula C correct (and breaks Formula B), the winding hypothesis is confirmed.

---

## 6. Immediate Game-Side Fixes

These can be done now, before any engine changes.

### 6.1 Fix Formula Default and Remove Toggle Code

In `modules/sun_position_manager.py`:

**Step 1:** Change `self._light_formula = 2` to `self._light_formula = 1` temporarily (so the game works correctly on startup).

**Step 2:** After validating Formula B at all four cardinal positions (Section 7), remove the toggle entirely and hard-code the formula:

```python
# Remove these from __init__:
#   self._light_formula = 2
#   app.accept("shift-f9", self._cycle_light_formula)

# Remove these class-level attributes:
#   _FORMULA_NAMES
#   _cycle_light_formula()

# Replace the formula dispatch block (lines 196-218) with:
heading = math.degrees(math.atan2(-sun_dir.x, sun_dir.y))
horiz_len = math.sqrt(sun_dir.x ** 2 + sun_dir.y ** 2)
pitch = math.degrees(math.atan2(sun_dir.z, horiz_len))
app.lighting.sun_light_np.setHpr(heading, pitch, 0)
app.lighting.set_sun_direction(sun_dir)
```

### 6.2 Fix Debug Angle Check

In `modules/planetary_debug_tools.py` line 208, the angle check computes `dot(-forward, sun_visual_dir)` expecting ~0 degrees. With Formula B, `forward = sun_dir`, so the check should be `dot(forward, sun_visual_dir)`:

```python
# WRONG (assumes Formula C: lit = -forward):
toward_light = Vec3(-fwd)

# CORRECT for Formula B (lit = +forward, forward = sun_dir):
toward_light = Vec3(fwd)
```

The OSD label should also change from "ANGLE (-fwd vs sun)" to "ANGLE (fwd vs sun)".

### 6.3 Fix Debug Line Legend

In `modules/planetary_debug_tools.py`, the docstring, console printout, and `_write_dump_file()` legend currently state:

```
GREEN line  = light travel direction (should OPPOSE yellow)
RED line    = toward light source (should OVERLAP yellow)
If correct: YELLOW and RED overlap, GREEN opposes them
```

With Formula B (`forward = sun_dir`), the correct legend is:

```
GREEN line  = light forward = toward sun (should OVERLAP yellow)
RED line    = away from sun (should OPPOSE yellow)
If correct: YELLOW and GREEN overlap, RED opposes them
```

Update all three locations: the class docstring at line 17, `toggle_lighting_debug()` console print at line 113-116, and `_write_dump_file()` at lines 290-297.

### 6.4 Fix Ctrl+Left/Right Cardinal Cycling

From the handover: "Ctrl+Left/Right reportedly not working even with debug active." The guard `if not self.active: return` is correct. Check for key binding conflicts with navigation controls (arrow keys are likely bound to spacecraft rotation). Consider changing the binding to `Ctrl+Shift+Left/Right` if arrow keys are consumed elsewhere.

### 6.5 Fix the Angle Check in the Debug Dump File

The auto-generated dump at `debug_modules/lighting_debug.md` shows:

```
ANGLE (-fwd vs sun): 180.0 deg
  >> MISMATCH: expected ~0, got 180.0
```

This is because the angle check uses `-fwd` but Formula B gives `fwd = sun_dir`, so the angle between `-fwd` and `sun_visual_dir` is 180 degrees — that is the expected result for a correct Formula B setup. After applying the fix in Section 6.2, this will read `~0.0 deg — OK`.

### 6.6 Investigate Winding in planet_factory.py

This is labelled optional in the handover but is important for understanding correctness guarantees. Compare the triangle winding between `modules/planet_factory.py:_create_procedural_sphere()` (lines 408-423) and the test sphere in `tools/lighttest.py`. Document whether they differ and whether reversing game sphere winding changes which formula is correct. This determines whether the Formula B "fix" is working around a winding error or is genuinely the correct formula for the game's mesh convention.

---

## 7. Testing Plan

### 7.1 Standalone Test (tools/lighttest.py)

The standalone test (`tools/lighttest.py`, formerly `test_directional_light.py`) creates a clean simplepbr context with a UV sphere and tests lighting at preset HPR values. Use this to:

1. Confirm that Formula C (`forward = -sun_dir`) is correct for the test sphere
2. Test with reversed winding (Section 5) to confirm the inversion
3. After engine Fix 2 (set_direction_world), test that the new API produces the same result as the manual atan2 calculation

### 7.2 In-Game Cardinal Position Test

Use `Ctrl+L` to enable the debug overlay, then `Ctrl+Left/Right` (after fixing cycling in Section 6.4) to step through SOUTH, WEST, NORTH, EAST:

| Cardinal | Ship position | Sun direction | Expected lit side | Formula B heading |
|----------|--------------|---------------|------------------|-------------------|
| SOUTH | (0, -180, 0) | +Y | +Y hemisphere (north pole) | H=0, P=0 |
| WEST | (180, 0, 0) | -X | -X hemisphere | H=90, P=0 |
| NORTH | (0, 180, 0) | -Y | -Y hemisphere (south pole) | H=180, P=0 |
| EAST | (-180, 0, 0) | +X | +X hemisphere (confirmed) | H=-90, P=0 |

For each cardinal, use `Shift+F9` to confirm that only Formula B (index 1) produces correct illumination, then confirm that the cleaned-up hard-coded formula produces the same result.

### 7.3 Elevation Tests

Test sun positions with non-zero Z component (sun above or below the ecliptic plane):

- Sun at (1, 0, 1) normalised: pitch should be ~45°, lit side should be +X+Z hemisphere
- Sun at (0, 1, -1) normalised: pitch should be ~-45°, south pole facing sun

These exercise the pitch formula `atan2(sun_dir.z, horiz_len)`.

### 7.4 Multi-Mesh Test

Verify consistent lighting across different mesh types:

- **Planet sphere** (procedural, `planet_factory.py`) — primary test
- **Moon sphere** (may use same factory or a different path — verify)
- **Ship model** (GLTF, `phobos_v3.glb`) — GLTFs have well-defined winding (counter-clockwise by spec), check if lighting is consistent
- **Space station** (GLTF) — same check

If GLTF meshes show opposite lighting to the procedural planet sphere, the winding hypothesis is confirmed: the procedural sphere has non-standard winding and the game should either fix the sphere winding or accept that Formula B is the correct compensating formula.

### 7.5 Shadow Mapping Test

Enable shadows in `config/settings.json`:

```json
"enable_shadows": true
```

With correct directional lighting, shadows should fall on the side of objects away from the sun visual. Verify at all four cardinal positions.

If shadows are correct but hemisphere lighting is wrong (or vice versa), the shadow map reads from a different source than the diffuse light calculation — likely confirming that `_direction` and the NodePath HPR are on different code paths.

---

## 8. Success Criteria

The directional lighting implementation is correct when all of the following are true:

1. **Formula hard-coded:** `sun_position_manager.py` uses Formula B with no toggle, no formula dispatch block, no `_light_formula` attribute, no `Shift+F9` binding.

2. **All cardinal positions correct:** Planet shows correct illumination at SOUTH, WEST, NORTH, EAST — lit hemisphere always faces the sun visual.

3. **Elevation correct:** Sun above/below the ecliptic plane illuminates the expected pole.

4. **Debug angle check reads ~0:** With the fixed angle check (`dot(fwd, sun_visual_dir)`), the OSD shows `ANGLE (fwd vs sun): ~0.0 deg — OK` at all test positions.

5. **Debug line legend correct:** GREEN line overlaps YELLOW (both point toward sun), RED opposes them.

6. **Cardinal cycling works:** `Ctrl+Left/Right` steps through all four cardinal positions when debug is active.

7. **Consistent across mesh types:** Ships (GLTF), stations (GLTF), moons, and planets all show the same illuminated hemisphere for a given sun direction. If GLTFs and procedural spheres disagree, the winding discrepancy is documented and accepted as a known limitation.

8. **No `setPos()` or `lookAt()` on DirectionalLight:** Verified by code search. The only transform calls on `sun_light_np` are `setHpr()` and `reparentTo()`.

9. **SCENE_LIGHTING.md accurate:** The formula section describes Formula B with the correct derivation (forward = sun_dir), not Formula C. Status field updated from "one cardinal" to "all four cardinals validated."

10. **Engine fix documented:** If Fix 2 (`set_direction_world()` or `set_sun_direction()` Python utility) is implemented, game code uses it instead of raw `atan2`, and the Pax3D engine changelog records the addition.

---

## Appendix A: Key File Locations

| File | Purpose |
|------|---------|
| `C:\python\pax3d\panda\src\pgraphnodes\directionalLight.h` | DirectionalLight class declaration — `set_direction()`, `get_direction()` |
| `C:\python\pax3d\panda\src\pgraphnodes\directionalLight.I` | Inline implementations — `_direction` CData field, default = forward |
| `C:\python\pax3d\panda\src\pgraphnodes\directionalLight.cxx` | `xform()`, `get_vector_to_light()`, serialisation |
| `C:\python\pax3d\panda\src\display\graphicsStateGuardian.cxx` | `fetch_specified_light()` (line 2172) — builds `LA_position` for GLSL shader |
| `C:\python\sfb2\modules\sun_position_manager.py` | Game: HPR computation from sun position, formula toggle |
| `C:\python\sfb2\modules\planetary_debug_tools.py` | Game: debug OSD, 3D lines, cardinal cycling |
| `C:\python\sfb2\modules\planet_factory.py` | Game: procedural sphere with specific triangle winding (lines 406-423) |
| `C:\python\sfb2\documents\3D_SPACEFLIGHT_MODULE\SCENE_LIGHTING.md` | Game: lighting documentation (currently correct re: Formula B, status partially wrong) |
| `C:\python\sfb2\debug_modules\lighting_debug.md` | Game: auto-generated debug dump |

---

## Appendix B: The Direction Pipeline

The complete chain from game code to shader for a DirectionalLight at `sun_light_np`:

```
1. Game calls: sun_light_np.setHpr(H, P, 0)
   - Sets NodePath transform: rotation matrix R from H, P, R=0
   - Does NOT touch DirectionalLight._direction CycleData

2. Engine builds light_mat:
   - light_mat = sun_light_np.get_net_transform()->get_mat()
             * scene_setup->get_world_transform()->get_mat()
   - This is the full NodePath rotation matrix (translation is present but
     irrelevant for LVector3 transformation)

3. Engine calls fetch_specified_light():
   - dir = -(light->get_direction() * light_mat)
   - get_direction() returns _direction = LVector3::forward() = (0, 1, 0)
   - (0, 1, 0) * light_mat = the rotated forward vector = sun_dir
     (because light_mat applies the HPR rotation)
   - dir = -sun_dir
   - LA_position = (dir.x, dir.y, dir.z, 0)
   - LA_position.xyz = -sun_dir = "toward planet" direction

4. simplepbr fragment shader:
   - l = normalize(p3d_LightSource[i].position.xyz) = normalize(-sun_dir)
   - n = vertex normal (either from vertex data or from normal map)
   - If planet winding is such that front-face normals point INWARD:
       n_effective = -n (after gl_FrontFacing flip, if present)
       NdotL = dot(-n, l) = dot(-n, -sun_dir) = dot(n, sun_dir)
       Lit when n points toward sun => lit hemisphere faces sun visual [CORRECT]
   - If planet winding is such that front-face normals point OUTWARD (standard):
       NdotL = dot(n, l) = dot(n, -sun_dir)
       Lit when n points away from sun => lit hemisphere faces away [WRONG]

5. Result: Formula B is correct IF the planet sphere has inward-facing normals
   (back-faces rendered) OR if simplepbr flips normals for back-faces,
   making the game's sphere effectively outward-facing after the flip,
   but with l = -sun_dir instead of the usual l = sun_dir convention.
```

This chain confirms that the discrepancy is in the vertex/winding/normal-direction path, not in the engine's light direction calculation itself. The engine correctly propagates the HPR through `light_mat` to produce `LA_position = -sun_dir`. The mystery is in step 4.
