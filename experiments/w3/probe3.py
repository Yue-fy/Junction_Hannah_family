import sys, time, json, re
from PIL import Image
from stoa import llm
from stoa.data import abspath
p = sys.argv[1]; up=float(sys.argv[2]) if len(sys.argv)>2 else 1.0
img = llm.load_image(abspath(p))
if up!=1: img = img.resize((int(img.width*up), int(img.height*up)), Image.LANCZOS)
prompt = ('This is a Finnish apartment floor plan. Find every ROOM NAME label written inside the rooms '
 '(abbreviations such as OH, MH, K, KT, KK, KH, PH, PESUH, S, SAUNA, LH, WC, ET, AK, VH, VAR, PARV, TK, KHH, TUPA, AULA). '
 'Ignore numbers, room areas, dimensions and furniture codes. '
 'Output one line per label: `<text> (x, y)` with x,y the label centre in 0-1000 image coordinates.')
t=time.time()
r = llm.chat(prompt, images=[img], max_tokens=700, max_pixels=8_000_000)
print(round(time.time()-t,1), r.prompt_tokens, r.completion_tokens, r.finish_reason)
print(r.text[:3000])
