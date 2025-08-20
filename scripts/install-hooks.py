#!/usr/bin/env python3
"""
Install git hooks from the version-controlled hooks/ directory.
Run this after cloning the repository to set up commit validation and tracking export.
"""

import shutil
import stat
import sys
from pathlib import Path


def install_hooks() -> bool:
    """Install git hooks from hooks/ directory to .git/hooks/."""

    # Check if we're in a git repository
    git_dir = Path(".git")
    if not git_dir.exists():
        print("❌ Not in a git repository. Run from repository root.", file=sys.stderr)
        return False

    hooks_src_dir = Path("hooks")
    if not hooks_src_dir.exists():
        print("❌ No hooks/ directory found", file=sys.stderr)
        return False

    hooks_dst_dir = Path(".git/hooks")
    hooks_dst_dir.mkdir(exist_ok=True)

    installed = 0

    for hook_file in hooks_src_dir.glob("*"):
        if hook_file.is_file():
            dst_file = hooks_dst_dir / hook_file.name

            try:
                # Copy hook file
                shutil.copy2(hook_file, dst_file)

                # Make executable
                dst_file.chmod(dst_file.stat().st_mode | stat.S_IEXEC)

                print(f"✓ Installed {hook_file.name}")
                installed += 1

            except Exception as e:
                print(f"❌ Failed to install {hook_file.name}: {e}", file=sys.stderr)
                return False

    if installed == 0:
        print("⚠ No hook files found in hooks/ directory")
        return False

    print(f"\n✓ Successfully installed {installed} git hook(s)")
    print("\nInstalled hooks:")
    print("• pre-commit: Auto-exports enrichment tracking data")
    print("• commit-msg: Validates commit message format")

    return True


def main() -> None:
    """Main entry point."""
    print("Installing git hooks...")
    success = install_hooks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
