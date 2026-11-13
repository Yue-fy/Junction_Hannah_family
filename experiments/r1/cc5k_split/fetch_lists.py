"""Fetch ONLY the official CubiCasa5K split lists (train.txt / val.txt / test.txt) from the Zenodo zip,
using HTTP range requests (reads the zip's central directory + 3 tiny files; no images, no labels).
Output: $JUNCTION_SHARED/artifacts/R1/cc5k_split/{train,val,test}.txt
Run: python3 -I fetch_lists.py
"""
import io
import os
import sys
import urllib.request
import zipfile

URL = "https://zenodo.org/records/2613548/files/cubicasa5k.zip?download=1"
OUT = os.path.join(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"), "artifacts", "R1", "cc5k_split")


class HttpFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "python-urllib"})
        with urllib.request.urlopen(req, timeout=60) as r:
            self.url = r.geturl()
            self.size = int(r.headers["Content-Length"])
        self.fetched = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{self.pos + n - 1}", "User-Agent": "python-urllib"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        b[: len(data)] = data
        self.pos += len(data)
        self.fetched += len(data)
        return len(data)


if __name__ == "__main__":
    f = HttpFile(URL)
    print("zip size", f.size, file=sys.stderr)
    z = zipfile.ZipFile(io.BufferedReader(f, buffer_size=1 << 20))
    names = [n for n in z.namelist() if n.endswith((".txt",)) and n.count("/") <= 1]
    print("txt files at top level:", names, file=sys.stderr)
    os.makedirs(OUT, exist_ok=True)
    for n in names:
        with open(os.path.join(OUT, os.path.basename(n)), "wb") as g:
            g.write(z.read(n))
    print("fetched bytes", f.fetched, file=sys.stderr)
