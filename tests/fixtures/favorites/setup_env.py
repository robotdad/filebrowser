"""Environment setup helper for favorites browser tests."""

from pathlib import Path

# Default base directory for fixture state.
WORK_DIR = Path(__file__).resolve().parents[3] / ".work"

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


def setup_test_environment(work_dir: Path = WORK_DIR) -> dict[str, Path]:
    """Create all fixture files, test directories, and legacy seeds."""
    work_dir = Path(work_dir).absolute()
    if not work_dir.is_relative_to(WORK_DIR) or WORK_DIR.is_symlink():
        raise ValueError("Fixture setup must stay within this worktree's .work directory")
    # Refuse existing symlinks before writing anything, including nested fixture
    # files. Setup is deliberately non-destructive: restarts must retain stores.
    for ancestor in (work_dir, *work_dir.parents):
        if ancestor == WORK_DIR.parent:
            break
        if ancestor.is_symlink():
            raise ValueError("Fixture setup does not follow symlinks")
    if not work_dir.resolve().is_relative_to(WORK_DIR.resolve()):
        raise ValueError("Fixture setup must stay within this worktree's .work directory")
    test_home = work_dir / "test-home"
    test_data = work_dir / "test-data"
    test_external = work_dir / "test-external"
    for root in (test_home, test_data, test_external):
        if root.is_symlink() or any(p.is_symlink() for p in root.rglob("*")):
            raise ValueError("Fixture setup does not follow symlinks")
    test_home.mkdir(parents=True, exist_ok=True)
    test_data.mkdir(parents=True, exist_ok=True)
    test_external.mkdir(parents=True, exist_ok=True)

    # Subdirectories
    (test_home / "alpha").mkdir(exist_ok=True)
    (test_home / "alpha" / "alpha_doc.txt").write_text("Alpha document content.\n", encoding="utf-8")

    (test_home / "beta").mkdir(exist_ok=True)
    (test_home / "beta" / "beta_code.py").write_text("def beta():\n    return 'beta'\n", encoding="utf-8")

    (test_home / "legacy-only").mkdir(exist_ok=True)
    (test_home / "legacy-only" / "legacy.txt").write_text("Legacy directory content.\n", encoding="utf-8")

    # Sample files in root of TEST_HOME
    (test_home / "notes.txt").write_text("Hello from baseline browser testing!\nLine 2.\n", encoding="utf-8")
    (test_home / "script.py").write_text(
        "#!/usr/bin/env python3\n\"\"\"Sample Python code for syntax highlight preview.\"\"\"\ndef greet(name: str) -> str:\n    return f'Hello, {name}!'\n\nif __name__ == '__main__':\n    print(greet('world'))\n",
        encoding="utf-8",
    )
    (test_home / "readme.md").write_text(
        "# Baseline Browser Verification\n\nThis is a **markdown** preview verification document.\n\n- Feature 1: Files\n- Feature 2: Favorites\n- Feature 3: Locations\n",
        encoding="utf-8",
    )
    (test_home / "sample.png").write_bytes(MINIMAL_PNG)
    (test_home / "graph.dot").write_text(
        "digraph G {\n    rankdir=LR;\n    node [shape=box];\n    Browser -> App -> Filesystem;\n}\n",
        encoding="utf-8",
    )

    # External directory outside HOME
    (test_external / "ext_info.txt").write_text("External root document.\n", encoding="utf-8")
    (test_external / "sub").mkdir(exist_ok=True)
    (test_external / "sub" / "data.txt").write_text("External nested document.\n", encoding="utf-8")

    # Seed legacy shared favorites.json with odd formatting
    legacy_only_resolved = str((test_home / "legacy-only").resolve())
    odd_formatted_favorites = f"""{{
  "favorites":   [
    {{
      "path":   "{legacy_only_resolved}"
    }}
  ]
}}
"""
    legacy_favorites = test_data / "favorites.json"
    if not legacy_favorites.exists():
        legacy_favorites.write_text(odd_formatted_favorites, encoding="utf-8")

    return {
        "home": test_home.resolve(),
        "data": test_data.resolve(),
        "external": test_external.resolve(),
    }


if __name__ == "__main__":
    paths = setup_test_environment()
    print("Test environment seeded successfully:")
    for k, v in paths.items():
        print(f"  {k}: {v}")
