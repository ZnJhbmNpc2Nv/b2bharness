#!/usr/bin/env python3
"""Offline Air-Gapped Packaging Tool for Corporate Spec-Kit.
Zero external dependencies; uses Python standard library only (zipfile, hashlib, os, sys).
Packages the entire Corporate Spec-Kit into a self-contained portable distribution with
SHA-256 cryptographic manifests and automated pre-flight integrity verification.
"""
import sys
import os
import zipfile
import hashlib
from pathlib import Path
from typing import List, Tuple, Set

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent charmap errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Script location and repository root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(SCRIPT_DIR, "dist")
ZIP_OUTPUT_NAME = "corporate_speckit_portable.zip"
ZIP_OUTPUT_PATH = os.path.join(DIST_DIR, ZIP_OUTPUT_NAME)

# Excluded directory names and file patterns
EXCLUDED_DIR_NAMES: Set[str] = {
    "__pycache__",
    ".git",
    ".github",
    ".pytest_cache",
    ".vscode",
    ".idea",
    "dist",
    "tmp",
}

EXCLUDED_EXTENSIONS: Set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".tmp",
    ".bak",
    ".swp",
    ".db-wal",
    ".db-shm",
}

EXCLUDED_FILE_NAMES: Set[str] = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}


STANDALONE_VERIFY_SCRIPT = r'''#!/usr/bin/env python3
"""Corporate Spec-Kit Pre-Flight Air-Gap Integrity Verifier.
Zero external dependencies; standard Python library only.
Used by corporate security and audit teams to verify cryptographic checksums
before deployment on intranet / air-gapped systems.
"""
import os
import sys
import hashlib

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sums_file = os.path.join(base_dir, "SHA256SUMS.txt")

    if not os.path.exists(sums_file):
        print(f"[!] Error: Checksums file not found at: {sums_file}")
        sys.exit(1)

    print("=" * 80)
    print("   CORPORATE SPEC-KIT AIR-GAP PRE-FLIGHT INTEGRITY VERIFICATION")
    print(f"   Manifest: {sums_file}")
    print("=" * 80 + "\n")

    total = 0
    passed = 0
    failed = 0
    missing = 0

    with open(sums_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        expected_hash, rel_path = parts
        rel_path = rel_path.lstrip("*").strip()
        full_path = os.path.join(base_dir, *rel_path.split("/"))

        total += 1
        if not os.path.exists(full_path):
            print(f"  [MISSING]  {rel_path}")
            missing += 1
            continue

        actual_hash = sha256_file(full_path)
        if actual_hash.lower() == expected_hash.lower():
            print(f"  [OK]       {rel_path}")
            passed += 1
        else:
            print(f"  [TAMPERED] {rel_path}")
            print(f"             Expected: {expected_hash}")
            print(f"             Actual:   {actual_hash}")
            failed += 1

    print("\n" + "=" * 80)
    if failed == 0 and missing == 0 and total > 0:
        print(f"   [OK] INTEGRITY AUDIT PASSED: {passed}/{total} files verified.")
        print("   Status: UNCOMPROMISED (Air-Gapped Bundle Sealed & Valid)")
        print("=" * 80 + "\n")
        sys.exit(0)
    else:
        print(f"   [FAIL] INTEGRITY AUDIT FAILED!")
        print(f"   Passed: {passed} | Tampered: {failed} | Missing: {missing} | Total: {total}")
        print("   DO NOT PROCEED with launch. Contact Corporate Information Security.")
        print("=" * 80 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
'''


def calculate_sha256(filepath: str) -> str:
    """Compute SHA-256 digest of a local file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def collect_bundle_files(root_dir: str) -> List[Tuple[str, str]]:
    """Recursively collect files to include in bundle, returning (abs_path, rel_path)."""
    bundled: List[Tuple[str, str]] = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Prune excluded directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDED_DIR_NAMES and not d.startswith(".")
        ]

        for filename in filenames:
            if filename in EXCLUDED_FILE_NAMES:
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext in EXCLUDED_EXTENSIONS:
                continue
            if filename.startswith("test_") and filename.endswith(".db"):
                continue

            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, root_dir).replace("\\", "/")
            bundled.append((abs_path, rel_path))

    return sorted(bundled, key=lambda x: x[1])


def build_offline_bundle():
    print("=" * 80)
    print("   CORPORATE SPEC-KIT: AIR-GAPPED OFFLINE PACKAGER")
    print(f"   Source Root: {SCRIPT_DIR}")
    print(f"   Destination: {ZIP_OUTPUT_PATH}")
    print("=" * 80 + "\n")

    os.makedirs(DIST_DIR, exist_ok=True)

    # 1. Collect files
    raw_files = collect_bundle_files(SCRIPT_DIR)
    print(f"[*] Scanning file tree... Found {len(raw_files)} eligible files.")

    # 2. Write standalone verifier script temporarily if not present
    temp_verifier_path = os.path.join(SCRIPT_DIR, "VERIFY_CHECKSUMS.py")
    with open(temp_verifier_path, "w", encoding="utf-8") as f:
        f.write(STANDALONE_VERIFY_SCRIPT)

    # Re-collect files including VERIFY_CHECKSUMS.py
    files_to_bundle = collect_bundle_files(SCRIPT_DIR)
    # Remove SHA256SUMS.txt from collection if it existed from previous run
    files_to_bundle = [item for item in files_to_bundle if item[1] != "SHA256SUMS.txt"]

    # 3. Calculate SHA-256 for all bundled files
    print(f"[*] Computing SHA-256 cryptographic hashes for {len(files_to_bundle)} files...")
    manifest_lines: List[str] = [
        "# Corporate Spec-Kit Air-Gapped Distribution SHA-256 Manifest",
        "# Generated automatically by pack_offline_bundle.py",
        "# Format: <SHA-256>  <relative_filepath>",
        "",
    ]

    for abs_path, rel_path in files_to_bundle:
        digest = calculate_sha256(abs_path)
        manifest_lines.append(f"{digest}  {rel_path}")

    # Write SHA256SUMS.txt
    manifest_content = "\n".join(manifest_lines) + "\n"
    temp_manifest_path = os.path.join(SCRIPT_DIR, "SHA256SUMS.txt")
    with open(temp_manifest_path, "w", encoding="utf-8") as f:
        f.write(manifest_content)

    # Also save in dist/
    dist_manifest_path = os.path.join(DIST_DIR, "SHA256SUMS.txt")
    with open(dist_manifest_path, "w", encoding="utf-8") as f:
        f.write(manifest_content)

    # Add SHA256SUMS.txt to the zip collection
    final_files = list(files_to_bundle)
    final_files.append((temp_manifest_path, "SHA256SUMS.txt"))
    final_files.sort(key=lambda x: x[1])

    # 4. Create ZIP Archive
    print(f"[*] Building ZIP archive: {ZIP_OUTPUT_NAME}...")
    if os.path.exists(ZIP_OUTPUT_PATH):
        os.remove(ZIP_OUTPUT_PATH)

    with zipfile.ZipFile(ZIP_OUTPUT_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path, rel_path in final_files:
            zf.write(abs_path, arcname=rel_path)
            print(f"  + {rel_path}")

    zip_size = os.path.getsize(ZIP_OUTPUT_PATH)
    zip_digest = calculate_sha256(ZIP_OUTPUT_PATH)

    # Write ZIP checksum file in dist/
    zip_sha_file = os.path.join(DIST_DIR, f"{ZIP_OUTPUT_NAME}.sha256")
    with open(zip_sha_file, "w", encoding="utf-8") as f:
        f.write(f"{zip_digest}  {ZIP_OUTPUT_NAME}\n")

    # Cleanup temporary files from source root to keep workdir clean
    if os.path.exists(temp_verifier_path):
        os.remove(temp_verifier_path)
    if os.path.exists(temp_manifest_path):
        os.remove(temp_manifest_path)

    print("\n" + "=" * 80)
    print("   [OK] AIR-GAPPED PORTABLE BUNDLE CREATED SUCCESSFULLY")
    print(f"   Bundle Archive:  {ZIP_OUTPUT_PATH}")
    print(f"   Bundle Size:     {zip_size:,} bytes")
    print(f"   Archive SHA-256: {zip_digest}")
    print(f"   Manifest:        {dist_manifest_path}")
    print(f"   Total Files:     {len(final_files)} files bundled (with VERIFY_CHECKSUMS.py)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    build_offline_bundle()
