import os
from dataclasses import FrozenInstanceError
from glob import glob
from time import sleep

import pytest
from entropylab.instruments.lab_topology import LabResources, ExperimentResources
from entropylab.results_backend.sqlalchemy.db import SqlAlchemyDB
from persistent.timestamp import _parseRaw

from entropylab_qpudb import Resolver, QpuDatabaseConnection, CalState
from entropylab_qpudb._qpudatabase import (
    _QpuDatabaseConnectionBase,
    create_new_qpu_database,
    ReadOnlyError,
)
from entropylab_qpudb._qpudb_basedefs import QpuParameter


class AClass:
    def __init__(self):
        self.a = 3

    def __eq__(self, other):
        return self.a == other.a


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


class SResolver(Resolver):
    def q(self, qubit, channel=None):
        return f"q{qubit}"

    def res(self, resonator):
        return f"res{resonator}"

    def coupler(self, qubit1, qubit2):
        return f"c{qubit1}{qubit2}"


@pytest.fixture
def simp_resolver():
    return SResolver()


def test_open_with_default_resolver(testdb):
    with QpuDatabaseConnection(testdb) as db:
        assert db.q(1).p1.value == 3.32
        print(db.q(1).p1)
        db.add_element(
            db._resolver.coupler(1, 2)
        )  # todo: add methods for adding specific element types
        db.add_attribute(db._resolver.coupler(1, 2), "xx", 20)
        print(db.coupler(1, 2).xx)
        assert db.coupler(1, 2).xx.value == 20
        assert db.coupler(2, 1).xx.value == 20


def test_open_empty():
    try:
        create_new_qpu_database("ptest")
        db = _QpuDatabaseConnectionBase("ptest")
        db.close()
    finally:
        for fl in glob("ptest*"):
            os.remove(fl)


def test_open_from_path():
    testdict = {"q1": {"p1": 5}}
    os.mkdir("testdir")
    try:
        create_new_qpu_database("ptest", testdict, path="./testdir")
        assert os.path.exists("testdir/ptest.fs")
        db = _QpuDatabaseConnectionBase("ptest", path="testdir")
        assert db.get("q1", "p1").value == 5
        db.close()
    finally:
        for fl in glob("testdir/*"):
            os.remove(fl)
        os.rmdir("testdir")


def test_open_without_creation():
    with pytest.raises(FileNotFoundError):
        _QpuDatabaseConnectionBase("testdb2")


def test_open_on_existing_connection_fail(testdb):
    db1 = _QpuDatabaseConnectionBase(testdb)
    with pytest.raises(ConnectionError):
        db2 = _QpuDatabaseConnectionBase(testdb)


def test_open_on_existing_connection_succeed(testdb):
    db1 = _QpuDatabaseConnectionBase(testdb)
    db1.close()
    db2 = _QpuDatabaseConnectionBase(testdb)


def test_simple_get(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        print(db.get("q2", "p1"))
        print(db.get("q1", "p1"))
        assert db.get("q1", "p1").value == 3.32
        assert db.get("q2", "p1").value == 3.4


def test_simple_set_no_commit(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.set("q2", "p1", 10.0)
        print(db.get("q2", "p1"))
        assert db.get("q2", "p1").value == 10.0

    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.get("q2", "p1")
        assert db.get("q2", "p1").value == 3.4


def test_modify_cal_state(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.set("q2", "p1", 10.0, new_cal_state=CalState.COARSE)
        print(db.get("q2", "p1"))
        assert db.get("q2", "p1").value == 10.0
        assert db.get("q2", "p1").cal_state == CalState.COARSE


def test_do_not_modify_cal_state(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.set("q2", "p1", 10.0, new_cal_state=CalState.COARSE)
        db.set("q2", "p1", 9.0)
        print(db.get("q2", "p1"))
        assert db.get("q2", "p1").value == 9.0
        assert db.get("q2", "p1").cal_state == CalState.COARSE


def test_simple_set_with_commit(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.set("q2", "p1", 11.0, new_cal_state=CalState.FINE)
        print(db.get("q2", "p1"))
        db.commit()
        assert len(db.get_history()) == 2

    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        assert len(db.get_history()) == 2
        print(db.get("q2", "p1"))
        assert db.get("q2", "p1").value == 11.0
        assert db.get("q2", "p1").cal_state == CalState.FINE


def test_impossible_to_set_via_get(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        with pytest.raises(FrozenInstanceError):
            db.get("q2", "p1").value = -10.0


def test_set_with_commit_multiple(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.set("q2", "p1", 11.0)
        print(db.get("q2", "p1"))
        assert len(db.get_history()) == 1
        db.commit()
        assert len(db.get_history()) == 2

    with _QpuDatabaseConnectionBase(testdb) as db:
        db.set("q1", "p1", [1, 2])
        db.commit()
        assert len(db.get_history()) == 3

    with _QpuDatabaseConnectionBase(testdb) as db:
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
    with QpuDatabaseConnection(testdb, simp_resolver, history_index=1) as db:
        db.set("q1", "p1", 444)
        with pytest.raises(ReadOnlyError):
            db.commit("trying")

    # should fail when DB is not modified
    with QpuDatabaseConnection(testdb, simp_resolver, history_index=1) as db:
        with pytest.raises(ReadOnlyError):
            db.commit("trying")


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
        db.set("q2", "p1", 3.4)
        db.commit("my first commit")
        print()
        db.set("q2", "p1", 11.0)
        print(db.get("q2", "p1"))
        db.commit("my second commit")

    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        assert db.get("q2", "p1").value == 11.0
        db.restore_from_history(1)
        print(db.get("q2", "p1"))
        assert db.get("q2", "p1").value == 3.4

    # make sure wasn't committed
    with QpuDatabaseConnection(testdb, simp_resolver) as db:
        print()
        assert db.get("q2", "p1").value == 11.0


def test_print(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        print()
        db.print()
        db.print("q1")


def test_without_cm(testdb):
    qpudb = _QpuDatabaseConnectionBase(testdb)
    try:
        qpudb.set("q1", "p1", 20)
        print(qpudb.get("q1", "p1").value == 20)
    finally:
        qpudb.close()


def test_add_attributes(testdb):
    # todo: fix this with add function
    with _QpuDatabaseConnectionBase(testdb) as db:
        with pytest.raises(AttributeError):
            db.set("q1", "p_new", 44)

    with _QpuDatabaseConnectionBase(testdb) as db:
        db.add_attribute("q1", "p_new")
        assert db.get("q1", "p_new").value is None


def test_add_attributes_no_persistence(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        db.add_attribute("q1", "p_new", -5, CalState.FINE)
        assert db.get("q1", "p_new").value == -5
        assert db.get("q1", "p_new").cal_state == CalState.FINE

    with _QpuDatabaseConnectionBase(testdb) as db:
        with pytest.raises(AttributeError):
            assert db.get("q1", "p_new").value == -5


def test_add_attributes_persistence(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        db.add_attribute("q1", "p_new", -5, CalState.FINE)
        assert db.get("q1", "p_new").value == -5
        assert db.get("q1", "p_new").cal_state == CalState.FINE
        db.commit()

    with _QpuDatabaseConnectionBase(testdb) as db:
        assert db.get("q1", "p_new").value == -5
        assert db.get("q1", "p_new").cal_state == CalState.FINE


def test_add_elements(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        db.add_element("q_new")
        db.add_attribute("q_new", "p_new", "something")
        assert db.get("q_new", "p_new").value == "something"

    with _QpuDatabaseConnectionBase(testdb) as db:
        with pytest.raises(AttributeError):
            assert db.add_element("q1")


def test_add_elements_persistence(testdb):
    with _QpuDatabaseConnectionBase(testdb) as db:
        db.add_element("q_new")
        db.add_attribute("q_new", "p_new", "something")
        db.commit()

    with _QpuDatabaseConnectionBase(testdb) as db:
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


def test_we_can_open_all_history_items(testdb):
    indices = []
    expected_values = []
    actual_values = []

    # prepare the database with items in the history
    with QpuDatabaseConnection(testdb) as db:
        for v_bias in range(6):
            db.set("q1", "p1", v_bias)
            db.commit()
            indices.append(len(db._con_hist.root()["entries"]) - 1)
            expected_values.append(db.q(1).p1.value)

    # try to pull an item from all history entries
    with QpuDatabaseConnection(testdb) as db:
        for i in indices:
            db.restore_from_history(i)
            actual_values.append(db.q(1).p1.value)

    assert expected_values == actual_values


def test_we_can_open_all_history_items_in_same_connection(testdb):
    indices = []
    expected_values = []
    actual_values = []

    # prepare the database with items in the history
    with QpuDatabaseConnection(testdb) as db:
        for v_bias in range(6):
            db.set("q1", "p1", v_bias)
            db.commit()
            indices.append(len(db._con_hist.root()["entries"]) - 1)
            expected_values.append(db.q(1).p1.value)

        # try to pull an item from all history entries
        for i in indices:
            db.restore_from_history(i)
            actual_values.append(db.q(1).p1.value)

    assert expected_values == actual_values


def test_write_to_json_editor(testdb):
    with QpuDatabaseConnection(testdb) as db:
        db.export_to_editor()

        import jsonpickle

        with open(testdb + ".json") as fl:
            db_dict = jsonpickle.decode(fl.read())
        for element in db.elements:
            for attribute in db.attributes(element):
                param = db.get(element, attribute)
                entry = tuple(jsonpickle.decode(db_dict[element][attribute]))
                saved_value, saved_cal_state = entry
                assert param.value == saved_value
                assert param.cal_state == saved_cal_state


def test_read_from_json_editor(testdb):
    with QpuDatabaseConnection(testdb) as db:
        db.export_to_editor()

    with QpuDatabaseConnection(testdb) as db:
        db.import_from_editor()
        import jsonpickle

        with open(testdb + ".json") as fl:
            db_dict = jsonpickle.decode(fl.read())
        for element in db.elements:
            for attribute in db.attributes(element):
                param = db.get(element, attribute)
                entry = tuple(jsonpickle.decode(db_dict[element][attribute]))
                saved_value, saved_cal_state = entry
                assert param.value == saved_value
                assert param.cal_state == saved_cal_state


def test_edit_in_editor(testdb):
    with QpuDatabaseConnection(testdb) as db:
        db.export_to_editor()

    with open(testdb + ".json", "r") as fl:
        s = fl.read()
    s = s.replace("3.32", "6.32")

    with open(testdb + ".json", "w") as fl:
        fl.write(s)

    with QpuDatabaseConnection(testdb) as db:
        db.import_from_editor()
        assert db.get("q1", "p1").value == 6.32
