"""Private-profile LibreOffice process adapter with bounded execution."""

import os
import signal
import subprocess
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from threading import Lock

FILTERS = {
    "docx": "Office Open XML Text",
    "xlsx": "Calc Office Open XML",
    "pptx": "Impress MS PowerPoint 2007 XML",
    "pdf": "writer_pdf_Export",
}


class ConversionError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LibreOfficeConverter:
    executable: str = "soffice"
    timeout_seconds: float = 120
    _version: str | None = field(default=None, init=False, repr=False, compare=False)
    _version_lock: Lock = field(
        default_factory=Lock, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Conversion timeout must be positive.")

    def convert(self, source: Path, fmt: str, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        profile = directory / "profile"
        command = [
            self.executable,
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--headless",
            "--infilter="
            + {
                ".fodt": "OpenDocument Text Flat XML",
                ".fods": "OpenDocument Spreadsheet Flat XML",
                ".fodp": "OpenDocument Presentation Flat XML",
            }[source.suffix],
            "--norestore",
            "--convert-to",
            f"{fmt}:{FILTERS[fmt]}",
            "--outdir",
            str(directory.resolve()),
            str(source.resolve()),
        ]
        log = directory / "conversion.log"
        environment = self._environment(directory)
        version = self._get_version(environment, log)
        (directory / "version.txt").write_text(version)

        try:
            process = subprocess.Popen(
                command,
                cwd=source.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix",
                env=environment,
            )
        except FileNotFoundError as exc:
            raise ConversionError(
                "converter_not_found", f"Converter not found: {self.executable}"
            ) from exc
        try:
            output, _ = process.communicate(timeout=self.timeout_seconds)
        except BaseException as exc:
            self._kill(process)
            if isinstance(exc, KeyboardInterrupt):
                # Cancellation must not block on a pipe inherited by descendants.
                if process.stdout is not None:
                    process.stdout.close()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                raise
            output, _ = process.communicate()
            log.write_bytes(output)
            if isinstance(exc, subprocess.TimeoutExpired):
                raise ConversionError(
                    "converter_timeout", "LibreOffice conversion timed out."
                ) from exc
            raise
        log.write_bytes(output)
        target = directory / f"{source.stem}.{fmt}"
        if process.returncode:
            raise ConversionError(
                "converter_failed", output.decode(errors="replace")[-4000:]
            )
        if not target.is_file() or not target.stat().st_size:
            raise ConversionError(
                "missing_output", "LibreOffice produced no output; see conversion.log."
            )
        return target

    @staticmethod
    def _environment(directory: Path) -> dict[str, str]:
        environment = {
            key: os.environ[key]
            for key in (
                "PATH",
                "LANG",
                "LC_ALL",
                "LC_CTYPE",
                "TZ",
                "SYSTEMROOT",
                "WINDIR",
            )
            if key in os.environ
        }
        for key, name in {
            "XDG_CACHE_HOME": "cache",
            "XDG_CONFIG_HOME": "config",
            "XDG_DATA_HOME": "data",
            "XDG_RUNTIME_DIR": "runtime",
            "TMPDIR": "tmp",
        }.items():
            path = directory.resolve() / name
            path.mkdir(mode=0o700, exist_ok=True)
            environment[key] = str(path)
        return environment

    def _get_version(self, environment: dict[str, str], log: Path) -> str:
        with self._version_lock:
            if self._version is None:
                object.__setattr__(
                    self, "_version", self._probe_version(environment, log)
                )
            return self._version

    def _probe_version(self, environment: dict[str, str], log: Path) -> str:
        try:
            return (
                subprocess.run(
                    [self.executable, "--version"],
                    capture_output=True,
                    timeout=min(10, self.timeout_seconds),
                    check=True,
                    env=environment,
                )
                .stdout.decode(errors="replace")
                .strip()
            )
        except FileNotFoundError as exc:
            raise ConversionError(
                "converter_not_found", f"Converter not found: {self.executable}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            log.write_text("LibreOffice version probe timed out.")
            raise ConversionError(
                "converter_timeout", "LibreOffice version probe timed out."
            ) from exc
        except (subprocess.SubprocessError, OSError) as exc:
            raise ConversionError(
                "converter_failed", f"Cannot probe converter version: {exc}"
            ) from exc

    @staticmethod
    def _kill(process):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
