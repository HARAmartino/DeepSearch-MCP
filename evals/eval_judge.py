"""
Automated quality scorer for DeepSearch-MCP extraction output.

Scores Markdown output from 0.0 to 10.0 based on three axes:
  - Noise Ratio    (0-4 pts): penalizes nav/footer/ad artifacts
  - MD Structure   (0-3 pts): rewards valid headers, lists, code blocks
  - Content Density(0-3 pts): text-to-noise ratio estimation
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Nav/footer/ad artifacts that should be stripped (case-insensitive)
_NOISE_PATTERNS = [
    r"skip\s+to\s+(main\s+)?content",
    r"cookie\s+(settings|policy|consent|banner|notice)",
    r"accept\s+(all\s+)?cookies",
    r"subscribe\s+to\s+(our\s+)?(newsletter|updates)",
    r"share\s+on\s+(twitter|facebook|linkedin|instagram)",
    r"follow\s+us\s+on",
    r"all\s+rights\s+reserved",
    r"privacy\s+policy",
    r"terms\s+(of\s+)?(use|service)",
    r"sign\s+(up|in)\s+to\s+(read|continue|access)",
    r"already\s+a\s+subscriber",
    r"related\s+(posts?|articles?|stories)",
    r"you\s+might\s+also\s+like",
    r"read\s+more\s+from",
    r"advertisement",
    r"sponsored\s+(content|post)",
    r"click\s+here\s+to\s+(read|learn|download)",
    r"©\s*\d{4}",
    r"^\s*(home|about|contact|search|menu|navigation)\s*$",
    r"back\s+to\s+top",
]
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE | re.MULTILINE)

# Markdown structural signals
_MD_H1_RE = re.compile(r"^#{1,2}\s+\S", re.MULTILINE)
_MD_H_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_MD_LIST_RE = re.compile(r"^\s*[-*+]\s+\S", re.MULTILINE)
_MD_CODE_RE = re.compile(r"```[\s\S]*?```", re.DOTALL)
_MD_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_YAML_FRONT_RE = re.compile(r"^---\n[\s\S]*?\n---\n", re.MULTILINE)

# Below this much body content, "absence of noise" is not evidence of a clean
# extraction — there is simply nothing to judge. Used to damp the noise reward
# for thin/failed extractions (B26). Sits below a real short answer (~200 chars)
# so substantive prose keeps full credit.
_MIN_CONTENT_CHARS = 150


@dataclass
class JudgeScore:
    noise_score: float      # 0-4
    structure_score: float  # 0-3
    density_score: float    # 0-3
    total: float            # 0-10
    noise_hits: list[str]
    details: str

    def passed(self, threshold: float = 8.0) -> bool:
        return self.total >= threshold


def score_markdown(text: str) -> JudgeScore:
    """
    Score a piece of Markdown text on the 0-10 scale.

    Args:
        text: The Markdown string to evaluate (e.g. output of read_article).

    Returns:
        JudgeScore with per-axis breakdown and total.
    """
    if not text or not text.strip():
        return JudgeScore(
            noise_score=0.0,
            structure_score=0.0,
            density_score=0.0,
            total=0.0,
            noise_hits=[],
            details="Empty input.",
        )

    # Strip YAML frontmatter before analysis (it's not noise)
    # but remember whether it carried a title — that counts as an implicit
    # H1 for structure scoring, so H1 deduplication (read_article ≥Phase5)
    # doesn't unfairly penalize a well-titled article.
    has_frontmatter_title = bool(re.search(r"^title:\s*\S", text, re.MULTILINE))
    body = _YAML_FRONT_RE.sub("", text).strip()
    lines = body.splitlines()
    total_lines = max(len(lines), 1)
    total_chars = len(body)

    # --- Axis 1: Noise Ratio (0-4 pts) ---
    # Find all noise matches
    noise_hits = list({m.group(0).strip() for m in _NOISE_RE.finditer(body)})
    noise_line_count = sum(
        1 for line in lines if _NOISE_RE.search(line)
    )
    noise_ratio = noise_line_count / total_lines  # 0.0 – 1.0

    # Scale: 0 noise → 4 pts; 25% noise → 2 pts; 50%+ noise → 0 pts
    noise_score = max(0.0, 4.0 - (noise_ratio * 16.0))
    noise_score = min(4.0, noise_score)

    # Content-sufficiency gate (B26): "no noise" is vacuous when there's barely
    # any content. A failed/thin extraction ("# Title / Loading…", ~20 chars)
    # would otherwise earn the full 4/4 noise reward simply for lacking noise
    # patterns — making an empty read look mediocre-but-okay (5.0/10). Scale the
    # noise reward by how much content there is to actually judge. Real articles
    # (hundreds+ of chars → factor 1.0) are unaffected, so the ≥8.5 gate region
    # is untouched; only near-empty bodies are damped. Calibrated against the
    # consumer judgment in evals/calibrate_judge.py (B1).
    content_sufficiency = min(1.0, total_chars / _MIN_CONTENT_CHARS)
    noise_score = round(noise_score * content_sufficiency, 2)

    # --- Axis 2: Markdown Structure (0-3 pts) ---
    structure_score = 0.0
    has_header = bool(_MD_H_RE.search(body))
    has_h1 = bool(_MD_H1_RE.search(body))
    has_list = bool(_MD_LIST_RE.search(body))
    has_code_block = bool(_MD_CODE_RE.search(body))
    has_inline_code = bool(_MD_INLINE_CODE_RE.search(body))
    # Count distinct heading levels (H1+H2+H3 = richer structure).
    # Frontmatter title counts as an implicit H1 — so an article with
    # frontmatter `title:` + body H2/H3 is hlevels=2 (well-sectioned),
    # not hlevels=1 (penalized).
    body_levels = {
        m.group(0)[0 : m.group(0).index(" ")]
        for m in _MD_H_RE.finditer(body)
    }
    if has_frontmatter_title:
        body_levels.add("#")
    heading_levels = len(body_levels)

    # Treat frontmatter title as H1 for the has_h1 check too
    effective_has_h1 = has_h1 or has_frontmatter_title

    # Points for structural elements
    if effective_has_h1:
        structure_score += 1.0
    elif has_header:
        structure_score += 0.5
    # Bonus for multiple heading levels (well-sectioned document)
    if heading_levels >= 2:
        structure_score += 0.5
    if has_list:
        structure_score += 0.75
    if has_code_block:
        structure_score += 1.0
    elif has_inline_code:
        structure_score += 0.25

    structure_score = round(min(3.0, structure_score), 2)

    # --- Axis 3: Content Density (0-3 pts) ---
    # Strip code-block content before computing avg line length:
    # code blocks have intentionally short lines and should not penalize density.
    body_no_code = _MD_CODE_RE.sub("", body)
    prose_lines = [
        ln for ln in body_no_code.splitlines()
        if ln.strip() and not re.match(r"^#{1,6}\s", ln) and not re.match(r"^[-*+]\s", ln)
    ]
    avg_line_len = (
        sum(len(ln) for ln in prose_lines) / len(prose_lines)
        if prose_lines else 0
    )

    # Heuristic: avg prose line length > 60 chars suggests real prose (not nav
    # menus). (total_chars computed once near the top, before the noise axis.)
    if avg_line_len >= 80:
        density_score = 3.0
    elif avg_line_len >= 60:
        density_score = 2.5
    elif avg_line_len >= 40:
        density_score = 2.0
    elif avg_line_len >= 20:
        density_score = 1.0
    else:
        density_score = 0.5

    # Code-heavy content (docs, tutorials) is inherently high-density — apply floor
    if has_code_block:
        density_score = max(density_score, 2.0)

    # Penalty for very short overall content
    if total_chars < 200:
        density_score = max(0.0, density_score - 1.5)

    density_score = round(min(3.0, density_score), 2)

    total = round(noise_score + structure_score + density_score, 2)

    details = (
        f"noise={noise_score}/4 (ratio={noise_ratio:.1%}, hits={len(noise_hits)}, "
        f"content={content_sufficiency:.2f}) | "
        f"structure={structure_score}/3 "
        f"(h1={effective_has_h1}, hlevels={heading_levels}, list={has_list}, code={has_code_block}) | "
        f"density={density_score}/3 (prose_avg={avg_line_len:.0f}ch, total={total_chars}ch)"
    )

    return JudgeScore(
        noise_score=noise_score,
        structure_score=structure_score,
        density_score=density_score,
        total=total,
        noise_hits=noise_hits,
        details=details,
    )


def score_from_file(path: str) -> JudgeScore:
    with open(path, encoding="utf-8") as f:
        return score_markdown(f.read())


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python eval_judge.py <file.md>")
        sys.exit(1)

    result = score_from_file(sys.argv[1])
    print(f"Score: {result.total}/10  ({'PASS' if result.passed() else 'FAIL'})")
    print(f"  {result.details}")
    if result.noise_hits:
        print(f"  Noise found: {result.noise_hits[:5]}")
