# Case Study: Reducing Repeat Support Tickets With Compass

## Executive Summary

A mid-market B2B SaaS company receives thousands of customer support tickets
every month across Zendesk or Intercom. Many tickets are repeats: the same
product issue, setup confusion, export failure, timeout, billing question, or
integration problem appears again and again.

Compass turns that historical support data into a Resolution Intelligence layer:
it finds repeat issue clusters, retrieves prior solved cases, generates an
evidence-backed agent playbook, recommends the missing KB or macro, and estimates
how many future tickets could be deflected.

This is not a helpdesk replacement. Compass sits above the support stack as a
system of intelligence for support operations, agents, CX leaders, and product
teams.

## Prospect Profile

Best fit:

- B2B SaaS company
- 5-100 support agents
- 3k-50k support tickets per month
- Zendesk or Intercom as the primary helpdesk
- Help center, macros, Slack/Jira escalations, and product context outside the helpdesk
- Leadership goal to reduce repeat tickets without unsafe full automation

Primary buyer:

- Head of Support
- Support Operations
- CX Operations
- VP Customer Experience

Primary users:

- Support operations manager
- Tier-1 and Tier-2 agents
- Product operations
- CX leadership

## The Problem

Support teams often already have the answers, but the answers are buried.

Prior resolutions live across:

- solved tickets;
- internal ticket comments;
- help-center articles;
- macros;
- Slack escalations;
- Jira or Linear bugs;
- CRM or customer context.

The result is expensive repetition:

- agents search manually before answering;
- new agents miss prior solutions;
- stale KB articles keep generating tickets;
- support ops sees volume, but not always the root cause;
- product teams lack clean evidence for repeated issues;
- AI answer generation feels risky without citations and human review.

## Compass Workflow

Compass creates a closed loop:

```text
support tickets
  -> repeat issue cluster
  -> cited prior resolutions
  -> evidence-backed playbook
  -> KB or macro gap
  -> estimated deflection
  -> human-reviewed improvement
```

## Example Scenario: Export Timeout Tickets

A prospect has many tickets like:

- "CSV export times out"
- "Report export failed again"
- "Customer cannot download large report"
- "Export stuck for enterprise account"

Compass identifies these as a repeat cluster:

```text
Cluster: Export + Timeout
Signal: repeated export failures and timeout language
Status mix: solved and open tickets
Opportunity: repeated issue suitable for macro or KB deflection
```

## What Compass Shows

### 1. Normalized Support Records

Compass ingests or syncs support data into a canonical model:

- ticket subject;
- ticket status;
- customer-visible comments;
- internal comments;
- linked articles;
- provider metadata;
- tenant and source boundaries.

This gives teams a helpdesk-neutral support memory that can work across Zendesk,
Intercom, and future sources.

### 2. Repeat-Ticket Insights

Compass groups repeated issues and ranks them by support impact.

For each cluster it shows:

- issue title;
- ticket count;
- share of analyzed volume;
- sample tickets;
- recommended next action;
- whether a KB or macro gap exists.

### 3. Ask Prior Resolutions

An agent or support ops user can ask:

```text
How have we resolved export timeout issues?
```

Compass retrieves similar solved tickets and articles, then answers with
citations. The team can inspect the underlying evidence instead of trusting an
uncited generated answer.

### 4. Evidence-Backed Playbook

Compass generates a review-ready playbook:

- issue signature;
- likely cause;
- recommended resolution;
- step-by-step agent instructions;
- customer response draft;
- citations to prior tickets or articles;
- confidence level;
- guardrails.

The playbook is marked for agent review, not autonomous sending.

### 5. Knowledge Gap Recommendation

If Compass finds solved tickets but weak or missing article evidence, it
recommends creating or updating:

- a macro;
- a help-center article;
- an internal runbook;
- a product bug or escalation.

This is where deflection becomes durable. The value is not only answering one
ticket faster; it is reducing the next 50 similar tickets.

### 6. Deflection Estimate

Compass estimates how many tickets in the analyzed sample could be deflected if
the playbook, macro, or KB recommendation is accepted.

The estimate is explicitly labeled as an estimate and includes assumptions.
For production pilots, Compass should compare before/after ticket volume once
the support team deploys the recommendation.

## Why This Is Different

Most support AI tools focus on drafting a single reply.

Compass focuses on the operating loop:

| Standard AI Reply Tool | Compass Resolution Intelligence |
|---|---|
| Drafts one response | Finds repeat issue clusters |
| Often opaque | Shows cited evidence |
| Optimized for agent speed | Optimized for ticket reduction |
| Helpdesk-bound | Helpdesk-neutral support memory |
| Risky automation pressure | Human review by default |
| Weak ROI trace | Deflection estimate and future measurement |

## Business Impact

Compass helps a support organization:

- reduce repeated tickets;
- shorten agent research time;
- improve onboarding for new agents;
- identify stale or missing KB content;
- give product teams evidence for repeated bugs;
- measure which knowledge improvements should reduce ticket volume.

Expected pilot metrics:

- repeat clusters discovered;
- playbooks generated;
- percentage of playbooks with citations;
- KB or macro gaps accepted;
- estimated deflectable tickets;
- actual repeat-ticket reduction after deployment;
- agent acceptance rate.

## Deployment Model

Compass can run as:

- a local pilot;
- a SaaS control plane with customer-specific data planes;
- a customer-region deployment for data residency.

For enterprise buyers, the control-plane/data-plane model keeps customer data in
the required region while the control plane manages auth, routing, tenant admin,
and observability.

## Demo Walkthrough

For a live local demo:

1. Open `http://localhost:5173/support`.
2. Click **Load demo data** or run the local demo gate.
3. Show normalized ticket counts.
4. Show repeat-ticket clusters.
5. Select or generate the `Export + Timeout` workflow.
6. Show the playbook, citations, KB gap, and deflection estimate.
7. Emphasize that customer-facing output remains review-required.

Local verification:

```bash
make demo-ready-local
make support-demo
```

Expected result:

```text
Resolution Intelligence local acceptance: PASS
```

## Caveats For Prospect Conversations

Say these clearly:

- The local demo uses representative seed data.
- A real pilot connects Zendesk or Intercom data.
- The GitHub connector in the local demo is visual/demo state unless real credentials are provided.
- Slack/Jira/CRM enrichment are roadmap or pilot-specific integrations.
- Customer-facing drafts require human review in v1.
- Before/after ROI measurement requires a live pilot period after KB or macro changes are deployed.

## Pilot Proposal

A practical pilot can be scoped to 2-4 weeks:

1. Connect Zendesk or Intercom sandbox/export.
2. Index 3-6 months of tickets, comments, and articles.
3. Identify top 10 repeat clusters.
4. Generate playbooks for the top 3 clusters.
5. Review citations with support leads.
6. Convert accepted playbooks into macros or KB updates.
7. Measure repeat ticket volume before and after rollout.

Pilot success criteria:

- at least 5 meaningful repeat clusters found;
- at least 3 playbooks accepted by support ops;
- citation coverage high enough for agent trust;
- at least 1 KB or macro gap accepted;
- measurable reduction plan for one repeat issue.

## Positioning

Compass is the evidence layer for support operations.

It does not ask prospects to replace Zendesk or Intercom. It helps them learn
from the tickets they already have, reduce repeated issues, and only then move
toward safer automation.
