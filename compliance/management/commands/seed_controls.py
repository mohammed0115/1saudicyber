"""
Management command to seed compliance controls from the consolidated Excel file.
Usage: python manage.py seed_controls
"""
from django.core.management.base import BaseCommand
from compliance.models import Framework, Domain, Control, ControlMapping


class Command(BaseCommand):
    help = 'Seed compliance controls for NCA ECC, Aramco SACS-002, and SABIC CyberTrust'

    def handle(self, *args, **options):
        self.stdout.write("Seeding compliance frameworks and controls...")

        # Create Frameworks
        nca, _ = Framework.objects.get_or_create(
            code='NCA_ECC',
            defaults={
                'name': 'NCA Essential Cybersecurity Controls',
                'name_ar': 'الضوابط الأساسية للأمن السيبراني',
                'version': '2.0',
                'description': 'National Cybersecurity Authority Essential Cybersecurity Controls for government and critical infrastructure.',
            }
        )
        aramco, _ = Framework.objects.get_or_create(
            code='ARAMCO_SACS002',
            defaults={
                'name': 'Saudi Aramco SACS-002',
                'name_ar': 'معيار أرامكو للأمن السيبراني',
                'version': '5.0',
                'description': 'Saudi Aramco Third-Party Cybersecurity Standard for suppliers and contractors.',
            }
        )
        sabic, _ = Framework.objects.get_or_create(
            code='SABIC_CT',
            defaults={
                'name': 'SABIC CyberTrust',
                'name_ar': 'معيار سابك للثقة السيبرانية',
                'version': '1.0',
                'description': 'SABIC CyberTrust Standard for supplier cybersecurity compliance.',
            }
        )

        # Create Domains
        domains_data = [
            ('GOV', 'Cybersecurity Governance', 'حوكمة الأمن السيبراني'),
            ('DEF', 'Cybersecurity Defense', 'الدفاع السيبراني'),
            ('RES', 'Cybersecurity Resilience', 'المرونة السيبرانية'),
            ('TPM', 'Third-Party & Cloud', 'الأطراف الخارجية والسحابة'),
            ('ICS', 'Industrial Control Systems', 'أنظمة التحكم الصناعي'),
            ('ACC', 'Access Control', 'التحكم في الوصول'),
            ('NET', 'Network Security', 'أمن الشبكات'),
            ('DAT', 'Data Protection', 'حماية البيانات'),
            ('INC', 'Incident Management', 'إدارة الحوادث'),
            ('PHY', 'Physical Security', 'الأمن المادي'),
            ('HRM', 'Human Resources Security', 'أمن الموارد البشرية'),
            ('ASM', 'Asset Management', 'إدارة الأصول'),
            ('CRY', 'Cryptography', 'التشفير'),
            ('CHM', 'Change Management', 'إدارة التغيير'),
            ('VUL', 'Vulnerability Management', 'إدارة الثغرات'),
            ('AUD', 'Audit & Compliance', 'التدقيق والامتثال'),
            ('BCP', 'Business Continuity', 'استمرارية الأعمال'),
            ('AWR', 'Security Awareness', 'التوعية الأمنية'),
        ]

        domain_objects = {}
        for code, name, name_ar in domains_data:
            for fw in [nca, aramco, sabic]:
                d, _ = Domain.objects.get_or_create(
                    code=code,
                    framework=fw,
                    defaults={'name': name, 'name_ar': name_ar}
                )
                domain_objects[(code, fw.code)] = d

        # NCA ECC Controls (sample of key controls)
        nca_controls = [
            ('NCA-1-1', 'GOV', 'Cybersecurity Strategy', 'استراتيجية الأمن السيبراني', 'high', 'Establish and maintain a cybersecurity strategy aligned with business objectives.'),
            ('NCA-1-2', 'GOV', 'Cybersecurity Policy', 'سياسة الأمن السيبراني', 'high', 'Define, approve, and communicate cybersecurity policies.'),
            ('NCA-1-3', 'GOV', 'Cybersecurity Roles & Responsibilities', 'أدوار ومسؤوليات الأمن السيبراني', 'high', 'Define and assign cybersecurity roles and responsibilities.'),
            ('NCA-1-4', 'GOV', 'Cybersecurity Risk Management', 'إدارة مخاطر الأمن السيبراني', 'critical', 'Implement a cybersecurity risk management framework.'),
            ('NCA-1-5', 'GOV', 'Cybersecurity in Project Management', 'الأمن السيبراني في إدارة المشاريع', 'medium', 'Integrate cybersecurity in project management processes.'),
            ('NCA-1-6', 'GOV', 'Compliance with Standards', 'الامتثال للمعايير', 'high', 'Ensure compliance with applicable cybersecurity standards and regulations.'),
            ('NCA-1-7', 'GOV', 'Cybersecurity Periodic Review', 'المراجعة الدورية للأمن السيبراني', 'medium', 'Conduct periodic reviews of cybersecurity controls.'),
            ('NCA-2-1', 'DEF', 'Asset Management', 'إدارة الأصول', 'high', 'Identify and manage information assets.'),
            ('NCA-2-2', 'DEF', 'Identity & Access Management', 'إدارة الهوية والوصول', 'critical', 'Implement identity and access management controls.'),
            ('NCA-2-3', 'DEF', 'Information System Protection', 'حماية أنظمة المعلومات', 'critical', 'Protect information systems from unauthorized access.'),
            ('NCA-2-4', 'DEF', 'Email Security', 'أمن البريد الإلكتروني', 'high', 'Implement email security controls.'),
            ('NCA-2-5', 'DEF', 'Network Security', 'أمن الشبكات', 'critical', 'Implement network security controls and segmentation.'),
            ('NCA-2-6', 'DEF', 'Mobile Device Security', 'أمن الأجهزة المحمولة', 'medium', 'Manage and secure mobile devices.'),
            ('NCA-2-7', 'DEF', 'Data Protection & Privacy', 'حماية البيانات والخصوصية', 'critical', 'Implement data protection and privacy controls.'),
            ('NCA-2-8', 'DEF', 'Cryptography', 'التشفير', 'high', 'Implement cryptographic controls for data protection.'),
            ('NCA-2-9', 'DEF', 'Backup Management', 'إدارة النسخ الاحتياطي', 'high', 'Implement and manage backup procedures.'),
            ('NCA-2-10', 'DEF', 'Vulnerability Management', 'إدارة الثغرات', 'critical', 'Identify and remediate vulnerabilities.'),
            ('NCA-2-11', 'DEF', 'Penetration Testing', 'اختبار الاختراق', 'high', 'Conduct regular penetration testing.'),
            ('NCA-2-12', 'DEF', 'Security Event Monitoring', 'مراقبة الأحداث الأمنية', 'critical', 'Monitor and analyze security events.'),
            ('NCA-2-13', 'DEF', 'Security Incident Management', 'إدارة الحوادث الأمنية', 'critical', 'Establish incident response procedures.'),
            ('NCA-2-14', 'DEF', 'Physical Security', 'الأمن المادي', 'high', 'Implement physical security controls.'),
            ('NCA-2-15', 'DEF', 'Web Application Security', 'أمن تطبيقات الويب', 'high', 'Secure web applications against common threats.'),
            ('NCA-3-1', 'RES', 'Business Continuity', 'استمرارية الأعمال', 'critical', 'Develop and maintain business continuity plans.'),
            ('NCA-3-2', 'RES', 'Disaster Recovery', 'التعافي من الكوارث', 'critical', 'Establish disaster recovery procedures.'),
            ('NCA-4-1', 'TPM', 'Third-Party Security', 'أمن الأطراف الخارجية', 'high', 'Manage third-party cybersecurity risks.'),
            ('NCA-4-2', 'TPM', 'Cloud Computing Security', 'أمن الحوسبة السحابية', 'high', 'Implement cloud security controls.'),
            ('NCA-5-1', 'ICS', 'ICS Security', 'أمن أنظمة التحكم الصناعي', 'critical', 'Implement ICS-specific security controls.'),
        ]

        for ctrl_id, domain_code, title, title_ar, criticality, desc in nca_controls:
            Control.objects.get_or_create(
                control_id=ctrl_id,
                framework=nca,
                defaults={
                    'title': title,
                    'title_ar': title_ar,
                    'description': desc,
                    'domain': domain_objects.get((domain_code, 'NCA_ECC')),
                    'priority': criticality,
                    'evidence_type': 'policy',
                }
            )

        # Aramco SACS-002 Controls
        aramco_controls = [
            ('SACS-1-1', 'GOV', 'Information Security Policy', 'سياسة أمن المعلومات', 'critical', 'Maintain an information security policy approved by management.'),
            ('SACS-1-2', 'GOV', 'Security Organization', 'تنظيم الأمن', 'high', 'Establish a security organization with defined roles.'),
            ('SACS-1-3', 'GOV', 'Risk Assessment', 'تقييم المخاطر', 'critical', 'Conduct regular risk assessments of information assets.'),
            ('SACS-2-1', 'ACC', 'Access Control Policy', 'سياسة التحكم في الوصول', 'critical', 'Define and enforce access control policies.'),
            ('SACS-2-2', 'ACC', 'User Access Management', 'إدارة وصول المستخدمين', 'critical', 'Manage user access rights and privileges.'),
            ('SACS-2-3', 'ACC', 'Password Management', 'إدارة كلمات المرور', 'high', 'Implement strong password policies.'),
            ('SACS-2-4', 'ACC', 'Multi-Factor Authentication', 'المصادقة متعددة العوامل', 'critical', 'Implement MFA for critical systems.'),
            ('SACS-2-5', 'ACC', 'Privileged Access Management', 'إدارة الوصول المميز', 'critical', 'Control and monitor privileged access.'),
            ('SACS-3-1', 'NET', 'Network Architecture', 'بنية الشبكة', 'high', 'Implement secure network architecture.'),
            ('SACS-3-2', 'NET', 'Firewall Management', 'إدارة جدار الحماية', 'critical', 'Configure and maintain firewalls.'),
            ('SACS-3-3', 'NET', 'Network Monitoring', 'مراقبة الشبكة', 'high', 'Monitor network traffic for anomalies.'),
            ('SACS-3-4', 'NET', 'Wireless Security', 'أمن الشبكات اللاسلكية', 'medium', 'Secure wireless network access.'),
            ('SACS-3-5', 'NET', 'Remote Access', 'الوصول عن بعد', 'high', 'Secure remote access connections.'),
            ('SACS-4-1', 'DAT', 'Data Classification', 'تصنيف البيانات', 'high', 'Classify data based on sensitivity.'),
            ('SACS-4-2', 'DAT', 'Data Encryption', 'تشفير البيانات', 'critical', 'Encrypt sensitive data at rest and in transit.'),
            ('SACS-4-3', 'DAT', 'Data Loss Prevention', 'منع فقدان البيانات', 'high', 'Implement DLP controls.'),
            ('SACS-4-4', 'DAT', 'Data Backup', 'النسخ الاحتياطي للبيانات', 'critical', 'Maintain regular data backups.'),
            ('SACS-5-1', 'INC', 'Incident Response Plan', 'خطة الاستجابة للحوادث', 'critical', 'Develop and maintain incident response procedures.'),
            ('SACS-5-2', 'INC', 'Incident Reporting', 'الإبلاغ عن الحوادث', 'high', 'Report security incidents to Aramco within 24 hours.'),
            ('SACS-5-3', 'INC', 'Forensic Investigation', 'التحقيق الجنائي', 'medium', 'Capability to conduct forensic investigations.'),
            ('SACS-6-1', 'VUL', 'Vulnerability Scanning', 'فحص الثغرات', 'high', 'Conduct regular vulnerability scans.'),
            ('SACS-6-2', 'VUL', 'Patch Management', 'إدارة التحديثات', 'critical', 'Apply security patches within defined timeframes.'),
            ('SACS-6-3', 'VUL', 'Penetration Testing', 'اختبار الاختراق', 'high', 'Conduct annual penetration testing.'),
            ('SACS-7-1', 'PHY', 'Physical Access Control', 'التحكم في الوصول المادي', 'high', 'Control physical access to facilities.'),
            ('SACS-7-2', 'PHY', 'Environmental Controls', 'الضوابط البيئية', 'medium', 'Implement environmental protection controls.'),
            ('SACS-8-1', 'HRM', 'Security Awareness Training', 'التدريب على التوعية الأمنية', 'high', 'Provide regular security awareness training.'),
            ('SACS-8-2', 'HRM', 'Background Checks', 'التحقق من الخلفية', 'medium', 'Conduct background checks for personnel.'),
            ('SACS-9-1', 'BCP', 'Business Continuity Plan', 'خطة استمرارية الأعمال', 'critical', 'Maintain and test business continuity plans.'),
            ('SACS-9-2', 'BCP', 'Disaster Recovery', 'التعافي من الكوارث', 'critical', 'Maintain disaster recovery capabilities.'),
            ('SACS-10-1', 'ASM', 'Asset Inventory', 'جرد الأصول', 'high', 'Maintain an inventory of information assets.'),
            ('SACS-10-2', 'CHM', 'Change Management', 'إدارة التغيير', 'high', 'Implement change management procedures.'),
        ]

        for ctrl_id, domain_code, title, title_ar, criticality, desc in aramco_controls:
            Control.objects.get_or_create(
                control_id=ctrl_id,
                framework=aramco,
                defaults={
                    'title': title,
                    'title_ar': title_ar,
                    'description': desc,
                    'domain': domain_objects.get((domain_code, 'ARAMCO_SACS002')),
                    'priority': criticality,
                    'evidence_type': 'policy',
                }
            )

        # SABIC CyberTrust Controls
        sabic_controls = [
            ('SCT-1-1', 'GOV', 'Security Governance Framework', 'إطار حوكمة الأمن', 'critical', 'Establish a cybersecurity governance framework.'),
            ('SCT-1-2', 'GOV', 'Security Policy', 'السياسة الأمنية', 'critical', 'Develop and maintain information security policies.'),
            ('SCT-1-3', 'GOV', 'Risk Management', 'إدارة المخاطر', 'critical', 'Implement a risk management process.'),
            ('SCT-1-4', 'GOV', 'Compliance Management', 'إدارة الامتثال', 'high', 'Ensure compliance with applicable regulations.'),
            ('SCT-2-1', 'ACC', 'Identity Management', 'إدارة الهوية', 'critical', 'Implement identity management controls.'),
            ('SCT-2-2', 'ACC', 'Access Control', 'التحكم في الوصول', 'critical', 'Enforce least privilege access.'),
            ('SCT-2-3', 'ACC', 'Authentication', 'المصادقة', 'critical', 'Implement strong authentication mechanisms.'),
            ('SCT-2-4', 'ACC', 'Privileged Access', 'الوصول المميز', 'critical', 'Control and monitor privileged accounts.'),
            ('SCT-3-1', 'NET', 'Network Segmentation', 'تقسيم الشبكة', 'high', 'Implement network segmentation.'),
            ('SCT-3-2', 'NET', 'Perimeter Security', 'أمن المحيط', 'critical', 'Maintain perimeter security controls.'),
            ('SCT-3-3', 'NET', 'Network Monitoring', 'مراقبة الشبكة', 'high', 'Monitor network for threats.'),
            ('SCT-3-4', 'NET', 'Secure Communications', 'الاتصالات الآمنة', 'high', 'Encrypt network communications.'),
            ('SCT-4-1', 'DAT', 'Data Classification', 'تصنيف البيانات', 'high', 'Classify and label data.'),
            ('SCT-4-2', 'DAT', 'Data Protection', 'حماية البيانات', 'critical', 'Protect data based on classification.'),
            ('SCT-4-3', 'DAT', 'Data Retention', 'الاحتفاظ بالبيانات', 'medium', 'Define data retention policies.'),
            ('SCT-4-4', 'CRY', 'Encryption', 'التشفير', 'critical', 'Implement encryption for sensitive data.'),
            ('SCT-5-1', 'INC', 'Incident Response', 'الاستجابة للحوادث', 'critical', 'Establish incident response capabilities.'),
            ('SCT-5-2', 'INC', 'Incident Communication', 'التواصل بشأن الحوادث', 'high', 'Define incident communication procedures.'),
            ('SCT-5-3', 'INC', 'Lessons Learned', 'الدروس المستفادة', 'medium', 'Conduct post-incident reviews.'),
            ('SCT-6-1', 'VUL', 'Vulnerability Management', 'إدارة الثغرات', 'critical', 'Implement vulnerability management program.'),
            ('SCT-6-2', 'VUL', 'Patch Management', 'إدارة التحديثات', 'critical', 'Apply patches in a timely manner.'),
            ('SCT-6-3', 'VUL', 'Security Testing', 'الاختبار الأمني', 'high', 'Conduct regular security testing.'),
            ('SCT-7-1', 'AWR', 'Security Awareness', 'التوعية الأمنية', 'high', 'Implement security awareness program.'),
            ('SCT-7-2', 'AWR', 'Security Training', 'التدريب الأمني', 'high', 'Provide role-based security training.'),
            ('SCT-8-1', 'BCP', 'Business Continuity', 'استمرارية الأعمال', 'critical', 'Develop business continuity plans.'),
            ('SCT-8-2', 'BCP', 'Disaster Recovery', 'التعافي من الكوارث', 'critical', 'Maintain disaster recovery capabilities.'),
            ('SCT-9-1', 'PHY', 'Physical Security', 'الأمن المادي', 'high', 'Implement physical security controls.'),
            ('SCT-9-2', 'PHY', 'Environmental Protection', 'الحماية البيئية', 'medium', 'Protect against environmental threats.'),
            ('SCT-10-1', 'ASM', 'Asset Management', 'إدارة الأصول', 'high', 'Maintain asset inventory.'),
            ('SCT-10-2', 'CHM', 'Change Control', 'التحكم في التغيير', 'high', 'Implement change control procedures.'),
        ]

        for ctrl_id, domain_code, title, title_ar, criticality, desc in sabic_controls:
            Control.objects.get_or_create(
                control_id=ctrl_id,
                framework=sabic,
                defaults={
                    'title': title,
                    'title_ar': title_ar,
                    'description': desc,
                    'domain': domain_objects.get((domain_code, 'SABIC_CT')),
                    'priority': criticality,
                    'evidence_type': 'policy',
                }
            )

        # Create Cross-Mappings
        mappings = [
            ('NCA-1-1', 'SACS-1-1', 'equivalent'),
            ('NCA-1-1', 'SCT-1-2', 'equivalent'),
            ('NCA-1-4', 'SACS-1-3', 'equivalent'),
            ('NCA-1-4', 'SCT-1-3', 'equivalent'),
            ('NCA-2-2', 'SACS-2-1', 'equivalent'),
            ('NCA-2-2', 'SCT-2-1', 'equivalent'),
            ('NCA-2-5', 'SACS-3-1', 'partial'),
            ('NCA-2-5', 'SCT-3-1', 'partial'),
            ('NCA-2-7', 'SACS-4-1', 'partial'),
            ('NCA-2-7', 'SCT-4-1', 'partial'),
            ('NCA-2-10', 'SACS-6-1', 'equivalent'),
            ('NCA-2-10', 'SCT-6-1', 'equivalent'),
            ('NCA-2-13', 'SACS-5-1', 'equivalent'),
            ('NCA-2-13', 'SCT-5-1', 'equivalent'),
            ('NCA-3-1', 'SACS-9-1', 'equivalent'),
            ('NCA-3-1', 'SCT-8-1', 'equivalent'),
            ('SACS-2-4', 'SCT-2-3', 'equivalent'),
            ('SACS-4-2', 'SCT-4-4', 'equivalent'),
            ('SACS-6-2', 'SCT-6-2', 'equivalent'),
            ('SACS-8-1', 'SCT-7-1', 'equivalent'),
        ]

        for src_id, tgt_id, mtype in mappings:
            try:
                src = Control.objects.get(control_id=src_id)
                tgt = Control.objects.get(control_id=tgt_id)
                ControlMapping.objects.get_or_create(
                    source_control=src,
                    target_control=tgt,
                    defaults={'mapping_type': mtype}
                )
            except Control.DoesNotExist:
                pass

        total = Control.objects.count()
        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {total} controls across 3 frameworks with cross-mappings.'))
