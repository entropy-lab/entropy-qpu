import dataclasses
import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Type, Optional

import ZODB
import ZODB.FileStorage
import pandas as pd
import transaction
from persistent import Persistent
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping
from quaentropy.instruments.instrument_driver import Instrument


class CalState(Enum):
    UNCAL = auto()
    COARSE = auto()
    MED = auto()
    FINE = auto()

    def __str__(self):
        return self.name


@dataclass(repr=False)
class QpuParameter(Persistent):
    value: Any
    last_updated: datetime = None
    cal_state: CalState = CalState.UNCAL

    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()

    def __repr__(self):
        if self.value is None:
            return "QpuParameter(None)"
        else:
            return (
                f"QpuParameter(value={self.value}, "
                f"last updated: {self.last_updated.strftime('%m/%d/%Y %H:%M:%S')}, "
                f"calibration state: {self.cal_state})"
            )


FrozenQpuParameter = dataclasses.make_dataclass(
    "FrozenQpuParameter",
    [fld.name for fld in dataclasses.fields(QpuParameter)],
    frozen=True,
)

FrozenQpuParameter.__repr__ = QpuParameter.__repr__


def _db_file_from_path(path, dbname):
    return os.path.join(path, dbname + ".fs")


def _hist_file_from_path(path, dbname):
    return os.path.join(path, dbname + "_history.fs")


def create_new_qpu_database(dbname, initial_data_dict, force_create=False, path=None):
    if path is None:
        path = os.getcwd()
    dbfilename = _db_file_from_path(path, dbname)
    if os.path.isfile(dbfilename) and not force_create:
        raise FileExistsError(f"db files for {dbname} already exists")
    storage = ZODB.FileStorage.FileStorage(dbfilename)
    db = ZODB.DB(storage)
    connection = db.open()
    root = connection.root()

    # promote all attributes to QpuParams
    # todo: turn into validation schema
    # todo: assert num_qubits is in system
    for element in initial_data_dict.keys():
        for attr in initial_data_dict[element].keys():
            parameter = initial_data_dict[element][attr]
            if not isinstance(parameter, QpuParameter):
                initial_data_dict[element][attr] = QpuParameter(parameter)

    root["elements"] = PersistentMapping(initial_data_dict)
    transaction.commit()
    db.close()

    # create history db
    hist_filename = _hist_file_from_path(path, dbname)
    storage_hist = ZODB.FileStorage.FileStorage(hist_filename)
    db_hist = ZODB.DB(storage_hist)
    connection_hist = db_hist.open()
    root_hist = connection_hist.root()
    root_hist["entries"] = PersistentList(
        [{"timestamp": datetime.utcnow(), "message": "initial commit"}]
    )
    transaction.commit()
    db_hist.close()


class QpuDatabaseConnectionBase(Instrument):
    def setup_driver(self):
        pass

    def teardown_driver(self):
        self.close()

    def revert_to_snapshot(self, snapshot: str):
        pass

    def snapshot(self, update: bool) -> str:
        hist_root = self._con_hist.root()
        return json.dumps(
            {
                "qpu_name": self._dbname,
                "index": len(hist_root["entries"]) - 1,
                "message": hist_root["entries"][-1]["message"],
            }
        )

    @staticmethod
    def deserialize_function(snapshot: str, class_object: Type):
        data = json.loads(snapshot)
        return class_object(data["qpu_name"])

    def __init__(self, dbname, history_index=None, path=None):
        if path is None:
            path = os.getcwd()
        dbfilename = _db_file_from_path(path, dbname)
        histfilename = _hist_file_from_path(path, dbname)
        if not os.path.exists(dbfilename):
            raise FileNotFoundError(f"QPU DB {dbname} does not exist")
        super().__init__()
        self._dbname = dbname
        self._history_index = history_index
        db_hist = ZODB.DB(histfilename)
        self._con_hist = db_hist.open(
            transaction_manager=transaction.TransactionManager()
        )
        self._con_hist.transaction_manager.begin()
        hist_entries = self._con_hist.root()["entries"]
        if self._history_index is not None:
            message_index = self._history_index
            at = self._con_hist.root()["entries"][self._history_index]["timestamp"]
        else:
            message_index = len(hist_entries) - 1
            at = None
        db = ZODB.DB(dbfilename)
        self._con = db.open(transaction_manager=transaction.TransactionManager(), at=at)
        self._con.transaction_manager.begin()
        print(
            f"opening qpu database {dbname} from "
            f"commit {self._str_hist_entry(hist_entries[message_index])} at index {message_index}"
        )

    def __enter__(self):
        return self

    def close(self):
        print(f"closing qpu database {self._dbname}")
        self._con._db.close()
        self._con_hist._db.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def set(self, element, attribute, value, new_cal_state=None):
        root = self._con.root()
        if attribute not in root["elements"][element]:
            raise AttributeError(
                f"attribute {attribute} does not exist for element {element}"
            )
        if new_cal_state is None:
            new_cal_state = CalState.UNCAL
        else:
            new_cal_state = root["elements"][element][attribute].cal_state
        root["elements"][element][attribute].value = value
        root["elements"][element][attribute].last_updated = datetime.now()
        root["elements"][element][attribute].cal_state = new_cal_state

    def add_attribute(
        self,
        element: str,
        attribute: str,
        value: Any = None,
        new_cal_state: Optional[CalState] = None,
    ) -> None:
        """
        Adds an attribute to an existing element.

        :raises: AttributeError if attribute already exists.
        :param element: the name of the element to add
        :param attribute: the name of the new atrribute
        :param value: an optional value for the new attribute
        :param new_cal_state: an optional new cal state
        """
        root = self._con.root()
        if attribute in root["elements"][element]:
            raise AttributeError(
                f"attribute {attribute} already exists for element {element}"
            )
        else:
            root["elements"][element][attribute] = QpuParameter(
                value, datetime.now(), new_cal_state
            )
            root["elements"]._p_changed = True

    def add_element(self, element: str) -> None:
        """
        :raises: AttributeError if element already exists.
        Adds a new element to the DB
        :param element: the name of the element to add
        """
        root = self._con.root()
        if element in root["elements"]:
            raise AttributeError(f"element {element} already exists")
        else:
            root["elements"][element] = dict()

    def get(self, element: str, attribute: str) -> FrozenQpuParameter:
        root = self._con.root()
        if attribute not in root["elements"][element]:
            raise AttributeError(
                f"attribute {attribute} does not exist for element {element}"
            )
        return FrozenQpuParameter(
            **dataclasses.asdict(root["elements"][element][attribute])
        )

    def commit(self, message: Optional[str] = None) -> None:
        """
        Permanently store the existing state to the DB and add a new commit to the history list
        :param message: an optional message for the commit
        """
        self._con.transaction_manager.commit()
        hist_root = self._con_hist.root()
        hist_entries = hist_root["entries"]
        now = datetime.utcnow()
        hist_entries.append({"timestamp": now, "message": message})
        self._con_hist.transaction_manager.commit()
        print(
            f"commiting qpu database {self._dbname} "
            f"with commit {self._str_hist_entry(hist_entries[-1])} at index {len(hist_entries) - 1}"
        )

    def abort(self):
        self._con.transaction_manager.abort()

    def print(self, element=None):
        # todo add resolver and invert it
        if element is None:
            data = self._con.root()["elements"]
            for element in data:
                print("\n" + element + "\n----")
                for attr in data[element]:
                    print(f"{attr}:\t{data[element][attr]}")
        else:
            data = self._con.root()["elements"]
            print("\n" + element + "\n----")
            for attr in data[element]:
                print(f"{attr}:\t{data[element][attr]}")

    def get_history(self) -> pd.DataFrame:
        return pd.DataFrame(self._con_hist.root()["entries"])

    @staticmethod
    def _str_hist_entry(hist_entry):
        return f"<timestamp: {hist_entry['timestamp'].strftime('%m/%d/%Y %H:%M:%S')}, message: {hist_entry['message']}>"


class QpuDatabaseConnection(QpuDatabaseConnectionBase):
    def __init__(self, dbname, resolver, **kwargs):
        super().__init__(dbname, **kwargs)
        self._resolver = resolver

    def q(self, qubit):
        element = self._resolver.q(qubit)
        return QpuAdapter(element, self)

    def res(self, res):
        element = self._resolver.res(res)
        return QpuAdapter(element, self)

    def coupler(self, qubit1, qubit2):
        element = self._resolver.coupler(qubit1, qubit2)
        return QpuAdapter(element, self)

    def system(self):
        return QpuAdapter("system", self)

    def update_q(self, qubit, field, value, new_cal_state=None):
        self.set(self._resolver.q(qubit), field, value, new_cal_state)

    def update_res(self, res, field, value, new_cal_state=None):
        self.set(self._resolver.res(res), field, value, new_cal_state)

    def update_coupler(self, qubit1, qubit2, field, value, new_cal_state=None):
        self.set(self._resolver.coupler(qubit1, qubit2), field, value, new_cal_state)

    def update_system(self, field, value, new_cal_state=None):
        self.set("system", field, value, new_cal_state)

    @property
    def num_qubits(self):
        return self.get("system", "num_qubits").value


class QpuAdapter(object):
    def __init__(self, element, db) -> None:
        self._element = element
        self._db = db

    def __getattr__(self, attribute: str) -> Any:
        return self._db.get(self._element, attribute)
