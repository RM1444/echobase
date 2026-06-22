"""Word Error Rate + command recognition over the reading-passage corpus
(thesis section 1.1).

``compute_corpus_wer`` takes any ``transcribe_fn(wav_path) -> str`` so it can be
driven by the real faster-whisper model (realmodel tests) or by a stub (unit
tests). For each passage it computes:

* WER vs the reference transcript;
* command recognition rate -- the fraction of the passage's embedded command
  phrases that survive transcription (appear as a normalised substring of the
  hypothesis). This is the STT-side complement to the router-side accuracy
  measured in test_command_routing.

CLI (loads the real model for the configured recognition profile):
    ECHOBASE_VALIDATION_REAL=1 python -m validation.harness.wer --profile 2
"""

from __future__ import annotations

from dataclasses import dataclass

from validation.harness import corpus as corpusmod
from validation.harness import metrics


@dataclass
class PassageWER:
    name: str
    wer_pct: float
    ref_words: int
    errors: int
    n_commands: int
    commands_recognized: int

    @property
    def command_recognition_rate(self) -> float:
        return self.commands_recognized / self.n_commands if self.n_commands else 1.0


def _command_recognized(phrase: str, hypothesis: str) -> bool:
    """A command counts as recognised if its normalised words appear, in order
    and contiguous, within the normalised hypothesis."""
    hyp = metrics.normalize_text(hypothesis)
    needle = metrics.normalize_text(phrase)
    return needle in hyp


def score_passage(passage: corpusmod.Passage, hypothesis: str) -> PassageWER:
    wer = metrics.word_error_rate(passage.reference, hypothesis)
    recognized = sum(_command_recognized(c.phrase, hypothesis) for c in passage.commands)
    return PassageWER(
        name=passage.name,
        wer_pct=wer.wer_pct,
        ref_words=wer.ref_words,
        errors=wer.errors,
        n_commands=len(passage.commands),
        commands_recognized=recognized,
    )


def compute_corpus_wer(passages, transcribe_fn, condition: str = "clean"):
    """Run *transcribe_fn* over every passage with audio; return (rows, summary).

    rows: per-passage dicts (thesis table). summary: corpus-level WER and command
    recognition, weighted by reference words / command counts.
    """
    rows = []
    total_errors = total_words = 0
    total_cmds = total_recognized = 0
    for p in passages:
        if not p.has_audio:
            continue
        hyp = transcribe_fn(str(p.wav))
        s = score_passage(p, hyp)
        rows.append(
            {
                "passage": s.name,
                "condition": condition,
                "wer_pct": s.wer_pct,
                "ref_words": s.ref_words,
                "errors": s.errors,
                "n_commands": s.n_commands,
                "commands_recognized": s.commands_recognized,
                "command_recognition_pct": round(s.command_recognition_rate * 100, 2),
            }
        )
        total_errors += s.errors
        total_words += s.ref_words
        total_cmds += s.n_commands
        total_recognized += s.commands_recognized
    summary = {
        "condition": condition,
        "n_passages": len(rows),
        "corpus_wer_pct": round(100 * total_errors / total_words, 2) if total_words else 0.0,
        "command_recognition_pct": (
            round(100 * total_recognized / total_cmds, 2) if total_cmds else 0.0
        ),
        "total_ref_words": total_words,
        "total_commands": total_cmds,
    }
    return rows, summary


def _main(argv=None) -> int:
    import argparse
    import os

    ap = argparse.ArgumentParser(description="WER over the reading-passage corpus.")
    ap.add_argument("--profile", type=int, default=2, help="recognition profile 1-4")
    args = ap.parse_args(argv)

    if os.environ.get("ECHOBASE_VALIDATION_REAL") != "1":
        print("Set ECHOBASE_VALIDATION_REAL=1 to run real-model WER.")
        return 2

    from validation.harness.whisper_runner import make_transcribe_fn

    passages = corpusmod.passages_with_audio()
    if not passages:
        print("No recorded passages found in corpora/reading_passages/*.clean.wav")
        return 2
    transcribe_fn = make_transcribe_fn(profile=args.profile)
    rows, summary = compute_corpus_wer(passages, transcribe_fn, condition="clean")
    out = metrics.write_report(
        "wer_clean",
        rows,
        summary,
        title="Word Error Rate -- clean condition",
        caption="Section 1.1 -- WER and command recognition over recorded passages.",
    )
    print(f"corpus WER {summary['corpus_wer_pct']}% | "
          f"command recognition {summary['command_recognition_pct']}% | "
          f"report: {out['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
