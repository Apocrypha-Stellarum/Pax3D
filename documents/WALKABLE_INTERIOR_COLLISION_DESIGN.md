# Walkable Interior Collision — Joint Design (Engine × Ship Dev)

**Status: AGREED 2026-07-18 (Session N).** Both sides' positions are
incorporated; every load-bearing engine mechanic below is MEASURED by
`tools/paxtest/probe_walkmesh.py` (7/7 on stock 1.10.16 AND Pax3D
1.11, identical numbers). Implementation is game-side; the engine
needs **no new code** — Panda's C++ collision system covers the whole
design. The unblocked feature: walking inside the Phobos Starhopper.

---

## 1. The contract (one sentence)

**The ship provides a hidden low-poly collision subtree; walk mode
queries it with a scene-local traverser when the player is inside the
ship's bounds.**

## 2. Division of labor

| Who | Does |
|---|---|
| Ship converter (Blender) | Emits a `phobos_collision` subtree next to the render meshes: `walk_*` groups (floors, ramp — low-poly quads) and `block_*` groups (walls, ceiling). Normals face into the walkable volume, same as render normals. Hidden (`hide()`) after load. |
| Game loader | Converts those groups' triangles → `CollisionNode`s of `CollisionPolygon`s with the reference recipe (`geom_np_to_collision` in `probe_walkmesh.py` — copy it). Masks: one CollideMask bit for WALK (floors/ramp), one for BLOCK (walls/ceiling). |
| Game walk mode | Inside the ship's bounds volume: ground = `max(segment_hit_z, heightfield_z)`, falling back to heightfield when the segment misses; a `CollisionHandlerPusher` sphere (from-mask BLOCK) is active only inside. Outside: pure heightfield, exactly as today. |
| Engine | Nothing new. `CollisionTraverser`/`CollisionSegment`/`CollisionHandlerPusher` are C++; at this scale (hundreds of polys, 1 segment + 1 sphere per frame) the cost is noise. |

**Masks note:** CollideMask (collision) and DrawMask (camera bits, e.g.
the pipeline's `shadow_caster_mask`) are SEPARATE systems — any
collide bits are free to use; there is no interaction with rendering.

## 3. Measured facts the design stands on (probe_walkmesh.py)

| # | Fact | Measurement |
|---|---|---|
| 1 | Render triangles convert 1:1 to CollisionPolygons via the recipe (nested transforms folded in) | 3 quads → 6 polys, valid |
| 2 | **Segment-vs-polygon intersection is DOUBLE-SIDED** — the "one-sided polygon" folklore does NOT apply to the ground query. Floor winding cannot break walking; the converter needs no floor fixups | flipped-normal floor still hit at z=2.0 |
| 3 | Multi-deck works with no special code: start the segment AT EYE HEIGHT and take the nearest sorted entry — you get the current deck, not the one below | stacked decks 2.0/0.5, eye 3.7 → hit 2.0 |
| 4 | The pusher stops a walker at a wall from the room side. Winding sets the PUSH DIRECTION: approached from behind, the sphere is pushed through to the room side — irrelevant in practice (the hull blocks outside approach), but keep wall normals facing inward | into wall at x=4.0, r=0.6 → x=3.400; from behind (4.55) → 3.400 |
| 5 | Sloped ramps read back exact analytic heights through the same query | mid-ramp → z=1.000000 vs analytic 1.0 |
| 6 | **Collision rides an animated part**: a CollisionPolygon under a node driven by `CharacterJoint.add_net_transform` (the expose-joint mechanism) follows a `control_joint`-posed joint exactly — the ramp/door pattern | panel at origin → no hit; joint moved to (20,0,1) → hit z=1.0 |
| 7 | **Same-frame procedural joint reads need `Character.force_update()`** — plain `update()` short-circuits when no animation has marked the bundle modified. In-game, PLAYING the door/ramp animation marks it and updates flow normally | update(): stale; force_update(): correct |

## 4. Ramp / door collision (the animated parts)

Two cases, depending on what panda3d-gltf makes of the FBX's discrete
animated nodes after conversion:

- **Plain animated PandaNodes** (no Character wrapping): parent each
  part's collision node directly under the part's node — it follows
  for free. Simplest; check the loaded GLB's graph first.
- **Character joints** (panda3d-gltf wraps animations in a Character):
  use the measured expose pattern —
  `joint = bundle.find_child(name); joint.add_net_transform(attach_node)`
  and hang the collision under `attach_node` (probe check 6). While a
  door animation is playing, updates flow normally; if you ever pose
  doors procedurally via `control_joint` and query the SAME frame,
  call `force_update()` (fact 7).

Either way: an open ramp is automatically walkable, a closed door
automatically blocks — no bookkeeping.

## 5. Walk-mode loop (ship dev's opening position, confirmed)

```python
if ship_bounds.contains(player_pos):          # cheap box/sphere test
    hit_z = ground_segment_query(eye_pos)     # WALK mask, nearest entry
    ground = max(hit_z, heightfield_z) if hit_z is not None else heightfield_z
    # pusher sphere (BLOCK mask) added to the traverser while inside
else:
    ground = heightfield_z                    # exactly today's path
```

The `max()` makes the ramp-foot handoff automatic: descending the ramp,
the walkmesh answer sinks toward the terrain and hands over smoothly —
no special transition zone required (the ship dev's zone idea also
works; `max()` is just less code). Step/eye heights are game tuning.

## 6. Open items (all game-side)

1. Converter emits the `phobos_collision` subtree (their tooling holds
   everything needed — confirmed).
2. Inspect the converted GLB's animated-part graph to pick the case in
   §4 (plain nodes vs Character joints).
3. Bounds volume authoring (a box around the hull + ramp apron).
4. Field feel: eye height, pusher radius, step tolerance.

Report field results back to the master plan §4.8 row when the first
walk-through happens.

## 7. Field triage — first walk-through fell through the floor (2026-07-18)

Engine-side measurement against the ACTUAL shipped GLB
(`sfb2/assets/models/phobos_starhopper.glb`), run through the §2
reference recipe:

- The converter's mesh is GOOD: top-level `COLL_floor` → **1366 valid
  CollisionPolygons**; ground queries hit correct deck heights
  (z ≈ −0.81 model space; ramp bay −1.34) across the cabin footprint.
- The GLB carries **0 CollisionNodes** — as designed: the LOADER must
  run the triangle→CollisionPolygon conversion. If walk mode queries
  before any conversion runs, there is nothing to hit → fall-through.
  This is suspect #1.
- **Naming drift**: the converter emitted `COLL_floor`, not the agreed
  `phobos_collision` subtree with `walk_*`/`block_*` groups. A loader
  searching for the agreed names finds nothing and silently degrades
  (suspect #2). Converge either way; the agreed split is still wanted
  once wall/ceiling blockers arrive (they are not in the GLB yet).
- **The ramp has no collision**: `COLL_floor` is static and the query
  MISSES at the far south end (y ≈ −11); the ramp lives in the
  separate animated `Phobos_Starhopper_Ramp.FBX` node. Until a ramp
  collision piece rides that node (§4, simple case — plain PandaNode,
  no joint machinery), boarding via the ramp falls through AT THE
  THRESHOLD. If the fall happens on entry, this is the spot.
- Animated parts confirmed PLAIN PandaNodes (0 Characters) — §4's
  simple case applies; ignore the joint/force_update machinery.
- Minor: 1366 polys is heavier than the low-poly intent — works, but
  a decimated collision floor would be kinder to per-frame queries.

Wiring checklist (in order): (1) conversion actually runs at load;
(2) name lookup matches what the converter emits; (3) `hide()` the
collision source, never `stash()` — stashed nodes are SKIPPED by the
collision traverser; (4) masks agree (`from` on the segment ==
`into` on the collision node); (5) world transform: after parenting
to the pad, `col_np.get_pos(render)` must be the pad, not the origin;
(6) eyeball with `col_np.show()` + `ctrav.show_collisions(render)`.

## 8. Walls — measured on the real asset (2026-07-18)

The GLB has NO blocker meshes yet, so as shipped nothing stops a
walker at a wall. The mechanism, tested by converting the RENDER
`Int_Walls` shell (27,161 tris → 27,151 CollisionPolygons, 0.1 s
one-time conversion; a handful of sliver polys auto-rejected):

- The pusher DOES stop the walker at the real cabin wall (x=2.0 →
  pushed to 1.662; from inside the wall shell 2.4 → 1.759).
- **But author low-poly `block_*` quads anyway**, for three measured
  reasons: (1) the sphere-vs-27k-poly traverse costs **2.3 ms/frame**
  — real frame budget, vs ~µs for a few dozen authored quads;
  (2) the dense mesh contains degenerate slivers (rejected, but
  noisy); (3) thin-wall escape: a discrete step fully PAST the shell
  (x=2.8) is no longer intersecting and is not pushed back — simple
  thick/inset blocker quads are robust against this; normal per-frame
  walk deltas against them cannot tunnel.
- Doorways: leave gaps in the blockers; the door meshes themselves
  (ArmoryDoor1/2, DoorRoot, CockpitDoor — all plain PandaNodes) get
  their own small collision pieces riding the animated nodes, so a
  closed door blocks and an open one doesn't, for free. Ceiling: one
  or two quads, BLOCK mask.
- Reminder: the pusher is NEW walk-mode code (their current loop is
  heightfield + eye height only) — §5 shows where it slots in.
