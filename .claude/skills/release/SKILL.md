---
name: release
description: "Step-by-step release procedure: bump __version__, write the CHANGELOG entry, check the build, produce Slack release notes, then tag and create the GitHub Release. Use when the user says \"do the release actions\" or asks to prepare/cut a release."
disable-model-invocation: true
---

# Release Actions

Follow these steps in order. Ask the user for the **new version number** and the **changes** if they have not been provided.

---

## Step 0 — Collect inputs

1. **New version number** (e.g. `0.2.0`)
2. **Previous version number** (e.g. `0.1.0`), for the GitHub compare URL
3. **Release date** in `YYYY-MM-DD` format (default: today)
4. **Changes**: the commits or PRs since the previous tag (`git log vPREVIOUS..HEAD --oneline`)

---

## Step 1 — Update the version

The version lives in one place: `src/robotframework_events/__init__.py` (`__version__ = "X.Y.Z"`).
`pyproject.toml` reads it (`[tool.setuptools.dynamic]`), and `rfevents --version` prints it.

---

## Step 2 — Update CHANGELOG.md

Insert a new section **at the top** (after the header block, before the previous latest version). Match the existing style.

```markdown
## [X.Y.Z](https://github.com/timdegroot1996/robotframework-events/releases/tag/vX.Y.Z) - YYYY-MM-DD

### Added
- <feature description>

### Fixed
- <fix description>

### Changed
- <change description>

---
```

Rules:
- Only include `### Added`, `### Fixed`, `### Changed` sections that are non-empty.
- Human-readable, user-facing bullets; no raw commit or PR titles, no contributor attribution, no PR URLs.
- Use backticks for options, file names, event types and code references.
- A change to the event format (new event type, new field, changed meaning) is always mentioned, with the format version `v` if it changed.

---

## Step 3 — Check the build

```bash
ruff check . && ruff format --check . && mypy
pytest
python -m build && python -m twine check dist/*
```

Then remove `dist/` again; `scripts\release.bat` builds it fresh.

---

## Step 4 — Generate Slack release notes

A ready-to-paste Slack message, **short and scannable**.

Rules:
- **One-line summary** under the title, naming the theme of the release.
- **Section headers without emoji**: `Added`, `Fixed`, `Changed`, `Resources`, in that order, only the non-empty ones. No `---` separators.
- **One bullet per change**: `*<Short name>* — <one or two sentences on what changed and why it matters>`. No code examples, no PR numbers.
- **No timings in the bullets**; performance gains go in the summary line as percentages.
- **Thank external contributors inline** (anyone who is not `@timdegroot1996`): `Thanks @name for …!`

Format:

```
:robot: *robotframework-events vX.Y.Z is out!* :tada:

<one-line summary of the release theme>

*Added*
• *<Feature name>* — <one or two sentences>.

*Fixed*
• <what the user no longer runs into>.

*Resources*
Full changelog: https://github.com/timdegroot1996/robotframework-events/compare/vPREVIOUS...vX.Y.Z
PyPI: https://pypi.org/project/robotframework-events/X.Y.Z/
Repository: https://github.com/timdegroot1996/robotframework-events
```

For the first release there is no previous version: link the changelog instead of a compare URL.

---

## Step 5 — Commit, upload, tag, GitHub Release

1. Commit the release (`Release X.Y.Z`) and push to `main`; wait for CI to pass.
2. The user uploads to PyPI from the repository root with `scripts\release.bat` (asks for the PyPI token) and posts the Slack notes.
3. **Tag the release commit** after it is on `main`:
   ```bash
   git checkout main && git pull
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```
4. **GitHub Release** (auto-generated "What's Changed"):
   ```bash
   gh release create vX.Y.Z --title "robotframework-events vX.Y.Z" --generate-notes --notes-start-tag vPREVIOUS --latest
   ```
   For the first release, leave out `--notes-start-tag`.
5. Check `https://pypi.org/project/robotframework-events/X.Y.Z/`.

---

## Quick checklist

- [ ] `src/robotframework_events/__init__.py` — `__version__` updated
- [ ] `CHANGELOG.md` — new section at the top
- [ ] Lint, mypy, tests and `twine check` pass
- [ ] Slack release notes produced
- [ ] Release commit on `main`, CI green
- [ ] `scripts\release.bat` run by the user (PyPI)
- [ ] `vX.Y.Z` tag pushed, GitHub Release created
