#This is for a lat/long mesh going north-south, west-east.
#A rotated latLon grid would need extra logic to account for the rotation.

import numpy as np

import helpers

print "Expected format: lats[0->1] goes South. lons[0->1] goes east.\n" #matters in forming searchDisk

def area_latLonCell(latN, latS, dLon, r):
  #input angles in radians of northern bound, southern bound, and width of rectangle in radians
  #r is radius of circle in meters
  
  solidAngle = dLon*(np.sin(latN)-np.sin(latS))
  area = solidAngle*r*r
  return area
    
def calc_areaLatStrips(lat, r):
  #return the areas of the latitude strips centered around the specified points.
  #lat[0] is north and lat[nLat-1] is south.
  #for multiple evenly spaced cells at a given latitude, areaCell = areaLats[iLat]/nLon
  
  #caps of sphere for poles and latitude strips for rest.
  dLon = 2.*np.pi
  nLat = len(lat)
  areaLats = np.empty(nLat, dtype=float)
  nonPole = np.arange(1,nLat-1) #[1,nlat-2]
  latsN = .5*(lat[nonPole]+lat[nonPole-1]) #face is halfway between centers
  latsS = .5*(lat[nonPole]+lat[nonPole+1])
  areaLats[nonPole] = area_latLonCell(latsN, latsS, dLon, r)
  
  #assuming symmetric latitudes for poles, area of cap is just residual.
  #who knows if this has more roundoff error than just computing area of cap zone.
  #either way, shouldn't matter too much.
  nonPoleArea = np.sum(areaLats[nonPole]); totArea = 4.*np.pi*r*r
  #print nonPoleArea, totArea
  areaCap = (totArea-nonPoleArea)/2
  areaLats[0] = areaCap; areaLats[nLat-1] = areaCap
  
  return areaLats

iLonRef = 0
def calc_lonIndicesWithinLength(lats, nLon, r, distRegion):
  #return the number of longitude indices within given length at each specified latitude.
  #imagine this is like a pyramid with more at the poles and less at the equator.
  #since radius, take nLons[iLat] points both east and west for disk
  dRadLon = 2.*np.pi/nLon #[0,2pi)
  dLons = r*np.cos(lats)*dRadLon; #arc lengths of pieces of latitude circles
  dLons = np.maximum(dLons, 1.e-12) #elementwise to avoid /0
  nLons = np.floor(distRegion/dLons).astype(int);
  #since made to index left and right, as max:
  #want len(range(left, right))=nLons (remember, not w/ right endpt)
  nLons = np.minimum(nLons, nLon/2)
  
  #indices are: np.arange(-nLons/2, nLons/2)%nLons...maybe np.sort(...)
  return nLons

def calc_latIndicesWithinLength(nLats, r, distRegion):
  #return the number of latitude indices within given length
  dRadLat = np.pi/(nLats-1) #[-pi/2, pi/2]
  distSN = r*dRadLat #arc length South-North
  nNorth = int(np.floor(distRegion/distSN))
  
  #actual indices are:
  #indN = np.min((iLat+nNorth, nLat-1)); indS = np.max((iLat-nNorth, 0))
  return nNorth

def gatherInds_region_latBox_1AtPole(iLat0, iLon0, nLat, nLon, latCell, lonCell,
                             nLatIndsLength, nLonIndsLength, r, distRegion):
  #return list of lat,lon indices within specified spatial region of given point.
  #for efficiency, call 1x per latitude and just shift lon indices.
  #nLonIndsLength = calc_lonIndicesWithinLength(lats, nLon, r, distRegion)...1x per mesh
  #Note that self=[iLat0,iLon0] pair will be in the returned region.
  #for added efficiency, only return index of 1 value at pole since all really same point.
  
  #we'll do this by searching within the input bounding box.
  lat0 = latCell[iLat0]; lon0 = lonCell[iLon0]
  indNPole = np.max((iLat0-nLatIndsLength, 0)); indSPole = np.min((iLat0+nLatIndsLength, nLat-1))
  indN = np.max((indNPole, 1)); indS = np.min((indSPole, nLat-2))
  candLats = np.arange(indN,indS+1) #include endpoint
  
  #go east at each latitude until too far
  inRegion_lat = []; inRegion_lon = []
  for iLat in candLats:
    #since symmetric about longitude, just have to plus distance and include
    # 0 and -plus indices in the returned result.
    candLons = np.arange(iLon0+1,iLon0+nLonIndsLength[iLat]+1)%nLon
    d = helpers.calc_distSphere_multiple(r, lat0, lon0, latCell[iLat], lonCell[candLons])
    closeLons = candLons[d<distRegion]
    lonInds = np.concatenate((closeLons,iLon0+iLon0-closeLons)).tolist();
    lonInds.append(iLon0)
    
    inRegion_lon.extend(lonInds)
    inRegion_lat.extend([iLat]*len(lonInds))
  
  #add in 1 value at pole if w/in region
  if (indNPole==0):
    inRegion_lon.append(iLon0); inRegion_lat.append(indNPole)
  if (indSPole==nLat-1):
    inRegion_lon.append(iLon0); inRegion_lat.append(indSPole)
    
  inRegion_lon = np.array(inRegion_lon, dtype=int)%nLon
  inRegion_lat = np.array(inRegion_lat, dtype=int)
  return (inRegion_lat, inRegion_lon)  
  
class Mesh(object):
  def __init__(self,lat,lon, r, rDisk):
    self.r = r
    self.lat = lat
    self.lon = lon
    nLat = len(lat); nLon = len(lon)
    self.nLat = nLat
    self.nLon = nLon
    self.nCells = nLat*nLon
    self.areaCell = calc_areaLatStrips(lat, r)/nLon
    self.inRegion = np.ones((nLat,nLon),dtype=int)
    self.inDiskLat = [None]*nLat
    self.inDiskLon = [None]*nLat
    self.rDisk = rDisk
    self.info = 'latLon'
    
  def fill_latCellArea(self):
    areaLat = calc_areaLatStrips(self.lat, self.r)
    self.areaCell = areaLat/self.nLon
  
  def fill_inDisk(self):
    dRegion = self.rDisk
    r = self.r; lat = self.lat; lon = self.lon;
    nLat = self.nLat; nLon = self.nLon
    nLatIndsLength = calc_latIndicesWithinLength(nLat, r, dRegion)
    nLonIndsLength = calc_lonIndicesWithinLength(lat, nLon, r, dRegion)
    
    for iLat in xrange(nLat):
      inDiskLat, inDiskLon_ref = gatherInds_region_latBox_1AtPole(iLat, iLonRef, nLat, nLon, lat, lon,
                                                  nLatIndsLength, nLonIndsLength, r, dRegion)
      #
      self.inDiskLat[iLat] = inDiskLat
      self.inDiskLon[iLat] = inDiskLon_ref
  
  def find_closestCell2Pt_ll(self, latPt, lonPt):
    #closest pt is (closest lat, closest lon)
    iLat = np.argmin(np.abs(self.lat-latPt)); 
    iLon = np.argmin(np.abs(self.lon-lonPt));
    
    return (iLat, iLon)
  
  def get_closestCell2Pt(self, latPt, lonPt):
    iLat, iLon = self.find_closestCell2Pt_ll(latPt, lonPt)
    #print 'delta lat/lon', latPt-self.lat[iLat], lonPt-self.lon[iLon]
    return helpers.index_2dTo1d(iLat, iLon, self.nLon)
  
  def fill_inRegion(self, latThresh):
    self.inRegion[self.lat<latThresh,:] = 0
  
  def get_inRegion1d(self):
    return helpers.flatten_2dTo1d(self.inRegion, self.nLat, self.nLon)>0
  
  def isIndsInRegion(self, inds):
    #creating a view should be cheap, but then we operate on it...
    inRegion = helpers.flatten_2dTo1d(self.inRegion, self.nLat, self.nLon)
    return inRegion[inds]>0
    
  def get_latLon_inds(self, inds):
    iLats, iLons = helpers.index_1dTo2d(inds, self.nLon)
    return (self.lat[iLats], self.lon[iLons])
    
  def get_area_inds(self, inds):
    iLats, iLons = helpers.index_1dTo2d(inds, self.nLon)
    return self.areaCell[iLats]
    
class Cell(object):
  def __init__(self,mesh,ind):
    iLat, iLon = helpers.index_1dTo2d(ind, mesh.nLon)
    self.iLat = iLat
    self.iLon = iLon
    self.mesh = mesh
    self.ind = ind
  
  def __iter__(self):
    return self

  def next(self): # Python 3: def __next__(self)
    if self.ind >= self.mesh.nCells-1:
      raise StopIteration
    else:
      self.ind = self.ind + 1
      self.iLat,self.iLon = helpers.index_1dTo2d(self.ind, self.mesh.nLon)
      return self
  
  def copy(self):
    return Cell(self.mesh, self.ind)
      
  def isInRegion(self):
    return self.mesh.inRegion[self.iLat,self.iLon]>0
      
  def nbrInds_ll(self):
    #return list of 8-conn nbr indices: [(latNbr1, lonNbr1), (latNbr2, lonNbr2),...]
    #always have east, west neighbors. not north/south at respective pole.
    #the entire equatorward latitude circle is the neighbor of a pole.
    
    iLat = self.iLat; iLon = self.iLon
    nLat = self.mesh.nLat; nLon = self.mesh.nLon
    
    iWest = (iLon-1)%nLon # -1%4=3 so don't worry about negatives
    #from docs, "The modulo operator always yields a result with the same sign as its second operand (or zero)"
    iEast = (iLon+1)%nLon
    iSouth = iLat+1
    iNorth = iLat-1
    
    haveSouth = iSouth<nLat
    haveNorth = iNorth>-1
    
    nbrLats = [iLat, iLat]; nbrLons = [iWest, iEast]
    if (haveSouth):
      if (haveNorth):
        nbrLats.extend([iSouth, iSouth, iSouth])
        nbrLons.extend([iWest, iLon, iEast])
      else:
        #north pole
        nbrLats.extend([iSouth]*nLon)
        nbrLons.extend(range(nLon))
        
    if (haveNorth):
      if (haveSouth):
        nbrLats.extend([iNorth, iNorth, iNorth])
        nbrLons.extend([iWest, iLon, iEast])
      else:
        #south pole
        nbrLats.extend([iNorth]*nLon)
        nbrLons.extend(range(nLon))
      
    return (nbrLats, nbrLons)

  def get_nbrInds(self):
    nbrInds_lat, nbrInds_lon = self.nbrInds_ll()
    nbrInds_lat = np.array(nbrInds_lat,dtype=int); nbrInds_lon = np.array(nbrInds_lon,dtype=int)
    return helpers.index_2dTo1d(nbrInds_lat,nbrInds_lon,self.mesh.nLon)
    
  def diskInds(self):
    iLat = self.iLat; iLon = self.iLon; nLon = self.mesh.nLon
    diffLonInd = iLon-iLonRef
    inDiskLon = (self.mesh.inDiskLon[iLat]+diffLonInd)%nLon
    
    return (self.mesh.inDiskLat[iLat], inDiskLon)
  
  def get_regionInds(self):
    iLats,iLons = self.diskInds()
    return helpers.index_2dTo1d(iLats,iLons,self.mesh.nLon)
  
  def get_areaCell(self):
    return self.mesh.areaCell[self.iLat]

