"""Loader for the reading-passage corpus (thesis sections 1.1 / 1.4 / 2.4).

Per the validation design, the corpus is a set of English reading passages that
the user records aloud, with command phrases embedded naturally as words. Each
passage is a trio of files under ``validation/corpora/reading_passages/``:

    passage_NN.txt           reference transcript (ground truth for WER)
    passage_NN.clean.wav     the clean recording (mono 16 kHz PCM)
    passage_NN.commands.json  embedded commands + expected routing target

``commands.json`` schema::

    {
      "commands": [
        {"phrase": "open firefox", "expected_plugin": "apps"},
        {"phrase": "scroll down",  "expected_plugin": "scroll"}
      ]
    }

The same recordings double as dictation material (section 2.4). The loader never
requires the .wav to exist (so the suite is usable before recordings are made);
callers skip passages without audio.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpora"
PASSAGES_DIR = CORPUS_DIR / "reading_passages"


@dataclass
class Command:
    phrase: str
    expected_plugin: str


@dataclass
class Passage:
    name: str
    reference: str
    wav: Path | None
    commands: list[Command] = field(default_factory=list)

    @property
    def has_audio(self) -> bool:
        return self.wav is not None and self.wav.exists()


def load_passages(passages_dir: Path | None = None) -> list[Passage]:
    """Load every passage that has at least a reference .txt. Audio/commands are
    optional and attached when present."""
    base = Path(passages_dir) if passages_dir else PASSAGES_DIR
    passages: list[Passage] = []
    if not base.exists():
        return passages
    for txt in sorted(base.glob("*.txt")):
        name = txt.stem
        reference = txt.read_text(encoding="utf-8").strip()
        wav = base / f"{name}.clean.wav"
        cmd_file = base / f"{name}.commands.json"
        commands: list[Command] = []
        if cmd_file.exists():
            data = json.loads(cmd_file.read_text(encoding="utf-8"))
            for item in data.get("commands", []):
                commands.append(
                    Command(
                        phrase=item["phrase"],
                        expected_plugin=item.get("expected_plugin", ""),
                    )
                )
        passages.append(
            Passage(name=name, reference=reference, wav=wav if wav.exists() else None,
                    commands=commands)
        )
    return passages


def passages_with_audio(passages_dir: Path | None = None) -> list[Passage]:
    return [p for p in load_passages(passages_dir) if p.has_audio]
