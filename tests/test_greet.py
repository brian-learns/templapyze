"""Tests for the greet CLI command and the Greeting model."""

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from templapyze.__main__ import Greeting, app

runner = CliRunner()


def test_greet_default() -> None:
    """greet greets the default name."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Hello from templapyze to world!" in result.output


def test_greet_named() -> None:
    """greet greets the given name."""
    result = runner.invoke(app, ["--name", "bob"])
    assert result.exit_code == 0
    assert "Hello from templapyze to bob!" in result.output


def test_greet_formal() -> None:
    """greet uses a formal salutation with --formal."""
    result = runner.invoke(app, ["--name", "bob", "--formal"])
    assert result.exit_code == 0
    assert "Good day from templapyze to bob!" in result.output


def test_greet_rejects_empty_name() -> None:
    """greet exits 1 and reports the validation error for an empty name."""
    result = runner.invoke(app, ["--name", "   "])
    assert result.exit_code == 1
    assert "String should have at least 1 character" in result.stderr


def test_name_is_stripped() -> None:
    """Greeting strips surrounding whitespace from the name."""
    assert Greeting(name="  bob  ").name == "bob"


def test_empty_name_rejected() -> None:
    """Greeting rejects an empty name."""
    with pytest.raises(ValidationError) as excinfo:
        Greeting(name="")
    assert "name" in excinfo.value.errors()[0]["loc"]
