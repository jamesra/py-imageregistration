'''
Created on Mar 29, 2013

@author: u0490822
'''

from nornir_imageregistration.files.mosaicfile import MosaicFile
import transforms.factory as tfactory
import transforms.utils as tutils
import assemble_tiles as at
import numpy as np
import os
import nornir_pools as pools
import nornir_imageregistration.arrange_mosaic as arrange


def LayoutToMosaic(layout):

    mosaic = Mosaic()

    for ID, Transform in layout.TileToTransform.items():
        tile = layout.Tiles[ID]
        mosaic.ImageToTransform[tile.ImagePath] = Transform

    mosaic.TranslateToZeroOrigin()

    return mosaic

class Mosaic(object):
    '''
    Maps images into a mosaic with a transform
    '''

    @classmethod
    def LoadFromMosaicFile(cls, mosaicfile):
        '''Return a dictionary mapping tiles to transform objects'''

        if isinstance(mosaicfile, str):
            mosaicfile = MosaicFile.Load(mosaicfile)
            if mosaicfile is None:
                raise Exception("Expected valid mosaic file path")
        elif not isinstance(mosaicfile, MosaicFile):
            raise Exception("Expected valid mosaic file path or object")

        ImageToTransform = {}
        for (k, v) in mosaicfile.ImageToTransformString.items():
            ImageToTransform[k] = tfactory.LoadTransform(v, pixelSpacing=1.0)

        return Mosaic(ImageToTransform)

    def ToMosaicFile(self):
        mfile = MosaicFile()

        for k, v in self.ImageToTransform.items():
            mfile.ImageToTransformString[k] = tfactory.TransformToIRToolsString(v)

        return mfile

    def SaveToMosaicFile(self, mosaicfile):

        mfile = self.ToMosaicFile()
        mfile.Save(mosaicfile)

    @classmethod
    def TranslateMosaicFileToZeroOrigin(cls, path):
        mosaicObj = Mosaic.LoadFromMosaicFile(path)
        mosaicObj.TranslateToZeroOrigin()
        mosaicObj.SaveToMosaicFile(path)

    @property
    def ImageToTransform(self):
        return self._ImageToTransform

    def __init__(self, ImageToTransform=None):
        '''
        Constructor
        '''

        if ImageToTransform is None:
            ImageToTransform = dict()

        self._ImageToTransform = ImageToTransform
        self.ImageScale = 1


    @property
    def FixedBoundingBox(self):
        '''Calculate the bounding box of the warped position for a set of transforms
           (minX, minY, maxX, maxY)'''

        return tutils.FixedBoundingBox(self.ImageToTransform.values())

    @property
    def MappedBoundingBox(self):
        '''Calculate the bounding box of the warped position for a set of transforms
           (minX, minY, maxX, maxY)'''

        return tutils.MappedBoundingBox(self.ImageToTransform.values())

    @property
    def FixedBoundingBoxWidth(self):
        return tutils.FixedBoundingBoxWidth(self.ImageToTransform.values())

    @property
    def FixedBoundingBoxHeight(self):
        return tutils.FixedBoundingBoxHeight(self.ImageToTransform.values())

    @property
    def MappedBoundingBoxWidth(self):
        return tutils.MappedBoundingBoxWidth(self.ImageToTransform.values())

    @property
    def MappedBoundingBoxHeight(self):
        return tutils.MappedBoundingBoxHeight(self.ImageToTransform.values())


    def TileFullPaths(self, tilesDir):
        '''Return a list of full paths to the tile for each transform'''
        return [os.path.join(tilesDir, x) for x in self.ImageToTransform.keys()]

    def TranslateToZeroOrigin(self):
        '''Ensure that the transforms in the mosaic do not map to negative coordinates'''

        tutils.TranslateToZeroOrigin(self.ImageToTransform.values())

    def TranslateFixed(self, offset):
        '''Translate the fixed space coordinates of all images in the mosaic'''
        for t in self.ImageToTransform.values():
            t.TranslateFixed(offset)

    @classmethod
    def TranslateLayout(cls, Images, Positions, ImageScale=1):
        '''Creates a layout for the provided images at the provided
           It is assumed that Positions are not scaled, but the image size may be scaled'''

        raise Exception("Not implemented")

    def CreateTilesPathList(self, tilesPath):
        if tilesPath is None:
            return self.ImageToTransform.keys()
        else:
            return [os.path.join(tilesPath, x) for x in self.ImageToTransform.keys()]



    def ArrangeTilesWithTranslate(self, tilesPath, usecluster=False):

        tilesPathList = self.CreateTilesPathList(tilesPath)

        layout = arrange.TranslateTiles(self.ImageToTransform.values(), tilesPathList)

        return LayoutToMosaic(layout)


    def AssembleTiles(self, tilesPath, usecluster=False):
        '''Create a single large mosaic'''

        # Ensure that all transforms map to positive values
        # self.TranslateToZeroOrigin()

        # Allocate a buffer for the tiles
        tilesPathList = self.CreateTilesPathList(tilesPath)

        if usecluster:
            cpool = pools.GetGlobalClusterPool()
            return at.TilesToImageParallel(self.ImageToTransform.values(), tilesPathList, pool=cpool)
        else:
            # return at.TilesToImageParallel(self.ImageToTransform.values(), tilesPathList)
            return at.TilesToImage(self.ImageToTransform.values(), tilesPathList)



