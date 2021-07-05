#!/usr/bin/env python
import asyncio
import json
import logging
import sys
from functools import wraps
from typing import Optional, TextIO

import click
import uvloop
from rich.console import Console

from mtsync.connection import Connection
from mtsync.settings import Settings
from mtsync.synchronizer import Synchronizer


def wrap_coroutine(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uvloop.install()
        asyncio.run(f(*args, **kwargs))

    return wrapper


@click.command()
@click.option(
    "--hostname",
    default="192.168.88.1",
    help="Hostname/IP to connect to",
)
@click.option(
    "--username",
    default="admin",
    help="Username to authenticate as",
)
@click.option(
    "--password",
    type=str,
    default="",
    help="Password to autenticate with",
)
@click.option(
    "--desired-file",
    help="File to get the desired state from",
    type=click.File("r"),
    default=sys.stdin,
)
@click.option(
    "--ignore-certificate-errors",
    help="Whether to ignore SSL/TLS errors",
    is_flag=True,
    default=False,
)
@wrap_coroutine
async def main(
    hostname: Optional[str],
    username: Optional[str],
    password: Optional[str],
    desired_file: TextIO,
    ignore_certificate_errors: bool,
) -> None:
    console = Console()
    logging.basicConfig(level=logging.DEBUG)

    console.log("Loading desired configuration...")

    if desired_file == sys.stdin:
        console.log("Waiting on stdin")

    desired_tree = json.load(desired_file)

    if not isinstance(desired_tree, dict):
        console.log("[red]Expected the input data to be a dictionary/mapping.[/red]")
        sys.exit(-1)

    if not "metadata" in desired_tree:
        desired_tree["metadata"] = {}

    console.log("Desired config loaded.")

    console.log("Loading settings...")
    settings = Settings()
    settings.apply_environment_variables()
    settings.apply_arguments(
        hostname=hostname,
        username=username,
        password=password,
        ignore_certificate_errors=ignore_certificate_errors,
    )
    settings.apply_metadata(desired_tree["metadata"])

    if not settings.valid():
        console.log("Settings seem to be invalid.")
        sys.exit(-1)

    del desired_tree["metadata"]
    console.log("Settings loaded.")

    async with Connection(console=console, settings=settings) as connection:
        synchronizer = Synchronizer(
            console=console,
            connection=connection,
        )

        await synchronizer.run(
            desired_tree=desired_tree,
        )


if __name__ == "__main__":
    main()
