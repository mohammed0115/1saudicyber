"""REST API views (/api/v1) — mirrors SRS Appendix D endpoints."""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from rest_framework import status, serializers
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes

from core.models import Company, User
from core.tenancy import TenantScopeError, require_company_for, scoped_queryset
from compliance.models import (
    Control, CompanyControl, Evidence, ControlAssessment, EvidenceSubmission,
)
from monitoring.models import ComplianceScore, Alert
from ai_engine.models import GapAnalysis
from .permissions import VerifiedAccountPermission
from .serializers import (
    RegisterSerializer, ControlSerializer, CompanyControlSerializer,
    EvidenceSerializer, ComplianceScoreSerializer, AlertSerializer,
    GapAnalysisSerializer, CompanySerializer,
    ControlAssessmentSerializer, EvidenceSubmissionSerializer,
)

ALLOWED = lambda: getattr(settings, 'ALLOWED_EVIDENCE_EXTENSIONS', [])
MAXSZ = lambda: getattr(settings, 'MAX_EVIDENCE_FILE_SIZE', 50 * 1024 * 1024)


def _require_company(request):
    """Resolve the active tenant through the central membership boundary."""
    try:
        return require_company_for(request.user)
    except TenantScopeError:
        return None


@extend_schema(summary="تسجيل شركة جديدة + مستخدم مسؤول", request=RegisterSerializer,
               responses={202: OpenApiTypes.OBJECT})
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    s = RegisterSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    with transaction.atomic():
        company = Company.objects.create(
            name=d['company_name'], name_ar=d.get('company_name_ar', ''),
            cr_number=d['cr_number'], sector=d['sector'], size=d['size'],
            contact_email=d['email'],
            target_nca=d['target_nca'], target_aramco=d['target_aramco'], target_sabic=d['target_sabic'],
        )
        user = User.objects.create_user(
            username=d['email'], email=d['email'], password=d['password'],
            first_name=d['first_name'], last_name=d['last_name'],
            company=company, role='company_admin',
        )
        from core.tenant_services import ensure_company_journey, ensure_company_membership
        ensure_company_membership(user, company, role='company_admin')
        ensure_company_journey(company)
    from core.views import _create_company_control_checklist
    _create_company_control_checklist(company)
    from core.services import send_verification_email
    send_verification_email(user)
    return Response({
        'company': CompanySerializer(company).data,
        'detail': 'تم إنشاء الحساب. أكّد البريد الإلكتروني قبل تسجيل الدخول إلى الواجهة البرمجية.',
    }, status=status.HTTP_202_ACCEPTED)


@extend_schema(summary="ضوابط الشركة (قديم — استخدم /assessments/)", deprecated=True,
               parameters=[OpenApiParameter('framework', str, description='رمز الإطار للتصفية (مثل NCA-ECC).')],
               responses=CompanyControlSerializer(many=True))
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def controls(request):
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    qs = scoped_queryset(CompanyControl, company).select_related(
        'control', 'control__framework', 'control__domain')
    fw = request.query_params.get('framework')
    if fw:
        qs = qs.filter(control__framework__code=fw)
    return Response(CompanyControlSerializer(qs, many=True).data)


@extend_schema(summary="تفاصيل ضابط رسمي", responses=ControlSerializer)
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def control_detail(request, control_id):
    try:
        control = Control.objects.select_related('framework', 'domain').get(id=control_id)
    except Control.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    return Response(ControlSerializer(control).data)


@extend_schema(summary="تقييمات الضوابط (قرار المدقّق النهائي — حديث)",
               parameters=[OpenApiParameter('framework', str, description='رمز الإطار للتصفية.'),
                           OpenApiParameter('status', str, description='تصفية بالحالة (compliant/non_compliant/…).')],
               responses=ControlAssessmentSerializer(many=True))
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def assessments(request):
    """Phase 3G — the auditor's final ControlAssessment per official control (tenant-scoped).
    Modern replacement for the legacy `controls` (CompanyControl) endpoint."""
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    qs = scoped_queryset(ControlAssessment, company).select_related(
        'control', 'control__framework')
    fw = request.query_params.get('framework')
    if fw:
        qs = qs.filter(control__framework__code=fw)
    st = request.query_params.get('status')
    if st:
        qs = qs.filter(status=st)
    return Response(ControlAssessmentSerializer(qs, many=True).data)


@extend_schema(summary="أدلة الشركة (upload v2 — حديث)",
               parameters=[OpenApiParameter('status', str, description='تصفية بالحالة (accepted/pending_review/…).')],
               responses=EvidenceSubmissionSerializer(many=True))
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def evidence_submissions(request):
    """Upload-v2 EvidenceSubmission list (tenant-scoped). Modern replacement for the
    legacy Evidence view."""
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    qs = scoped_queryset(EvidenceSubmission, company)
    st = request.query_params.get('status')
    if st:
        qs = qs.filter(status=st)
    return Response(EvidenceSubmissionSerializer(qs, many=True).data)


@extend_schema(summary="تصنيف الشركة (استشاري)", request=None, responses=OpenApiTypes.OBJECT)
@api_view(['POST'])
@permission_classes([VerifiedAccountPermission])
def classify(request):
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    from ai_engine.services import classify_company
    result = classify_company({
        'name': company.name, 'sector': company.get_sector_display(),
        'size': company.get_size_display(), 'target_aramco': company.target_aramco,
        'target_sabic': company.target_sabic, 'target_nca': company.target_nca,
    })
    if 'error' not in result:
        company.risk_level = result.get('risk_level', 'medium')
        company.classification_summary = result.get('summary_en', '')
        company.status = 'classified'
        company.classification_date = timezone.now()
        company.save()
    return Response(result)


@extend_schema(summary="رفع دليل لضابط", request=inline_serializer(
                   'EvidenceUploadRequest',
                   {'control_id': serializers.IntegerField(), 'evidence_file': serializers.FileField()}),
               responses={201: OpenApiTypes.OBJECT})
@api_view(['POST'])
@permission_classes([VerifiedAccountPermission])
@parser_classes([MultiPartParser, FormParser])
def evidence_upload(request):
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    control_id = request.data.get('control_id')
    f = request.FILES.get('evidence_file')
    if not control_id or not f:
        return Response({'detail': 'control_id and evidence_file are required.'}, status=400)
    try:
        control = Control.objects.get(id=control_id)
    except Control.DoesNotExist:
        return Response({'detail': 'Control not found.'}, status=404)

    # Size cap first (cheap), then magic-byte validation — parity with the web upload paths.
    # Extension + size alone lets a spoofed file through; validate_evidence_file sniffs the
    # real content type so a renamed executable/HTML cannot masquerade as allowed evidence.
    if f.size > MAXSZ():
        return Response({'detail': 'File too large.'}, status=400)
    from compliance.upload_validation import validate_evidence_file
    ok, ext, err = validate_evidence_file(f, ALLOWED())
    if not ok:
        return Response({'detail': err or f'Unsupported type .{ext}.'}, status=400)

    cc, _ = CompanyControl.objects.get_or_create(company=company, control=control)
    # A storage failure (e.g. MEDIA_ROOT not writable) must NOT surface as a 500 with a
    # server path — return a clean 503 instead.
    try:
        evidence = Evidence.objects.create(
            company_control=cc, uploaded_by=request.user, file=f,
            original_filename=f.name, file_type=ext, file_size=f.size, status='processing',
        )
    except (OSError, IOError):
        return Response({'detail': 'Evidence storage is temporarily unavailable.'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)
    from compliance.services import process_evidence_pipeline
    # Only touch the broker when async is explicitly enabled (worker provisioned).
    # Otherwise process synchronously — no broker connection attempt, no hang.
    queued = False
    if getattr(settings, 'EVIDENCE_ASYNC_ENABLED', False):
        try:
            from monitoring.tasks import analyze_evidence_async
            analyze_evidence_async.delay(evidence.id, expected_company_id=company.id)
            queued = True
        except Exception:
            process_evidence_pipeline(evidence.id, expected_company_id=company.id)
    else:
        process_evidence_pipeline(evidence.id)
    evidence.refresh_from_db()
    return Response({'evidence': EvidenceSerializer(evidence).data, 'queued': queued},
                    status=status.HTTP_201_CREATED)


@extend_schema(summary="تشغيل تحليل دليل", request=None, responses=OpenApiTypes.OBJECT)
@api_view(['POST'])
@permission_classes([VerifiedAccountPermission])
def evidence_analyze(request, evidence_id):
    from compliance.services import process_evidence_pipeline
    # TENANT ISOLATION: IsAuthenticated only proves login, NOT ownership. Without this
    # scope any authenticated user could analyze (and read the result of) another
    # company's evidence via its id — a cross-tenant IDOR / data leak.
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    if not Evidence.objects.filter(id=evidence_id, company_control__company=company).exists():
        return Response({'detail': 'Evidence not found.'}, status=status.HTTP_404_NOT_FOUND)
    result = process_evidence_pipeline(evidence_id, expected_company_id=company.id)
    return Response(result)


@extend_schema(summary="أحدث تحليل فجوات لكل إطار", responses=GapAnalysisSerializer(many=True))
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def gap_analysis(request):
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    latest = (scoped_queryset(GapAnalysis, company)
              .order_by('framework_code', '-generated_at'))
    seen, rows = set(), []
    for g in latest:
        if g.framework_code not in seen:
            seen.add(g.framework_code)
            rows.append(g)
    return Response(GapAnalysisSerializer(rows, many=True).data)


@extend_schema(summary="لوحة تنفيذية (شركة + تنبيهات + نقاط)", responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def dashboard_executive(request):
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    return Response({
        'company': CompanySerializer(company).data,
        'open_alerts': scoped_queryset(Alert, company).filter(is_resolved=False).count(),
        'critical_alerts': scoped_queryset(Alert, company).filter(is_resolved=False, severity='critical').count(),
        'scores': ComplianceScoreSerializer(
            scoped_queryset(ComplianceScore, company).order_by('-date')[:30], many=True).data,
    })


@extend_schema(summary="توزيع حالة الضوابط", responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def dashboard_compliance(request):
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    qs = CompanyControl.objects.filter(company=company)
    by_status = {}
    for row in qs.values('status'):
        by_status[row['status']] = by_status.get(row['status'], 0) + 1
    return Response({'company': CompanySerializer(company).data, 'status_breakdown': by_status,
                     'total_controls': qs.count()})


@extend_schema(summary="سلسلة نقاط الامتثال (آخر 90)", responses=ComplianceScoreSerializer(many=True))
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def monitoring_scores(request):
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    qs = scoped_queryset(ComplianceScore, company).order_by('-date')[:90]
    return Response(ComplianceScoreSerializer(qs, many=True).data)


@extend_schema(summary="تنبيهات المراقبة (آخر 100)", responses=AlertSerializer(many=True))
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def monitoring_alerts(request):
    company = _require_company(request)
    if not company:
        return Response({'detail': 'No company associated.'}, status=400)
    qs = scoped_queryset(Alert, company).order_by('-created_at')[:100]
    return Response(AlertSerializer(qs, many=True).data)


@extend_schema(summary="تكليفات المدقّق (قديم — نموذج Assessment)", deprecated=True,
               responses=OpenApiTypes.OBJECT)
@api_view(['GET'])
@permission_classes([VerifiedAccountPermission])
def auditor_assignments(request):
    if request.user.role != 'auditor':
        return Response({'detail': 'Auditor role required.'}, status=403)
    from compliance.models import Assessment
    qs = Assessment.objects.filter(assigned_auditor=request.user)
    return Response([{'id': a.id, 'company': a.company.name, 'status': a.status} for a in qs])
