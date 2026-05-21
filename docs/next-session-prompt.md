## Continue from: CI content quality fixes (2026-04-02)

Three fixes from Seth/Lawrence review of the actual CI data:

### 1. Fix persona extraction prompt (30 min)
Personas are job titles, not humans. "Scaling CTOs" tells a hunter nothing about the person.

Fix `jobs/ingestion/extract.py` FOUNDATION_EXTRACTION_TEMPLATE persona section. Current prompt asks for name, role, profile, communication, decision_criteria, objections, how_to_reach. It produces functional descriptions.

Add: fears (what keeps them up at 2AM), motivation (what does success look like for them personally), trigger (what event makes them ready to buy). The extraction already asks for objections — extend to emotional context. Then truncate personas table and re-run foundation ingestion for both site and marketing.

### 2. Add proof point extraction
Sanoma Learning (12yr) and Consumentenbond (6yr) are our strongest selling points but they're not in the CI. The foundation lens correctly skips client outcomes (it extracts our positioning). The narrative lens extracts reframes but not structured proof points with specific numbers.

Options:
- Add a "proof_point" type to the narrative extraction prompt: company name, outcome (with numbers), duration, relevance to which change statement
- Or create a manual proof_points table and curate the top 5-10 from case studies
- Or tag specific insights as proof points

The proof points should surface in meeting prep and training exercises. The calendar prep prompt should include relevant proof points for the attendee's industry.

### 3. Generate safe passage questions from worldview pairs
Lawrence's idea: questions that open the door to vulnerability in a meeting. Generated from worldview belief + pain pairs.

Example: belief "Lock-in is invisible until you try to leave" + pain "Shock at the true cost of migration" → safe passage question: "Many CTOs we talk to didn't realize the full switching cost until they tried to move. Has that come up for you?"

Build as:
- A function that takes a worldview record and generates a safe passage question
- Wire into meeting prep (calendar_sync.py generate_prep) — include 1-2 relevant questions
- Could also be a training exercise type: "practice asking this question"
