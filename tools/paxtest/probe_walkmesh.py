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

    print(f'\nprobe_walkmesh: {PASS} pass, {FAIL} fail')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
