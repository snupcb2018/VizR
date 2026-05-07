#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(edgeR)
})

args <- commandArgs(trailingOnly = TRUE)

input_file <- NULL
output_file <- NULL

i <- 1
while (i <= length(args)) {
  if (args[i] == "--input") {
    input_file <- args[i + 1]
    i <- i + 2
  } else if (args[i] == "--output") {
    output_file <- args[i + 1]
    i <- i + 2
  } else {
    i <- i + 1
  }
}

if (is.null(input_file) || is.null(output_file)) {
  stop("Usage: Rscript run_tmm_from_counts.R --input <genes.counts.matrix> --output <genes.TMM.matrix>")
}

if (!file.exists(input_file)) {
  stop(paste("Input matrix not found:", input_file))
}

counts_df <- read.table(
  input_file,
  header = TRUE,
  sep = "\t",
  check.names = FALSE,
  stringsAsFactors = FALSE,
  quote = "",
  comment.char = ""
)

if (ncol(counts_df) < 2) {
  stop("Counts matrix must contain a gene_id column and at least one sample column")
}

first_col <- colnames(counts_df)[1]
if (!(first_col %in% c("gene_id", "GeneID"))) {
  stop("First column must be gene_id or GeneID")
}

gene_ids <- as.character(counts_df[[1]])
if (any(is.na(gene_ids)) || any(trimws(gene_ids) == "")) {
  stop("gene_id column contains blank values")
}

if (any(duplicated(gene_ids))) {
  stop("gene_id column contains duplicate values")
}

count_matrix <- as.matrix(counts_df[, -1, drop = FALSE])
storage.mode(count_matrix) <- "numeric"
rownames(count_matrix) <- gene_ids

if (any(is.na(count_matrix))) {
  stop("Counts matrix contains non-numeric or NA values")
}

dge <- DGEList(counts = count_matrix)
dge <- calcNormFactors(dge, method = "TMM")
tmm_matrix <- cpm(dge, normalized.lib.sizes = TRUE, log = FALSE, prior.count = 0)

output_df <- data.frame(gene_id = rownames(tmm_matrix), tmm_matrix, check.names = FALSE)
write.table(
  output_df,
  file = output_file,
  sep = "\t",
  quote = FALSE,
  row.names = FALSE,
  col.names = TRUE
)
