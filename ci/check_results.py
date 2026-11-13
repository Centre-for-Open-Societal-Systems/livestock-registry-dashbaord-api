"""CI must exercise DB contracts rather than passing with skipped fixtures."""

import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
if not suites or sum(int(s.attrib.get("tests", 0)) for s in suites) == 0:
    raise SystemExit("No tests ran")
if any(int(s.attrib.get(key, 0)) for s in suites for key in ("errors", "failures", "skipped")):
    raise SystemExit("CI requires all reporting and authentication tests; no skips or failures")
print("All reporting and authentication tests executed without skips")
