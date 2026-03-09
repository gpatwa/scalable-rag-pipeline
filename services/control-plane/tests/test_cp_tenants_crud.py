# services/control-plane/tests/test_cp_tenants_crud.py
"""
Control Plane tenant CRUD tests using in-memory SQLite.

Run with:
    pytest services/control-plane/tests/test_cp_tenants_crud.py -v
"""
import pytest


# db_session fixture provided by conftest.py


class TestTenantModel:
    """Tests for the Tenant SQLAlchemy model."""

    def test_tenant_has_required_columns(self):
        from app.models.tenant import Tenant

        columns = {c.name for c in Tenant.__table__.columns}
        expected = {"id", "name", "plan", "enabled", "rate_limit_rpm", "storage_quota_mb"}
        assert expected.issubset(columns)

    def test_tenant_column_defaults(self):
        """Column defaults are applied at INSERT time — verify columns have defaults configured."""
        from app.models.tenant import Tenant

        col_plan = Tenant.__table__.columns["plan"]
        col_enabled = Tenant.__table__.columns["enabled"]
        col_rpm = Tenant.__table__.columns["rate_limit_rpm"]
        col_storage = Tenant.__table__.columns["storage_quota_mb"]

        assert col_plan.default.arg == "free"
        assert col_enabled.default.arg is True
        assert col_rpm.default.arg == 60
        assert col_storage.default.arg == 0

    @pytest.mark.asyncio
    async def test_create_tenant_in_db(self, db_session):
        from app.models.tenant import Tenant
        from sqlalchemy import select

        async with db_session() as session:
            async with session.begin():
                tenant = Tenant(id="t1", name="Acme Corp", plan="enterprise")
                session.add(tenant)

        async with db_session() as session:
            result = await session.execute(select(Tenant).where(Tenant.id == "t1"))
            tenant = result.scalars().first()
            assert tenant is not None
            assert tenant.name == "Acme Corp"
            assert tenant.plan == "enterprise"
            assert tenant.enabled is True

    @pytest.mark.asyncio
    async def test_update_tenant(self, db_session):
        from app.models.tenant import Tenant
        from sqlalchemy import select

        async with db_session() as session:
            async with session.begin():
                session.add(Tenant(id="t2", name="Beta Inc"))

        async with db_session() as session:
            async with session.begin():
                result = await session.execute(select(Tenant).where(Tenant.id == "t2"))
                tenant = result.scalars().first()
                tenant.plan = "starter"
                tenant.rate_limit_rpm = 120

        async with db_session() as session:
            result = await session.execute(select(Tenant).where(Tenant.id == "t2"))
            tenant = result.scalars().first()
            assert tenant.plan == "starter"
            assert tenant.rate_limit_rpm == 120

    @pytest.mark.asyncio
    async def test_disable_tenant(self, db_session):
        from app.models.tenant import Tenant
        from sqlalchemy import select

        async with db_session() as session:
            async with session.begin():
                session.add(Tenant(id="t3", name="Gamma LLC"))

        async with db_session() as session:
            async with session.begin():
                result = await session.execute(select(Tenant).where(Tenant.id == "t3"))
                tenant = result.scalars().first()
                tenant.enabled = False

        async with db_session() as session:
            result = await session.execute(select(Tenant).where(Tenant.id == "t3"))
            tenant = result.scalars().first()
            assert tenant.enabled is False

    @pytest.mark.asyncio
    async def test_list_tenants(self, db_session):
        from app.models.tenant import Tenant
        from sqlalchemy import select

        async with db_session() as session:
            async with session.begin():
                session.add(Tenant(id="a1", name="Alpha"))
                session.add(Tenant(id="b1", name="Bravo"))
                session.add(Tenant(id="c1", name="Charlie"))

        async with db_session() as session:
            result = await session.execute(select(Tenant))
            tenants = result.scalars().all()
            assert len(tenants) == 3
            names = {t.name for t in tenants}
            assert names == {"Alpha", "Bravo", "Charlie"}


class TestTenantRequestModels:
    """Tests for Pydantic request/response models."""

    def test_tenant_create_defaults(self):
        from app.routes.tenants import TenantCreate

        req = TenantCreate(name="Test Corp")
        assert req.plan == "free"
        assert req.rate_limit_rpm == 60
        assert req.storage_quota_mb == 0

    def test_tenant_update_partial(self):
        from app.routes.tenants import TenantUpdate

        req = TenantUpdate(name="New Name")
        assert req.name == "New Name"
        assert req.plan is None
        assert req.enabled is None
        assert req.rate_limit_rpm is None

    def test_tenant_response_model(self):
        from app.routes.tenants import TenantResponse

        resp = TenantResponse(
            id="t1", name="Acme", plan="enterprise",
            enabled=True, rate_limit_rpm=100, storage_quota_mb=1024,
        )
        assert resp.id == "t1"
        assert resp.plan == "enterprise"
