# -*- coding: utf-8 -*-


class Individual(dict):
    """Individual representation."""
    def __init__(self, ind_id, case_id=None, mother=None, 
    father=None, sex=None, phenotype = None, index=None, 
    variant_source=None, bam_path=None):
        """Construct a individual object
            
            Args:
                ind_id (str): The individual id
                case_id (str): What case it belongs to
                mother (str): The mother id
                father (str): The father id
                sex (str): Sex in ped format
                phenotype (str): Phenotype in ped format
                index (int): Either the column in the vcf or what position in
                             the gemini database the individual represents.
                variant_source (str): Path to source (vcf file)
                bam_path (str): Path to bamfiles (vcf file)
        """
        super(Individual, self).__init__(id=ind_id, name=name or ind_id, 
                case_id=case_id, mother=mother, father=father, sex=sex,
                phenotype=phenotype, index=index, variant_source=variant_source,
                bam_path=bam_path)
