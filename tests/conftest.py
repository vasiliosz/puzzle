# -*- coding: utf-8 -*-
import pytest
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# from puzzle.factory import create_app
from puzzle.models import Variant
from puzzle.models.sql import BASE
from puzzle.plugins import VcfPlugin, SqlStore
from puzzle.utils import get_case
# from puzzle.settings import TestConfig

from puzzle.log import configure_stream

root_logger = configure_stream()
logger = logging.getLogger(__name__)


@pytest.fixture
def vcf():
    db = VcfPlugin()
    return db


@pytest.fixture
def variant():
    """Return a variant dictionary"""
    data = dict(CHROM='1', POS='100', ID='rs01', REF='A', ALT='T', QUAL='100',
                FILTER='PASS')
    variant = Variant(**data)
    return variant


@pytest.fixture(scope='session')
def session(request):
    """Create and return a session to a sqlite database"""
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()

    session = sessionmaker()
    session.configure(bind=engine)
    BASE.metadata.create_all(engine)

    s = session()

    def teardown():
        print('\n')
        logger.info("Teardown sqlite database")
        s.close()
        connection.close()
    request.addfinalizer(teardown)

    return s


@pytest.yield_fixture(scope='session')
def ped_lines():
    """Return an unformatted list of ped lines."""
    _ped_lines = [
        "636808\tADM1059A1\t0\t0\t1\t1",
        "636808\tADM1059A2\tADM1059A1\tADM1059A3\t1\t2",
        "636808\tADM1059A3\t0\t0\t2\t1"
    ]
    yield _ped_lines


@pytest.yield_fixture(scope='session')
def case_obj(ped_lines):
    """Return a test case object with individuals."""
    _case = get_case('test.vcf', case_lines=ped_lines)
    yield _case


@pytest.yield_fixture(scope='function')
def sql_store():
    """Setup an in-memory database."""
    _test_db = SqlStore('sqlite:///:memory:')
    _test_db.set_up()
    yield _test_db
    _test_db.tear_down()


@pytest.yield_fixture(scope='function')
def test_db(sql_store, case_obj):
    """Populate database with some sample data."""
    sql_store.add_case(case_obj)
    yield sql_store
    sql_store.tear_down()
    sql_store.set_up()
