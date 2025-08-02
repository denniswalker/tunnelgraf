import click
from tunnelgraf.tunnels import Tunnels
from tunnelgraf.run_remote import RunCommand
from tunnelgraf.interactive_session import InteractiveSSHSession
from importlib.metadata import version
import sys
import json
import pathlib
import os
import syslog
import signal
import psutil
import paramiko
import stat
from tunnelgraf.transfer import Transfer


# Default arguments for all commands.
@click.group()
@click.version_option(
    package_name="tunnelgraf", prog_name="tunnelgraf", version=version("tunnelgraf")
)
@click.option(
    "--profile",
    "-p",
    "config_file",
    envvar="TUNNELGRAF_PROFILE",
    type=click.Path(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        path_type=pathlib.Path,
    ),
    required=True,
    help="Path to the connection profile.",
)
@click.option(
    "--tunnel-id",
    "-t",
    help="The tunnel id to use for the command.",
    default=None,
)
@click.pass_context
def cli(ctx, config_file: pathlib.Path, tunnel_id: str) -> None:
    if ctx.invoked_subcommand == "help":
        return
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file
    ctx.obj["tunnel_id"] = tunnel_id


# Connect to all remote tunnels defined in a connection profile.
@cli.command(
    help="Connect to the remote tunnels defined in a connection profile. Requires an argument containing the path to the connection profile, e.g `tunnelgraf connect <tunnelfile.yml>"
)
@click.option(
    "--detach",
    "-d",
    help="Run in background and return process ID",
    is_flag=True,
    default=False,
)
def connect(detach: bool) -> None:
    if not detach:
        config_file = click.get_current_context().obj["config_file"]
        Tunnels(config_file, connect_tunnels=True)
    else:
        # Fork the current process
        pid = os.fork()
        if pid > 0:
            # Parent process
            print("Starting tunnels in process with PID:", pid)
            os._exit(0)  # Exit the parent process
        elif pid == 0:
            # Child process
            # Redirect stdout and stderr to syslog
            syslog.openlog(
                ident="tunnelgraf", logoption=syslog.LOG_PID, facility=syslog.LOG_DAEMON
            )

            class SyslogRedirector:
                def write(self, message):
                    if message.strip():
                        syslog.syslog(syslog.LOG_INFO, message.strip())

                def flush(self):
                    pass

            sys.stdout = SyslogRedirector()
            sys.stderr = SyslogRedirector()

            config_file = click.get_current_context().obj["config_file"]
            Tunnels(config_file, connect_tunnels=True, detach=True)
        else:
            print("Fork failed.")
            sys.exit(1)


@cli.command(help="Print the resulting tunnels configuration w/o connecting.")
@click.option(
    "--show-credentials",
    help="Print the credentials used when connecting. Default: false",
    is_flag=True,
    default=False,
)
def show(show_credentials: bool) -> None:
    config_file = click.get_current_context().obj["config_file"]
    tunnel_id = click.get_current_context().obj["tunnel_id"]
    tunnels = Tunnels(
        config_file, connect_tunnels=False, show_credentials=show_credentials
    ).tunnel_configs
    if tunnel_id:
        try:
            this_tunnel = [
                tunnel for tunnel in tunnels if tunnel_id == tunnel.id][0]
        except IndexError:
            print(f"Tunnel id {tunnel_id} not found.")
            sys.exit(1)
        print(json.dumps(this_tunnel.model_dump(), indent=4))
    else:
        print(json.dumps([t.model_dump() for t in tunnels], indent=4))


@cli.command(
    help="Print the URLs to access each tunnel. Protocol is displayed as ssh unless specified."
)
def urls() -> None:
    config_file = click.get_current_context().obj["config_file"]
    tunnels = Tunnels(config_file, connect_tunnels=False).tunnel_configs
    links: dict = {}
    for tunnel in tunnels:
        links[tunnel.id]: list = []
        if tunnel.hosts_file_entry:
            host = tunnel.hosts_file_entry
            links[tunnel.id].append(
                f"{tunnel.protocol}://{host}:{tunnel.port}"
            )
        elif tunnel.hosts_file_entries:
            for hosts_entry in tunnel.hosts_file_entries:
                links[tunnel.id].append(
                    f"{tunnel.protocol}://{hosts_entry}:{tunnel.port}"
                )
        else:
            host = tunnel.host
            links[tunnel.id].append(
                f"{tunnel.protocol}://{host}:{tunnel.port}"
            )
    print(json.dumps(links, indent=4))


@cli.command(
    help="Run a specified shell command on the remote host defined in the connection profile."
)
@click.argument(
    "command",
    type=str,
    required=True,
)
def command(command: str) -> None:
    config_file = click.get_current_context().obj["config_file"]
    tunnel_id = click.get_current_context().obj["tunnel_id"]
    tunnels = Tunnels(
        config_file, connect_tunnels=False, show_credentials=True
    ).tunnel_configs
    try:
        this_tunnel = [
            tunnel for tunnel in tunnels if tunnel_id == tunnel.id][0]
    except IndexError:
        print(f"Tunnel id {tunnel_id} not found.")
        sys.exit(1)
    host = this_tunnel.host
    port = this_tunnel.port
    # print(f"Running command \"{command}\" on {host}:{port}...")
    RunCommand(
        host=host,
        port=port,
        identityfile=this_tunnel.sshkeyfile,
        password=this_tunnel.sshpass,
        user=this_tunnel.sshuser,
    ).run(command)


@cli.command(
    help="Open an interactive SSH shell to the remote host defined in the connection profile."
)
def shell() -> None:
    config_file = click.get_current_context().obj["config_file"]
    tunnel_id = click.get_current_context().obj["tunnel_id"]
    tunnels = Tunnels(
        config_file, connect_tunnels=False, show_credentials=True
    ).tunnel_configs
    try:
        this_tunnel = [
            tunnel for tunnel in tunnels if tunnel_id == tunnel.id][0]
    except IndexError:
        print(f"Tunnel id {tunnel_id} not found.")
        sys.exit(1)
    InteractiveSSHSession(
        host=this_tunnel.host,
        port=this_tunnel.port,
        identityfile=this_tunnel.sshkeyfile,
        password=this_tunnel.sshpass,
        user=this_tunnel.sshuser,
    ).start_interactive_session()


@cli.command(help="Stop the tunnels associated with the given connection profile.")
@click.pass_context
def stop(ctx) -> None:
    config_file = ctx.obj["config_file"]
    profile_path = os.path.abspath(str(config_file))
    current_pid = os.getpid()

    # Find the process with the profile path in the command line arguments.
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            pid = proc.info["pid"]
            # Skip the current process
            if pid == current_pid:
                continue

            cmdline = proc.info["cmdline"]
            if cmdline:
                # Iterate through each argument in cmdline with index
                for i, arg in enumerate(cmdline):
                    # Check if the argument contains a path separator
                    if ("/" in arg or "\\" in arg) and i + 1 < len(cmdline):
                        # Convert to absolute path
                        arg_path = os.path.abspath(arg)
                        # Compare with the profile_path and check the next entry
                        if arg_path == profile_path and cmdline[i + 1] == "connect":
                            os.kill(pid, signal.SIGINT)
                            print(f"Stopping tunnels for profile {profile_path}...")
                            return
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    print("Tunnels are not running.")


@cli.command(
    help=(
        "Copy files to/from a remote host using SCP and tunnel configuration.\n\n"
        "Arguments:\n"
        "  source: The source path for the copy. It can be a local path or a remote path in the format 'tunnel_id:path'.\n"
        "  destination: The destination path for the copy. It can be a local path or a remote path in the format 'tunnel_id:path'.\n\n"
        "Copy Direction:\n"
        "  - If the source is prefixed with 'tunnel_id:', it indicates a download from the remote host to the local destination.\n"
        "  - If the destination is prefixed with 'tunnel_id:', it indicates an upload from the local source to the remote host.\n\n"
        "Tunnel Selection:\n"
        "  - Use --tunnel-id to explicitly specify which tunnel to use for the scp operation.\n"
        "  - If --tunnel-id is not provided, the tunnel ID will be extracted from the source or destination path."
    )
)
@click.argument('source', type=str, required=True)
@click.argument('destination', type=str, required=True)
def scp(source: str, destination: str) -> None:
    """Copy files between local and remote hosts using SCP."""
    config_file = click.get_current_context().obj["config_file"]
    tunnel_id = click.get_current_context().obj["tunnel_id"]
    tunnels = Tunnels(config_file, connect_tunnels=False, show_credentials=True).tunnel_configs

    # Determine which tunnel to use
    if tunnel_id:
        # Use the explicitly specified tunnel-id
        try:
            tunnel_config = [t for t in tunnels if t.id == tunnel_id][0]
        except IndexError:
            print(f"Tunnel id {tunnel_id} not found.")
            sys.exit(1)
    else:
        # Fall back to extracting tunnel ID from source or destination
        extracted_tunnel_id = None
        if ':' in source:
            extracted_tunnel_id = source.split(':', 1)[0]
        elif ':' in destination:
            extracted_tunnel_id = destination.split(':', 1)[0]
        
        if not extracted_tunnel_id:
            print("Error: Either specify --tunnel-id or use tunnel_id:path format in source/destination")
            sys.exit(1)
            
        try:
            tunnel_config = [t for t in tunnels if t.id == extracted_tunnel_id][0]
        except IndexError:
            print(f"Tunnel id {extracted_tunnel_id} not found.")
            sys.exit(1)

    # Instantiate the Transfer class and execute the transfer
    transfer = Transfer(source, destination, tunnel_config, tunnel_id)
    transfer.execute()
