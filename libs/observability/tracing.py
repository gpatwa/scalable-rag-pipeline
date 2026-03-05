# libs/observability/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
# In prod, import OTLPSpanExporter to send to Datadog/Jaeger

def configure_tracing(service_name: str):
    """
    Sets up OpenTelemetry tracing.
    """
    # 1. Create Tracer Provider
    provider = TracerProvider()
    
    # 2. Configure Exporter
    # For dev: Print to console. 
    # For prod: Send to OTLP collector (e.g., Jaeger/Grafana)
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    
    # 3. Set Global Tracer
    trace.set_tracer_provider(provider)
    
    return trace.get_tracer(service_name)

def get_current_span_id():
    """Helper to get current trace ID for logging correlation"""
    span = trace.get_current_span()
    if span:
        return span.get_span_context().trace_id
    return None