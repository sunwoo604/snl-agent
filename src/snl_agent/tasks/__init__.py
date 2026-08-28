"""Task logic — one module per subcommand.

Each module exposes a pure-Python entry point that takes plain arguments and
returns a result object. Nothing here touches Typer, ``sys.argv``, or stdout,
so every task is testable without the CLI.
"""
