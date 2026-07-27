# Pax3D VR Plan — Quest 2/3 Seated PCVR

**Status: DIRECTION RATIFIED (user, 2026-07-26). No code yet — VR0 not started.**

User direction: build VR for the market leader, **Meta Quest 2 and 3**, as a
**seated simulation experience** — keyboard + mouse + headset are the primary
inputs. Controllers are a stretch goal ("would be fun"): interact ("E")
actions and moving around walkable ship interiors. Not a room-scale game.

Reference implementation studied 2026-07-26: `el-dee/panda3d-openxr`
(Apache-2.0, ~1,300 lines). The public repo is **frozen at v0.1.2, June
2024** — the author's April-2026 forum-mentioned improvements were never
pushed. Treat as a reference to mine, not a dependency. His older
`el-dee/panda3d-openvr` is more mature (action manifests, skeletons) and is
the fallback-path reference.

---

## 1. Decision register

| Decision | Choice | Status |
|---|---|---|
| Target hardware | Meta Quest 2 + Quest 3, PCVR (streamed) | **Ratified 2026-07-26** |
| Experience model | Seated sim; kb+m primary; HMD owns view orientation | **Ratified 2026-07-26** |
| Controllers | Stretch goal: interact + interior locomotion only | **Ratified 2026-07-26** |
| VR API | **OpenXR** (via pyopenxr); OpenVR (pyopenvr + panda3d-openvr reference) stays the documented fallback if VR0 hits GL trouble on the SteamVR OpenXR runtime | **DECIDED 2026-07-26** (user delegated the call) |
| Runtime | **SteamVR as the active OpenXR runtime** (forced: only runtime exposing GL on Windows) | Forced by the GL matrix, §2 |
| Swapchain hand-off | **Blit path first** (pipeline output → `glBlitFramebuffer` → XR image); direct-attach or C++ adoption API later on evidence | Proposed |
| Reference space | `LOCAL` (seated), not `STAGE`; recenter bound to a key + runtime-native recenter | Proposed |

The API decision rationale: Meta deprecated LibOVR (native PC SDK) in favor
of OpenXR; OpenVR is in maintenance mode at Valve; every future native path
(VDXR, Meta Link runtime via D3D interop, eventual Vulkan backend) is
OpenXR-only. But OpenVR's GL-on-Windows path is older and more proven than
SteamVR's OpenXR GL support, and the Panda-side reference library for OpenVR
is more complete. Since BOTH terminate at SteamVR for a GL engine (§2), the
choice costs little either way — if the VR0 spike hits GL problems on the
OpenXR runtime, switch to OpenVR with minimal sunk cost.

## 2. The runtime matrix (why SteamVR)

Two independent layers for Quest PCVR — do not conflate them:

- **Transport** (frames to the headset): Quest Link / Air Link (Meta),
  Virtual Desktop, Steam Link, ALVR. User's choice; all fine.
- **Runtime** (what our process talks to): must expose
  `XR_KHR_opengl_enable` for our GL-only engine.

| Runtime | GL on Windows? | Note |
|---|---|---|
| SteamVR OpenXR | **YES** (added ~2021; internally bridges GL↔D3D — known pink-screen wrinkles on AMD GPUs, solid on NVIDIA) | **Our runtime.** Works over every transport (with Link it drives the Oculus driver) |
| SteamVR OpenVR API | YES (most battle-tested GL path in VR) | The fallback API route |
| Meta Quest Link runtime | NO (D3D11/12, Vulkan) | Native path only via D3D interop bridge or Vulkan — see §6 |
| VDXR (Virtual Desktop) | Almost certainly NO (unverified — README silent; same-author family is D3D11/12+Vulkan) | Same |
| WMR | NO (and WMR is dead) | — |

User setup prerequisite (dev machine): SteamVR installed, Quest connected
via any transport, **SteamVR set as the active OpenXR runtime** (SteamVR
Settings → OpenXR → "Set SteamVR as OpenXR runtime"). This is a completely
standard consumer Quest-PCVR configuration.

## 3. What we take from panda3d-openxr, and what we do differently

Mechanism proven by the reference (whole thing works WITHOUT engine
changes): hand Panda's live `wglGetCurrentDC/Context` to the runtime
(`XR_KHR_opengl_enable`); per eye, an offscreen buffer at the runtime's
recommended resolution + a camera with a `MatrixLens` built from the XR
asymmetric FOV angles; frame pacing by `xrWaitFrame` in an early task
(`sync-video 0` + `__GL_SYNC_TO_VBLANK=0` — v-sync OFF, the runtime blocks
for pacing; the game's own frame limiter must also be off in VR);
`xrLocateViews` at predicted display time → eye camera pos/quat; at draw
time, get pixels into the acquired swapchain image; `xrEndFrame` submits.
Coordinate conversion Y-up-RH ↔ Z-up-RH throughout.

Differences for us:

1. **Blit, don't attachment-swap.** The reference hijacks Panda's FBO color
   attachment via raw PyOpenGL at draw-callback time — fragile, and
   incompatible with MSAA eye buffers. We render the pipeline (incl. MSAA 4×
   and the post chain) into its own resolved texture and
   `glBlitFramebuffer` into the XR image. One copy; measure before
   optimizing it away (§6 item 1 removes it properly).
2. **Pipeline-native eyes.** Two eye cameras registered with pax3d_render
   like any other camera (multi-camera is proven machinery: sky, viewmodel).
   The sun shadow pass is view-independent — rendered once, shared by both
   eyes. Per-eye: scene + post. VR1 detail against
   `PAX3D_RENDER_ARCHITECTURE.md` at implementation time.
3. **sRGB is a contract, not a hope.** Swapchain `SRGB8_ALPHA8`; the encode
   state of our tonemap output into it gets a gate check (mismatched
   `GL_FRAMEBUFFER_SRGB` is THE classic VR washed-out bug — same defect
   class R1 killed).
4. **`LOCAL` reference space** (seated), not the reference's hardcoded
   `Stage`.
5. **Fix the quat TODO.** The reference hand-rolls the orientation remap
   `(w, x, -z, y)` with a "check why" comment — derive it properly from the
   coordinate-system change and gate the round-trip.
6. **Optional import discipline.** `pax3d_render/xr/` imports pyopenxr +
   PyOpenGL only when VR is enabled — the pipeline stays dependency-light.
7. **Mirror window for free.** Eye buffers are textures; card the left eye
   into the normal desktop window. Desktop window keeps keyboard/mouse
   focus — that IS the kb+m input path.

## 4. Phases

| Phase | Content | Exit gate |
|---|---|---|
| VR0 | Spike: vendored/adapted session+swapchain+views layer in `pax3d_render/xr/`; testbed `--vr` on the stock scene; blit path; SteamVR runtime on real Quest. **Decides OpenXR vs OpenVR.** | Stable stereo view in-headset; `test_xr_math` green (see §5); GL-error clean (`test_gl_clean` discipline) |
| VR1 | Pipeline integration: registered eye cameras, shared shadow pass, per-eye post, sRGB encode pinned, mirror window, recenter key. Perf measured on openworld + station scenes. | Gate rows green; measured frame budget report at Quest-2 90 Hz target resolution |
| VR2 | Actions (stretch): one action set — interact bool ("E"), thumbstick locomotion + snap turn, aim pose; suggested bindings for `oculus/touch_controller` profile; hand anchors. Game-side mapping. | Live smoke (SKIP-unless-runtime) + game adoption note |
| VR3 | Build-window promotions on evidence only (§6) | Per item |

Game-side (sfb2, not this repo): mouse-look decoupling (HMD owns
orientation; mouse keeps ship/turret control — the Elite Dangerous model),
cockpit seat anchor, comfort options for interior walking if VR2 lands.

## 5. Harness strategy

Almost everything above the session layer is testable WITHOUT a headset:

- `test_xr_math`: projection-from-FOV-angles vs an independent construction
  (the test_orbital pattern), coordinate/quat conversion round-trips,
  anchor hierarchy contract. Pure math — runs everywhere, no xr import.
- **Fixture replay** (the fact-#12 "pin poses" lesson): record real
  `XrView` data from one live session once; replay deterministically
  in-gate. Render both eyes of a known scene; check horizontal disparity
  against the IPD/depth formula analytically; pin the sRGB encode.
- Live-runtime smoke: SKIPs when no runtime present (the test_thread_bind
  SKIP pattern).

## 6. Engine C++ candidates (→ master-plan build-window queue when armed)

1. **External-texture adoption** (small): wrap a foreign GL texture ID as a
   first-class color attachment / Panda Texture. Kills the PyOpenGL blit AND
   the copy. Generally useful beyond XR (video/capture interop). First
   promotion once VR0 proves the shape. (This is the upstream feature
   request el-dee said he'd file and never did — we just build it.)
2. **D3D11 interop bridge** (`WGL_NV_DX_interop2`, the Blender GHOST_XR
   pattern): unlocks Meta's native Link runtime + VDXR without SteamVR.
   Medium C++. Only if SteamVR-hop latency/quality proves to matter.
3. **Multiview stereo** (`GL_OVR_multiview2`): one cull + one draw for both
   eyes (~halves VR CPU cost); shader variant work (`gl_ViewID_OVR`).
   Strictly on profile evidence — if two-pass holds 90 Hz, it never lands.
4. **Native frame pacing** (move `xrWaitFrame` into the frame loop):
   marginal; only if task-based pacing proves janky.

The Vulkan watch item (R6) quietly gains weight: a Vulkan backend is also
the door to every non-SteamVR runtime natively.

## 7. Risks / watch items

- **Perf is the main risk.** Quest 2 target ≈ 90 Hz × 2 eyes at ~1832×1920
  each (SteamVR's recommended target varies with supersampling). openworld
  measured 103–115 fps at 1600×900 MONO — stereo at ~4× the pixels is a
  real jump. Levers: render-scale knob (ship it in VR1), per-eye post cost,
  §6.3 multiview if CPU-bound. No eye-tracked foveation on Quest 2/3.
  Measure in VR1, don't speculate.
- **SteamVR OpenXR GL↔D3D internal bridge**: AMD pink-screen history;
  dev machine GPU believed NVIDIA (verify at VR0).
- **TAA in VR** is its own research topic (jitter × reprojection) — MSAA 4×
  stays the VR quality baseline.
- **Log depth × depth-layer submission**: `XR_KHR_composition_layer_depth`
  (better reprojection) expects a conventional depth buffer; under
  `enable_log_depth` linearize or skip depth submission. The reference
  submits no depth at all — acceptable v1.
- **Camera-relative rendering (R4) gains priority**: sub-millimeter head
  tracking at space-sim offsets will show float32 jitter far sooner than a
  mouse camera does.
- **In-world screens (ER-005) are the VR UI answer** — no screen-space HUD
  conversion debt. Design HUD-ish elements as cockpit surfaces.

## 8. References

- `el-dee/panda3d-openxr` (Apache-2.0, frozen v0.1.2 2024-06-11) — studied
  clone in session scratchpad 2026-07-26; re-clone from GitHub when needed.
- `el-dee/panda3d-openvr` — the more mature OpenVR sibling; fallback-path
  reference.
- pyopenxr (cmbruns) ≥1.1.0 — actively maintained ctypes wrapper.
- Blender `GHOST_XR` — the D3D interop bridge precedent for GL engines.
