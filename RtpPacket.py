import sys
from time import time

HEADER_SIZE = 12

class RtpPacket:
    
    def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload, extid=0, extlen=0, *args, **kwargs):
        timestamp = int(time())
        self.header = bytearray(HEADER_SIZE)
        self.header[0] = (version << 6) | (padding << 5) | (extension << 4) | cc
        self.header[1] = (marker << 7) | pt
        self.header[2] = seqnum >> 8
        self.header[3] = seqnum & 255
        self.header[4] = timestamp >> 24
        self.header[5] = timestamp >> 16 & 255
        self.header[6] = timestamp >> 8 & 255
        self.header[7] = timestamp & 255
        self.header[8] = ssrc >> 24
        self.header[9] = ssrc >> 16 & 255
        self.header[10] = ssrc >> 8 & 255
        self.header[11] = ssrc & 255
        self.extensionHeader = bytearray(4*(extlen + 1))
        self.extensionHeader[0] = extid >> 8
        self.extensionHeader[1] = extid & 255
        self.extensionHeader[2] = extlen >> 8
        self.extensionHeader[3] = extlen & 255
        self.extensionHeader[4] = kwargs['frameCnt'] >> 24
        self.extensionHeader[5] = kwargs['frameCnt'] >> 16 & 255
        self.extensionHeader[6] = kwargs['frameCnt'] >> 8 & 255
        self.extensionHeader[7] = kwargs['frameCnt'] & 255
        self.payload = payload
    
    def decode(self, byteStream):
        self.header = bytearray(byteStream[:HEADER_SIZE])
        extlen = int(byteStream[HEADER_SIZE + 2] << 8 | byteStream[HEADER_SIZE + 3])
        self.extensionHeader = bytearray(byteStream[HEADER_SIZE : (HEADER_SIZE + 4*(extlen + 1))])
        self.payload = byteStream[(HEADER_SIZE + 4*(extlen + 1)):]
    
    def version(self):
        return int(self.header[0] >> 6)
    
    def seqNum(self):
        return int(self.header[2] << 8 | self.header[3])
    
    def timestamp(self):
        return int(self.header[4] << 24 | self.header[5] << 16 | self.header[6] << 8 | self.header[7])

    def payloadType(self):
        return int(self.header[1] & 127)

    def getPayload(self):
        return self.payload

    def getFrameCnt(self):
        return int(self.extensionHeader[4] << 24 | self.extensionHeader[5] << 16 | self.extensionHeader[6] << 8 | self.extensionHeader[7])
    
    def getPacket(self):
        return self.header + self.extensionHeader + self.payload
