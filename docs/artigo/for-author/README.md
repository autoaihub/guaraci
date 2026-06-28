# Guaraci — source material for a *Data in Brief* article

**For:** the co-author (PhD candidate) who will select the content and write the final manuscript.
**Language:** English (ready to reuse).
**Target journal:** *Data in Brief* (Elsevier) — chosen by the advisor.
**Subject of the article:** the **Guaraci platform itself** — an open-source system that
**acquires, decodes, harmonizes and records downloads of Brazilian public data** from the
primary official sources. It is *not* about a single bespoke dataset; Guaraci is the protagonist
(the "download registrar"/acquisition engine).

> This folder is a **compilation of relevant material**, current to **Guaraci v0.5.2**. It is
> intentionally comprehensive — pick and trim what fits the manuscript. The selection and final
> writing are yours.

## What is in this folder

| File | What it is | Use it for |
|---|---|---|
| `guaraci-dossier.md` | Comprehensive, factual technical + historical description of Guaraci, **updated to v0.5.2** (the prior `.docx` narratives stopped at v0.4.1). | The source of truth: architecture, acquisition mechanisms, full source list, data engineering, governance, evolution timeline, limitations. |
| `data-in-brief-sections.md` | Draft text **organized by the exact sections of the *Data in Brief* template**, platform-as-subject, in English. | Drop-in/adapt content for each template box (title, abstract, specifications table, value of the data, methods, etc.). |
| `README.md` (this file) | Orientation + fixed facts (authors, version, citation) + one note on journal fit. | Read first. |

## Fixed facts (verified against the repository, v0.5.2)

- **Software version:** 0.5.2 (Development status: Alpha). **License:** MIT. **Python:** 3.11/3.12.
- **Repository:** https://github.com/autoaihub/guaraci · **Workflow:** Docker-first.
- **Authors (from `pyproject.toml`/`CITATION.cff`)** — confirm order and affiliations:
  - Luis Felipe Vogel Lopes — `vogel@usp.br` — ICMC-USP (corresponding/maintainer)
  - Pedro Guilherme dos Reis Teixeira — `pedro.guilherme2305@usp.br` — USP
  - Robson Parmezan Bonidia — UTFPR (Universidade Tecnológica Federal do Paraná)
  - André Carlos Ponce de Leon Ferreira de Carvalho — ICMC-USP
- **Project context:** developed within **AutoAI-Pandemics** (ICMC-USP), part of the **AI4PEP**
  network; funded by **IDRC (Canada)**. *Confirm the exact grant ID with the coordination.*
- **Recommended software citation (current release):**
  > Vogel Lopes, Luis Felipe, dos Reis Teixeira, Pedro Guilherme, Bonidia, Robson Parmezan, and
  > de Carvalho, André Carlos Ponce de Leon Ferreira. 2026. Guaraci (Version 0.5.2)
  > [Computer software]. https://github.com/autoaihub/guaraci

## One note on journal fit (please read — your call, not a blocker)

*Data in Brief* publishes **data articles**: each one describes a **dataset deposited in a public
repository** (with a DOI/accession reachable by reviewers) and explains how it was collected and
how to reuse it — **without conclusions or interpretation**. A pure software/tool description is
usually out of scope for DiB (that would fit **SoftwareX** or **JOSS**).

To keep a **platform-centred** story submittable to DiB, the common bridge is:

- Treat **Guaraci as the data-collection method** (it goes in *Experimental Design, Materials and
  Methods*), and
- Anchor the article to **a concrete, representative dataset assembled with Guaraci** that you
  **deposit** (Zenodo/Mendeley Data, CC BY 4.0). Minimal viable options:
  1. a harmonized snapshot of one or a few sources (e.g., a DATASUS system over its full history), or
  2. a small **multi-source example collection** (one representative extract per acquisition
     mechanism: gov.br crawl + OpenDataSUS REST + DATASUS FTP + NASA), plus the machine-readable
     **source catalog** and the **manifests** Guaraci emits.

`data-in-brief-sections.md` is written so the platform is the protagonist *and* there is a data
object to point at. If the advisor prefers a strict tool paper, the same dossier feeds a
SoftwareX/JOSS submission with little change.
