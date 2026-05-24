from __future__ import annotations

import time

from .pipeline import AudioTxtPipeline


def watch(pipeline: AudioTxtPipeline) -> None:
    poll_seconds = float(pipeline.config.data["watch"]["poll_seconds"])
    stop_after_empty_cycles = pipeline.config.data["watch"].get("stop_after_empty_cycles")
    empty_cycles = 0

    while True:
        stats = pipeline.run_once()
        if stats["processed"] == 0 and stats["failed"] == 0 and stats["duplicates"] == 0:
            empty_cycles += 1
        else:
            empty_cycles = 0

        if stop_after_empty_cycles is not None and empty_cycles >= int(stop_after_empty_cycles):
            return
        time.sleep(poll_seconds)
