"""
Populate Arabic helper text (title_ar / description_ar) for official controls.

WHY: The framework control-preview UI is already built to show Arabic on top of
the authoritative English source, but the *_ar fields ship empty, so every
control renders in English for Arabic-speaking users. This command fills those
blanks with a professional MSA translation.

SCOPE & SAFETY:
- Operates ONLY on PUBLIC regulatory control text (NCA/Aramco/SABIC published
  standards) — NOT tenant/company/evidence data. It therefore does not fall
  under the company-data residency guard (external_ai_allowed), which governs
  runtime analysis of customer content.
- Advisory/helper only: the English `title`/`description` remain the official
  source (the template labels the Arabic as helper text, not an official
  translation). This command NEVER touches English fields, control IDs,
  applicability, scope, assessments, or any compliance decision.
- Idempotent & resumable: only fills rows whose target field is blank. Re-runs
  translate whatever is still missing. No schema change (fields already exist).
"""
import json
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from compliance.models import Control

SYSTEM_PROMPT = (
    "أنت مترجم محترف متخصص في الأمن السيبراني والامتثال في المملكة العربية السعودية. "
    "تُترجم عناوين ونصوص الضوابط التنظيمية (NCA ECC/CCC، Aramco SACS، SABIC) إلى "
    "عربية فصحى واضحة ودقيقة يفهمها مسؤولو الامتثال. القواعد: "
    "1) حافظ على المختصرات التقنية كما هي بالإنجليزية (مثل NCA, ECC, CSP, RACI, OT/ICS, SIEM, IAM, MFA, API). "
    "2) حافظ على أرقام الضوابط ورموزها (مثل 1-2-P-1-1) دون تغيير. "
    "3) ترجمة أمينة دون إضافة أو حذف أو تعليق. "
    "4) أعِد النتيجة بصيغة JSON فقط."
)


class Command(BaseCommand):
    help = "Translate official control title/description into Arabic helper fields (title_ar/description_ar)."

    def add_arguments(self, parser):
        parser.add_argument('--framework', default='', help='Only controls whose framework_version.code contains this (e.g. NCA-CCC).')
        parser.add_argument('--limit', type=int, default=0, help='Max controls to process (0 = no limit).')
        parser.add_argument('--batch-size', type=int, default=8, help='Controls per API call.')
        parser.add_argument('--model', default='gpt-4o-mini', help='OpenAI model.')
        parser.add_argument('--sleep', type=float, default=0.5, help='Seconds to pause between batches.')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be translated; make no API calls and save nothing.')
        parser.add_argument('--yes-external', action='store_true',
                            help='Required confirmation: acknowledges this sends PUBLIC regulatory text to OpenAI.')

    def handle(self, *args, **opts):
        key = (getattr(settings, 'OPENAI_API_KEY', '') or '').strip()
        if not key and not opts['dry_run']:
            raise CommandError('OPENAI_API_KEY is not configured; cannot translate.')

        qs = Control.objects.filter(Q(title_ar='') | Q(title_ar__isnull=True)
                                    | Q(description_ar='') | Q(description_ar__isnull=True))
        if opts['framework']:
            qs = qs.filter(framework_version__code__icontains=opts['framework'])
        qs = qs.order_by('framework_version__code', 'control_id')
        if opts['limit']:
            qs = qs[:opts['limit']]

        controls = list(qs)
        total = len(controls)
        self.stdout.write(f'Controls needing Arabic: {total}'
                          + (f" (framework filter: {opts['framework']})" if opts['framework'] else ''))
        if not total:
            self.stdout.write(self.style.SUCCESS('Nothing to translate.'))
            return

        if opts['dry_run']:
            for c in controls[:20]:
                self.stdout.write(f'  [{c.framework_version.code if c.framework_version else "?"}] {c.control_id}: {c.title[:70]}')
            self.stdout.write(self.style.WARNING(f'DRY-RUN: would translate {total} controls in batches of {opts["batch_size"]}. No API calls made.'))
            return

        if not opts['yes_external']:
            raise CommandError('Refusing to run without --yes-external (this sends PUBLIC regulatory control text to OpenAI). '
                               'Re-run with --yes-external to proceed.')

        from ai_engine.services import get_openai_client
        client = get_openai_client()
        model = opts['model']
        bsize = opts['batch_size']
        done = 0
        failed_batches = 0

        for start in range(0, total, bsize):
            batch = controls[start:start + bsize]
            payload = [{'id': c.id, 'control_id': c.control_id,
                        'title': c.title or '', 'description': c.description or ''} for c in batch]
            user_prompt = (
                'ترجم الحقلين title و description لكل عنصر إلى العربية الفصحى. '
                'أعِد JSON بالشكل: {"items":[{"id":<الرقم>,"title_ar":"...","description_ar":"..."}]} '
                'مع نفس قيمة id لكل عنصر.\n\n'
                + json.dumps(payload, ensure_ascii=False)
            )
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{'role': 'system', 'content': SYSTEM_PROMPT},
                              {'role': 'user', 'content': user_prompt}],
                    response_format={'type': 'json_object'},
                    temperature=0.2,
                )
                data = json.loads(resp.choices[0].message.content)
                items = {int(it['id']): it for it in data.get('items', []) if 'id' in it}
            except Exception as e:  # noqa: BLE001 — one bad batch must not abort the run
                failed_batches += 1
                self.stderr.write(self.style.WARNING(f'  batch {start//bsize+1} failed: {str(e)[:120]} — skipping'))
                time.sleep(opts['sleep'])
                continue

            for c in batch:
                it = items.get(c.id)
                if not it:
                    continue
                fields = []
                t_ar = (it.get('title_ar') or '').strip()
                d_ar = (it.get('description_ar') or '').strip()
                if t_ar and not (c.title_ar or '').strip():
                    c.title_ar = t_ar[:500]; fields.append('title_ar')
                if d_ar and not (c.description_ar or '').strip():
                    c.description_ar = d_ar; fields.append('description_ar')
                if fields:
                    c.save(update_fields=fields)
                    done += 1

            self.stdout.write(f'  {min(start+bsize, total)}/{total} processed ({done} saved)')
            time.sleep(opts['sleep'])

        self.stdout.write(self.style.SUCCESS(
            f'Done. Saved Arabic for {done} controls. Failed batches: {failed_batches}.'))
