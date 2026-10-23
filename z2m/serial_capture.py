"""Optional serial transport for the firmware descriptor protocol; no raw logs saved."""
import time
from .converter import MAX_BYTES,parse_descriptor,require

PREFIX=b'Z2M_DESCRIPTOR '


def read_descriptor(stream,timeout=15):
    require(isinstance(timeout,(int,float)) and 0<timeout<=120,'Invalid capture timeout')
    deadline=time.monotonic()+timeout;next_request=0;buffer=bytearray();discard_line=False
    while time.monotonic()<deadline:
        now=time.monotonic()
        if now>=next_request:
            stream.write(b'describe\n');next_request=now+2
        chunk=stream.read(256)
        for byte in chunk:
            if byte==10:
                if not discard_line and buffer.startswith(PREFIX):
                    try:return parse_descriptor(bytes(buffer[len(PREFIX):]).rstrip(b'\r'))
                    except ValueError:pass
                buffer.clear();discard_line=False
            elif not discard_line:
                buffer.append(byte)
                if len(buffer)>MAX_BYTES+len(PREFIX)+1:buffer.clear();discard_line=True
    raise ValueError('No valid firmware descriptor received before timeout; no raw serial logs saved')


def capture_descriptor(port,baud=115200,timeout=15):
    require(isinstance(port,str) and bool(port),'Explicit serial port required')
    require(type(baud) is int and 0<baud<=2000000,'Invalid serial baud')
    require(isinstance(timeout,(int,float)) and 1<=timeout<=120,'Capture timeout must be 1 to 120 seconds')
    try:import serial
    except ImportError as e:raise ValueError('Serial capture requires pyserial; see z2m/requirements-serial.txt') from e
    connection=serial.Serial();connection.port=port;connection.baudrate=baud;connection.timeout=.2;connection.write_timeout=.5
    connection.dtr=False;connection.rts=False
    try:
        connection.open()
        return read_descriptor(connection,timeout)
    finally:
        connection.close()
