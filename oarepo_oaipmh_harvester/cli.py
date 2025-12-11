#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""OAI-PMH Harvester CLI commands."""

from __future__ import annotations

import json
import textwrap
from typing import Any

import click
from flask.cli import with_appcontext
from invenio_access.permissions import system_identity
from invenio_accounts.models import User
from invenio_db import db
from rich.console import Console
from rich.table import Table

from oarepo_oaipmh_harvester.oai_harvester.models import OAIHarvester
from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service


def indented_json(data: Any) -> str:
    """Convert data to indented JSON string with proper indentation."""
    json_str = json.dumps(data, indent=2)
    return textwrap.indent(json_str, "  ")


def lookup_user(user_email: str) -> str:
    """Lookup user ID by email and return the user ID."""
    user = db.session.query(User).filter_by(email=user_email).one()
    return str(user.id)


@click.group(name="oai")
def oai_cli() -> None:
    """OAI-PMH harvesting commands."""


@oai_cli.group("harvesters")
def harvesters_cli() -> None:
    """Management of OAI PMH harvesters."""  # noqa: D401


@harvesters_cli.command("list")
@click.option("--json-output", "--json", is_flag=True, help="Output as JSON")
@with_appcontext
def list_harvesters(json_output: bool) -> None:
    """List all OAI-PMH harvesters."""
    harvesters = db.session.query(OAIHarvester).all()

    if json_output:
        # JSON output
        data = [
            {
                "id": harvester.id,
                "name": harvester.name,
                "base_url": harvester.base_url,
                "metadata_prefix": harvester.metadata_prefix,
                "setspec": harvester.setspec,
                "loader": harvester.loader,
                "transformers": harvester.transformers,
                "writers": harvester.writers,
                "harvest_managers": harvester.harvest_managers,
                "comment": harvester.comment,
                "created": (harvester.created.isoformat() if harvester.created else None),
                "updated": (harvester.updated.isoformat() if harvester.updated else None),
            }
            for harvester in harvesters
        ]
        click.echo(json.dumps(data, indent=2))
    else:
        # Table output using rich
        if not harvesters:
            click.echo("No harvesters found.")
            return

        console = Console()

        # Main table
        table = Table(title="OAI-PMH Harvesters", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Base URL", style="blue")
        table.add_column("Metadata Prefix")
        table.add_column("Set")
        table.add_column("Comment", max_width=50)

        for harvester in harvesters:
            table.add_row(
                str(harvester.id),
                str(harvester.name),
                str(harvester.base_url),
                str(harvester.metadata_prefix),
                str(harvester.setspec or ""),
                str(harvester.comment or ""),
            )

        console.print(table)

        # Additional details
        console.print("\n[bold]Additional Details:[/bold]")
        for harvester in harvesters:
            console.print(f"\n[bold cyan]Harvester:[/bold cyan] {harvester.name} (ID: {harvester.id})")
            console.print(f"  [yellow]Loader:[/yellow] {harvester.loader}")
            console.print(f"  [yellow]Transformers:[/yellow] {indented_json(harvester.transformers)}")
            console.print(f"  [yellow]Writers:[/yellow] {indented_json(harvester.writers)}")
            console.print(f"  [yellow]Harvest Managers:[/yellow] {indented_json(harvester.harvest_managers)}")
            console.print(f"  [yellow]Created:[/yellow] {harvester.created}")
            console.print(f"  [yellow]Updated:[/yellow] {harvester.updated}")


@harvesters_cli.command("create")
@click.option("--id", required=True, help="Harvester ID")
@click.option("--name", required=True, help="Harvester name")
@click.option("--base-url", required=True, help="OAI-PMH base URL")
@click.option("--metadata-prefix", required=True, help="Metadata prefix (e.g., oai_dc)")
@click.option("--setspec", default="", help="Set specification")
@click.option("--loader", default="oai-pmh", help="Loader definition (default: oai-pmh)")
@click.option("--model", help="Model name (automatically sets transformers and writers)")
@click.option(
    "--transformer",
    multiple=True,
    help="Transformer (can be specified multiple times, overrides --model)",
)
@click.option(
    "--writer",
    multiple=True,
    help="Writer (can be specified multiple times, overrides --model)",
)
@click.option(
    "--harvest-manager",
    multiple=True,
    help="Harvest manager user email (can be specified multiple times)",
)
@click.option("--comment", default="", help="Comment")
@with_appcontext
def create_harvester(  # noqa: PLR0913  # many parameters
    id: str,  # noqa: A002 # shadows built-in
    name: str,
    base_url: str,
    metadata_prefix: str,
    setspec: str,
    loader: str,
    model: str | None,
    transformer: tuple[str, ...],
    writer: tuple[str, ...],
    harvest_manager: tuple[str, ...],
    comment: str,
) -> None:
    """Create a new OAI-PMH harvester."""
    # Handle model option to auto-generate transformers and writers
    transformers = list(transformer)
    writers = list(writer)

    if model:
        if not transformers:
            transformers = [f'oai-import{{model:"{model}"}}']
        if not writers:
            writers = [f'oai-service{{model:"{model}",update:true}}']

    harvester_data = {
        "id": id,
        "name": name,
        "base_url": base_url,
        "metadata_prefix": metadata_prefix,
        "setspec": setspec,
        "loader": loader,
        "transformers": transformers,
        "writers": writers,
        "harvest_managers": [{"user": lookup_user(email)} for email in harvest_manager],
        "comment": comment,
    }

    try:
        current_oai_harvester_service.create(system_identity, harvester_data)
        db.session.commit()
        current_oai_harvester_service.indexer.refresh()

        console = Console()
        console.print(f"[green]✓[/green] Harvester '{name}' created successfully with ID: {id}")
    except Exception as e:
        db.session.rollback()
        click.echo(f"Error creating harvester: {e}", err=True)
        raise


@harvesters_cli.command("update")
@click.argument("harvester_id")
@click.option("--name", help="Harvester name")
@click.option("--base-url", help="OAI-PMH base URL")
@click.option("--metadata-prefix", help="Metadata prefix (e.g., oai_dc)")
@click.option("--setspec", help="Set specification")
@click.option("--loader", help="Loader definition")
@click.option("--model", help="Model name (automatically sets transformers and writers)")
@click.option(
    "--transformer",
    multiple=True,
    help="Transformer (can be specified multiple times, replaces all, overrides --model)",
)
@click.option(
    "--writer",
    multiple=True,
    help="Writer (can be specified multiple times, replaces all, overrides --model)",
)
@click.option(
    "--harvest-manager",
    multiple=True,
    help="Harvest manager user email (can be specified multiple times, replaces all)",
)
@click.option("--comment", help="Comment")
@with_appcontext
def update_harvester(  # noqa: PLR0913  # many parameters
    harvester_id: str,
    name: str | None,
    base_url: str | None,
    metadata_prefix: str | None,
    setspec: str | None,
    loader: str | None,
    model: str | None,
    transformer: tuple[str, ...],
    writer: tuple[str, ...],
    harvest_manager: tuple[str, ...],
    comment: str | None,
) -> None:
    """Update an existing OAI-PMH harvester."""

    def set_if_provided(field: str, value: Any, data: dict[str, Any]) -> None:
        if value is not None and value not in ([], ()):
            data[field] = value

    try:
        # Read existing harvester
        update_data = current_oai_harvester_service.read(system_identity, harvester_id).to_dict()

        # Handle model option to auto-generate transformers and writers
        transformers = list(transformer)
        writers = list(writer)

        if model:
            if not transformers:
                transformers = [f'oai-import{{model:"{model}"}}']
            if not writers:
                writers = [f'oai-service{{model:"{model}",update:true}}']

        if name is not None:
            update_data["name"] = name

        set_if_provided("base_url", base_url, update_data)
        set_if_provided("metadata_prefix", metadata_prefix, update_data)
        set_if_provided("setspec", setspec, update_data)
        set_if_provided("loader", loader, update_data)
        set_if_provided("transformers", transformers, update_data)
        set_if_provided("writers", writers, update_data)
        set_if_provided(
            "harvest_managers",
            [{"user": lookup_user(email)} for email in harvest_manager],
            update_data,
        )
        set_if_provided("comment", comment, update_data)

        current_oai_harvester_service.update(system_identity, harvester_id, update_data)
        db.session.commit()
        current_oai_harvester_service.indexer.refresh()

        console = Console()
        console.print(f"[green]✓[/green] Harvester '{harvester_id}' updated successfully")
    except Exception as e:
        db.session.rollback()
        click.echo(f"Error updating harvester: {e}", err=True)
        raise


@harvesters_cli.command("delete")
@click.argument("harvester_id")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@with_appcontext
def delete_harvester(harvester_id: str, yes: bool) -> None:
    """Delete an OAI-PMH harvester."""
    if not yes:
        click.confirm(
            f"Are you sure you want to delete harvester '{harvester_id}'?",
            abort=True,
        )

    try:
        current_oai_harvester_service.delete(system_identity, harvester_id)
        db.session.commit()
        current_oai_harvester_service.indexer.refresh()

        console = Console()
        console.print(f"[green]✓[/green] Harvester '{harvester_id}' deleted successfully")
    except Exception as e:
        db.session.rollback()
        click.echo(f"Error deleting harvester: {e}", err=True)
        raise
