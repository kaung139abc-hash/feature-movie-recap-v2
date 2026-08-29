assets/README.md

Place the following into the assets/ directory before running the 2D worker:
- portrait.png            (the character portrait/base image)
- mouths/mouth_rest.png   (default mouth)
- mouths/mouth_A.png
- mouths/mouth_O.png
- mouths/mouth_M.png
- ... add other mouth_<VISEME>.png files matching Rhubarb viseme labels

Mouth image sizes should be similar and be designed to overlay on portrait.png at the coordinates used in the worker (currently overlay at x=520,y=400). You can adjust overlay coordinates in create_video_worker_2d.js if needed.
