# Set up workspace

from __future__ import division

import contextlib
import shutil
import os
import os.path

import numpy as np

from osgeo import gdal

from pymclevel import mclevel, nbt, box, level
from pymclevel.materials import alphaMaterials as mat



# Point to some system locations

# Optionally set to your Minecraft save directory, e.g.
# savedir = "/Users/olearym/Library/Application Support/minecraft/saves/"
savedir = "./saves"

# Location of elevation data
bedmapdir = "./rasters/"



# Define the model scaling and output name

mapname = "Test_02"
# For AB map, 500:1 lateral scale worked - some topographic features were recognizable.
# 200:1 worked very well for recognition of topographic features and continuity of river valleys.
# Vertical exaggeration of 5 was okay.
vscale = 0.025   # Vertical scale factor
vshift = 5     # Vertical shift - shifts whole model up or down. Remember model must be [0,264].
step = 2         # Step size (use every "step"th pixel) (LATERAL SCALING)
batch_size = 32  # Save changes every N rows - ideally a multiple of 16



# Define materials

rock = mat.Stone
ice = mat[174]    # Packed ice is new in Minecraft 1.8, so it isn't named in
                  # pymclevel
water = mat.Water
air = mat.Air
glass = mat[95]
glass.grey = mat[95,7]
glowstone = mat.Glowstone
grass = mat.Grass



# Define some funtions

@contextlib.contextmanager
def create_world(name):
    if not os.path.isdir(savedir):
        print "Creating directory", savedir
        os.makedirs(savedir)
    path = os.path.join(savedir, name)
    shutil.rmtree(path, ignore_errors=True)
    world = mclevel.MCInfdevOldLevel(path, create=True)
    tags = [nbt.TAG_Int(0, "MapFeatures"),
            nbt.TAG_String("flat", "generatorName"),
            nbt.TAG_String("0", "generatorOptions")]
    for tag in tags:
        world.root_tag["Data"].add(tag)
    world.GameType = 1 # Creative mode
    yield world
    world.saveInPlace()

def fill_box(world, material, x0, x1, y0, y1, z0, z1):
    tilebox = box.BoundingBox((x0,y0,z0), (x1-x0,y1-y0,z1-z0))
    world.createChunksInBox(tilebox)
    world.fillBlocks(tilebox, material)

def fill_column(world, x, z, *matheights):
    elev = 0
    for material, height in matheights:
        if height > 0:
            fill_box(world, material, x, x + 1, elev, elev + height, z, z + 1)
            elev += height

@contextlib.contextmanager
def batch_changes():
    chunkset = set()
    def deferred(chunk, needsLighting=True):
        chunkset.add(chunk)
    tmp, level.LightedChunk.chunkChanged = level.LightedChunk.chunkChanged, deferred
    yield
    level.LightedChunk.chunkChanged = tmp
    for chunk in chunkset:
        chunk.chunkChanged(True)

def load_tiff(filename, nanvalue=np.nan):
    filepath = os.path.join(bedmapdir, filename)
    dat = gdal.Open(filepath).ReadAsArray()
    dat = dat.astype(float)
    dat[dat == np.nanmin(dat)] = nanvalue #added np.nanmin(dat) to account for nanvalue
    print "%s: min %.1f, max %.1f" % (filename, np.nanmin(dat), np.nanmax(dat))
    return dat



# Assign surfaces. Two layers in this model are defined by three surfaces.

# Top of upper layer
surf = 1 + load_tiff("Alberta DEM 100m 10TM.tif", 0)
# Base of upper layer is also the top of bottom layer
base = load_tiff("Alberta DEM 100m 10TM.tif", 0)
# Base of bottom layer is the model bottom. COuld set to 0 with extent identical to other layers.
bed = 0* load_tiff("Alberta DEM 100m 10TM.tif", 0)



# Test to ensure model is within vertical limits

tomc = lambda x: int(x * vscale + vshift)

assert tomc(np.nanmin(bed)) > 0, \
    "Bed goes below y=0 (decrease vscale or increase vshift)"
assert tomc(np.nanmax(surf)) < 255, \
    "Surface goes above y=255 (decrease vscale or decrease vshift)"



# Loop through all cells and assign blocks:

total = 0
with create_world(mapname) as world:
    for i_ in xrange(0,bed.shape[0],step*batch_size):
        with batch_changes():
            for i in xrange(i_, min(i_ + step * batch_size, bed.shape[0]), step):
                print "Processing row %d/%d" % (i//step+1, bed.shape[0]//step)
                for j in xrange(0,bed.shape[1],step):
                    try:
                        bedheight = tomc(bed[i, j])
                        baseheight = tomc(base[i, j])
                        surfheight = tomc(surf[i, j])
                        if base[i, j] > 0 and surfheight == baseheight:
                            baseheight -= 1
                        if baseheight < bedheight:
                            bedheight = baseheight
                    except ValueError:
                        continue
                    mats = [(air, bedheight), (rock, baseheight - bedheight),
                            (grass, surfheight - baseheight)]
                    total += surfheight
                    fill_column(world, j//step, i//step, *mats)
        world.saveInPlace() 
        world.setPlayerPosition((bed.shape[1]//(step*2), 250,
            bed.shape[0]//(step*2)))

print total, "blocks used"
