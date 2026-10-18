#!/usr/bin/env python3
"""Build the package index served at https://ntsc.yasakei.dev/v1/registry.

Every file in ``packages/`` describes one package:

    [package]
    name = "json"
    description = "JSON parsing and encoding"
    repo = "https://github.com/owner/ntsc-json"
    license = "MIT"
    keywords = ["json", "serialization"]

Versions are discovered from the repository's git tags (``v1.2.3`` or
``1.2.3``). A ``versions = [...]`` list in the package table overrides tag
discovery for repositories that cannot be reached from CI.

Usage:
    python3 scripts/build_index.py                # write index.json
    python3 scripts/build_index.py --check        # fail if index.json is stale
    python3 scripts/build_index.py --validate-only  # schema checks, no network
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ROOT / "packages"
INDEX = ROOT / "index.json"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")
REPO_PREFIXES = ("https://", "http://", "ssh://", "git@")


def version_key(version: str) -> tuple[int, int, int, int, str]:
    match = VERSION_RE.match(version)
    if match is None:
        return (-1, -1, -1, -1, "")
    major, minor, patch = (int(match.group(i)) for i in range(1, 4))
    prerelease = match.group(4) or ""
    return (major, minor, patch, 0 if prerelease else 1, prerelease)


def discover_versions(repo: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", repo],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"error: cannot list tags for {repo}: {error}")
    if result.returncode != 0:
        raise SystemExit(
            f"error: git ls-remote failed for {repo}: {result.stderr.strip()}"
        )
    versions = set()
    for line in result.stdout.splitlines():
        ref = line.split("\t")[-1]
        tag = ref.removeprefix("refs/tags/")
        if tag.startswith("v"):
            tag = tag[1:]
        if VERSION_RE.match(tag):
            versions.add(tag)
    return sorted(versions, key=version_key)


def load_package(path: Path) -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        return {}, [f"{path.name}: invalid TOML: {error}"]

    table = data.get("package")
    if not isinstance(table, dict):
        return {}, [f"{path.name}: missing [package] table"]

    name = table.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        errors.append(
            f"{path.name}: 'name' must match {NAME_RE.pattern} (lowercase letters, digits, '.', '_', '-')"
        )
    elif name != path.stem:
        errors.append(f"{path.name}: 'name' must equal the file name ('{path.stem}')")

    description = table.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{path.name}: 'description' is required")
    elif len(description) > 200:
        errors.append(f"{path.name}: 'description' must be at most 200 characters")

    repo = table.get("repo")
    if not isinstance(repo, str) or not repo.startswith(REPO_PREFIXES):
        errors.append(
            f"{path.name}: 'repo' must be an https://, http://, ssh:// or git@ URL"
        )

    license_name = table.get("license", "")
    if not isinstance(license_name, str):
        errors.append(f"{path.name}: 'license' must be a string")

    keywords = table.get("keywords", [])
    if not isinstance(keywords, list) or any(
        not isinstance(keyword, str) for keyword in keywords
    ):
        errors.append(f"{path.name}: 'keywords' must be a list of strings")

    declared = table.get("versions")
    if declared is not None and (
        not isinstance(declared, list)
        or any(not isinstance(v, str) or not VERSION_RE.match(v) for v in declared)
    ):
        errors.append(f"{path.name}: 'versions' must be a list of semantic versions")

    if errors:
        return {}, errors

    entry = {
        "name": name,
        "description": description.strip(),
        "repo": repo,
        "license": license_name,
        "keywords": keywords,
        "versions": sorted(set(declared or []), key=version_key),
    }
    return entry, []


def collect(validate_only: bool) -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    errors: list[str] = []
    for path in sorted(PACKAGES.glob("*.toml")):
        entry, problems = load_package(path)
        errors.extend(problems)
        if problems:
            continue
        if not entry["versions"] and not validate_only:
            entry["versions"] = discover_versions(entry["repo"])
            if not entry["versions"]:
                errors.append(
                    f"{path.name}: no semantic-version tags found in {entry['repo']}"
                )
                continue
        entries.append(entry)

    seen: set[str] = set()
    for entry in entries:
        if entry["name"] in seen:
            errors.append(f"duplicate package name '{entry['name']}'")
        seen.add(entry["name"])
    return entries, errors


def render(entries: list[dict]) -> str:
    document = {"version": 1, "packages": entries}
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    validate_only = "--validate-only" in argv

    if not PACKAGES.is_dir():
        print("error: packages/ is missing", file=sys.stderr)
        return 1

    entries, errors = collect(validate_only)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    if validate_only:
        print(f"validated {len(entries)} package(s)")
        return 0

    text = render(entries)
    if check:
        current = INDEX.read_text(encoding="utf-8") if INDEX.is_file() else ""
        if current != text:
            print("error: index.json is stale; run python3 scripts/build_index.py", file=sys.stderr)
            return 1
        print(f"index.json is up to date ({len(entries)} package(s))")
        return 0

    INDEX.write_text(text, encoding="utf-8")
    print(f"wrote index.json with {len(entries)} package(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
