#!/usr/bin/env python3
"""
Generate professional RAG Platform architecture diagram.
Output: docs/images/00-rag-platform-overview.png
"""

import os
os.chdir("/Users/gopalpatwa/opt/scalable-rag-pipeline")

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EKS
from diagrams.aws.database import Aurora, ElastiCache
from diagrams.aws.storage import S3
from diagrams.aws.network import ALB
from diagrams.aws.security import SecretsManager
from diagrams.azure.compute import KubernetesServices
from diagrams.azure.database import DatabaseForPostgresqlServers, CacheForRedis
from diagrams.azure.storage import BlobStorage
from diagrams.azure.security import KeyVaults
from diagrams.azure.network import LoadBalancers as AzureLB
from diagrams.k8s.network import Ingress
from diagrams.k8s.compute import Deploy, Pod
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.tracing import Jaeger
from diagrams.onprem.database import Neo4J
from diagrams.onprem.ci import GithubActions
from diagrams.programming.framework import FastAPI
from diagrams.generic.compute import Rack
from diagrams.generic.device import Tablet
from diagrams.saas.identity import Auth0

graph_attr = {
    "fontsize": "32",
    "fontname": "Helvetica Bold",
    "bgcolor": "#f0f4f8",
    "pad": "1.5",
    "splines": "curved",
    "nodesep": "1.5",
    "ranksep": "2.2",
    "compound": "true",
    "rankdir": "TB",
    "dpi": "220",
    "size": "40,28",
    "newrank": "true",
}

def cluster(bg, border, width="2"):
    return {
        "fontsize": "19",
        "fontname": "Helvetica Bold",
        "style": "filled,rounded",
        "bgcolor": bg,
        "color": border,
        "penwidth": width,
        "margin": "24",
    }

node_attr = {"fontsize": "16", "fontname": "Helvetica"}

with Diagram(
    "  Scalable RAG Platform — Multi-Cloud Architecture  ",
    filename="docs/images/00-rag-platform-overview",
    outformat="png",
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    node_attr=node_attr,
):
    # ── Row 1: Entry points ───────────────────────────────────────────────────
    with Cluster("Users & Clients", graph_attr=cluster("#e0f2f1", "#00695c")):
        browser  = Tablet("Browser\n/ Chat UI")
        ext_api  = Rack("External\nAPI Clients")

    with Cluster("CI/CD  ·  GitHub Actions", graph_attr=cluster("#e8f5e9", "#2e7d32")):
        github = GithubActions("lint  ·  test  ·  build  ·  push")

    with Cluster("Identity  ·  Auth", graph_attr=cluster("#f3e5f5", "#6a1b9a")):
        auth0 = Auth0("Auth0 / Azure AD\n/ Cognito  (JWT · JWKS)")

    # ── Row 2: AWS and Azure side-by-side (forced by same upstream/downstream) ─
    with Cluster("☁  AWS Cloud", graph_attr={
        **cluster("#fff8e1", "#f57c00", "3"),
    }):
        alb = ALB("ALB\nLoad Balancer")

        with Cluster("EKS  ·  Karpenter Autoscale", graph_attr=cluster("#fff3e0", "#e65100")):
            nginx_aws = Ingress("NGINX Ingress\nTLS  ·  Rate Limit")

            with Cluster("FastAPI  +  Code Sandbox", graph_attr=cluster("#fffde7", "#f9a825")):
                api_aws     = FastAPI("FastAPI\nOrchestrator")
                sandbox_aws = Deploy("Code\nSandbox")

            with Cluster("AI Engines  —  GPU", graph_attr=cluster("#ede7f6", "#7b1fa2")):
                ray_aws   = Deploy("Ray Serve")
                vllm_aws  = Deploy("vLLM\nLlama-3-70B")
                embed_aws = Deploy("Embedding\nEngine")

            qdrant_aws = Deploy("Qdrant\nVector DB")

        with Cluster("AWS Managed Services", graph_attr=cluster("#fff8e1", "#ff8f00")):
            aurora = Aurora("Aurora\nPostgres")
            rcache = ElastiCache("ElastiCache\nRedis")
            s3     = S3("S3\nDocuments")
            sm     = SecretsManager("Secrets Mgr\n+  IRSA")

    with Cluster("☁  Azure Cloud", graph_attr={
        **cluster("#e3f2fd", "#1565c0", "3"),
    }):
        az_lb = AzureLB("Load\nBalancer")

        with Cluster("AKS  ·  Karpenter Autoscale", graph_attr=cluster("#e1f5fe", "#0277bd")):
            nginx_az = Ingress("NGINX Ingress\nTLS  ·  Rate Limit")

            with Cluster("FastAPI  +  Code Sandbox ", graph_attr=cluster("#e8f5e9", "#2e7d32")):
                api_az     = FastAPI("FastAPI\nOrchestrator")
                sandbox_az = Deploy("Code\nSandbox")

            with Cluster("AI Engines  —  GPU ", graph_attr=cluster("#ede7f6", "#7b1fa2")):
                ray_az   = Deploy("Ray Serve")
                vllm_az  = Deploy("vLLM\nLlama-3-70B")
                embed_az = Deploy("Embedding\nEngine")

            qdrant_az = Deploy("Qdrant\nVector DB")

        with Cluster("Azure Managed Services", graph_attr=cluster("#e3f2fd", "#1565c0")):
            pg_az    = DatabaseForPostgresqlServers("Postgres\nFlex Server")
            redis_az = CacheForRedis("Azure Cache\nRedis")
            blob     = BlobStorage("Blob\nStorage")
            kv       = KeyVaults("Key Vault\n+  Workload Identity")

    # ── Row 3: Shared multi-cloud ─────────────────────────────────────────────
    with Cluster("Shared  ·  Multi-Cloud", graph_attr=cluster("#f3e5f5", "#6a1b9a")):
        neo4j = Neo4J("Neo4j  AuraDB\n(Graph DB  —  cross-cloud)")

    # ── Row 4: Monitoring ─────────────────────────────────────────────────────
    with Cluster("Monitoring  &  Observability", graph_attr=cluster("#fce4ec", "#880e4f")):
        otel = Jaeger("OpenTelemetry\nTracing")
        prom = Prometheus("Prometheus\nMetrics")
        graf = Grafana("Grafana\nDashboards")

    # ── Edges ─────────────────────────────────────────────────────────────────
    teal   = Edge(color="#00897b", style="bold",   penwidth="2.5")
    orange = Edge(color="#e65100", style="bold",   penwidth="2.0")
    blue   = Edge(color="#1565c0", style="bold",   penwidth="2.0")
    sec    = Edge(color="#6a1b9a", style="dashed", penwidth="1.5")
    obs    = Edge(color="#880e4f", style="dashed", penwidth="1.5")
    cicd   = Edge(color="#2e7d32", style="dashed", penwidth="1.5")

    # users → both load balancers (puts them in the same rank)
    [browser, ext_api] >> teal  >> alb
    [browser, ext_api] >> teal  >> az_lb

    # auth
    auth0 >> sec >> api_aws
    auth0 >> sec >> api_az

    # CI/CD → both clouds
    github >> cicd >> alb
    github >> cicd >> az_lb

    # LB → ingress → API
    alb   >> nginx_aws >> api_aws
    az_lb >> nginx_az  >> api_az

    # API → AI engines
    api_aws >> ray_aws
    ray_aws >> [vllm_aws, embed_aws]
    api_aws >> [qdrant_aws, sandbox_aws]

    api_az >> ray_az
    ray_az >> [vllm_az, embed_az]
    api_az >> [qdrant_az, sandbox_az]

    # API → managed
    api_aws >> [aurora, rcache, s3]
    sm      >> sec >> api_aws

    api_az >> [pg_az, redis_az, blob]
    kv     >> sec >> api_az

    # both → shared Neo4j (forces them to the same rank level)
    api_aws >> sec >> neo4j
    api_az  >> sec >> neo4j

    # both → monitoring (forces same rank level)
    api_aws >> obs >> otel
    api_az  >> obs >> otel
    otel >> prom >> graf

print("✅  Diagram saved → docs/images/00-rag-platform-overview.png")
