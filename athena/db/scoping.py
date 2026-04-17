from sqlalchemy import Select
from sqlalchemy.orm.attributes import InstrumentedAttribute


def scoped(stmt: Select, model, *, tenant_id: str) -> Select:
    """Every tenant-data query MUST go through this helper.

    Missing/empty tenant_id, a non-class `model`, or a model whose `tenant_id`
    isn't a mapped column raises — the default is never 'all tenants'.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for scoped queries")
    if not isinstance(model, type):
        raise ValueError("model must be a class, not an instance")
    col = getattr(model, "tenant_id", None)
    if not isinstance(col, InstrumentedAttribute):
        raise ValueError(f"{model.__name__} has no mapped tenant_id column")
    return stmt.where(col == tenant_id)
