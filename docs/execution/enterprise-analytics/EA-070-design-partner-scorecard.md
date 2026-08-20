# Task EA-070: Enterprise Design-Partner Scorecard

## Objective

Create the discovery and acceptance artifacts needed to turn one enterprise
customer's real analytics workflow into authoritative requirements and an
evaluation set.

## Allowed Scope

- New discovery templates under `docs/execution/enterprise-analytics/`
- No source code, configuration, infrastructure, or customer secrets

## Required Behavior

Produce a reusable template that captures:

1. Business domain, executive sponsor, semantic owners, security owner, and
   operational owner.
2. Warehouse/dialect, dbt state, catalog product, BI tools, identity provider,
   network restrictions, residency, and retention requirements.
3. Twenty-five to fifty authoritative questions grouped into P0, P1, and
   exploratory classes.
4. For each question: approved metric definition, grain, filters, joins, time
   semantics, source assets, expected result or verification method, ambiguity,
   allowed roles, freshness SLA, and maximum cost/latency.
5. Questions that must clarify, refuse, or require human review.
6. Current workflow, analyst effort, error rate, and business impact baseline.
7. Pilot SLOs, security gates, acceptance thresholds, and named signatories.
8. A sanitization process so customer data and credentials never enter the
   repository or model prompts without approval.

## Acceptance Review

- A data owner can approve metric meaning without reading implementation code.
- A security owner can identify data movement and access boundaries.
- Each P0 question can become an `EA-061` golden case without guessing missing
  semantics.
- Pilot go/no-go criteria are measurable and have named owners.
- The artifact distinguishes customer claims from independently verified
  evidence.

## Deliverables

- Interview questionnaire.
- Authoritative-question worksheet template.
- Pilot scorecard and sign-off template.
- Sanitization and repository-handling instructions.

## Stop Conditions

- Real customer identifiers, credentials, query results, or confidential schema
  details would be committed.
- A proposed pilot promise lacks an engineering or security owner.
- Stakeholders cannot name the authority for a metric or policy decision.
