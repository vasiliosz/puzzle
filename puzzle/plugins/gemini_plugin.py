# -*- coding: utf-8 -*-
import logging
from sqlite3 import OperationalError

from gemini import GeminiQuery
from puzzle.plugins import Plugin
from puzzle.models import (Variant, Genotype, Gene, Transcript, Case, Individual)
from puzzle.utils import (get_omim_number, get_ensembl_id, get_hgnc_symbols,
                          get_most_severe_consequence)
from puzzle.exceptions import DatabaseError

logger = logging.getLogger(__name__)

class GeminiPlugin(Plugin):
    """This is the base class for puzzle plugins"""

    def __init__(self):
        super(GeminiPlugin, self).__init__()
        
        
    def init_app(self, app):
        """Initialize plugin via Flask."""
        logger.debug("Updating root path to {0}".format(
            app.config['PUZZLE_ROOT']
        ))
        self.db = app.config['PUZZLE_ROOT']
        logger.debug("Updating pattern to {0}".format(
            app.config['PUZZLE_ROOT']
        ))
        self.case_objs = []
        self.individuals = []
        
        case_ids = set()
        logger.info("Looking for cases in {0}".format(
            self.db
        ))
        gq = GeminiQuery(self.db)
        #Dictionaru with sample to index in the gemini database
        sample_to_idx = gq.sample_to_idx
        
        query = "SELECT * from samples"
        gq.run(query)
        for individual in gq:
            logger.info("Found individual {0} with family id {1}".format(
                individual['name'], individual['family_id']))
            self.individuals.append(
                Individual(
                    ind_id=individual['name'], 
                    case_id=individual['family_id'], 
                    mother=individual['maternal_id'], 
                    father=individual['paternal_id'],
                    sex=individual['sex'],
                    phenotype=individual['sex'],
                    index=sample_to_idx.get(individual['name']), 
                    variant_source=self.db, 
                    bam_path=None)
            )
            case_ids.add(individual['family_id'])
        
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
        
    
    def cases(self, pattern=None):
        """Return all cases."""
        
        return self.case_objs

    def _get_individuals(self, gemini_variant, individual_objs):
        """Add the genotypes for a variant for all individuals
        
            Args:
                gemini_variant (GeminiQueryRow): The gemini variant
                individual_objs (list(dict)): A list of Individuals
            
            Returns:
                individuals (list) A list of Genotypes
        """
        individuals = []
        for ind in individual_objs:
            index = ind['index']
            individuals.append(Genotype(
                sample_id=ind['ind_id'], 
                genotype=gemini_variant['gts'][index], 
                ref_depth=gemini_variant['gt_ref_depths'][index], 
                alt_depth=gemini_variant['gt_alt_depths'][index],
                depth=gemini_variant['gt_depths'][index],
                genotype_quality=gemini_variant['gt_quals'][index]
            ))
        
        return individuals
    
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
    
    def _get_transcripts(self, gemini_variant):
        """Return a Transcript object
            
            Gemini stores the information for the most severe transcript
            so only one transcript is connected to one variant.
            
            Args:
                gemini_variant (GeminiQueryRow): The gemini variant
            
            Returns:
                transcripts list: List of affected transcripts
        
        """
        query = "SELECT * from variant_impacts WHERE variant_id = {0}".format(
            gemini_variant['variant_id']
        )
        gq = GeminiQuery(self.db)
        gq.run(query)
        
        transcripts = []
        for transcript in gq:
            transcripts.append(Transcript(
                SYMBOL=transcript['gene'], 
                Feature=transcript['transcript'], 
                Consequence=transcript['impact_so'],
                BIOTYPE=transcript['biotype'],
                PolyPhen=transcript['polyphen_pred'],
                SIFT=transcript['sift_pred'],
                HGVSc = transcript['codon_change'],
                HGVSp = transcript['aa_change']
                
                )
            )
        return transcripts
    
    def _is_variant(self, gemini_variant, indexes):
        """Check if the variants is a variation in any of the individuals
        
            Args:
                gemini_variant (GeminiQueryRow): The gemini variant
                indexes (list(int)): A list of indexes for the individuals
            
            Returns:
                bool : If any of the individuals has the variant
        """
        
        for index in indexes:
            if gemini_variant['gts'][index] != 0:
                return True
        
        return False

    def _format_variant(self, gemini_variant, individual_objs, index=0):
        """Make a puzzle variant from a gemini variant

            Args:
                gemini_variant (GeminiQueryRow): The gemini variant
                individual_objs (list(dict)): A list of Individuals
                index(int): The index of the variant
            
            Returns:
                variant (dict): A Variant object
        """
        variant_dict = {
            'CHROM':gemini_variant['chrom'].lstrip('chr'),
            'POS':str(gemini_variant['start']),
            'ID':gemini_variant['rs_ids'],
            'REF':gemini_variant['ref'],
            'ALT':gemini_variant['alt'],
            'QUAL':gemini_variant['qual'],
            'FILTER':gemini_variant['filter']
        }
    
        variant = Variant(**variant_dict)
        variant['index'] = index
        
        # Use the gemini id for fast search
        variant.update_variant_id(gemini_variant['variant_id'])
        # Update the individuals
        individual_genotypes = self._get_individuals(
            gemini_variant=gemini_variant, 
            individual_objs=individual_objs
            )
        
        for individual in individual_genotypes:
            # Add the genotype calls to the variant
            variant.add_individual(individual)
    
        for transcript in self._get_transcripts(gemini_variant):
            variant.add_transcript(transcript)
    
        variant['most_severe_consequence'] = get_most_severe_consequence(
            variant['transcripts']
        )
    
        for gene in self._get_genes(variant):
            variant.add_gene(gene)
    
        #### Check the impact annotations ####
        if gemini_variant['cadd_scaled']:
            variant['cadd_score'] = gemini_variant['cadd_scaled']
    
        # We use the prediction in text
        polyphen = gemini_variant['polyphen_pred']
        if polyphen:
            variant.add_severity('Polyphen', polyphen)

        # We use the prediction in text
        sift = gemini_variant['sift_pred']
        if sift:
            variant.add_severity('SIFT', sift)
    
        #### Check the frequencies ####
        thousand_g = gemini_variant['aaf_1kg_all']
        if thousand_g:
            variant['thousand_g'] = float(thousand_g)
            variant.add_frequency(name='1000GAF', value=float(thousand_g))
    
        exac = gemini_variant['aaf_exac_all']
        if exac:
            variant.add_frequency(name='EXaC', value=float(exac))

        esp = gemini_variant['aaf_esp_all']
        if esp:
            variant.add_frequency(name='ESP', value=float(esp))
        
        max_freq = gemini_variant['max_aaf_all']
        if max_freq:
            variant.set_max_freq(max_freq)
        
        return variant
        
    def _variants(self, case_id, gemini_query):
        """Return variants found in the gemini database
        
            Args:
                case_id (str): The case for which we want to see information
                gemini_query (str): What variants should be chosen
            
            Yields:
                variant_obj (dict): A Variant formatted doctionary
        """
        
        gq = GeminiQuery(self.db)
        
        gq.run(gemini_query)
        
        individuals = []
        # Get the individuals for the case
        for case in self.cases():
            if case['name'] == case_id:
                for individual in case['individuals']:
                    individuals.append(individual)
        
        indexes = [individual['index'] for individual in individuals]
        
        index = 0
        for gemini_variant in gq:
            # Check if variant is non ref in the individuals
            if self._is_variant(gemini_variant, indexes):
                index += 1
                logger.debug("Updating index to: {0}".format(index))
                
                variant = self._format_variant(
                    gemini_variant=gemini_variant, 
                    individual_objs=individuals, 
                    index=index
                )
                yield variant
            
        
    
    def variants(self, case_id, skip=0, count=30, gene_list=None, 
                    frequency=None, cadd=None):
        """Return count variants for a case.
            
            case_id : A gemini db
            skip (int): Skip first variants
            count (int): The number of variants to return
            gene_list (list): A list of genes
            frequency (float): filter variants based on frequency
            
        """
        logger.debug("Looking for variants in {0}".format(case_id))
        
        limit = count + skip
        
        gemini_query = "SELECT * from variants"
        
        #This would be the fastest solution but it seems like we loose all variants
        #that are missing a frequency...
        any_filter = None
        if frequency:
            gemini_query += " WHERE (max_aaf_all < {0} or max_aaf_all is"\
                            " Null)".format(frequency)
            any_filter = True
        
        if cadd:
            if any_filter:
                gemini_query += " AND (cadd_scaled > {0})".format(cadd)
            else:
                gemini_query += " WHERE (cadd_scaled > {0})".format(cadd)
            any_filter = True
            
        filtered_variants = self._variants(
            case_id=case_id,
            gemini_query=gemini_query)
        
        if gene_list:
            gene_list = set(gene_list)
            filtered_variants = (variant for variant in filtered_variants
                                 if (set(gene['symbol'] for gene in variant['genes'])
                                     .intersection(gene_list)))

        for index, variant_obj in enumerate(filtered_variants):
            if index >= skip:
                if index < limit:
                    yield variant_obj
                else:
                    break
        
        
    def variant(self, case_id, variant_id):
        """Return a specific variant.
        
            We solve this by building a gemini query and send it to _variants
            
            Args:
                case_id (str): Path to a gemini database
                variant_id (int): A gemini variant id
            
            Returns:
                variant_obj (dict): A puzzle variant
                
        """
        variant_id = int(variant_id)
        gemini_query = "SELECT * from variants WHERE variant_id = {0}".format(
            variant_id
        )
        
        individuals = []
        # Get the individuals for the case
        for case in self.cases():
            if case['name'] == case_id:
                for individual in case['individuals']:
                    individuals.append(individual)
        
        gq = GeminiQuery(self.db)
        
        gq.run(gemini_query)
        
        for gemini_variant in gq:
            variant = self._format_variant(
                gemini_variant=gemini_variant, 
                individual_objs=individuals, 
                index=gemini_variant['variant_id']
            )
            
            return variant
        
        return None
        
if __name__ == '__main__':
    import sys
    from pprint import pprint as pp
    from puzzle.log import configure_stream
    configure_stream(level="DEBUG")
    gemini_db = sys.argv[1]
    plugin = GeminiPlugin()
    
    for case in plugin.cases(gemini_db):
        print("Case found: {0}".format(case))
    # try:
    #     for variant in plugin.variants(gemini_db, thousand_g=0.01):
    #         # print(variant['thousand_g'])
    #         pp(variant)
    # except DatabaseError as e:
    #     logger.info("Exiting...")
    #     sys.exit()
    # try:
    #     for variant in plugin.variant(gemini_db, variant_id=3):
    #         print(variant)
    # except DatabaseError as e:
    #     logger.info("Exiting...")
    #     sys.exit()

