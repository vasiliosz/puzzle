# -*- coding: utf-8 -*-
import os
import logging

from path import path

from puzzle.models import (Case, Compound, Variant, Gene, Genotype, Transcript,
                            Individual)
from puzzle.utils import (get_most_severe_consequence, get_hgnc_symbols,
                          get_omim_number, get_ensembl_id)

from puzzle.plugins import Plugin

from vcftoolbox import (get_variant_dict, HeaderParser, get_info_dict,
                        get_vep_dict)

from ped_parser import FamilyParser

logger = logging.getLogger(__name__)

class FamilyPlugin(Plugin):
    """Plugin for dealing with vcf files when using a family file.
        
        In this case only one vcf is used but it can include multiple
        cases. Since we know from the family file what individuals is included
        we can save the information in a different way than in the VcfPlugin
    """
    
    def __init__(self):
        super(FamilyPlugin, self).__init__()
    
    def init_app(self, app):
        """Initialize plugin via Flask."""
        logger.debug("Updating root path to {0}".format(
            app.config['PUZZLE_ROOT']
        ))
        self.vcf_path = app.config['PUZZLE_ROOT']
        self.head = self._get_header(self.vcf_path)

        self.case_objs = []
        self.individuals = []

        self.header_line = self.head.header
        vcf_individuals = self.head.individuals
        
        case_ids = set()
        with open(app.config['FAMILY_FILE'], 'r') as family_file:
            family_parser = FamilyParser(
                family_info=family_file,
                family_type=app.config['FAMILY_TYPE']
                )
        
        for ind_id in family_parser.individuals:
            individual = family_parser.individuals[ind_id]
            logger.info("Found individual {0} with family id {1}".format(
                ind_id, individual.family))
            
            if ind_id not in vcf_individuals:
                logger.error("Individual {0} is not in vcf".format(
                    individual
                ))
                logger.info("All individuals from ped file has to be present in"\
                            "the vcf file.")
                ##TODO raise a more specific exception here
                raise SyntaxError
            
            self.individuals.append(
                Individual(
                    ind_id=individual.individual_id, 
                    case_id=individual.family, 
                    mother=individual.mother, 
                    father=individual.father,
                    sex=individual.sex,
                    phenotype=individual.phenotype,
                    variant_source=self.vcf_path, 
                    bam_path=None)
            )
            
            case_ids.add(individual.family)
        
        # Add the cases to the adapter
        for case_id in case_ids:
            case = Case(
                case_id=case_id,
                name=case_id
                )
            # Add the individuals to the correct case
            for individual in self.individuals:
                if individual['case_id'] == case_id:
                    logger.info("Adding ind {0} to case {1}".format(
                        individual['name'], individual['case_id']
                    ))
                    case.add_individual(individual)
            logger.info("Adding case {0} to adapter.".format(case_id))
            self.case_objs.append(case)
        
    
    def _get_header(self, vcf_file_path):
        """Return a HeaderParser
        
            Args:
                vcf_file_path (str): Path to a vcf file
            
            Returns:
                head (HeaderParser): A header object
        """
        head = HeaderParser()
        
        with open(vcf_file_path, 'r') as variant_file:
            for line in variant_file:
                line = line.rstrip()
                if line.startswith('#'):
                    if line.startswith('##'):
                        head.parse_meta_data(line)
                    else:
                        head.parse_header_line(line)
                else:
                    break
        return head
    
    
    def cases(self, pattern=None):
        """Return all VCF file paths."""
        
        return case_objs

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
        genes = []
        hgnc_symbols = get_hgnc_symbols(
            transcripts = variant['transcripts']
        )
        for hgnc_id in hgnc_symbols:
            genes.append(Gene(
                symbol=hgnc_id,
                omim_number=get_omim_number(hgnc_id),
                ensembl_id=get_ensembl_id(hgnc_id)
                )
            )
        return genes
    
    def _get_transcripts(self, variant, vep_dict):
        """Get all transcripts for a variant
        
            Args:
                vep_dict (dict): A vep dict
            
            Returns:
                transcripts (list): A list of transcripts
        """
        transcripts = []
        for allele in vep_dict:
            for transcript_info in vep_dict[allele]:
                transcripts.append(Transcript(
                    SYMBOL = transcript_info.get('SYMBOL'),
                    Feature = transcript_info.get('Feature'),
                    BIOTYPE = transcript_info.get('BIOTYPE'),
                    Consequence = transcript_info.get('Consequence'),
                    STRAND = transcript_info.get('STRAND'),
                    SIFT = transcript_info.get('SIFT'),
                    PolyPhen = transcript_info.get('PolyPhen'),
                    EXON = transcript_info.get('EXON'),
                    HGVSc = transcript_info.get('HGVSc'),
                    HGVSp = transcript_info.get('HGVSp')
                ))
        return transcripts

    def _variants(self, vcf_file_path):
        head = HeaderParser()
        # Parse the header
        with open(vcf_file_path, 'r') as variant_file:
            for line in variant_file:
                line = line.rstrip()
                if line.startswith('#'):
                    if line.startswith('##'):
                        head.parse_meta_data(line)
                    else:
                        head.parse_header_line(line)
                else:
                    break

        header_line = head.header
        individuals = head.individuals

        variant_columns = ['CHROM', 'POS', 'ID', 'REF', 'ALT', 'QUAL', 'FILTER']

        vep_header = head.vep_columns

        with open(vcf_file_path, 'r') as vcf_file:
            index = 0
            for variant_line in vcf_file:
                if not variant_line.startswith('#'):
                    index += 1
                    #Create a variant dict:
                    variant_dict =  get_variant_dict(
                        variant_line = variant_line,
                        header_line = header_line
                    )
                    #Crreate a info dict:
                    info_dict = get_info_dict(
                        info_line = variant_dict['INFO']
                    )
                    vep_string = info_dict.get('CSQ')

                    if vep_string:
                        vep_dict = get_vep_dict(
                            vep_string = vep_string,
                            vep_header = vep_header
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

                    variant['stop'] = int(variant_dict['POS']) + \
                        (len(variant_dict['REF']) - len(variant_dict['ALT']))

                    # It would be easy to update these keys...
                    thousand_g = info_dict.get('1000GAF')
                    if thousand_g:
                        logger.debug("Updating thousand_g to: {0}".format(
                            thousand_g))
                        variant['thousand_g'] = float(thousand_g)
                    variant.add_frequency('1000GAF', variant.get('thousand_g'))

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
                    if individuals:
                        for sample_id in individuals:
                            raw_call = dict(zip(
                                variant_dict['FORMAT'].split(':'),
                                variant_dict[sample_id].split(':'))
                            )
                            variant.add_individual(Genotype(
                                sample_id = sample_id,
                                genotype = raw_call.get('GT', './.'),
                                ref_depth = raw_call.get('AD', ',').split(',')[0],
                                alt_depth = raw_call.get('AD', ',').split(',')[1],
                                genotype_quality = raw_call.get('GQ', '.'),
                                depth = raw_call.get('DP', '.')
                            ))

                    # Add transcript information:
                    if vep_string:
                        for transcript in self._get_transcripts(variant, vep_dict):
                            variant.add_transcript(transcript)

                    variant['most_severe_consequence'] = get_most_severe_consequence(
                        variant['transcripts']
                    )
                    for gene in self._get_genes(variant):
                        variant.add_gene(gene)
                    
                    self._add_compounds(variant=variant, info_dict=info_dict)
                    
                    yield variant

    def variants(self, case_id, skip=0, count=30, gene_list=None,
                 thousand_g=None):
        """Return all variants in the VCF.

            Args:
                case_id (str): Path to a vcf file (for this adapter)
                skip (int): Skip first variants
                count (int): The number of variants to return
                gene_list (list): A list of genes
                thousand_g (float): filter variants based on frequency
        """
        vcf_path = case_id.replace('|', '/')
        limit = count + skip

        filtered_variants = self._variants(vcf_path)
        
        if gene_list:
            gene_list = set(gene_list)
            filtered_variants = (variant for variant in filtered_variants
                                 if (set(gene['symbol'] for gene in variant['genes'])
                                     .intersection(gene_list)))
        if thousand_g:
            filtered_variants = (variant for variant in filtered_variants
                                 if variant['thousand_g'] <= thousand_g)

        for index, variant_obj in enumerate(filtered_variants):
            if index >= skip:
                if index <= limit:
                    yield variant_obj
                else:
                    break

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


if __name__ == '__main__':
    import sys
    from pprint import pprint as pp
    vcf_file = sys.argv[1]
    plugin = VcfPlugin()
    for variant in plugin.variants(case_id=vcf_file):
        print(variant)
        print('')
