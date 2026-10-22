"""Discover an installed Codex CLI without retaining a stale application path.

Only probes --version. Account verification still belongs to checked_app, and
this module never reads credentials, installs programs, or changes permissions.
"""
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from reliability import BridgeFault


@dataclass(frozen=True)
class Executable:
    path: str
    source: str
    version: str


def candidates(environ=None, home=None, app_roots=None, package_roots=None):
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    override = environ.get('DOT_CODEX_EXECUTABLE', '').strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise BridgeFault('CODEX_EXECUTABLE_OVERRIDE_INVALID',
                              'DOT_CODEX_EXECUTABLE must be an absolute executable path.', user_action=True)
        yield path, 'explicit_override'
        return  # A broken explicit choice must not silently select another installation.
    roots = [Path('/Applications'), home / 'Applications'] if app_roots is None else app_roots
    for root in roots:
        root = Path(root)
        for relative in (
            'ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
            'Codex.app/Contents/Resources/codex',
            'Codex.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
            'ChatGPT.app/Contents/Resources/codex',
        ):
            yield root / relative, 'app_bundle'
    for root in ('/opt/homebrew/bin', '/usr/local/bin') if package_roots is None else package_roots:
        yield Path(root) / 'codex', 'package_manager'
    for root in environ.get('PATH', '').split(os.pathsep):
        # Ignore empty/relative entries so the bridge never executes cwd/codex.
        if root and Path(root).is_absolute():
            yield Path(root) / 'codex', 'path'


def resolve_executable(environ=None, home=None, app_roots=None, package_roots=None, runner=None,
                       probe_timeout=2, budget_seconds=8):
    """Fresh, bounded discovery for every connection; no installation cache."""
    runner = subprocess.run if runner is None else runner
    deadline = time.monotonic() + budget_seconds
    seen = set()
    found = False
    override = bool((os.environ if environ is None else environ).get('DOT_CODEX_EXECUTABLE', '').strip())
    for path, source in candidates(environ, home, app_roots, package_roots):
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_file() or not os.access(resolved, os.X_OK):
                continue
        except (OSError, RuntimeError):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        found = True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            result = runner([str(resolved), '--version'], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            timeout=min(probe_timeout, remaining))
            match = re.search(r'^codex(?:-cli)?\s+(\d[\w.+-]{0,80})\s*$',
                              (result.stdout or '')[:4096], re.MULTILINE)
            if result.returncode == 0 and match:
                return Executable(str(resolved), source, match.group(1))
        except (OSError, subprocess.TimeoutExpired):
            pass
    if override:
        raise BridgeFault('CODEX_EXECUTABLE_OVERRIDE_INVALID',
                          'The explicitly selected Codex executable is missing or failed its version probe.', user_action=True)
    raise BridgeFault('CODEX_EXECUTABLE_UNUSABLE' if found else 'CODEX_EXECUTABLE_NOT_FOUND',
                      'No usable installed Codex CLI was found. Delivery is paused; no program was installed or account recreated.',
                      user_action=True)
