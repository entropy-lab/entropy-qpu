
Architecture v1
===============

> This is the architecture definition of the first version

The QPU is a specialized interface used to access parameters and calibrations
that are tracked between quantum experiments and enable detection of staleness

Concept
-------

The data is stored in a two level hierarchy which can be thought of as a filesystem.

The first level is `folder` or `directory`, and the second level is `file`

QPU is an easy interface to save files in directories, while keeping the history of each
file. QPU will also handle the versioning using a git-based single-branched model.

Create Script
-------------

Bundled with this package, there should be a script (installed in bin) that will help the 
users create new databases. The python API itself focuses on manipulating such database

```shell
entropy-qpu init
```

This creates a clear separation between the initial setup work, and the day-to-day work

API
---

```python
from entropylab_qpudb import QpuDatabase

# Create the object connecting to the database on the python side
db = QpuDatabase("./db")

# (Optional) Set the entire content of the database
initial_dictionary = {
    "folder1": {
        "file1": 6,
        "file2": 6
    },
    "folder2": {
        "file5": [1, 2, 3],
        "file8": np.array([1 + 0.4 * 1j, 2, 3])
    }
}
db.set_all(initial_dictionary)
```

Working with individual files and folders can be done using explicit methods
```python
db.get("folder2", "file5").value = 60
print(db.get("folder2", "file5").value) # prints 60
```

`db.get("folder2", "file5")` returns a wrapping object QpuParameter which
enable access to the content and the metadata (file modification datetime)

It is possible to access the items using properties
```python
db.folder2.file5.value = 60
```

This should be equivalent
