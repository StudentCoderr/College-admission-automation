"""The read-only `db-check` diagnostic.

It reports the live schema and row counts so an empty-looking catalogue can be
traced to an empty ``courses`` table or to columns the live database is still
missing (an un-applied migration). It must never write anything and must fail
clearly when Supabase is unreachable/unconfigured.
"""


def _run(app):
    return app.test_cli_runner().invoke(args=["db-check"])


def test_db_check_reports_tables_columns_and_counts(app):
    result = _run(app)

    assert result.exit_code == 0, result.output
    assert "Tables and columns:" in result.output
    assert "courses" in result.output
    assert "users" in result.output
    assert "applications" in result.output
    # The conftest seeds one course; the schema is the modern one.
    assert "courses schema is up to date." in result.output
    assert "no rows yet" not in result.output


def test_db_check_warns_when_course_columns_are_missing(app):
    app.supabase.simulate_legacy_courses_schema()

    result = _run(app)

    assert result.exit_code == 0, result.output
    assert "courses is missing" in result.output
    assert "program_type" in result.output
    assert "eligible_qualifications" in result.output
    assert "sql/schema.sql" in result.output


def test_db_check_notes_an_empty_catalogue(app):
    app.supabase.courses.clear()

    result = _run(app)

    assert result.exit_code == 0, result.output
    assert "courses has no rows yet" in result.output
    assert "/admin/courses" in result.output


def test_db_check_fails_clearly_when_schema_unavailable(app):
    # Simulate an unreachable/unconfigured backend: no schema can be read.
    app.supabase.describe_schema = lambda: {}

    result = _run(app)

    assert result.exit_code == 1
    assert "Could not read the live schema" in result.output


def test_db_check_warns_when_name_columns_are_missing(app):
    app.supabase.simulate_legacy_users_schema()
    app.supabase.simulate_legacy_applications_schema()

    result = _run(app)

    assert result.exit_code == 0, result.output
    assert "users is missing" in result.output
    assert "first_name" in result.output
    assert "applications is missing: middle_name" in result.output
    assert "sql/upgrade_application_names.sql" in result.output
