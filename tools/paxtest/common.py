"""paxtest core: offscreen harness, pipeline adapters, readback, reporting.

Each test is a standalone script (run via run.py or directly):

    python tools/paxtest/test_gamma.py --pipeline pax_pbr

Pipelines:
    none            raw Panda3D, no post-processing (control)
    simplepbr       stock pip simplepbr (known-good reference, if installed)
    pax3d_simplepbr the fork in the Pax3D repo (unused by the game today)
    pax_pbr         the game's pipeline from C:/python/sfb2 (what ships today)

Baselines (R1.4, 2026-07-23 — the GLSL-120 path is deleted; the game
sets gl-version 3 2 in every entry point):
    game    (default) mimics sfb2 PRC: gl-version 3 2 (core profile)
    modern  legacy alias of game (kept so existing scripts/logs work)
    compat  DIAGNOSTIC ONLY: no gl-version (compat context; the
            pipeline still emits GLSL 330 and warns). Not part of the
            standard gate — for fixed-function-interplay archaeology
            (fact #17 class) only.
"""
import argparse
import json
import math
import os
import sys

import panda3d.core as p3d

HERE = os.path.dirname(os.path.abspath(__file__))
PAX3D_ROOT = os.path.dirname(os.path.dirname(HERE))
SFB2_ROOT = 'C:/python/sfb2'
OUTPUT_DIR = os.path.join(HERE, 'output')
GOLDEN_DIR = os.path.join(HERE, 'goldens')

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_SKIP = 77


# ----------------------------------------------------------------------
# Analytic tonemap transfer curves (must match the shaders)
# ----------------------------------------------------------------------

def _clamp01(v):
    return max(0.0, min(1.0, v))


def curve_linear(v):
    return _clamp01(v)


def curve_hejl_dawson(v):
    # Bakes in its own sRGB-ish gamma — no explicit pow afterwards.
    x = max(0.0, v - 0.004)
    return (x * (6.2 * x + 0.5)) / (x * (6.2 * x + 1.7) + 0.06)


def curve_aces(v):
    x = v
    r = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    return _clamp01(r) ** (1.0 / 2.2)


def curve_reinhard(v):
    return _clamp01(v / (1.0 + v)) ** (1.0 / 2.2)


def _uc2_partial(x):
    a, b, c, d, e, f = 0.15, 0.50, 0.10, 0.20, 0.02, 0.30
    return ((x * (a * x + c * b) + d * e) / (x * (a * x + b) + d * f)) - e / f


def curve_uncharted2(v):
    w = 11.2
    curr = _uc2_partial(2.0 * v)
    white = 1.0 / _uc2_partial(w)
    return _clamp01(curr * white) ** (1.0 / 2.2)


CURVES = {
    'linear': curve_linear,
    'hejl_dawson': curve_hejl_dawson,
    'stock': curve_hejl_dawson,   # stock simplepbr's fixed tonemap
    'aces': curve_aces,
    'reinhard': curve_reinhard,
    'uncharted2': curve_uncharted2,
}


def expected_output(operator, linear_value, exposure_ev=0.0):
    """What the final framebuffer value should be for a scene-linear input."""
    v = linear_value * (2.0 ** exposure_ev)
    return CURVES[operator](v)


# ----------------------------------------------------------------------
# Pipeline adapters
# ----------------------------------------------------------------------

class AdapterError(Exception):
    """Raised when a pipeline is unavailable in this environment."""


class NoneAdapter:
    """No post-processing: scene renders directly to the window."""
    name = 'none'
    supports_bloom = False
    supports_sun_uniforms = False
    supports_camera_registration = False
    consumes_directional_light = True   # fixed-function / auto-shader
    operators = ['linear']

    def create(self, base, msaa=0, exposure=0.0, tonemap='linear',
               bloom=None, sun_mode=None, shadows=False, log_depth=False,
               extra_kwargs=None):
        if sun_mode and sun_mode != 'uniforms':
            raise AdapterError('none pipeline has no sun_light_mode support')
        if shadows:
            raise AdapterError('none pipeline has no shadow support')
        if log_depth:
            raise AdapterError('none pipeline has no log-depth support')
        if extra_kwargs:
            raise AdapterError('none pipeline takes no pipeline kwargs')
        self.base = base

    def set_tonemap(self, op):
        pass

    def set_exposure(self, ev):
        pass

    def update_sun(self, toward_sun, color):
        return False


class _SimplepbrFamilyAdapter:
    """Shared logic for stock simplepbr and the pax3d_simplepbr fork."""
    module_name = None
    extra_path = None

    def _import(self):
        if self.extra_path and self.extra_path not in sys.path:
            sys.path.insert(0, self.extra_path)
        try:
            return __import__(self.module_name)
        except ImportError as exc:
            raise AdapterError(
                f'{self.module_name} not importable here: {exc}') from exc

    def create(self, base, msaa=0, exposure=0.0, tonemap='hejl_dawson',
               bloom=None, sun_mode=None, shadows=False, log_depth=False,
               extra_kwargs=None):
        if sun_mode and sun_mode != 'uniforms':
            raise AdapterError(
                f'{self.module_name} has no sun_light_mode support')
        if shadows:
            raise AdapterError(
                f'{self.module_name} shadow testing not wired in paxtest')
        if log_depth:
            raise AdapterError(
                f'{self.module_name} has no log-depth support')
        if extra_kwargs:
            raise AdapterError(
                f'{self.module_name} takes no extra pipeline kwargs')
        mod = self._import()
        self.base = base
        kwargs = dict(
            msaa_samples=msaa,
            enable_shadows=False,
            exposure=exposure,
        )
        if self.supports_bloom:
            kwargs['tonemap_operator'] = tonemap
            if bloom:
                kwargs.update(
                    enable_bloom=True,
                    bloom_strength=bloom.get('strength', 1.0),
                    bloom_intensity=bloom.get('intensity', 1.0),
                    bloom_levels=bloom.get('levels', 5),
                )
        self.pipeline = mod.init(**kwargs)

    def set_tonemap(self, op):
        if self.supports_bloom:
            self.pipeline.tonemap_operator = op

    def set_exposure(self, ev):
        self.pipeline.exposure = ev

    def update_sun(self, toward_sun, color):
        return False


class StockSimplepbrAdapter(_SimplepbrFamilyAdapter):
    name = 'simplepbr'
    module_name = 'simplepbr'
    extra_path = None
    supports_bloom = False
    supports_sun_uniforms = False
    supports_camera_registration = False
    consumes_directional_light = True
    operators = ['stock']


class Pax3dSimplepbrAdapter(_SimplepbrFamilyAdapter):
    name = 'pax3d_simplepbr'
    module_name = 'pax3d_simplepbr'
    extra_path = PAX3D_ROOT
    supports_bloom = True
    supports_sun_uniforms = False
    supports_camera_registration = False
    consumes_directional_light = True
    operators = ['aces', 'reinhard', 'uncharted2', 'hejl_dawson']

    def set_bloom_enabled(self, enabled):
        self.pipeline.enable_bloom = enabled


class PaxPbrAdapter:
    """The game's actual pipeline (sfb2/graphics/pax_pbr)."""
    name = 'pax_pbr'
    supports_bloom = True
    supports_sun_uniforms = True
    supports_camera_registration = False
    consumes_directional_light = False  # shader skips p3d_LightSource w==0
    operators = ['aces', 'reinhard', 'uncharted2', 'hejl_dawson']

    def _import_init(self):
        if not os.path.isdir(SFB2_ROOT):
            raise AdapterError(f'game repo not found at {SFB2_ROOT}')
        if SFB2_ROOT not in sys.path:
            sys.path.insert(0, SFB2_ROOT)
        try:
            from graphics.pax_pbr import init as pipeline_init
        except ImportError as exc:
            raise AdapterError(f'graphics.pax_pbr not importable: {exc}') from exc
        return pipeline_init

    supports_sun_modes = False
    supports_log_depth = False

    def create(self, base, msaa=0, exposure=0.0, tonemap='hejl_dawson',
               bloom=None, sun_mode=None, shadows=False, log_depth=False,
               extra_kwargs=None):
        pipeline_init = self._import_init()
        self.base = base
        kwargs = dict(
            msaa_samples=msaa,
            enable_shadows=shadows,
            exposure=exposure,
            tonemap_operator=tonemap,
        )
        if extra_kwargs:
            kwargs.update(extra_kwargs)
        if sun_mode and sun_mode != 'uniforms':
            if not self.supports_sun_modes:
                raise AdapterError(
                    f'{self.name} has no sun_light_mode support')
            kwargs['sun_light_mode'] = sun_mode
        if log_depth:
            if not self.supports_log_depth:
                raise AdapterError(
                    f'{self.name} has no log-depth support')
            kwargs['enable_log_depth'] = True
        if bloom:
            kwargs.update(
                enable_bloom=True,
                bloom_strength=bloom.get('strength', 1.0),
                bloom_intensity=bloom.get('intensity', 1.0),
                bloom_levels=bloom.get('levels', 5),
            )
        self.pipeline = pipeline_init(**kwargs)
        # The game's init manager seeds this before the first frame; the
        # pipeline's per-frame task keeps it updated afterwards.
        base.render.set_shader_input('camera_world_position',
                                     p3d.Vec3(0, 0, 0))

    def set_tonemap(self, op):
        self.pipeline.set_tonemap_operator(op)

    def set_exposure(self, ev):
        self.pipeline.set_exposure(ev)

    def set_bloom_enabled(self, enabled):
        self.pipeline.set_enable_bloom(enabled)

    def update_sun(self, toward_sun, color):
        self.pipeline.update_sun(p3d.Vec3(*toward_sun), p3d.Vec3(*color))
        return True


class Pax3dRenderAdapter(PaxPbrAdapter):
    """The unified pipeline in this repo (pax3d_render, Phase R1)."""
    name = 'pax3d_render'
    supports_camera_registration = True
    supports_sun_modes = True   # 'uniforms' | 'directional' (R2)
    supports_log_depth = True   # enable_log_depth (R4.1)

    def _import_init(self):
        if PAX3D_ROOT not in sys.path:
            sys.path.insert(0, PAX3D_ROOT)
        try:
            from pax3d_render import init as pipeline_init
        except ImportError as exc:
            raise AdapterError(f'pax3d_render not importable: {exc}') from exc
        return pipeline_init


ADAPTERS = {
    'none': NoneAdapter,
    'simplepbr': StockSimplepbrAdapter,
    'pax3d_simplepbr': Pax3dSimplepbrAdapter,
    'pax_pbr': PaxPbrAdapter,
    'pax3d_render': Pax3dRenderAdapter,
}


# ----------------------------------------------------------------------
# Harness
# ----------------------------------------------------------------------

def add_common_args(parser):
    parser.add_argument('--pipeline', default='none', choices=sorted(ADAPTERS))
    parser.add_argument('--baseline', default='game',
                        choices=['game', 'modern', 'compat'])
    parser.add_argument('--msaa', type=int, default=0)
    parser.add_argument('--win-size', default='512x512',
                        help='WxH, e.g. 512x512 or 960x540')
    parser.add_argument('--show', action='store_true',
                        help='open a real window instead of offscreen')
    parser.add_argument('--golden', action='store_true',
                        help='bless captures as golden references')
    parser.add_argument('--check-golden', action='store_true',
                        help='compare captures against goldens if present')
    return parser


def parse_win_size(spec):
    if 'x' in spec:
        w, h = spec.lower().split('x')
        return int(w), int(h)
    return int(spec), int(spec)


class Harness:
    def __init__(self, args, test_name):
        self.args = args
        self.test_name = test_name
        self.win_w, self.win_h = parse_win_size(args.win_size)
        self.report = TestReport(test_name, args)

        prc = [
            f'win-size {self.win_w} {self.win_h}',
            'window-title paxtest',
            'audio-library-name null',
            'sync-video 0',
            'show-frame-rate-meter 0',
            'textures-power-2 none',
            # sfb2/plan.py baseline
            'color-bits 8 8 8',
            'depth-bits 24',
            'multisamples 0',
        ]
        if not args.show:
            prc.append('window-type offscreen')
        if args.baseline != 'compat':
            prc.append('gl-version 3 2')
        for line in prc:
            p3d.load_prc_file_data('paxtest', line)

        from direct.showbase.ShowBase import ShowBase
        self.base = ShowBase()
        self.base.disable_mouse()
        self.base.set_background_color(0, 0, 0, 1)

        self.use_330 = args.baseline != 'compat'
        self.adapter = ADAPTERS[args.pipeline]()

    def init_pipeline(self, exposure=0.0, tonemap='hejl_dawson', bloom=None,
                      sun_mode=None, shadows=False, log_depth=False,
                      extra_pipeline_kwargs=None):
        """Create the pipeline; call before building the scene.

        extra_pipeline_kwargs: passed through to the pipeline constructor
        (pax_pbr-family adapters only) for test-specific init flags, e.g.
        {'enable_hardware_skinning': False}.
        """
        try:
            self.adapter.create(self.base, msaa=self.args.msaa,
                                exposure=exposure, tonemap=tonemap,
                                bloom=bloom, sun_mode=sun_mode,
                                shadows=shadows, log_depth=log_depth,
                                extra_kwargs=extra_pipeline_kwargs)
        except AdapterError as exc:
            self.report.skip(str(exc))

    def set_ortho(self, film_w=None, film_h=2.0):
        """Orthographic camera: film maps 1:1 to the window."""
        if film_w is None:
            film_w = film_h * self.win_w / self.win_h
        lens = p3d.OrthographicLens()
        lens.set_film_size(film_w, film_h)
        lens.set_near_far(-50, 50)
        self.base.cam.node().set_lens(lens)
        return film_w, film_h

    def step(self, n=1):
        for _ in range(n):
            self.base.task_mgr.step()

    def capture(self):
        img = p3d.PNMImage()
        if not self.base.win.get_screenshot(img):
            raise RuntimeError('screenshot failed')
        return img

    def save_capture(self, img, tag):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        name = f'{self.test_name}_{self.args.pipeline}_{tag}.png'
        path = os.path.join(OUTPUT_DIR, name)
        img.write(p3d.Filename.from_os_specific(path))
        if self.args.golden:
            os.makedirs(GOLDEN_DIR, exist_ok=True)
            img.write(p3d.Filename.from_os_specific(
                os.path.join(GOLDEN_DIR, name)))
        elif self.args.check_golden:
            gpath = os.path.join(GOLDEN_DIR, name)
            if os.path.exists(gpath):
                golden = p3d.PNMImage()
                golden.read(p3d.Filename.from_os_specific(gpath))
                rms = image_rms_diff(img, golden)
                self.report.check(f'golden:{tag}', rms < 0.03,
                                  f'rms={rms:.4f}')
        return path


# ----------------------------------------------------------------------
# Shadow depth-map readback (the openworld diff method)
# ----------------------------------------------------------------------

def find_light_depth_texture(light_np):
    """The depth texture of a shadow-casting light's buffer, or None.

    Walks the engine's outputs for the display region whose camera is the
    light node (the same association pipeline._get_all_casters uses)."""
    engine = p3d.GraphicsEngine.get_global_ptr()
    for win in engine.windows:
        for dr in win.active_display_regions:
            cam = dr.camera
            if cam.is_empty() or cam.node() != light_np.node():
                continue
            for i in range(win.count_textures()):
                plane = win.get_texture_plane(i)
                if plane in (p3d.GraphicsOutput.RTP_depth,
                             p3d.GraphicsOutput.RTP_depth_stencil):
                    return win.get_texture(i)
            if win.count_textures():
                return win.get_texture(0)
    return None


def read_depth_image(base, tex):
    """Extract a depth texture into a grayscale PNMImage (None on failure)."""
    if tex is None:
        return None
    try:
        if not base.graphics_engine.extract_texture_data(
                tex, base.win.get_gsg()):
            return None
        img = p3d.PNMImage()
        if not tex.store(img):
            return None
        return img
    except Exception:
        return None


def count_gray_diff(a, b, thresh=1.0 / 512, step=2):
    """Number of sampled texels whose gray value differs by > thresh."""
    if a is None or b is None:
        return -1
    if (a.get_x_size() != b.get_x_size()
            or a.get_y_size() != b.get_y_size()):
        return -1
    n = 0
    for y in range(0, a.get_y_size(), step):
        for x in range(0, a.get_x_size(), step):
            if abs(a.get_gray(x, y) - b.get_gray(x, y)) > thresh:
                n += 1
    return n * step * step  # scale sample count back to full-res texels


# ----------------------------------------------------------------------
# Pixel helpers (PNMImage: x right, y DOWN from top)
# ----------------------------------------------------------------------

def lum_at(img, x, y):
    x = max(0, min(img.get_x_size() - 1, int(x)))
    y = max(0, min(img.get_y_size() - 1, int(y)))
    c = img.get_xel(x, y)
    return (c[0] + c[1] + c[2]) / 3.0


def avg_lum(img, cx, cy, half=2):
    """Mean luminance of a small box (dodges dither noise)."""
    total, n = 0.0, 0
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            total += lum_at(img, cx + dx, cy + dy)
            n += 1
    return total / n


def mean_lum_disc(img, cx, cy, radius, half_x=None, half_y=None, step=2,
                  exclude_band=0):
    """Mean luminance inside a disc; optionally restricted to one half.

    half_x=+1/-1 keeps x > cx / x < cx; half_y likewise (y in PNM coords,
    +1 = lower half of the screen). exclude_band drops pixels within that
    distance of the dividing line.
    """
    total, n = 0.0, 0
    r2 = radius * radius
    for y in range(int(cy - radius), int(cy + radius) + 1, step):
        for x in range(int(cx - radius), int(cx + radius) + 1, step):
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy > r2:
                continue
            if half_x == 1 and dx < exclude_band:
                continue
            if half_x == -1 and dx > -exclude_band:
                continue
            if half_y == 1 and dy < exclude_band:
                continue
            if half_y == -1 and dy > -exclude_band:
                continue
            total += lum_at(img, x, y)
            n += 1
    return total / n if n else 0.0


def image_rms_diff(a, b, step=3):
    if (a.get_x_size() != b.get_x_size()
            or a.get_y_size() != b.get_y_size()):
        return 1.0
    total, n = 0.0, 0
    for y in range(0, a.get_y_size(), step):
        for x in range(0, a.get_x_size(), step):
            d = lum_at(a, x, y) - lum_at(b, x, y)
            total += d * d
            n += 1
    return math.sqrt(total / n) if n else 0.0


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------

class TestReport:
    def __init__(self, test_name, args):
        self.test_name = test_name
        self.args = args
        self.checks = []

    def check(self, name, passed, detail=''):
        self.checks.append({'name': name, 'status':
                            'PASS' if passed else 'FAIL', 'detail': detail})
        print(f'[{"PASS" if passed else "FAIL"}] {name}  {detail}')
        return passed

    def info(self, name, detail):
        self.checks.append({'name': name, 'status': 'INFO', 'detail': detail})
        print(f'[INFO] {name}  {detail}')

    def skip(self, reason):
        payload = {
            'test': self.test_name,
            'pipeline': self.args.pipeline,
            'baseline': self.args.baseline,
            'win_size': self.args.win_size,
            'status': 'SKIP',
            'reason': reason,
            'checks': [],
        }
        print(f'[SKIP] {self.test_name}/{self.args.pipeline}: {reason}')
        print('PAXTEST_JSON: ' + json.dumps(payload))
        sys.exit(EXIT_SKIP)

    def finish(self):
        failed = [c for c in self.checks if c['status'] == 'FAIL']
        payload = {
            'test': self.test_name,
            'pipeline': self.args.pipeline,
            'baseline': self.args.baseline,
            'win_size': self.args.win_size,
            'status': 'FAIL' if failed else 'PASS',
            'checks': self.checks,
        }
        print('PAXTEST_JSON: ' + json.dumps(payload))
        sys.exit(EXIT_FAIL if failed else EXIT_PASS)
