import serial
from picamera.array import PiRGBArray
from picamera import PiCamera
import trans
import argparse
import time
import cv2
import math
import numpy as np
import zbarlight
import imutils
from PIL import Image

def parseUrl(url):
  #separate address & params
  result = { 'success': True, 'params': {} }
  split = url.split('?')
  #extract address
  address_half = split[0]
  address_split = address_half.split('bitcoin:')
  if len(address_split) == 2:
    result['address'] = address_split[1]
  else:
    return { 'success': False, 'params': {} }
  #extract params
  if len(split) > 1:
    params_half = split[1]
    params = params_half.split('&')
    for param in params:
      print param
      pair = param.split('=')
      result['params'][pair[0]] = pair[1] 
  return result

def overlayImage(src, overlay, posx, posy, S, D):
  for x in range(overlay.width):
    if x+posx < src.width:
      for y in range(overlay.height):
        if y+posy < src.width:

          source = cv2.cv.Get2D(src, y+posy, x+posx)
          over   = cv2.cv.Get2D(overlay, y, x)
          merger = [0, 0, 0, 0]

          for i in range(3):
            merger[i] = (S[i]*source[i]+D[i]*over[i])

          merged = tuple(merger)
          cv2.cv.Set2D(src, y+posy, x+posx, merged)

def distance(p,q):
  return math.sqrt(math.pow(math.fabs(p[0]-q[0]),2)+math.pow(math.fabs(p[1]-q[1]),2))

def lineEquation(l,m,j):
  a = -((m[1] - l[1])/(m[0] - l[0]))
  b = 1.0
  c = (((m[1] - l[1])/(m[0] - l[0]))*l[0]) - l[1]
  try:
    pdist = (a*j[0]+(b*j[1])+c)/math.sqrt((a*a)+(b*b))
  except:
    return 0
  else:
    return pdist

def lineSlope(l,m):
  dx = m[0] - l[0]
  dy = m[1] - l[1]
  if dy != 0:
    align = 1
    dxy = dy/dx
    return dxy,align
  else:
    align = 0
    dxy = 0.0
    return dxy,align

def getSquares(contours,cid):
  x,y,w,h= cv2.boundingRect(contours[cid])
  return x,y,w,h

def updateCorner(p,ref,baseline,corner):
  temp_dist = distance(p,ref)
  if temp_dist > baseline:
    baseline = temp_dist
    corner = p
  return baseline,corner

def getVertices(contours,cid,slope,quad):
  M0 = (0.0,0.0)
  M1 = (0.0,0.0)
  M2 = (0.0,0.0)
  M3 = (0.0,0.0)
  x,y,w,h = cv2.boundingRect(contours[cid])
  A = (x,y)
  B = (x+w,y)
  C = (x+w,h+y)
  D = (x,y+h)
  W = ((A[0]+B[0])/2,A[1])
  X = (B[0],(B[1]+C[1])/2)
  Y = ((C[0]+D[0])/2,C[1])
  Z = (D[0],(D[1]+A[1])/2)
  dmax = []
  for i in range(4):
    dmax.append(0.0)
  pd1 = 0.0
  pd2 = 0.0
  if(slope > 5 or slope < -5 ):
    for i in range(len(contours[cid])):
      pd1 = lineEquation(C,A,contours[cid][i])
      pd2 = lineEquation(B,D,contours[cid][i])
      if(pd1 >= 0.0 and pd2 > 0.0):
        dmax[1],M1 = updateCorner(contours[cid][i],W,dmax[1],M1)
      elif(pd1 > 0.0 and pd2 <= 0):
        dmax[2],M2 = updateCorner(contours[cid][i],X,dmax[2],M2)
      elif(pd1 <= 0.0 and pd2 < 0.0):
        dmax[3],M3 = updateCorner(contours[cid][i],Y,dmax[3],M3)
      elif(pd1 < 0 and pd2 >= 0.0):
        dmax[0],M0 = updateCorner(contours[cid][i],Z,dmax[0],M0)
      else:
        continue
  else:
    halfx = (A[0]+B[0])/2
    halfy = (A[1]+D[1])/2
    for i in range(len(contours[cid])):
      if(contours[cid][i][0][0]<halfx and contours[cid][i][0][1]<=halfy):
        dmax[2],M0 = updateCorner(contours[cid][i][0],C,dmax[2],M0)
      elif(contours[cid][i][0][0]>=halfx and contours[cid][i][0][1]<halfy):
        dmax[3],M1 = updateCorner(contours[cid][i][0],D,dmax[3],M1)
      elif(contours[cid][i][0][0]>halfx and contours[cid][i][0][1]>=halfy):
        dmax[0],M2 = updateCorner(contours[cid][i][0],A,dmax[0],M2)
      elif(contours[cid][i][0][0]<=halfx and contours[cid][i][0][1]>halfy):
        dmax[1],M3 = updateCorner(contours[cid][i][0],B,dmax[1],M3)
  quad.append(M0)
  quad.append(M1)
  quad.append(M2)
  quad.append(M3)
  return quad

def updateCornerOr(orientation,IN):
  if orientation == 0:
    M0 = IN[0]
    M1 = IN[1]
    M2 = IN[2]
    M3 = IN[3]
  elif orientation == 1:
    M0 = IN[1]
    M1 = IN[2]
    M2 = IN[3]
    M3 = IN[0]
  elif orientation == 2:
    M0 = IN[2]
    M1 = IN[3]
    M2 = IN[0]
    M3 = IN[1]
  elif orientation == 3:
    M0 = IN[3]
    M1 = IN[0]
    M2 = IN[1]
    M3 = IN[2]

  OUT = []
  OUT.append(M0)
  OUT.append(M1)
  OUT.append(M2)
  OUT.append(M3)

  return OUT

def cross(v1,v2):
  cr = v1[0]*v2[1] - v1[1]*v2[0]
  return cr


def four_point_transform(image, pts):
  # compute the width of the new image, which will be the
  # maximum distance between bottom-right and bottom-left
  # x-coordiates or the top-right and top-left x-coordinates
  widthA = np.sqrt(
      ((pts[2][0] - pts[3][0]) ** 2) + ((pts[2][1] - pts[3][1]) ** 2))
  widthB = np.sqrt(
      ((pts[1][0] - pts[0][0]) ** 2) + ((pts[1][1] - pts[0][1]) ** 2))
  maxWidth = max(int(widthA), int(widthB))

  # compute the height of the new image, which will be the
  # maximum distance between the top-right and bottom-right
  # y-coordinates or the top-left and bottom-left y-coordinates
  heightA = np.sqrt(
      ((pts[1][0] - pts[2][0]) ** 2) + ((pts[1][1] - pts[2][1]) ** 2))
  heightB = np.sqrt(
      ((pts[0][0] - pts[3][0]) ** 2) + ((pts[0][1] - pts[3][1]) ** 2))
  maxHeight = max(int(heightA), int(heightB))

  # now that we have the dimensions of the new image, construct
  # the set of destination points to obtain a "birds eye view",
  # (i.e. top-down view) of the image, again specifying points
  # in the top-left, top-right, bottom-right, and bottom-left
  # order
  dst = np.array([
      [0, 0],
      [maxWidth - 1, 0],
      [maxWidth - 1, maxHeight - 1],
      [0, maxHeight - 1]], dtype="float32")

  # compute the perspective transform matrix and then apply it
  M = cv2.getPerspectiveTransform(pts, dst)
  warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

  # return the warped image
  return warped

def getIntersection(a1,a2,b1,b2,intersection):
  p = a1
  q = b1
  r = (a2[0]-a1[0],a2[1]-a1[1])
  s = (b2[0]-b1[0],b2[1]-b1[1])
  if cross(r,s) == 0:
    return False, intersection
  t = cross((q[0]-p[0],q[1]-p[1]),s)/float(cross(r,s))
  intersection = (int(p[0]+(t*r[0])),int(p[1]+(t*r[1])))
  return True,intersection

#############################

def start():
  print "Starting capture..."
  camera = PiCamera()
  camera.resolution = (640,480)
  camera.framerate = 24
  camera.hlip = False

  rawCapture = PiRGBArray(camera,size=(640,480))
  time.sleep(0.1)

  qrResult = {}
  confirmationFrames = 5
  frameCountdown = 140

  for frame in camera.capture_continuous(rawCapture,format="bgr",use_video_port=True):
    #GIVEUP AFTER SO MANY FRAMES
    frameCountdown-=1
    if (frameCountdown <= 0):
      break

    image = frame.array
    img = image
    
    edges = cv2.Canny(image,100,200)
    contours,hierarchy = cv2.findContours(edges,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    mu = []
    mc = []
    mark = 0
    for x in range(0,len(contours)):
      mu.append(cv2.moments(contours[x]))

    for m in mu:
      if m['m00'] != 0:
        mc.append((m['m10']/m['m00'],m['m01']/m['m00']))
      else:
        mc.append((0,0))

    for x in range(0,len(contours)):
      k = x
      c = 0
      while(hierarchy[0][k][2] != -1):
        k = hierarchy[0][k][2]
        c = c + 1
      if hierarchy[0][k][2] != -1:
        c = c + 1

      if c >= 5:
        if mark == 0:
          A = x
        elif mark == 1:
          B = x
        elif mark == 2:
          C = x
        mark = mark+1

    if mark >2 :
      AB = distance(mc[A],mc[B])
      BC = distance(mc[B],mc[C])
      AC = distance(mc[A],mc[C])

      if(AB>BC and AB>AC):
        outlier = C
        median1 = A
        median2 = B
      elif(AC>AB and AC>BC):
        outlier = B
        median1 = A 
        median2 = C 
      elif(BC>AB and BC>AC):
        outlier = A 
        median1 = B
        median2 = C

      top = outlier
      dist = lineEquation(mc[median1],mc[median2],mc[outlier])
      slope,align = lineSlope(mc[median1],mc[median2])

      if align == 0:
        bottom = median1
        right = median2
      elif(slope < 0 and dist < 0):
        bottom = median1
        right = median2
        orientation = 0
      elif(slope > 0 and dist < 0):
        right = median1
        bottom = median2
        orientation = 1
      elif(slope < 0 and dist > 0):
        right = median1
        bottom = median2
        orientation = 2
      elif(slope > 0 and dist > 0):
        bottom = median1
        right = median2
        orientation = 3

      areatop = 0.0
      arearight = 0.0
      areabottom = 0.0

      if(top < len(contours) and right < len(contours) and bottom < len(contours) and cv2.contourArea(contours[top]) > 10 and cv2.contourArea(contours[right]) > 10 and cv2.contourArea(contours[bottom]) > 10):
        #FLIP, SCAN, AND SAVE BEFORE ADDING COLOURS 
        scanimg = cv2.flip(img,1)

        #DRAW DETECTED LINES
        tempL = []
        tempM = []
        tempO = []
        N = (0,0)
        tempL = getVertices(contours,top,slope,tempL)
        tempM = getVertices(contours,right,slope,tempM)
        tempO = getVertices(contours,bottom,slope,tempO)
        L = updateCornerOr(orientation,tempL)
        M = updateCornerOr(orientation,tempM)
        O = updateCornerOr(orientation,tempO)
        
        iflag,N = getIntersection(M[1],M[2],O[3],O[2],N)
        cv2.circle(img,N,1,(0,0,255),2)
        cv2.drawContours(img,contours,top,(255,0,0),2)
        cv2.drawContours(img,contours,right,(0,255,0),2)
        cv2.drawContours(img,contours,bottom,(0,0,255),2)

        #SCAN FLIPPED
        code = zbarlight.scan_codes('qrcode', Image.fromarray(scanimg))
        if code == None:
          print "No qr found"
        elif len(code) == 1:
          confirmationFrames -= 1
          qrResult = parseUrl(code[0])
          if qrResult['success'] and (confirmationFrames <= 0):
            break
    
    #DISPLAY      
    img = cv2.flip(img,1)
    #draw arrow
    cv2.line(img,(630,470),(590,430),(240,240,240),2)
    cv2.line(img,(630,470),(630,460),(240,240,240),2)
    cv2.line(img,(630,470),(620,470),(240,240,240),2)
    
    #add text
    cv2.putText(img, "Show your address QR code", (50, 50), cv2.FONT_HERSHEY_PLAIN, 2, (240,240,240), 2, cv2.CV_AA)
    cv2.putText(img, "Camera", (560, 420), cv2.FONT_HERSHEY_PLAIN, 1, (240,240,240), 2, cv2.CV_AA)

    cv2.namedWindow("window", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("window", cv2.WND_PROP_FULLSCREEN, 1)
    cv2.imshow("window", img)

    key = cv2.waitKey(1) & 0xFF
    rawCapture.truncate(0)
    if key == ord("q"):
      break

  camera.close()
  cv2.destroyAllWindows()
  for i in range (1,5):
    cv2.waitKey(1)
  return qrResult