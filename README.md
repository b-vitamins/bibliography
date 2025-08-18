# Bibliography Management System

A comprehensive BibTeX bibliography management system with automated enrichment tracking, quality validation, and systematic organization of academic references.

## Quick Start

### First Time Setup (Fresh Clone)
```bash
# Clone repository
git clone <repository-url>
cd bibliography

# Enter Guix environment
guix shell -m manifest.scm

# Restore enrichment history from version control
python3 scripts/import-tracking.py

# Verify setup
python3 scripts/enrichment-status.py
```

### Daily Usage Patterns

#### 1. Adding a Single Paper
When you find a new paper to add:

```
Claude, I found this paper: https://arxiv.org/abs/2401.12345
Add it to by-domain/transformers.bib
```

Claude will:
- Extract metadata and create BibTeX entry
- Check for duplicates
- Enrich with OpenAlex ID and official PDF
- Add to target file
- Track in enrichment database

#### 2. Enriching Existing Files
To enrich all unenriched entries in a file:

```
Claude, enrich all entries in by-domain/llm.bib
```

Claude will:
- Analyze the file for unenriched entries
- Process in batches of 20
- Track all enrichment attempts
- Report success/failure statistics

#### 3. Finding Papers on a Topic
To search your bibliography:

```
Claude, find all papers about vision transformers
```

Claude will search across titles, abstracts, and keywords.

#### 4. Checking Bibliography Health
To see enrichment status:

```
Claude, show me the enrichment status of my bibliography
```

Or for a specific file:
```
Claude, what's the status of by-domain/reinforcement.bib?
```

#### 5. Organizing Papers
To move papers between categories:

```
Claude, this paper about RLHF should be in by-domain/alignment.bib 
not in by-domain/reinforcement.bib
```

#### 6. Cleaning and Validating
To clean up formatting issues:

```
Claude, clean and validate by-format/theses/masters.bib
```

## Repository Structure

```
bibliography/
├── by-domain/          # Papers organized by research domain
│   ├── llm.bib        # Large language models
│   ├── transformers.bib # Transformer architectures
│   ├── alignment.bib  # AI alignment research
│   └── ...
├── by-format/         # Papers organized by publication type
│   ├── references/    # Standard references
│   │   ├── whitepapers.bib
│   │   └── award.bib
│   ├── theses/       # Academic theses
│   └── courses/      # Course materials
├── meta/             # Working files and tests
├── scripts/          # Python utilities
├── enrichment-tracking.json  # Version-controlled enrichment history
└── CLAUDE.md         # Technical reference for Claude
```

## Common Workflows

### Adding Papers from URLs

**ArXiv Papers:**
```
Claude, add this paper: https://arxiv.org/abs/2312.11805
Put it in by-domain/ssm.bib
```

**Conference Papers:**
```
Claude, add this ICLR paper: https://openreview.net/forum?id=abc123
It's about diffusion models, so put it in by-domain/generative.bib
```

**Multiple Papers:**
```
Claude, I have these papers to add:
1. https://arxiv.org/abs/2401.00001 - about LLM reasoning
2. https://arxiv.org/abs/2401.00002 - about code generation
3. https://arxiv.org/abs/2401.00003 - about multimodal models
Add them to appropriate domain files
```

### Bulk Enrichment

**Enrich Entire Domain:**
```
Claude, enrich all unenriched entries in by-domain/
```

**Retry Failed Enrichments:**
```
Claude, retry enrichment for entries that failed more than 7 days ago
```

### Quality Checks

**Find Duplicates:**
```
Claude, check for duplicate entries across all bibliography files
```

**Validate Entries:**
```
Claude, validate all entries in by-format/references/
Check for missing mandatory fields
```

**Find Papers Without PDFs:**
```
Claude, find all enriched entries that don't have PDF links
```

### Research Tasks

**Literature Review:**
```
Claude, create a literature review outline for papers about 
"emergent abilities in large language models"
```

**Citation Network:**
```
Claude, which papers in my bibliography cite Vaswani et al. 2017?
```

**Recent Papers:**
```
Claude, show me all 2024 papers about constitutional AI
```

## Best Practices

### 1. Entry Quality Standards
- Always enrich entries when adding (automatic with Claude)
- Prefer official PDFs over arXiv when available
- Use consistent author names (full first names)
- Include abstracts for searchability

### 2. Organization Guidelines
- Place papers in most specific applicable domain
- Use meta/ for temporary work
- Keep format-based organization for special collections

### 3. Commit Messages
Follow these patterns:
- `enhance: Add 5 transformer papers to by-domain/transformers.bib`
- `fix: Correct duplicate entries in by-domain/llm.bib`
- `refactor: Move RLHF papers from rl.bib to alignment.bib`

### 4. Regular Maintenance

**Weekly:**
- Check enrichment status
- Retry failed enrichments
- Clean up tmp/ directory

**Monthly:**
- Validate all files
- Check for duplicates
- Update README if needed

## Script Reference

### Core Scripts

**Verify BibTeX syntax:**
```bash
python3 scripts/verify-bib.py file.bib
```

**Clean BibTeX files:**
```bash
python3 scripts/clean-bib.py --in-place file.bib
```

**Count entries:**
```bash
python3 scripts/count-entries.py file.bib
python3 scripts/count-entries.py file.bib --enrichment-stats
```

### Enrichment Tracking

**Check enrichment status:**
```bash
# Overall status
python3 scripts/enrichment-status.py

# Specific file
python3 scripts/enrichment-status.py by-domain/llm.bib

# Find retry candidates
python3 scripts/enrichment-status.py --retry-candidates

# JSON output for automation
python3 scripts/enrichment-status.py --json
```

**Import/Export tracking data:**
```bash
# Import on fresh clone
python3 scripts/import-tracking.py

# Manual export (automatic on commit)
python3 scripts/export-tracking.py
```

### Entry Management

**Prepare single entry for enrichment:**
```bash
python3 scripts/prepare-entry.py target.bib new-entry.bib
```

**Finalize enriched entry:**
```bash
python3 scripts/finalize-entry.py target.bib enriched-entry.bib
```

**Analyze file for batch enrichment:**
```bash
python3 scripts/analyze-enrichment.py file.bib
```

### Utilities

**Extract individual entries:**
```bash
python3 scripts/extract-entries.py file.bib
# Creates tmp/filename/entry-N.bib files
```

**Compare BibTeX files:**
```bash
python3 scripts/compare-bib-files.py original.bib modified.bib
```

## Troubleshooting

### Missing Enrichment History
```bash
# If enrichment history is missing after fresh clone
python3 scripts/import-tracking.py
```

### Corrupted BibTeX Files
```bash
# Validate and report issues
python3 scripts/verify-bib.py problematic.bib

# Clean with backup
python3 scripts/clean-bib.py --in-place problematic.bib
```

### Failed Enrichments
```bash
# See what failed
python3 scripts/enrichment-status.py --retry-candidates

# Check specific file
python3 scripts/enrichment-status.py by-domain/llm.bib
```

## Tips for Working with Claude

1. **Be Specific:** Instead of "add this paper", provide the URL or title
2. **Batch Operations:** Claude can handle multiple papers at once efficiently
3. **Trust Enrichment:** Claude tracks what's been enriched - no need to check manually
4. **Use Natural Language:** Describe what you want in plain English
5. **Leverage Search:** Claude can search by author, title, topic, year, etc.

## Technical Details

For implementation details and Claude-specific instructions, see [CLAUDE.md](CLAUDE.md).
