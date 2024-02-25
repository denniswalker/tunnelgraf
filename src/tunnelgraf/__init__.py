import click
from tunnelgraf.tunnels import Tunnels
from io import TextIOWrapper
import tomllib


with open("pyproject.toml", "rb") as f:
    app_data = tomllib.load(f)["project"]


@click.group()
@click.version_option(
    package_name=app_data["name"],
    prog_name=app_data["name"],
    version=app_data["version"],
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
