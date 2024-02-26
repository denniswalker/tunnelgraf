import click
from tunnelgraf.tunnels import Tunnels
from io import TextIOWrapper
from importlib.metadata import version


@click.group()
@click.version_option(
    package_name="tunnelgraf", prog_name="tunnelgraf", version=version("tunnelgraf")
)
@click.pass_context
def cli(ctx) -> None:
    pass


@cli.command(
    help="Connect to the remote tunnels defined in a connection profile. Requires an argument containing the path to the connection profile, e.g `tunnelgraf connect <tunnelfile.yml>"
)
@click.argument("config_file", envvar="TUNNELGRAF_CONFIG", type=click.File("r"))
def connect(config_file: TextIOWrapper) -> None:
    Tunnels(config_file)
