import sys, time, json
from stoa import llm
from stoa.data import abspath
p = sys.argv[1]
prompt = sys.argv[2] if len(sys.argv) > 2 else ('Read every text label written on this floor plan (room names and abbreviations such as MH, OH, KH, WC, S, K, KT, PARV, ET, VH). '
 'Output JSON: [{"bbox_2d":[x1,y1,x2,y2],"text":"<exact text>"}], one entry per label occurrence.')
t=time.time()
r = llm.chat(prompt, images=[abspath(p)], max_tokens=2048, max_pixels=int(sys.argv[3]) if len(sys.argv)>3 else 3_200_000)
print(time.time()-t, r.prompt_tokens, r.completion_tokens, r.images[0])
print(r.text[:3000])
