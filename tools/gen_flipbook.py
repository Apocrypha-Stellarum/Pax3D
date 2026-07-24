"""gen_flipbook.py — video/frames -> flipbook atlas for pax3d_render
screens (ER-005, Session V) and effect sprites (Session AD).

The Pax3D wheel builds with --no-ffmpeg: MP4 decode DOES NOT EXIST
engine-side, so looping screen videos (the Unity packs ship 6 mp4 UI
loops) are converted at intake into a texture atlas played back by
pipeline.play_flipbook() — VRAM-resident, zero per-frame uploads,
works identically on stock and Pax3D engines.

Alpha (Session AD, explosion footage): sources with an alpha channel
(ProRes 4444 MOVs, RGBA frame sequences) produce an RGBA atlas —
alpha survives extraction, scaling, and assembly. The CGVision
air/space explosion pack measured PREMULTIPLIED (RGB <= alpha up to a
deliberate additive glow tail), which is exactly what
pipeline.spawn_effect() composites; bake as-is, no unpremultiply.
Alpha-free sources produce the same 3-channel atlas as before,
byte-identical (paxtest test_effects guards both).

    # from a video (needs the ffmpeg CLI on PATH — present on the dev
    # machine; any format ffmpeg reads):
    python tools/gen_flipbook.py ui_loop.mp4 --fps 10 --cell 256x144

    # explosion footage: decimate 25 fps -> 12.5 and downscale
    python tools/gen_flipbook.py 5_1.mov --fps 12.5 --cell 256x188

    # from an already-exported frame directory (alphabetical order):
    python tools/gen_flipbook.py frames_dir/ --fps 10

Output: <name>_flipbook.png + <name>_flipbook.json sidecar
({cols, rows, frames, fps, cell_w, cell_h, alpha}) and the exact
set_screen/play_flipbook (or spawn_effect, for alpha atlases) call to
paste game-side.

Atlas convention (must match Pipeline._flipbook_transform): frames
row-major from the TOP-LEFT, cols x rows grid. Keep atlases <= 8192 px
(GPU limit; 4096 to be safe on older cards) — the tool warns. Sizing
math: a 10 s loop @ 10 fps @ 256x144 cells = 100 frames = 10x10 grid =
2560x1440 atlas. Loops read best when fps divides the source duration
evenly (seamless wrap).
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

from panda3d.core import PNMImage, Filename


def video_has_alpha(video):
    """True when the video's pixel format carries an alpha channel
    (ffprobe pix_fmt contains 'a': yuva444p12le, rgba, ...). Falls back
    to False when ffprobe is unavailable or the probe fails."""
    ffprobe = shutil.which('ffprobe')
    if ffprobe is None:
        return False
    try:
        out = subprocess.run(
            [ffprobe, '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=pix_fmt',
             '-of', 'default=noprint_wrappers=1:nokey=1', video],
            capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return False
    return (out.startswith(('yuva', 'gbrap', 'ya'))
            or out.split('64')[0].split('le')[0].split('be')[0]
            in ('rgba', 'bgra', 'argb', 'abgr'))


def extract_video_frames(video, workdir, fps, cell, max_frames):
    if shutil.which('ffmpeg') is None:
        sys.exit('ffmpeg CLI not found on PATH — extract frames yourself '
                 'and pass the directory instead')
    vf = [f'fps={fps}']
    if cell:
        vf.append(f'scale={cell[0]}:{cell[1]}')
    cmd = ['ffmpeg', '-loglevel', 'error', '-i', video,
           '-vf', ','.join(vf)]
    if video_has_alpha(video):
        # Alpha-carrying sources (ProRes 4444 explosion footage): pin
        # rgba so the PNG encoder cannot pick an opaque format.
        cmd += ['-pix_fmt', 'rgba']
    if max_frames:
        cmd += ['-frames:v', str(max_frames)]
    cmd.append(os.path.join(workdir, 'f%05d.png'))
    subprocess.run(cmd, check=True)
    return sorted(os.path.join(workdir, f) for f in os.listdir(workdir)
                  if f.endswith('.png'))


def load_frames(paths, cell):
    frames = []
    for p in paths:
        img = PNMImage()
        if not img.read(Filename.from_os_specific(p)):
            sys.exit(f'cannot read frame {p}')
        if cell and (img.get_x_size(), img.get_y_size()) != cell:
            scaled = PNMImage(cell[0], cell[1], img.get_num_channels(),
                              img.get_maxval())
            scaled.quick_filter_from(img)
            img = scaled
        frames.append(img)
    # Mixed sources: if ANY frame carries alpha the atlas does, and
    # alpha-free frames read as fully opaque.
    if any(f.has_alpha() for f in frames):
        for f in frames:
            if not f.has_alpha():
                f.add_alpha()
                f.alpha_fill(1.0)
    return frames


def assemble_atlas(frames, cols=0):
    """Tile `frames` (PNMImages, uniform size) into a contact-sheet
    atlas: row-major from the TOP-LEFT, near-square grid unless `cols`
    is forced. RGBA when the frames carry alpha (effect sprites),
    plain RGB otherwise (screens — byte-identical to the pre-alpha
    tool). Returns (atlas, cols, rows)."""
    n = len(frames)
    cw, ch = frames[0].get_x_size(), frames[0].get_y_size()
    cols = cols or max(1, math.ceil(math.sqrt(n * ch / cw)))
    rows = math.ceil(n / cols)
    has_alpha = frames[0].has_alpha()
    atlas = PNMImage(cols * cw, rows * ch, 4 if has_alpha else 3)
    atlas.fill(0, 0, 0)
    if has_alpha:
        # Unused trailing cells stay fully transparent — they never
        # render even if a bad num_frames walks into them.
        atlas.alpha_fill(0.0)
    for i, img in enumerate(frames):
        col, row = i % cols, i // cols       # row-major from TOP-LEFT
        atlas.copy_sub_image(img, col * cw, row * ch)
    return atlas, cols, rows


def main():
    ap = argparse.ArgumentParser(
        description='video/frames -> flipbook atlas for '
                    'pipeline.play_flipbook()')
    ap.add_argument('source', help='video file (ffmpeg CLI) or frame dir')
    ap.add_argument('--fps', type=float, default=10.0,
                    help='sampled/playback frames per second (default 10)')
    ap.add_argument('--cell', default=None,
                    help='cell size WxH, e.g. 256x144 (default: source '
                         'size)')
    ap.add_argument('--max-frames', type=int, default=0,
                    help='cap the frame count (0 = all)')
    ap.add_argument('--cols', type=int, default=0,
                    help='grid columns (default: near-square)')
    ap.add_argument('--out', default=None,
                    help='output atlas path (default: '
                         '<source>_flipbook.png)')
    args = ap.parse_args()

    cell = None
    if args.cell:
        w, hh = args.cell.lower().split('x')
        cell = (int(w), int(hh))

    src = args.source
    stem = os.path.splitext(os.path.basename(src.rstrip('/\\')))[0]
    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(src)), f'{stem}_flipbook.png')

    tmp = None
    try:
        if os.path.isdir(src):
            paths = sorted(
                os.path.join(src, f) for f in os.listdir(src)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif',
                                       '.tga', '.bmp')))
            if args.max_frames:
                paths = paths[:args.max_frames]
        else:
            tmp = tempfile.mkdtemp(prefix='flipbook_')
            paths = extract_video_frames(src, tmp, args.fps, cell,
                                         args.max_frames)
        if not paths:
            sys.exit('no frames found')
        frames = load_frames(paths, cell)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    n = len(frames)
    cw, ch = frames[0].get_x_size(), frames[0].get_y_size()
    atlas, cols, rows = assemble_atlas(frames, args.cols)
    aw, ah = atlas.get_x_size(), atlas.get_y_size()
    if max(aw, ah) > 8192:
        print(f'WARNING: atlas {aw}x{ah} exceeds 8192 px — reduce --fps, '
              f'--cell, or --max-frames')
    if not atlas.write(Filename.from_os_specific(out)):
        sys.exit(f'cannot write {out}')

    has_alpha = atlas.get_num_channels() == 4
    meta = {'cols': cols, 'rows': rows, 'frames': n, 'fps': args.fps,
            'cell_w': cw, 'cell_h': ch, 'alpha': has_alpha,
            'source': os.path.basename(src)}
    with open(os.path.splitext(out)[0] + '.json', 'w',
              encoding='utf8') as f:
        json.dump(meta, f, indent=2)

    print(f'{out}: {aw}x{ah}, {n} frames in {cols}x{rows} cells of '
          f'{cw}x{ch} @ {args.fps} fps'
          + (' (RGBA — premultiplied effect atlas)' if has_alpha else ''))
    print('game-side:')
    print(f"    atlas = loader.load_texture('{os.path.basename(out)}')")
    if has_alpha:
        print(f"    meta = json.load(open("
              f"'{os.path.basename(os.path.splitext(out)[0])}.json'))")
        print(f"    fx = pipeline.spawn_effect(atlas, meta=meta, "
              f"pos=impact_pos, size=10.0)")
    else:
        print(f"    pipeline.set_screen(screen_np, atlas)")
        print(f"    pipeline.play_flipbook(screen_np, cols={cols}, "
              f"rows={rows}, num_frames={n}, fps={args.fps})")


if __name__ == '__main__':
    main()
