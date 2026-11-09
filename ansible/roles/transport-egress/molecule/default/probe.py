"""Actual native frontend TCP and UDP echo, never a replacement proxy."""
import socket, struct

def exact(conn, count):
    result=b''
    while len(result)<count:
        part=conn.recv(count-len(result))
        if not part:raise RuntimeError('peer-closed')
        result+=part
    return result

def control(command):
    conn=socket.create_connection(('127.0.0.1',19080),timeout=5)
    conn.sendall(b'\x05\x01\x00')
    assert exact(conn,2)==b'\x05\x00'
    target='192.0.2.80' if command==1 else '0.0.0.0'
    port=9000 if command==1 else 0
    conn.sendall(bytes([5,command,0,1])+socket.inet_aton(target)+struct.pack('!H',port))
    header=exact(conn,4);assert header[:3]==b'\x05\x00\x00'
    count=4 if header[3]==1 else 16
    address=socket.inet_ntop(socket.AF_INET if count==4 else socket.AF_INET6,exact(conn,count))
    port=struct.unpack('!H',exact(conn,2))[0]
    return conn,address,port

# The peer accepts on 192.0.2.81 too, so missing echo through the frontend proves the deny range.
with socket.create_connection(('192.0.2.81',9000),timeout=5) as conn:
    conn.sendall(b'x');assert exact(conn,1)==b'x'
for target in (bytes([1])+socket.inet_aton('192.0.2.81'),bytes([3,19])+b'denied-name.invalid'):
    with socket.create_connection(('127.0.0.1',19080),timeout=5) as conn:
        conn.sendall(b'\x05\x01\x00');assert exact(conn,2)==b'\x05\x00'
        conn.sendall(b'\x05\x01\x00'+target+struct.pack('!H',9000)+b'payload')
        received=b''
        try:
            while b'payload' not in received:
                part=conn.recv(4096)
                if not part:break
                received+=part
        except OSError:
            pass  # A reset or timeout is the expected denial; the next line checks that no echo arrived.
        assert b'payload' not in received
with control(1)[0] as conn:
    conn.sendall(b'genuine-tcp-echo');assert exact(conn,16)==b'genuine-tcp-echo'
conn,address,port=control(3)
with conn:
    address='127.0.0.1' if address in ('0.0.0.0','::') else address
    assert address=='127.0.0.1' and 0<port<=65535 and port!=19080
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
        udp.settimeout(5)
        frame=b'\0\0\0\1'+socket.inet_aton('192.0.2.80')+struct.pack('!H',9000)+b'genuine-udp-echo'
        udp.sendto(frame,(address,port))
        reply,_=udp.recvfrom(65535);assert reply[10:]==b'genuine-udp-echo'
