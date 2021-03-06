# -*- coding: utf-8 -*-
import json
import os
import pkg_resources
import gzip
from intervaltree import Interval, IntervalTree

import puzzle

SO_TERMS = (
  'transcript_ablation',
  'splice_donor_variant',
  'splice_acceptor_variant',
  'stop_gained',
  'frameshift_variant',
  'stop_lost',
  'start_lost',
  'initiator_codon_variant',
  'transcript_amplification',
  'inframe_insertion',
  'inframe_deletion',
  'missense_variant',
  'protein_altering_variant',
  'splice_region_variant',
  'incomplete_terminal_codon_variant',
  'stop_retained_variant',
  'synonymous_variant',
  'coding_sequence_variant',
  'mature_miRNA_variant',
  '5_prime_UTR_variant',
  '3_prime_UTR_variant',
  'non_coding_exon_variant',
  'non_coding_transcript_exon_variant',
  'non_coding_transcript_variant',
  'nc_transcript_variant',
  'intron_variant',
  'NMD_transcript_variant',
  'non_coding_transcript_variant',
  'upstream_gene_variant',
  'downstream_gene_variant',
  'TFBS_ablation',
  'TFBS_amplification',
  'TF_binding_site_variant',
  'regulatory_region_ablation',
  'regulatory_region_amplification',
  'regulatory_region_variant',
  'feature_elongation',
  'feature_truncation',
  'intergenic_variant'
)

# -*- coding: utf-8 -*-
SEVERITY_DICT = {}
for severity, term in enumerate(SO_TERMS):
    SEVERITY_DICT[term] = severity

resource_package = puzzle.__name__
hgnc_to_omim_path = os.path.join('resources', 'hgnc_to_omim.json')
cytoband_path = os.path.join('resources', 'cytoBand.txt.gz')
schema_path = os.path.join('configs', 'schema.sql')

converter_file = pkg_resources.resource_string(resource_package, hgnc_to_omim_path)
cytoband_file = os.path.join(resource_package, cytoband_path)

HGNC_TO_OMIM = json.loads(converter_file.decode('utf-8'))

CYTOBANDS = {}

with gzip.open(cytoband_file, 'r') as cytobands:
    for line in cytobands:
        line = line.rstrip().split('\t')
        chrom = line[0].strip('chr')
        start = int(line[1])
        stop = int(line[2])
        cytoband = line[3]
        if chrom in CYTOBANDS:
            tree = CYTOBANDS[chrom]
            tree[start:stop] = cytoband
        else:
            CYTOBANDS[chrom] = IntervalTree([Interval(start, stop, cytoband)])
