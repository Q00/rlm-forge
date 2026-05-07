"""Project-local Ouroboros CLI wrapper with the RLM-FORGE TraceGuard gate."""

from __future__ import annotations


def main() -> None:
    """Run upstream Ouroboros after installing the RLM TraceGuard integration."""
    from rlm_forge.ooo_rlm_traceguard import install_ouroboros_rlm_cli_gate

    install_ouroboros_rlm_cli_gate()

    from ouroboros.cli.main import app

    app()
