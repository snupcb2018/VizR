# TAIR10 Reference Files

Arabidopsis thaliana TAIR10 reference genome files.

## Files

### Compressed Archive (Recommended for Git)
- `tair10_reference.tar.gz` (66MB) - Contains all reference files

### Included Files (after extraction)
1. `Arabidopsis_thaliana.TAIR10.dna.toplevel.fa` (117MB) - Genome sequence
2. `Arabidopsis_thaliana.TAIR10.cdna.all.fa` (96MB) - cDNA sequences
3. `Arabidopsis_thaliana.TAIR10.58.gtf` (261MB) - Gene annotations

## Usage

### Extract Reference Files
```bash
cd resource/arabidopsis/reference/TAIR10
tar -xzf tair10_reference.tar.gz
```

### Auto-extraction (if VizR needs it)
VizR will automatically extract these files on first use if they are not present.

## Source
Downloaded from Ensembl Plants: https://plants.ensembl.org/Arabidopsis_thaliana/

## Metadata
See `metadata.json` for detailed information about:
- Version
- Download date
- Source URLs
- File descriptions
