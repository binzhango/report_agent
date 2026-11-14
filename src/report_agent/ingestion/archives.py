"""Reject oversized Office ZIP containers before an XML/workbook reader opens them."""

from zipfile import BadZipFile, ZipFile

from report_agent.errors import ReportError

MAX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 3000


def validate_members(archive):
    members = archive.infolist()
    if (
        len(members) > MAX_ARCHIVE_ENTRIES
        or sum(member.file_size for member in members) > MAX_EXPANDED_BYTES
    ):
        raise ReportError("Expanded Office archive exceeds the size or entry limit.")


def validate_archive(path):
    try:
        with ZipFile(path) as archive:
            validate_members(archive)
    except BadZipFile as exc:
        raise ReportError("Unreadable Office archive.") from exc
