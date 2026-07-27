# GitHub Presence — The Public Repo Program

**Status: LIVE.** https://github.com/Apocrypha-Stellarum/Pax3D is a
**standalone public repository** (not a fork) as of 2026-07-28. The
original panda3d fork was renamed `Pax3D-fork-archive` and archived (kept
as the fork-network record; deletion is the user's call, needs the UI).

This document records what was done, the recipes to repeat it, and the
queue for future sessions. House style for all public materials
(user-ratified 2026-07-27): confident and evidence-forward, never
boastful — let the measurements carry the case — and always warm toward
Panda3D/CMU (heritage section, BACKERS.md preserved, full upstream history
preserved). Positioning/strategy notes stay out of the repo.

---

## 1. Identity policy (user-ratified 2026-07-28)

- **Author identity: `Rob de la Selva <actualhuman2025@proton.me>`** — use
  it for all commits, docs, and public text from 2026-07-28 on.
- Git config is set **globally** on this machine (local overrides removed
  from pax3d, sfb2, paxcraft) — all future commits in every repo inherit it.
- **Pre-2026-07-28 history keeps its original author fields BY USER
  DECISION** — do NOT rewrite/force-push history for this.
- Outstanding (user, manual): update the GitHub **profile display name** at
  github.com/settings/profile to match (API token lacks `user` scope), and
  add `actualhuman2025@proton.me` at github.com/settings/emails so future
  commits link to the account (avatar + profile attribution); until then
  they show unlinked.

## 2. What was done (2026-07-27 → 28)

| Step | Detail |
|---|---|
| First push in 5 months | Remote had been stale since 2026-02-26; 213 commits (Sessions A–AJ, all R6 surgery, GVAD + bind-pin) pushed, plus `pre-catchup-merge` tag. Tidy-up first: VR plan committed, `.gitignore` grew a local-artifacts section (build/gate logs, `wheels_*`, scratch notes, `.claude` local). |
| Security audit | CLEAN. Full tree + full fork-era history (every added line) scanned: no keys/tokens/passwords; no personal identifiers in any tracked file (the `tests/express/*.pem` are upstream's public test fixtures). Only exposure: commit author email — addressed by the identity policy above (old history exempt). |
| Rebrand | README rewritten as Pax3D (features, games, heritage+license section), `CHANGELOG.md` curated (fork → Session AJ), `CONTRIBUTING.md` = sovereign-engine policy, upstream `.github` plumbing deleted (Panda3D FUNDING.yml, CI workflows, dependabot, codecov, issue/PR templates). |
| Standalone migration | Via API with the stored GCM credential (scopes: `repo, gist, workflow` — NO `delete_repo`, NO `user`): renamed fork → created fresh `Pax3D` repo (fork=false, description+topics set) → pushed master+tag → archived old fork. Old stale `dev`/`main` branches (Feb-era ancestors) deliberately NOT migrated. Local `origin` URL unchanged. |
| Front page round | README gallery (3 offscreen testbed renders + shields badges), `ROADMAP.md` (public distillation), `documents/USING_PAX3D_RENDER.md` (mirrored from game repo with provenance note), evidence-first bug-report template, **Release `v2026.07`** with the bind-pin wheel (39.8 MB) attached, `documents/media/social_preview.png` (1280×640). |

## 3. Recipes

**Screenshots** (the gallery images): from `C:\python\sfb2`, pax3d-env
python, `PYTHONUTF8=1`:

```
test3d_pax.py --pax3d --sun-mode directional --shadows --selftest
              --win-size 1920x1080 --focus planet --orbital   # (etc.)
```

Fully offscreen, writes `screencaps/pax_testbed_selftest_*.png`. The debug
HUD occupies the top ~180 px — crop `(0, 180, 1920, 1080)` with PIL before
publishing. Known cosmetic bug: the HUD prints a stale `glsl 120` label
(pre-R1.4 leftover; fix game-side someday).

**Releases with wheels**: create via `POST /repos/.../releases`, upload the
`.whl` to `uploads.github.com/.../releases/<id>/assets`. Auth: pull the GCM
token with `git credential fill` (never print it). Tag scheme in use:
CalVer `v2026.07`.

## 4. Future-session queue (rough value order)

0. **Great screenshots, then restore the gallery** — the 2026-07-28
   first-round shots were judged not strong enough (user) and the README
   gallery section was REMOVED pending better ones; the images remain in
   `documents/media/`. Ideas for stronger shots: brighter sun angle (the
   selftest pins az -50 el 18 — add a CLI sun-angle arg to the testbed),
   bloom + lens flare on, orbital limb at a grazing sunrise angle, higher
   supersampled resolution, better-lit hero assets. Also revisit
   `social_preview.png` (same source material) when new shots exist.
1. **README GIF** — 10–20 s of motion (station orbit, nav-light circuits
   blinking [testbed key C], or the clip door [Y]); frames via repeated
   offscreen steps + screenshots, assemble with PIL. Motion outsells stills.
2. **`examples/hello_pax3d.py`** — a ~30-line quickstart proving the
   renderer (init pipeline, load a glb, directional sun + shadows, bloom);
   verify on BOTH stock 1.10 and the Pax3D wheel before publishing.
3. **PyPI question (decision needed)** — the wheel keeps dist name
   `panda3d`, which PyPI reserves for upstream. Real adoption eventually
   wants `pip install pax3d` (dist rename — a build-window item) and/or
   publishing `pax3d_render` as its own pure-Python package. Don't start
   without the user; it's a naming commitment.
4. **GitHub Discussions** — enable when there's any inbound interest;
   Issues alone is fine until then.
5. **GitHub Pages** — docs site (documents/ is already the content); only
   worth it once there are external readers.
6. **Release cadence** — attach future wheels to CalVer releases as build
   windows produce them; note the doubles wheel stays quarantined
   (stock-simplepbr crash, see CLAUDE.md environments table).
7. **Old fork deletion — DECIDED 2026-07-28: delete it** (user; motive:
   one public surface, not two). Safety was proven first: the fork's
   dev/main tips are ancestors of the new repo's master, so it holds zero
   unique commits. GitHub cannot make forks private, so deletion was the
   only alternative to keeping it public. Needs the user in the UI
   (Settings → Danger Zone; API token lacks `delete_repo` by design).
   Note: this does NOT remove pre-rename author emails from public view;
   the same history lives in the new repo by accepted decision.
8. Testbed HUD `glsl 120` stale label (game repo, one line).

## 5. Outstanding manual steps (user)

- Settings → Social preview: upload `documents/media/social_preview.png`.
- github.com/settings/profile: display name → **Rob de la Selva**.
- github.com/settings/emails: add `actualhuman2025@proton.me` (links future
  commits to the account).
- Optional: account avatar/logo for Apocrypha-Stellarum.
- Delete `Pax3D-fork-archive` (decided 2026-07-28, see queue item 7):
  repo Settings → Danger Zone → Delete this repository.
- Unrelated to GitHub: the local `C:\Pax3D` ~58 GB stale pre-transfer copy
  is still pending a decision.
