"""Fail-closed contract policy evaluation."""
from __future__ import annotations

from uuid import uuid4

from packages.platform_contracts.security import AnalyticsIdentity, AuthorizationDecision
from packages.platform_contracts.semantic import SemanticContract


def authorize(identity: AnalyticsIdentity, contract: SemanticContract, target_ids: set[str], purpose: str) -> AuthorizationDecision:
    if identity.tenant_id != contract.tenant_id:
        return AuthorizationDecision(decision_id=uuid4().hex, effect="deny", reasons=["tenant_mismatch"], policy_version=contract.version)
    for policy in contract.policies:
        if not target_ids.intersection(policy.target_ids):
            continue
        if purpose not in policy.allowed_purposes:
            return AuthorizationDecision(decision_id=uuid4().hex, effect="deny", reasons=[f"purpose_not_allowed:{policy.id}"], enforced_filter_ids=policy.required_filter_ids, policy_version=contract.version)
        if policy.classification in {"confidential", "restricted"} and not identity.groups:
            return AuthorizationDecision(decision_id=uuid4().hex, effect="review", reasons=[f"group_required:{policy.id}"], enforced_filter_ids=policy.required_filter_ids, policy_version=contract.version)
        return AuthorizationDecision(decision_id=uuid4().hex, effect="allow", reasons=[f"policy_allowed:{policy.id}"], enforced_filter_ids=policy.required_filter_ids, policy_version=contract.version)
    return AuthorizationDecision(decision_id=uuid4().hex, effect="allow", reasons=["no_restrictive_policy"], policy_version=contract.version)
