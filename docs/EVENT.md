# EVENT — Junction 2026 facts

> Collected by the captain on Fri 13 Nov 2026 (evening), before the challenge details were public.
> Where this file and the Junction Platform or a mentor disagree, they win. Tell the captain so this file gets fixed.

## Deadlines and schedule (Helsinki time, EET)

| When | What |
|---|---|
| Fri 13 Nov 18:00 | Opening ceremony: challenge videos, Google DeepMind keynote |
| Fri 19:30 | Hacking starts |
| Fri 20:00 | Google DeepMind workshop |
| Fri 20:30 | Arduino workshop "Getting started with the UNO Q" (Modulino sensors, running AI locally) and the Verda workshop (Loft) |
| **Fri 23:59** | **Preliminary submission.** The app says 23:55, so aim for 23:30 |
| Sat 14 Nov 11:00 | Cala workshop, Loft (4th floor). Cala shares its judging criteria here |
| Sat 12:00 | Submissions open on the Junction Platform |
| **Sun 15 Nov 10:00** | **Final submission deadline** |
| Sun 14:00 | Final ceremony and top-5 pitches |
| Sun 15:10 / 15:50 | Challenge winners / Junction overall winner |

## How winning works

- **Challenge prizes:** each challenge partner picks its own winner using its own criteria. Ask the mentor for those criteria early.
- **Overall winner:** face-to-face peer review picks the top 5. They pitch live to a seven-person grand jury:
  Kia Kanninen (Founders House), Daksh Raghuvanshi (AfterQuery), Otto Söderlund (Supercell),
  Timo Ahopelto (Lifeline Ventures), Umar Noor (Google DeepMind), Hubertus van der Drift (Context.dev),
  and Arturs Polis (Verda). Verda says he looks for "prototypes with a clear path to production and scale".
- Prizes total €100,000; the breakdown is TBD. Teams have 1–4 people. Submissions are open-sourced under the MIT licence.

## Tracks and challenges (known before the videos)

| Track / challenge | Partner | What we know |
|---|---|---|
| Hardware Track | Arduino (main partner) | A whole floor. UNO Q boards, components, 3D printers, LeRobot arms, and hardware mentors |
| AI Infrastructure Track | Verda (main partner) | TBD |
| "Make Unicorns Real" | Cala | Build a product for founders or VCs on Cala's public data (companies, people, investors, funding rounds) |
| AI glasses / new hardware | Meta | Only known from LinkedIn; details TBD |
| Main Challenge | Tieto | TBD |
| Healthcare, FinTech, Agentic AI, Data | TBD | Track names only |

Other challenge partners (logos only so far): Hostinger, Valio Aimo, S-Pankki, Aalto University,
City of Espoo, Exa, MariaDB, AfterQuery, Bahn Express, AstraZeneca, Stoa, Intel, Context.dev, Rokoko,
Ignite Next. Google DeepMind says "something special" is planned for the winning teams.

## MLH sponsor tech and prizes

MLH runs its own prize categories, and **its tech can be combined with any Junction challenge**.
- Promo codes: MLH's email "Everything you'll need to know from MLH at Junction" (from hi@mlh.io).
  **Never commit promo codes or API keys, because this repo is public.** Put them in `.env`.
- How to enter the MLH prizes: TBD. Check https://mlh.link/junction-26 in a browser; it doesn't render for scripts.
- Use sponsor tech only where it actually improves the demo. Judges notice integrations that were bolted on.

| Tech | Good for | Free credit | Link | Captain's take |
|---|---|---|---|---|
| Gemini API (Google) | Multimodal LLMs, reasoning, image models | Hackathon guides | https://mlh.link/gemini | **High.** Vision and voice, and DeepMind is both a Junction partner and on the jury |
| ElevenLabs | Realistic speech, sound generation, voice cloning | ~$50 | https://mlh.link/elevenlabs | **High** for any voice or wearable demo |
| MongoDB Atlas | Database with vector search, so RAG without a separate vector store | $50 | https://mlh.link/mongodb | Medium–high for agentic or data apps |
| Vultr | Cloud servers and hosting | $100 | https://mlh.link/vultr | Medium. Gives us a public demo host, since our GPU box is on the Aalto network |
| TigerData | Real-time analytics and time-series data on PostgreSQL | $1000 for 30 days | https://mlh.link/tigerdata | Medium for sensor data (hardware) or fintech |
| Entire | AI-native version control that links commits to their prompts and agents | $10 | https://mlh.link/entire | Low–medium. It fits our agent workflow, but don't switch tooling mid-hackathon |
| Solana | Fast, cheap, verifiable ownership and payments | Free access | https://mlh.link/solana | Low, unless our challenge is about payments or ownership |

## Our own resources

- A workstation with an NVIDIA RTX PRO 6000 (96 GB VRAM). It can run large open models (vision, speech,
  LLM) locally. It's on the Aalto network, so reach it from the venue through SSH port forwarding, and test
  that early. Ask the captain for access.

## Sources

- Junction 2026 site: https://2026.hackjunction.com/
- Junction Platform event page: https://hackjunction.app/hackathons/junction-2026
- MLH summary: https://mlh.link/junction-26 (MLH announcement on stage, 13 Nov)
