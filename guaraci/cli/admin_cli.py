"""Administração do Guaraci hospedado pela linha de comando.

Opera direto no banco de contas (``GUARACI_DB_PATH``), sem passar pela API.
Serve para criar o primeiro administrador e para destravar contas.
"""

from __future__ import annotations

from typing import Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _accounts():
    from guaraci.hosted.accounts import Accounts
    from guaraci.hosted.db import Database
    from guaraci.hosted.settings import HostedSettings

    settings = HostedSettings.from_env()
    return Accounts(Database(settings.db_path)), settings


def _find(accounts, email: str):
    user = accounts.get_by_email(email)
    if user is None:
        raise click.ClickException(f"Não há conta com o e-mail {email}.")
    return user


@click.group()
def admin() -> None:
    """Contas do Guaraci hospedado (criar administrador, aprovar, listar)."""


@admin.command("create")
@click.option("--email", required=True)
@click.option("--name", default="Administração")
@click.option("--institution", default="")
@click.password_option(help="Senha (pedida no terminal se omitida).")
def create(email: str, name: str, institution: str, password: str) -> None:
    """Cria uma conta de administrador já aprovada."""
    from guaraci.hosted.accounts import AccountError

    accounts, settings = _accounts()
    try:
        user = accounts.register(
            email=email,
            name=name,
            institution=institution,
            purpose="administração",
            password=password,
            consent_version=settings.privacy_version,
            role="admin",
            status="approved",
        )
    except AccountError as exc:
        raise click.ClickException(str(exc)) from exc
    if user is None:
        raise click.ClickException("Já existe conta com esse e-mail. Use 'guaraci admin promote'.")
    console.print(f"Administrador criado: {user.email} (id {user.id})")


@admin.command("list")
@click.option("--status", type=click.Choice(["pending", "approved", "rejected", "disabled"]))
def list_users(status: Optional[str]) -> None:
    """Lista as contas, opcionalmente por situação."""
    accounts, _ = _accounts()
    table = Table("id", "e-mail", "nome", "instituição", "papel", "situação", "criada em")
    for user in accounts.list(status):
        table.add_row(
            str(user.id),
            user.email,
            user.name,
            user.institution or "",
            user.role,
            user.status,
            (user.created_at or "")[:16],
        )
    console.print(table)


@admin.command("approve")
@click.argument("email")
def approve(email: str) -> None:
    """Aprova uma conta pendente."""
    accounts, _ = _accounts()
    user = accounts.set_status(_find(accounts, email).id, "approved")
    console.print(f"Aprovada: {user.email}")


@admin.command("disable")
@click.argument("email")
def disable(email: str) -> None:
    """Bloqueia uma conta e encerra as sessões dela."""
    accounts, _ = _accounts()
    user = accounts.set_status(_find(accounts, email).id, "disabled")
    console.print(f"Bloqueada: {user.email}")


@admin.command("promote")
@click.argument("email")
def promote(email: str) -> None:
    """Dá papel de administrador a uma conta existente."""
    accounts, _ = _accounts()
    user = accounts.set_role(_find(accounts, email).id, "admin")
    console.print(f"Agora é administrador: {user.email}")


@admin.command("backup")
@click.argument("destino", type=click.Path(dir_okay=False))
def backup(destino: str) -> None:
    """Copia o banco de contas e registros com o serviço no ar (backup online do SQLite)."""
    from guaraci.hosted.db import Database
    from guaraci.hosted.settings import HostedSettings

    db = Database(HostedSettings.from_env().db_path)
    try:
        db.backup_to(destino)
    finally:
        db.close()
    console.print(f"Backup gravado em {destino}")


@admin.command("set-password")
@click.argument("email")
@click.password_option()
def set_password(email: str, password: str) -> None:
    """Troca a senha de uma conta e encerra as sessões abertas."""
    from guaraci.hosted.accounts import AccountError

    accounts, _ = _accounts()
    user = _find(accounts, email)
    try:
        accounts.set_password(user.id, password)
    except AccountError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"Senha trocada: {user.email}")
