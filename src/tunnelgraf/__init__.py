import click
from tunnelgraf.tunnels import Tunnels
from io import TextIOWrapper
from importlib.metadata import version
import sys
import json


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


@cli.command(help="Print the resulting tunnels configuration w/o connecting.")
@click.argument("config_file", envvar="TUNNELGRAF_CONFIG", type=click.File("r"))
@click.option(
    "--tunnel-id",
    "-t",
    help="Print the resulting configuration of the specified tunnel id.",
    default=None,
)
@click.option(
    "--show-credentials",
    help="Print the credentials used when connecting. Default: false",
    is_flag=True,
    default=False,
)
def show(config_file: TextIOWrapper, tunnel_id: str, show_credentials: bool) -> None:
    tunnels = Tunnels(
        config_file, connect_tunnels=False, show_credentials=show_credentials
    ).tunnel_configs
    if tunnel_id:
        try:
            this_tunnel = [tunnel for tunnel in tunnels if tunnel_id == tunnel["id"]][0]
        except IndexError:
            print(f"Tunnel id {tunnel_id} not found.")
            sys.exit(1)
        print(json.dumps(this_tunnel))
    else:
        print(json.dumps(tunnels))


@cli.command(
    help="Print the URLs to access each tunnel. Protocol is displayed as ssh unless specified."
)
@click.argument("config_file", envvar="TUNNELGRAF_CONFIG", type=click.File("r"))
def urls(config_file: TextIOWrapper) -> None:
    tunnels = Tunnels(config_file, connect_tunnels=False).tunnel_configs
    links: dict = {}
    for tunnel in tunnels:
        links[tunnel["id"]]: list = []
        if "hosts_file_entry" in tunnel.keys() and tunnel["hosts_file_entry"]:
            host = tunnel["hosts_file_entry"]
            links[tunnel["id"]].append(
                f"{tunnel['protocol']}://{host}:{tunnel['port']}"
            )
        elif "hosts_file_entries" in tunnel.keys() and tunnel["hosts_file_entries"]:
            for hosts_entry in tunnel["hosts_file_entries"]:
                links[tunnel["id"]].append(
                    f"{tunnel['protocol']}://{hosts_entry}:{tunnel['port']}"
                )
        else:
            host = tunnel["host"]
            links[tunnel["id"]].append(
                f"{tunnel['protocol']}://{host}:{tunnel['port']}"
            )
    print(json.dumps(links))
