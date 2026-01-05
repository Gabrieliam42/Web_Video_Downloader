## Web Video Downloader

# What each of the script does:
  - It checks admin privileges - If not admin, relaunches itself with elevated permissions
  - Then it finds yt-dlp.exe - Searches bundled location (when compiled) or current directory
  - Opens the graphical interface with URL input field
  - The user  should then enter URL , so copy paste the YouTube/Facebook video URL and click "Download Video"
  - The script downloads the video from the URL to the current directory, it uses yt-dlp (https://github.com/yt-dlp/yt-dlp) with a simple GUI to fetch the best quality MP4 (or MP3)
  - It also downloads any available English subtitle and saves it as separate .srt file
  - You can see its progress in the scrollable text area
  - It saves the video or audio and subtitle to the current directory

`YT-DLP_HQ_Video_w_Subtitle_EN_lib.py` and `YT-DLP_HQ_MP3_w_Subtitle_EN_lib.py` use the `yt-dlp` Python library
#
`YT-DLP_HQ_Video_w_Subtitle_EN_local.py` and `YT-DLP_HQ_MP3_w_Subtitle_EN_local.py` work with your local files from the current working directory


  Key parameters: Best MP4 quality (or MP3 quality), English subtitles, no subtitle embedding, the video filename is the same as the video name, the same goes with the MP3 name.

##### This script has been tested and compiled for the Windows environment.
#

`YT-DLP_HQ_Video_w_Subtitle_EN_lib.exe` is already bundled and compiled with the `yt-dlp` Python library.
`YT-DLP_HQ_Video_w_Subtitle_EN_local.exe` is already bundled and compiled with the `yt-dlp.exe` and `_internal` directory included.
#### You can use either of them, the two versions are built differently but both versions do the same action.

`YT-DLP_HQ_MP3_w_Subtitle_EN_lib.exe` is already bundled and compiled with the `yt-dlp` Python library.
`YT-DLP_HQ_MP3_w_Subtitle_EN_local.exe` is already bundled and compiled with the `yt-dlp.exe` and `_internal` directory included.
#
[Download Latest Releases(v1.0.0)](https://github.com/Gabrieliam42/Web_Video_Downloader/releases/tag/1.0.0)


##### Requirements:

- `yt-dlp`

#

##### The compiled versions don't have any requirements, they are already bundled with everything they need.



<br><br>





<br><br>




**Script Developer:** Gabriel Mihai Sandu  
**GitHub Profile:** [https://github.com/Gabrieliam42](https://github.com/Gabrieliam42)
