import sys, time, json
from stoa import llm
from stoa.data import abspath
p = sys.argv[1]
prompt = ('This is a Finnish apartment floor plan. Find every ROOM NAME label written inside the rooms '
 '(abbreviations such as OH, MH, K, KT, KK, KH, PH, PESUH, S, SAUNA, LH, WC, ET, AK, VH, VAR, PARV, TK, KHH, TUPA, AULA). '
 'Ignore numbers, room areas, dimensions and furniture codes. '
 'Output JSON: [{"point_2d":[x,y],"label":"<exact text>"}], one entry per label.')
t=time.time()
r = llm.chat(prompt, images=[abspath(p)], max_tokens=700, extra_body={"repetition_penalty":1.05})
print(round(time.time()-t,1), r.prompt_tokens, r.completion_tokens, r.finish_reason)
print(r.text[:3000])
