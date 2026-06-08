import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'cybertrust_ksa.settings'
django.setup()
from compliance.models import Framework, Domain, Control

nca = Framework.objects.get(name='NCA Essential Cybersecurity Controls')
aramco = Framework.objects.get(name='Saudi Aramco SACS-002')
sabic = Framework.objects.get(name='SABIC CyberTrust')

# NCA additional domains and controls
nca_additions = {
    'Cybersecurity Resilience': [
        ('NCA-5-1', 'Business Continuity Management', 'Establish business continuity plan for cybersecurity incidents', 'high', 'policy'),
        ('NCA-5-2', 'Disaster Recovery', 'Implement disaster recovery procedures for critical systems', 'high', 'policy'),
        ('NCA-5-3', 'Backup Management', 'Regular backup of critical data and systems', 'high', 'screenshot'),
        ('NCA-5-4', 'Resilience Testing', 'Regular testing of business continuity and disaster recovery plans', 'medium', 'report'),
        ('NCA-5-5', 'Crisis Communication', 'Establish crisis communication procedures', 'medium', 'policy'),
        ('NCA-5-6', 'Recovery Time Objectives', 'Define and test RTO/RPO for critical systems', 'high', 'report'),
        ('NCA-5-7', 'Alternate Processing Sites', 'Maintain alternate processing capabilities', 'high', 'screenshot'),
    ],
    'Third-Party Cybersecurity': [
        ('NCA-6-1', 'Third-Party Risk Assessment', 'Assess cybersecurity risks of third parties', 'high', 'report'),
        ('NCA-6-2', 'Third-Party Agreements', 'Include cybersecurity requirements in contracts', 'high', 'policy'),
        ('NCA-6-3', 'Third-Party Monitoring', 'Monitor third-party compliance continuously', 'medium', 'report'),
        ('NCA-6-4', 'Supply Chain Security', 'Manage supply chain cybersecurity risks', 'high', 'policy'),
        ('NCA-6-5', 'Cloud Security', 'Ensure cloud service provider compliance', 'high', 'report'),
        ('NCA-6-6', 'Vendor Access Control', 'Control and monitor vendor access to systems', 'high', 'screenshot'),
        ('NCA-6-7', 'Third-Party Incident Management', 'Include third parties in incident response', 'medium', 'policy'),
    ],
    'Industrial Control Systems': [
        ('NCA-7-1', 'ICS Security Policy', 'Establish ICS/OT cybersecurity policy', 'high', 'policy'),
        ('NCA-7-2', 'ICS Network Segmentation', 'Segment ICS networks from IT networks', 'critical', 'screenshot'),
        ('NCA-7-3', 'ICS Access Control', 'Implement access control for ICS systems', 'critical', 'screenshot'),
        ('NCA-7-4', 'ICS Monitoring', 'Monitor ICS systems for anomalies', 'high', 'report'),
        ('NCA-7-5', 'ICS Patch Management', 'Manage patches for ICS components', 'high', 'report'),
        ('NCA-7-6', 'ICS Incident Response', 'Develop ICS-specific incident response procedures', 'high', 'policy'),
    ],
    'Physical Security': [
        ('NCA-8-1', 'Physical Access Control', 'Control physical access to IT facilities', 'high', 'screenshot'),
        ('NCA-8-2', 'Environmental Controls', 'Implement environmental controls for data centers', 'medium', 'report'),
        ('NCA-8-3', 'Equipment Security', 'Secure IT equipment from theft and damage', 'medium', 'policy'),
        ('NCA-8-4', 'Secure Disposal', 'Securely dispose of IT equipment and media', 'high', 'report'),
        ('NCA-8-5', 'Visitor Management', 'Control and monitor visitor access', 'medium', 'policy'),
    ],
    'Cybersecurity in E-Commerce': [
        ('NCA-9-1', 'E-Commerce Security', 'Secure e-commerce platforms and transactions', 'high', 'report'),
        ('NCA-9-2', 'Payment Security', 'Implement payment card security standards', 'critical', 'report'),
        ('NCA-9-3', 'Customer Data Protection', 'Protect customer personal data in e-commerce', 'high', 'policy'),
        ('NCA-9-4', 'Transaction Monitoring', 'Monitor e-commerce transactions for fraud', 'high', 'screenshot'),
    ],
    'Cryptography': [
        ('NCA-10-1', 'Cryptographic Policy', 'Establish cryptographic controls policy', 'high', 'policy'),
        ('NCA-10-2', 'Key Management', 'Implement secure key management procedures', 'critical', 'policy'),
        ('NCA-10-3', 'Encryption Standards', 'Use approved encryption algorithms and protocols', 'high', 'screenshot'),
        ('NCA-10-4', 'Certificate Management', 'Manage digital certificates lifecycle', 'high', 'screenshot'),
        ('NCA-10-5', 'Data Encryption', 'Encrypt sensitive data at rest and in transit', 'critical', 'screenshot'),
    ],
    'Human Resources Security': [
        ('NCA-11-1', 'Background Checks', 'Conduct background checks for sensitive positions', 'high', 'policy'),
        ('NCA-11-2', 'Security Terms in Employment', 'Include security responsibilities in employment contracts', 'high', 'policy'),
        ('NCA-11-3', 'Termination Procedures', 'Revoke access upon employee termination', 'critical', 'policy'),
        ('NCA-11-4', 'Security Awareness Training', 'Provide regular security awareness training', 'high', 'report'),
        ('NCA-11-5', 'Disciplinary Process', 'Establish disciplinary process for security violations', 'medium', 'policy'),
    ],
}

# Aramco additional controls
aramco_additions = {
    'Identity & Access Management': [
        ('ARA-IAM-1', 'Multi-Factor Authentication', 'Implement MFA for all privileged accounts', 'critical', 'screenshot'),
        ('ARA-IAM-2', 'Privileged Access Management', 'Manage and monitor privileged access', 'critical', 'screenshot'),
        ('ARA-IAM-3', 'Identity Lifecycle Management', 'Manage user identity lifecycle', 'high', 'policy'),
        ('ARA-IAM-4', 'Service Account Management', 'Secure and monitor service accounts', 'high', 'screenshot'),
        ('ARA-IAM-5', 'Access Review', 'Conduct periodic access reviews', 'high', 'report'),
        ('ARA-IAM-6', 'Password Policy', 'Enforce strong password policies', 'high', 'screenshot'),
        ('ARA-IAM-7', 'Single Sign-On', 'Implement SSO where applicable', 'medium', 'screenshot'),
    ],
    'Endpoint Security': [
        ('ARA-EP-1', 'Endpoint Protection', 'Deploy endpoint protection on all devices', 'critical', 'screenshot'),
        ('ARA-EP-2', 'Endpoint Detection & Response', 'Implement EDR capabilities', 'high', 'screenshot'),
        ('ARA-EP-3', 'Mobile Device Management', 'Manage and secure mobile devices', 'high', 'screenshot'),
        ('ARA-EP-4', 'Removable Media Control', 'Control use of removable media', 'medium', 'policy'),
        ('ARA-EP-5', 'Endpoint Hardening', 'Harden endpoint configurations', 'high', 'report'),
        ('ARA-EP-6', 'Application Whitelisting', 'Implement application whitelisting', 'high', 'screenshot'),
    ],
    'Security Operations': [
        ('ARA-SO-1', 'Security Operations Center', 'Establish 24/7 SOC capabilities', 'critical', 'report'),
        ('ARA-SO-2', 'SIEM Implementation', 'Implement SIEM for log aggregation', 'critical', 'screenshot'),
        ('ARA-SO-3', 'Threat Intelligence', 'Integrate threat intelligence feeds', 'high', 'report'),
        ('ARA-SO-4', 'Incident Response Plan', 'Maintain and test incident response plan', 'critical', 'policy'),
        ('ARA-SO-5', 'Forensic Readiness', 'Maintain digital forensic capabilities', 'medium', 'policy'),
        ('ARA-SO-6', 'Security Metrics', 'Track and report security metrics', 'medium', 'report'),
    ],
    'Application Security': [
        ('ARA-AS-1', 'Secure Development Lifecycle', 'Implement SDLC with security gates', 'high', 'policy'),
        ('ARA-AS-2', 'Application Vulnerability Testing', 'Regular application security testing', 'high', 'report'),
        ('ARA-AS-3', 'API Security', 'Secure all APIs with authentication', 'high', 'screenshot'),
        ('ARA-AS-4', 'Code Review', 'Conduct security code reviews', 'medium', 'report'),
        ('ARA-AS-5', 'Web Application Firewall', 'Deploy WAF for public-facing apps', 'high', 'screenshot'),
    ],
    'Data Security': [
        ('ARA-DS-1', 'Data Classification', 'Classify data according to sensitivity', 'high', 'policy'),
        ('ARA-DS-2', 'Data Encryption', 'Encrypt data at rest and in transit', 'critical', 'screenshot'),
        ('ARA-DS-3', 'Data Loss Prevention', 'Implement DLP controls', 'high', 'screenshot'),
        ('ARA-DS-4', 'Database Security', 'Secure database configurations and access', 'high', 'screenshot'),
        ('ARA-DS-5', 'Data Retention', 'Implement data retention and disposal policies', 'medium', 'policy'),
        ('ARA-DS-6', 'Data Masking', 'Mask sensitive data in non-production environments', 'medium', 'screenshot'),
    ],
    'Cloud & Virtualization': [
        ('ARA-CV-1', 'Cloud Security Architecture', 'Design secure cloud architecture', 'high', 'report'),
        ('ARA-CV-2', 'Cloud Access Controls', 'Implement cloud IAM controls', 'critical', 'screenshot'),
        ('ARA-CV-3', 'Container Security', 'Secure container environments', 'high', 'screenshot'),
        ('ARA-CV-4', 'Cloud Monitoring', 'Monitor cloud environments', 'high', 'screenshot'),
        ('ARA-CV-5', 'Cloud Backup', 'Implement cloud backup procedures', 'high', 'report'),
    ],
}

# SABIC additional controls
sabic_additions = {
    'Security Awareness': [
        ('SAB-SA-1', 'Security Awareness Program', 'Establish comprehensive security awareness program', 'high', 'policy'),
        ('SAB-SA-2', 'Phishing Simulation', 'Conduct regular phishing simulation exercises', 'medium', 'report'),
        ('SAB-SA-3', 'Role-Based Training', 'Provide role-specific security training', 'high', 'report'),
        ('SAB-SA-4', 'New Employee Onboarding', 'Include security training in onboarding', 'high', 'policy'),
        ('SAB-SA-5', 'Security Culture Assessment', 'Assess and improve security culture', 'medium', 'report'),
    ],
    'Vulnerability Management': [
        ('SAB-VM-1', 'Vulnerability Scanning', 'Conduct regular vulnerability scans', 'critical', 'report'),
        ('SAB-VM-2', 'Patch Management', 'Implement timely patch management', 'critical', 'report'),
        ('SAB-VM-3', 'Penetration Testing', 'Conduct annual penetration testing', 'high', 'report'),
        ('SAB-VM-4', 'Vulnerability Prioritization', 'Prioritize vulnerabilities by risk', 'high', 'report'),
        ('SAB-VM-5', 'Remediation Tracking', 'Track vulnerability remediation progress', 'high', 'screenshot'),
    ],
    'Network Security': [
        ('SAB-NS-1', 'Network Segmentation', 'Implement network segmentation', 'critical', 'screenshot'),
        ('SAB-NS-2', 'Firewall Management', 'Manage and review firewall rules', 'high', 'screenshot'),
        ('SAB-NS-3', 'Intrusion Detection', 'Deploy IDS/IPS systems', 'high', 'screenshot'),
        ('SAB-NS-4', 'VPN Security', 'Secure remote access via VPN', 'high', 'screenshot'),
        ('SAB-NS-5', 'DNS Security', 'Implement DNS security measures', 'medium', 'screenshot'),
        ('SAB-NS-6', 'Wireless Security', 'Secure wireless networks', 'high', 'screenshot'),
    ],
    'Cloud Security': [
        ('SAB-CS-1', 'Cloud Security Policy', 'Establish cloud security policy', 'high', 'policy'),
        ('SAB-CS-2', 'Cloud Access Security', 'Implement CASB controls', 'high', 'screenshot'),
        ('SAB-CS-3', 'Cloud Configuration', 'Secure cloud configurations', 'high', 'screenshot'),
        ('SAB-CS-4', 'Cloud Data Protection', 'Protect data in cloud environments', 'critical', 'screenshot'),
        ('SAB-CS-5', 'Cloud Monitoring', 'Monitor cloud environments for threats', 'high', 'screenshot'),
    ],
    'Compliance & Audit': [
        ('SAB-CA-1', 'Compliance Framework', 'Maintain compliance with applicable regulations', 'high', 'policy'),
        ('SAB-CA-2', 'Internal Audit', 'Conduct regular internal security audits', 'high', 'report'),
        ('SAB-CA-3', 'External Audit', 'Support external audit requirements', 'high', 'report'),
        ('SAB-CA-4', 'Regulatory Reporting', 'Report security incidents to regulators', 'high', 'policy'),
        ('SAB-CA-5', 'Continuous Improvement', 'Implement continuous improvement program', 'medium', 'report'),
    ],
    'Business Continuity': [
        ('SAB-BC-1', 'BCP Policy', 'Establish business continuity policy', 'high', 'policy'),
        ('SAB-BC-2', 'BCP Testing', 'Test business continuity plans regularly', 'high', 'report'),
        ('SAB-BC-3', 'Disaster Recovery', 'Implement disaster recovery procedures', 'critical', 'policy'),
        ('SAB-BC-4', 'Crisis Management', 'Establish crisis management team and procedures', 'high', 'policy'),
        ('SAB-BC-5', 'Recovery Metrics', 'Define and measure recovery objectives', 'medium', 'report'),
    ],
    'Privacy & Data Protection': [
        ('SAB-PD-1', 'Privacy Policy', 'Establish data privacy policy', 'high', 'policy'),
        ('SAB-PD-2', 'Data Subject Rights', 'Implement data subject rights procedures', 'high', 'policy'),
        ('SAB-PD-3', 'Privacy Impact Assessment', 'Conduct privacy impact assessments', 'high', 'report'),
        ('SAB-PD-4', 'Cross-Border Data Transfer', 'Control cross-border data transfers', 'critical', 'policy'),
        ('SAB-PD-5', 'Data Breach Notification', 'Implement data breach notification procedures', 'critical', 'policy'),
    ],
}

def seed_framework(framework, additions):
    for domain_name, controls in additions.items():
        domain, _ = Domain.objects.get_or_create(name=domain_name, framework=framework)
        for item in controls:
            code, title, desc, priority, evidence_type = item
            Control.objects.get_or_create(
                control_id=code,
                framework=framework,
                defaults={
                    'title': title,
                    'description': desc,
                    'domain': domain,
                    'priority': priority,
                    'evidence_type': evidence_type,
                    'is_mandatory': priority in ('critical', 'high'),
                }
            )

seed_framework(nca, nca_additions)
seed_framework(aramco, aramco_additions)
seed_framework(sabic, sabic_additions)

# Print final counts
print(f'\nTotal Controls: {Control.objects.count()}')
for f in Framework.objects.all():
    print(f'  - {f.name}: {f.controls.count()} controls')
print(f'Total Domains: {Domain.objects.count()}')
