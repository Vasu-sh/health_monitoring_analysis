# Updating This Repo — Quick Runbook

A cheat sheet for making changes later (dashboard tweaks, pipeline changes,
adding features) and getting them live, without re-learning Git from
scratch each time.

## The short version

```bash
cd path/to/pdm-bearing-diagnostics-repo   # or wherever you keep the folder
git pull                                  # 1. get any changes you made on github.com
# ...edit files...
git add .                                 # 2. stage your edits
git commit -m "Describe what you changed" # 3. save a checkpoint
git push                                  # 4. upload it
```

That's it for 90% of changes. Streamlit Cloud auto-redeploys within a
minute or two of any push to `main` — no separate deploy step.

## Before you start editing (every session)

Always run `git pull` first, **especially** if you ever edited a file
directly on github.com (pencil icon) instead of locally — otherwise your
local copy is behind and your next push gets rejected.

## Testing a change locally before pushing

```bash
streamlit run app/app.py
```

Opens the dashboard in your browser using your local files, so you can
catch a broken change before it goes live. `Ctrl+C` in the terminal stops
it.

## Adding a new Python package

1. `pip install <package>` locally to try it.
2. Add it to `requirements.txt` (one line, e.g. `seaborn>=0.13`).
3. Commit and push as usual — Streamlit Cloud reinstalls from
   `requirements.txt` on every deploy, so it picks it up automatically.

## If a Streamlit Cloud deploy fails

Open the app on [share.streamlit.io](https://share.streamlit.io) → click
into it → **Manage app** → read the log at the bottom. Common causes:
- A package in `requirements.txt` with a typo or version that doesn't exist
- A new `import` in the code that isn't listed in `requirements.txt`
- An indentation/syntax error — test locally with `streamlit run app/app.py`
  first to catch these before pushing

## Git Bash gotchas we hit while setting this up (Windows / MINGW64)

- **Pasting a command with Ctrl+V can corrupt it** (shows up as `?[200~`
  errors). Use right-click → Paste, or Shift+Insert, instead.
- **"LF will be replaced by CRLF" warnings are harmless** — just Git
  normalizing line endings for Windows. Not an error, ignore them.
- **`git push` rejected ("fetch first" / "non-fast-forward")** means the
  remote (GitHub) has commits you don't have locally yet — usually because
  you edited a file on github.com directly. Fix: `git pull --no-edit`,
  then `git push` again.
- **"remote origin already exists"** when re-adding a remote — check what
  it's currently pointing to first with `git remote -v`; if it's wrong or
  blank, `git remote remove origin` then re-add it correctly.

## Bigger changes (new sections, new datasets, restructuring)

For anything you're not sure you'll want to keep, work on a separate
branch so `main` (what's deployed) stays stable:

```bash
git checkout -b try-new-feature
# ...edit, test locally...
git add .
git commit -m "Try new feature"
git push -u origin try-new-feature
```

Then on GitHub you can open a "Pull Request" to merge it into `main` once
you're happy with it — or just delete the branch if it didn't work out.
Not required for small edits; just nice to have once changes get bigger.

## One-time reference

- Live app: `https://<your-app-name>.streamlit.app` (add your actual URL
  here once deployed)
- Repo: https://github.com/Vasu-sh/health_monitoring_analysis
- Data source: see `data/README.md`
- Shared Drive storage setup: see `SETUP_DRIVE.md`
- Shared Drive-backed storage (optional): see `SETUP_DRIVE.md`
