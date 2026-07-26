// 1SaudiCyber — Alpine.js shared data & utilities
// All pages include this file via <script defer src="../assets/js/app.js">

document.addEventListener('alpine:init', () => {

  // ── Scroll shadow on topbar ──────────────────────────────────────────────
  Alpine.data('topbar', () => ({
    scrolled: false,
    mobileOpen: false,
    init() {
      window.addEventListener('scroll', () => {
        this.scrolled = window.scrollY > 10;
      }, { passive: true });
    }
  }));

  // ── Landing page hero dashboard demo ────────────────────────────────────
  Alpine.data('heroDash', () => ({
    activeNav: 'overview',
    frameworks: [
      { name: 'NCA ECC',        pct: 81 },
      { name: 'Aramco SACS-002', pct: 74 },
      { name: 'SABIC',           pct: 65 },
      { name: 'ISO 27001',       pct: 60 },
    ],
    gaps: [
      { label: 'ضبط الوصول',       count: 8 },
      { label: 'إدارة الأصول',      count: 6 },
      { label: 'استجابة الحوادث',   count: 4 },
      { label: 'إدارة المخاطر',     count: 3 },
      { label: 'أخرى',             count: 2 },
    ]
  }));

  // ── Registration: account type selection ────────────────────────────────
  Alpine.data('accountType', () => ({
    selected: null,
    select(type) { this.selected = type; },
    proceed() {
      if (!this.selected) return;
      window.location.href = this.selected === 'company'
        ? 'register-company.html'
        : 'register-auditor.html';
    }
  }));

  // ── Registration form (company) ──────────────────────────────────────────
  Alpine.data('registerForm', () => ({
    accountType: 'company',
    fullName: '',
    email: '',
    phone: '',
    password: '',
    confirmPassword: '',
    agreeTerms: false,
    showPass: false,
    showConfirm: false,
    loading: false,
    submit() {
      if (!this.agreeTerms) return;
      this.loading = true;
      setTimeout(() => {
        window.location.href = 'verify-email.html';
      }, 800);
    }
  }));

  // ── Email verification ───────────────────────────────────────────────────
  Alpine.data('emailVerify', () => ({
    countdown: 105,
    canResend: false,
    timer: null,
    init() {
      this.startTimer();
    },
    startTimer() {
      this.timer = setInterval(() => {
        if (this.countdown > 0) {
          this.countdown--;
        } else {
          this.canResend = true;
          clearInterval(this.timer);
        }
      }, 1000);
    },
    get timeDisplay() {
      const m = String(Math.floor(this.countdown / 60)).padStart(2, '0');
      const s = String(this.countdown % 60).padStart(2, '0');
      return `${m}:${s}`;
    },
    resend() {
      if (!this.canResend) return;
      this.countdown = 105;
      this.canResend = false;
      this.startTimer();
    }
  }));

  // ── Company setup form ───────────────────────────────────────────────────
  Alpine.data('companySetup', () => ({
    legalName: 'شركة الحلول الرقمية المتقدمة',
    tradeName: 'الحلول المتقدمة لتقنية المعلومات',
    crNumber: '1010234567',
    crDate: '2015-06-15',
    sector: 'تقنية المعلومات والاتصالات',
    size: 'متوسطة (50 - 59 موظف)',
    city: 'الرياض',
    hasSensitive: true,
    officialEmail: 'info@company.com',
    phone: '50 123 4567',
    saving: false,
    save() {
      this.saving = true;
      setTimeout(() => { this.saving = false; }, 1200);
    }
  }));

  // ── Compliance scope wizard ──────────────────────────────────────────────
  Alpine.data('scopeWizard', () => ({
    step: 1,
    totalSteps: 6,
    entityType: 'private',
    sector: '',
    activities: [],
    size: '',
    regulatoryBodies: ['NCA'],
    hasContractual: true,
    techScope: [],
    cloudUsed: false,
    suggestedFrameworks: ['NCA ECC', 'Aramco SACS-002'],
    activityOptions: [
      'تقنية المعلومات والخدمات الرقمية','التصنيع','الطاقة والمرافق',
      'النفط والغاز والبتروكيماويات','الخدمات المالية','الرعاية الصحية',
      'التعليم','التجارة الإلكترونية والتجزئة','النقل والخدمات اللوجستية',
      'الاستشارات والخدمات المهنية','الاتصالات','أخرى'
    ],
    sizeOptions: ['أقل من 50','من 50 إلى 249','من 250 إلى 999','من 1,000 إلى 4,999','5,000 أو أكثر'],
    regulatoryOptions: [
      'الهيئة الوطنية للأمن السيبراني (NCA)',
      'هيئة الاتصالات والفضاء والتقنية (CST)',
      'وزارة الداخلية','وزارة الدفاع',
      'هيئة الزكاة والضريبة والجمارك (ZATCA)',
      'وزارة الطاقة','أخرى'
    ],
    toggleActivity(a) {
      const i = this.activities.indexOf(a);
      i === -1 ? this.activities.push(a) : this.activities.splice(i, 1);
    },
    toggleRegulatory(r) {
      const i = this.regulatoryBodies.indexOf(r);
      i === -1 ? this.regulatoryBodies.push(r) : this.regulatoryBodies.splice(i, 1);
    },
    next() { if (this.step < this.totalSteps) this.step++; },
    prev() { if (this.step > 1) this.step--; },
    get progress() { return Math.round((this.step / this.totalSteps) * 100); }
  }));

  // ── Company Dashboard ────────────────────────────────────────────────────
  Alpine.data('companyDash', () => ({
    activeSection: 'overview',
    sections: [
      { id: 'overview',    label: 'نظرة عامة',      icon: 'grid' },
      { id: 'assessments', label: 'التقييمات',       icon: 'clipboard' },
      { id: 'controls',    label: 'الضوابط',         icon: 'shield' },
      { id: 'evidence',    label: 'الأدلة',           icon: 'folder' },
      { id: 'gaps',        label: 'الفجوات',          icon: 'alert-triangle' },
      { id: 'risks',       label: 'المخاطر',          icon: 'alert-circle' },
      { id: 'remediation', label: 'المعالجة',         icon: 'tool' },
      { id: 'audit',       label: 'التدقيق',          icon: 'search' },
      { id: 'monitoring',  label: 'المراقبة',         icon: 'activity' },
      { id: 'reports',     label: 'التقارير',         icon: 'file-text' },
      { id: 'settings',    label: 'الإعدادات',        icon: 'settings' },
    ],
    kpis: [
      { label: 'الأدلة',             value: '1,254', trend: '+15%', up: true },
      { label: 'الإجراءات المفتوحة', value: '48',    trend: '↓ 8',  up: false },
      { label: 'الفجوات الحرجة',     value: '23',    trend: '↓ 5',  up: false },
      { label: 'مؤشر الجاهزية',      value: '78%',   trend: '+12%', up: true },
    ],
    frameworks: [
      { name: 'NCA ECC',         pct: 81 },
      { name: 'Aramco SACS-002', pct: 74 },
      { name: 'SABIC',           pct: 65 },
      { name: 'ISO 27001',       pct: 60 },
    ],
    navigate(id) { this.activeSection = id; }
  }));

  // ── Controls list ────────────────────────────────────────────────────────
  Alpine.data('controlsList', () => ({
    search: '',
    filter: 'all',
    controls: [
      { id: 'ECC-1-1', name: 'سياسة الأمن السيبراني',        status: 'complete',  evidence: 3, framework: 'NCA ECC' },
      { id: 'ECC-1-2', name: 'أدوار ومسؤوليات الأمن',        status: 'partial',   evidence: 2, framework: 'NCA ECC' },
      { id: 'ECC-2-1', name: 'إدارة الأصول',                  status: 'gap',       evidence: 0, framework: 'NCA ECC' },
      { id: 'ECC-2-2', name: 'تصنيف المعلومات',               status: 'complete',  evidence: 4, framework: 'NCA ECC' },
      { id: 'ECC-3-1', name: 'ضبط الوصول',                   status: 'gap',       evidence: 1, framework: 'NCA ECC' },
      { id: 'ECC-3-2', name: 'إدارة الهويات والصلاحيات',      status: 'partial',   evidence: 2, framework: 'NCA ECC' },
      { id: 'ECC-4-1', name: 'أمن الشبكات',                  status: 'complete',  evidence: 5, framework: 'NCA ECC' },
      { id: 'ECC-5-1', name: 'الاستجابة للحوادث',             status: 'gap',       evidence: 0, framework: 'NCA ECC' },
      { id: 'SACS-1-1','name': 'متطلبات الموردين',            status: 'partial',   evidence: 1, framework: 'Aramco SACS-002' },
      { id: 'SACS-2-1','name': 'تقييم المخاطر',               status: 'complete',  evidence: 3, framework: 'Aramco SACS-002' },
    ],
    get filtered() {
      return this.controls.filter(c => {
        const matchSearch = !this.search || c.name.includes(this.search) || c.id.includes(this.search);
        const matchFilter = this.filter === 'all' || c.status === this.filter;
        return matchSearch && matchFilter;
      });
    },
    statusLabel(s) {
      return { complete: 'مكتمل', partial: 'جزئي', gap: 'فجوة' }[s] || s;
    },
    statusClass(s) {
      return {
        complete: 'badge-green',
        partial:  'badge-gold',
        gap:      'badge-red',
      }[s] || '';
    }
  }));

  // ── Evidence upload ──────────────────────────────────────────────────────
  Alpine.data('evidenceUpload', () => ({
    files: [],
    dragging: false,
    analyzing: false,
    aiResult: null,
    handleDrop(e) {
      this.dragging = false;
      const dropped = Array.from(e.dataTransfer.files);
      this.addFiles(dropped);
    },
    addFiles(newFiles) {
      newFiles.forEach(f => {
        this.files.push({ name: f.name, size: f.size, status: 'pending' });
      });
    },
    analyze() {
      this.analyzing = true;
      setTimeout(() => {
        this.analyzing = false;
        this.aiResult = {
          score: 87,
          summary: 'الأدلة المرفوعة تدعم الامتثال بشكل جيد. يُنصح بإضافة سياسة مكتوبة موقّعة.',
          recommendations: [
            'أضف وثيقة سياسة ضبط الوصول الموقّعة',
            'أرفق سجل مراجعة الصلاحيات الأخير',
          ]
        };
      }, 2000);
    }
  }));

  // ── RFI (Company side) ───────────────────────────────────────────────────
  Alpine.data('rfiList', () => ({
    activeRfi: null,
    rfis: [
      {
        id: 'RFI-001', control: 'ECC-3-1 ضبط الوصول',
        auditor: 'م. سعد العتيبي', date: '2026-07-20',
        status: 'open',
        question: 'يرجى تقديم سجل مراجعة الصلاحيات لآخر ربع سنة مع توقيع المسؤول.',
        response: '', files: []
      },
      {
        id: 'RFI-002', control: 'ECC-5-1 الاستجابة للحوادث',
        auditor: 'م. سعد العتيبي', date: '2026-07-18',
        status: 'closed',
        question: 'هل تم اختبار خطة الاستجابة للحوادث خلال العام الماضي؟',
        response: 'نعم، تم إجراء اختبار محاكاة في مارس 2026. التقرير مرفق.',
        files: ['incident-test-report-2026.pdf']
      },
    ],
    open(rfi) { this.activeRfi = rfi; },
    close() { this.activeRfi = null; },
    submit(rfi) {
      rfi.status = 'responded';
      this.activeRfi = null;
    }
  }));

  // ── Auditor portal ───────────────────────────────────────────────────────
  Alpine.data('auditorPortal', () => ({
    activeSection: 'companies',
    companies: [
      { id: 1, name: 'شركة الحلول الرقمية',   sector: 'تقنية المعلومات', progress: 78, status: 'in_review', controls: 42, done: 33 },
      { id: 2, name: 'مجموعة الطاقة الوطنية', sector: 'الطاقة',          progress: 45, status: 'pending',   controls: 38, done: 17 },
    ],
    selectedCompany: null,
    selectedControl: null,
    verdict: '',
    verdictNote: '',
    rfiText: '',
    showRfiForm: false,
    openCompany(c) { this.selectedCompany = c; this.activeSection = 'controls'; },
    openControl(c) { this.selectedControl = c; this.activeSection = 'control-detail'; },
    submitVerdict() {
      if (!this.verdict) return;
      this.selectedControl.verdict = this.verdict;
      this.activeSection = 'controls';
      this.verdict = '';
      this.verdictNote = '';
    },
    submitRfi() {
      this.showRfiForm = false;
      this.rfiText = '';
    },
    verdictOptions: [
      { value: 'accepted',  label: 'مقبول',              color: 'green' },
      { value: 'partial',   label: 'مقبول جزئيًا',       color: 'gold'  },
      { value: 'rejected',  label: 'مرفوض',              color: 'red'   },
      { value: 'rfi',       label: 'يحتاج معلومات إضافية', color: 'blue' },
    ]
  }));

  // ── Admin platform ───────────────────────────────────────────────────────
  Alpine.data('adminPlatform', () => ({
    activeSection: 'dashboard',
    sections: [
      { id: 'dashboard',    label: 'لوحة التحكم' },
      { id: 'companies',    label: 'الشركات' },
      { id: 'subscriptions',label: 'الاشتراكات والمدفوعات' },
      { id: 'auditors',     label: 'المدققون' },
      { id: 'assignments',  label: 'التعيينات' },
      { id: 'reviews',      label: 'متابعة المراجعات' },
      { id: 'reports',      label: 'التقارير' },
    ],
    stats: {
      companies: 47, activeSubscriptions: 38,
      pendingPayments: 5, auditorRequests: 3,
      assignments: 12, avgReadiness: 71
    },
    companies: [
      { id: 1, name: 'شركة الحلول الرقمية',   subscription: 'نشط',    readiness: 78, auditor: 'م. سعد العتيبي', payment: 'مدفوع' },
      { id: 2, name: 'مجموعة الطاقة الوطنية', subscription: 'معلق',   readiness: 45, auditor: '—',              payment: 'معلق'  },
      { id: 3, name: 'شركة التقنية الخضراء',  subscription: 'نشط',    readiness: 62, auditor: 'م. نورة السالم', payment: 'مدفوع' },
    ],
    auditors: [
      { id: 1, name: 'م. سعد العتيبي',  status: 'active',  assigned: 2, speciality: 'NCA / ISO 27001' },
      { id: 2, name: 'م. نورة السالم',  status: 'active',  assigned: 1, speciality: 'Aramco SACS-002' },
      { id: 3, name: 'م. خالد الشمري', status: 'pending',  assigned: 0, speciality: 'NCA ECC' },
    ],
    pendingPayments: [
      { id: 1, company: 'مجموعة الطاقة الوطنية', plan: 'Professional', amount: '12,000 ر.س', date: '2026-07-24' },
    ],
    approvePayment(p) { p.status = 'approved'; },
    rejectPayment(p)  { p.status = 'rejected'; },
    approveAuditor(a) { a.status = 'active'; },
    rejectAuditor(a)  { a.status = 'rejected'; },
    navigate(id) { this.activeSection = id; }
  }));

});

// ── Intersection Observer for enter animations ────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!('IntersectionObserver' in window)) {
    document.querySelectorAll('.sc-enter').forEach(el => el.classList.add('sc-show'));
    return;
  }
  const io = new IntersectionObserver((entries, obs) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('sc-show');
        obs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });
  document.querySelectorAll('.sc-enter').forEach(el => io.observe(el));

  // scroll shadow
  const bar = document.querySelector('[data-topbar]');
  if (bar) {
    window.addEventListener('scroll', () => {
      bar.style.boxShadow = window.scrollY > 10 ? '0 8px 28px rgba(20,60,45,.06)' : 'none';
    }, { passive: true });
  }
});
