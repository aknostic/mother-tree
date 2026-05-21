#!/usr/bin/env bash
# Build the Springer LNCS LaTeX paper.
# Usage: ./build-latex.sh
#
# Steps:
#   1. Re-render any figures/*.dot to figures/*.pdf (graphviz).
#   2. Convert ../sections/*.md to body-raw.tex via pandoc.
#   3. Apply transformations (section labels, figure labels,
#      cross-references, Unicode glyphs, citations) -> body.tex.
#   4. Run xelatex + bibtex + xelatex + xelatex.

set -euo pipefail
cd "$(dirname "$0")"

# 1. Figures
if command -v dot >/dev/null 2>&1; then
  for f in ../figures/*.dot; do
    [ -e "$f" ] || continue
    out="${f%.dot}.pdf"
    if [ ! -e "$out" ] || [ "$f" -nt "$out" ]; then
      echo "→ rendering $(basename "$f")"
      dot -Tpdf "$f" -o "$out"
    fi
  done
else
  echo "⚠  graphviz (dot) not installed; figures will not be regenerated."
fi

# 2. Markdown -> raw LaTeX body
pandoc ../sections/*.md \
  -t latex --wrap=preserve --syntax-highlighting=none \
  -o body-raw.tex

# 3. Transform body-raw.tex -> body.tex (section labels, figure labels,
#    Unicode, cross-refs, citations).
cp body-raw.tex body.tex
python3 transform-body.py

# 4. xelatex + bibtex + xelatex + xelatex
echo "→ xelatex (pass 1)"
xelatex -interaction=nonstopmode -halt-on-error paper.tex > /dev/null
echo "→ bibtex"
bibtex paper > /dev/null
echo "→ xelatex (pass 2)"
xelatex -interaction=nonstopmode paper.tex > /dev/null
echo "→ xelatex (pass 3)"
xelatex -interaction=nonstopmode paper.tex > /dev/null

pages=$(mdls -name kMDItemNumberOfPages -raw paper.pdf 2>/dev/null || echo "?")
size=$(wc -c <paper.pdf | tr -d ' ')
echo "→ paper.pdf (${size} bytes, ${pages} pages)"
