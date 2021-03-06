'''
Created on Sep 14, 2018

@author: u0490822
'''

import numpy as np
from nornir_imageregistration.spatial import Rectangle

#Collection of masks we have already calculated
__known_overlap_masks = {}



def __CreateMaskLookupIndex(FixedImageShape, WarpedImageShape, CorrelationImageShape, MinOverlap, MaxOverlap):
    '''
    Create an index into a dictionary for a overlap mask
    '''
    dimensions = np.concatenate((FixedImageShape, WarpedImageShape, CorrelationImageShape))
    full_index = list(dimensions) + [MinOverlap, MaxOverlap]
    return tuple(full_index) 


def GetOverlapMask(FixedImageSize, MovingImageSize, CorrelationImageSize, MinOverlap=0.0, MaxOverlap=1.0):
    '''Defines a mask that determines which peaks should be considered
    :param array FixedImageSize: Shape of fixed image, before padding
    :param array MovingImageSize: Shape of moving image, before padding
    :param array CorrelationImageSize: Shape of correlation image, which will be equal to size of largest padded image dimensions
    :param float MinOverlap: The minimum amount of overlap between the fixed and moving images, area based
    :param float MaxOverlap: The maximum amount of overlap between the fixed and moving images, area based
    :return: An mxn image mask, with 1 indicating allowed peak locations
    '''
    
    global __known_overlap_masks
    
    if MinOverlap == 0.0 and MaxOverlap == 1.0: # and np.array_equal(FixedImageSize, MovingImageSize) and np.array_equal(FixedImageSize, CorrelationImageSize):
        return None
    
    MaskIndex = __CreateMaskLookupIndex(FixedImageSize, MovingImageSize, CorrelationImageSize, MinOverlap, MaxOverlap)

    if MaskIndex in __known_overlap_masks:
        return __known_overlap_masks[MaskIndex]

    Mask = __CreateOverlapMaskBruteForce(FixedImageSize, MovingImageSize, CorrelationImageSize, MinOverlap, MaxOverlap)
    __known_overlap_masks[MaskIndex] = Mask

    return Mask


def __CreateFullMaskFromQuadrant(Mask, isOddDimension):
    '''
    Given an image, replicates the image symetrically around both the X and Y axis to create a full mask
    :param array isOddDimension: True if the axis has an odd dimension in the input.
    '''
    MaskUpRight = Mask
    
    if isOddDimension[1]:
        MaskUpLeft = np.fliplr(Mask[:,1:])
    else:
        MaskUpLeft = np.fliplr(Mask)
        
    UpperMask = np.hstack((MaskUpLeft, MaskUpRight))
    
    if isOddDimension[0]:
        LowerMask = np.flipud(UpperMask[1:,:])
        #MaskDownLeft = np.flipud(MaskUpLeft[1:,:])
        #MaskDownRight = np.fliplr(MaskUpRight[1:,:])
    else:
        LowerMask = np.flipud(UpperMask)
        #MaskDownLeft = np.flipud(MaskUpLeft)
        #MaskDownRight = np.fliplr(MaskUpRight)

#    LowerMask = np.hstack((MaskDownLeft, MaskDownRight))

    Mask = np.vstack((LowerMask, UpperMask))

    return Mask


def __CreateOverlapMaskBruteForce(FixedImageSize, MovingImageSize, CorrelationImageSize, MinOverlap=0.0, MaxOverlap=1.0):
    '''Defines a mask that determines which peaks should be considered
    :param array FixedImageSize: Shape of fixed image, before padding
    :param array MovingImageSize: Shape of moving image, before padding
    :param array CorrelationImageSize: Shape of correlation image, which will be equal to size of largest padded image dimensions
    :param float MinOverlap: The minimum amount of overlap between the fixed and moving images, area based
    :param float MaxOverlap: The maximum amount of overlap between the fixed and moving images, area based
    :return: An mxn image mask, with 1 indicating allowed peak locations
    '''
    if MinOverlap is None:
        MinOverlap = 0.0
        
    if MaxOverlap is None:
        MaxOverlap = 1.0
        
    if MinOverlap >= MaxOverlap:
        raise ValueError("Minimum overlap must be less than maximum overlap")
 
    QuadrantSize = np.asarray((CorrelationImageSize[0] / 2.0, CorrelationImageSize[1] / 2.0), dtype=np.float64)
    isOddDimension = np.mod(QuadrantSize, 1) > 0
    QuadrantSize = np.ceil(QuadrantSize).astype(np.int32)
    Mask = np.zeros(QuadrantSize, dtype=np.bool)

    Mask = _PopulateMaskQuadrantBruteForceOptimized(Mask, FixedImageSize, MovingImageSize, MinOverlap, MaxOverlap)
#     for ix in range(0, HalfCorrelationSize[1]):
#         for iy in range(0, HalfCorrelationSize[0]):
#             WarpedImageRect = Rectangle.CreateFromCenterPointAndArea((iy, ix), MovingImageSize)
# 
#             overlap = Rectangle.overlap(WarpedImageRect, FixedImageRect)
#             Mask[iy, ix] = overlap >= MinOverlap and overlap <= MaxOverlap
    return __CreateFullMaskFromQuadrant(Mask, isOddDimension)


def _PopulateMaskQuadrantBruteForce(Mask, FixedImageSize, MovingImageSize, MinOverlap=0.0, MaxOverlap=1.0):

    FixedImageRect = Rectangle.CreateFromCenterPointAndArea((0,0), FixedImageSize)
    WarpedImageRect = None
    
    #We cannot overlap more than the minimum of each dimension
    maxPossibleOverlap = np.min(np.vstack((FixedImageSize, MovingImageSize)),1)
    maxPossibleOverlapArea = np.prod(maxPossibleOverlap)
    
    Overlap = np.zeros(Mask.shape,dtype=np.float32)

    for ix in range(0, Mask.shape[1]):
        for iy in range(0, Mask.shape[0]):
            WarpedImageRect = Rectangle.CreateFromCenterPointAndArea((iy, ix), MovingImageSize)

            overlap_rect = Rectangle.overlap_rect(WarpedImageRect, FixedImageRect)
            overlap = 0
            if overlap_rect is not None:
                overlap = overlap_rect.Area / maxPossibleOverlapArea
                
            Overlap[iy, ix] = overlap
            
    Mask = np.logical_and(Overlap >= MinOverlap, Overlap <= MaxOverlap)
    return Mask

def _PopulateMaskQuadrantBruteForceOptimized(Mask, FixedImageSize, MovingImageSize, MinOverlap=0.0, MaxOverlap=1.0):

    FixedImageRect = Rectangle.CreateFromCenterPointAndArea((0,0), FixedImageSize)
    WarpedImageRect = None
    
    #We cannot overlap more than the minimum of each dimension
    maxPossibleOverlap = np.min(np.vstack((FixedImageSize, MovingImageSize)),0)
    maxPossibleOverlapArea = np.prod(maxPossibleOverlap)
             
    for ix in range(0, Mask.shape[1]):
        for iy in range(0, Mask.shape[0]):
            WarpedImageRect = Rectangle.CreateFromCenterPointAndArea((iy, ix), MovingImageSize)

            overlap_rect = Rectangle.overlap_rect(WarpedImageRect, FixedImageRect)
            overlap = 0
            if overlap_rect is not None:
                overlap = overlap_rect.Area / maxPossibleOverlapArea
            
            #Overlap[iy, ix] = overlap #Rectangle.overlap(WarpedImageRect, FixedImageRect)
            Mask[iy, ix] = overlap >= MinOverlap and overlap <= MaxOverlap

            if overlap < MinOverlap:
                Mask[iy:Mask.shape[0], ix] = False
                break

    #Mask = np.logical_and(Overlap >= MinOverlap, Overlap <= MaxOverlap)
    return Mask
    