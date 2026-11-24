Build a fact-checking system that verifies claims against a small corpus of documents using LLM API calls.

**Requirements**

1. *Document corpus.* Fetch the following 50 arXiv paper abstracts. These are your documents. Use the abstract as the document text; include title, authors, and published date as metadata.

2309.01431v2 2401.15884v3 2504.19754v1 2412.15246v1 2508.15253v2
2601.11863v1 2407.01102v1 2501.00332v1 2406.13692v2 2411.09213v1
2402.13178v2 2602.18734v2 2406.05804v6 2401.07324v3 2602.20867v1
2603.22386v1 2603.13404v1 2602.20426v1 2509.25370v1 2601.06112v1
2406.12276v1 2603.19896v1 2305.01937v1 2308.01862v1 2404.13076v1
2310.05657v1 2406.00936v1 2412.00543v1 2406.04244v1 2502.07445v2
2403.01432v5 2312.05934v3 2604.23801v1 2407.04528v4 2501.04652v2
2510.01600v2 2402.11035v3 2408.02152v3 2307.03172v3 2406.16008v2
2310.03025v2 2411.03538v1 2310.01427v1 2401.18058v1 2406.02818v1
2503.17407v2 2412.16926v3 2601.22548v3 2307.03172v1 2403.01432v1

2. *Claim verification.* The system takes a claim and returns:
   - A verdict: supported, contradicted, or unknown
   - Supporting evidence from the documents (relevant excerpts)

   Include a retrieval step: for each claim, select a smaller subset of relevant documents or passages before calling the LLM. Today's corpus is small enough to fit in a single context window; architect for a corpus several orders of magnitude larger.

3. *Grounding / reliability.* Verdicts must be supported by the documents.

4. *LLM usage.* Use an LLM via API as part of your solution. Structure the system however you like.

**Implementation**
- No GUI.
- No Docker - don't burn time on infra setup and external services.
- You should be able to run the program and verify example claims.
- Any libraries or frameworks you prefer.
- Aim to have a functioning app around the 30 minute mark. You are responsible for all the code produced and should be able to defend it.

**Before you start coding:** Walk us through three decisions out loud:
1. How you'll select relevant documents for each claim.
2. How you'll prevent the system from making things up when the corpus doesn't support a verdict.
3. How you'll know if your verdicts are correct.

You're free to change your mind as you build, but we'll use your initial answers as a reference point.

**What we're looking for.** We care more about how you direct your coding assistant, reason about reliability, and respond when we push on whether your system actually works than in the polish of the final output. Once you build something that works, expect us to probe its limits. Think aloud throughout.
