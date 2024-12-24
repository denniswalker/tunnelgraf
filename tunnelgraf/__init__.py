import click
from tunnelgraf.tunnels import Tunnels
from tunnelgraf.run_remote import RunCommand
from tunnelgraf.interactive_session import InteractiveSSHSession
from importlib.metadata import version
import sys
import json
import pathlib


# Default arguments for all commands.
@click.group()
@click.version_option(
    package_name="tunnelgraf", prog_name="tunnelgraf", version=version("tunnelgraf")
)
@click.option(
    "--profile",
    "-p",
    "config_file",
    envvar="TUNNELGRAF_CONFIG",
    type=click.Path(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        path_type=pathlib.Path,
    ),
    required=True,
    help="Path to the connection profile."
)
@click.option(
    "--tunnel-id",
    "-t",
    help="The tunnel id to use for the command.",
    default=None,
)
@click.pass_context
def cli(ctx, config_file: pathlib.Path, tunnel_id: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj['config_file'] = config_file
    ctx.obj['tunnel_id'] = tunnel_id


# Connect to all remote tunnels defined in a connection profile.
@cli.command(
    help="Connect to the remote tunnels defined in a connection profile. Requires an argument containing the path to the connection profile, e.g `tunnelgraf connect <tunnelfile.yml>"
)
def connect() -> None:
    config_file = click.get_current_context().obj['config_file']
    Tunnels(config_file)


@cli.command(help="Print the resulting tunnels configuration w/o connecting.")
@click.option(
    "--show-credentials",
    help="Print the credentials used when connecting. Default: false",
    is_flag=True,
    default=False,
)
def show(show_credentials: bool) -> None:
    config_file = click.get_current_context().obj['config_file']
    tunnel_id = click.get_current_context().obj['tunnel_id']
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
def urls() -> None:
    config_file = click.get_current_context().obj['config_file']
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


@cli.command(
    help="Run a specified shell command on the remote host defined in the connection profile."
)
@click.argument(
    "command",
    type=str,
    required=True,
)
def command(command: str) -> None:
    config_file = click.get_current_context().obj['config_file']
    tunnel_id = click.get_current_context().obj['tunnel_id']
    tunnels = Tunnels(config_file, connect_tunnels=False, show_credentials=True).tunnel_configs
    try:
        this_tunnel = [tunnel for tunnel in tunnels if tunnel_id == tunnel["id"]][0]
    except IndexError:
        print(f"Tunnel id {tunnel_id} not found.")
        sys.exit(1)
    host = this_tunnel.get("host")
    port = this_tunnel.get("port")
    #print(f"Running command \"{command}\" on {host}:{port}...")
    result = RunCommand(
        host=host,
        port=port,
        identityfile=this_tunnel.get("sshkeyfile"),
        password=this_tunnel.get("sshpass"),
        user=this_tunnel.get("sshuser"),
    ).run(command)
    print(f"{result}")


@cli.command(
    help="Open an interactive SSH shell to the remote host defined in the connection profile."
)
def shell() -> None:
    config_file = click.get_current_context().obj['config_file']
    tunnel_id = click.get_current_context().obj['tunnel_id']
    tunnels = Tunnels(config_file, connect_tunnels=False, show_credentials=True).tunnel_configs
    try:
        this_tunnel = [tunnel for tunnel in tunnels if tunnel_id == tunnel["id"]][0]
    except IndexError:
        print(f"Tunnel id {tunnel_id} not found.")
        sys.exit(1)
    InteractiveSSHSession(
        host=this_tunnel.get("host"),
        port=this_tunnel.get("port"),
        identityfile=this_tunnel.get("sshkeyfile"),
        password=this_tunnel.get("sshpass"),
        user=this_tunnel.get("sshuser"),
    ).start_interactive_session()
