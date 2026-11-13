"""A green CI run must not hide missing database coverage behind skips."""

import subprocess
import sys
from pathlib import Path

import pytest

CHECK = Path(__file__).parents[1] / "ci/check_results.py"


@pytest.mark.parametrize(
    "tests,skipped,failures,passed", [(3, 0, 0, True), (0, 0, 0, False), (3, 1, 0, False), (3, 0, 1, False)]
)
def test_ci_requires_executed_unskipped_contracts(tmp_path, tests, skipped, failures, passed):
    report = tmp_path / "results.xml"
    report.write_text(
        f'<testsuites><testsuite tests="{tests}" skipped="{skipped}" failures="{failures}" errors="0"/></testsuites>'
    )
    result = subprocess.run([sys.executable, str(CHECK), str(report)], capture_output=True, text=True, check=False)
    assert (result.returncode == 0) is passed
