# Contributing to Pax3D

Pax3D is a sovereign engine developed by a small team, with a roadmap
driven by the games shipping on it. It is not (yet) run as a community
project: there is no contribution pipeline, review rota, or Discord. That
may change as the engine matures.

## Bug reports

Bug reports are welcome via GitHub Issues. The most valuable thing you can
include is a **minimal reproduction**, ideally one that could become a
`tools/paxtest/` check. This project's history is a graveyard of
plausible-sounding rendering bugs that measurement disproved (see the
"hard-won facts" in `CLAUDE.md` and `documents/PAX3D_MASTER_PLAN.md`), so
evidence beats description.

## Pull requests

PRs are read, but the bar is the same one the engine holds itself to:

1. **Measure first.** A rendering change needs a paxtest check that fails
   before and passes after. A performance change needs a number.
2. **Match the canon.** Prototype in Python/GLSL (`pax3d_render/`); C++
   only where the work class demands it, tagged with `// PAX3D:` comments.
3. **Keep diffs focused.** No drive-by reformatting.

If your contribution is general-purpose engine work that isn't specific to
Pax3D's direction, consider offering it to
[Panda3D](https://github.com/panda3d/panda3d) as well. The upstream
project is community-driven and welcomes contributors.

## Copyright

Pax3D descends from Panda3D (copyright Carnegie Mellon University) and is
licensed under the Modified BSD License. By submitting changes you accept
that your code is placed under the same license.
