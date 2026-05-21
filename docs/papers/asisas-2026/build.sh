#!/usr/bin/env bash
# Build paper.pdf from paper.md via pandoc + xelatex.
# Usage: ./build.sh
#
# Steps:
#   1. Re-render any figures/*.dot to figures/*.pdf (graphviz).
#   2. Reassemble paper.md from abstract.md head + sections/*.md + references.
#   3. Pre-process Unicode glyphs (CO₂, ≥, ≤, →) into LaTeX equivalents
#      so xelatex doesn't warn about missing characters in non-math fonts.
#   4. Run pandoc (xelatex, Palatino + Menlo, 10pt, 2.5cm margins).
#
# This is a draft renderer; final submission needs the Springer LNCS template.

set -euo pipefail
cd "$(dirname "$0")"

# --- 1. Render figures ------------------------------------------------------
if command -v dot >/dev/null 2>&1; then
  for f in figures/*.dot; do
    [ -e "$f" ] || continue
    out="${f%.dot}.pdf"
    if [ ! -e "$out" ] || [ "$f" -nt "$out" ]; then
      echo "→ rendering $(basename "$f")"
      dot -Tpdf "$f" -o "$out"
    fi
  done
else
  echo "⚠  graphviz (dot) not installed; figures will not be regenerated."
  echo "   install with: brew install graphviz"
fi

# --- 2. Reassemble paper.md -------------------------------------------------
{
  cat <<'TITLE'
# Mother Tree: A Methodology-First, Choreographed Multi-Agent System for Individual–Collective Commercial Intelligence

**Jurg van Vliet, Flavia Paganelli, Jasper Geurtsen**
*Aknostic, Amsterdam, the Netherlands*
`{jurg, flavia, jasper}@aknostic.com`

**Submission:** ASISAS 2026 — *Architecting Secure, Intelligent, and Sovereign Agentic Systems* (workshop at ECSA 2026). Experience report (full paper).

---

TITLE
  awk '/^\*\*Abstract\.\*\*/,/^\*\*Keywords:\*\*/' abstract.md
  echo
  echo "---"
  echo
  for s in sections/*.md; do
    cat "$s"
    echo
  done
  echo "---"
  echo
  echo "## References"
  echo
  cat <<'REFS'
> *To be completed before paper submission. Anchor citations:*
>
> - Simard, S. W., et al. (1997). Net transfer of carbon between ectomycorrhizal tree species in the field. *Nature*, 388(6642), 579–582.
> - Simard, S. W. (2021). *Finding the Mother Tree: Discovering the Wisdom of the Forest*. Knopf.
> - Dixon, M., Adamson, B., & Toman, N. (2011). *The Challenger Sale: Taking Control of the Customer Conversation*. Portfolio.
> - Richardson, L. (2008). *Perfect Selling*. McGraw-Hill.
> - Wintzen, E. (2007). *Eckart's Notes*. Lemniscaat.
> - Paganelli, F., & Geurtsen, J. (2026). KEIT: Kubernetes Emissions Insights Tool. Apache-2.0. https://github.com/aknostic/keit.
> - PostGraphile project; pgvector project; CloudNativePG project; Flux CD project; Kepler project; Boavizta project; ElectricityMaps; Scaleway Generative APIs documentation.
REFS
} > paper.md

# --- 3 + 4. Pre-process Unicode and run pandoc ------------------------------
sed \
  -e 's/₂/$_2$/g' \
  -e 's/≥/$\\geq$/g' \
  -e 's/≤/$\\leq$/g' \
  -e 's/→/$\\to$/g' \
  paper.md |
  pandoc -o paper.pdf \
    --pdf-engine=xelatex \
    -V geometry:margin=2.5cm \
    -V fontsize=10pt \
    -V mainfont="Palatino" \
    -V monofont="Menlo" \
    -V "header-includes=\usepackage{float}\let\origfigure\figure\let\endorigfigure\endfigure\renewenvironment{figure}[1][]{\origfigure[H]}{\endorigfigure}" \
    --toc --toc-depth=2

pages=$(mdls -name kMDItemNumberOfPages -raw paper.pdf 2>/dev/null || echo "?")
size=$(wc -c <paper.pdf | tr -d ' ')
echo "→ paper.pdf (${size} bytes, ${pages} pages)"
