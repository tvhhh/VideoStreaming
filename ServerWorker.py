from random import randint
import sys, traceback, threading, socket, os

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
	SETUP = 'SETUP'
	DESCRIBE = 'DESCRIBE'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	SWITCH = 'SWITCH'
	GET_LIST = 'GET_LIST'
	
	INIT = 0
	READY = 1
	PLAYING = 2
	SWITCHING = 3
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	clientInfo = {}
	serverInfo = {}
	
	def __init__(self, clientInfo, serverInfo):
		self.clientInfo = clientInfo
		self.serverInfo = serverInfo
		self.requestType = ''
		self.filename = ''
		self.fps = 25
		
	def run(self):
		threading.Thread(target=self.recvRtspRequest).start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.clientInfo['rtspSocket'][0]
		while True:
			data = connSocket.recv(256)
			if data:
				print("Data received:\n" + data.decode("utf-8"))
				self.processRtspRequest(data.decode("utf-8"))
	
	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		self.requestType = line1[0]
		
		# Get the media file name
		self.filename = line1[1]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request
		if self.requestType == self.SETUP:
			if self.state == self.INIT or self.state == self.SWITCHING:
				# Update state
				print("processing SETUP\n")
				
				try:
					self.clientInfo['videoStream'] = VideoStream(self.filename)
					self.state = self.READY
				except IOError:
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
				
				# Generate a randomized RTSP session ID
				self.clientInfo['session'] = randint(100000, 999999)
				
				# Send RTSP reply
				self.replyRtsp(self.OK_200, seq[1])
				
				# Get the RTP/UDP port from the last line
				self.clientInfo['rtpPort'] = request[2].split(' ')[3]

				# Initialize a frame counter
				self.frameCnt = 0
		
		# Process DESCRIBE request
		elif self.requestType == self.DESCRIBE:
			print("processing DESCRIBE\n")
			self.replyRtsp(self.OK_200, seq[1])
		
		# Process PLAY request 		
		elif self.requestType == self.PLAY:
			if self.state == self.READY:
				print("processing PLAY\n")
				self.state = self.PLAYING

				requestedFrame = int(request[3].split(' ')[1])
				frameCnt = self.serverInfo[self.filename]
				if requestedFrame >= frameCnt:
					requestedFrame = frameCnt - 1
				self.clientInfo['requestedFrame'] = requestedFrame

				# Create a new socket for RTP/UDP
				self.clientInfo['rtpSocket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1])
				
				# Create a new thread and start sending RTP packets
				self.clientInfo['event'] = threading.Event()
				self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.clientInfo['worker'].start()
		
		# Process PAUSE request
		elif self.requestType == self.PAUSE:
			if self.state == self.PLAYING:
				print("processing PAUSE\n")
				self.state = self.READY
				
				self.clientInfo['event'].set()
			
				self.replyRtsp(self.OK_200, seq[1])
		
		# Process TEARDOWN request
		elif self.requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")
			self.state = self.INIT

			self.clientInfo['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1])
			
			# Close the RTP socket
			self.clientInfo['rtpSocket'].close()
		
		# Process SWITCH request
		elif self.requestType == self.SWITCH:
			print("processing SWITCH\n")
			self.state = self.SWITCHING

			self.clientInfo['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1])
			
			# Close the RTP socket
			self.clientInfo['rtpSocket'].close()
		
		# Process GET_LIST request
		elif self.requestType == self.GET_LIST:
			print("processing GET_LIST\n")

			self.replyRtsp(self.OK_200, seq[1])
			
	
	def sendRtp(self):
		"""Send RTP packets over UDP."""
		while True:
			self.clientInfo['event'].wait(1/self.fps) 
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet(): 
				break

			if self.clientInfo['requestedFrame'] != -1:
				data = self.clientInfo['videoStream'].getFrame(self.clientInfo['requestedFrame'])
				self.clientInfo['requestedFrame'] = -1
			else:
				data = self.clientInfo['videoStream'].nextFrame()
			
			if data:
				frameNumber = self.clientInfo['videoStream'].frameNbr()
				try:
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
					self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
					self.frameCnt += 1
				except:
					print("Connection Error")
					#print('-'*60)
					#traceback.print_exc(file=sys.stdout)
					#print('-'*60)

	def makeRtp(self, payload, frameNbr):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0

		extid = 0
		extlen = 1 # the length of the extension in 32-bit units,
		frameCnt = self.frameCnt + 1
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload, extid, extlen, frameCnt=frameCnt)
		
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq):
		"""Send RTSP reply to the client."""
		if code == self.OK_200:
			# reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
			reply = "RTSP/1.0 200 OK\nCSeq: {}".format(seq)
			
			if self.requestType == self.SETUP:
				frameCnt = self.serverInfo[self.filename]
				session = "\nSession: {}".format(self.clientInfo['session'])
				meta = "\nFrames: {}\nFps: {}".format(frameCnt, self.fps)
				reply = reply + session + meta
			
			elif self.requestType == self.DESCRIBE:
				session = "\nSession: {}".format(self.clientInfo['session'])
				body = "\nv={}\nm=video {} RTP/AVP {}\na=control:streamid={}\na=mimetype:string;\"video/MJPEG\""\
					.format(0, self.clientInfo['rtspPort'], 26, self.clientInfo['session'])
				content = "\n\nContent-Base: {}\nContent-Type: {}\nContent-Length: {}"\
					.format(self.filename, "application/sdp", len(body))
				reply = reply + session + body + content
			
			elif self.requestType == self.GET_LIST:
				lst = ""
				for vid in self.serverInfo:
					lst = lst + '\n' + vid
				reply = reply + lst

			else:
				session = "\nSession: {}".format(self.clientInfo['session'])
				reply = reply + session
			
			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())

		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
	
