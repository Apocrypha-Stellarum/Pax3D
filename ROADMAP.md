# Pax3D Roadmap

The roadmap is driven by the games shipping on the engine — features land
because a game filed a request with field evidence, and everything below is
gated by the paxtest harness before it merges. The detailed program (with
its evidence trail) lives in `documents/PAX3D_MASTER_PLAN.md`; this is the
public summary.

## Recently completed (July 2026)

The founding program is done: unified PBR renderer, directional sun +
shadows, HDR bloom, logarithmic depth, atmospheric scattering (ground and
orbital), IBL, SSAO, terrain stack, instancing, GPU morphs, and the legacy
platform surgery (−43k lines). See [CHANGELOG.md](CHANGELOG.md).

## Active lanes

- **Content adoption** — the games are wiring recently-landed features
  (terrain water, detail maps, photo mode, nav-light fleets) into shipping
  content; field reports feed the next engine slices.
- **VR (parked, scoped)** — OpenXR seated PCVR for Quest-class headsets via
  the SteamVR runtime. Direction ratified, dev-machine bring-up verified
  (`XR_KHR_opengl_enable` measured present); the first code spike is next
  when the lane resumes. Plan: `documents/PAX3D_VR_PLAN.md`.

## Engine queue (lands on evidence, in scheduled build windows)

C++ changes are batched into build windows and only promoted when a
measurement demands them — see the Language Canon in `CLAUDE.md`.

- **Texture-palette skinning** — joint matrices in a texture/UBO, removing
  the bone cap entirely (full 343-bone rigs verbatim). Deprioritized on
  field evidence until animation packs actually key the extra bones.
- **InstanceList bulk fill** — flat-buffer/numpy fill for per-instance
  transforms; queued on profile evidence only.
- **DirectionalLight conveniences** — `set_direction_world`, translation
  stripping; low urgency, the pipeline owns sun orientation.
- **Python→C++ promotions** — none yet; nothing in the Python orchestration
  layer has profiled hot.

## Watching

- **Vulkan** — upstream Panda3D's SPIR-V shaderpipeline work is tracked as
  a read-only reference. A port is evaluated when it can run the paxtest
  suite; the July 2026 catch-up merge moved our base adjacent to that
  branch, making a future port materially cheaper.
- **Shadow stripes at certain sun angles** — reported planetside, never
  reproduced in the testbed; instrumented and waiting for a capture.

## Principles that shape all of it

1. **Measure first.** No feature or fix lands without a harness check;
   performance claims need a profile.
2. **Opt-in until proven.** New behavior ships behind flags; default output
   stays byte-identical until sign-off.
3. **Two games, one engine.** When either game asks for a capability,
   prefer a shape the other gets for free.
