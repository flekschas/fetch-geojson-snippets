#!/usr/bin/env python3

import argparse
import math
import numpy as np
import os
import requests
import sqlite3
import struct
import sys
import zlib

from hgtiles.geo import get_tile_pos_from_lng_lat
from io import BytesIO
from PIL import Image
from random import random


def is_within(start1, end1, start2, end2, width, height):
    return start1 < width and end1 > 0 and start2 < height and end2 > 0


def np_to_png(arr, comp=9):
    sz = arr.shape

    # Add alpha values
    if arr.shape[2] == 3:
        out = np.ones(
            (sz[0], sz[1], sz[2] + 1)
        )
        out[:, :, 3] = 255
        out[:, :, 0:3] = arr
    else:
        out = arr

    return write_png(
        np.flipud(out).astype('uint8').flatten('C').tobytes(),
        sz[1],
        sz[0],
        comp
    )


def png_pack(png_tag, data):
    chunk_head = png_tag + data
    return (struct.pack("!I", len(data)) +
            chunk_head +
            struct.pack("!I", 0xFFFFFFFF & zlib.crc32(chunk_head)))


def write_png(buf, width, height, comp=9):
    """ buf: must be bytes or a bytearray in Python3.x,
        a regular string in Python2.x.
    """

    # reverse the vertical line order and add null bytes at the start
    width_byte_4 = width * 4
    raw_data = b''.join(
        b'\x00' + buf[span:span + width_byte_4]
        for span in np.arange((height - 1) * width_byte_4, -1, - width_byte_4)
    )

    return b''.join([
        b'\x89PNG\r\n\x1a\n',
        png_pack(b'IHDR', struct.pack("!2I5B", width, height, 8, 6, 0, 0, 0)),
        png_pack(b'IDAT', zlib.compress(raw_data, comp)),
        png_pack(b'IEND', b'')])


def get_snippet_from_image_tiles(
    tiles,
    tile_size,
    tiles_x_range,
    tiles_y_range,
    tile_start1_id,
    tile_start2_id,
    from_x,
    to_x,
    from_y,
    to_y
):
    im = (
        tiles[0]
        if len(tiles) == 1
        else Image.new(
            'RGB',
            (tile_size * len(tiles_x_range), tile_size * len(tiles_y_range))
        )
    )

    # Stitch them tiles together
    if len(tiles) > 1:
        i = 0
        for y in range(len(tiles_y_range)):
            for x in range(len(tiles_x_range)):
                im.paste(tiles[i], (x * tile_size, y * tile_size))
                i += 1

    # Convert starts and ends to local tile ids
    start1_rel = from_x - tile_start1_id * tile_size
    end1_rel = to_x - tile_start1_id * tile_size
    start2_rel = from_y - tile_start2_id * tile_size
    end2_rel = to_y - tile_start2_id * tile_size

    # Ensure that the cropped image is at least 1x1 pixel otherwise the image
    # is not returned as a numpy array but the Pillow object... (odd bug)
    x_diff = end1_rel - start1_rel
    y_diff = end2_rel - start2_rel

    if x_diff < 1.0:
        x_center = start1_rel + (x_diff / 2)
        start1_rel = x_center - 0.5
        end1_rel = x_center + 0.5

    if y_diff < 1.0:
        y_center = start1_rel + (y_diff / 2)
        start2_rel = y_center - 0.5
        end2_rel = y_center + 0.5

    # Notice the shape: height x width x channel
    return np.array(im.crop((start1_rel, start2_rel, end1_rel, end2_rel)))


def get_images(
    id,
    db,
    session,
    src_url,
    start_lng,
    end_lng,
    start_lat,
    end_lat,
    zoom_from=0,
    zoom_to=math.inf,
    padding=0,
    tile_size=256,
    max_size=512,
    mapbox_api_key=None,
    verbose=False,
):
    width = 360
    height = 180

    ims = []

    q = 'SELECT COUNT(*) FROM images WHERE id = ? AND z = ?'

    for zoom_level in range(zoom_from, zoom_to + 1):
        if db.execute(q, (id, zoom_level)).fetchone()[0] > 0:
            if verbose:
                print('Skipped [{}: {}]. Already loaded!'.format(
                    id, zoom_level
                ))
            # Snippet already loaded
            continue

        if not is_within(
            start_lng + 180,
            end_lng + 180,
            end_lat + 90,
            start_lat + 90,
            width,
            height
        ):
            ims.append(None)
            continue

        # Get tile ids
        start1, start2 = get_tile_pos_from_lng_lat(
            start_lng, start_lat, zoom_level
        )
        end1, end2 = get_tile_pos_from_lng_lat(
            end_lng, end_lat, zoom_level
        )

        xPad = padding * (end1 - start1)
        yPad = padding * (start2 - end2)
        pad = min(xPad, yPad)

        start1 -= pad
        end1 += pad
        start2 += pad
        end2 -= pad

        tile_start1_id = math.floor(start1)
        tile_start2_id = math.floor(start2)
        tile_end1_id = math.floor(end1)
        tile_end2_id = math.floor(end2)

        start1 = math.floor(start1 * tile_size)
        start2 = math.floor(start2 * tile_size)
        end1 = math.ceil(end1 * tile_size)
        end2 = math.ceil(end2 * tile_size)

        max_dim = max(end1 - start1, end2 - start2)

        if max_dim > max_size:
            print('Too big for a preview ({} > {})'.format(max_dim, max_size))
            ims.append(None)
            continue

        tiles_x_range = range(tile_start1_id, tile_end1_id + 1)
        tiles_y_range = range(tile_start2_id, tile_end2_id + 1)

        # Extract image tiles
        tiles = []
        for y in tiles_y_range:
            for x in tiles_x_range:
                src = (
                    '{}/{}/{}/{}.png'.format(src_url, zoom_level, x, y)
                )

                if mapbox_api_key:
                    src += '?access_token={}'.format(mapbox_api_key)

                req = session.get(src)

                if req.status_code == 200:
                    tiles.append(Image.open(
                        BytesIO(req.content)
                    ).convert('RGB'))
                else:
                    tiles.append(None)

        im_snip = get_snippet_from_image_tiles(
            tiles,
            tile_size,
            tiles_x_range,
            tiles_y_range,
            tile_start1_id,
            tile_start2_id,
            start1,
            end1,
            start2,
            end2
        )

        if verbose:
            print(
                'Loaded [{}: {}]'.format(id, zoom_level),
                'Shape: {}'.format(im_snip.shape),
                'Pixel Pos: x:{}-{} y:{}-{}'.format(
                    start1,
                    end1,
                    start2,
                    end2,
                ),
                'Geo Pos: lng:{}-{} lat:{}-{}'.format(
                    start_lng,
                    end_lng,
                    start_lat,
                    end_lat,
                )
            )

        ims.append((zoom_level, np_to_png(im_snip)))

    return ims


def store_meta_data(
    db, zoom_step, max_length, assembly, chrom_names,
    chrom_sizes, tile_size, max_zoom, max_size, width, height
):
    db.execute('''
        CREATE TABLE tileset_info
        (
            zoom_step INT,
            max_length INT,
            assembly TEXT,
            chrom_names TEXT,
            chrom_sizes TEXT,
            tile_size INT,
            max_zoom INT,
            max_size INT,
            width INT,
            height INT
        )
        ''')

    db.execute(
        'INSERT INTO tileset_info VALUES (?,?,?,?,?,?,?,?,?,?)', (
            zoom_step,
            max(width, height),
            assembly,
            chrom_names,
            chrom_sizes,
            tile_size,
            max_zoom,
            max_size,
            width,
            height
        )
    )
    db.commit()

    pass


def create_img_cache(db, clear=False):
    if clear:
        db.execute('DROP TABLE IF EXISTS images')
        db.commit()

    db.execute('''
        CREATE TABLE IF NOT EXISTS images
        (
            id int NOT NULL,
            z INT NOT NULL,
            image BLOB,
            PRIMARY KEY (id, z)
        )
        ''')
    db.commit()


def pre_fetch_and_save_img(
    db,
    session,
    src_url,
    id,
    x_from,
    x_to,
    y_from,
    y_to,
    zoom_from,
    zoom_to,
    max_size,
    padding,
    mapbox_api_key=None,
    verbose=False,
):
    # ?,?,? are uuid, zoom-level, bytes (of the image)
    query_insert_image = 'INSERT INTO images VALUES (?,?,?)'

    images = get_images(
        id,
        db,
        session,
        src_url,
        x_from,
        x_to,
        y_from,
        y_to,
        zoom_from=zoom_from,
        zoom_to=zoom_to,
        max_size=max_size,
        padding=padding,
        mapbox_api_key=mapbox_api_key,
        verbose=verbose,
    )

    for image in images:
        if image is not None:
            db.execute(
                query_insert_image,
                (id, image[0], sqlite3.Binary(image[1]))
            )
            db.commit()


def fetch_geojson_snippets(
    geojson_db_path,
    mapbox_api_key,
    mapbox_style,
    zoom_from,
    zoom_to,
    max_size,
    padding,
    clear,
    verbose
):
    if not os.path.isfile(geojson_db_path):
        sys.exit('GeoJSON file not found! ☹️')

    padding /= 100
    padding = max(0, min(1, padding))

    # Read snapshots
    db = sqlite3.connect(geojson_db_path)

    create_img_cache(db, clear)

    info = db.execute('SELECT * FROM tileset_info').fetchone()
    info = {
        'zoom_step': info[0],
        'tile_size': info[1],
        'max_zoom': info[2],
        'min_x': info[3],
        'max_x': info[4],
        'min_y': info[5],
        'max_y': info[6],
    }

    annotations = db.execute('SELECT * FROM intervals').fetchall()

    if len(mapbox_api_key) == 0:
        prefixes = ['a', 'b', 'c']
        prefix_idx = math.floor(random() * len(prefixes))
        src = 'http://{}.tile.openstreetmap.org'.format(prefixes[prefix_idx])
    else:
        src = 'http://api.tiles.mapbox.com/v4/'
        if len(mapbox_style) > 0:
            src += mapbox_style + '/'

    session = requests.Session()

    # Convert snapshots to dict
    for annotation in annotations:
        pre_fetch_and_save_img(
            db,
            session,
            src,
            annotation[0],
            annotation[3], annotation[4],
            annotation[6], annotation[5],
            max(zoom_from, 0),
            min(zoom_to, info['max_zoom']),
            max_size,
            padding,
            mapbox_api_key=mapbox_api_key,
            verbose=verbose,
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        'file',
        help='GeoJSON DB file',
        type=str
    )

    parser.add_argument(
        '-f', '--zoom-from',
        default=0,
        help='initial zoom of for preloading (farthest zoomed out)',
        type=int
    )

    parser.add_argument(
        '-t', '--zoom-to',
        default=math.inf,
        help='final zoom of for preloading (farthest zoomed in)',
        type=int
    )

    parser.add_argument(
        '-m', '--max-size',
        default=512,
        help='max size (in pixel) for preloading a snapshot',
        type=int
    )

    parser.add_argument(
        '-p', '--padding',
        default=10,
        help='percentage padding per side relative to the width / height',
        type=int
    )

    parser.add_argument(
        '-c', '--clear',
        action='store_true',
        help='clear previsouly fetched images',
    )

    parser.add_argument(
        '-v', '--verbose',
        help='increase output verbosity',
        action='store_true'
    )

    parser.add_argument(
        '--mapbox',
        default='',
        help='Mapbox API key to load their tiles',
        type=str
    )

    parser.add_argument(
        '--mapbox-style',
        default='',
        help='Mapbox style',
        type=str
    )

    args = parser.parse_args()

    fetch_geojson_snippets(
        args.file,
        args.mapbox,
        args.mapbox_style,
        args.zoom_from,
        args.zoom_to,
        args.max_size,
        args.padding,
        args.clear,
        args.verbose
    )

if __name__ == '__main__':
    main()
