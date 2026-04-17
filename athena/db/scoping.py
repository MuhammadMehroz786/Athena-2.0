from sqlalchemy import Select


def scoped(stmt: Select, model, *, tenant_id: str) -> Select:
    """Every tenant-data query MUST go through this helper.

    Missing or empty tenant_id raises — the default is never 'all tenants'.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for scoped queries")
    if not hasattr(model, "tenant_id"):
        raise ValueError(f"{model.__name__} has no tenant_id column")
    return stmt.where(model.tenant_id == tenant_id)
