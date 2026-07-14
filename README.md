# Legend Of Zelda: Breath Of The Wild ASCII
2D Top Down FULL ASCII of BOTW with HTML renderer and PNG overview for performance boost.  <br>
HOWEVER, heightfield is toggleable in settings, so 2.25D? <br>
I can't do much more than this, so expand on it and make it better if you want. <br><br>
Web Demo Live: https://katsugachi.github.io/botw-ascii-2D/ <br>

## Resolution Adjusting
Web version has 89MB version built in, local version by default uses DEFAULT_TILE_RESOLUTION of 100 (total 10mb, very small). <br>
You can adjust the resolution in the stitching python file under DEFAULT_TILE_RESOLUTION 
| Setting   | Tile Resolution | Approx. Size |
|-----------|------------------|--------------|
| Small     | 100              | ~10MB        |
| Medium    | 200              | ~45MB        |
| Big       | 300              | ~90MB        |
| Full Res  | 750              | ~560MB       |

## Instructions - Build From Scratch
#### 1. Clone & Navigate <br>
`git clone https://github.com/Katsugachi/botw-ascii-2D/tree/main` <br>
and <br>
`cd botw-ascii-2D`
<br>

#### 2. Run Tile Stitch and convert to ASCII <br>
use built in `stitchandasciify.py` to stitch and ascii<br>
`py -m stitchandasciify` <br>
confirm and run script to generate `BOTW-ASCII.txt`
<br>

#### 3. Import & Render <br>
typical text programs (notepad, notepad++) will lag heavily trying to render 10mb+ of ASCII art. <br>
Instead, use built in `Hyrule Atlas.html` and import `BOTW-ASCII.txt` <br>
should render a bit laggy but fine

## Alternative
Grab finished fully built `BOTW-ASCII.txt` from /finished file/BOTW-ASCII.txt directly and download it to load it into the renderer.

## Side Note
Since its the holidays rn, this took like one afternoon and a cup of tea, pretty neat! 
