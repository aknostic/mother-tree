#!/usr/bin/env python3
"""Transform pandoc-generated body-raw.tex into body.tex with LNCS conventions:
- strip numbered prefixes from \\section / \\subsection titles
- rename pandoc auto-labels to sec:* / fig:* scheme
- replace § cross-references with Sect.~\\ref{}
- replace (Fig. N) with (Fig.~\\ref{})
- replace inline citation brackets with \\cite{}
- replace Unicode glyphs with LaTeX equivalents
- fix image paths to point at ../figures/
"""
import re

SECTION_MAP = [
    ('1 Introduction', 'Introduction', 'sec:intro', 'introduction'),
    ('2 Background: the Mycorrhizal Method', 'Background: The Mycorrhizal Method',
     'sec:background', 'background-the-mycorrhizal-method'),
    ('3 Architecture', 'Architecture', 'sec:arch', 'architecture'),
    ('4 Choreography over Autonomy', 'Choreography over Autonomy',
     'sec:choreography', 'choreography-over-autonomy'),
    ('5 Freedom to Operate', 'Freedom to Operate', 'sec:freedom', 'freedom-to-operate'),
    ('6 Mutualism in Practice', 'Mutualism in Practice', 'sec:mutualism', 'mutualism-in-practice'),
    ('7 Sustaining the Stack: Measured Emissions', 'Sustaining the Stack: Measured Emissions',
     'sec:keit', 'sustaining-the-stack-measured-emissions'),
    ('8 Related Work, Lessons, Future Work', 'Related Work, Lessons, Future Work',
     'sec:related', 'related-work-lessons-future-work'),
]

FIG_MAP = {'1': 'fig:arch', '2': 'fig:loop', '3': 'fig:judges', '4': 'fig:models'}

SECTION_REF_MAP = {
    '1': 'sec:intro', '2': 'sec:background',
    '3': 'sec:arch', '3.1': 'sec:arch', '3.2': 'sec:arch', '3.3': 'sec:arch', '3.4': 'sec:arch',
    '4': 'sec:choreography', '4.2': 'sec:choreography',
    '5': 'sec:freedom', '5.2': 'sec:freedom',
    '6': 'sec:mutualism', '6.1': 'sec:mutualism', '6.4': 'sec:mutualism',
    '7': 'sec:keit', '7.3': 'sec:keit',
    '8': 'sec:related',
}

CITATIONS = [
    ('{[}Simard et al., \\emph{Nature} 1997; Simard, \\emph{Finding the Mother Tree}, 2021{]}',
     '\\cite{simard1997,simard2021}'),
    ('{[}Richardson, \\emph{Perfect Selling}, 2008{]}',
     '\\cite{richardson2008}'),
    ('\\emph{The Challenger Sale} identified',
     '\\emph{The Challenger Sale}~\\cite{dixon2011} identified'),
    ("Wintzen's cell-based model of a professional services firm {[}\\emph{Eckart's Notes}{]}",
     "Wintzen's cell-based model of a professional services firm~\\cite{wintzen2007}"),
    ('\\href{https://github.com/aknostic/keit}{https://github.com/aknostic/keit}',
     '\\cite{keit2026}'),
    ('{[}Paganelli \\& Geurtsen, https://github.com/aknostic/keit{]}', '\\cite{keit2026}'),
    ('{[}Paganelli \\& Geurtsen, \\cite{keit2026}{]}', '\\cite{keit2026}'),
    # §8.1 related work citations
    ('{[}Moura, \\emph{CrewAI}, 2024{]}', '\\cite{crewai}'),
    ('{[}LangChain AI, \\emph{LangGraph}, 2024{]}', '\\cite{langgraph}'),
    ('{[}Wu et al., \\emph{AutoGen}, 2023{]}', '\\cite{autogen}'),
    ('{[}Project URL withheld for blind review{]}', '\\cite{openclaw}'),
    ('{[}Apache, \\emph{Airflow}{]}', '\\cite{airflow}'),
    ('{[}Prefect Technologies, \\emph{Prefect}{]}', '\\cite{prefect}'),
    ('{[}Elementl, \\emph{Dagster}{]}', '\\cite{dagster}'),
    ('{[}Zheng et al., \\emph{Judging LLM-as-a-Judge}, 2023{]}', '\\cite{zheng2023}'),
    ('{[}Patterson et al., \\emph{Carbon Emissions and Large Neural Network Training}, 2021{]}',
     '\\cite{patterson2021}'),
    ('{[}Evans, \\emph{Domain-Driven Design}, 2003{]}', '\\cite{evans2003}'),
    ('{[}Wintzen, \\emph{Eckart\'s Notes}, 2007{]}', '\\cite{wintzen2007}'),
]


def main():
    with open('body.tex', 'r') as f:
        s = f.read()

    # Sections
    for old_title, new_title, new_label, old_label in SECTION_MAP:
        s = s.replace(
            f'\\section{{{old_title}}}\\label{{{old_label}}}',
            f'\\section{{{new_title}}}\\label{{{new_label}}}'
        )

    # Subsections: strip "N.M " prefix
    s = re.sub(r'\\subsection\{(\d+\.\d+) ([^}]+)\}',
               lambda m: '\\subsection{' + m.group(2) + '}', s)

    # Unicode
    s = s.replace('CO₂', 'CO\\textsubscript{2}')
    s = s.replace('₂', '\\textsubscript{2}')
    s = s.replace('→', '\\(\\rightarrow\\)')
    s = s.replace('≥', '\\(\\geq\\)')
    s = s.replace('≤', '\\(\\leq\\)')

    # Figures: strip "Fig. N: " from \caption{} and add \label{}
    def fix_figure(m):
        body = m.group(0)
        cm = re.search(r'\\caption\{Fig\.\s*(\d+):\s*', body)
        if not cm:
            return body
        fig_n = cm.group(1)
        label = FIG_MAP.get(fig_n, 'fig:' + fig_n)
        body = re.sub(r'\\caption\{Fig\.\s*\d+:\s*', '\\\\caption{', body)
        body = re.sub(r'alt=\{Fig\.\s*\d+:\s*', 'alt={', body)
        body = body.replace('\\end{figure}', '\\label{' + label + '}\n\\end{figure}')
        return body

    s = re.sub(r'\\begin\{figure\}.*?\\end\{figure\}', fix_figure, s, flags=re.DOTALL)

    # Inline (Fig. N) refs
    for fig_n, label in FIG_MAP.items():
        s = s.replace('(Fig. ' + fig_n + ')', '(Fig.~\\ref{' + label + '})')

    # §N cross-refs (longer first)
    for k in sorted(SECTION_REF_MAP.keys(), key=len, reverse=True):
        s = s.replace('§' + k, 'Sect.~\\ref{' + SECTION_REF_MAP[k] + '}')

    # Citations
    for old, new in CITATIONS:
        s = s.replace(old, new)

    # Figure paths (../figures/ instead of figures/)
    s = s.replace('{figures/', '{../figures/')

    with open('body.tex', 'w') as f:
        f.write(s)

    print(f"  sections:    {s.count(chr(92) + 'section{')}")
    print(f"  subsections: {s.count(chr(92) + 'subsection{')}")
    print(f"  figures:     {s.count(chr(92) + 'begin{figure}')}")
    print(f"  fig labels:  {s.count(chr(92) + 'label{fig:')}")
    print(f"  citations:   {s.count(chr(92) + 'cite{')}")
    print(f"  sect refs:   {s.count('Sect.~' + chr(92) + 'ref{')}")
    print(f"  fig refs:    {s.count('Fig.~' + chr(92) + 'ref{')}")


if __name__ == '__main__':
    main()
