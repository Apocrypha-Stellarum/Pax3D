"""probe_morph — measured facts: vertex morphs (egg <Dxyz> sliders)
under the pax3d_render skinning paths (Session S, NPC-character scoping).

NOT a gate test. The character pipeline ships rigs with NO morph
targets because the pax shaders have no slider path — but what Panda
itself does with slider-animated vertices under hardware skinning was
never measured. This probe pins it:

  1. does the egg loader create a CharacterSlider for a <Dxyz> morph?
  2. does the CPU animation path (animate_vertices) apply the morph?
  3. does the RENDERED image follow the slider with hardware skinning
     ON (the pipeline default)?
  4. does it follow with the per-node CPU opt-out
     (set_hardware_skinning(np, False))?

Geometry: a 2-joint soft-skinned quad sheet (same class as
scenes.make_skinned_sheet) whose +x-edge vertices carry a
<Dxyz> morph0 { 1 0 0 } — slider 1.0 stretches the sheet's footprint
from x=+1 to x=+2, observed top-down with an ortho camera at a sample
point beyond the bind-pose edge.

Run:  <python> tools/paxtest/probe_morph.py --pipeline pax3d_render
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


EGG_TEXT = """<CoordinateSystem> { Z-Up }
<Group> morph_sheet {
  <Dart> { default }
  <VertexPool> vp {
    <Vertex> 0 { -1 -1 4 <Normal> { 0 0 1 } }
    <Vertex> 1 { 1 -1 4 <Normal> { 0 0 1 } <Dxyz> morph0 { 1 0 0 } }
    <Vertex> 2 { 1 1 4 <Normal> { 0 0 1 } <Dxyz> morph0 { 1 0 0 } }
    <Vertex> 3 { -1 1 4 <Normal> { 0 0 1 } }
  }
  <Joint> joint_root {
    <VertexRef> { 0 3 <Scalar> membership { 1.0 } <Ref> { vp } }
    <VertexRef> { 1 2 <Scalar> membership { 0.5 } <Ref> { vp } }
    <Joint> joint_tip {
      <VertexRef> { 1 2 <Scalar> membership { 0.5 } <Ref> { vp } }
    }
  }
  <Polygon> { <VertexRef> { 0 1 2 3 <Ref> { vp } } }
}
"""

PASS_ = []


def fact(name, value, detail):
    PASS_.append(name)
    print(f'[fact] {name} = {value}   {detail}')


def max_animated_x(np):
    """Max x over the CPU-animated (AT_panda truth) vertex data."""
    best = -1e9
    for geom_np in np.find_all_matches('**/+GeomNode'):
        for geom in geom_np.node().get_geoms():
            vdata = geom.get_vertex_data().animate_vertices(
                True, p3d.Thread.get_current_thread())
            reader = p3d.GeomVertexReader(vdata, 'vertex')
            while not reader.is_at_end():
                best = max(best, reader.get_data3()[0])
    return best


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'probe_morph')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None:
        h.report.skip('probe needs a pax_pbr-family pipeline')
    base = h.base

    alight = p3d.AmbientLight('probe_ambient')
    alight.set_color(p3d.LColor(0.6, 0.6, 0.6, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, 0, 1), (0, 0, 0))

    from panda3d import egg as pegg
    data = pegg.EggData()
    ss = p3d.StringStream(EGG_TEXT.encode())
    if not data.read(ss):
        print('[fact] egg_text_parses = False   (egg text rejected)')
        sys.exit(1)
    node = pegg.load_egg_data(data)
    sheet = p3d.NodePath(node)
    sheet.set_two_sided(True)
    scenes.apply_flat_pbr_surface(sheet, rgb=(1, 1, 1))
    sheet.reparent_to(base.render)

    char_np = sheet.find('**/+Character')
    fact('character_created', not char_np.is_empty(),
         'egg with <Dxyz> + joints loads as a Character')
    bundle = char_np.node().get_bundle(0)
    slider = bundle.find_child('morph0')
    fact('slider_created', slider is not None,
         'bundle.find_child("morph0") — the egg loader made a '
         'CharacterSlider for the <Dxyz> target')

    # Top-down ortho: the sheet occupies x,y in [-1,1] at slider 0 and
    # stretches to x=+2 at slider 1. Sample beyond the bind edge.
    h.set_ortho(film_h=6.0)
    base.camera.set_pos(0, 0, 20)
    base.camera.set_hpr(0, -90, 0)
    scale = h.win_h / 6.0
    px = h.win_w // 2 + int(round(1.5 * scale))
    py = h.win_h // 2

    def set_slider(v):
        if slider is not None:
            slider.apply_freeze_scalar(v)
        char_np.node().force_update()

    def lum():
        h.step(4)
        return common.avg_lum(h.capture(), px, py, half=3)

    # CPU truth first
    set_slider(0.0)
    x0 = max_animated_x(sheet)
    set_slider(1.0)
    x1 = max_animated_x(sheet)
    fact('cpu_path_applies_morph', abs(x1 - 2.0) < 1e-3 and
         abs(x0 - 1.0) < 1e-3,
         f'animate_vertices max x: slider 0 -> {x0:.3f}, '
         f'slider 1 -> {x1:.3f} (expected 1.0 / 2.0)')

    # Rendered, hardware skinning ON (pipeline default)
    set_slider(0.0)
    lum_hw0 = lum()
    set_slider(1.0)
    lum_hw1 = lum()
    fact('render_follows_slider_hw', lum_hw1 > lum_hw0 + 0.1,
         f'top-down lum at x=+1.5: slider 0 -> {lum_hw0:.3f}, '
         f'slider 1 -> {lum_hw1:.3f} (hardware-skinning path)')

    # Rendered, per-node CPU opt-out
    if hasattr(pipeline, 'set_hardware_skinning'):
        pipeline.set_hardware_skinning(sheet, False)
        set_slider(0.0)
        lum_cpu0 = lum()
        set_slider(1.0)
        lum_cpu1 = lum()
        fact('render_follows_slider_cpu_optout',
             lum_cpu1 > lum_cpu0 + 0.1,
             f'same points on the per-node CPU path: {lum_cpu0:.3f} -> '
             f'{lum_cpu1:.3f}')
        pipeline.clear_hardware_skinning(sheet)

    print(f'\nprobe_morph: {len(PASS_)} facts measured')


if __name__ == '__main__':
    main()
