"""`flask seed-courses` inserts the bundled catalogue idempotently."""

from app.data.courses import DEFAULT_COURSES


def _run(app):
    return app.test_cli_runner().invoke(args=["seed-courses"])


def test_seed_courses_inserts_every_default_course(app):
    fake = app.config["FAKE"]
    fake.courses.clear()

    result = _run(app)

    assert result.exit_code == 0, result.output
    assert "{} added".format(len(DEFAULT_COURSES)) in result.output
    codes = {c["code"] for c in fake.list_courses()}
    assert codes == {c["code"] for c in DEFAULT_COURSES}


def test_seed_courses_is_idempotent_and_preserves_edits(app):
    fake = app.config["FAKE"]
    fake.courses.clear()
    assert _run(app).exit_code == 0

    # Simulate an administrator editing a course after the first seed.
    first = fake.list_courses()[0]
    fake.update_course(first["id"], {"seats_total": 999})

    result = _run(app)

    assert result.exit_code == 0, result.output
    assert "0 added" in result.output
    assert len(fake.list_courses()) == len(DEFAULT_COURSES)
    edited = next(c for c in fake.list_courses() if c["id"] == first["id"])
    assert edited["seats_total"] == 999
