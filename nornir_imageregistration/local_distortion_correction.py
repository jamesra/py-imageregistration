'''
Created on Apr 7, 2015

@author: u0490822

This module performs local distortions of images to refine alignments of mosaics and sections
'''

import nornir_imageregistration

import nornir_imageregistration.core as core
import nornir_imageregistration.spatial as spatial
import nornir_imageregistration.tile as tile
import nornir_imageregistration.tileset as tileset
import nornir_imageregistration.stos_brute
import nornir_imageregistration.transforms
from nornir_imageregistration.transforms.triangulation import Triangulation
import nornir_imageregistration.grid_subdivision
import nornir_pools
import nornir_shared.histogram
import nornir_shared.plot
import numpy as np
from alignment_record import AlignmentRecord
from _ctypes import alignment
from numpy import histogram


class DistortionCorrection:
    
    def __init__(self):
        self.PointsForTile = {}

          
def CreateDisplacementGridForTile(tile):
    
    grid_dim = core.TileGridShape(overlapping_rect_A.Size, subregion_shape)
    
    
def RefineMosaic(transforms, imagepaths, imageScale=None, subregion_shape=None):
    '''
    Locate overlapping regions between tiles in a mosaic and align multiple small subregions within.  This generates a set of control points. 
    
    More than one tile may overlap, for example corners.  To solve this the set of control points is merged into a KD tree.  Points closer than a set distance (less than subregion size) are averaged to create a single offset. 
    
    Using the remaining points a mesh transform is generated for the tile. 
    '''
    
    if imageScale is None:
        imageScale = 1.0
        
    if subregion_shape is None:
        subregion_shape = np.array([128, 128])
        
    downsample = 1.0 / imageScale
    
    tiles = nornir_imageregistration.tile.CreateTiles(transforms, imagepaths)
    list_tiles = list(tiles.values())
    pool = nornir_pools.GetGlobalMultithreadingPool()
    tasks = list()
    
    if imageScale is None:
        imageScale = tileset.MostCommonScalar(transforms, imagepaths)
    
    layout = nornir_imageregistration.layout.Layout()
    for t in list_tiles:
        layout.CreateNode(t.ID, t.ControlBoundingBox.Center)
             
    for A, B in tile.IterateOverlappingTiles(list_tiles, minOverlap=0.03):
        # OK... add some small neighborhoods and register those...
        (downsampled_overlapping_rect_A, downsampled_overlapping_rect_B, OffsetAdjustment) = nornir_imageregistration.tile.Tile.Calculate_Overlapping_Regions(A, B, imageScale)
#          
        task = pool.add_task("Align %d -> %d" % (A.ID, B.ID), __RefineTileAlignmentRemote, A, B, downsampled_overlapping_rect_A, downsampled_overlapping_rect_B, OffsetAdjustment, imageScale, subregion_shape)
        task.A = A
        task.B = B
        task.OffsetAdjustment = OffsetAdjustment
        tasks.append(task)
#          
#         (point_pairs, net_offset) = __RefineTileAlignmentRemote(A, B, downsampled_overlapping_rect_A, downsampled_overlapping_rect_B, OffsetAdjustment, imageScale)
#         offset = net_offset[0:2] + OffsetAdjustment
#         weight = net_offset[2]
#           
#         print("%d -> %d : %s" % (A.ID, B.ID, str(net_offset)))
#           
#         layout.SetOffset(A.ID, B.ID, offset, weight)
         
        # print(str(net_offset))      

    for t in tasks:
        try:
            (point_pairs, net_offset) = t.wait_return()
        except Exception as e:
            print("Could not register %d -> %d" % (t.A.ID, t.B.ID))
            print("%s" % str(e))
            continue 
        
        SplitDisplacements(t.A, t.B, point_pairs)
        # offset = net_offset[0:2] + (t.OffsetAdjustment * downsample)
        # weight = net_offset[2]
        # layout.SetOffset(t.A.ID, t.B.ID, offset, weight) 
        
        # Figure out what offset we found vs. what offset we expected
        # PredictedOffset = t.B.ControlBoundingBox.Center - t.A.ControlBoundingBox.Center
        
        # diff = offset - PredictedOffset
        # distance = np.sqrt(np.sum(diff ** 2))
        
        # print("%d -> %d = %g" % (t.A.ID, t.B.ID, distance))
        
    pool.wait_completion()
    
    return (layout, tiles)


def __RefineTileAlignmentRemote(A, B, overlapping_rect_A, overlapping_rect_B, OffsetAdjustment, imageScale, subregion_shape=None):
    
    if subregion_shape is None:
        subregion_shape = np.array([128, 128])
        
    downsample = 1.0 / imageScale
        
    grid_dim = core.TileGridShape(overlapping_rect_A.Size, subregion_shape)
    
    # overlapping_rect_A = spatial.Rectangle.change_area(overlapping_rect_A, grid_dim * subregion_shape)
    # overlapping_rect_B = spatial.Rectangle.change_area(overlapping_rect_B, grid_dim * subregion_shape)
        
    overlapping_rect = spatial.Rectangle.overlap_rect(A.ControlBoundingBox, B.ControlBoundingBox)
    overlapping_rect = spatial.Rectangle.change_area(overlapping_rect, grid_dim * subregion_shape * downsample)
        
    ATransformedImageData = nornir_imageregistration.assemble_tiles.TransformTile(transform=A.Transform, imagefullpath=A.ImagePath, distanceImage=None, requiredScale=imageScale, FixedRegion=overlapping_rect.ToArray())
    BTransformedImageData = nornir_imageregistration.assemble_tiles.TransformTile(transform=B.Transform, imagefullpath=B.ImagePath, distanceImage=None, requiredScale=imageScale, FixedRegion=overlapping_rect.ToArray())
      
    # I tried a 1.0 overlap.  It works better for light microscopy where the reported stage position is more precise
    # For TEM the stage position can be less reliable and the 1.5 scalar produces better results
    # OverlappingRegionA = __get_overlapping_image(A, overlapping_rect_A,excess_scalar=1.0)
    # OverlappingRegionB = __get_overlapping_image(B, overlapping_rect_B,excess_scalar=1.0)
    A_image = core.RandomNoiseMask(ATransformedImageData.image, ATransformedImageData.centerDistanceImage < np.finfo(ATransformedImageData.centerDistanceImage.dtype).max, Copy=True)
    B_image = core.RandomNoiseMask(BTransformedImageData.image, BTransformedImageData.centerDistanceImage < np.finfo(BTransformedImageData.centerDistanceImage.dtype).max, Copy=True)
    
    # OK, create tiles from the overlapping regions
    # A_image = core.ReplaceImageExtramaWithNoise(ATransformedImageData.image)
    # B_image = core.ReplaceImageExtramaWithNoise(BTransformedImageData.image)
    # core.ShowGrayscale([A_image,B_image])
    A_tiles = core.ImageToTiles(A_image, subregion_shape, cval='random')
    B_tiles = core.ImageToTiles(B_image, subregion_shape, cval='random')
    
    # grid_dim = core.TileGridShape(ATransformedImageData.image.shape, subregion_shape)
    
    refine_dtype = np.dtype([('SourceY', 'f4'),
                           ('SourceX', 'f4'),
                           ('TargetY', 'f4'),
                           ('TargetX', 'f4'),
                           ('Weight', 'f4'),
                           ('Angle', 'f4')])
    
    point_pairs = np.empty(grid_dim, dtype=refine_dtype)
    
    net_displacement = np.empty((grid_dim.prod(), 3), dtype=np.float32)  # Amount the refine points are moved from the defaultf
    
    cell_center_offset = subregion_shape / 2.0
    
    for iRow in range(0, grid_dim[0]):
        for iCol in range(0, grid_dim[1]): 
            subregion_offset = (np.array([iRow, iCol]) * subregion_shape) + cell_center_offset  # Position subregion coordinate space
            source_tile_offset = subregion_offset + overlapping_rect_A.BottomLeft  # Position tile image coordinate space
            global_offset = OffsetAdjustment + subregion_offset  # Position subregion in tile's mosaic space
            
            if not (iRow, iCol) in A_tiles or not (iRow, iCol) in B_tiles:
                net_displacement[(iRow * grid_dim[1]) + iCol, :] = np.array([0, 0, 0])
                point_pairs[iRow, iCol] = np.array((source_tile_offset[0], source_tile_offset[1], 0 + global_offset[0], 0 + global_offset[1], 0, 0), dtype=refine_dtype)
                continue 
            
            try:
                record = core.FindOffset(A_tiles[iRow, iCol], B_tiles[iRow, iCol], FFT_Required=True)
            except:
                net_displacement[(iRow * grid_dim[1]) + iCol, :] = np.array([0, 0, 0])
                point_pairs[iRow, iCol] = np.array((source_tile_offset[0], source_tile_offset[1], 0 + global_offset[0], 0 + global_offset[1], 0, 0), dtype=refine_dtype)
                continue
            
            adjusted_record = nornir_imageregistration.AlignmentRecord(np.array(record.peak) * downsample, record.weight)
            
            # print(str(record))
            
            if np.any(np.isnan(record.peak)):
                net_displacement[(iRow * grid_dim[1]) + iCol, :] = np.array([0, 0, 0])
                point_pairs[iRow, iCol] = np.array((source_tile_offset[0], source_tile_offset[1], 0 + global_offset[0], 0 + global_offset[1], 0, record.angle), dtype=refine_dtype)
            else:
                net_displacement[(iRow * grid_dim[1]) + iCol, :] = np.array([adjusted_record.peak[0], adjusted_record.peak[1], record.weight])
                point_pairs[iRow, iCol] = np.array((source_tile_offset[0], source_tile_offset[1], adjusted_record.peak[0] + global_offset[0], adjusted_record.peak[1] + global_offset[1], record.weight, record.angle), dtype=refine_dtype)
            
    # TODO: return two sets of point pairs, one for each tile, with the offsets divided by two so both tiles are warping to improve the fit equally?
    # TODO: Try a number of angles
    # TODO: The original refine-grid assembled the image before trying to improve the fit.  Is this important or an artifact of the implementation?
    weighted_net_offset = np.copy(net_displacement)
    weighted_net_offset[:, 2] /= np.sum(net_displacement[:, 2])
    weighted_net_offset[:, 0] *= weighted_net_offset[:, 2]
    weighted_net_offset[:, 1] *= weighted_net_offset[:, 2]
    
    net_offset = np.sum(weighted_net_offset[:, 0:2], axis=0)
    
    meaningful_weights = weighted_net_offset[weighted_net_offset[:, 2] > 0, 2]
    weight = 0
    if meaningful_weights.shape[0] > 0:
        weight = np.median(meaningful_weights)
    
    net_offset = np.hstack((np.around(net_offset, 3), weight))
     
    # net_offset = np.median(net_displacement,axis=0) 
    
    return (point_pairs, net_offset)


def SplitDisplacements(A, B, point_pairs):
    '''
    :param tile A: Tile A, point_pairs are registered relative to this tile
    :param tile A: Tile B, the tile that point pairs register A onto
    :param ndarray point_pairs: A set of point pairs from a grid refinement
    '''
    
    raise NotImplementedError()



    

def RefineTwoImages(Transform, target_image, source_image, target_mask=None, 
                    source_mask=None, cell_size=(256, 256), grid_spacing=(256, 256),
                    finalized=None):
    '''
    :param transform transform: Transform
    :param ndarray target_image: Fixed image
    :param ndarray source_image: Warped image
    :param ndarray target_mask: Fixed image mask, can be None
    :param ndarray source_mask: Warped image mask, can be None
    :param dict finalized: A dictionary of points, indexed by FixedPosition, that are finalized and do not need to be checked
    :param tuple cell_size: (width, height) amount of image to use for registration 
    :param tuple grid_spacing: (width, height) of separation between points on the grid
    
    '''
    
    if isinstance(Transform, str):
        Transform = nornir_imageregistration.factory.LoadTransform(Transform, 1)
         
    grid_spacing = np.asarray(grid_spacing, np.int32)
    cell_size = np.asarray(cell_size, np.int32)
        
    target_image = core.ImageParamToImageArray(target_image)
    source_image = core.ImageParamToImageArray(source_image)
    
    if target_mask is not None:
        target_mask = core.ImageParamToImageArray(target_mask).astype(np.bool)
        target_image = nornir_imageregistration.core.RandomNoiseMask(target_image, target_mask)
        
    if source_mask is not None:
        source_mask = core.ImageParamToImageArray(source_mask).astype(np.bool)
        source_image = nornir_imageregistration.core.RandomNoiseMask(source_image, source_mask)
    
#     shared_fixed_image  = core.npArrayToReadOnlySharedArray(target_image)
#     shared_fixed_image.mode = 'r'
#     shared_warped_image = core.npArrayToReadOnlySharedArray(source_image)
#     shared_warped_image.mode = 'r'
    
    # Mark a grid along the fixed image, then find the points on the warped image
    
    #grid_data = nornir_imageregistration.grid_subdivision.CenteredGridRefinementCells(target_image.shape, cell_size)
    grid_data = nornir_imageregistration.grid_subdivision.ITKGridDivision(target_image.shape, cell_size=cell_size)
    
    #grid_dims = core.TileGridShape(target_image.shape, grid_spacing)
    
    AnglesToSearch = [0]
    #AnglesToSearch = np.linspace(-7.5, 7.5, 11)
    
    # Create the grid coordinates
#    coords = [np.asarray((iRow, iCol), dtype=np.int32) for iRow in range(grid_data.grid_dims[0]) for iCol in range(grid_data.grid_dims[1])]
#    coords = np.vstack(coords)
    
    # Create 
#    TargetPoints = coords * grid_spacing  # [np.asarray((iCol * grid_spacing[0], iRow * grid_spacing[1]), dtype=np.int32) for (iRow, iCol) in coords]
    
    #Grid dimensions round up, so if we are larger than image find out by how much and adjust the points so they are centered on the image
#    overage = ((grid_dims * grid_spacing) - target_image.shape) / 2.0
#    TargetPoints = np.round(TargetPoints - overage).astype(np.int64)
    
    #TODO, ensure fixedPoints are within the bounds of target_image
    grid_data.FilterOutofBoundsSourcePoints(source_image.shape)
    grid_data.RemoveCellsUsingSourceImageMask(source_mask,0.45)
    grid_data.PopulateTargetPoints(Transform)
    grid_data.RemoveCellsUsingTargetImageMask(target_mask,0.45)
     #grid_data.ApplyWarpedImageMask(source_mask)
#     valid_inbounds = np.logical_and(np.all(FixedPoi4nts >= np.asarray((0, 0)), 1), np.all(TargetPoints < target_mask.shape, 1))
#     TargetPoints = TargetPoints[valid_inbounds, :]
#     coords = coords[valid_inbounds, :]
#     
    if finalized is not None:
        found = [tuple(grid_data.SourcePoints[i,:]) not in finalized for i in range(grid_data.coords.shape[0])]
        valid = np.asarray(found, np.bool)
        grid_data.RemoveMaskedPoints(valid)
        
        
#         TargetPoints = TargetPoints[valid, :]
#         coords = coords[valid, :]
#     
#     # Filter Fixed Points falling outside the mask
#     if target_mask is not None:
#         valid = nornir_imageregistration.index_with_array(target_mask, TargetPoints)
#         TargetPoints = TargetPoints[valid, :]
#         coords = coords[valid, :]
#         
#     SourcePoints = Transform.InverseTransform(TargetPoints).astype(np.int32)
#     if source_mask is not None:
#         valid = np.logical_and(np.all(SourcePoints >= np.asarray((0, 0)), 1), np.all(SourcePoints < source_mask.shape, 1))
#         SourcePoints = SourcePoints[valid, :]
#         TargetPoints = TargetPoints[valid, :]
#         coords = coords[valid, :]
#         
#         valid = nornir_imageregistration.index_with_array(source_mask, SourcePoints)
#         SourcePoints = SourcePoints[valid, :]
#         TargetPoints = TargetPoints[valid, :]
#         coords = coords[valid, :]
    
    pool = nornir_pools.GetGlobalMultithreadingPool()
    tasks = list()
    alignment_records = list()
    
    for (i, coord) in enumerate(grid_data.coords):
        
        AlignTask = StartAttemptAlignPoint(pool,
                                           "Align %d,%d" % (coord[0], coord[1]),
                                           Transform,
                                           target_image,
                                           source_image,
                                           grid_data.TargetPoints[i, :],
                                           cell_size,
                                           anglesToSearch=AnglesToSearch)
        
#         AlignTask = pool.add_task("Align %d,%d" % (coord[0], coord[1]),
#                                   AttemptAlignPoint,
#                                   Transform,
#                                   shared_fixed_image,
#                                   shared_warped_image,
#                                   TargetPoints[i,:],
#                                   cell_size,
#                                   anglesToSearch=AnglesToSearch)
        
        AlignTask.ID = i
        AlignTask.coord = coord
        tasks.append(AlignTask)
        
    #             arecord.iRow = iRow
#             arecord.iCol = iCol
#             arecord.TargetPoint = TargetPoint
#             arecord.WarpedPoint = WarpedPoint
#             arecord.AdjustedWarpedPoint = WarpedPoint + arecord.peak
#             
#             alignment_records.append(arecord)
    
    for t in tasks:
        arecord = t.wait_return()
        
        erec = nornir_imageregistration.alignment_record.EnhancedAlignmentRecord(ID=t.coord,
                                                                                 TargetPoint=grid_data.TargetPoints[t.ID],
                                                                                 SourcePoint=grid_data.SourcePoints[t.ID],
                                                                                 peak=arecord.peak,
                                                                                 weight=arecord.weight,
                                                                                 angle=arecord.angle,
                                                                                 flipped_ud=arecord.flippedud)
        
        erec.TargetROI = t.TargetROI
        erec.SourceROI = t.SourceROI
        #erec.CalculatedWarpedPoint = Transform.InverseTransform(erec.AdjustedTargetPoint).reshape(2)
        # arecord.ID = (iRow, iCol)
        # arecord.TargetPoint = t.TargetPoint
        # arecord.WarpedPoint = t.WarpedPoint
        # arecord.AdjustedWarpedPoint = t.WarpedPoint + arecord.peak
         
        alignment_records.append(erec)
#         
#     del shared_warped_image
#     del shared_fixed_image
    
    
    
    return alignment_records
    # Cull the worst of the alignment records
    
    # Build a new transform using our alignment points
    # peaks = np.list(map(lambda a: a.peak, alignment_records))
    # updatedTransform = _PeakListToTransform(alignment_records)
    
    # Re-run the loop
    
    # return updatedTransform

    
def _PeakListToTransform(alignment_records, percentile = None):
    '''
    Converts a set of EnhancedAlignmentRecord peaks from the RefineTwoImages function into a transform
    '''
    
    #TargetPoints = np.asarray(list(map(lambda a: a.TargetPoint, alignment_records)))
    OriginalSourcePoints = np.asarray(list(map(lambda a: a.SourcePoint, alignment_records)))
    AdjustedTargetPoints = np.asarray(list(map(lambda a: a.AdjustedTargetPoint, alignment_records)))
    #AdjustedWarpedPoints = np.asarray(list(map(lambda a: a.AdjustedWarpedPoint, alignment_records)))
    #CalculatedWarpedPoints = np.asarray(list(map(lambda a: a.CalculatedWarpedPoint, alignment_records)))
    weights = np.asarray(list(map(lambda a: a.weight, alignment_records)))
    #WarpedPeaks = AdjustedWarpedPoints - OriginalSourcePoints
    
    cutoff = 0
    if percentile is not None:
        cutoff = np.percentile(weights, percentile)       
    
    valid_indicies = weights >= cutoff
    
    ValidFP = AdjustedTargetPoints[valid_indicies, :]
    ValidWP = OriginalSourcePoints[valid_indicies, :]
    
    assert(np.array_equiv(Triangulation.RemoveDuplicates(ValidFP).shape,
                          ValidFP.shape), "Duplicate fixed points detected")
    assert(np.array_equiv(Triangulation.RemoveDuplicates(ValidWP).shape,
                          ValidWP.shape), "Duplicate warped points detected")
    
    # PointPairs = np.hstack((TargetPoints, SourcePoints))
    PointPairs = np.hstack((ValidFP, ValidWP))
    # PointPairs.append((ControlY, ControlX, mappedY, mappedX))

    T = nornir_imageregistration.transforms.meshwithrbffallback.MeshWithRBFFallback(PointPairs)
    
    return T


def _ConvertTransformToGridTransform(Transform, target_image_shape, source_image_shape, cell_size=None, grid_dims=None, grid_spacing=None):
    '''
    Converts a set of EnhancedAlignmentRecord peaks from the RefineTwoImages function into a transform
    '''
    
    grid_data = nornir_imageregistration.grid_subdivision.ITKGridDivision(target_image_shape, cell_size=cell_size, grid_spacing=grid_spacing, grid_dims=grid_dims)
    grid_data.PopulateTargetPoints(Transform)
    
    PointPairs = np.hstack((grid_data.TargetPoints, grid_data.SourcePoints))
     
    #TODO, create a specific grid transform object that uses numpy's RegularGridInterpolator
    T = nornir_imageregistration.transforms.triangulation.Triangulation(PointPairs)
    T.gridWidth = grid_data.grid_dims[1]
    T.gridHeight = grid_data.grid_dims[0]
    
    return T


# def AlignmentRecordsTo2DArray(alignment_records):
#     
#     def IsFinalFunc(record):
#         record.weight = 
#     
#     #Create a 2D array of 
#     Indicies = np.hstack([np.asarray(a.ID,np.int32) for a in alignment_records])
#     
#     grid_dims = Indicies.max()
#     
#     mask = np.zeros(grid_dims, np.bool)
#     
#     for a in alignment_records:
#         mask[a.ID] = 
#           

def AlignmentRecordsToDict(alignment_records):
    
    lookup = {}
    for a in alignment_records:
        lookup[a.ID] = a
        
    return lookup


def CalculateFinalizedAlignmentPointsMask(alignment_records, old_mask = None, percentile=0.5, min_travel_distance = 1.0):
    
    weights = np.asarray(list(map(lambda a: a.weight, alignment_records)))
    peaks = np.asarray(list(map(lambda a: a.peak, alignment_records)))
    peak_distance = np.square(peaks)
    peak_distance = np.sum(peak_distance, axis=1)
    
    cutoff = np.percentile(weights, percentile)    
    
    valid_weight = weights > cutoff 
    valid_distance = peak_distance <= np.square(min_travel_distance)
    
    finalize_mask = np.logical_and(valid_weight, valid_distance)
    
    return finalize_mask
    
    
def AttemptAlignPoint(transform, fixedImage, warpedImage, controlpoint, alignmentArea, anglesToSearch=None):
    '''Try to use the Composite view to render the two tiles we need for alignment'''
    if anglesToSearch is None:
        anglesToSearch = np.linspace(-7.5, 7.5, 11)
        
    FixedRectangle = nornir_imageregistration.Rectangle.CreateFromPointAndArea(point=[controlpoint[0] - (alignmentArea[0] / 2.0),
                                                                                   controlpoint[1] - (alignmentArea[1] / 2.0)],
                                                                             area=alignmentArea)

    FixedRectangle = nornir_imageregistration.Rectangle.SafeRound(FixedRectangle)
    FixedRectangle = nornir_imageregistration.Rectangle.change_area(FixedRectangle, alignmentArea)
    
    # Pull image subregions 
    warpedImageROI = nornir_imageregistration.assemble.WarpedImageToFixedSpace(transform,
                            fixedImage.shape, warpedImage, botleft=FixedRectangle.BottomLeft, area=FixedRectangle.Size, extrapolate=True)

    fixedImageROI = nornir_imageregistration.core.CropImage(fixedImage.copy(), FixedRectangle.BottomLeft[1], FixedRectangle.BottomLeft[0], int(FixedRectangle.Size[1]), int(FixedRectangle.Size[0]))

    # nornir_imageregistration.core.ShowGrayscale([fixedImageROI, warpedImageROI])

    # pool = Pools.GetGlobalMultithreadingPool()

    # task = pool.add_task("AttemptAlignPoint", core.FindOffset, fixedImageROI, warpedImageROI, MinOverlap = 0.2)
    # apoint = task.wait_return()
    # apoint = core.FindOffset(fixedImageROI, warpedImageROI, MinOverlap=0.2)
    # nornir_imageregistration.ShowGrayscale([fixedImageROI, warpedImageROI], "Fixed <---> Warped")
    
    # core.ShowGrayscale([fixedImageROI, warpedImageROI])
    
    apoint = nornir_imageregistration.stos_brute.SliceToSliceBruteForce(fixedImageROI, warpedImageROI, AngleSearchRange=anglesToSearch, MinOverlap=0.25, SingleThread=True, Cluster=False, TestFlip=False)
 
    # print("Auto-translate result: " + str(apoint))
    return apoint

    
def StartAttemptAlignPoint(pool, taskname, transform, targetImage, sourceImage, controlpoint, alignmentArea, anglesToSearch=None):
    if anglesToSearch is None:
        anglesToSearch = np.linspace(-7.5, 7.5, 11)
        
    FixedRectangle = nornir_imageregistration.Rectangle.CreateFromPointAndArea(point=[controlpoint[0] - (alignmentArea[0] / 2.0),
                                                                                   controlpoint[1] - (alignmentArea[1] / 2.0)],
                                                                             area=alignmentArea)

    FixedRectangle = nornir_imageregistration.Rectangle.SafeRound(FixedRectangle)
    FixedRectangle = nornir_imageregistration.Rectangle.change_area(FixedRectangle, alignmentArea)
    
    # Pull image subregions 
    sourceImageROI = nornir_imageregistration.assemble.WarpedImageToFixedSpace(transform,
                            targetImage.shape, sourceImage, botleft=FixedRectangle.BottomLeft, area=FixedRectangle.Size, extrapolate=True)

    targetImageROI = nornir_imageregistration.CropImage(targetImage, FixedRectangle.BottomLeft[1], FixedRectangle.BottomLeft[0], int(FixedRectangle.Size[1]), int(FixedRectangle.Size[0]))

    # nornir_imageregistration.core.ShowGrayscale([targetImageROI, sourceImageROI])

    # pool = Pools.GetGlobalMultithreadingPool()

    # task = pool.add_task("AttemptAlignPoint", core.FindOffset, targetImageROI, sourceImageROI, MinOverlap = 0.2)
    # apoint = task.wait_return()
    # apoint = core.FindOffset(targetImageROI, sourceImageROI, MinOverlap=0.2)
    # nornir_imageregistration.ShowGrayscale([targetImageROI, sourceImageROI], "Fixed <---> Warped")
    
    # core.ShowGrayscale([targetImageROI, sourceImageROI])
    
    task = pool.add_task(taskname,
                        nornir_imageregistration.stos_brute.SliceToSliceBruteForce,
                        targetImageROI,
                        sourceImageROI,
                        AngleSearchRange=anglesToSearch,
                        MinOverlap=0.25,
                        SingleThread=True,
                        Cluster=False,
                        TestFlip=False)
    
    task.TargetROI = targetImageROI
    task.SourceROI = sourceImageROI
    
    return task
