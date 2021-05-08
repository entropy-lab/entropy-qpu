import os
from dataclasses import FrozenInstanceError
from glob import glob
from time import sleep

import pytest
from persistent.timestamp import _parseRaw
from quaentropy.instruments.lab_topology import LabResources, ExperimentResources
from quaentropy.results_backend.sqlalchemy.db import SqlAlchemyDB

from entropylab_qpudb import Resolver, QpuDatabaseConnection, CalState
from entropylab_qpudb._qpudatabase import (
    QpuDatabaseConnectionBase,
    create_new_qpu_database,
    QpuParameter, ReadOnlyError,
)


class AClass:
    def __init__(self):
        self.a = 3


@pytest.fixture(scope="function")
def testdb():
    testdict = {
        "q1": {"p1": 3.32, "p2": [1, 2], "p3": AClass()},
        "q2": {"p1": QpuParameter(3.4)},
        "res1": {"p1": 10},
        "system": {"num_qubits": 2},
    }
    dbname = "testdb1"
    create_new_qpu_database(dbname, testdict, force_create=True)
    yield dbname
    for fl in glob(dbname + "*"):
        os.remove(fl)


@pytest.fixture
def simp_resolver():
    class SResolver(Resolver):
        def q(self, qubit, channel=None):
            return f"q{qubit}"

        def res(self, resonator):
            return f"res{resonator}"

        def coupler(self, qubit1, qubit2):
            return f"c{qubit1}{qubit2}"

    return SResolver()


def test_open_from_path():
    testdict = {"q1": {"p1": 5}}
    os.mkdir("testdir")
    try:
        create_new_qpu_database("ptest", testdict, path="./testdir")
        assert os.path.exists("testdir/ptest.fs")
        db = QpuDatabaseConnectionBase("ptest", path="testdir")
        assert db.get("q1", "p1").value == 5
        db.close()
    finally:
        for fl in glob("testdir/*"):
            os.remove(fl)
        os.rmdir("testdir")


def test_open_without_creation():
    with pytest.raises(FileNotFoundError):
        QpuDatabaseConnectionBase("testdb2")


def test_simple_get(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        print(db.get("q2", "p1"))
        print(db.get("q1", "p1"))
        assert db.get("q1", "p1").value == 3.32
        assert db.get("q2", "p1").value == 3.4


def test_simple_set_no_commit(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.set("q2", "p1", 10.0)
        print(db.get("q2", "p1"))
        assert db.get("q2", "p1").value == 10.0

    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.get("q2", "p1")
        assert db.get("q2", "p1").value == 3.4


def test_simple_set_with_commit(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.set("q2", "p1", 11.0)
        print(db.get("q2", "p1"))
        db.commit()
        assert len(db.get_history()) == 2

    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        assert len(db.get_history()) == 2
        print(db.get("q2", "p1"))
        assert db.get("q2", "p1").value == 11.0


def test_impossible_to_set_via_get(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        with pytest.raises(FrozenInstanceError):
            db.get("q2", "p1").value = -10.0


def test_set_with_commit_multiple(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.set("q2", "p1", 11.0)
        print(db.get("q2", "p1"))
        assert len(db.get_history()) == 1
        db.commit()
        assert len(db.get_history()) == 2

    with QpuDatabaseConnectionBase(testdb) as db:
        db.set("q1", "p1", [1, 2])
        db.commit()
        assert len(db.get_history()) == 3

    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        print(db.get("q2", "p1"))
        print(db.get("q1", "p1"))
        assert db.get("q2", "p1").value == 11.0
        assert db.get("q1", "p1").value == [1, 2]


def test_set_with_commit_history(testdb):
    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        db.set("q2", "p1", 11.0)
        print(db.get("q2", "p1"))
        db.commit("my first commit")

    sleep(0.5)

    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        db.set("q1", "p1", [1, 2])
        db.commit("my second commit")

    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        print(db.get("q2", "p1"))
        print(db.get("q1", "p1"))
        assert db.get("q2", "p1").value == 11.0
        assert db.get("q1", "p1").value == [1, 2]

    # open historical connection

    with QpuDatabaseConnection(testdb, simp_resolver, history_index=1) as db:
        print()
        print(db.get("q2", "p1"))
        print(db.get("q1", "p1"))
        assert db.get("q2", "p1").value == 11.0
        assert db.get("q1", "p1").value == 3.32

    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print(db.get_history())


def test_fail_on_commit_to_readonly(testdb):
    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        db.set("q2", "p1", 11.0)
        print(db.get("q2", "p1"))
        db.commit("my first commit")

    sleep(0.5)

    # open historical connection

    # should fail when DB is modified
    with QpuDatabaseConnection(testdb, simp_resolver, history_index=0) as db:
        db.set('q1', 'p1', 444)
        with pytest.raises(ReadOnlyError):
            db.commit('trying')

    # should fail when DB is not modified
    with QpuDatabaseConnection(testdb, simp_resolver, history_index=0) as db:
        with pytest.raises(ReadOnlyError):
            db.commit('trying')


def test_commit_unmodified(testdb):
    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        print(_parseRaw(db._con._db.lastTransaction()))
        assert len(db.get_history()) == 1
        db.commit("my first commit - unmodified")
        print(_parseRaw(db._con._db.lastTransaction()))
        assert len(db.get_history()) == 1


def test_restore_from_history(testdb):
    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        db.set("q2", "p1", 11.0)
        print(db.get("q2", "p1"))
        db.commit("my first commit")

    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        assert db.get("q2", "p1").value == 11.0
        db.restore_from_history(0)
        print(db.get("q2", "p1"))
        assert db.get("q2", "p1").value == 3.4

    # make sure wasn't committed
    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        assert db.get("q2", "p1").value == 11.0


def test_print(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.print()
        db.print("q1")


def test_without_cm(testdb):
    qpudb = QpuDatabaseConnectionBase(testdb)
    try:
        qpudb.set("q1", "p1", 20)
        print(qpudb.get("q1", "p1").value == 20)
    finally:
        qpudb.close()


def test_add_attributes(testdb):
    # todo: fix this with add function
    with QpuDatabaseConnectionBase(testdb) as db:
        with pytest.raises(AttributeError):
            db.set("q1", "p_new", 44)

    with QpuDatabaseConnectionBase(testdb) as db:
        db.add_attribute("q1", "p_new")
        assert db.get("q1", "p_new").value == None


def test_add_attributes_no_persistence(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        db.add_attribute("q1", "p_new", -5, CalState.FINE)
        assert db.get("q1", "p_new").value == -5
        assert db.get("q1", "p_new").cal_state == CalState.FINE

    with QpuDatabaseConnectionBase(testdb) as db:
        with pytest.raises(AttributeError):
            assert db.get("q1", "p_new").value == -5


def test_add_attributes_persistence(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        db.add_attribute("q1", "p_new", -5, CalState.FINE)
        assert db.get("q1", "p_new").value == -5
        assert db.get("q1", "p_new").cal_state == CalState.FINE
        db.commit()

    with QpuDatabaseConnectionBase(testdb) as db:
        assert db.get("q1", "p_new").value == -5
        assert db.get("q1", "p_new").cal_state == CalState.FINE


def test_add_elements(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        db.add_element("q_new")
        db.add_attribute("q_new", "p_new", "something")
        assert db.get("q_new", "p_new").value == "something"

    with QpuDatabaseConnectionBase(testdb) as db:
        with pytest.raises(AttributeError):
            assert db.add_element("q1")


def test_add_elements_persistence(testdb):
    with QpuDatabaseConnectionBase(testdb) as db:
        db.add_element("q_new")
        db.add_attribute("q_new", "p_new", "something")
        db.commit()

    with QpuDatabaseConnectionBase(testdb) as db:
        assert db.get("q_new", "p_new").value == "something"


def test_with_resolver(testdb, simp_resolver):
    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        db.update_q(1, "p1", 555)
        print(db.q(1).p1.value)
        assert db.q(1).p1.value == 555

    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        assert db.res(1).p1.value == 10
        assert db.system().num_qubits.value == 2
        assert db.num_qubits == 2


def test_use_in_entropy(testdb, simp_resolver):
    try:
        entropydb_name, qpudb_name = "entropy.db", testdb
        entropydb = SqlAlchemyDB(entropydb_name)
        lab_resources = LabResources(entropydb)
        lab_resources.register_resource(
            qpudb_name, QpuDatabaseConnection, [qpudb_name, simp_resolver]
        )

        experiment_resources = ExperimentResources(entropydb)
        experiment_resources.import_lab_resource(testdb)
        print(experiment_resources.get_resource(testdb).get("q1", "p1"))
        assert experiment_resources.get_resource(testdb).get("q1", "p1").value == 3.32
        experiment_resources.save_snapshot(qpudb_name, "a_snapshot")
        # todo: verify that we can load from snapshot
        experiment_resources.get_resource(testdb).close()
    finally:
        os.remove("entropy.db")
