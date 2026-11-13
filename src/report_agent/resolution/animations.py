"""Application-registered Matplotlib animation generators with owned worker lifetime."""

import json
import math
import multiprocessing
import os
import signal
from collections.abc import Callable, Mapping
from itertools import islice
from pathlib import Path

from report_agent.metadata.office import ExportOptions
from report_agent.models.inputs import AnimationInput


def _generate(connection, generator, tables, options, workspace):
    if os.name == "posix":
        os.setsid()
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.animation import Animation, FFMpegWriter, PillowWriter

        animation = generator(tables, options)
        if not isinstance(animation, Animation):
            raise ValueError("Animation generator must return a Matplotlib Animation.")
        animation._fig.set_size_inches(options.width_px / 100, options.height_px / 100)
        target = workspace / f"animation.{options.format}"
        poster = workspace / "poster.png"
        if options.poster_frame == "first":
            animation._init_draw()
            animation._fig.savefig(poster, dpi=100)
        count = math.ceil(options.duration_seconds * options.fps)
        # Bound iteration independently of interactive repeat settings.
        frames = (
            list(islice(animation.new_frame_seq(), count + 1))
            if getattr(animation, "_save_count", None) is not None
            else []
        )
        if len(frames) != count:
            raise ValueError(f"Generator needs {count} finite frames.")
        writer = (
            PillowWriter(fps=options.fps)
            if options.format == "gif"
            else FFMpegWriter(
                fps=options.fps, codec="libx264", extra_args=["-pix_fmt", "yuv420p"]
            )
        )
        animation.save(target, writer=writer, dpi=100)
        if options.poster_frame == "last":
            animation._fig.savefig(poster, dpi=100)
        if target.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("Encoded animation exceeds 50 MiB.")
        (workspace / "animation.json").write_text(
            json.dumps(
                {
                    "format": options.format,
                    "fps": options.fps,
                    "frames": count,
                    "width": options.width_px,
                    "height": options.height_px,
                    "duration_seconds": options.duration_seconds,
                },
                indent=2,
            )
        )
        plt.close(animation._fig)
        connection.send(None)
    except BaseException as exc:
        connection.send(f"{type(exc).__name__}: {exc}")
    finally:
        connection.close()


class AnimationGenerators:
    """Generators are trusted application functions; no imports/code from metadata.

    The registry uses fork on macOS/Linux to avoid serializing live figures or
    arbitrary callbacks. Call from a dedicated single-threaded rendering worker.
    """

    def __init__(self, generators: Mapping[str, Callable], timeout_seconds=120):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Animation timeout must be positive.")
        self.generators = dict(generators)
        self.timeout_seconds = timeout_seconds

    def generate(self, name, tables, options: ExportOptions, workspace: Path):
        if name not in self.generators:
            raise ValueError(f"Unknown animation generator: {name}")
        if os.name != "posix":
            raise ValueError("Animation workers currently require macOS/Linux.")
        # Pillow retains decoded frames; reject jobs exceeding a 512 MiB budget.
        if (
            options.format == "gif"
            and math.ceil(options.fps * options.duration_seconds)
            * options.width_px
            * options.height_px
            * 4
            > 512 * 1024 * 1024
        ):
            raise ValueError("Animation decoded frames exceed 512 MiB.")
        workspace.mkdir(parents=True, exist_ok=True)
        context = multiprocessing.get_context("fork")
        receive, send = context.Pipe(duplex=False)
        worker = context.Process(
            target=_generate,
            args=(
                send,
                self.generators[name],
                {k: v.copy(deep=True) for k, v in tables.items()},
                options,
                workspace,
            ),
        )
        worker.start()
        send.close()
        try:
            if not receive.poll(self.timeout_seconds):
                raise ValueError("Animation generation timed out.")
            try:
                error = receive.recv()
            except EOFError as exc:
                raise ValueError("Animation worker exited without output.") from exc
            if error:
                raise ValueError(error)
            worker.join(timeout=2)
            if worker.is_alive():
                raise ValueError("Animation worker did not exit.")
            return AnimationInput(
                workspace / f"animation.{options.format}", workspace / "poster.png"
            )
        finally:
            if worker.is_alive():
                try:
                    os.killpg(worker.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                worker.kill()
            worker.join()
            receive.close()
