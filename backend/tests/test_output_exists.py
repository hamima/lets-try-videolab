"""
backend/tests/test_output_exists.py — Regression test for _output_exists()
and the step-17 ("Final Assembly") output path.

_output_exists() used to special-case any "output/"-prefixed step output as
BASE_DIR-relative (a single path shared across every run), rather than
workspace-relative like every other step. That meant any run's step 17 would
report "done" the moment *any* run anywhere had ever produced
output/final_video.mp4, regardless of whether that specific run had actually
assembled its own video. Locks in the fix: step 17's output must be resolved
relative to the run's own workspace.
"""

import tasks


def test_output_exists_is_workspace_scoped_for_output_prefixed_steps(tmp_path):
    step = tasks.STEPS_BY_ID["17"]
    assert step["output"] == "output/final_video.mp4"

    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir()
    run_b.mkdir()

    # Only run_a has actually assembled its video.
    (run_a / "output").mkdir()
    (run_a / "output" / "final_video.mp4").write_bytes(b"fake video")

    assert tasks._output_exists(step, run_a) is True
    assert tasks._output_exists(step, run_b) is False
