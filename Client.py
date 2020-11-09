from tkinter import Button, Label
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3

    def __init__(self, master, server_addr, server_port, rtp_port, filename):
        self.master = master
        self.createWidgets()
        self.serverAddr = server_addr
        self.serverPort = int(server_port)
        self.rtpPort = int(rtp_port)
        self.filename = filename
        self.connectToServer()
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.frameNumber = 0

    def createWidgets(self):
        self.setup = Button(self.master, width=30, padx=3, pady=3)
        self.setup['text'] = "Setup"
        self.setup['command'] = self.setupVideo
        self.setup.grid(row=1, column=0, padx=2, pady=2)

        self.play = Button(self.master, width=30, padx=3, pady=3)
        self.play['text'] = "Play"
        self.play['command'] = self.playVideo
        self.play.grid(row=1, column=1, padx=2, pady=2)

        self.pause = Button(self.master, width=30, padx=3, pady=3)
        self.pause['text'] = "Pause"
        self.pause['command'] = self.pauseVideo
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        self.teardown = Button(self.master, width=30, padx=3, pady=3)
        self.teardown['text'] = "Teardown"
        self.teardown['command'] = self.teardownVideo
        self.teardown.grid(row=1, column=3, padx=2, pady=2)

        self.label = Label(self.master, height=40)
        self.label.grid(row=0, column=0, columnspan=4, padx=5, pady=5)
    
    def setupVideo(self):
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)
    
    def playVideo(self):
        if self.state == self.READY:
            threading.Thread(target=self.listenRtp).start()
            self.playEvent = threading.Event()
            self.playEvent.clear()
            self.sendRtspRequest(self.PLAY)

    def pauseVideo(self):
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def teardownVideo(self):
        self.sendRtspRequest(self.TEARDOWN)
        self.master.destroy()
    
    def connectToServer(self):
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except Exception as e:
            print(e)

    def sendRtspRequest(self, requestCode):
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.receiveRtspReply).start()
            self.rtspSeq += 1
            request = 'SETUP ' + self.filename + ' RTSP/1.0\nCSeq: ' + str(self.rtspSeq) + '\nTransport: RTP/UDP; client_port= ' + str(self.rtpPort)
            self.requestSent = self.SETUP 
        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq += 1
            request = 'PLAY ' + self.filename + ' RTSP/1.0\nCSeq: ' + str(self.rtspSeq) + '\nSession: ' + str(self.sessionId)
            self.requestSent = self.PLAY
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq += 1
            request = 'PAUSE ' + self.filename + ' RTSP/1.0\nCSeq: ' + str(self.rtspSeq) + '\nSession: ' + str(self.sessionId)
            self.requestSent = self.PAUSE
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            self.rtspSeq += 1
            request = 'TEARDOWN ' + self.filename + ' RTSP/1.0\nCSeq: ' + str(self.rtspSeq) + '\nSession: ' + str(self.sessionId)
            self.requestSent = self.TEARDOWN
        else:
            return
        self.rtspSocket.sendall(request.encode())
        print('\nData sent:\n' + request)
    
    def receiveRtspReply(self):
        while True:
            reply = self.rtspSocket.recv(1024)
            if reply:
                self.parseRtspReply(reply.decode('utf-8'))
            if self.requestSent == self.TEARDOWN:
                self.rtspSocket.shutdown(socket.SHUT_RDWR)
                self.rtspSocket.close()
                break
    
    def parseRtspReply(self, data):
        reply = data.split('\n')
        seq = int(reply[1].split(' ')[1])
        if seq == self.rtspSeq:
            session = int(reply[2].split(' ')[1])
            if self.sessionId == 0:
                self.sessionId = session
            if session == self.sessionId:
                code = int(reply[0].split(' ')[1])
                if code == 200:
                    if self.requestSent == self.SETUP:
                        self.state = self.READY
                        self.openRtpPort()
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.teardownAcked = 1
                elif code == 404:
                    print("404 NOT FOUND")
                elif code == 500:
                    print("500 CONNECTION ERROR")
    
    def openRtpPort(self):
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.settimeout(0.5)
        try:
            self.rtpSocket.bind(('', self.rtpPort))
        except Exception as e:
            print(e)
    
    def listenRtp(self):
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    currFrameNumber = rtpPacket.seqNum()
                    if currFrameNumber > self.frameNumber:
                        self.frameNumber = currFrameNumber
                        self.updateVideo(self.writeFrame(rtpPacket.getPayload()))
            except:
                if self.playEvent.isSet():
                    break
                if self.teardownAcked == 1:
                    self.rtpSocket.shutdown(socket.SHUT_RDWR)
                    self.rtpSocket.close()
                    break
    
    def writeFrame(self, data):
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, 'wb')
        file.write(data)
        file.close()
        return cachename

    def updateVideo(self, imageFile):
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image=photo, height=500)
        self.label.image = photo
