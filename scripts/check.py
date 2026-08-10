#!/usr/bin/env python
"""Tiered "smart" checks for Cyber-5.

Three layers, cheapest first, so you only pay for the confidence you need:

  guard    Fast, must-pass gate (no test DB, ~seconds). Catches project-breaking
           issues before they land: Django system check, missing-migration drift,
           a template lint for multi-line ``{# #}`` comments (which Django renders
           as visible text), and a full template compile pass (real ``{% %}`` syntax
           / bad ``{% load %}`` errors).
  changed  Runs ONLY the tests for the apps your working tree touches (git diff vs a
           base, default HEAD, plus untracked files). Shared templates (base.html /
           auth_base.html) expand to the core render set. This is the everyday check.
  full     The complete test suite.
  all      guard -> changed -> full, stopping at the first failure.

Usage:
  ./.venv/bin/python scripts/check.py [guard|changed|full|all] [base-ref]
  scripts/check.sh   [guard|changed|full|all] [base-ref]     # picks the venv for you

Examples:
  scripts/check.sh guard              # is the project still coherent? (seconds)
  scripts/check.sh changed            # test what I changed since my last commit
  scripts/check.sh changed origin/main   # test everything on this branch
  scripts/check.sh full               # the whole suite
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))  # so in-process django.setup() finds cybertrust_ksa.settings

# ── local Django apps that own a test suite (label == top-level dir) ──
APPS_WITH_TESTS = [
    "ai_engine", "api", "auditor_portal", "auditors", "billing",
    "compliance", "core", "dashboard", "monitoring", "risk",
]
# templates/<dir>/ that don't map 1:1 to an app label
TEMPLATE_DIR_TO_APPS = {
    "onboarding": ["core"],          # onboarding views live in core
    "platform_admin": ["core"],      # best-effort; platform_admin is served under core
}
# a change here re-renders the shell for every screen -> test the busy render paths
SHARED_TEMPLATES = {"templates/base.html", "templates/onboarding/auth_base.html"}
CORE_SET = ["core", "compliance", "dashboard"]
# path prefixes that never affect test outcomes -> ignored for test selection
IGNORE_PREFIXES = ("docs/", "static/", "staticfiles/", "locale/", "media/",
                   "private_media/", "node_modules/", "scripts/", "سيناريو/")
IGNORE_SUFFIXES = (".md", ".css", ".js", ".po", ".mo", ".json", ".lock", ".txt", ".cfg")

C = sys.stdout.isatty()
def c(s, code):  return f"\033[{code}m{s}\033[0m" if C else s
def green(s):    return c(s, "32")
def red(s):      return c(s, "31")
def yellow(s):   return c(s, "33")
def bold(s):     return c(s, "1")


def run(cmd, label):
    """Run a subcommand, streaming output; return True on success."""
    print(bold(f"▶ {label}"))
    print(f"  $ {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    ok = rc == 0
    print((green("  ✓ نجح") if ok else red(f"  ✗ فشل (رمز {rc})")) + f"  — {label}\n")
    return ok


def manage(*args):
    return [sys.executable, "manage.py", *args]


# ───────────────────────────── template lint ─────────────────────────────
_OPEN = re.compile(r"\{#")
_CLOSE = re.compile(r"#\}")

def _template_files():
    seen = set()
    for pat in ("templates/**/*.html", "*/templates/**/*.html"):
        for f in ROOT.glob(pat):
            if f.is_file():
                seen.add(f)
    return sorted(seen)


def lint_multiline_comments():
    """Flag ``{#`` that isn't closed by ``#}`` on the SAME line.

    Django template comments are single-line only; a multi-line ``{# … #}`` is not
    a comment — its text renders verbatim into the page (the exact bug that leaked
    onto the classification screen). Use ``{% comment %}…{% endcomment %}`` instead.
    """
    print(bold("▶ template lint — multi-line {# #} comments"))
    offenders = []
    for f in _template_files():
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(lines, 1):
            opens = [m.start() for m in _OPEN.finditer(line)]
            if not opens:
                continue
            # every {# must be followed by a #} later on the same line
            for pos in opens:
                if not _CLOSE.search(line, pos):
                    offenders.append((f.relative_to(ROOT), i, line.strip()[:80]))
                    break
    if offenders:
        for path, ln, txt in offenders:
            print(red(f"  ✗ {path}:{ln}: ") + txt)
        print(red(f"  ✗ فشل — {len(offenders)} تعليق(ات) متعددة الأسطر تتسرّب كنصّ. "
                  "استخدم {% comment %}…{% endcomment %}.\n"))
        return False
    print(green("  ✓ نجح") + "  — لا تعليقات متسرّبة\n")
    return True


def compile_templates():
    """Compile every template through the Django engine to catch syntax / load errors."""
    print(bold("▶ template compile — {% %} syntax & {% load %}"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cybertrust_ksa.settings")
    try:
        import django
        django.setup()
        from django.template import engines, TemplateSyntaxError
    except Exception as exc:  # pragma: no cover - environment/setup failure
        print(red(f"  ✗ تعذّر تهيئة Django: {exc}\n"))
        return False
    dj = engines["django"]
    errors = []
    for f in _template_files():
        try:
            dj.from_string(f.read_text(encoding="utf-8"))
        except TemplateSyntaxError as exc:
            errors.append((f.relative_to(ROOT), str(exc)))
        except (UnicodeDecodeError, OSError):
            continue
    if errors:
        for path, msg in errors:
            print(red(f"  ✗ {path}: ") + msg.splitlines()[0][:120])
        print(red(f"  ✗ فشل — {len(errors)} قالب(قوالب) بها أخطاء بناء\n"))
        return False
    print(green("  ✓ نجح") + "  — كل القوالب تُترجم\n")
    return True


# ───────────────────────────── changed detection ─────────────────────────────
def changed_files(base="HEAD"):
    """Working-tree changes vs `base`, plus untracked files."""
    files = set()
    tracked = subprocess.run(["git", "diff", "--name-only", base],
                             capture_output=True, text=True)
    files.update(l for l in tracked.stdout.splitlines() if l.strip())
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                               capture_output=True, text=True)
    files.update(l for l in untracked.stdout.splitlines() if l.strip())
    return sorted(files)


def apps_for_changes(files):
    """Map changed paths -> set of app test labels. Returns (labels, notes)."""
    labels, notes = set(), []
    for path in files:
        if path in SHARED_TEMPLATES:
            labels.update(CORE_SET)
            notes.append(f"shared template {path} → {'+'.join(CORE_SET)}")
            continue
        if path.startswith(IGNORE_PREFIXES) or path.endswith(IGNORE_SUFFIXES):
            continue
        top = path.split("/", 1)[0]
        if path.startswith("templates/"):
            parts = path.split("/")
            tdir = parts[1] if len(parts) > 2 else ""  # templates/<tdir>/file.html
            if tdir in TEMPLATE_DIR_TO_APPS:
                labels.update(TEMPLATE_DIR_TO_APPS[tdir])
            elif tdir in APPS_WITH_TESTS:
                labels.add(tdir)
            elif tdir == "components":
                labels.update(CORE_SET)
                notes.append("shared components/ → core set")
            else:
                notes.append(f"unmapped template dir '{tdir}' ({path}) — skipped")
            continue
        if top in APPS_WITH_TESTS:
            labels.add(top)
    return sorted(labels), notes


# ───────────────────────────── tiers ─────────────────────────────
def guard():
    print(bold("\n══ فحص الحماية (يمنع كسر المشروع) ══\n"))
    ok = True
    ok &= run(manage("check"), "manage.py check — فحص النظام والمسارات")
    ok &= run(manage("makemigrations", "--check", "--dry-run"),
              "makemigrations --check — لا هجرات ناقصة")
    ok &= lint_multiline_comments()
    ok &= compile_templates()
    return ok


def changed(base="HEAD"):
    print(bold(f"\n══ فحص التعديلات الجديدة فقط (مقابل {base}) ══\n"))
    files = changed_files(base)
    if not files:
        print(yellow("لا تغييرات في شجرة العمل — لا شيء لفحصه.\n"))
        return True
    labels, notes = apps_for_changes(files)
    print("ملفات متغيّرة: " + str(len(files)))
    for n in notes:
        print(yellow(f"  · {n}"))
    if not labels:
        print(yellow("لا تطبيقات لها اختبارات تتأثّر بهذه التغييرات (توثيق/أصول فقط). "
                     "شغّل فحص الحماية للتأكد من السلامة.\n"))
        return True
    print(bold("التطبيقات المتأثّرة: ") + ", ".join(labels) + "\n")
    return run(manage("test", *labels, "-v1"),
               f"tests: {' '.join(labels)}")


def full():
    print(bold("\n══ الفحص الشامل ══\n"))
    return run(manage("test", "-v1"), "الفحص الشامل (كل الاختبارات)")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "guard"
    base = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    t0 = time.time()

    if mode == "guard":
        ok = guard()
    elif mode == "changed":
        ok = changed(base)
    elif mode == "full":
        ok = full()
    elif mode == "all":
        ok = guard() and changed(base) and full()
    else:
        print(red(f"وضع غير معروف: {mode}"))
        print(__doc__)
        return 2

    dt = time.time() - t0
    print(bold("─" * 48))
    print((green("✓ اجتاز الفحص") if ok else red("✗ رصد الفحص مشاكل")) +
          f"  [{mode}]  ({dt:.1f}s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
