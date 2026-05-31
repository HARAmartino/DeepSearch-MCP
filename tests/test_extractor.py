"""
Phase 1 Gauntlet Tests — 10 site-category HTML fixtures → eval_judge scoring.
(5 original + 5 added in B3: forum Q&A, academic, government, press, e-commerce.)
Phase 4 Edge Cases — UNSUPPORTED_FORMAT detection for non-HTML URLs/content-types.

Gate condition (ROADMAP Phase 1): average eval_judge score > 8.5/10 across all categories.
Tests also verify specific structural properties per category.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from evals.eval_judge import score_markdown
from src.deepsearch_mcp.core import errors as err
from src.deepsearch_mcp.core.extractor import build_frontmatter, extract
from src.deepsearch_mcp.tools.extractor import (
    _is_non_html_content_type,
    _is_non_html_url,
    read_article,
)

# ---------------------------------------------------------------------------
# HTML Fixtures — one per site category
# ---------------------------------------------------------------------------

NEWS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Central Bank Raises Interest Rates by 0.5% Amid Inflation Concerns</title>
<meta name="author" content="Sarah Chen">
<meta property="article:published_time" content="2024-03-15">
</head>
<body>
<nav>Home | Business | Politics | Sports | Entertainment | Subscribe | Log in</nav>
<header><a href="/">The Daily Tribune</a> | <a href="/subscribe">Subscribe now</a></header>
<main>
<article>
  <h1>Central Bank Raises Interest Rates by 0.5% Amid Inflation Concerns</h1>
  <time datetime="2024-03-15">March 15, 2024</time>
  <p class="byline">By Sarah Chen, Economics Correspondent</p>

  <p>The central bank announced a 0.5 percentage point increase in its benchmark
  interest rate on Thursday, the third consecutive hike this year as policymakers
  battle persistent inflation that has remained above the 4% target for six months.</p>

  <p>Governor Michael Torres stated that the decision was unanimous among the
  nine-member monetary policy committee. "We remain committed to bringing inflation
  back to target," Torres said at a press conference following the announcement.</p>

  <h2>Market Reaction</h2>
  <p>Financial markets reacted swiftly to the news. The main stock index fell 1.2%
  in afternoon trading, while bond yields rose sharply across all maturities.
  The currency strengthened 0.8% against the dollar within minutes of the announcement.</p>

  <p>Analysts at several major investment banks revised their growth forecasts
  downward, citing the cumulative impact of tighter monetary conditions on
  consumer spending and business investment.</p>

  <h2>What Economists Say</h2>
  <p>The consensus among economists surveyed by the Tribune is that one more rate
  hike of 0.25% is likely before the bank pauses. However, the outlook depends
  heavily on upcoming CPI data due next month.</p>
</article>
</main>
<aside>
  <h3>Related Articles</h3>
  <ul>
    <li><a href="/story1">Inflation hits 5-year high in February</a></li>
    <li><a href="/story2">Housing market shows signs of cooling</a></li>
  </ul>
</aside>
<footer>
  © 2024 The Daily Tribune. All rights reserved. Privacy Policy | Terms of Use
  Share on Twitter | Share on Facebook | Subscribe to our newsletter
  Cookie Settings | Accept All Cookies
</footer>
</body></html>"""

BLOG_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>10 Python Performance Tips You Should Know in 2024</title></head>
<body>
<nav><a href="/">DevBytes Blog</a> | <a href="/about">About</a> | <a href="/archive">Archive</a></nav>
<div class="author-bio">
  <img src="/authors/jane.jpg" alt="Jane"> <strong>Jane Kowalski</strong>
  <p>Python enthusiast & open source contributor. Follow me on Twitter @janedev</p>
</div>
<article>
  <h1>10 Python Performance Tips You Should Know in 2024</h1>
  <p class="meta">Published: February 28, 2024 | 8 min read</p>

  <p>Python's flexibility comes with a performance cost, but many bottlenecks
  are avoidable with the right patterns. Here are ten tips distilled from
  profiling real production systems over the past year.</p>

  <h2>1. Use Local Variables in Hot Loops</h2>
  <p>Python's attribute lookup is expensive. Binding frequently accessed globals
  or module attributes to local names before a tight loop can yield 15–30%
  speedups in CPU-bound code.</p>

  <h2>2. Prefer list comprehensions over for-loops for simple transforms</h2>
  <p>List comprehensions are implemented in C and bypass the interpreter overhead
  of the LOAD_FAST/STORE_FAST bytecodes that appear in equivalent for-loops.</p>

  <h2>3. Use __slots__ for data-heavy classes</h2>
  <p>By declaring <code>__slots__</code> on a class, you eliminate the per-instance
  <code>__dict__</code>, reducing memory by 40–60% for classes with many instances.</p>

  <h2>4. Profile before optimizing</h2>
  <p>Always use <code>cProfile</code> or <code>py-spy</code> to identify the actual
  bottleneck before investing time in micro-optimizations. Premature optimization
  remains the root of all evil.</p>

  <h2>Conclusion</h2>
  <p>Performance optimization in Python is about understanding the interpreter's
  cost model. Measure first, optimize second, and always validate improvements
  with benchmarks that reflect real workloads.</p>
</article>
<div class="social-share">
  Share on Twitter | Share on LinkedIn | Share on Facebook
</div>
<div class="comments">
  <h3>12 Comments</h3>
  <p>Leave a comment below. Subscribe to our newsletter for weekly tips!</p>
</div>
<footer>
  Follow us on Twitter | All rights reserved © 2024 DevBytes
  Cookie Settings | Privacy Policy
</footer>
</body></html>"""

TECH_DOCS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>asyncio — Asynchronous I/O — Python 3.12 Documentation</title></head>
<body>
<nav id="sidebar">
  <ul>
    <li><a href="/library/">Library</a></li>
    <li><a href="/library/asyncio">asyncio</a></li>
    <li><a href="/library/asyncio-task">Coroutines and Tasks</a></li>
  </ul>
</nav>
<div class="body" role="main">
  <section id="asyncio-coroutine">
    <h1>Coroutines and Tasks</h1>

    <p>This section outlines high-level asyncio APIs to work with coroutines
    and Tasks. Coroutines declared with the <code>async</code>/<code>await</code>
    syntax are the preferred way to write asyncio applications.</p>

    <h2>Running an asyncio Program</h2>
    <p>Use <code>asyncio.run()</code> to execute a coroutine and return the result.
    This function always creates a new event loop and closes it at the end.</p>

    <pre><code class="language-python">import asyncio

async def main():
    print("Hello")
    await asyncio.sleep(1)
    print("World")

asyncio.run(main())
</code></pre>

    <h2>Awaitable Objects</h2>
    <p>An object is <em>awaitable</em> if it can be used in an <code>await</code>
    expression. Coroutines, Tasks, and Futures are all awaitable objects in asyncio.</p>

    <h2>Creating Tasks</h2>
    <p>Tasks are used to schedule coroutines to run concurrently.
    Use <code>asyncio.create_task()</code> to wrap a coroutine as a Task:</p>

    <pre><code class="language-python">async def fetch_data():
    await asyncio.sleep(2)
    return {"data": 42}

async def main():
    task = asyncio.create_task(fetch_data())
    result = await task
    print(result)
</code></pre>

    <h2>Gathering Multiple Tasks</h2>
    <p>Use <code>asyncio.gather()</code> to run multiple coroutines concurrently
    and collect their results:</p>

    <pre><code class="language-python">results = await asyncio.gather(
    fetch_data(),
    fetch_data(),
    fetch_data(),
)
</code></pre>

    <p>See also: <a href="/library/asyncio-sync">Synchronization Primitives</a>
    for coordinating multiple tasks.</p>
  </section>
</div>
<footer>
  © 2001–2024 Python Software Foundation | <a href="/license">License</a>
  Cookie Settings | Privacy Policy
</footer>
</body></html>"""

WIKI_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Photosynthesis - Wikipedia</title></head>
<body>
<div id="mw-navigation">
  <nav id="mw-head">
    <ul><li><a href="/wiki/Main_Page">Main page</a></li>
    <li><a href="/wiki/Special:Random">Random article</a></li>
    <li><a href="/wiki/Special:Search">Search</a></li>
    </ul>
  </nav>
</div>
<div id="content">
  <h1 id="firstHeading">Photosynthesis</h1>
  <div id="toc">
    <ul>
      <li><a href="#Overview">1 Overview</a></li>
      <li><a href="#Light_reactions">2 Light-dependent reactions</a></li>
      <li><a href="#Calvin_cycle">3 Calvin cycle</a></li>
      <li><a href="#Factors">4 Limiting factors</a></li>
    </ul>
  </div>
  <div id="mw-content-text">
    <p><b>Photosynthesis</b> is the process used by plants, algae, and some bacteria
    to convert light energy — usually from the sun — into chemical energy stored in
    glucose or other organic compounds. It is one of the most important biochemical
    processes on Earth, underpinning almost all food chains and oxygen production.</p>

    <h2 id="Overview">Overview</h2>
    <p>The overall equation for photosynthesis in plants can be summarized as:</p>
    <p>6CO₂ + 6H₂O + light energy → C₆H₁₂O₆ + 6O₂</p>

    <p>This reaction occurs in two main stages: the light-dependent reactions,
    which capture energy from sunlight, and the light-independent reactions
    (the Calvin cycle), which use that energy to fix carbon dioxide into sugars.</p>

    <h2 id="Light_reactions">Light-dependent Reactions</h2>
    <p>These reactions occur in the thylakoid membranes of chloroplasts. Chlorophyll
    and other pigments absorb photons, exciting electrons to a higher energy state.
    The captured energy drives the synthesis of ATP and NADPH, which power
    downstream reactions.</p>

    <h2 id="Calvin_cycle">The Calvin Cycle</h2>
    <p>Also known as the light-independent reactions or carbon fixation, the Calvin
    cycle takes place in the stroma of the chloroplast. It uses ATP and NADPH from
    the light reactions to convert CO₂ into glyceraldehyde-3-phosphate (G3P),
    a precursor to glucose and other organic molecules.</p>

    <h2 id="Factors">Limiting Factors</h2>
    <p>The rate of photosynthesis is influenced by light intensity, CO₂ concentration,
    temperature, and water availability. At low light intensities, the process is
    light-limited. At higher intensities, CO₂ concentration often becomes the
    limiting factor.</p>
  </div>
</div>
<div id="mw-panel">
  <div class="portal" id="p-navigation">
    <h3>Navigation</h3>
    <ul><li><a href="/wiki/Wikipedia:About">About Wikipedia</a></li>
    <li><a href="/wiki/Wikipedia:Community_portal">Community portal</a></li>
    </ul>
  </div>
</div>
<footer id="footer">
  This page was last edited on 10 March 2024. Text is available under the
  Creative Commons Attribution-ShareAlike License 4.0.
  Privacy Policy | About Wikipedia | Cookie Settings
</footer>
</body></html>"""

RECIPE_SEO_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>The Best Chocolate Chip Cookies Ever (My Grandmother's Secret Recipe)</title></head>
<body>
<nav>Home | Recipes | Desserts | Cookies | About Me | Subscribe</nav>
<article>
  <h1>The Best Chocolate Chip Cookies Ever (My Grandmother's Secret Recipe)</h1>
  <p class="meta">By Emma Wilson | Updated: March 1, 2024 | ⭐ 4.9 (2,341 reviews)</p>

  <div class="story">
    <p>Every year when I was a child, my grandmother would bake these incredible
    chocolate chip cookies for our family reunion in Vermont. The smell of butter
    and vanilla would fill the entire house from the moment we arrived. I remember
    sitting on the kitchen counter watching her hands move with such confidence,
    measuring ingredients by feel rather than by cup.</p>

    <p>She passed away in 2015, but her recipe card lives on in my recipe box,
    stained with chocolate and decades of love. After years of testing and tweaking
    to adapt it to modern ovens, I'm finally ready to share it with the world.</p>

    <p>Before I get to the recipe, I just want to say — if you're here for the
    quick version, scroll down. But I hope you'll read this first because understanding
    the "why" behind each step makes you a better baker.</p>
  </div>

  <h2>Why These Cookies Are Different</h2>
  <p>The secret is browned butter. Instead of using softened butter, we brown it
  first to develop deep nutty, caramel notes that transform an ordinary cookie into
  something extraordinary. Combined with a higher ratio of brown sugar to white
  sugar, you get cookies with crispy edges and chewy centers every time.</p>

  <h2>Ingredients</h2>
  <ul>
    <li>225g (2 sticks) unsalted butter</li>
    <li>200g (1 cup) brown sugar, packed</li>
    <li>100g (½ cup) granulated white sugar</li>
    <li>2 large eggs + 1 egg yolk</li>
    <li>2 tsp pure vanilla extract</li>
    <li>280g (2¼ cups) all-purpose flour</li>
    <li>1 tsp baking soda</li>
    <li>1 tsp fine sea salt</li>
    <li>300g (2 cups) semi-sweet chocolate chips</li>
  </ul>

  <h2>Instructions</h2>
  <ol>
    <li>Brown the butter in a light-colored pan over medium heat, swirling
    frequently, until golden and nutty-smelling, about 5–7 minutes. Pour into
    a large mixing bowl and let cool for 10 minutes.</li>
    <li>Whisk in both sugars until combined. Add eggs, egg yolk, and vanilla;
    whisk vigorously for 60 seconds until the mixture lightens in color.</li>
    <li>Fold in flour, baking soda, and salt with a rubber spatula until just
    combined. Fold in chocolate chips.</li>
    <li>Chill the dough for at least 30 minutes (or overnight for best results).</li>
    <li>Preheat oven to 375°F (190°C). Scoop dough into 50g balls, space 2 inches
    apart on a lined baking sheet.</li>
    <li>Bake 11–13 minutes until edges are golden but centers still look slightly
    underdone. Cool on the pan for 5 minutes before transferring.</li>
  </ol>

  <h2>Storage and Make-Ahead Tips</h2>
  <p>Baked cookies keep at room temperature for up to 5 days in an airtight
  container. Cookie dough balls can be frozen for up to 3 months — bake directly
  from frozen, adding 2–3 extra minutes.</p>
</article>
<div class="cta">
  Subscribe to our newsletter for weekly recipes!
  Share on Pinterest | Share on Instagram | Share on Facebook
  Follow us on social media @emmabakes
</div>
<footer>
  © 2024 Emma's Kitchen. All rights reserved.
  Privacy Policy | Terms of Use | Cookie Settings
</footer>
</body></html>"""


# ---------------------------------------------------------------------------
# B3: 5 additional site categories (corpus 5 → 10). Real research surfaces the
# original gauntlet didn't cover: forum Q&A, academic preprint, government
# notice, corporate press release, e-commerce product. Each carries realistic
# 2026-era chrome (vote rails, cite boxes, datelines, add-to-cart) so the gate
# protects extraction across far more of the web the agent actually reads.
# ---------------------------------------------------------------------------

FORUM_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>How do I merge two dictionaries in Python? - Stack Overflow</title>
<meta name="author" content="community wiki"></head>
<body>
<header><nav>Stack Overflow | Questions | Tags | Users | Find a Job | Teams</nav></header>
<div id="question">
  <h1>How do I merge two dictionaries in a single expression in Python?</h1>
  <div class="post-meta">Asked 12 years ago · Modified 2 months ago · Viewed 3.1m times</div>
  <article class="answer">
    <p>For two dictionaries, on Python 3.9 and later you can merge them with the union
    operator. It returns a brand-new dictionary and leaves both operands completely
    unchanged, which is usually what callers want when they say "merge":</p>
    <pre><code class="language-python">x = {"a": 1, "b": 2}
y = {"b": 3, "c": 4}
z = x | y
# z is now {"a": 1, "b": 3, "c": 4}</code></pre>
    <p>On Python 3.5 through 3.8 you can use dictionary unpacking inside a literal instead.
    Keys from the right-hand mapping win on collision, exactly as with the union operator
    above, so the behaviour stays consistent across all of these versions:</p>
    <pre><code class="language-python">z = {**x, **y}
# keys from y win on collision, same as x | y</code></pre>
    <p>Both approaches create a shallow copy of the data. If a key exists in both mappings,
    the value from the second operand is kept, which is the behaviour most callers expect
    when they talk about merging two dictionaries together into a new one.</p>
    <h2>Why not use update()?</h2>
    <p>The update method mutates the left-hand dictionary in place and returns nothing, so
    it cannot be used inside an expression and it destroys the original mapping. Prefer the
    operators above whenever you need a new mapping with no side effects on the inputs.</p>
  </article>
  <div class="post-actions">Share Improve this answer Follow edited Jun 2 at 14:00</div>
</div>
<aside class="sidebar">
  Related: 38 ways to iterate a list
  Hot Network Questions
  Sign up using Google
</aside>
<footer>Stack Overflow © 2026. Cookie Settings | Privacy Policy | Terms of Service</footer>
</body></html>"""

ACADEMIC_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Attention Sinks in Long-Context Transformers - arXiv</title>
<meta name="author" content="A. Researcher, B. Scientist"></head>
<body>
<nav>arXiv | cs.CL | Search | Login | Help</nav>
<main>
  <h1>Attention Sinks in Long-Context Transformers</h1>
  <div class="authors">A. Researcher, B. Scientist, C. Engineer</div>
  <h2>Abstract</h2>
  <p>We study the phenomenon of attention sinks, where transformer language models allocate
  disproportionate attention mass to the first few tokens of a sequence regardless of their
  semantic content. We show that this behaviour emerges early in training and acts as a
  default destination for attention when no strongly relevant token is present. Removing the
  sink tokens at inference time degrades long-context performance sharply.</p>
  <h2>1. Introduction</h2>
  <p>Long-context inference has become central to retrieval-augmented and agentic systems.
  Prior work observed that streaming attention degrades when early tokens are evicted from
  the key-value cache. We attribute this to learned attention sinks and propose a lightweight
  remedy that preserves a small fixed prefix of cached keys throughout generation.</p>
  <h2>2. Method</h2>
  <p>Our approach retains the first four token positions in the cache at all times,
  independent of the sliding window. This adds negligible memory overhead while recovering
  most of the accuracy lost to naive eviction across documents up to one million tokens in
  length, as we demonstrate in the experiments that follow.</p>
</main>
<div class="cite-box">Cite (BibTeX) | Download PDF | Submission history</div>
<footer>Which authors of this paper are endorsers? | © 2026 arXiv. Privacy Policy</footer>
</body></html>"""

GOV_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Spectrum Reallocation for Rural Broadband: Policy Statement</title>
<meta name="author" content="Federal Communications Office"></head>
<body>
<nav>Home › Policy › Broadband › Spectrum Reallocation</nav>
<header>Federal Communications Office — Official Notice</header>
<main>
  <h1>Spectrum Reallocation for Rural Broadband: Policy Statement</h1>
  <p>The Office today issued a policy statement setting out how the 600 MHz band will be
  reallocated to expand fixed-wireless broadband access in underserved rural areas. The
  statement follows an eighteen-month consultation with carriers, equipment vendors, and
  regional authorities, and takes effect at the start of the next licensing period.</p>
  <h2>Background</h2>
  <p>Rural communities relying on shared community-reception facilities have faced declining
  service quality as legacy equipment ages. The reallocation prioritises geographic licences
  for operators that commit to coverage obligations rather than population-weighted targets,
  which historically left the lowest-density areas effectively unserved.</p>
  <h2>Obligations for Licensees</h2>
  <p>Successful applicants must reach ninety percent of households within the designated
  service contour within three years, publish coverage maps each quarter, and offer a
  regulated wholesale rate to smaller resellers. Failure to meet these milestones may result
  in licence revocation and reassignment to a competing applicant.</p>
  <h2>Next Steps</h2>
  <p>A draft licensing framework will be published for public comment, after which final
  rules are expected before the end of the fiscal year. Interested parties may submit written
  responses through the consultation portal linked above.</p>
</main>
<aside>Related notices | Subscribe to our newsletter for policy updates</aside>
<footer>Contact us | © 2026 Federal Communications Office. All rights reserved.</footer>
</body></html>"""

PRESS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Acme Robotics Announces General Availability of Atlas-2 Platform</title>
<meta name="author" content="Acme Robotics Communications"></head>
<body>
<nav>Newsroom | Investors | Products | Careers | Contact</nav>
<main>
  <h1>Acme Robotics Announces General Availability of Atlas-2 Platform</h1>
  <p>SAN JOSE, Calif., May 31, 2026 — Acme Robotics today announced the general availability
  of Atlas-2, its second-generation warehouse automation platform, following a nine-month
  pilot with logistics customers across three continents.</p>
  <p>Atlas-2 introduces on-device perception that lets autonomous units re-plan routes around
  unexpected obstacles without contacting a central server, cutting average pick latency by a
  claimed forty percent compared with the previous generation of the platform.</p>
  <h2>Availability and Pricing</h2>
  <p>The platform is available immediately in North America and Europe, with Asia-Pacific
  availability to follow in the third quarter. Acme is offering existing customers a trade-in
  credit toward fleet upgrades through the end of the calendar year.</p>
  <h2>About Acme Robotics</h2>
  <p>Acme Robotics designs and manufactures autonomous material-handling systems for
  warehouses and distribution centres. Founded in 2014, the company operates in twelve
  countries and is headquartered in San Jose, California.</p>
  <p>This press release contains forward-looking statements that involve risks and
  uncertainties. Actual results may differ materially from those expressed or implied here.</p>
</main>
<div class="cta">Media Contact: press@example.com | Follow us on LinkedIn</div>
<footer>© 2026 Acme Robotics. All rights reserved. Privacy Policy | Terms of Use</footer>
</body></html>"""

ECOMMERCE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>TrailLight 800 Rechargeable Headlamp - OutdoorGear</title>
<meta name="author" content="OutdoorGear"></head>
<body>
<header><nav>Home | Camping | Lighting | Cart (0) | Sign in</nav></header>
<main>
  <h1>TrailLight 800 Rechargeable Headlamp</h1>
  <div class="purchase">$49.99 · In stock · Add to Cart · Free shipping over $35</div>
  <div class="rating">4.6 out of 5 · 1,284 ratings</div>
  <h2>Product Description</h2>
  <p>The TrailLight 800 is a USB-C rechargeable headlamp aimed at trail runners and overnight
  hikers who need reliable hands-free lighting without carrying spare batteries. Its 800-lumen
  peak output is bright enough to pick out trail markers at distance, while a regulated low
  mode sustains forty hours of usable light on a single charge.</p>
  <p>A tilting housing directs the beam where you look, and the rear battery pack balances the
  weight so the strap does not slip during running. The body is rated IPX7, meaning it
  survives sustained rain and brief submersion, though it is not intended for diving.</p>
  <h2>Specifications</h2>
  <ul>
    <li>Peak output: 800 lumens; regulated low mode: 25 lumens for 40 hours</li>
    <li>Battery: 2000 mAh lithium-ion, USB-C charging in roughly two hours</li>
    <li>Weight: 98 grams including the battery and elastic strap</li>
    <li>Water resistance: IPX7 (sustained rain and brief submersion)</li>
  </ul>
  <h2>What's in the Box</h2>
  <p>The headlamp ships with the lamp unit, an elastic head strap, a USB-C charging cable, and
  a printed quick-start guide. A two-year limited warranty covers manufacturing defects but
  excludes damage from improper charging or disassembly.</p>
</main>
<aside>Customers also bought: TrailLight 400 · Spare battery pack</aside>
<footer>© 2026 OutdoorGear. Returns | Privacy Policy | Cookie Settings</footer>
</body></html>"""


# ---------------------------------------------------------------------------
# Gauntlet: extract + score all 10 categories
# ---------------------------------------------------------------------------

GAUNTLET_FIXTURES = [
    ("News", NEWS_HTML, "https://example.com/news/interest-rates"),
    ("Blog", BLOG_HTML, "https://devbytes.example.com/python-tips"),
    ("Tech Docs", TECH_DOCS_HTML, "https://docs.python.org/3/library/asyncio-task.html"),
    ("Wiki", WIKI_HTML, "https://en.wikipedia.org/wiki/Photosynthesis"),
    ("Recipe/SEO", RECIPE_SEO_HTML, "https://emmaskitchen.example.com/chocolate-chip-cookies"),
    # B3 — additional categories (5 → 10)
    ("Forum/Q&A", FORUM_HTML, "https://stackoverflow.com/questions/38987/merge-dicts"),
    ("Academic", ACADEMIC_HTML, "https://arxiv.org/abs/2605.01234"),
    ("Government", GOV_HTML, "https://fco.example.gov/policy/spectrum-reallocation"),
    ("Press Release", PRESS_HTML, "https://acme.example.com/newsroom/atlas-2-ga"),
    ("E-commerce", ECOMMERCE_HTML, "https://outdoorgear.example.com/traillight-800"),
]

GATE_THRESHOLD = 8.5
PER_CATEGORY_MIN = 7.0  # Individual category floor (avg must hit 8.5)


class TestGauntletScores:
    """Verify eval_judge scores on all 5 site categories."""

    def _extract_and_score(self, html: str, url: str) -> tuple[str, object]:
        body, meta = extract(html, url=url)
        frontmatter = build_frontmatter(meta)
        full = f"{frontmatter}\n\n{body}"
        score = score_markdown(full)
        return full, score

    def test_news_score(self):
        full, score = self._extract_and_score(NEWS_HTML, GAUNTLET_FIXTURES[0][2])
        print(f"\nNews: {score.total}/10 | {score.details}")
        assert score.total >= PER_CATEGORY_MIN, (
            f"News score {score.total} < {PER_CATEGORY_MIN}\n{full[:500]}"
        )

    def test_blog_score(self):
        full, score = self._extract_and_score(BLOG_HTML, GAUNTLET_FIXTURES[1][2])
        print(f"\nBlog: {score.total}/10 | {score.details}")
        assert score.total >= PER_CATEGORY_MIN, (
            f"Blog score {score.total} < {PER_CATEGORY_MIN}\n{full[:500]}"
        )

    def test_tech_docs_score(self):
        full, score = self._extract_and_score(TECH_DOCS_HTML, GAUNTLET_FIXTURES[2][2])
        print(f"\nTech Docs: {score.total}/10 | {score.details}")
        assert score.total >= PER_CATEGORY_MIN, (
            f"Tech Docs score {score.total} < {PER_CATEGORY_MIN}\n{full[:500]}"
        )

    def test_wiki_score(self):
        full, score = self._extract_and_score(WIKI_HTML, GAUNTLET_FIXTURES[3][2])
        print(f"\nWiki: {score.total}/10 | {score.details}")
        assert score.total >= PER_CATEGORY_MIN, (
            f"Wiki score {score.total} < {PER_CATEGORY_MIN}\n{full[:500]}"
        )

    def test_recipe_seo_score(self):
        full, score = self._extract_and_score(RECIPE_SEO_HTML, GAUNTLET_FIXTURES[4][2])
        print(f"\nRecipe/SEO: {score.total}/10 | {score.details}")
        assert score.total >= PER_CATEGORY_MIN, (
            f"Recipe/SEO score {score.total} < {PER_CATEGORY_MIN}\n{full[:500]}"
        )

    def test_new_categories_meet_floor(self):
        # B3: every added category (index 5+) must clear the per-category floor.
        for name, html, url in GAUNTLET_FIXTURES[5:]:
            full, score = self._extract_and_score(html, url)
            print(f"\n{name}: {score.total}/10 | {score.details}")
            assert score.total >= PER_CATEGORY_MIN, (
                f"{name} score {score.total} < {PER_CATEGORY_MIN}\n{full[:500]}"
            )

    def test_corpus_has_at_least_ten_categories(self):
        # B3 acceptance: the adversarial corpus expanded from 5 to 10+.
        assert len(GAUNTLET_FIXTURES) >= 10

    def test_gauntlet_average_meets_gate(self):
        scores = []
        for name, html, url in GAUNTLET_FIXTURES:
            full, score = self._extract_and_score(html, url)
            scores.append(score.total)
            print(f"  {name}: {score.total}/10 | {score.details}")

        avg = sum(scores) / len(scores)
        print(f"\n  AVERAGE: {avg:.2f}/10 (gate: {GATE_THRESHOLD})")
        assert avg >= GATE_THRESHOLD, (
            f"Gauntlet average {avg:.2f} < gate {GATE_THRESHOLD}\n"
            f"Scores: {dict(zip([f[0] for f in GAUNTLET_FIXTURES], scores))}"
        )


class TestTechDocsCodeBlocks:
    """Tech Docs category: verify code block language annotations are preserved."""

    def test_python_code_blocks_have_language(self):
        body, _ = extract(TECH_DOCS_HTML, url="https://docs.python.org/3/library/asyncio-task.html")
        assert "```python" in body, (
            f"Expected ```python in Tech Docs output, got:\n{body[:800]}"
        )

    def test_multiple_code_blocks_annotated(self):
        body, _ = extract(TECH_DOCS_HTML, url="https://docs.python.org/3/library/asyncio-task.html")
        count = body.count("```python")
        assert count >= 2, f"Expected ≥2 ```python blocks, got {count}\n{body[:800]}"

    def test_no_duplicate_content(self):
        body, _ = extract(TECH_DOCS_HTML, url="https://docs.python.org/3/library/asyncio-task.html")
        # The phrase "asyncio.run(main())" should appear exactly once after dedup
        count = body.count("asyncio.run(main())")
        assert count == 1, (
            f"Content duplicated: 'asyncio.run(main())' appears {count} times\n{body}"
        )


class TestMetadataExtraction:
    """Verify metadata extraction from different HTML patterns."""

    def test_news_metadata_title(self):
        _, meta = extract(NEWS_HTML, url="https://example.com/news/interest-rates")
        assert "Central Bank" in meta["title"] or meta["title"] != ""

    def test_news_metadata_date_is_iso8601(self):
        _, meta = extract(NEWS_HTML, url="https://example.com/news/interest-rates")
        if meta["published_date"]:
            assert meta["published_date"] == "2024-03-15", meta["published_date"]

    def test_hostname_extracted(self):
        _, meta = extract(NEWS_HTML, url="https://example.com/news/interest-rates")
        assert meta["hostname"] == "example.com"


class TestCleanerNoNoise:
    """Verify that noise artifacts do not leak into extraction output."""

    def _get_body(self, html: str, url: str) -> str:
        body, _ = extract(html, url=url)
        return body.lower()

    def test_no_cookie_settings_in_news(self):
        body = self._get_body(NEWS_HTML, "https://example.com/news")
        assert "cookie settings" not in body, "Cookie Settings leaked into output"

    def test_no_subscribe_in_recipe(self):
        body = self._get_body(RECIPE_SEO_HTML, "https://example.com/recipe")
        assert "subscribe to our newsletter" not in body

    def test_no_share_buttons_in_blog(self):
        body = self._get_body(BLOG_HTML, "https://devbytes.example.com/tips")
        assert "share on twitter" not in body


class TestExtractionEdgeCases:
    """Unit-level tests for extractor helpers."""

    def test_empty_html_returns_empty(self):
        body, _ = extract("<html><body></body></html>", url="https://x.com")
        assert body == ""

    def test_frontmatter_format(self):
        _, meta = extract(NEWS_HTML, url="https://example.com/news/interest-rates")
        fm = build_frontmatter(meta)
        assert fm.startswith("---")
        assert fm.endswith("---")
        assert "url:" in fm

    def test_content_truncation_at_limit(self):
        # Build a very long article
        huge_html = (
            "<html><body><article><h1>Long Article</h1>"
            + "<p>" + "A" * 100 + "</p>\n" * 300
            + "</article></body></html>"
        )
        body, _ = extract(huge_html, url="https://example.com/long")
        assert len(body) <= 16_500, f"Content not truncated: {len(body)} chars"
        if len(body) >= 16_000:
            assert "truncated" in body.lower()


# ---------------------------------------------------------------------------
# Phase 4: UNSUPPORTED_FORMAT — non-HTML detection
# ---------------------------------------------------------------------------

class TestIsNonHtmlUrl:
    """Unit tests for URL extension detection helper."""

    def test_pdf_extension_detected(self):
        assert _is_non_html_url("https://example.com/report.pdf") is True

    def test_zip_extension_detected(self):
        assert _is_non_html_url("https://example.com/archive.zip") is True

    def test_jpg_extension_detected(self):
        assert _is_non_html_url("https://example.com/photo.jpg") is True

    def test_png_extension_detected(self):
        assert _is_non_html_url("https://cdn.example.com/logo.png") is True

    def test_docx_extension_detected(self):
        assert _is_non_html_url("https://files.example.com/doc.docx") is True

    def test_mp4_extension_detected(self):
        assert _is_non_html_url("https://video.example.com/clip.mp4") is True

    def test_html_url_not_detected(self):
        assert _is_non_html_url("https://example.com/article.html") is False

    def test_plain_path_url_not_detected(self):
        assert _is_non_html_url("https://example.com/news/2026/my-article") is False

    def test_uppercase_extension_detected(self):
        assert _is_non_html_url("https://example.com/report.PDF") is True

    def test_pdf_with_query_string_detected(self):
        assert _is_non_html_url("https://example.com/report.pdf?download=1") is True

    def test_empty_url_returns_false(self):
        assert _is_non_html_url("") is False


class TestIsNonHtmlContentType:
    """Unit tests for Content-Type header detection helper."""

    def test_pdf_content_type(self):
        assert _is_non_html_content_type("application/pdf") is True

    def test_pdf_with_charset(self):
        assert _is_non_html_content_type("application/pdf; charset=utf-8") is True

    def test_zip_content_type(self):
        assert _is_non_html_content_type("application/zip") is True

    def test_octet_stream(self):
        assert _is_non_html_content_type("application/octet-stream") is True

    def test_image_jpeg(self):
        assert _is_non_html_content_type("image/jpeg") is True

    def test_image_png(self):
        assert _is_non_html_content_type("image/png") is True

    def test_video_mp4(self):
        assert _is_non_html_content_type("video/mp4") is True

    def test_audio_mpeg(self):
        assert _is_non_html_content_type("audio/mpeg") is True

    def test_vnd_msword(self):
        assert _is_non_html_content_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document") is True

    def test_text_html_not_detected(self):
        assert _is_non_html_content_type("text/html; charset=utf-8") is False

    def test_text_plain_not_detected(self):
        assert _is_non_html_content_type("text/plain") is False

    def test_empty_string_not_detected(self):
        assert _is_non_html_content_type("") is False


class TestReadArticleUnsupportedFormat:
    """Integration tests for UNSUPPORTED_FORMAT errors in read_article."""

    async def test_pdf_url_returns_unsupported_format_no_fetch(self):
        """PDF URL must be rejected before any network call."""
        with patch("src.deepsearch_mcp.tools.extractor.fetch", new_callable=AsyncMock) as mock_fetch:
            result = await read_article(url="https://example.com/report.pdf")
            mock_fetch.assert_not_called()

        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == err.UNSUPPORTED_FORMAT
        assert data["retryable"] is False
        assert "skip" in data["hint"].lower() or "non-html" in data["hint"].lower()

    async def test_zip_url_returns_unsupported_format(self):
        with patch("src.deepsearch_mcp.tools.extractor.fetch", new_callable=AsyncMock) as mock_fetch:
            result = await read_article(url="https://example.com/files.zip")
            mock_fetch.assert_not_called()
        data = json.loads(result)
        assert data["code"] == err.UNSUPPORTED_FORMAT

    async def test_image_url_returns_unsupported_format(self):
        with patch("src.deepsearch_mcp.tools.extractor.fetch", new_callable=AsyncMock) as mock_fetch:
            result = await read_article(url="https://cdn.example.com/hero.jpg")
            mock_fetch.assert_not_called()
        data = json.loads(result)
        assert data["code"] == err.UNSUPPORTED_FORMAT

    async def test_pdf_content_type_returns_unsupported_format(self):
        """Server returns text/html URL but Content-Type is application/pdf."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = b"%PDF-1.4 binary content"
        mock_resp.headers = {"content-type": "application/pdf"}

        with patch("src.deepsearch_mcp.tools.extractor.fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            result = await read_article(url="https://example.com/disguised-pdf")

        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == err.UNSUPPORTED_FORMAT

    async def test_image_content_type_returns_unsupported_format(self):
        """URL has no extension but server responds with image/png."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = b"\x89PNG binary"
        mock_resp.headers = {"content-type": "image/png"}

        with patch("src.deepsearch_mcp.tools.extractor.fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            result = await read_article(url="https://example.com/logo")

        data = json.loads(result)
        assert data["code"] == err.UNSUPPORTED_FORMAT

    async def test_html_url_proceeds_normally(self):
        """Normal HTML URL must NOT trigger unsupported format detection."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = NEWS_HTML
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}

        with patch("src.deepsearch_mcp.tools.extractor.fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            result = await read_article(url="https://example.com/news/story")

        # Should NOT be an UNSUPPORTED_FORMAT error
        try:
            data = json.loads(result)
            assert data.get("code") != err.UNSUPPORTED_FORMAT
        except json.JSONDecodeError:
            pass  # Non-JSON means it returned article markdown (also fine)

    async def test_unsupported_format_hint_is_actionable(self):
        """The hint must tell the agent to search for HTML alternatives."""
        with patch("src.deepsearch_mcp.tools.extractor.fetch", new_callable=AsyncMock):
            result = await read_article(url="https://example.com/deck.pptx")
        data = json.loads(result)
        hint_lower = data["hint"].lower()
        assert any(kw in hint_lower for kw in ["html", "skip", "search", "alternative"]), (
            f"Hint lacks actionable advice: {data['hint']}"
        )


# ---------------------------------------------------------------------------
# Phase 5 Regression: H1 deduplication (FRICTION-D1)
# When frontmatter `title:` and body `# H1` are the same, strip the H1
# to save tokens. The article still has a hierarchical structure thanks
# to the title in frontmatter.
# ---------------------------------------------------------------------------

class TestH1Deduplication:
    """Regression for FRICTION-D1: redundant H1 must be stripped from body."""

    def _build_html(self, title: str) -> str:
        return f"""<!DOCTYPE html>
<html><head>
<title>{title}</title>
<meta property="article:published_time" content="2026-04-01">
</head><body>
<article>
<h1>{title}</h1>
<p class="byline">By Test Author</p>
<p>The first paragraph contains substantive content that the LLM should reason
about. It introduces the topic and frames the analysis that follows in the
later sections of the article.</p>
<h2>Background</h2>
<p>Substantive background paragraph explaining the topic in enough detail
that an agent can understand the prior art and motivation.</p>
<h2>Analysis</h2>
<p>More substantive content that takes a few sentences to develop the
main argument of the article in a meaningful way.</p>
</article>
</body></html>"""

    def test_exact_title_h1_is_stripped(self):
        html = self._build_html("RAG vs Long-Term Memory: The Debate")
        body, meta = extract(html, url="https://example.com/article")
        assert meta["title"]  # title extracted into frontmatter
        # The H1 should be gone from body
        assert "# RAG vs Long-Term Memory: The Debate" not in body, (
            f"H1 matching title was not stripped:\n{body[:400]}"
        )
        # But H2s remain
        assert "## Background" in body or "## Analysis" in body

    def test_h1_stripped_only_at_top(self):
        """A later H1 deeper in body must NOT be stripped (only the leading one)."""
        title = "Article Title"
        html = f"""<!DOCTYPE html><html><head><title>{title}</title></head><body><article>
<h1>{title}</h1>
<p>First section paragraph with enough content to be meaningful.</p>
<h2>Section</h2>
<p>Another paragraph.</p>
<h1>Different Later H1</h1>
<p>Another long paragraph after the second H1.</p>
</article></body></html>"""
        body, _ = extract(html, url="https://example.com/x")
        # Leading title H1 stripped
        assert "# Article Title" not in body
        # Deeper unrelated H1 preserved
        assert "Different Later H1" in body

    def test_h1_not_stripped_when_different(self):
        """If H1 differs meaningfully from title, keep it (unit test on helper)."""
        from src.deepsearch_mcp.core.extractor import _strip_redundant_h1

        markdown = (
            "# Section Heading Specific To Body\n\n"
            "Substantive paragraph one with meaningful content.\n\n"
            "## Subsection\n\n"
            "More paragraphs."
        )
        frontmatter_title = "Completely Unrelated Article Metadata Title"
        result = _strip_redundant_h1(markdown, frontmatter_title)
        # Heading should remain because it does not match the title
        assert "# Section Heading Specific To Body" in result

    def test_h1_stripped_case_insensitive(self):
        """Title-vs-H1 comparison ignores case differences."""
        html = """<!DOCTYPE html><html><head>
<title>ASYNCIO COROUTINES AND TASKS</title>
</head><body><article>
<h1>asyncio coroutines and tasks</h1>
<p>Substantive intro paragraph about asyncio and how it works in Python.</p>
<h2>Subsection</h2>
<p>Another substantive paragraph adding more detail to the discussion.</p>
</article></body></html>"""
        body, _ = extract(html, url="https://example.com/docs")
        assert "# asyncio coroutines and tasks" not in body.lower().split("##")[0]

    def test_h1_strip_does_not_break_short_articles(self):
        """Even after H1 strip, body should not be empty for short articles."""
        html = self._build_html("Short")
        body, _ = extract(html, url="https://example.com/short")
        # Content should still be present
        assert "substantive" in body.lower() or "Background" in body


# ---------------------------------------------------------------------------
# Phase 6: Domain adapters — automated PDCA patch
# Telemetry analysis flagged substack.com at 38% EMPTY_CONTENT and medium.com
# at 27% BLOCKED_403. Adapters strip subscription/paywall noise before
# trafilatura sees the HTML.
# ---------------------------------------------------------------------------

_SUBSTACK_HTML = """<!DOCTYPE html>
<html><head>
<title>The Memory Wars: RAG vs Long-Term Memory in 2026</title>
<meta name="author" content="Sample Author">
<meta property="article:published_time" content="2026-04-15">
</head><body>
<article>
<h1>The Memory Wars: RAG vs Long-Term Memory in 2026</h1>
<p class="byline">By Sample Author · Apr 15, 2026</p>

<div class="subscription-widget-wrap" data-component-name="SubscribeWidget">
  <h2>Subscribe to our newsletter</h2>
  <p>Get the latest essays delivered to your inbox.</p>
  <form class="subscribe-form">
    <input type="email" placeholder="your@email.com">
    <button>Subscribe</button>
  </form>
  <p>Join 50,000+ readers from leading AI labs.</p>
</div>

<p>The fundamental question of how AI agents should retain information has emerged as the central
architectural debate of 2026. While Retrieval-Augmented Generation (RAG) dominated 2023-2024,
long-term memory architectures are now reshaping how we build agentic systems.</p>

<h2>The RAG Approach</h2>
<p>RAG retrieves relevant chunks from a vector database at inference time. It is simple, scalable,
and works with any LLM. However, retrieval quality degrades sharply when context spans dozens of
related documents that require synthesis rather than lookup.</p>

<div class="subscribe-dialog">
  <h3>Enjoying this post?</h3>
  <p>Subscribe for free to receive new posts.</p>
  <button>Subscribe now</button>
</div>

<h2>The Long-Term Memory Approach</h2>
<p>Long-term memory systems like MemGPT and Letta maintain persistent state across sessions. They
excel at multi-turn reasoning but require careful management of memory budgets and eviction
policies to prevent unbounded context growth.</p>

<h2>Hybrid is Winning</h2>
<p>Most practitioners in 2026 now combine both approaches: RAG for breadth-first lookup over
large corpora, long-term memory for continuity within a session. Pure RAG is increasingly seen
as a 2023-era pattern that the field has moved beyond.</p>

<div class="post-footer">
  <p>Subscribe to our newsletter for weekly AI essays. Share on Twitter, LinkedIn, Facebook.</p>
  <button>Subscribe</button>
</div>

<div class="comments-wrapper">
  <h3>Comments (47)</h3>
  <p>Subscribe to leave a comment.</p>
</div>
</article>
</body></html>"""


class TestSubstackAdapter:
    """Regression for Phase 6 Act-phase patch: substack.com EMPTY_CONTENT fix."""

    def test_substack_subscription_widget_stripped(self):
        body, meta = extract(_SUBSTACK_HTML, url="https://author.substack.com/p/memory-wars")
        # The substantive content should be present
        assert "RAG" in body
        assert "Long-Term Memory" in body or "Long-term Memory" in body
        # Subscription noise should be GONE
        assert "Join 50,000+ readers" not in body
        assert "your@email.com" not in body
        assert "Subscribe to leave a comment" not in body

    def test_substack_extraction_yields_substantial_content(self):
        """The whole point of the adapter: body must not be empty (was EMPTY_CONTENT before)."""
        body, _ = extract(_SUBSTACK_HTML, url="https://author.substack.com/p/x")
        # Real prose should account for the majority — at least 600 chars of meaningful body
        assert len(body) >= 600, (
            f"Substack body too short after adapter: {len(body)} chars\n{body[:500]}"
        )

    def test_substack_subdomain_match(self):
        """`fooauthor.substack.com` (subdomain) must match the same adapter."""
        body, _ = extract(_SUBSTACK_HTML, url="https://platformer.substack.com/p/test")
        assert "your@email.com" not in body  # adapter ran

    def test_substack_base_domain_match(self):
        """`substack.com` exact host must match."""
        body, _ = extract(_SUBSTACK_HTML, url="https://substack.com/p/test")
        assert "your@email.com" not in body

    def test_non_substack_unaffected(self):
        """Adapter must not touch unrelated domains."""
        from src.deepsearch_mcp.core.extractor import _apply_domain_adapter
        sample = "<div class='subscription-widget-wrap'>spam</div><p>real</p>"
        # The "subscription-widget-wrap" class string should survive on non-substack
        result = _apply_domain_adapter(sample, "https://example.com/x")
        assert sample == result, "Non-substack domain triggered adapter"

    def test_unknown_domain_passthrough(self):
        """Domains without an adapter return HTML unmodified."""
        from src.deepsearch_mcp.core.extractor import _apply_domain_adapter
        html = "<html><body><p>hello</p></body></html>"
        assert _apply_domain_adapter(html, "https://random.example.org/") == html

    def test_empty_url_returns_html_unmodified(self):
        from src.deepsearch_mcp.core.extractor import _apply_domain_adapter
        html = "<p>x</p>"
        assert _apply_domain_adapter(html, "") == html

    def test_substack_quality_score_meets_threshold(self):
        """Post-adapter substack extraction should score reasonably on eval_judge."""
        from evals.eval_judge import score_markdown
        body, meta = extract(_SUBSTACK_HTML, url="https://author.substack.com/p/x")
        full = build_frontmatter(meta) + "\n\n" + body
        score = score_markdown(full)
        # Phase 6 quality bar for adapter output
        assert score.total >= 7.0, (
            f"Substack adapter output too low quality: {score.total}/10\n{score.details}"
        )


class TestMediumAdapter:
    """Regression for medium.com paywall stripping."""

    _MEDIUM_HTML = """<!DOCTYPE html>
<html><head>
<title>Why Composable Tools Beat Monolithic Agents</title>
<meta name="author" content="Test Author">
</head><body>
<article>
<h1>Why Composable Tools Beat Monolithic Agents</h1>
<p class="byline">Test Author · 8 min read</p>

<div data-test-id="MemberOnlyWall">
  <h2>This is a member-only story</h2>
  <p>Upgrade to read the full article.</p>
  <button aria-label="Sign in to read">Sign in</button>
</div>

<p>The case for composable tooling in autonomous agents rests on a simple
observation: when each tool has a clear single responsibility, the agent's
planner can reason about combinations without having to model each tool's
internal complexity. This composability is what makes Unix pipes timeless.</p>

<h2>Single Responsibility</h2>
<p>A search tool should search. An extractor should extract. A summarizer
should summarize. Mixing these inside a single tool forces the agent to
guess about behavior boundaries — and agents are bad at guessing.</p>

<h2>Composition Patterns</h2>
<p>The most effective composition patterns mirror functional programming:
the output of one tool flows into the input of the next, with the agent
choosing the chain based on the task. This requires that outputs be
self-describing and that errors be recoverable at the composition boundary.</p>

<div class="meteredContent">
  <p>You have 0 free stories remaining this month. Subscribe to continue.</p>
</div>
</article>
</body></html>"""

    def test_medium_member_wall_stripped(self):
        body, _ = extract(self._MEDIUM_HTML, url="https://medium.com/p/composable-tools")
        assert "member-only story" not in body
        assert "0 free stories remaining" not in body
        # Real prose preserved
        assert "composable" in body.lower()

    def test_medium_subdomain_routes_to_adapter(self):
        body, _ = extract(self._MEDIUM_HTML, url="https://blog.medium.com/p/x")
        assert "0 free stories" not in body


# ---------------------------------------------------------------------------
# Real-usage finding (2026-05-30): inline citation markers.
# Reading a live Wikipedia extraction showed "[1]" / "[12]" citation
# superscripts leaking into prose — context pollution my hand-written
# fixtures never contained. The strip must NOT touch code (where [0]/[1]
# are array indices).
# ---------------------------------------------------------------------------

class TestCitationMarkers:
    def test_strips_prose_citations(self):
        from src.deepsearch_mcp.utils.cleaner import strip_reference_markers
        out = strip_reference_markers("behind modern chatbots.[1] Biased data.[12] more")
        assert "[1]" not in out and "[12]" not in out
        assert "chatbots. Biased data. more" in out

    def test_preserves_inline_code_indices(self):
        from src.deepsearch_mcp.utils.cleaner import strip_reference_markers
        assert strip_reference_markers("use `items[0]` to index") == "use `items[0]` to index"

    def test_preserves_fenced_code_indices(self):
        from src.deepsearch_mcp.utils.cleaner import strip_reference_markers
        src = "```python\nx = arr[1]\ny = lst[12]\n```"
        assert strip_reference_markers(src) == src

    def test_strips_editorial_annotations(self):
        from src.deepsearch_mcp.utils.cleaner import strip_reference_markers
        out = strip_reference_markers(
            "needs a source.[citation needed] outdated.[update] see.[note 1]"
        )
        assert "citation needed" not in out
        assert "[update]" not in out
        assert "[note 1]" not in out

    def test_preserves_nlp_tokens(self):
        """[MASK]/[UNK]/[CLS] are real NLP content, NOT editorial noise."""
        from src.deepsearch_mcp.utils.cleaner import strip_reference_markers
        text = "The [MASK] token and the [UNK] token feed the [CLS] head."
        assert strip_reference_markers(text) == text

    def test_dubious_with_endash_stripped(self):
        from src.deepsearch_mcp.utils.cleaner import strip_reference_markers
        out = strip_reference_markers("a claim[dubious – discuss] continues")
        assert "dubious" not in out


# ---------------------------------------------------------------------------
# B9: leading Wikipedia chrome (infobox / "Part of a series on") — strip the
# leading table before prose, but NEVER a legit data table. Found 2026-05-30
# on real Sam Altman / Mitoma / LLM articles.
# ---------------------------------------------------------------------------

class TestLeadingWikiChrome:
    def _strip(self, text):
        from src.deepsearch_mcp.utils.cleaner import strip_leading_wiki_chrome
        return strip_leading_wiki_chrome(text)

    def test_strips_part_of_a_series_nav(self):
        text = ("| Part of a series on |\n| Machine learning |\n|---|\n\n"
                "A large language model is a neural network trained on text for tasks.")
        out = self._strip(text)
        assert "Part of a series on" not in out
        assert "large language model" in out

    def test_strips_person_infobox(self):
        text = ("| Born | April 22, 1985 |\n| Education | Stanford |\n"
                "| Notable work | Loopt |\n| Spouse | Someone |\n\n"
                "Altman attended Stanford University before he dropped out to co-found Loopt.")
        out = self._strip(text)
        assert "Notable work" not in out and "| Born |" not in out
        assert "Altman attended Stanford" in out

    def test_strips_footballer_infobox(self):
        text = ("| Personal information | |\n|---|---|\n| Date of birth | 1997 |\n"
                "| Team information | |\n| Senior career | |\n\n"
                "Kaoru Mitoma is a Japanese professional footballer who plays as a winger.")
        out = self._strip(text)
        assert "Personal information" not in out and "Date of birth" not in out
        assert "Japanese professional footballer" in out

    def test_preserves_prose_first_body(self):
        text = ("A long opening paragraph of genuine article prose with plenty of words.\n\n"
                "| Model | Score |\n|---|---|\n| GPT | 90 |")
        assert self._strip(text) == text  # unchanged

    def test_preserves_leading_data_table_without_marker(self):
        # A legit leading data table (no infobox marker) must NOT be stripped.
        text = ("| Model | Score |\n|---|---|\n| GPT | 90 |\n| Claude | 88 |\n\n"
                "Real prose follows with enough words to count as a sentence here.")
        assert self._strip(text) == text

    def test_strips_company_website_infobox(self):
        # B18: company/website infobox (DuckDuckGo shape) must be caught.
        text = ("| Type of site | Search engine |\n|---|---|\n"
                "| Headquarters | Paoli, PA |\n| Key people | Weinberg |\n\n"
                "DuckDuckGo is an American software company focused on online privacy.")
        out = self._strip(text)
        assert "Type of site" not in out and "Key people" not in out
        assert "American software company" in out

    def test_preserves_company_comparison_table(self):
        # B18 safety: a real comparison table whose COLUMNS happen to be
        # Headquarters/Founder (but no infobox KEY marker) must survive.
        text = ("| Company | Headquarters | Founder |\n|---|---|---|\n"
                "| A | NYC | Jane |\n| B | SF | Bob |\n\n"
                "The table compares several companies and their founding facts here.")
        assert self._strip(text) == text

    def test_preserves_mid_article_table(self):
        text = ("Opening prose paragraph that is clearly the start of the real article body.\n\n"
                "## Section\n\n| Born | x |\n|---|---|\n| Notable work | y |")
        # 'Notable work' here is mid-article, after prose → must survive.
        assert "Notable work" in self._strip(text)

    def test_strips_programming_language_infobox(self):
        # B25: software / programming-language infobox (Rust shape) must be
        # caught. 'Typing discipline' + 'Filename extensions' are unique
        # language-infobox keys.
        text = ("| Rust | |\n|---|---|\n| Paradigms | Multi-paradigm |\n"
                "| Designed by | Graydon Hoare |\n| First appeared | 2012 |\n"
                "| Stable release | 1.x |\n| Typing discipline | Static, inferred |\n"
                "| Filename extensions | .rs, .rlib |\n\n"
                "Rust is a general-purpose programming language emphasizing performance "
                "and type safety without a garbage collector.")
        out = self._strip(text)
        assert "Typing discipline" not in out and "Filename extensions" not in out
        assert "Paradigms" not in out  # whole leading table region is dropped
        assert "general-purpose programming language" in out

    def test_preserves_language_comparison_table(self):
        # B25 safety: a real comparison table whose COLUMNS are First appeared /
        # Paradigm (the "Comparison of programming languages" shape) must survive
        # — those are NOT markers, exactly so we don't strip a legit table.
        text = ("| Language | First appeared | Paradigm |\n|---|---|---|\n"
                "| Lisp | 1958 | Functional |\n| C | 1972 | Imperative |\n\n"
                "This table compares several historic programming languages by year here.")
        assert self._strip(text) == text

    def test_handles_leading_h1_then_infobox(self):
        text = ("# Kaoru Mitoma\n\n| Personal information | |\n| Date of birth | 1997 |\n\n"
                "Kaoru Mitoma is a Japanese professional footballer who plays on the wing.")
        out = self._strip(text)
        assert "# Kaoru Mitoma" in out          # H1 preserved
        assert "Personal information" not in out  # infobox stripped
        assert "Japanese professional" in out

    def test_extract_end_to_end(self):
        html = """<article>
<h1>Jane Athlete</h1>
<table><tr><th>Personal information</th></tr>
<tr><td>Date of birth</td><td>1990</td></tr>
<tr><td>Senior career</td><td>Club X</td></tr></table>
<p>Jane Athlete is a professional sportsperson known for a long and storied
career across several major clubs and international competitions worldwide.</p>
<h2>Stats</h2>
<table><tr><th>Season</th><th>Goals</th></tr><tr><td>2020</td><td>10</td></tr></table>
</article>"""
        body, _ = extract(html, url="https://en.wikipedia.org/wiki/Jane_Athlete")
        # leading infobox gone, prose + mid-article stats table kept
        assert "Personal information" not in body
        assert "professional sportsperson" in body

    def test_extract_end_to_end_strips_citations_keeps_code(self):
        html = """<article>
<h1>Citations Test</h1>
<p>Large language models are neural networks.[1] They scale with data.[2]
This sentence has enough length to be recognized as real article prose.</p>
<pre><code class="language-python">value = items[0]
other = data[1]</code></pre>
<p>A closing paragraph that also carries a citation marker.[3] and continues
with enough words to remain genuine extractable prose content here.</p>
</article>"""
        body, _ = extract(html, url="https://example.com/cites")
        assert "[1]" not in body.split("```")[0]  # no citation in prose region
        assert "[2]" not in body and "[3]" not in body
        # code indices survive
        assert "items[0]" in body
        assert "data[1]" in body


# ---------------------------------------------------------------------------
# Dogfooding Phase: noise patterns discovered by using the server ourselves
# Source session: evals/dogfood_research.py (2026-05-29)
# Real fixtures from TechCrunch + LangChain blog leaked these 2026-style
# noise lines past the v1 cleaner regex.
# ---------------------------------------------------------------------------

class TestDogfoodingNoisePatterns:
    """Regression for noise leaks found during real agent-session dogfooding."""

    def _extract_body(self, html: str, url: str = "https://example.com/x") -> str:
        body, _ = extract(html, url=url)
        return body

    def test_estimated_reading_time_stripped(self):
        html = """<article>
<h1>Article</h1>
<p>This is a substantive paragraph with enough content to extract meaningfully
for the purpose of a regression test that exercises the extractor end-to-end.</p>
<p>Estimated reading time: 8 minutes</p>
<p>A second substantive paragraph rounding out the body content so the article
is long enough for trafilatura to consider it extractable prose.</p>
</article>"""
        body = self._extract_body(html)
        assert "Estimated reading time" not in body
        assert "8 minutes" not in body  # the value alone should not survive

    def test_short_form_reading_time_stripped(self):
        html = """<article>
<h1>Title</h1>
<p>Substantive paragraph one with enough content to pass extraction thresholds
and keep the article body recognizable as real prose.</p>
<p>8 min read</p>
<p>Another paragraph providing additional reasoning material for the body.</p>
</article>"""
        body = self._extract_body(html)
        assert "8 min read" not in body

    def test_listen_to_article_cta_stripped(self):
        html = """<article>
<h1>Title</h1>
<p>The substantive content of the article begins here with enough length
to satisfy trafilatura's minimum extraction threshold for prose detection.</p>
<p>Listen to this article on the TechCrunch Daily Podcast.</p>
<p>And here is a closing paragraph with more substantive material covering
additional context that an agent would want to read.</p>
</article>"""
        body = self._extract_body(html)
        assert "Listen to this article" not in body

    def test_continue_reading_gate_stripped(self):
        html = """<article>
<h1>Title</h1>
<p>Substantive opening paragraph with enough length to be recognized as
real article prose by the trafilatura extractor running over this HTML.</p>
<p>Continue reading to see the production deployment checklist.</p>
<h2>Checklist</h2>
<ul><li>Item one of the checklist that adds substantive content.</li>
<li>Item two adding more material to the article body.</li></ul>
</article>"""
        body = self._extract_body(html)
        assert "Continue reading to" not in body

    def test_consent_gate_stripped(self):
        html = """<article>
<h1>Title</h1>
<p>Substantive opening paragraph adding sufficient body length so that
extraction has enough material to recognize the article as prose content.</p>
<p>By signing up, you agree to our Terms and Privacy Policy.</p>
<p>And a closing substantive paragraph that provides more useful body text
for the article body that an agent would want to read.</p>
</article>"""
        body = self._extract_body(html)
        assert "By signing up" not in body

    def test_newsletter_cta_stripped(self):
        html = """<article>
<h1>Title</h1>
<p>The substantive prose of the article begins here with enough length
to satisfy trafilatura's threshold for recognizing real article body content.</p>
<p>Get the latest in AI delivered to your inbox.</p>
<p>And a closing substantive paragraph rounding out the body so the article
is solidly long enough to extract under typical extractor settings.</p>
</article>"""
        body = self._extract_body(html)
        assert "Get the latest" not in body
        assert "your inbox" not in body

    def test_tags_line_stripped(self):
        html = """<article>
<h1>Title</h1>
<p>Substantive paragraph one with enough content to extract meaningfully
under the trafilatura extractor's standard prose-detection threshold.</p>
<p>Tags: LangGraph, Production, AI Agents, MCP</p>
<p>A closing substantive paragraph providing more body material so the
article has enough total length to pass extraction.</p>
</article>"""
        body = self._extract_body(html)
        assert "Tags: LangGraph" not in body

    def test_posted_in_stripped(self):
        html = """<article>
<h1>Title</h1>
<p>Substantive opening paragraph providing enough length for trafilatura to
recognize the article as real prose content during extraction.</p>
<p>Posted in: Engineering Blog</p>
<p>A second substantive paragraph providing additional material to round
out the article body and satisfy the prose-detection threshold.</p>
</article>"""
        body = self._extract_body(html)
        assert "Posted in:" not in body

    def test_affiliate_disclosure_stripped(self):
        """Surfaced 2026-05-29 by dogfood_audit.py STRONG tier (full-sentence noise)."""
        html = """<article>
<h1>Best AI Frameworks</h1>
<p>This article may contain affiliate links. If you buy through them we may earn a commission.</p>
<p>The substantive review content begins here with enough length to be
recognized as real article prose during the trafilatura extraction pass.</p>
<h2>Section</h2>
<p>A second substantive paragraph that develops the comparison in enough
detail to round out the body of the article for extraction.</p>
</article>"""
        body = self._extract_body(html)
        assert "affiliate links" not in body
        assert "earn a commission" not in body
        # real prose preserved
        assert "substantive review content" in body

    def test_paid_partnership_stripped(self):
        html = """<article>
<h1>Title</h1>
<p>Produced in paid partnership with Acme Corporation.</p>
<p>The substantive article content begins here and continues for long enough
that trafilatura recognizes it as genuine prose worth extracting cleanly.</p>
<h2>Details</h2>
<p>Another substantive paragraph adding more material to the article body so
the prose-detection threshold is comfortably exceeded.</p>
</article>"""
        body = self._extract_body(html)
        assert "paid partnership" not in body.lower()

    def test_clean_article_unchanged(self):
        """Sanity: a clean article (no noise targets) must NOT lose body content."""
        html = """<article>
<h1>How Async IO Works</h1>
<p>Asynchronous I/O is a concurrent programming design that has received
dedicated support in Python via the asyncio library standard module.</p>
<p>The fundamental primitive is the coroutine, declared with the async
def syntax and awaited with the await keyword inside another coroutine.</p>
<h2>The Event Loop</h2>
<p>The event loop is the central execution device that schedules coroutines
and runs callbacks for completed I/O operations.</p>
</article>"""
        body = self._extract_body(html)
        # All prose paragraphs must be preserved
        assert "Asynchronous I/O is a concurrent" in body
        assert "fundamental primitive is the coroutine" in body
        assert "event loop is the central" in body

    def test_dogfooding_gauntlet_quality_maintained(self):
        """The new noise patterns must NOT lower the Phase 1 Gauntlet average."""
        from evals.eval_judge import score_markdown
        scores = []
        for name, html, url in GAUNTLET_FIXTURES:
            body, meta = extract(html, url=url)
            full = build_frontmatter(meta) + "\n\n" + body
            scores.append(score_markdown(full).total)
        avg = sum(scores) / len(scores)
        assert avg >= GATE_THRESHOLD, (
            f"Gauntlet avg dropped to {avg:.2f}/10 after dogfooding patches; "
            f"new noise patterns may be too aggressive"
        )
