"""pax3d_render — the unified Pax3D rendering pipeline (Phase R1).

Merges sfb2's graphics/pax_pbr and this repo's pax3d_simplepbr into one
first-party package. The game consumes this; rendering fixes land here and
only here.

Usage (drop-in for graphics.pax_pbr):

    import pax3d_render
    pipeline = pax3d_render.init(enable_shadows=False, msaa_samples=4)
    pipeline.update_sun(sun_dir_world, sun_color)

    # Auxiliary cameras (sky camera) — survives bloom/TAA rebuilds:
    reg = pipeline.register_scene_camera(sky_cam_np, sort=-100)

Color contract helpers (R1.3 — opt-in):

    pax3d_render.make_base_color_textures_srgb(model)

Recommended PRC (before ShowBase) — GLSL 330 core:

    pax3d_render.configure_prc()   # sets gl-version 3 2 if unset
"""
import panda3d.core as p3d

from .pipeline import (Pipeline, sh_from_cubemap, data_texture,
                       load_data_texture)
from .rigid_clips import (RigidClip, RigidClipPlayer, load_rigid_clips,
                          get_model_clips)
from .water import WaterParams, WaterSurface, water_sun

# Drop-in alias matching simplepbr's / pax_pbr's API
init = Pipeline

__version__ = '0.1.0'

__all__ = ['init', 'Pipeline', 'configure_prc',
           'make_base_color_textures_srgb', 'sh_from_cubemap',
           'data_texture', 'load_data_texture',
           'RigidClip', 'RigidClipPlayer', 'load_rigid_clips',
           'get_model_clips',
           'WaterParams', 'WaterSurface', 'water_sun']


def configure_prc():
    """Set the PRC baseline pax3d_render targets. Call BEFORE ShowBase().

    Currently: gl-version 3 2 (GLSL 330 core) if not already configured,
    and textures-power-2 none.
    """
    cvar = p3d.ConfigVariableInt('gl-version')
    if cvar.get_num_words() < 2:
        p3d.load_prc_file_data('pax3d_render', 'gl-version 3 2')
    p3d.load_prc_file_data('pax3d_render', 'textures-power-2 none')


def make_base_color_textures_srgb(nodepath):
    """Flag base-color (modulate-stage) textures as sRGB so the GPU decodes
    them to linear light on sampling — the input half of the R1 color
    contract (see PAXTEST_FINDINGS_SESSION_A.md Finding 1).

    Only modulate-mode stages are converted: normal maps, metal-rough maps,
    and other data textures must stay linear. Returns the number of
    textures converted.
    """
    converted = 0
    for np in nodepath.find_all_matches('**'):
        for stage in np.find_all_texture_stages():
            if stage.get_mode() != p3d.TextureStage.M_modulate:
                continue
            tex = np.get_texture(stage)
            if tex is None:
                continue
            fmt = tex.get_format()
            if fmt == p3d.Texture.F_rgb:
                tex.set_format(p3d.Texture.F_srgb)
                converted += 1
            elif fmt == p3d.Texture.F_rgba:
                tex.set_format(p3d.Texture.F_srgb_alpha)
                converted += 1
    return converted
