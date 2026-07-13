# Legend Of Zelda: Breath Of The Wild ASCII
2D Top Down FULL ASCII of BOTW with HTML renderer and overview for performance boost.  <br>
HOWEVER, heightfield is toggleable in settings, so 2.25D? <br>
I can't do much more than this, so expand on it and make it better if you want. <br><br>
Web Demo Live: https://katsugachi.github.io/botw-ascii-2D/
## Instructions
1. Clone & Navigate <br>
`git clone https://github.com/Katsugachi/botw-ascii-2D/tree/main` <br>
and <br>
`cd botw-ascii-2D`
<br>

2. Run Tile Stitch and convert to ASCII <br>
use built in `stitchandasciify.py` to stitch and ascii<br>
`py -m stitchandasciify` <br>
confirm and run script to generate `BOTW-ASCII.txt`
<br>

3. Import & Render <br>
typical text programs (notepad, notepad++) will lag heavily trying to render 10mb+ of ASCII art. <br>
Instead, use built in `Hyrule Atlas.html` and import `BOTW-ASCII.txt` <br>
should render a bit laggy but fine

## Alternative
Grab finished fully built `BOTW-ASCII.txt` from /finished file/BOTW-ASCII.txt directly and download it to load it into the renderer.
