import pytest
from sf_mcp import soql


def test_escape_quote():
    assert soql.escape("O'Brien") == "O\\'Brien"
    assert soql.escape("\\'") == "\\\\\\'"


@pytest.mark.parametrize("bad", ["' OR Id != null --", "a%", "a_b", "", "x" * 81, "a\nb"])
def test_text_rejects_injection_and_wildcards(bad):
    with pytest.raises(soql.InvalidInput):
        soql.text(bad)


def test_text_allows_names_and_email():
    assert soql.text("O'Brien") == "O'Brien"
    assert soql.text("maria.lopez@example.com")


@pytest.mark.parametrize("bad", ["123", "0035g00000AbCdE' OR '1'='1", None])
def test_sf_id_rejects(bad):
    with pytest.raises(soql.InvalidInput):
        soql.sf_id(bad)


def test_sf_id_accepts_15_and_18():
    assert soql.sf_id("0035g00000AbCdE")
    assert soql.sf_id("0035g00000AbCdEAAA")


def test_iso_date():
    assert soql.iso_date("2026-09-29") == "2026-09-29"
    with pytest.raises(soql.InvalidInput):
        soql.iso_date("2026-09-29 OR 1=1")


def test_clamp_limit():
    assert soql.clamp_limit(None, 10, 25) == 10
    assert soql.clamp_limit(999, 10, 25) == 25
    assert soql.clamp_limit(0, 10, 25) == 1


@pytest.mark.parametrize("good", ["barr_tim@grandhotels.com", "o'brien@x.org", "a+b@x.io"])
def test_email_accepts_common_forms(good):
    assert soql.email(good) == good


@pytest.mark.parametrize("bad", ["", "nope", "a@b", "x@y.com' OR '1'='1", "a b@x.com", "a@x.com\n.evil"])
def test_email_rejects_garbage_and_injection(bad):
    with pytest.raises(soql.InvalidInput):
        soql.email(bad)


def test_email_strips_surrounding_whitespace_only():
    assert soql.email(" a@x.com\n") == "a@x.com"
