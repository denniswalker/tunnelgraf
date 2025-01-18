import paramiko
import socket
from sshtunnel import SSHTunnelForwarder, BaseSSHTunnelForwarderError, address_to_str, SSH_TIMEOUT, TUNNEL_TIMEOUT
import os


class UnixSocketSSHTunnelForwarder(SSHTunnelForwarder):
    def __init__(self, ssh_unix_socket, *args, **kwargs):
        self.ssh_unix_socket = ssh_unix_socket
        super().__init__(self.ssh_unix_socket, *args, **kwargs)
    
    def _get_transport(self):
        """ Return the SSH transport to the remote gateway """
        import ipdb; ipdb.set_trace()
        if self.ssh_proxy:
            if isinstance(self.ssh_proxy, paramiko.proxy.ProxyCommand):
                proxy_repr = repr(self.ssh_proxy.cmd[1])
            else:
                proxy_repr = repr(self.ssh_proxy)
            self.logger.debug('Connecting via proxy: {0}'.format(proxy_repr))
            _socket = self.ssh_proxy
        else:
            _socket = self.ssh_unix_socket
        if isinstance(_socket, socket.socket):
            _socket.settimeout(SSH_TIMEOUT)
            _socket.connect(self.ssh_unix_socket)
        transport = paramiko.Transport(_socket)
        sock = transport.sock
        if isinstance(sock, socket.socket):
            sock.settimeout(SSH_TIMEOUT)
        transport.set_keepalive(self.set_keepalive)
        transport.use_compression(compress=self.compression)
        transport.daemon = self.daemon_transport
        # try to solve https://github.com/paramiko/paramiko/issues/1181
        # transport.banner_timeout = 200
        if isinstance(sock, socket.socket):
            sock_timeout = sock.gettimeout()
            sock_info = repr((sock.family, sock.type, sock.proto))
            self.logger.debug('Transport socket info: {0}, timeout={1}'
                              .format(sock_info, sock_timeout))
        return transport

    # def _make_ssh_forward_server(self, remote_address, local_bind_address):
    #     """ Make SSH forward proxy Server class """
    #     _Handler = self._make_ssh_forward_handler_class(remote_address)
    #     try:
    #         if isinstance(local_bind_address, str):  # Unix socket
    #             _Server = self._make_stream_ssh_forward_server_class(remote_address)
    #         else:
    #             _Server = self._make_ssh_forward_server_class(remote_address)
    #         ssh_forward_server = _Server(
    #             local_bind_address,
    #             _Handler,
    #             logger=self.logger,
    #         )
    #         if ssh_forward_server:
    #             ssh_forward_server.daemon_threads = self.daemon_forward_servers
    #             self._server_list.append(ssh_forward_server)
    #             self.tunnel_is_up[ssh_forward_server.server_address] = False
    #         else:
    #             self._raise(
    #                 BaseSSHTunnelForwarderError,
    #                 'Problem setting up ssh {0} <> {1} forwarder. You can '
    #                 'suppress this exception by using the `mute_exceptions`'
    #                 'argument'.format(address_to_str(local_bind_address),
    #                                   address_to_str(remote_address))
    #             )
    #     except IOError:
    #         self._raise(
    #             BaseSSHTunnelForwarderError,
    #             "Couldn't open tunnel {0} <> {1} might be in use or "
    #             "destination not reachable".format(
    #                 address_to_str(local_bind_address),
    #                 address_to_str(remote_address)
    #             )
    #         )

    def _get_binds(self, bind_address, bind_addresses, is_remote=False):
        """ Process bind addresses, allowing Unix sockets """
        addr_kind = 'remote' if is_remote else 'local'

        if not bind_address and not bind_addresses:
            if is_remote:
                raise ValueError("No {0} bind addresses specified. Use "
                                 "'{0}_bind_address' or '{0}_bind_addresses'"
                                 " argument".format(addr_kind))
            else:
                return []
        elif bind_address and bind_addresses:
            raise ValueError("You can't use both '{0}_bind_address' and "
                             "'{0}_bind_addresses' arguments. Use one of "
                             "them.".format(addr_kind))
        if bind_address:
            bind_addresses = [bind_address]
        if not is_remote:
            # Add random port if missing in local bind
            for (i, local_bind) in enumerate(bind_addresses):
                if isinstance(local_bind, tuple) and len(local_bind) == 1:
                    bind_addresses[i] = (local_bind[0], 0)
        return bind_addresses

    def _check_tunnel(self, _srv):
        """ Check if tunnel is already established """
        if self.skip_tunnel_checkup:
            self.tunnel_is_up[_srv.local_address] = True
            return
        self.logger.info('Checking tunnel to: {0}'.format(_srv.remote_address))
        if isinstance(_srv.local_address, str):  # Unix stream
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TUNNEL_TIMEOUT)
        try:
            # Only check connection through self.ssh_unix_socket
            s.connect(self.ssh_unix_socket)
            self.tunnel_is_up[_srv.local_address] = _srv.tunnel_ok.get(
                timeout=TUNNEL_TIMEOUT * 1.1
            )
            self.logger.debug(
                'Tunnel to {0} is DOWN'.format(_srv.remote_address)
            )
        except socket.error:
            self.logger.debug(
                'Tunnel to {0} is DOWN'.format(_srv.remote_address)
            )
            self.tunnel_is_up[_srv.local_address] = False

        except queue.Empty:
            self.logger.debug(
                'Tunnel to {0} is UP'.format(_srv.remote_address)
            )
            self.tunnel_is_up[_srv.local_address] = True
        finally:
            s.close()