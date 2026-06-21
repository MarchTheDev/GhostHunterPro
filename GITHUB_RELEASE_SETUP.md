# GitHub Release Setup for Ghost Hunter Pro

This file explains how to connect the built-in updater and the multi-platform GitHub Actions workflow to your own repository.

## 1. Create or choose your GitHub repository
Use the repository where you will publish Ghost Hunter Pro source code and releases.

Example:

```text
https://github.com/yourname/ghosthunterpro
```

## 2. Update the repo settings inside the app config
Open:

```text
ghosthunter_app/config.py
```

Set these two values:

```python
UPDATE_REPO_OWNER = "yourname"
UPDATE_REPO_NAME = "ghosthunterpro"
```

After that, the Settings page can check the latest GitHub release.

## 3. Commit the workflow file
Make sure this file exists in your project:

```text
.github/workflows/build.yml
```

This workflow builds:
- Windows EXE
- Windows NSIS installer
- Windows portable ZIP
- Linux portable tar.gz
- Linux .deb
- macOS ZIP
- Draft GitHub release

## 4. Update the VERSION file before release
Open:

```text
VERSION
```

Set the version number, for example:

```text
2.3
```

## 5. Push to GitHub
Push your code to the repository.

If your workflow is configured to build on push, GitHub Actions will start automatically.

You can also run it manually from:
- GitHub
- Actions
- Build Multi-Platform
- Run workflow

## 6. Check the draft release
When the workflow completes, it creates a **draft release** with all artifacts attached.

Open:
- your repository
- Releases
- Draft release

Review the assets, then publish the release.

## 7. How the app updater works
Once a release is published:
- the app checks the GitHub Releases API
- if a newer version exists, Settings can show it
- the installer update can be downloaded and launched
- the portable package can also be downloaded

## 8. Optional but recommended
For a cleaner professional setup, also add:
- repository description
- app icon files (`ghosthunter.ico`, `ghosthunter.icns`)
- release notes for every version
- screenshots in the repo README

## 9. Notes
- The updater is currently designed around GitHub Releases.
- The installer update flow works best on Windows.
- Make sure release asset names stay consistent with the workflow and updater expectations.
