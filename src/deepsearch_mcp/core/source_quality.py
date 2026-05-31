"""Source-quality classification for search results (B15).

**Why.** A real Meta-LLM research run (2026-05-30) returned 8/8 SEO/content-farm
blogs and zero primary sources — and the agent had no way to tell a content
farm from Reuters. This tags each result so the agent can weight sources and
read the trustworthy ones first.

**Honest design.** We classify only what we can do with *high precision*:
  - `authoritative` — on a curated allowlist of well-known wire services,
    reputable press, academic/primary sources, and official company blogs, or
    on a trusted TLD (.gov/.edu/...).
  - `unknown` — everything else. This is the honest default: most of the web is
    not on a trust list, and "unknown" means *exactly that* — not "bad". We do
    NOT try to label sites `low_quality`: a content farm and a legitimate small
    blog are structurally identical, so a confident "low quality" verdict would
    defame real sites. Absence of `authoritative` is the useful signal (e.g.
    "this result set has zero authoritative sources → corroborate carefully").
"""

from __future__ import annotations

from urllib.parse import urlparse

AUTHORITATIVE = "authoritative"
UNKNOWN = "unknown"

# Trusted TLD suffixes (government / academic). Matched by host.endswith(...).
# All are registration-restricted to gov/academic bodies, so they stay
# high-precision. Extended beyond US/UK 2026-05-30 (B21) after a Japanese-policy
# run tagged 総務省 (soumu.go.jp) as `unknown`. NOTE: deliberately NOT the
# geographic `.<pref>.jp` municipal pattern (not gov-exclusive).
_AUTH_TLDS: tuple[str, ...] = (
    # United States
    ".gov", ".mil",
    # academic (generic + national)
    ".edu", ".ac.uk", ".edu.au", ".ac.jp", ".ac.kr", ".edu.sg",
    # United Kingdom / Commonwealth
    ".gov.uk", ".gov.au", ".govt.nz",
    # Canada
    ".gc.ca", ".canada.ca",
    # Japan (national + local government)
    ".go.jp", ".lg.jp",
    # Europe
    ".gouv.fr", ".bund.de", ".admin.ch", ".europa.eu",
    # Other national governments (gov.XX / go.XX / gob.XX patterns)
    ".gov.in", ".gov.sg", ".gov.br", ".gov.za", ".gov.cn",
    ".go.kr", ".gob.mx", ".gob.es",
)

# Curated registrable domains. A host matches if it equals one of these or is a
# subdomain (news.bbc.co.uk → bbc.co.uk). Kept deliberately high-precision;
# expand as new authoritative sources are vetted (see MAINTENANCE.md).
_AUTH_DOMAINS: frozenset[str] = frozenset({
    # Wire services / reputable press
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "bbc.com",
    "bbc.co.uk", "npr.org", "economist.com", "axios.com", "politico.com",
    # Tech press
    "theverge.com", "arstechnica.com", "wired.com", "techcrunch.com",
    "engadget.com", "zdnet.com", "cnbc.com", "theinformation.com",
    "venturebeat.com", "technologyreview.com", "spectrum.ieee.org",
    # Academic / primary research
    "arxiv.org", "nature.com", "science.org", "sciencedirect.com",
    "acm.org", "ieee.org", "semanticscholar.org", "pubmed.ncbi.nlm.nih.gov",
    # Official company / lab primary sources
    "openai.com", "anthropic.com", "ai.meta.com", "about.fb.com", "meta.com",
    "blog.google", "deepmind.google", "microsoft.com", "huggingface.co",
    "github.com", "modelcontextprotocol.io",
    # Editorially-maintained reference
    "wikipedia.org",
    # Industry analysts / research / consulting (B24, 2026-05-31) — their
    # published reports are editorially controlled and widely cited for tech
    # trends, markets, and funding data.
    "gartner.com", "forrester.com", "idc.com",
    "deloitte.com", "mckinsey.com", "bcg.com", "pwc.com", "accenture.com",
    "computer.org",        # IEEE Computer Society
    "crunchbase.com",      # incl. news.crunchbase.com (funding journalism)
    "hbr.org", "pewresearch.org",
    # NOTE: deliberately NOT forbes.com / inc.com / entrepreneur.com — these
    # run large *contributor* networks whose quality is per-author, not
    # per-domain, so the domain can't certify the article (same precision
    # principle as refusing to guess `low_quality`).
})


def classify_source(url: str) -> str:
    """Return AUTHORITATIVE or UNKNOWN for a result URL.

    Subdomain-aware (news.bbc.co.uk → authoritative) and strips a leading www.
    Never raises — a malformed URL is UNKNOWN.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return UNKNOWN
    if not host:
        return UNKNOWN
    if host.startswith("www."):
        host = host[4:]

    # Match a trusted suffix either as a real suffix (india.gov.in) OR when the
    # host IS the suffix itself (canada.ca, europa.eu, www.gov.in → gov.in).
    if any(host == tld[1:] or host.endswith(tld) for tld in _AUTH_TLDS):
        return AUTHORITATIVE
    for domain in _AUTH_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return AUTHORITATIVE
    return UNKNOWN
