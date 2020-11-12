from tkinter import *
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
    DESCRIBE = 1
    PLAY = 2
    PAUSE = 3
    TEARDOWN = 4

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
        self.setupFlag = threading.Event()
        self.playEvent = threading.Event()
        self.stopFlag = threading.Event()
        self.exitFlag = threading.Event()
        self.setupVideo()
        self.openRtpPort()


    def createWidgets(self):
        """Build GUI."""
        # Create Describe button
        self.describe = Button(self.master, width=30, padx=3, pady=3)
        self.describe['text'] = "DESCRIBE"
        self.describe['command'] = self.describeVideo
        self.describe.grid(row=2, column=0, padx=2, pady=2)

        # Create Play button
        self.play = Button(self.master, width=30, padx=3, pady=3)
        self.play['text'] = "PLAY"
        self.play['command'] = self.playVideo
        self.play.grid(row=2, column=1, padx=2, pady=2)

        # Create Pause button
        self.pause = Button(self.master, width=30, padx=3, pady=3)
        self.pause['text'] = "PAUSE"
        self.pause['command'] = self.pauseVideo
        self.pause.grid(row=2, column=2, padx=2, pady=2)

        # Create Stop button
        self.stop = Button(self.master, width=30, padx=3, pady=3)
        self.stop['text'] = "STOP"
        self.stop['command'] = self.stopVideo
        self.stop.grid(row=2, column=3, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=35)
        self.label.grid(row=0, column=0, columnspan=4, padx=5, pady=5)

        # Create scroll bar
        self.bar = Scale(self.master, length=500, orient=HORIZONTAL, showvalue=0)
        self.bar.grid(row=1, column=1, columnspan=2, padx=3, pady=3)

        # Create text fields for time
        self.totaltime = Label(self.master, text="00:00 / 00:00")
        self.totaltime.grid(row=1, column=0, padx=3, pady=3)
        self.remaintime = Label(self.master, text="- 00:00")
        self.remaintime.grid(row=1, column=3, padx=3, pady=3)
    

    def setupVideo(self):
        """Setup button handler."""
        if self.state == self.INIT:
            threading.Thread(target=self.receiveRtspReply).start()
            self.sendRtspRequest(self.SETUP)
    

    def exitClient(self):
        """Teardown button handler."""
        self.clearFrame()
        self.master.destroy()
        self.rtpSocket.close()
        self.exitFlag.set()
    
    
    def describeVideo(self):
        self.sendRtspRequest(self.DESCRIBE)

    
    def pauseVideo(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)
    
    
    def playVideo(self):
        """Play button handler."""
        if self.state == self.READY:
            threading.Thread(target=self.listenRtp).start()
            self.sendRtspRequest(self.PLAY)
    

    def stopVideo(self):
        """Stop button handler."""
        self.stopFlag.set()
        self.sendRtspRequest(self.TEARDOWN)
        self.setupFlag.wait()
        self.clearFrame()
        self.rtspSeq = 0
        self.sessionId = 0
        self.frameNumber = 0
        self.sendRtspRequest(self.SETUP)
        self.setupFlag.clear()
    

    def listenRtp(self):
        """Listen for RTP packets."""
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
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, 'wb')
        file.write(data)
        file.close()
        return cachename
    

    def updateVideo(self, imageFile):
        """Update the image file as video frame in the GUI."""
        img = Image.open(imageFile)
        photoWidth = int(img.size[0]/img.size[1]*500)
        photo = ImageTk.PhotoImage(img.resize((photoWidth,500), Image.ANTIALIAS))
        self.label.configure(image=photo, height=500)
        self.label.image = photo
    
    
    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.settimeout(0.5)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)


    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        if requestCode == self.SETUP and self.state == self.INIT:
            self.rtspSeq += 1
            request = "SETUP {} RTSP/1.0\nCSeq: {}\nTransport: RTP/UDP; client_port= {}".format(self.filename, str(self.rtspSeq), str(self.rtpPort))
            self.requestSent = self.SETUP
        elif requestCode == self.DESCRIBE:
            self.rtspSeq += 1
            request = "DESCRIBE {} RTSP/1.0\ncSeq: {}\nSession: {}".format(self.filename, str(self.rtspSeq), str(self.sessionId))
            self.requestSent = self.DESCRIBE
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
        """Receive RTSP reply from the server."""
        while True:
            try:
                reply = self.rtspSocket.recv(1024)
                if reply:
                    self.parseRtspReply(reply.decode('utf-8'))
            except:
                if self.exitFlag.isSet():
                    self.rtspSocket.shutdown(socket.SHUT_RDWR)
                    self.rtspSocket.close()
                    break
    

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
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
                    elif self.requestSent == self.DESCRIBE:
                        self.writeDescriptionFile('\n'.join(reply[3:]))
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.playEvent.set()
                        if self.stopFlag.isSet():
                            self.setupFlag.set()
                            self.stopFlag.clear()
    
    
    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.settimeout(0.5)
        try:
            self.rtpSocket.bind(('', self.rtpPort))
        except:
            tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

    
    def clearFrame(self):
        """Clear cache and video frame in the GUI."""
        self.label.configure(image='')
        self.label['height'] = 35
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        if os.path.isfile(cachename):
            os.remove(cachename)
    
    
    def writeDescriptionFile(self, description):
        """Write description file which contains response of DESCRIBE request."""
        with open('describe.txt', 'w') as f:
            f.write(description)
    

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseVideo()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:
            self.playVideo()
