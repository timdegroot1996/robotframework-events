"""Checks step screenshots with real libraries: every suite runs twice, without and with screenshots.

Per suite it checks that the test results are the same, that screenshots were taken and are real
(non-blank) images, and that robotframework-events reported no problems (screenshot.unavailable).
Runs with the current Python; the libraries must be installed (see .github/workflows/libraries.yml).

    python tests/libraries/check.py browser selenium
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = Path(os.environ.get("RESULTS_DIR", HERE / "results"))
PAGES = (HERE / "pages").as_uri()


@dataclass
class Suite:
    name: str
    suite: str
    libraries: list[str]
    min_shots: int = 3
    variables: dict[str, str] = field(default_factory=dict)


SUITES = {
    suite.name: suite
    for suite in [
        Suite("browser", "web_browser.robot", ["Browser"]),
        Suite("selenium", "web_selenium.robot", ["SeleniumLibrary"]),
        Suite("qweb", "web_qweb.robot", ["QWeb"]),
        Suite("puppeteer", "web_puppeteer.robot", ["PuppeteerLibrary"]),
        Suite("rpa-selenium", "rpa_browser_selenium.robot", ["RPA.Browser.Selenium"]),
        Suite("rpa-playwright", "rpa_browser_playwright.robot", ["RPA.Browser.Playwright"]),
        Suite("appium", "mobile_appium.robot", ["AppiumLibrary"]),
        Suite("mobileweb", "mobile_web.robot", ["AppiumLibrary"]),
        Suite("flaui", "desktop_flaui.robot", ["FlaUI"], min_shots=2),
        Suite("white", "desktop_white.robot", ["WhiteLibrary"], min_shots=2),
        Suite("rpa-windows", "rpa_windows.robot", ["RPA.Windows"], min_shots=2),
    ]
}


def robot(suite: Suite, outdir: Path, screenshots: bool) -> None:
    if outdir.exists():
        shutil.rmtree(outdir)
    listener = "robotframework_events.Listener"
    if screenshots:
        listener += f";screenshots=actions;screenshot_libraries={','.join(suite.libraries)}"
    command = [sys.executable, "-m", "robot", "--listener", listener, "--outputdir", str(outdir), "--console", "dotted"]
    for name, value in {"PAGES": PAGES, **suite.variables}.items():
        command += ["--variable", f"{name}:{value}"]
    subprocess.run([*command, str(HERE / "suites" / suite.suite)], check=False)


def statuses(outdir: Path) -> dict[str, str]:
    from robot.api import ExecutionResult

    result = ExecutionResult(str(outdir / "output.xml"))
    return {test.full_name: test.status for test in result.suite.all_tests}


def blank(path: Path) -> bool:
    from PIL import Image, ImageStat

    with Image.open(path) as image:
        return max(ImageStat.Stat(image.convert("L")).stddev) < 2


def check(suite: Suite) -> dict[str, object]:
    plain, shots = RESULTS / suite.name / "plain", RESULTS / suite.name / "shots"
    robot(suite, plain, screenshots=False)
    robot(suite, shots, screenshots=True)
    events_file = shots / "events.jsonl"
    lines = events_file.read_text(encoding="utf-8").splitlines() if events_file.is_file() else []
    events = [json.loads(line) for line in lines if line]
    taken = [e for e in events if e["type"] == "step.screenshot"]
    problems = [f"{e.get('library')}: {e['reason']}" for e in events if e["type"] == "screenshot.unavailable"]
    files = [shots / e["path"] for e in taken]
    blanks = [f.name for f in files if f.is_file() and blank(f)]
    missing = [f.name for f in files if not f.is_file()]
    try:
        before, after = statuses(plain), statuses(shots)
    except Exception as error:  # no output.xml: the run itself broke
        before, after = {"error": str(error)}, {}
    passed = sum(s == "PASS" for s in after.values())
    same = before == after
    ok = same and passed == len(after) > 0 and len(taken) >= suite.min_shots and not missing and not blanks
    ok = ok and not problems
    return {
        "suite": suite.name,
        "ok": ok,
        "tests": f"{passed}/{len(after)} pass",
        "same results": same,
        "screenshots": len(taken),
        "expected": f">= {suite.min_shots}",
        "missing": missing,
        "blank": blanks,
        "problems": problems,
    }


def summary(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Suite | Result | Tests | Same results | Screenshots | Blank | Missing | Problems |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['suite']} | {'OK' if row['ok'] else 'FAIL'} | {row['tests']} | {row['same results']} "
            f"| {row['screenshots']} ({row['expected']}) | {len(row['blank'])} | {len(row['missing'])} "
            f"| {'; '.join(row['problems']) or '-'} |"
        )
    return "\n".join(lines) + "\n"


def main(names: list[str]) -> int:
    unknown = [name for name in names if name not in SUITES]
    if unknown or not names:
        print(f"Name one or more suites of: {', '.join(SUITES)}" + (f" (unknown: {unknown})" if unknown else ""))
        return 2
    rows = [check(SUITES[name]) for name in names]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    table = summary(rows)
    print(table)
    if step_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(step_summary, "a", encoding="utf-8") as file:
            file.write(table)
    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
