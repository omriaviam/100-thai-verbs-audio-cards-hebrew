# Thai Vocabulary Audio Cards in Hebrew

Interactive Hebrew study cards for learning Thai vocabulary with local audio.
The site contains the original 100 verb cards plus 2,677 short vocabulary
items extracted from the Collins *Thai - 3,000 words and phrases* booklet.

## Data and maintenance

- `data/vocabulary.js` is the single structured data source rendered by the site.
- `audio/word-NNN.mp3` contains the matching Thai pronunciation for each card.
- `scripts/extract_pdf_vocab.py` reproducibly extracts and deduplicates short entries.
- `scripts/audit_translations.py` applies category-aware Hebrew quality corrections.
- `scripts/build_vocabulary_data.py` merges the original cards with the audited data.
- `scripts/generate_audio.py` creates the local Thai audio files.
- `scripts/validate_site.py` checks data, duplicates, audio coverage and UI contracts.

## Live Site

After enabling GitHub Pages, the site will be available at:

https://omriaviam.github.io/100-thai-verbs-audio-cards-hebrew/

## GitHub Pages

This repository is intended to be published with GitHub Pages from the main branch and repository root.
