import logging

from vcftoolbox import (get_variant_dict, HeaderParser, get_info_dict,
                        get_vep_info, get_snpeff_info, get_vcf_handle)

from puzzle.models import (Compound, Variant, Gene, Genotype, Transcript,)

from puzzle.utils import (get_most_severe_consequence, get_omim_number,
                          get_cytoband_coord, get_gene_info)

logger = logging.getLogger(__name__)

class VariantMixin(object):
    """Class to store variant specific functions for vcf plugin"""

    def variant(self, case_id, variant_id):
        """Return a specific variant.

            Args:
                case_id (str): Path to vcf file
                variant_id (str): A variant id

            Returns:
                variant (Variant): The variant object for the given id
        """
        for variant_obj in self.variants(case_id, count=float('inf')):
            if variant_obj['variant_id'] == variant_id:
                return variant_obj
        return None

    def variants(self, case_id, skip=0, count=30, filters=None):
        """Return all variants in the VCF.

            Args:
                case_id (str): Path to a vcf file (for this adapter)
                skip (int): Skip first variants
                count (int): The number of variants to return
                filters (dict): A dictionary with filters. Currently this will
                look like: {
                    gene_list: [] (list of hgnc ids),
                    frequency: None (float),
                    cadd: None (float),
                    sv_len: None (float),
                    consequence: [] (list of consequences),
                    is_lof: None (Bool),
                    genetic_models [] (list of genetic models)
                    sv_type: List (list of sv types),
                }
        """
        filters = filters or {}
        case_obj = self.case(case_id=case_id)
        limit = count + skip

        raw_variants = self._get_filtered_variants(case_obj, filters)

        formated_variants = self._formated_variants(raw_variants, case_obj)

        if filters.get('frequency'):
            frequency = float(filters['frequency'])
            formated_variants = (variant for variant in formated_variants
                                 if variant['max_freq'] <= frequency)

        if filters.get('cadd'):
            cadd_score = float(filters['cadd'])
            formated_variants = (variant for variant in formated_variants
                                 if variant['max_freq'] <= cadd_score)

        if filters.get('genetic_models'):
            genetic_models = set(filters['genetic_models'])
            formated_variants = (variant for variant in formated_variants
            if set(variant.get('genetic_models',[])).intersection(genetic_models))

        if filters.get('sv_len'):
            sv_len = float(filters['sv_len'])
            formated_variants = (variant for variant in formated_variants
                                    if variant.get('sv_len') >= sv_len)

        for index, variant_obj in enumerate(formated_variants):
            if index >= skip:
                if index <= limit:
                    yield variant_obj
                else:
                    break

    def _get_filtered_variants(self, case_obj, filters={}):
        """Check if variants follows the filters

            This function will try to make filters faster for the vcf adapter

            Args:
                case_obj (puzzle.models.Case): A case object
                filters (dict): A dictionary with filters
        """

        genes = set()
        consequences = set()
        sv_types = set()

        vcf_file_path = case_obj.variant_source
        logger.info("Parsing file {0}".format(vcf_file_path))

        if filters.get('gene_ids'):
            genes = set([gene_id.strip() for gene_id in filters['gene_ids']])

        if filters.get('consequence'):
            consequences = set(filters['consequence'])

        if filters.get('sv_types'):
            sv_types = set(filters['sv_types'])

        handle = get_vcf_handle(infile=vcf_file_path)

        for variant_line in handle:
            if not variant_line.startswith('#'):
                keep_variant = True

                if genes and keep_variant:
                    keep_variant = False
                    for gene in genes:
                        if "|{0}|".format(gene) in variant_line:
                            keep_variant = True
                            break

                if consequences and keep_variant:
                    keep_variant = False
                    for consequence in consequences:
                        if consequence in variant_line:
                            keep_variant = True
                            break

                if sv_types and keep_variant:
                    keep_variant = False
                    for sv_type in sv_types:
                        if sv_type in variant_line:
                            keep_variant = True
                            break

                if keep_variant:
                    yield variant_line


    def _add_compounds(self, variant, info_dict):
        """Check if there are any compounds and add them to the variant

        """
        compound_entry = info_dict.get('Compounds')
        if compound_entry:
            for family_annotation in compound_entry.split(','):
                compounds = family_annotation.split(':')[-1].split('|')
                for compound in compounds:
                    splitted_compound = compound.split('>')

                    compound_score = None
                    if len(splitted_compound) > 1:
                        compound_id = splitted_compound[0]
                        compound_score = splitted_compound[-1]

                    variant.add_compound(Compound(
                        variant_id=compound_id,
                        combined_score=compound_score
                    ))

    def _get_genes(self, variant):
        """Add the genes for a variant

            Get the hgnc symbols from all transcripts and add them
            to the variant

            Args:
                variant (dict): A variant dictionary

            Returns:
                genes (list): A list of Genes
        """
        genes = get_gene_info(variant['transcripts'])
        return genes

    def _get_vep_transcripts(self, transcript_info):
        """Get all transcripts for a variant

            Args:
                transcript_info (dict): A dict with vep info

            Returns:
                transcript (puzzle.models.Transcript): A Transcripts
        """
        transcript = Transcript(
                hgnc_symbol = transcript_info.get('SYMBOL'),
                transcript_id = transcript_info.get('Feature'),
                ensembl_id = transcript_info.get('Gene'),
                biotype = transcript_info.get('BIOTYPE'),
                consequence = transcript_info.get('Consequence'),
                strand = transcript_info.get('STRAND'),
                sift = transcript_info.get('SIFT'),
                polyphen = transcript_info.get('PolyPhen'),
                exon = transcript_info.get('EXON'),
                HGVSc = transcript_info.get('HGVSc'),
                HGVSp = transcript_info.get('HGVSp')
            )
        return transcript

    def _get_snpeff_transcripts(self, transcript_info):
        """Get all transcripts for a variant

            Args:
                transcript_info (dict): A dict with snpeff info

            Returns:
                transcript (puzzle.models.Transcript): A Transcripts
        """
        transcript = Transcript(
                hgnc_symbol = transcript_info.get('Gene_Name'),
                transcript_id = transcript_info.get('Feature'),
                ensembl_id = transcript_info.get('Gene_ID'),
                biotype = transcript_info.get('Transcript_BioType'),
                consequence = transcript_info.get('Annotation'),
                exon = transcript_info.get('Rank'),
                HGVSc = transcript_info.get('HGVS.c'),
                HGVSp = transcript_info.get('HGVS.p')
            )
        return transcript

    def _formated_variants(self, raw_variants, case_obj):
        """Return variant objects

            Args:
                raw_variants (Iterable): An iterable with variant lines
                case_obj (puzzle.nodels.Case): A case object

        """
        vcf_file_path = case_obj.variant_source

        logger.info("Parsing file {0}".format(vcf_file_path))
        head = HeaderParser()
        handle = get_vcf_handle(infile=vcf_file_path)
        # Parse the header
        for line in handle:
            line = line.rstrip()
            if line.startswith('#'):
                if line.startswith('##'):
                    head.parse_meta_data(line)
                else:
                    head.parse_header_line(line)
            else:
                break

        handle.close()

        header_line = head.header

        # Get the individual ids for individuals in vcf file
        vcf_individuals = set([ind_id for ind_id in head.individuals])

        variant_columns = ['CHROM', 'POS', 'ID', 'REF', 'ALT', 'QUAL', 'FILTER']

        vep_header = head.vep_columns
        snpeff_header = head.snpeff_columns

        index = 0
        for variant_line in raw_variants:
            if not variant_line.startswith('#'):
                index += 1
                #Create a variant dict:
                variant_dict =  get_variant_dict(
                    variant_line = variant_line,
                    header_line = header_line
                )
                variant_dict['CHROM'] = variant_dict['CHROM'].lstrip('chrCHR')
                #Crreate a info dict:
                info_dict = get_info_dict(
                    info_line = variant_dict['INFO']
                )
                #Check if vep annotation:
                vep_string = info_dict.get('CSQ')

                #Check if snpeff annotation:
                snpeff_string = info_dict.get('ANN')

                if vep_string:
                    #Get the vep annotations
                    vep_info = get_vep_info(
                        vep_string = vep_string,
                        vep_header = vep_header
                    )

                elif snpeff_string:
                    #Get the vep annotations
                    snpeff_info = get_snpeff_info(
                        snpeff_string = snpeff_string,
                        snpeff_header = snpeff_header
                    )

                variant = Variant(
                    **{column: variant_dict.get(column, '.')
                        for column in variant_columns}
                    )

                logger.debug("Creating a variant object of variant {0}".format(
                    variant.get('variant_id')))

                variant['index'] = index
                logger.debug("Updating index to: {0}".format(
                    index))

                variant['start'] = int(variant_dict['POS'])


                if self.variant_type == 'sv':
                    other_chrom = variant['CHROM']
                    # If we have a translocation:
                    if ':' in variant_dict['ALT'] and not '<' in variant_dict['ALT']:
                        other_coordinates = variant_dict['ALT'].strip('ACGTN[]').split(':')
                        other_chrom = other_coordinates[0].lstrip('chrCHR')
                        other_position = other_coordinates[1]
                        variant['stop'] = other_position

                        #Set 'infinity' to length if translocation
                        variant['sv_len'] = float('inf')
                    else:
                        variant['stop'] = int(info_dict.get('END', variant_dict['POS']))
                        variant['sv_len'] = variant['stop'] - variant['start']

                    variant['stop_chrom'] = other_chrom

                else:
                    variant['stop'] = int(variant_dict['POS']) + \
                        (len(variant_dict['REF']) - len(variant_dict['ALT']))

                variant['sv_type'] = info_dict.get('SVTYPE')
                variant['cytoband_start'] = get_cytoband_coord(
                                                chrom=variant['CHROM'],
                                                pos=variant['start'])
                if variant.get('stop_chrom'):
                    variant['cytoband_stop'] = get_cytoband_coord(
                                                chrom=variant['stop_chrom'],
                                                pos=variant['stop'])

                # It would be easy to update these keys...
                thousand_g = info_dict.get('1000GAF')
                if thousand_g:
                    logger.debug("Updating thousand_g to: {0}".format(
                        thousand_g))
                    variant['thousand_g'] = float(thousand_g)
                    variant.add_frequency('1000GAF', variant.get('thousand_g'))

                #SV specific tag for number of occurances
                occurances = info_dict.get('OCC')
                if occurances:
                    logger.debug("Updating occurances to: {0}".format(
                        occurances))
                    variant['occurances'] = float(occurances)
                    variant.add_frequency('OCC', occurances)

                cadd_score = info_dict.get('CADD')
                if cadd_score:
                    logger.debug("Updating cadd_score to: {0}".format(
                        cadd_score))
                    variant['cadd_score'] = float(cadd_score)

                rank_score_entry = info_dict.get('RankScore')
                if rank_score_entry:
                    for family_annotation in rank_score_entry.split(','):
                        rank_score = family_annotation.split(':')[-1]
                    logger.debug("Updating rank_score to: {0}".format(
                        rank_score))
                    variant['rank_score'] = float(rank_score)

                genetic_models_entry = info_dict.get('GeneticModels')
                if genetic_models_entry:
                    genetic_models = []
                    for family_annotation in genetic_models_entry.split(','):
                        for genetic_model in family_annotation.split(':')[-1].split('|'):
                            genetic_models.append(genetic_model)
                    logger.debug("Updating rank_score to: {0}".format(
                        rank_score))
                    variant['genetic_models'] = genetic_models

                #Add genotype calls:
                for individual in case_obj.individuals:
                    sample_id = individual.ind_id

                    if sample_id in vcf_individuals:

                        raw_call = dict(zip(
                            variant_dict['FORMAT'].split(':'),
                            variant_dict[sample_id].split(':'))
                        )
                        variant.add_individual(Genotype(
                            sample_id = sample_id,
                            genotype = raw_call.get('GT', './.'),
                            case_id = individual.case_name,
                            phenotype = individual.phenotype,
                            ref_depth = raw_call.get('AD', ',').split(',')[0],
                            alt_depth = raw_call.get('AD', ',').split(',')[1],
                            genotype_quality = raw_call.get('GQ', '.'),
                            depth = raw_call.get('DP', '.'),
                            supporting_evidence = raw_call.get('SU', '0'),
                            pe_support = raw_call.get('PE', '0'),
                            sr_support = raw_call.get('SR', '0'),
                        ))

                # Add transcript information:
                gmaf = None
                if vep_string:
                    for transcript_info in vep_info:
                        transcript = self._get_vep_transcripts(transcript_info)
                        gmaf_raw = transcript_info.get('GMAF')
                        if gmaf_raw:
                            gmaf = float(gmaf_raw.split(':')[-1])
                        variant.add_transcript(transcript)

                if gmaf:
                    variant.add_frequency('GMAF', gmaf)
                    if not variant.thousand_g:
                        variant.thousand_g = gmaf

                elif snpeff_string:
                    for transcript_info in snpeff_info:
                        transcript = self._get_snpeff_transcripts(transcript_info)
                        variant.add_transcript(transcript)

                variant['most_severe_consequence'] = get_most_severe_consequence(
                    variant['transcripts']
                )

                for gene in self._get_genes(variant):
                    variant.add_gene(gene)

                self._add_compounds(variant=variant, info_dict=info_dict)

                yield variant

