from __future__ import annotations

import threading
import time
import webbrowser

import click
import uvicorn


@click.command()
@click.option("--port", default=8000, show_default=True,
              help="Port to run the SynapChart server on.")
@click.option("--no-browser", is_flag=True, default=False,
              help="Start server without opening a browser tab.")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Host address to bind to. Use 0.0.0.0 to allow network access.")
def main(port: int, no_browser: bool, host: str) -> None:
    """SynapChart — visual pipeline builder for neuroscience.

    Starts the local server and opens the UI in your browser.
    Press Ctrl+C to stop.
    """
    if host == "0.0.0.0":
        click.echo(
            "WARNING: Running with --host 0.0.0.0 exposes the server to your network. "
            "Custom block execution runs arbitrary Python code. "
            "Only do this on a trusted network.", err=True,
        )
    click.echo(f"Starting SynapChart on http://{host}:{port}")
    click.echo("Press Ctrl+C to stop.\n")

    if not no_browser:
        def _open() -> None:
            time.sleep(1.5)
            webbrowser.open(f"http://127.0.0.1:{port}")
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
