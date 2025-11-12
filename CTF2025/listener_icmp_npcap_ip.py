#!/usr/bin/env python3
"""
ICMP-Listener mit Scapy (empfohlen)

Voraussetzungen:
 - Linux: scapy (pip install scapy)
 - Windows: Npcap (https://nmap.org/npcap/) installiert + scapy (pip install scapy)

Dieses Script benutzt Scapy zum Sniffen (libpcap-basiert). Es filtert nach Quell-IP
und optional nach ICMP-Typ, speichert optional in eine PCAP-Datei und gibt Payload
als Text oder Hexdump aus.

Zusätzlich prüft es beim Start, ob Npcap läuft und listet alle verfügbaren Interfaces.

Beispiel:
  sudo python3 listener_icmp_scapy.py --source-ip 198.51.100.10
  python listener_icmp_scapy.py --source-ip 198.51.100.10 --iface "Ethernet" --icmp-type 8 --hex --save pcap_out.pcap
"""

import argparse
import datetime
import sys
import textwrap

try:
    from scapy.all import sniff, IP, ICMP, raw, PcapWriter, conf, get_if_list
except Exception as e:
    print("Fehler: Scapy ist nicht installiert oder konnte nicht importiert werden.")
    print("Installiere scapy: pip install scapy")
    print(f"Import error: {e}")
    sys.exit(1)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def hexdump(data: bytes, width: int = 16) -> str:
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i+width]
        hex_bytes = ' '.join(f"{b:02x}" for b in chunk)
        ascii_bytes = ''.join((chr(b) if 32 <= b <= 126 else '.') for b in chunk)
        lines.append(f"{i:08x}  {hex_bytes:<{width*3}}  {ascii_bytes}")
    return '\n'.join(lines)


def packet_handler(pkt, args, pcap_writer=None):
    if not pkt.haslayer(IP) or not pkt.haslayer(ICMP):
        return

    ip = pkt.getlayer(IP)
    icmp = pkt.getlayer(ICMP)

    if ip.src != args.source_ip:
        return

    if args.icmp_type is not None and icmp.type != args.icmp_type:
        return

    payload = bytes(icmp.payload)
    header = f"[{now_iso()}] ICMP from {ip.src} -> {ip.dst}, type={icmp.type}, code={icmp.code}, len={len(payload)}"
    print(header)

    if args.save and pcap_writer:
        pcap_writer.write(pkt)

    if args.hex:
        print(hexdump(payload))
    else:
        if payload:
            try:
                print(payload.decode('utf-8'))
            except Exception:
                print(payload)
        else:
            print('<no payload>')


def main():
    p = argparse.ArgumentParser(description='ICMP-Listener mit Scapy: filtert nach Quell-IP, speichert optional als PCAP')
    p.add_argument('--source-ip', '-s', required=True, help='Nur Pakete mit dieser Quell-IP akzeptieren')
    p.add_argument('--iface', '-i', help='Interface-Name (optional). Unter Windows typischerweise der Adapter-Name wie "Ethernet" oder "Wi-Fi"')
    p.add_argument('--icmp-type', type=int, help='Nur ICMP-Pakete mit diesem Typ (z.B. 8 für Echo-Request)')
    p.add_argument('--hex', action='store_true', help='Payload als Hexdump ausgeben')
    p.add_argument('--save', metavar='PCAP', help='Optional: Schreibe empfangene Pakete in diese PCAP-Datei')
    p.add_argument('--bpf', help='Zusätzlicher BPF-Filter (z.B. "icmp[0] == 8")')
    args = p.parse_args()

    # Check für Windows Npcap / alle Interfaces ausgeben
    print("\n=== ICMP Listener Startup ===")
    if sys.platform.startswith('win'):
        print("Prüfe Npcap auf Windows...")
        interfaces = get_if_list()
        if interfaces:
            print(f"Gefundene Interfaces: {interfaces}")
        else:
            print("Warnung: Keine Interfaces gefunden. Stelle sicher, dass Npcap installiert ist und du als Administrator startest.")
    else:
        interfaces = get_if_list()
        print(f"Verfügbare Interfaces: {interfaces}")

    print(textwrap.dedent(f"""
    ICMP-Listener (Scapy)
      source-ip : {args.source_ip}
      iface     : {args.iface or '*'}
      icmp-type : {args.icmp_type if args.icmp_type is not None else 'any'}
      hex       : {args.hex}
      save pcap : {args.save or '<no>'}

    Hinweis: Stelle sicher, dass du die Konsole als Administrator/Root startest (libpcap/npcap benötigt).
    """))

    pcap_writer = None
    if args.save:
        try:
            pcap_writer = PcapWriter(args.save, append=True, sync=True)
            print(f"Schreibe PCAP nach: {args.save}")
        except Exception as e:
            print(f"Warnung: Konnte PCAP-Writer nicht öffnen: {e}")
            pcap_writer = None

    bpf_parts = ['icmp']
    if args.source_ip:
        bpf_parts.append(f'src host {args.source_ip}')
    if args.bpf:
        bpf_parts.append(f'({args.bpf})')
    bpf = ' and '.join(bpf_parts)
    print(f"Benutze BPF-Filter: {bpf}")

    try:
        sniff(filter=bpf, prn=lambda pkt: packet_handler(pkt, args, pcap_writer), iface=args.iface, store=0)
    except PermissionError:
        print('PermissionError: Bitte als Administrator/Root ausführen (libpcap/npcap benötigt).')
    except OSError as e:
        print(f'OSError beim Starten des Sniffers: {e}')
        print('Unter Windows: stelle sicher, dass Npcap installiert ist und du die Konsole als Administrator gestartet hast.')
    except KeyboardInterrupt:
        print('\nBeendet durch Benutzer')
    finally:
        if pcap_writer:
            pcap_writer.close()


if __name__ == '__main__':
    main()
