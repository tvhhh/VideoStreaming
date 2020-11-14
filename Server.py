import os, sys, socket

from ServerWorker import ServerWorker
from VideoStream import VideoStream

VIDEO_FILE_EXT = ('.webm','.mpg','.mp2','.mpeg','.mpe','.mpv','.mjpeg','.mp4','.m4p','.m4v','.avi','.wmv','.mov','.qt')

class Server:

	def __init__(self):
		print("Preparing server...")
		self.getServerInfo()
		print("Server done.")

	def getServerInfo(self):
		self.serverInfo = {}
		for file in os.listdir(os.getcwd()):
			if file.endswith(VIDEO_FILE_EXT):
				videoSream = VideoStream(file)
				videoSream.countFrame()
				self.serverInfo[file] = videoSream.frameCnt
	
	def main(self):
		try:
			SERVER_PORT = int(sys.argv[1])
		except:
			print("[Usage: Server.py Server_port]\n")
		rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		rtspSocket.bind(('', SERVER_PORT))
		rtspSocket.listen(5) 

		# Receive client info (address,port) through RTSP/TCP session
		while True:
			clientInfo = {}
			clientInfo['rtspSocket'] = rtspSocket.accept()
			clientInfo['rtspPort'] = SERVER_PORT
			serverInfo = self.serverInfo
			ServerWorker(clientInfo, serverInfo).run()

if __name__ == "__main__":
	(Server()).main()


