import abc

import jsonpickle

from entropylab_qpudb._qpudb_basedefs import CalState


class QpuEditor(abc.ABC):
    @abc.abstractmethod
    def write(self, db):
        pass

    @abc.abstractmethod
    def read(self, db) -> dict:
        pass


class JsonEditor(QpuEditor):
    def __init__(self, dbname):
        self.dbname = dbname

    def write(self, db) -> None:

        json_dict = {}
        for element in db.elements:
            json_dict[element] = {}
            for attribute in db.attributes(element):
                param = db.get(element, attribute)
                json_dict[element][attribute] = jsonpickle.encode(
                    [param.value, int(param.cal_state)]
                )

        s = jsonpickle.encode(json_dict, indent=4)
        with open(self.dbname + ".json", "w") as fl:
            fl.write(s)

    def read(self, db) -> None:
        with open(self.dbname + ".json", "r") as fl:
            s = fl.read()
        json_dict = jsonpickle.decode(s)
        # todo: validate dict
        for element in json_dict:
            if element not in db.elements:
                db.add_element(element)
            for attribute in json_dict[element]:

                value, cal_state = tuple(
                    jsonpickle.decode(json_dict[element][attribute])
                )
                cal_state = CalState(cal_state)
                if attribute not in db.attributes(element):
                    db.add_attribute(element, value, cal_state)
                else:
                    existing_value = db.get(element, attribute).value
                    existing_cal_state = db.get(element, attribute).cal_state
                    if value != existing_value or cal_state != existing_cal_state:
                        db.set(element, attribute, value, cal_state)
