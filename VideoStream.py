import io
import imageio

class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.reader = imageio.get_reader(filename, 'ffmpeg')
		except:
			raise IOError
		self.frameCnt = 0
		self.frameNum = 0
	
	def countFrame(self):
		reader = imageio.get_reader(self.filename, 'ffmpeg')
		self.frameCnt = 0
		while True:
			try:
				reader.get_next_data()
				self.frameCnt += 1
			except:
				break
	
	def setFrameCnt(self, cnt):
		self.frameCnt = cnt
		
	def nextFrame(self):
		"""Get next frame."""
		try:
			buffer = io.BytesIO()
			data = self.reader.get_next_data()
			imageio.imwrite(buffer, data, format='JPEG')
			self.frameNum += 1
			return buffer.getvalue()
		except:
			return bytes(0)
	
	def getFrame(self, index):
		try:
			buffer = io.BytesIO()
			data = self.reader.get_data(index)
			imageio.imwrite(buffer, data, format='JPEG')
			self.frameNum = index
			return buffer.getvalue()
		except:
			return bytes(0)
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum


# class VideoStream:
# 	def __init__(self, filename):
# 		self.filename = filename
# 		try:
# 			self.file = open(filename, 'rb')
# 		except:
# 			raise IOError
# 		self.frameNum = 0
		
# 	def nextFrame(self):
# 		"""Get next frame."""
# 		data = self.file.read(5) # Get the framelength from the first 5 bits
# 		if data: 
# 			framelength = int(data)
							
# 			# Read the current frame
# 			data = self.file.read(framelength)
# 			self.frameNum += 1
# 		return data
		
# 	def frameNbr(self):
# 		"""Get frame number."""
# 		return self.frameNum
