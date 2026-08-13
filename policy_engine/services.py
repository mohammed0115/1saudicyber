"""Deterministic evaluation services for versioned policy packages."""
from __future__ import annotations

from typing import Any

from compliance.models import Control
from policy_engine.models import PolicyEvaluation, PolicyVersion


def _matches_condition(subject: dict[str, Any], condition: dict[str, Any]) -> bool:
    """Evaluate a deliberately small, auditable condition DSL."""
    if not condition:
        return True
    field = condition.get('field')
    if not field:
        return False
    value = subject.get(field)
    if 'equals' in condition:
        return value == condition['equals']
    if 'in' in condition:
        return value in condition['in']
    if condition.get('exists') is True:
        return value not in (None, '', [], {})
    if condition.get('exists') is False:
        return value in (None, '', [], {})
    return False


def evaluate_policy(policy_version: PolicyVersion, subject: dict[str, Any], *, company=None, user=None):
    """Evaluate a policy version without calling an AI model or mutating a checklist."""
    if not policy_version.is_effective_on():
        raise ValueError('Policy version is not approved and effective.')

    matched_rules = []
    requested_control_ids = set()
    for rule in policy_version.rules:
        conditions = rule.get('all', [])
        if not isinstance(conditions, list):
            conditions = []
        if all(_matches_condition(subject, condition) for condition in conditions):
            control_ids = [str(value) for value in rule.get('include_control_ids', [])]
            requested_control_ids.update(control_ids)
            matched_rules.append({
                'rule_id': rule['id'],
                'reason': rule.get('reason', ''),
                'control_ids': control_ids,
            })

    existing_controls = {
        control.control_id: control
        for control in Control.objects.filter(control_id__in=requested_control_ids).select_related('framework')
    }
    applicable_controls = [
        {
            'control_id': control_id,
            'framework': existing_controls[control_id].framework.code,
            'title': existing_controls[control_id].title,
        }
        for control_id in sorted(existing_controls)
    ]
    unresolved_control_ids = sorted(requested_control_ids - set(existing_controls))
    result = {
        'policy_pack': policy_version.policy_pack.key,
        'policy_version': policy_version.version,
        'policy_content_hash': policy_version.content_hash,
        'matched_rules': matched_rules,
        'applicable_controls': applicable_controls,
        'unresolved_control_ids': unresolved_control_ids,
    }
    evaluation = PolicyEvaluation.objects.create(
        company=company,
        policy_version=policy_version,
        input_data=subject,
        result_data=result,
        evaluated_by=user,
    )
    result['evaluation_id'] = evaluation.id
    result['decision_hash'] = evaluation.decision_hash
    return result


def subject_from_company(company):
    """Create a bounded, non-sensitive policy subject from a Company record."""
    return {
        'company_id': company.id,
        'sector': company.sector,
        'size': company.size,
        'target_nca': company.target_nca,
        'target_aramco': company.target_aramco,
        'target_sabic': company.target_sabic,
    }


def evaluate_company_policy(policy_version: PolicyVersion, company, *, user=None):
    """Evaluate policy against a company, retaining the company as the tenant context."""
    return evaluate_policy(policy_version, subject_from_company(company), company=company, user=user)
