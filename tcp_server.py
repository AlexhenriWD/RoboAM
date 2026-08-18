import socket
import select
import threading
import queue
import time


class TCPServer:
    """
    TCP Server com suporte a dois modos:
    - read_enabled=True  -> servidor de COMANDOS (texto, full-duplex)
    - read_enabled=False -> servidor de VÍDEO (binário, write-only)
    """

    def __init__(self):
        self.server_socket = None
        self.client_sockets = {}
        self.message_queue = queue.Queue()

        self.max_clients = 1
        self.active_connections = 0

        self.accept_thread = None
        self.stop_event = threading.Event()

        self.read_enabled = True  # definido no start()

        # pipe para encerrar select sem travar
        self.stop_pipe_r, self.stop_pipe_w = socket.socketpair()
        self.stop_pipe_r.setblocking(False)
        self.stop_pipe_w.setblocking(False)

    # ==========================================================
    # START / STOP
    # ==========================================================

    def start(self, ip, port, max_clients=1, listen_count=1, read_enabled=True):
        self.read_enabled = read_enabled
        self.max_clients = max_clients

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((ip, port))
        self.server_socket.listen(listen_count)
        self.server_socket.setblocking(False)

        print(
            f"Server started on {ip}:{port} | "
            f"mode={'COMMAND' if read_enabled else 'VIDEO(write-only)'}"
        )

        self.accept_thread = threading.Thread(
            target=self.accept_connections,
            daemon=True
        )
        self.accept_thread.start()

    def close(self):
        self.stop_event.set()
        try:
            self.stop_pipe_w.send(b'\x00')
        except Exception:
            pass

        if self.accept_thread:
            self.accept_thread.join(timeout=2)

        if self.server_socket:
            self.server_socket.close()

        for s in list(self.client_sockets.keys()):
            try:
                s.close()
            except Exception:
                pass

        self.client_sockets.clear()
        self.active_connections = 0
        print("Server stopped.")

    # ==========================================================
    # CONNECTION LOOP
    # ==========================================================

    def accept_connections(self):
        """
        Loop principal:
        - aceita conexões
        - lê dados APENAS se read_enabled=True
        """
        while not self.stop_event.is_set():
            try:
                # ⚠️ seletor DIFERENTE dependendo do modo, mas os DOIS
                # incluem os sockets de cliente agora -- ver abaixo o
                # motivo de o modo vídeo (read_enabled=False) precisar
                # disso mesmo nunca processando dado nenhum de cliente.
                read_list = (
                    [self.server_socket, self.stop_pipe_r]
                    + list(self.client_sockets.keys())
                )

                readable, _, _ = select.select(read_list, [], [], 0.5)

                for s in readable:
                    # --------------------------
                    # nova conexão
                    # --------------------------
                    if s is self.server_socket:
                        if self.active_connections >= self.max_clients:
                            client_socket, addr = s.accept()
                            client_socket.close()
                            print(f"Rejected {addr} (max clients)")
                            continue

                        client_socket, addr = s.accept()
                        client_socket.setblocking(False)
                        self.client_sockets[client_socket] = addr
                        self.active_connections += 1
                        print(f"New connection from {addr}, {self.active_connections} active.")
                        continue

                    # --------------------------
                    # parada
                    # --------------------------
                    if s is self.stop_pipe_r:
                        self.stop_event.set()
                        break

                    # --------------------------
                    # leitura
                    # --------------------------
                    if not self.read_enabled:
                        # Modo vídeo: NUNCA processa dado de cliente (o
                        # protocolo é write-only por desenho), mas ainda
                        # assim faz o recv() só pra DETECTAR desconexão
                        # (recv devolvendo vazio = cliente fechou).
                        #
                        # CORRIGIDO (achado em uso real): antes, o modo
                        # vídeo excluía client_sockets do select()
                        # inteiro -- e como escrita só acontece quando há
                        # frame pra mandar (send_data_to_video_client,
                        # chamado de _video_loop), se a câmera parasse de
                        # produzir frame por qualquer motivo, o servidor
                        # NUNCA tentava escrever pros clientes de vídeo,
                        # NUNCA descobria que um cliente antigo tinha
                        # desconectado (FIN), e portanto NUNCA chamava
                        # _remove_client -- cada reconexão de um cliente
                        # (ex: ver_camera_robo.py tentando de novo depois
                        # de timeout) empilhava mais uma conexão morta,
                        # até estourar max_clients pra sempre, mesmo com
                        # bem menos clientes de vídeo reais do que isso.
                        try:
                            data = s.recv(1024)
                            if not data:
                                self._remove_client(s)
                            # dado não-vazio: cliente de vídeo mandou algo
                            # (não deveria, protocolo é write-only) --
                            # descarta, não é motivo pra derrubar a
                            # conexão por si só.
                        except OSError:
                            self._remove_client(s)
                        continue

                    try:
                        data = s.recv(1024)
                        if data:
                            addr = self.client_sockets.get(s)
                            if addr:
                                try:
                                    msg = data.decode("utf-8")
                                except UnicodeDecodeError:
                                    continue
                                # Timestamp aqui, no recv() de verdade --
                                # não em quem consome a fila depois. É
                                # isso que dá pra medir "quanto tempo a
                                # mensagem ficou esperando" com o relógio
                                # de uma máquina só (o servidor), sem
                                # depender do relógio de quem mandou (ver
                                # robot_protocol.CommandEnvelope.is_expired).
                                # Terceiro elemento da tupla é NOVO --
                                # qualquer consumidor antigo que
                                # desempacotava só (addr, msg) quebra;
                                # ver eva_server.py (legado, sendo
                                # substituído por eva_command_server.py,
                                # que já espera 3 elementos).
                                self.message_queue.put((addr, msg, time.time()))
                        else:
                            self._remove_client(s)

                    except OSError:
                        self._remove_client(s)

            except Exception as e:
                print(f"TCPServer loop error: {e}")

        print("accept_connections loop ended.")

    # ==========================================================
    # SEND
    # ==========================================================

    def send_to_all_client(self, data):
        for s in list(self.client_sockets.keys()):
            try:
                if isinstance(data, str):
                    s.sendall(data.encode("utf-8"))
                else:
                    s.sendall(data)
            except OSError:
                self._remove_client(s)

    def send_to_client(self, client_address, data):
        for s, addr in self.client_sockets.items():
            if addr == client_address:
                try:
                    if isinstance(data, str):
                        s.sendall(data.encode("utf-8"))
                    else:
                        s.sendall(data)
                except OSError:
                    self._remove_client(s)
                return
        print(f"Client at {client_address} not found.")

    # ==========================================================
    # UTILS
    # ==========================================================

    def _remove_client(self, client_socket):
        addr = self.client_sockets.get(client_socket)
        if addr:
            print(f"{addr} disconnected")
        try:
            client_socket.close()
        except Exception:
            pass
        if client_socket in self.client_sockets:
            del self.client_sockets[client_socket]
            self.active_connections -= 1

    def get_client_ips(self):
        return [addr[0] for addr in self.client_sockets.values()]
