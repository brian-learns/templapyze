"""Minimal typer + pydantic example: typer parses args, pydantic validates and renders."""

import typer
from pydantic import BaseModel, Field, ValidationError, field_validator

app = typer.Typer()


class Greeting(BaseModel):
    """A greeting, validated and rendered by pydantic."""

    name: str = Field(min_length=1)
    formal: bool = False

    @field_validator("name", mode="before")
    def normalize_name(name: str) -> str:  # noqa: N805 -- pydantic validator, not a method
        """Strip surrounding whitespace from the name."""
        return name.strip()

    def render(self) -> str:
        """Format the greeting for output."""
        salutation = "Good day" if self.formal else "Hello"
        return f"{salutation} from templapyze to {self.name}!"


@app.command()
def greet(
    name: str = typer.Option("world", help="Who to greet."),
    formal: bool = typer.Option(False, help="Use a formal salutation."),
) -> None:
    """Greet someone by name."""
    try:
        greeting = Greeting(name=name, formal=formal)
    except ValidationError as err:
        typer.echo(err, err=True)
        raise typer.Exit(code=1) from err
    typer.echo(greeting.render())


def main() -> None:
    """Entry point for the `templapyze` command and `python -m templapyze`."""
    app()


if __name__ == "__main__":
    main()
