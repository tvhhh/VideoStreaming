from tkinter import *
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os, time

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
        self.teardownAcked = 0
        self.frameNumber = 0
        self.requestedFrame = -1
        self.setupFlag = threading.Event()
        self.playEvent = threading.Event()
        self.exitFlag = threading.Event()
        self.setupVideo()
        self.openRtpPort()

        self.fps = 0

        # statistic
        self.timeStartPlaying = 0
        self.receivedBytes = 0
        self.totalReceivedFrames = 0 


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

        # Create backward and forward button
        self.backward = Button(self.master, width=30, padx=3, pady=3)
        self.backward['text'] = "<<"
        self.backward['command'] = self.fastBackward
        self.backward.grid(row=1, column=1, padx=2, pady=2)
        self.forward = Button(self.master, width=30, padx=3, pady=3)
        self.forward['text'] = ">>"
        self.forward['command'] = self.fastForward
        self.forward.grid(row=1, column=2, padx=2, pady=2)

        # Create text fields for time
        self.currentTime = StringVar()
        self.currentTime.set("00:00")
        self.currentTimeLabel = Label(self.master, textvariable=self.currentTime)
        self.currentTimeLabel.grid(row=1, column=0, padx=3, pady=3)

        self.totalTime = StringVar()
        self.totalTime.set("00:00")
        self.totalTimeLabel = Label(self.master, textvariable=self.totalTime)
        self.totalTimeLabel.grid(row=1, column=3, padx=3, pady=3)

        # Create text fields for statistic
        ## video rate: KB/s
        self.videoRateSpeed = StringVar()
        self.videoRateLabel = Label(self.master, textvariable=self.videoRateSpeed)
        self.videoRateLabel.grid(row=3, column=0, columnspan=4, padx=2, pady=2)
        self.setVideoRate(0, 0)

        ## loss rate: %
        self.lossRatePercent = StringVar()
        self.lossRateLabel = Label(self.master, textvariable=self.lossRatePercent)
        self.lossRateLabel.grid(row=4, column=0, columnspan=4, padx=2, pady=2)
        self.setLossRate(0, 0)


    def setupVideo(self):
        """Setup button handler."""
        if self.state == self.INIT:
            threading.Thread(target=self.receiveRtspReply).start()
            self.sendRtspRequest(self.SETUP)


    def exitClient(self):
        """Exit client launcher."""
        self.exitFlag.set()
        self.clearFrame()
        self.master.destroy()
        self.rtpSocket.close()
    
    
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
            self.playEvent.clear()
            self.sendRtspRequest(self.PLAY)
            self.timeStartPlaying = time.time()
    

    def fastForward(self):
        if not self.state == self.INIT:
            self.sendRtspRequest(self.PAUSE)
            self.playEvent.wait()
            self.requestedFrame = self.frameNumber + self.fps * 5
            self.sendRtspRequest(self.PLAY)
    

    def fastBackward(self):
        if not self.state == self.INIT:
            self.sendRtspRequest(self.PAUSE)
            self.playEvent.wait()
            self.frameNumber -= self.fps * 5
            self.requestedFrame = self.frameNumber
            if self.requestedFrame < 0:
                self.requestedFrame = 0
            self.sendRtspRequest(self.PLAY)
    

    def stopVideo(self):
        """Stop button handler."""
        self.pauseVideo()
        if tkMessageBox.askokcancel("Stop?", "Your video will be terminated."):
            self.sendRtspRequest(self.TEARDOWN)
            self.setupFlag.wait()
            self.clearFrame()
            self.resetVideoRate()
            self.resetLossRate()
            self.setCurrentTime(0)
            self.rtspSeq = 0
            self.sessionId = 0
            self.teardownAcked = 0
            self.frameNumber = 0
            self.sendRtspRequest(self.SETUP)
            self.setupFlag.clear()
        else:
            self.playVideo()
    

    def listenRtp(self):
        """Listen for RTP packets."""
        while True:
            try:
                data = self.rtpSocket.recv(40960)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    currFrameNumber = rtpPacket.seqNum()

                    if currFrameNumber > self.frameNumber:
                        self.frameNumber = currFrameNumber
                        self.updateVideo(self.writeFrame(rtpPacket.getPayload()))

                        currentTime = self.frameNumber // self.fps
                        self.setCurrentTime(currentTime)

                        self.receivedBytes += len(rtpPacket.getPacket())
                        self.setVideoRate(time.time() - self.timeStartPlaying, self.receivedBytes)

                        self.totalReceivedFrames += 1
                        self.setLossRate(currFrameNumber, self.totalReceivedFrames)
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
        elif requestCode == self.PLAY:
            self.rtspSeq += 1
            request = "PLAY {} RTSP/1.0\ncSeq: {}\nSession: {}\nRequestedFrame: {}".format(self.filename, str(self.rtspSeq), str(self.sessionId), self.requestedFrame)
            self.requestedFrame = -1
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
                        frameCnt = int(reply[3].split(' ')[1])
                        self.fps = int(reply[4].split(' ')[1])
                        totalTime = int(frameCnt/self.fps)
                        self.setTotalTime(totalTime)
                    elif self.requestSent == self.DESCRIBE:
                        self.writeDescriptionFile('\n'.join(reply[3:]))
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.setupFlag.set()
    
    
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
    

    def setLossRate(self, totalFrames, totalReceivedFrames):
        lossFrames = totalFrames - totalReceivedFrames
        if lossFrames < 0:
            lossFrames = 0
        packetCount = "Loss / Total (packets) = {:5d} / {:5d}".format(lossFrames,totalFrames)
        lossRate = "Loss rate = {:.2f} %".format(0 if totalFrames == 0 else lossFrames/totalFrames*100)
        self.lossRatePercent.set(packetCount + '\t\t' + lossRate)


    def resetLossRate(self):
        self.totalReceivedFrames = 0
        self.setLossRate(0, 0)


    def setVideoRate(self, period, receivedBytes):
        self.videoRateSpeed.set("Video rate = {:.2f} KB/s".format(0 if period == 0 else (receivedBytes/period)/1024))


    def resetVideoRate(self):
        self.receivedBytes = 0
        self.timeStartPlaying = 0
        self.setVideoRate(0, 0)
    
    
    def writeDescriptionFile(self, description):
        """Write description file which contains response of DESCRIBE request."""
        with open('describe.txt', 'w') as f:
            f.write(description)
    

    def setTotalTime(self, totalTime):
        mm = totalTime // 60
        ss = totalTime % 60
        self.totalTime.set("{:02d}:{:02d}".format(mm, ss))
    

    def setCurrentTime(self, currentTime):
        mm = currentTime // 60
        ss = currentTime % 60
        self.currentTime.set("{:02d}:{:02d}".format(mm, ss))
    

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseVideo()
        if tkMessageBox.askokcancel("Quit?", "Do you really want to quit?"):
            self.exitClient()
        else:
            self.playVideo()
