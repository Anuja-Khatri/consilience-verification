import sys
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPRINT / "logic"))
sys.path.insert(0, str(SPRINT / "pipeline"))
sys.path.insert(0, str(SPRINT / "pipeline" / "engine_copy" / "pipeline"))
import no_text_channel_test as B5  # noqa


def test_no_text_channel():
    r = B5.run()
    assert r["verdict_invariant"] is True       # text injection does not change the verdict
    assert r["sentinel_in_output"] is False      # sentinel never reaches outputs
    assert r["p5_reads_free_text"] is False       # p5 reads only typed fields (grep-proof)
    assert r["judge_text_channel"] == 0
