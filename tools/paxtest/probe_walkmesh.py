"""probe_walkmesh — measured engine facts for the walkable-interior
collision design (Session N; master plan §4.8, design doc
WALKABLE_INTERIOR_COLLISION_DESIGN.md).

Headless (no window, no ShowBase): Panda's collision system is pure
scene graph. Builds a synthetic ship interior — floor deck above a
conceptual heightfield, lower deck, wall, ramp — converts its RENDER
triangles to CollisionPolygons with the reference recipe below (the
one the ship converter/loader should copy), and measures:

  1. triangle -> CollisionPolygon conversion (counts, validity)
  2. segment-vs-polygon intersection is DOUBLE-SIDED (measured — the
     "one-sided polygon" folklore does NOT apply to the ground query;
     a flipped floor still reads back, so the converter needs no
     winding fixups for floors)
  3. multi-deck: a segment STARTED AT EYE HEIGHT with sorted entries
     returns the current deck, not the one below it
  4. the pusher sphere stops a walker at a wall from the room side;
     approached from BEHIND the wall it pushes THROUGH to the room
     side (winding sets the push direction — harmless for hulls,
     since outside approach is blocked by the exterior shell)
  5. a ramp reads back the analytic slope height
  6. collision attached to an EXPOSED, CONTROLLED Character joint
     follows the pose — the door/ramp-collision-rides-the-animated-
     part mechanism, proven on the same egg Character machinery
     panda3d-gltf produces. NOTE: same-frame procedural reads need
     Character.force_update() (update() short-circuits when no
     animation has marked the bundle modified — measured)
  7. (Session S, ship-dev pusher consult) a DIRECTLY-POSITIONED walker
     (game sets pos from its own sim state every frame) MUST read the
     pusher's corrected position back into that sim state after
     traverse. Without readback the sim keeps integrating into the
     wall while only the node is corrected; the moment the sim
     position passes wall + sphere radius the sphere stops
     intersecting and the walker ESCAPES through the wall — at the
     ship-dev numbers (r 0.35, 0.10 units/frame) that is a HELD KEY
     FOR ~7 FRAMES. With readback the walker pins stably at the wall
     face, no oscillation, and set_horizontal(True) leaves z alone.
  8. (Session S) splitting a big wall mesh into spatially-separated
     CollisionNode chunks is cheap insurance: the traverser culls
     whole into-nodes by bounds before testing solids, so per-frame
     cost tracks the CHUNK the walker is near, not the whole ship
     (measured speedup on a synthetic 3200-poly wall run: see the
     [info] ratio line; grows with mesh size)

Run:  <any python with panda3d> tools/paxtest/probe_walkmesh.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import scenes

WALK_MASK = p3d.BitMask32.bit(5)    # floors + ramps: segment queries
BLOCK_MASK = p3d.BitMask32.bit(6)   # walls + ceilings: pusher sphere

PASS = FAIL = 0


def check(name, ok, detail):
    global PASS, FAIL
    print(f'[{"PASS" if ok else "FAIL"}] {name}  {detail}')
    PASS, FAIL = PASS + (1 if ok else 0), FAIL + (0 if ok else 1)


# ----------------------------------------------------------------------
# The reference recipe (copy into the ship converter/loader)
# ----------------------------------------------------------------------

def geom_np_to_collision(geom_np, into_mask, name=None):
    """All triangles under `geom_np` -> one CollisionNode of
    CollisionPolygons, attached NEXT TO the source node (same parent,
    same local space) and hidden from every camera by nature.

    Winding: polygon normals follow the render winding. MEASURED
    (checks 2/4): segment queries intersect from BOTH sides, so floor
    winding cannot break the ground query; winding DOES set the
    pusher's push direction, so walls should keep normals facing into
    the room (a correctly-normaled render mesh does, with no fixups).
    """
    cnode = p3d.CollisionNode(name or geom_np.get_name() + '_col')
    cnode.set_from_collide_mask(p3d.BitMask32.all_off())
    cnode.set_into_collide_mask(into_mask)
    for np in geom_np.find_all_matches('**/+GeomNode'):
        rel_mat = np.get_mat(geom_np)
        for geom in np.node().get_geoms():
            geom = geom.decompose()
            vdata = geom.get_vertex_data()
            reader = p3d.GeomVertexReader(vdata, 'vertex')
            for prim in geom.get_primitives():
                for t in range(prim.get_num_primitives()):
                    s = prim.get_primitive_start(t)
                    pts = []
                    for k in range(3):
                        reader.set_row(prim.get_vertex(s + k))
                        pts.append(rel_mat.xform_point(
                            p3d.Point3(reader.get_data3())))
                    poly = p3d.CollisionPolygon(pts[0], pts[1], pts[2])
                    if poly.is_valid():
                        cnode.add_solid(poly)
    col_np = geom_np.get_parent().attach_new_node(cnode)
    col_np.set_transform(geom_np.get_transform())
    return col_np


# ----------------------------------------------------------------------
# Synthetic interior geometry (render meshes; world units)
# ----------------------------------------------------------------------

def make_quad(parent, name, p0, p1, p2, p3_):
    """Two-triangle quad, wound p0->p1->p2 / p0->p2->p3 (CCW seen from
    the normal side)."""
    fmt = p3d.GeomVertexFormat.get_v3()
    vdata = p3d.GeomVertexData(name, fmt, p3d.Geom.UH_static)
    w = p3d.GeomVertexWriter(vdata, 'vertex')
    for p in (p0, p1, p2, p3_):
        w.add_data3(*p)
    tris = p3d.GeomTriangles(p3d.Geom.UH_static)
    tris.add_vertices(0, 1, 2)
    tris.close_primitive()
    tris.add_vertices(0, 2, 3)
    tris.close_primitive()
    geom = p3d.Geom(vdata)
    geom.add_primitive(tris)
    node = p3d.GeomNode(name)
    node.add_geom(geom)
    return parent.attach_new_node(node)


def ground_hit(ctrav, queue, root, seg_np, seg, x, y, eye_z, depth=6.0):
    """The walk-mode ground query: segment from eye straight down,
    nearest entry wins. Returns surface z or None."""
    seg.set_point_a(x, y, eye_z)
    seg.set_point_b(x, y, eye_z - depth)
    queue.clear_entries()
    ctrav.traverse(root)
    if not queue.get_num_entries():
        return None
    queue.sort_entries()
    return queue.get_entry(0).get_surface_point(root).z


def main():
    root = p3d.NodePath('world')
    ship = root.attach_new_node('ship')

    # Render meshes (normals face into the walkable volume)
    floors = ship.attach_new_node('floors')
    make_quad(floors, 'deck', (-4, -4, 2), (4, -4, 2),
              (4, 4, 2), (-4, 4, 2))                        # normal +Z
    make_quad(floors, 'lower_deck', (-4, -4, 0.5), (4, -4, 0.5),
              (4, 4, 0.5), (-4, 4, 0.5))                    # normal +Z
    make_quad(floors, 'ramp', (-8, -1, 0), (-4, -1, 2),
              (-4, 1, 2), (-8, 1, 0))                       # sloped, up
    walls = ship.attach_new_node('walls')
    make_quad(walls, 'wall_east', (4, -4, 2), (4, -4, 4.5),
              (4, 4, 4.5), (4, 4, 2))                       # normal -X (inward)
    bad = ship.attach_new_node('bad_winding')
    make_quad(bad, 'floor_flipped', (10, -1, 2), (10, 1, 2),
              (12, 1, 2), (12, -1, 2))                      # normal -Z (WRONG)

    # Convert render triangles -> collision
    col_floors = geom_np_to_collision(floors, WALK_MASK)
    col_walls = geom_np_to_collision(walls, BLOCK_MASK)
    col_bad = geom_np_to_collision(bad, WALK_MASK)

    n_polys = col_floors.node().get_num_solids()
    check('triangles_become_polys',
          n_polys == 6 and col_walls.node().get_num_solids() == 2,
          f'floors: 3 quads -> {n_polys} CollisionPolygons, '
          f'wall: {col_walls.node().get_num_solids()}')

    # Walk-mode ground query rig
    ctrav = p3d.CollisionTraverser()
    queue = p3d.CollisionHandlerQueue()
    seg = p3d.CollisionSegment(0, 0, 0, 0, 0, -1)
    seg_node = p3d.CollisionNode('walk_probe')
    seg_node.add_solid(seg)
    seg_node.set_from_collide_mask(WALK_MASK)
    seg_node.set_into_collide_mask(p3d.BitMask32.all_off())
    seg_np = root.attach_new_node(seg_node)
    ctrav.add_collider(seg_np, queue)

    # 2. Ground query works; segment-vs-polygon is DOUBLE-SIDED
    z_above = ground_hit(ctrav, queue, root, seg_np, seg, 0, 0, 3.7)
    check('floor_ground_query',
          z_above is not None and abs(z_above - 2.0) < 1e-3,
          f'from eye 3.7: hit z={z_above} (deck at 2.0)')
    z_bad = ground_hit(ctrav, queue, root, seg_np, seg, 11, 0, 3.7)
    check('segment_hits_both_sides',
          z_bad is not None and abs(z_bad - 2.0) < 1e-3,
          f'flipped-normal floor STILL hit at z={z_bad}: segment '
          f'intersection ignores facing — floor winding cannot break '
          f'the ground query (folklore disproven, converter needs no '
          f'floor fixups)')

    # 3. Multi-deck: eye-height start + nearest entry = current deck
    z_deck = ground_hit(ctrav, queue, root, seg_np, seg, 1, 1, 3.7)
    check('nearest_hit_is_current_deck',
          z_deck is not None and abs(z_deck - 2.0) < 1e-4,
          f'two stacked decks (2.0 / 0.5): eye 3.7 gets {z_deck} '
          f'(sorted nearest, not the deck below)')

    # 4. Pusher stops the walker at the wall
    player = root.attach_new_node('player')
    player.set_pos(3.0, 0, 2.9)
    sph_node = p3d.CollisionNode('player_body')
    sph_node.add_solid(p3d.CollisionSphere(0, 0, 0, 0.6))
    sph_node.set_from_collide_mask(BLOCK_MASK)
    sph_node.set_into_collide_mask(p3d.BitMask32.all_off())
    sph_np = player.attach_new_node(sph_node)
    pusher = p3d.CollisionHandlerPusher()
    pusher.add_collider(sph_np, player)
    ctrav.add_collider(sph_np, pusher)
    player.set_pos(4.2, 0, 2.9)          # try to walk through the wall
    ctrav.traverse(root)
    px = player.get_x()
    check('pusher_blocks_wall', px < 3.45,
          f'walker pushed to x={px:.3f} (wall at 4.0, radius 0.6 -> '
          f'expected ~3.4)')
    player.set_pos(4.55, 0, 2.9)         # approach from BEHIND the wall
    ctrav.traverse(root)
    print(f'[info] from behind the wall (x=4.55): pushed to '
          f'x={player.get_x():.3f} — winding sets the push direction '
          f'(inward); irrelevant in practice, the hull blocks outside '
          f'approach')
    ctrav.remove_collider(sph_np)

    # 5. Ramp reads the analytic slope
    z_ramp = ground_hit(ctrav, queue, root, seg_np, seg, -6, 0, 3.0)
    check('ramp_walkable',
          z_ramp is not None and abs(z_ramp - 1.0) < 1e-4,
          f'mid-ramp (x=-6, slope 0..2 over -8..-4): hit z={z_ramp} '
          f'vs analytic 1.0')
    z_off = ground_hit(ctrav, queue, root, seg_np, seg, -9, 0, 3.0)
    print(f'[info] handoff rule: off-ramp (x=-9) walkmesh hit={z_off} '
          f'-> heightfield; inside: ground = max(walkmesh, heightfield)')

    # 6. Collision follows an exposed + controlled Character joint
    sheet = scenes.make_skinned_sheet(half=1.0, height=2.0)
    sheet.reparent_to(root)
    char_np = sheet.find('**/+Character')
    bundle = char_np.node().get_bundle(0)
    ctrl = char_np.attach_new_node('door_ctrl')
    controlled = bool(bundle.control_joint('joint_tip', ctrl.node()))
    joint = bundle.find_child('joint_tip')
    hatch = char_np.attach_new_node('door_expose')
    joint.add_net_transform(hatch.node())
    door_col = p3d.CollisionNode('door_col')
    door_col.add_solid(p3d.CollisionPolygon(
        p3d.Point3(-0.5, -0.5, 0), p3d.Point3(0.5, -0.5, 0),
        p3d.Point3(0.5, 0.5, 0), p3d.Point3(-0.5, 0.5, 0)))
    door_col.set_from_collide_mask(p3d.BitMask32.all_off())
    door_col.set_into_collide_mask(WALK_MASK)
    hatch.attach_new_node(door_col)

    char_np.node().force_update()
    z_closed = ground_hit(ctrav, queue, root, seg_np, seg, 20, 0, 5.0)
    ctrl.set_pos(20, 0, 1.0)             # "open the ramp": drive the joint
    # update() short-circuits when no anim marked the bundle modified;
    # force_update() is the reliable same-frame push (measured). In-game,
    # PLAYING the door animation marks the bundle and update flows.
    char_np.node().force_update()
    z_open = ground_hit(ctrav, queue, root, seg_np, seg, 20, 0, 5.0)
    check('collision_follows_joint',
          controlled and z_closed is None and z_open is not None
          and abs(z_open - 1.0) < 1e-4,
          f'joint-mounted panel: before move hit={z_closed}, after '
          f'control_joint move to (20,0,1) hit z={z_open} '
          f'(expose_joint/add_net_transform keeps collision in sync)')

    # 7. Direct-positioning + pusher: the readback contract (Session S,
    #    ship-dev consult — their walk mode sets the camera pos from sim
    #    state each frame; sphere r 0.35 chest height, ~0.10 units/frame)
    walker = root.attach_new_node('walker')
    wsph_node = p3d.CollisionNode('walker_body')
    wsph_node.add_solid(p3d.CollisionSphere(0, 0, 0, 0.35))
    wsph_node.set_from_collide_mask(BLOCK_MASK)
    wsph_node.set_into_collide_mask(p3d.BitMask32.all_off())
    wsph_np = walker.attach_new_node(wsph_node)
    wpusher = p3d.CollisionHandlerPusher()
    wpusher.set_horizontal(True)
    wpusher.add_collider(wsph_np, walker)
    ctrav.add_collider(wsph_np, wpusher)

    # Variant A — NO readback: sim state is authoritative, pusher
    # corrections are overwritten next frame. Hold the key toward the
    # wall (at x=4.0) and watch for escape.
    sim_x, escape_frame = 3.0, None
    for frame in range(1, 41):
        sim_x += 0.10
        walker.set_pos(sim_x, 0, 2.9)
        ctrav.traverse(root)
        if walker.get_x() > 4.35:        # beyond wall + radius: free
            escape_frame = frame
            break
    frames_expected = int(round((4.35 - 3.0) / 0.10))
    frames_past_contact = int(round((4.35 - (4.0 - 0.35)) / 0.10))
    check('pusher_no_readback_escapes',
          escape_frame is not None,
          f'sim keeps integrating into the wall: walker ESCAPED through '
          f'it on frame {escape_frame} (~{frames_expected} expected: '
          f'the walk-up plus {frames_past_contact} held frames past '
          f'first contact at r 0.35, 0.10/frame) — direct positioning '
          f'without readback walks through any wall on a held key')

    # Variant B — WITH readback: after traverse, the pusher-corrected
    # node position becomes the sim state. Same held key, 40 frames.
    sim_x, zs, xs = 3.0, [], []
    walker.set_pos(sim_x, 0, 2.9)
    for frame in range(40):
        sim_x += 0.10
        walker.set_pos(sim_x, 0, 2.9)
        ctrav.traverse(root)
        sim_x = walker.get_x()           # THE contract
        xs.append(sim_x)
        zs.append(walker.get_z())
    tail = xs[10:]
    check('pusher_readback_pins_stable',
          max(tail) < 4.0 and (max(tail) - min(tail)) < 1e-3
          and all(abs(z - 2.9) < 1e-6 for z in zs),
          f'sim_x = walker.get_x() after traverse: pinned at '
          f'x={tail[-1]:.3f} (wall 4.0 - r 0.35 - margin), spread '
          f'{max(tail) - min(tail):.2e} over 30 held frames, z untouched '
          f'(set_horizontal) — read the correction back and the wall '
          f'is solid')
    ctrav.remove_collider(wsph_np)

    # 8. Chunked wall nodes vs one monolithic node (Session S consult:
    #    loader spatial chunks / converter block_room_* groups). A long
    #    wall of 1600 quads (3200 polys) as ONE CollisionNode vs 8
    #    spatially-separated chunk nodes; walker parked near one end.
    import time as _time
    arena = root.attach_new_node('arena')
    n_seg, seg_w = 1600, 0.5

    def wall_solids(lo, hi):
        node = p3d.CollisionNode(f'chunk_{lo}')
        node.set_from_collide_mask(p3d.BitMask32.all_off())
        node.set_into_collide_mask(BLOCK_MASK)
        for i in range(lo, hi):
            x0, x1 = 100 + i * seg_w, 100 + (i + 1) * seg_w
            node.add_solid(p3d.CollisionPolygon(
                p3d.Point3(x0, 5, 0), p3d.Point3(x1, 5, 0),
                p3d.Point3(x1, 5, 3), p3d.Point3(x0, 5, 3)))
            node.add_solid(p3d.CollisionPolygon(
                p3d.Point3(x0, 5, 3), p3d.Point3(x1, 5, 3),
                p3d.Point3(x1, 5, 6), p3d.Point3(x0, 5, 6)))
        return node

    def time_traverse(n_frames=100):
        t0 = _time.perf_counter()
        for _ in range(n_frames):
            ctrav.traverse(root)
        return (_time.perf_counter() - t0) / n_frames * 1000.0

    probe_np = arena.attach_new_node('perf_walker')
    probe_np.set_pos(100 + seg_w, 4.5, 1.5)   # near the wall's west end
    psph = p3d.CollisionNode('perf_body')
    psph.add_solid(p3d.CollisionSphere(0, 0, 0, 0.35))
    psph.set_from_collide_mask(BLOCK_MASK)
    psph.set_into_collide_mask(p3d.BitMask32.all_off())
    psph_np = probe_np.attach_new_node(psph)
    ppusher = p3d.CollisionHandlerPusher()
    ppusher.add_collider(psph_np, probe_np)
    ctrav.add_collider(psph_np, ppusher)

    mono_np = arena.attach_new_node(wall_solids(0, n_seg))
    ms_mono = time_traverse()
    mono_np.remove_node()
    chunk_nps = [arena.attach_new_node(
        wall_solids(k * (n_seg // 8), (k + 1) * (n_seg // 8)))
        for k in range(8)]
    ms_chunk = time_traverse()
    for np_ in chunk_nps:
        np_.remove_node()
    ctrav.remove_collider(psph_np)
    check('chunked_walls_cull', ms_chunk < ms_mono,
          f'3200-poly wall, walker near one end: one node '
          f'{ms_mono:.3f} ms/traverse vs 8 chunks {ms_chunk:.3f} '
          f'ms/traverse ({ms_mono / max(ms_chunk, 1e-9):.1f}x) — the '
          f'traverser culls whole into-nodes by bounds, so chunking '
          f'bounds per-frame cost by proximity, not ship size')

    print(f'\nprobe_walkmesh: {PASS} pass, {FAIL} fail')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
