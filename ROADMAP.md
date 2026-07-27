# Pax3D Roadmap

The roadmap is driven by the games shipping on the engine. Features land
because a game filed a request with field evidence, and everything below
is gated by the paxtest harness before it merges. The detailed program,
with its evidence trail, lives in
[`documents/PAX3D_MASTER_PLAN.md`](documents/PAX3D_MASTER_PLAN.md); this
is the public summary.

## Recently completed (July 2026)

The founding program is done: unified PBR renderer, directional sun and
shadows, HDR bloom, logarithmic depth, atmospheric scattering (ground and
orbital), IBL, SSAO, terrain stack, instancing, GPU morphs, and the legacy
platform surgery (43k lines removed). See [CHANGELOG.md](CHANGELOG.md).

## Active lanes

- **Content adoption.** The games are wiring recently landed features
  (terrain water, detail maps, photo mode, nav-light fleets) into shipping
  content, and their field reports feed the next engine slices.
- **VR (parked, scoped).** OpenXR seated PCVR for Quest-class headsets via
  the SteamVR runtime. Direction ratified, dev-machine bring-up verified
  (`XR_KHR_opengl_enable` measured present). The first code spike is next
  when the lane resumes. Plan:
  [`documents/PAX3D_VR_PLAN.md`](documents/PAX3D_VR_PLAN.md).

## Engine queue (lands on evidence, in scheduled build windows)

C++ changes are batched into build windows and only promoted when a
measurement demands them. See the Language Canon in
[`documents/PAX3D_MASTER_PLAN.md`](documents/PAX3D_MASTER_PLAN.md).

- **Texture-palette skinning.** Joint matrices in a texture/UBO, removing
  the bone cap entirely (full 343-bone rigs verbatim). Deprioritized on
  field evidence until animation packs actually key the extra bones.
- **InstanceList bulk fill.** Flat-buffer/numpy fill for per-instance
  transforms. Queued on profile evidence only.
- **DirectionalLight conveniences.** `set_direction_world`, translation
  stripping. Low urgency; the pipeline owns sun orientation.
- **Python-to-C++ promotions.** None yet. Nothing in the Python
  orchestration layer has profiled hot.

## Watching

- **Vulkan.** Upstream Panda3D's SPIR-V shaderpipeline work is tracked as
  a read-only reference. A port gets evaluated when it can run the paxtest
  suite. The July 2026 catch-up merge moved our base adjacent to that
  branch, which makes a future port materially cheaper.
- **Shadow stripes at certain sun angles.** Reported planetside, never
  reproduced in the testbed. Instrumented and waiting for a capture.

## Principles that shape all of it

1. **Measure first.** No feature or fix lands without a harness check, and
   performance claims need a profile.
2. **Opt-in until proven.** New behavior ships behind flags, and default
   output stays byte-identical until sign-off.
3. **Two games, one engine.** When either game asks for a capability,
   prefer a shape the other gets for free.
