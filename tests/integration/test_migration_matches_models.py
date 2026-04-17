import pytest
from sqlalchemy import create_engine, inspect
from athena.db.base import Base
from athena.db import models  # noqa: F401


def _run_migration_on_sqlite(engine):
    # Import the migration module and invoke upgrade() with op bound to this engine.
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op_proxy = Operations(ctx)
        import alembic.op as op_mod
        original_proxy = op_mod.__dict__.get("_proxy", _SENTINEL)
        op_mod._proxy = op_proxy
        try:
            import importlib.util, pathlib
            mig_path = pathlib.Path(__file__).resolve().parent.parent.parent / "alembic" / "versions" / "0001_initial.py"
            spec = importlib.util.spec_from_file_location("mig_0001", mig_path)
            mig = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mig)
            mig.upgrade()
            conn.commit()
        finally:
            if original_proxy is _SENTINEL:
                # _proxy did not exist before; remove the attribute we added
                op_mod.__dict__.pop("_proxy", None)
            else:
                op_mod._proxy = original_proxy


_SENTINEL = object()


def test_migration_produces_same_tables_as_models(tmp_path):
    # Apply the migration to a fresh SQLite file database.
    db_file = tmp_path / "mig.db"
    mig_engine = create_engine(f"sqlite:///{db_file}")
    _run_migration_on_sqlite(mig_engine)

    # Build reference schema from models into a separate SQLite.
    ref_file = tmp_path / "ref.db"
    ref_engine = create_engine(f"sqlite:///{ref_file}")
    Base.metadata.create_all(ref_engine)

    mig_insp = inspect(mig_engine)
    ref_insp = inspect(ref_engine)

    assert set(mig_insp.get_table_names()) == set(ref_insp.get_table_names())

    for table in sorted(ref_insp.get_table_names()):
        mig_cols = {c["name"] for c in mig_insp.get_columns(table)}
        ref_cols = {c["name"] for c in ref_insp.get_columns(table)}
        assert mig_cols == ref_cols, f"column mismatch on {table}"

        mig_uq = {u["name"] for u in mig_insp.get_unique_constraints(table)}
        ref_uq = {u["name"] for u in ref_insp.get_unique_constraints(table)}
        assert mig_uq == ref_uq, f"unique-constraint mismatch on {table}: mig={mig_uq} ref={ref_uq}"

        mig_ix = {i["name"] for i in mig_insp.get_indexes(table)}
        ref_ix = {i["name"] for i in ref_insp.get_indexes(table)}
        assert mig_ix == ref_ix, f"index mismatch on {table}: mig={mig_ix} ref={ref_ix}"
