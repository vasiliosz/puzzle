# -*- coding: utf-8 -*-
import logging

from puzzle.models.dotdict import DotDict

logger = logging.getLogger(__name__)


class Plugin(object):
    """docstring for Plugin"""
    def __init__(self):
        super(Plugin, self).__init__()
        self.db = None
        self.puzzle_db = None
        self.individuals = None
        self.case_obj = None
        self.variant_type = 'snv'
        self.filters = DotDict(
            can_filter_frequency=False,
            can_filter_cadd=False,
            can_filter_consequence=False,
            can_filter_gene=False,
            can_filter_inheritance=False,
            can_filter_sv=False
        )

    def init_app(self, app):
        """Initialize plugin via Flask."""
        self.root_path = app.config['PUZZLE_ROOT']
        self.pattern = app.config['PUZZLE_PATTERN']

    def cases(self, pattern=None):
        """Return all cases."""
        raise NotImplementedError

    def variants(self, case_id, skip=0, count=30, filters=None):
        """Return count variants for a case.

        """
        raise NotImplementedError

    def variant(self, variant_id):
        """Return a specific variant."""
        raise NotImplementedError

    def individual_dict(self, ind_ids):
        """Return a dict with ind_id as key and Individual as values."""
        ind_dict = {ind.ind_id: ind for ind in self.individuals(ind_ids=ind_ids)}
        return ind_dict
