"""Daily Markdown storage with a hidden aggregate compatibility view."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .sync.atomic import atomic_write_text

if TYPE_CHECKING:
    from .config import Config

_DATE = r"\d{4}-\d{2}-\d{2}"
_DATE_HEADING_RE = re.compile(rf"(?m)^## (?P<date>{_DATE})\s*$")
_DATE_FILE_RE = re.compile(rf"^(?P<date>{_DATE})\.md$")


def daily_enabled(config: Config) -> bool:
    return config.observation_daily_dir is not None


def daily_paths(config: Config) -> list[Path]:
    directory = config.observation_daily_dir
    if directory is None or not directory.exists():
        return []
    return sorted(
        (path for path in directory.iterdir() if path.is_file() and _DATE_FILE_RE.fullmatch(path.name)),
        reverse=True,
    )


def read_daily_observations(config: Config, dates: set[str] | None = None) -> str:
    sections: dict[str, str] = {}
    for path in daily_paths(config):
        date = path.stem
        if dates is not None and date not in dates:
            continue
        sections.update(parse_observation_sections(path.read_text(encoding="utf-8")))
    return render_aggregate(sections)


def write_daily_observations(config: Config, text: str, *, append: bool = False) -> int:
    directory = config.observation_daily_dir
    if directory is None:
        raise RuntimeError("Daily observation storage is not configured.")

    sections = parse_observation_sections(text)
    if not sections:
        raise RuntimeError("Observer response did not contain a '## YYYY-MM-DD' section.")

    directory.mkdir(parents=True, exist_ok=True)
    for date, section in sections.items():
        path = directory / f"{date}.md"
        if append and path.exists():
            existing = parse_observation_sections(path.read_text(encoding="utf-8")).get(date, "")
            if existing and section.strip() not in existing:
                section = existing.rstrip() + "\n\n" + section.lstrip()
            elif existing:
                section = existing
        atomic_write_text(path, render_daily_file(date, section))

    materialize_daily_observations(config)
    return len(sections)


def materialize_daily_observations(config: Config) -> str:
    text = read_daily_observations(config)
    config.ensure_memory_dir()
    atomic_write_text(config.observations_path, text)
    write_daily_index(config)
    return text


def migrate_legacy_observations(config: Config, legacy_path: Path) -> int:
    if not daily_enabled(config):
        raise RuntimeError("Set OM_OBSERVATION_DAILY_DIR before migrating observations.")
    if not legacy_path.is_file():
        return 0
    return write_daily_observations(config, legacy_path.read_text(encoding="utf-8"))


def write_daily_index(config: Config) -> None:
    directory = config.observation_daily_dir
    if directory is None:
        return
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Observation Index",
        "",
        "<!-- Auto-maintained by Observational Memory. -->",
        "",
    ]
    for path in daily_paths(config):
        lines.append(f"- [{path.stem}](<{path.name}>)")
    atomic_write_text(directory / "INDEX.md", "\n".join(lines).rstrip() + "\n")


def parse_observation_sections(text: str) -> dict[str, str]:
    matches = list(_DATE_HEADING_RE.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        date = match.group("date")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[date] = text[match.end() : end].strip()
    return sections


def render_daily_file(date: str, section: str) -> str:
    return f"# Observations\n\n## {date}\n\n{section.strip()}\n"


def render_aggregate(sections: dict[str, str]) -> str:
    parts = ["# Observations"]
    for date in sorted(sections, reverse=True):
        parts.extend(["", f"## {date}", "", sections[date].strip()])
    return "\n".join(parts).rstrip() + "\n"
