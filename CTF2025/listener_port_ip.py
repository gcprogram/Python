#!/usr/bin/env python3
"""
Einfacher Listener, der auf einem Port lauscht (TCP/UDP) **oder** ICMP-Pakete empfängt
und nur Pakete von einer bestimmten Quell-IP ausgibt.

Usage (UDP):
  python3 listener_port_ip.py --protocol udp --port 9999 --source-ip 192.0.2.1
Usage (TCP):
  python3 listener_port_ip.py --protocol tcp --port 8080 --source-ip 18.198.70.70 --hex
Usage (ICMP):
  sudo python3 listener_port_ip.py --protocol icmp --source-ip 18.198.70.70

Hinweise:
 - Für ICMP werden RAW-Sockets benötigt — Root/Administrator-Rechte sind erforderlich.
 - Für Ports < 1024 sind Administratorrechte/root nötig (bei TCP/UDP).
 - Dieses Script nutzt normale Python-Sockets; für tiefgehendes Sniffing kann Scapy genutzt werden.
"""

import argparse
import socket
import sys
import datetime


def hexdump(data: bytes, width: int = 16) -> str:
    """Gibt einen Hexdump-String für die Bytes zurück."""
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i+width]
        hex_bytes = ' '.join(f"{b:02x}" for b in chunk)
        ascii_bytes = ''.join((chr(b) if 32 <= b <= 126 else '.') for b in chunk)
        lines.append(f"{i:08x}  {hex_bytes:<{width*3}}  {ascii_bytes}")
    return '\n'.join(lines)


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def run_udp(port: int, source_ip: str, hex_output: bool, iface: str | None, logfile: str | None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if iface:
        sock.bind((iface, port))
        bind_addr = f"{iface}:{port}"
    else:
        sock.bind(("", port))
        bind_addr = f"*:{port}"

    print(f"[{now_iso()}] UDP listening on {bind_addr} (expecting packets from {source_ip})")

    try:
        while True:
            data, addr = sock.recvfrom(65535)
            peer_ip, peer_port = addr[0], addr[1]
            if peer_ip != source_ip:
                continue

            header = f"[{now_iso()}] UDP packet from {peer_ip}:{peer_port} ({len(data)} bytes)"
            print(header)
            if logfile:
                with open(logfile, 'a') as f:
                    f.write(header + "\n")

            if hex_output:
                dump = hexdump(data)
                print(dump)
                if logfile:
                    with open(logfile, 'a') as f:
                        f.write(dump + "\n")
            else:
                try:
                    text = data.decode('utf-8')
                    print(text)
                    if logfile:
                        with open(logfile, 'a') as f:
                            f.write(text + "\n")
                except Exception:
                    print(data)
                    if logfile:
                        with open(logfile, 'ab') as f:
                            f.write(data + b"\n")

    except KeyboardInterrupt:
        print("\nInterrupted, shutting down.")
    finally:
        sock.close()


def run_tcp(port: int, source_ip: str, hex_output: bool, iface: str | None, logfile: str | None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if iface:
        sock.bind((iface, port))
        bind_addr = f"{iface}:{port}"
    else:
        sock.bind(("", port))
        bind_addr = f"*:{port}"

    sock.listen(5)
    print(f"[{now_iso()}] TCP listening on {bind_addr} (accepting connections only from {source_ip})")

    try:
        while True:
            conn, addr = sock.accept()
            peer_ip, peer_port = addr[0], addr[1]
            if peer_ip != source_ip:
                conn.close()
                continue

            with conn:
                header = f"[{now_iso()}] TCP connection from {peer_ip}:{peer_port}"
                print(header)
                if logfile:
                    with open(logfile, 'a') as f:
                        f.write(header + "\n")

                while True:
                    data = conn.recv(65535)
                    if not data:
                        break
                    if hex_output:
                        dump = hexdump(data)
                        print(dump)
                        if logfile:
                            with open(logfile, 'a') as f:
                                f.write(dump + "\n")
                    else:
                        try:
                            text = data.decode('utf-8')
                            print(text)
                            if logfile:
                                with open(logfile, 'a') as f:
                                    f.write(text + "\n")
                        except Exception:
                            print(data)
                            if logfile:
                                with open(logfile, 'ab') as f:
                                    f.write(data + b"\n")

                print(f"[{now_iso()}] Connection closed {peer_ip}:{peer_port}")

    except KeyboardInterrupt:
        print("\nInterrupted, shutting down.")
    finally:
        sock.close()


def parse_icmp_packet(data: bytes) -> dict:
    """Parst grundlegende ICMP-Felder aus den empfangenen Bytes.
    Erwartet: ICMP Header + Payload (kein IP-Header)"""
    if len(data) < 4:
        return {'raw': data}

    icmp_type = data[0]
    code = data[1]
    checksum = int.from_bytes(data[2:4], 'big')
    info = {'type': icmp_type, 'code': code, 'checksum': checksum, 'raw': data}

    # Für Echo (Typ 8/0) gibt es Identifier und Sequence
    if len(data) >= 8 and icmp_type in (0, 8):
        identifier = int.from_bytes(data[4:6], 'big')
        sequence = int.from_bytes(data[6:8], 'big')
        info.update({'identifier': identifier, 'sequence': sequence, 'payload': data[8:]})
    else:
        info.update({'payload': data[4:]})

    return info


def run_icmp(source_ip: str, hex_output: bool, iface: str | None, logfile: str | None):
    # Raw socket für ICMP. Benötigt Root.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except PermissionError:
        raise

    if iface:
        # Beim Binden an ein Interface die IP-Adresse verwenden (IPv4)
        sock.bind((iface, 0))
        bind_addr = iface
    else:
        bind_addr = '*'

    print(f"[{now_iso()}] ICMP raw socket listening on {bind_addr} (expecting packets from {source_ip})")

    try:
        while True:
            data, addr = sock.recvfrom(65535)
            peer_ip = addr[0]
            if peer_ip != source_ip:
                continue

            header = f"[{now_iso()}] ICMP packet from {peer_ip} ({len(data)} bytes)"
            print(header)
            if logfile:
                with open(logfile, 'a') as f:
                    f.write(header + "\n")

            info = parse_icmp_packet(data)
            summary_lines = [f"Type={info.get('type')}, Code={info.get('code')}, Checksum=0x{info.get('checksum'):04x}"]
            if 'identifier' in info:
                summary_lines.append(f"ID={info['identifier']}, Seq={info['sequence']}")
            print(' | '.join(summary_lines))
            if logfile:
                with open(logfile, 'a') as f:
                    f.write(' | '.join(summary_lines) + "\n")

            if hex_output:
                dump = hexdump(info['raw'])
                print(dump)
                if logfile:
                    with open(logfile, 'a') as f:
                        f.write(dump + "\n")
            else:
                # Versuche Payload als UTF-8 darzustellen
                try:
                    payload = info.get('payload', b'')
                    if payload:
                        text = payload.decode('utf-8')
                        print(text)
                        if logfile:
                            with open(logfile, 'a') as f:
                                f.write(text + "\n")
                    else:
                        print('<no payload>')
                except Exception:
                    print(info['raw'])
                    if logfile:
                        with open(logfile, 'ab') as f:
                            f.write(info['raw'] + b"\n")

    except KeyboardInterrupt:
        print("\nInterrupted, shutting down.")
    finally:
        sock.close()


def parse_args():
    p = argparse.ArgumentParser(description='Port/ICMP-Listener: wartet auf Pakete von bestimmter IP und gibt sie aus')
    p.add_argument('--protocol', '-P', choices=['udp', 'tcp', 'icmp'], default='udp', help='Protokoll (udp, tcp oder icmp)')
    p.add_argument('--port', '-p', type=int, help='Portnummer (nur für udp/tcp)')
    p.add_argument('--source-ip', '-s', required=True, help='Nur Pakete von dieser Quell-IP akzeptieren')
    p.add_argument('--hex', action='store_true', help='Hexdump der empfangenen Bytes ausgeben')
    p.add_argument('--iface', help='Lokale Interface-IP zum Binden (optional)')
    p.add_argument('--log', help='Log-Datei (append)')
    return p.parse_args()


def main():
    args = parse_args()

    if args.protocol in ('udp', 'tcp'):
        if not args.port:
            print('Fehler: Für tcp/udp muss --port angegeben werden.')
            sys.exit(1)
        if args.port < 1 or args.port > 65535:
            print('Ungültiger Port. Bitte 1-65535.')
            sys.exit(1)

    try:
        if args.protocol == 'udp':
            run_udp(args.port, args.source_ip, args.hex, args.iface, args.log)
        elif args.protocol == 'tcp':
            run_tcp(args.port, args.source_ip, args.hex, args.iface, args.log)
        else:  # icmp
            if args.port:
                print('Hinweis: --port wird für ICMP ignoriert.')
            run_icmp(args.source_ip, args.hex, args.iface, args.log)
    except PermissionError:
        print('PermissionError: Für dieses Protokoll/Port werden erhöhte Rechte benötigt (root/Administrator).')
    except OSError as e:
        print(f'OSError: {e}')


if __name__ == '__main__':
    main()
