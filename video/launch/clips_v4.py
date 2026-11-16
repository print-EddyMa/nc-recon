"""Cut and grade the public-domain DVIDS footage for the v4 film: `python3 video/launch/clips_v4.py [--check]`.

Sources (assets/dvids, git-ignored): DVIDS 943308 "Hurricane Helene Debris Swannanoa",
939562 "NCNG Aircrew Surveys Damage, Supports Relief Efforts in Western NC",
939345 "Aviation b-roll package during Hurricane Helene". All marked PUBLIC DOMAIN on
DVIDS. Grade: lower the white overcast sky, cool shadows, warm highlights, less colour.
Writes assets/v4/clips/<name>/0000.jpg ...
"""
import os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "assets", "dvids")
OUT = os.path.join(HERE, "assets", "v4", "clips")
SW, NG, AV = "DOD_110675946.mp4", "DOD_110611356.mp4", "DOD_110607871.mp4"
GRADE = ("curves=master='0/0 0.18/0.11 0.5/0.44 0.8/0.74 1/0.9',"
         "eq=contrast=1.08:saturation=0.8,"
         "colorbalance=rs=-0.05:gs=-0.01:bs=0.06:rh=0.05:gh=0.01:bh=-0.05")
CLIPS = [  # name, source, start s, duration s
    ("aerial", NG, 342.0, 3.2), ("flood", NG, 156.0, 3.2), ("river", NG, 221.0, 3.0), ("washed", NG, 245.0, 3.0),
    ("crew", NG, 190.0, 3.0), ("cockpit", NG, 205.0, 2.6), ("trailer", NG, 365.0, 3.0), ("bridge", SW, 494.0, 2.6),
    ("fridge", SW, 548.0, 2.6), ("balls", SW, 445.0, 3.6), ("toycar", SW, 593.0, 3.4), ("wreck", SW, 805.0, 2.6),
    ("roof", SW, 729.0, 2.6), ("pallet", AV, 202.0, 2.4),
]


def main() -> None:
    check = "--check" in sys.argv
    for name, src, ss, dur in CLIPS:
        d = os.path.join(OUT, name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        t = ["-t", "0.04"] if check else ["-t", str(dur)]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(ss), "-i", os.path.join(D, src), *t,
                        "-vf", f"fps=30,{GRADE}", "-q:v", "3", os.path.join(d, "%04d.jpg")], check=True)
        print(name, len(os.listdir(d)))


if __name__ == "__main__":
    main()
