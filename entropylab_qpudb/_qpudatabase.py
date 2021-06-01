import dataclasses
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Type, Optional, Dict

import ZODB
import ZODB.FileStorage
import pandas as pd
import transaction
from persistent import Persistent
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping
from entropylab.instruments.instrument_driver import Resource
from zc.lockfile import LockError

from entropylab_qpudb._resolver import DefaultResolver


class CalState(Enum):
    UNCAL = auto()
    COARSE = auto()
    MED = auto()
    FINE = auto()

    def __str__(self):
        return self.name


@dataclass(repr=False)
class QpuParameter(Persistent):
    """
    A QPU parameter which stores values and modification status for QPU DB entries
    """

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


def create_new_qpu_database(
    dbname: str,
    initial_data_dict: Dict = None,
    force_create: bool = False,
    path: str = None,
) -> None:
    """
    Create a new QPU database permanent storage file. This operation is performed once in the lifetime of a database,
    and is quite similar to initializing a git repo.

    When this method is called, DB files are generated in the working directory of the script by default. An attempt
    to create a DB where one already exists by the same name will lead to an error, unless `force_create` flag is used.

    .. note::

        if the scripts that create this database are managed by a version control system such as git, it is not
        recommended to create the DB files in the same path as the scripts, since then they will be tracked by the
        versioning system or, if ignored, can be deleted by it.

    :param dbname: The name of the database. Used when opening with `QpuDatabaseConnection`.
    :param initial_data_dict: An initial dictionary of QPU parameters.
    :param force_create: If set to true, calling this method when an array already exists in the folder will lead to
    it being overridden.
    :param path: The path where the DB is to be stored.
    """
    if initial_data_dict is None:
        initial_data_dict = {}
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
    initial_data_dict = deepcopy(initial_data_dict)
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
        [
            {
                "timestamp": datetime.utcnow(),
                "connected_tx": None,
                "message": "initial commit",
            }
        ]
    )
    transaction.commit()
    db_hist.close()


class ReadOnlyError(Exception):
    pass


class _QpuDatabaseConnectionBase(Resource):
    def connect(self):
        pass

    def teardown(self):
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
        self._path = path
        self._dbname = dbname
        dbfilename = _db_file_from_path(self._path, self._dbname)
        if not os.path.exists(dbfilename):
            raise FileNotFoundError(f"QPU DB {self._dbname} does not exist")
        self._db = None
        super().__init__()
        self._con_hist = self._open_hist_db()
        self._con = self._open_data_db(history_index)

    def _open_data_db(self, history_index):
        dbfilename = _db_file_from_path(self._path, self._dbname)
        hist_entries = self._con_hist.root()["entries"]
        if history_index is not None:
            message_index = history_index
            at = self._con_hist.root()["entries"][history_index]["connected_tx"]
        else:
            message_index = len(hist_entries) - 1
            at = None
        try:
            self._db = ZODB.DB(dbfilename) if self._db is None else self._db
        except LockError:
            raise ConnectionError(
                f"attempting to open a connection to {self._dbname} but a connection already exists."
                f"Try closing existing python sessions."
            )

        con = self._db.open(transaction_manager=transaction.TransactionManager(), at=at)
        con.transaction_manager.begin()
        print(
            f"opening qpu database {self._dbname} from "
            f"commit {self._str_hist_entry(hist_entries[message_index])} at index {message_index}"
        )
        return con

    def _open_hist_db(self):
        histfilename = _hist_file_from_path(self._path, self._dbname)
        try:
            db_hist = ZODB.DB(histfilename)
        except LockError:
            raise ConnectionError(
                f"attempting to open a connection to {self._dbname} but a connection already exists."
                f"Try closing existing python sessions."
            )
        con_hist = db_hist.open(transaction_manager=transaction.TransactionManager())
        con_hist.transaction_manager.begin()
        return con_hist

    def __enter__(self):
        return self

    @property
    def readonly(self):
        return self._con.isReadOnly()

    def close(self) -> None:
        """
        Closes QPU DB connection to allow for other connections.
        """
        print(f"closing qpu database {self._dbname}")
        self._con._db.close()
        self._con_hist._db.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def set(
        self,
        element: str,
        attribute: str,
        value: Any,
        new_cal_state: Optional[CalState] = None,
    ) -> None:
        """
        A generic function for modifying values of element attributes.

        Modifies the value in memory. The modified value will persist until the connection object
        is deleted. To store the object in memory constantly,
        use :func:`~entropylab_qpudb._qpudatabase.QpuDatabaseConnectionBase.commit`.

        :param element: The name of the element whose attribute should be modified
        :param attribute: The name of the attribute
        :param value: The value to modify
        :param new_cal_state: (optional) new calibration state specification
        """
        root = self._con.root()
        if attribute not in root["elements"][element]:
            raise AttributeError(
                f"attribute {attribute} does not exist for element {element}"
            )
        if new_cal_state is None:
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
        """
        Get a QpuParameter object from which values, last modified and calibration can be extracted.

        :param element: name of the element from which to get
        :param attribute: name of the attribute to get
        :return: a :class:`entropylab_qpudb._qpudatabase.FrozenQpuParameter` instance from which values and modification
        data can be obtained
        """
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
        if self.readonly:
            raise ReadOnlyError("Attempting to commit to a DB in a readonly state")
        lt_before = self._con._db.lastTransaction()
        self._con.transaction_manager.commit()
        lt_after = self._con._db.lastTransaction()
        if lt_before != lt_after:  # this means a commit actually took place
            hist_root = self._con_hist.root()
            hist_entries = hist_root["entries"]
            now = datetime.utcnow()
            hist_entries.append(
                {"timestamp": now, "connected_tx": lt_after, "message": message}
            )
            self._con_hist.transaction_manager.commit()
            print(
                f"commiting qpu database {self._dbname} "
                f"with commit {self._str_hist_entry(hist_entries[-1])} at index {len(hist_entries) - 1}"
            )
        else:
            print("did not commit")

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

    def restore_from_history(self, history_index: int) -> None:
        """
        restore the current unmodified and open DB data to be the same as the one from `history_index`.
        Will not commit the restored data.

        .. note::

            The `last_modified` values will return to the ones in the stored commit as well.

        :param history_index: History index from which to restore
        """
        con = self._open_data_db(history_index)
        self._con.root()["elements"] = deepcopy(con.root()["elements"])
        con.close()


class QpuDatabaseConnection(_QpuDatabaseConnectionBase):
    def __init__(self, dbname, resolver=None, **kwargs):
        super().__init__(dbname, **kwargs)
        if resolver is None:
            self._resolver = DefaultResolver()
        else:
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
