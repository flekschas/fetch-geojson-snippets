# Fetch Snippets for HiGlass's GeoJSON DB

> Load multiresolution images of GeoJSON annotations and store them alongside the annotations for fast retrieval.

[![HiGlass](https://img.shields.io/badge/higlass-👍-red.svg?colorB=000000)](http://higlass.io)

Loading image snippets for GeoJSON annotations from OpenStreetMap or Mapbox can be slow as it requires 2 requests: one to the HiGlass server and another one from the HiGlass server to OSM or Mapbox. Since annotations rarely overlap perfectly with a pre-compiled image tiles, on-the-fly extraction requires saving the cut out snippet as JPEG or PNG again, which is computationally heavy if the number of requested GeoJSON annotation snippets is high. To alleviate this problem we can cut out these snippets a priori and store them alongside the annotations.

**Note**: This is the source code for loading the GeoJSON annotations only! You might want to check out the following repositories as well if you want to know how to convert and view GeoJSON in HiGlass:

- HiGlass viewer: https://github.com/hms-dbmi/higlass
- HiGlass server: https://github.com/hms-dbmi/higlass-server
- HiGlass GeoJSON track: https://github.com/flekschas/higlass-geojson
- Clodius GeoJSON to GeoDB converter: https://github.com/hms-dbmi/clodius

## Installation

**Prerequirements**:

- Python `v3.6`
- PIP (or conda)

```bash
git clone https://github.com/flekschas/fetch-geojson-snippets && cd fetch-geojson-snippets
mkvirtualenv -a $(pwd) -p python3 fetch-geojson-snippets  // Not necessary but recommended
pip install --upgrade -r ./requirements.txt
```

## CLI

```bash
usage: fetch.py [-h] [-f ZOOM_FROM] [-t ZOOM_TO] [-m MAX_SIZE] [-p PADDING]
                [-c] [-v] [--mapbox MAPBOX] [--mapbox-style MAPBOX_STYLE]
                file

positional arguments:
  file                  GeoJSON DB file

optional arguments:
  -h, --help            show this help message and exit
  -f ZOOM_FROM, --zoom-from ZOOM_FROM
                        initial zoom of for preloading (farthest zoomed out)
  -t ZOOM_TO, --zoom-to ZOOM_TO
                        final zoom of for preloading (farthest zoomed in)
  -m MAX_SIZE, --max-size MAX_SIZE
                        max size (in pixel) for preloading a snapshot
  -p PADDING, --padding PADDING
                        percentage padding per side relative to the width /
                        height
  -c, --clear           clear previsouly fetched images
  -v, --verbose         increase output verbosity
  --mapbox MAPBOX       Mapbox API key to load their tiles
  --mapbox-style MAPBOX_STYLE
                        Mapbox style
```

**Example:**

```
./fetch.py my-fancy-annotations.geodb
```

*Note: This script augments `my-fancy-annotations.geodb` in-place*
