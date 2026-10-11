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

with control(1)[0] as conn:
    conn.sendall(b'genuine-tcp-echo');assert exact(conn,16)==b'genuine-tcp-echo'
with control(3)[0] as conn:
    # The actual Xray frontend binds SOCKS UDP on its inbound listener port.
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
        udp.settimeout(5)
        frame=b'\0\0\0\1'+socket.inet_aton('192.0.2.80')+struct.pack('!H',9000)+b'genuine-udp-echo'
        udp.sendto(frame,('127.0.0.1',19080))
        reply,_=udp.recvfrom(65535);assert reply[10:]==b'genuine-udp-echo'
