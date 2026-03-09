# services/data-plane/tests/conftest.py
"""
Shared fixtures for data plane tests.

Sets up Python path so both the data plane app (dp_app) and the
shared monolith code (app) are importable.

Key: "app" → services/api/app/ (shared code)
     "dp_app" → services/data-plane/app/ (data plane specific)
"""
import os
import sys
import importlib
import importlib.util

# Set env vars before any app imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("NEO4J_PASSWORD", "test")
os.environ.setdefault("ENV", "dev")

# Path setup
_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_api_dir = os.path.abspath(os.path.join(_base_dir, "..", "api"))
_dp_app_path = os.path.join(_base_dir, "app")
_api_app_path = os.path.join(_api_dir, "app")

# Put api dir on path so "app" submodule imports work
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

# ── Force "app" to resolve to services/api/app/ ──────────────────────────
# Pytest adds services/data-plane/ to sys.path which would cause
# "import app" to find services/data-plane/app/ (the wrong one).
# We explicitly register services/api/app/ in sys.modules so Python
# always uses it, regardless of sys.path ordering.
if "app" not in sys.modules:
    _app_init = os.path.join(_api_app_path, "__init__.py")
    _app_spec = importlib.util.spec_from_file_location(
        "app",
        _app_init,
        submodule_search_locations=[_api_app_path],
    )
    _app_mod = importlib.util.module_from_spec(_app_spec)
    sys.modules["app"] = _app_mod
    _app_spec.loader.exec_module(_app_mod)

# ── Register "dp_app" as a separate namespace for data-plane code ─────────
if "dp_app" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "dp_app",
        os.path.join(_dp_app_path, "__init__.py"),
        submodule_search_locations=[_dp_app_path],
    )
    dp_app = importlib.util.module_from_spec(spec)
    sys.modules["dp_app"] = dp_app
    spec.loader.exec_module(dp_app)

    # Register subpackage stubs so dp_app.auth.X works
    for sub in ["auth", "config", "routes", "registration"]:
        sub_path = os.path.join(_dp_app_path, sub)
        init_file = os.path.join(sub_path, "__init__.py")
        if os.path.isdir(sub_path) and os.path.isfile(init_file):
            sub_spec = importlib.util.spec_from_file_location(
                f"dp_app.{sub}",
                init_file,
                submodule_search_locations=[sub_path],
            )
            sub_mod = importlib.util.module_from_spec(sub_spec)
            sys.modules[f"dp_app.{sub}"] = sub_mod
            sub_spec.loader.exec_module(sub_mod)
