#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modpack Processor for RichAutoUpdater.
Supports two upload methods:
1. GitHub Releases: When a release is published with asset '{Name}${Version}.zip',
   computes SHA-256 via streaming and records the direct release URL in metadata.meta.
2. Git Repository: Detects files/folders named '{Name}${Version}' in 'modpacks/',
   computes SHA-256, renames to '{checksum}.zip', and updates metadata.meta.
"""

import os
import sys
import json
import shutil
import hashlib
import zipfile
import urllib.request
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def compute_sha256(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()

def compute_stream_sha256(url):
    hasher = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "RichAutoUpdater-Processor"})
    with urllib.request.urlopen(req) as resp:
        while chunk := resp.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()

def zip_directory(dir_path, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(dir_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dir_path)
                zipf.write(full_path, rel_path)

def load_metadata(meta_file):
    entries = []
    if meta_file.exists():
        with open(meta_file, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str or line_str.startswith("#"):
                    continue
                parts = line_str.split("$")
                if len(parts) >= 4:
                    entries.append({
                        "name": parts[0].strip(),
                        "version": parts[1].strip(),
                        "url": parts[2].strip(),
                        "checksum": parts[3].strip()
                    })
    return entries

def save_metadata(meta_file, entries):
    with open(meta_file, "w", encoding="utf-8", newline="\n") as f:
        for entry in entries:
            f.write(f"{entry['name']}${entry['version']}${entry['url']}${entry['checksum']}\n")
    print(f"Updated '{meta_file}' with {len(entries)} entry(ies).")

def process_release_assets(assets_json_str, meta_file):
    try:
        assets = json.loads(assets_json_str) if isinstance(assets_json_str, str) else assets_json_str
    except Exception as e:
        print(f"Error parsing release assets JSON: {e}")
        return False

    entries = load_metadata(meta_file)
    processed = 0

    for asset in assets:
        name_full = asset.get("name", "")
        download_url = asset.get("browser_download_url", "")
        if "$" not in name_full or not name_full.lower().endswith(".zip"):
            continue

        base_name = name_full[:-4]
        parts = base_name.split("$", 1)
        modpack_name = parts[0].strip()
        modpack_version = parts[1].strip()

        if not modpack_name or not modpack_version or not download_url:
            continue

        print(f"Processing Release Asset: '{name_full}'")
        print(f" -> Downloading stream to compute SHA-256...")
        checksum = compute_stream_sha256(download_url)
        print(f" -> Checksum: {checksum}")
        print(f" -> Download URL: {download_url}")

        found = False
        for entry in entries:
            if entry["name"].lower() == modpack_name.lower() and entry["version"].lower() == modpack_version.lower():
                entry["name"] = modpack_name
                entry["version"] = modpack_version
                entry["url"] = download_url
                entry["checksum"] = checksum
                found = True
                break

        if not found:
            entries.append({
                "name": modpack_name,
                "version": modpack_version,
                "url": download_url,
                "checksum": checksum
            })

        processed += 1

    if processed > 0:
        save_metadata(meta_file, entries)

    return processed > 0

def process_local_modpacks(repo, root_path, meta_file):
    modpacks_dir = root_path / "modpacks"
    if not modpacks_dir.exists():
        modpacks_dir.mkdir(parents=True, exist_ok=True)

    for item in list(modpacks_dir.iterdir()):
        if item.is_dir() and "$" in item.name:
            zip_target = modpacks_dir / f"{item.name}.zip"
            print(f"Compressing folder '{item.name}' -> '{zip_target.name}'...")
            zip_directory(item, zip_target)
            shutil.rmtree(item)

    entries = load_metadata(meta_file)
    processed_count = 0

    for item in list(modpacks_dir.iterdir()):
        if not item.is_file() or "$" not in item.name:
            continue

        filename = item.name
        base_name = filename[:-4] if filename.lower().endswith(".zip") else filename
        parts = base_name.split("$", 1)
        modpack_name = parts[0].strip()
        modpack_version = parts[1].strip()

        if not modpack_name or not modpack_version:
            continue

        checksum = compute_sha256(item)
        target_filename = f"{checksum}.zip"
        target_path = modpacks_dir / target_filename

        print(f"Processed: '{filename}' -> '{target_filename}' (SHA256: {checksum})")

        if target_path.exists() and target_path != item:
            item.unlink()
        else:
            item.rename(target_path)

        download_url = f"https://raw.githubusercontent.com/{repo}/main/modpacks/{target_filename}"

        found = False
        for entry in entries:
            if entry["name"].lower() == modpack_name.lower() and entry["version"].lower() == modpack_version.lower():
                entry["name"] = modpack_name
                entry["version"] = modpack_version
                entry["url"] = download_url
                entry["checksum"] = checksum
                found = True
                break

        if not found:
            entries.append({
                "name": modpack_name,
                "version": modpack_version,
                "url": download_url,
                "checksum": checksum
            })

        processed_count += 1

    if processed_count > 0:
        save_metadata(meta_file, entries)

    return processed_count > 0

def main():
    root_path = Path(".")
    meta_file = root_path / "metadata.meta"
    repo = os.environ.get("GITHUB_REPOSITORY", "TwelveNord-Swiffty/richautoupdater")
    release_assets = os.environ.get("RELEASE_ASSETS_JSON")

    if release_assets and release_assets.strip() not in ("[]", ""):
        print("Detected GitHub Release event. Processing assets...")
        process_release_assets(release_assets, meta_file)
    else:
        print("Processing modpacks directory...")
        process_local_modpacks(repo, root_path, meta_file)

    sys.exit(0)

if __name__ == "__main__":
    main()
