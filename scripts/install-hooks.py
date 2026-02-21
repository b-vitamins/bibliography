#!/usr/bin/env python3
"""
Install git hooks from the version-controlled hooks/ directory.

Installed hooks are lightweight wrappers that exec `hooks/<name>` from the
repository root. This avoids stale copied hooks when versioned hook logic
changes.
"""

import stat
import sys
from pathlib import Path

WRAPPER_HEADER = "# Managed by scripts/install-hooks.py; DO NOT EDIT.\n"


def _build_wrapper(hook_name: str) -> str:
    return f"""#!/usr/bin/env bash
{WRAPPER_HEADER}set -euo pipefail
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
hook="$repo_root/hooks/{hook_name}"

if [ ! -f "$hook" ]; then
    echo "Missing versioned hook: $hook" >&2
    exit 1
fi

if [ ! -x "$hook" ]; then
    chmod +x "$hook" 2>/dev/null || true
fi

exec "$hook" "$@"
"""


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
    updated = 0

    for hook_file in hooks_src_dir.glob("*"):
        if hook_file.is_file():
            dst_file = hooks_dst_dir / hook_file.name

            try:
                wrapper = _build_wrapper(hook_file.name)
                prev = ""
                if dst_file.exists():
                    prev = dst_file.read_text(encoding="utf-8")
                if prev != wrapper:
                    dst_file.write_text(wrapper, encoding="utf-8")
                    updated += 1

                # Make executable
                dst_file.chmod(dst_file.stat().st_mode | stat.S_IEXEC)

                print(f"✓ Installed wrapper for {hook_file.name}")
                installed += 1

            except Exception as e:
                print(f"❌ Failed to install {hook_file.name}: {e}", file=sys.stderr)
                return False

    if installed == 0:
        print("⚠ No hook files found in hooks/ directory")
        return False

    print(f"\n✓ Successfully installed {installed} git hook wrapper(s) ({updated} updated)")
    print("\nInstalled hooks:")
    print("• pre-commit: Executes versioned hooks/pre-commit")
    print("• commit-msg: Validates commit message format")

    return True


def main() -> None:
    """Main entry point."""
    print("Installing git hooks...")
    success = install_hooks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
