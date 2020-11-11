from tkinter import Button, Label
import tkinter.messagebox as tkMessageBox
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

    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.filename = filename
        self.connectToServer()
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.frameNumber = 0
        self.exitFlag = 0
        self.setupVideo()
        self.openRtpPort()

    def createWidgets(self):
        self.describe = Button(self.master, width=30, padx=3, pady=3)
        self.describe['text'] = "DESCRIBE"
        self.describe.grid(row=1, column=0, padx=2, pady=2)

        self.play = Button(self.master, width=30, padx=3, pady=3)
        self.play['text'] = "PLAY"
        self.play['command'] = self.playVideo
        self.play.grid(row=1, column=1, padx=2, pady=2)

        self.pause = Button(self.master, width=30, padx=3, pady=3)
        self.pause['text'] = "PAUSE"
        self.pause['command'] = self.pauseVideo
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        self.stop = Button(self.master, width=30, padx=3, pady=3)
        self.stop['text'] = "STOP"
        self.stop['command'] = self.stopVideo
        self.stop.grid(row=1, column=3, padx=2, pady=2)

        self.label = Label(self.master, height=35)
        self.label.grid(row=0, column=0, columnspan=4, padx=5, pady=5)
    
    def setupVideo(self):
        if self.state == self.INIT:
            threading.Thread(target=self.receiveRtspReply).start()
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
    
    def stopVideo(self):
        self.sendRtspRequest(self.TEARDOWN)
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        if os.path.isfile(cachename):
            os.remove(cachename)
        threading.Thread(target=self.restartVideo).start()
    
    def restartVideo(self):
        while True:
            if self.state == self.INIT:
                self.rtspSeq = 0
                self.sessionId = 0
                self.sendRtspRequest(self.SETUP)
                self.frameNumber = 0
                self.clearVideo()
                break

    def exitClient(self):
        self.master.destroy()
        self.rtpSocket.close()
        self.exitFlag = 1
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        if os.path.isfile(cachename):
            os.remove(cachename)
    
    def connectToServer(self):
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.settimeout(0.5)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)

    def sendRtspRequest(self, requestCode):
        if requestCode == self.SETUP and self.state == self.INIT:
            self.rtspSeq += 1
            request = "SETUP {} RTSP/1.0\nCSeq: {}\nTransport: RTP/UDP; client_port= {}".format(self.filename, str(self.rtspSeq), str(self.rtpPort))
            self.requestSent = self.SETUP 
        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq += 1
            request = "PLAY {} RTSP/1.0\ncSeq: {}\nSession: {}".format(self.filename, str(self.rtspSeq), str(self.sessionId))
            self.requestSent = self.PLAY
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq += 1
            request = "PAUSE {} RTSP/1.0\ncSeq: {}\nSession: {}".format(self.filename, str(self.rtspSeq), str(self.sessionId))
            self.requestSent = self.PAUSE
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            self.rtspSeq += 1
            request = "TEARDOWN {} RTSP/1.0\ncSeq: {}\nSession: {}".format(self.filename, str(self.rtspSeq), str(self.sessionId))
            self.requestSent = self.TEARDOWN
        else:
            return
        self.rtspSocket.sendall(request.encode())
        print('\nData sent:\n' + request)
    
    def receiveRtspReply(self):
        while True:
            try:
                reply = self.rtspSocket.recv(1024)
                if reply:
                    self.parseRtspReply(reply.decode('utf-8'))
            except:
                if self.exitFlag == 1:
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
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.playEvent.set()
    
    def openRtpPort(self):
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.settimeout(0.5)
        try:
            self.rtpSocket.bind(('', self.rtpPort))
        except:
            tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)
    
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
                
    def writeFrame(self, data):
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, 'wb')
        file.write(data)
        file.close()
        return cachename

    def updateVideo(self, imageFile):
        img = Image.open(imageFile)
        photoWidth = int(img.size[0]/img.size[1]*500)
        photo = ImageTk.PhotoImage(img.resize((photoWidth,500), Image.ANTIALIAS))
        self.label.configure(image=photo, height=500)
        self.label.image = photo
    
    def clearVideo(self):
        self.label.configure(image='')
        self.label['height'] = 35
    
    def handler(self):
        self.pauseVideo()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:
            self.playVideo()
