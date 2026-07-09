"""Kaydan Shield Local Agent — CLI d'entrée.

Usage :
    kshield-agent run --config ~/.kshield-agent.toml
    kshield-agent doctor       # vérifie config + connectivité
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import click

from .client import AgentClient
from .config import AgentConfig


@click.group()
@click.version_option("0.1.0")
def cli():
    """Kaydan Shield — Agent local."""


@cli.command()
@click.option("--server-url", envvar="KSHIELD_SERVER_URL",
                help="URL du serveur Kaydan Shield.")
@click.option("--token", envvar="KSHIELD_ACTIVATION_TOKEN",
                help="Token d'activation à usage unique.")
@click.option("--config", "-c", default=None)
def activate(server_url, token, config):
    """Appaire le Gateway avec le serveur cloud (première installation)."""
    from .bootstrap import activate as do_activate
    try:
        cfg = do_activate(server_url=server_url, activation_token=token,
                           cfg_path=config)
    except RuntimeError as exc:
        click.secho(f"[KO] {exc}", fg="red")
        sys.exit(1)
    click.secho(f"[OK] Gateway activé — id={cfg.agent_id}", fg="green")
    click.echo(f"Config écrite dans {config or '~/.kshield-agent.toml'}")
    click.echo("Lancer maintenant : kshield-agent run")


@cli.command()
@click.option("--config", "-c", default=None, help="Chemin du fichier TOML.")
def run(config):
    """Démarre l'agent en écoute permanente."""
    from .bootstrap import needs_activation

    # Activation auto au premier démarrage si les env sont fournis
    if needs_activation(config):
        server = os.environ.get("KSHIELD_SERVER_URL")
        token = os.environ.get("KSHIELD_ACTIVATION_TOKEN")
        if server and token:
            from .bootstrap import activate as do_activate
            try:
                do_activate(server_url=server, activation_token=token, cfg_path=config)
                click.secho("[OK] Activation auto réussie", fg="green")
            except RuntimeError as exc:
                click.secho(f"[FATAL] Activation impossible : {exc}", fg="red")
                sys.exit(1)

    try:
        cfg = AgentConfig.load(config)
    except FileNotFoundError as e:
        click.echo(f"[FATAL] {e}", err=True)
        sys.exit(1)

    logging.basicConfig(
        level=cfg.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    )
    click.echo(f"[BOOT] Agent {cfg.agent_id} → {cfg.server_url}")
    click.echo(f"[BOOT] {len(cfg.readers)} lecteurs configurés")

    agent = AgentClient(cfg)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(*_):
        click.echo("\n[STOP] shutdown demandé")
        loop.create_task(agent.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:  # Windows
            signal.signal(sig, _shutdown)

    try:
        loop.run_until_complete(agent.run())
    finally:
        loop.close()
    click.echo("[BYE]")


@cli.command()
@click.option("--config", "-c", default=None)
def doctor(config):
    """Vérifie la config et la connectivité serveur."""
    import httpx

    from .offline_queue import DEFAULT_QUEUE_PATH, OfflineQueue

    cfg = AgentConfig.load(config)
    click.echo(f"Server URL : {cfg.server_url}")
    click.echo(f"WS URL     : {cfg.ws_url}")
    click.echo(f"Lecteurs   : {len(cfg.readers)}")

    # Test HTTP simple
    try:
        r = httpx.get(f"{cfg.http_base}/devices/agent/{cfg.agent_id}/commands/",
                        headers={"Authorization": f"Bearer {cfg.api_token}"},
                        timeout=5)
        if r.status_code == 200:
            click.secho("[OK]  HTTP /agent/commands/ répond", fg="green")
        elif r.status_code == 401:
            click.secho("[KO]  Token agent invalide (401)", fg="red")
        else:
            click.secho(f"[??]  HTTP {r.status_code}: {r.text[:200]}", fg="yellow")
    except Exception as e:
        click.secho(f"[KO]  HTTP inaccessible : {e}", fg="red")

    # État de la queue offline
    queue = OfflineQueue(DEFAULT_QUEUE_PATH)
    stats = queue.stats()
    if stats["pending"]:
        click.secho(f"[!!]  Queue offline : {stats['pending']} événements en attente",
                     fg="yellow")
    if stats["dead"]:
        click.secho(f"[KO]  Queue offline : {stats['dead']} événements morts "
                     f"(>10 échecs)", fg="red")


@cli.command()
def queue_status():
    """Affiche l'état de la queue offline (SQLite)."""
    from .offline_queue import DEFAULT_QUEUE_PATH, OfflineQueue

    queue = OfflineQueue(DEFAULT_QUEUE_PATH)
    stats = queue.stats()
    click.echo(f"Total   : {stats['total']}")
    click.echo(f"Pending : {stats['pending']}")
    click.echo(f"Dead    : {stats['dead']}")
    if stats["pending"] or stats["dead"]:
        preview = queue.peek(limit=5)
        click.echo("\n5 prochains événements :")
        for e in preview:
            click.echo(f"  #{e['id']} · {e['topic']} · attempts={e['attempts']} "
                        f"· {e['created_at']}")


@cli.command()
@click.confirmation_option(prompt="Purger tous les événements morts ?")
def queue_purge_dead():
    """Purge les événements morts (dead=1) après investigation."""
    from .offline_queue import DEFAULT_QUEUE_PATH, OfflineQueue
    OfflineQueue(DEFAULT_QUEUE_PATH).drain_dead()
    click.secho("[OK] Dead letters purgés", fg="green")


def main():
    cli()


if __name__ == "__main__":
    main()
