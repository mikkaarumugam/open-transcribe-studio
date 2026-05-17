from pathlib import Path

from app.mac_dictation.status_writer import write_status


def test_write_status_creates_file_with_one_line(tmp_path: Path):
    target = tmp_path / "status.txt"
    write_status("recording", target)
    assert target.read_text() == "recording\n"


def test_write_status_overwrites_previous_value(tmp_path: Path):
    target = tmp_path / "status.txt"
    write_status("recording", target)
    write_status("transcribing", target)
    assert target.read_text() == "transcribing\n"


def test_write_status_creates_parent_directories(tmp_path: Path):
    target = tmp_path / "nested" / "dir" / "status.txt"
    write_status("idle", target)
    assert target.exists()
    assert target.read_text() == "idle\n"


def test_write_status_swallows_oserror_silently(tmp_path: Path):
    # If the path is unwritable, we must not crash the dictation worker.
    blocked = tmp_path / "file_then_dir.txt"
    blocked.write_text("not a directory")
    write_status("recording", blocked / "child.txt")
