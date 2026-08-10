"""Phase 8H-B — Commercial Readiness Report PDF export (reportlab).

Reuses build_commercial_readiness_report(company) and renders a simple, stable
A4 PDF mirroring the HTML report sections. Deterministic; no AI, no writes.

Positioning (printed on every PDF): INTERNAL readiness report — NOT an official
certification and NOT a government accreditation; requires human review.

reportlab is already a project dependency (see dashboard/reports.py). Arabic text
is included only as safe negated disclaimers; the structural content is English so
the layout stays stable regardless of glyph shaping.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

GOV_GREEN = colors.HexColor('#1a4731')

DISCLAIMER_EN = ('This is an internal readiness report based on available platform data and '
                 'evidence, deterministic gap analysis, risks, and remediation tasks. It requires '
                 'human review. It is not an official certification and not a government accreditation.')
DISCLAIMER_AR = 'هذا التقرير لا يُعد شهادة امتثال رسمية ولا يمثل اعتمادًا رسميًا أو حكوميًا، ويتطلب مراجعة بشرية.'


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle('H1x', parent=ss['Heading1'], textColor=GOV_GREEN))
    ss.add(ParagraphStyle('H2x', parent=ss['Heading2'], textColor=GOV_GREEN, fontSize=12))
    ss.add(ParagraphStyle('Smallx', parent=ss['Normal'], fontSize=8, textColor=colors.grey))
    ss.add(ParagraphStyle('Disc', parent=ss['Normal'], fontSize=8, textColor=colors.HexColor('#7A5B16')))
    return ss


def _table(rows, ss, col_widths=None):
    t = Table(rows, hAlign='LEFT', colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf3ef')),
        ('TEXTCOLOR', (0, 0), (-1, 0), GOV_GREEN),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d8e1dd')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def build_commercial_readiness_pdf(company):
    """Return the PDF as bytes. Never raises for empty data (safe empty sections)."""
    from .report_engine import build_commercial_readiness_report
    report = build_commercial_readiness_report(company)
    ex = report['executive']
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title='Cyber-5 Internal Readiness Report',
                            author='Get Solution Company',
                            leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    e = []
    e.append(Paragraph('Cyber-5 — Internal Readiness Report', ss['H1x']))
    e.append(Paragraph('%s (CR %s)' % (company.name, company.cr_number), ss['Normal']))
    e.append(Paragraph('Report date: %s' % ex['report_date'].strftime('%Y-%m-%d %H:%M'), ss['Smallx']))
    e.append(Spacer(1, 6))
    e.append(Paragraph(DISCLAIMER_EN, ss['Disc']))
    e.append(Paragraph(DISCLAIMER_AR, ss['Disc']))
    e.append(Spacer(1, 10))

    # Executive summary
    e.append(Paragraph('Executive summary', ss['H2x']))
    c = ex['counts']
    e.append(_table([
        ['Overall readiness', 'Controls assessed', 'Open risks', 'High/Critical', 'Overdue tasks'],
        ['%s%%' % ex['overall_readiness_percent'], str(ex['controls_assessed']),
         str(ex['open_risks']), str(ex['high_critical_risks']), str(ex['overdue_tasks'])],
    ], ss))
    e.append(Spacer(1, 4))
    e.append(_table([
        ['Compliant', 'Partial', 'Missing', 'Needs review', 'Not applicable'],
        [str(c.get('compliant', 0)), str(c.get('partially_compliant', 0)), str(c.get('missing', 0)),
         str(c.get('needs_review', 0)), str(c.get('not_applicable', 0))],
    ], ss))
    e.append(Spacer(1, 6))
    e.append(Paragraph('Recommended next actions:', ss['Normal']))
    for a in report['next_actions']:
        e.append(Paragraph('• %s' % a, ss['Normal']))
    e.append(Spacer(1, 10))

    # Framework readiness
    e.append(Paragraph('Framework readiness', ss['H2x']))
    if report['framework_readiness']:
        rows = [['Framework', 'Readiness', 'Compliant', 'Partial', 'Missing', 'Needs review', 'N/A']]
        for fw in report['framework_readiness']:
            cc = fw['counts']
            rows.append([fw['code'], '%s%%' % fw['readiness_percent'], str(cc['compliant']),
                         str(cc['partially_compliant']), str(cc['missing']),
                         str(cc['needs_review']), str(cc['not_applicable'])])
        e.append(_table(rows, ss))
    else:
        e.append(Paragraph('No approved frameworks yet.', ss['Normal']))
    e.append(Spacer(1, 10))

    # Evidence summary
    ev = report['evidence']
    e.append(Paragraph('Evidence summary', ss['H2x']))
    e.append(_table([
        ['Uploaded', 'Extracted', 'Manual review', 'Failed'],
        [str(ev['uploaded']), str(ev['extracted']), str(ev['manual_review']), str(ev['failed'])],
    ], ss))
    e.append(Spacer(1, 10))

    # Gap summary
    e.append(Paragraph('Gap summary (%d)' % report['gap']['total'], ss['H2x']))
    if report['gap']['rows']:
        rows = [['Control', 'Status']]
        for r in report['gap']['rows'][:40]:
            rows.append([r.control.control_id, r.get_status_display()])
        e.append(_table(rows, ss, col_widths=[90 * mm, 70 * mm]))
    else:
        e.append(Paragraph('No open gaps.', ss['Normal']))
    e.append(Spacer(1, 10))

    # Risk summary
    rk = report['risk']
    e.append(Paragraph('Risk summary', ss['H2x']))
    sv = rk['severity_counts']
    e.append(_table([
        ['Critical', 'High', 'Medium', 'Low', 'Accepted', 'Mitigated'],
        [str(sv['critical']), str(sv['high']), str(sv['medium']), str(sv['low']),
         str(rk['accepted']), str(rk['mitigated'])],
    ], ss))
    if rk['high_critical']:
        e.append(Spacer(1, 4))
        e.append(Paragraph('Open high/critical risks:', ss['Normal']))
        for r in rk['high_critical'][:20]:
            e.append(Paragraph('• %s (%s)' % (r.title, r.get_severity_display()), ss['Normal']))
    e.append(Spacer(1, 10))

    # Remediation plan
    rem = report['remediation']
    e.append(Paragraph('Remediation plan (%d)' % rem['total'], ss['H2x']))
    if rem['tasks']:
        rows = [['Task', 'Priority', 'Status', 'Due', 'Control']]
        for t in rem['tasks'][:40]:
            rows.append([t.title, t.get_priority_display(), t.get_status_display(),
                         t.due_date.strftime('%Y-%m-%d') if t.due_date else '—',
                         t.risk.control.control_id if t.risk and t.risk.control else '—'])
        e.append(_table(rows, ss, col_widths=[60 * mm, 20 * mm, 25 * mm, 25 * mm, 30 * mm]))
    else:
        e.append(Paragraph('No remediation tasks yet.', ss['Normal']))
    e.append(Spacer(1, 12))

    e.append(Paragraph(DISCLAIMER_EN, ss['Disc']))
    doc.build(e)
    return buf.getvalue()
