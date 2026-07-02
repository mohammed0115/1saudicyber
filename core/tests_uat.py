"""Phase 8J-A — Final commercial QA / UAT hardening: durable filesystem scanners.

These tests read the template files directly (not just rendered public pages) so any
future template that introduces an affirmative certification/accreditation claim, or
leaks a Moyasar secret / card field, fails CI immediately. They are intentionally
negation-aware: the safe negated disclaimers the product uses everywhere are allowed.
"""
import os

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = str(settings.TEMPLATES[0]['DIRS'][0])


def _iter_templates():
    for root, _dirs, files in os.walk(TEMPLATES_DIR):
        for fn in files:
            if fn.endswith('.html'):
                path = os.path.join(root, fn)
                with open(path, encoding='utf-8') as fh:
                    yield os.path.relpath(path, TEMPLATES_DIR), fh.read()


# Negation tokens that make an otherwise-affirmative phrase safe.
_NEG_EN = ('not ', 'never ', 'no ', "n't")
_NEG_AR = ('لا ', 'ليس', 'ولا', 'دون ', 'لاُ', 'لاّ')


def _every_occurrence_negated(text, phrase, neg_tokens, window=70):
    """True iff every occurrence of `phrase` has a negation token within `window`
    characters before it. Empty (no occurrences) is vacuously True."""
    start = 0
    while True:
        idx = text.find(phrase, start)
        if idx == -1:
            return True
        pre = text[max(0, idx - window):idx]
        if not any(tok in pre for tok in neg_tokens):
            return False
        start = idx + len(phrase)


class TemplateWordingScanTests(SimpleTestCase):
    """No affirmative certification/accreditation claims anywhere in templates."""

    # Phrases that have NO legitimate negated substring — must never appear at all.
    HARD_BANNED = (
        'certified by NCA', 'certified by Aramco', 'certified by SABIC',
        'government accredited', 'officially certified', 'officially accredited',
        'معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك',
        'اعتماد حكومي رسمي', 'شهادة رسمية معتمدة',
    )
    # Phrases that DO occur inside safe negated disclaimers — allowed only when negated.
    NEG_REQUIRED_EN = ('official certification', 'official accreditation')
    NEG_REQUIRED_AR = ('شهادة امتثال رسمية', 'اعتمادًا رسميًا', 'اعتماد رسمي', 'اعتمادًا حكوميًا')

    def test_no_hard_banned_wording_in_any_template(self):
        for name, body in _iter_templates():
            low = body.lower()
            for bad in self.HARD_BANNED:
                self.assertNotIn(bad.lower(), low, f'hard-banned "{bad}" found in {name}')

    def test_affirmative_english_claims_are_negated(self):
        for name, body in _iter_templates():
            low = body.lower()
            for phrase in self.NEG_REQUIRED_EN:
                self.assertTrue(
                    _every_occurrence_negated(low, phrase, _NEG_EN),
                    f'affirmative "{phrase}" (not negated) found in {name}')

    def test_affirmative_arabic_claims_are_negated(self):
        for name, body in _iter_templates():
            for phrase in self.NEG_REQUIRED_AR:
                self.assertTrue(
                    _every_occurrence_negated(body, phrase, _NEG_AR),
                    f'affirmative "{phrase}" (not negated) found in {name}')


class TemplateSecretAndCardScanTests(SimpleTestCase):
    """No Moyasar secret key or card-data patterns in any template file."""

    SECRET_PATTERNS = ('sk_test_', 'sk_live_', 'MOYASAR_SECRET', 'secret_api_key',
                       'secret_key', 'MOYASAR_WEBHOOK_SECRET')
    # Live publishable keys must not be hard-coded either (sandbox uses pk_test_ via context).
    LIVE_KEY_PATTERNS = ('pk_live_',)
    CARD_PATTERNS = ('card_number', 'cardholder', 'card_holder', 'cvv', 'cvc',
                     'card-number', 'data-card')

    def test_no_secret_in_templates(self):
        for name, body in _iter_templates():
            for pat in self.SECRET_PATTERNS:
                self.assertNotIn(pat, body, f'secret pattern "{pat}" in {name}')

    def test_no_hardcoded_live_key_in_templates(self):
        for name, body in _iter_templates():
            for pat in self.LIVE_KEY_PATTERNS:
                self.assertNotIn(pat, body, f'live key "{pat}" in {name}')

    def test_no_card_fields_in_templates(self):
        for name, body in _iter_templates():
            low = body.lower()
            for pat in self.CARD_PATTERNS:
                self.assertNotIn(pat, low, f'card pattern "{pat}" in {name}')
