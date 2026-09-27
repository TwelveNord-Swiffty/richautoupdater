#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modpack Processor for RichAutoUpdater.
Detects modpack files/directories named '{Name}${Version}' in 'modpacks/',
computes their SHA-256 checksum, renames the archive to '{checksum}.zip',
and updates/appends the metadata entry in 'metadata.meta'.
"""

import os
import sys
import shutil
import hashlib
import zipfile
from pathlib import Path

# Ensure UTF-8 output even in environments with different defaults
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def compute_sha256(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()

def zip_directory(dir_path, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(dir_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dir_path)
                zipf.write(full_path, rel_path)

def process_modpacks(repo=None, branch=None, root_dir="."):
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "TwelveNord-Swiffty/richautoupdater")
    branch = branch or os.environ.get("GITHUB_REF_NAME", "main")
    if branch.startswith("refs/heads/"):
        branch = branch[len("refs/heads/"):]

    root_path = Path(root_dir)
    modpacks_dir = root_path / "modpacks"
    meta_file = root_path / "metadata.meta"

    if not modpacks_dir.exists():
        print(f"Directory '{modpacks_dir}' does not exist. Creating...")
        modpacks_dir.mkdir(parents=True, exist_ok=True)

    # 1. Check for any folders containing '$' in 'modpacks/' and compress them into zip
    for item in list(modpacks_dir.iterdir()):
        if item.is_dir() and "$" in item.name:
            zip_target = modpacks_dir / f"{item.name}.zip"
            print(f"Compressing folder '{item.name}' -> '{zip_target.name}'...")
            zip_directory(item, zip_target)
            shutil.rmtree(item)

    # 2. Read existing metadata
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

    # 3. Find and process files named '{Name}${Version}' or '{Name}${Version}.zip'
    processed_count = 0
    for item in list(modpacks_dir.iterdir()):
        if not item.is_file():
            continue

        filename = item.name
        if "$" not in filename:
            continue

        base_name = filename
        if base_name.lower().endswith(".zip"):
            base_name = base_name[:-4]

        parts = base_name.split("$", 1)
        modpack_name = parts[0].strip()
        modpack_version = parts[1].strip()

        if not modpack_name or not modpack_version:
            print(f"Skipping '{filename}': could not extract Name and Version.")
            continue

        # Verify zip archive integrity
        try:
            with zipfile.ZipFile(item, "r") as zf:
                bad_file = zf.testzip()
                if bad_file:
                    print(f"Warning: Archive '{filename}' contains corrupted file '{bad_file}'!")
        except Exception as e:
            print(f"Error reading zip archive '{filename}': {e}")
            continue

        # Calculate checksum (SHA-256)
        checksum = compute_sha256(item)
        target_filename = f"{checksum}.zip"
        target_path = modpacks_dir / target_filename

        print(f"Processed: '{filename}'")
        print(f" -> Name: '{modpack_name}', Version: '{modpack_version}'")
        print(f" -> Checksum: {checksum}")
        print(f" -> Target File: {target_filename}")

        if target_path.exists() and target_path != item:
            item.unlink()
        else:
            item.rename(target_path)

        # Permanent download URL always points to main
        download_url = f"https://raw.githubusercontent.com/{repo}/main/modpacks/{target_filename}"

        # Update or append to metadata
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

    # 4. Save metadata.meta
    if processed_count > 0:
        with open(meta_file, "w", encoding="utf-8", newline="\n") as f:
            for entry in entries:
                f.write(f"{entry['name']}${entry['version']}${entry['url']}${entry['checksum']}\n")
        print(f"Updated '{meta_file}' with {len(entries)} entry(ies).")

    return processed_count > 0

if __name__ == "__main__":
    changed = process_modpacks()
    sys.exit(0 if changed else 0)
