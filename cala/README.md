# Cala · Make Unicorns Real

Junction 2026 candidate notes · 14 November 2026. The public announcement examples have been checked. Live Cala results for these rounds and the product workflow still need verification.

[Challenge and judging](https://hackjunction.app/participate/45/challenges/350) · [Cala quickstart](https://docs.cala.ai/quickstart) · [Cala Console](https://console.cala.ai/)

## Product and demo

Help a European construction software founder preparing a Seed round choose a short list of investors to contact. Ask which funds recently led rounds for comparable companies. Each result shows the comparable company, round and date, recorded investor role and a link to the original source. Explain why a fund appeared using the selected sector, stage and recent documented activity.

Give each result a small, clickable relationship view: fund, role in this round, financing round, company. Use explicit labels for **Lead confirmed**, **Participation confirmed** and **Role unknown**. If sources conflict, show the discrepancy. Changing the stage, time window or lead-only filter should update the list and the displayed reasons.

Start by checking two real Seed rounds. The Volve announcement says Skyfall Ventures led the round and J12 participated. Switching on **Only confirmed leads** should keep Skyfall and remove J12 from that round's result. The Brickanta announcement gives a second expected match with Northzone as lead. Open the publisher's announcement from the graph in both cases.

[Original Volve announcement](https://www.volvetech.com/insights/volve-raises-seed-round) · [Original Brickanta announcement](https://brickanta.com/blog/brickanta-seed-announcement)

## Data and implementation

1. Use [Cala Query](https://docs.cala.ai/api-reference/query) to find candidate companies, rounds and entities. Query the company-to-round data first and retain Cala entity IDs where available. Result columns depend on the query and amounts may arrive as strings with currency or qualifiers.
2. Discover available relationship fields via [Entity Introspection](https://docs.cala.ai/api-reference/entity-introspection), then retrieve them with [Retrieve Entity](https://docs.cala.ai/api-reference/entities). Use [Cala Search](https://docs.cala.ai/api-reference/search) for sourced narrative and evidence references. Verify that each claimed lead can be tied to a publisher URL and to the correct round.
3. Give each relationship a company, round or date, investor, role, source URL, supporting passage or locator and retrieval time. Preserve qualifiers such as an approximate amount. Keep an unknown role visible as unknown. Use stable IDs to deduplicate where available and distinguish two rounds involving the same fund and company.
4. Rank by stage fit, recency of confirmed roles and the number of comparable rounds. Show the reasons in the UI. An LLM can summarize the retrieved facts in a short founder brief. Validate the brief's evidence references before display.
5. Redeem event credits using the code and instructions on the challenge page. The listed path is **Billing → Extra credits → Add credits → Add promo code** in Cala Console. API calls use `X-API-KEY`. Use the server-side key for development or connect through [Cala MCP](https://docs.cala.ai/integrations/mcp).

## Pilot and judging

Time-box the first API probe to 30 minutes. Try an industry search for recent European construction software Seed rounds, then query Volve and Brickanta directly. Aim for three usable company–round–investor links and at least two leads that you can verify against an original announcement. Record coverage, time, source quality and any confusion between lead and participant. Add one case with an unknown role and re-run with the stage filter changed. Publisher announcements provide the expected answers for the probe. For the demo, showing a role as confirmed requires supporting evidence in the product flow.

Cala weights real need, execution, originality and meaningful use of Cala at 25% each. In a two-minute recording, show a founder's input, a short list, the source for a role and how the lead-only control changes the result. The demo story is about priority and evidence, with Cala powering discovery and the relationships.

If lead-role coverage is too thin, test a second concept for the same founder: **Find the first customers to call after a funding announcement.** Focus on companies that announced a specific expansion, show the wording that signals a need and explain where the founder's product fits. Check three such claims before choosing it.

## Research and product references

- [Xu et al., investor recommendation](https://arxiv.org/abs/1912.02962) and [SocioLink](https://www.tandfonline.com/doi/abs/10.1080/07421222.2023.2196771). Use their emphasis on investor, company and domain relationships to guide the data model. A few visible evidence paths are enough for the first demo.
- [OpenVC investor filters](https://docs.openvc.app/en/articles/13228069-filter-the-right-investors) and [Dealroom Top Investors](https://knowledge.dealroom.co/knowledge/top-investors). Investor filters and activity rankings already exist. Our proposed differentiation is tying each ranking reason to a specific round, role and original announcement.
- [Bedrock](https://github.com/BedRockerAI/bedrock) is a public Cala-based project that makes a source field mandatory for visible claims. [Clay funding signals](https://university.clay.com/docs/monitor-for-news-fundraising) is a reference for the customer discovery alternative.
