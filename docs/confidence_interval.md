# Confidence intervals in QPU-DB

Parameters in the QPU-DB can have errors associated with them. 
To add an error to a parameter you can 


```python 
    with QpuDatabaseConnection(testdb) as db:
            db.set("q1", "p1", value, new_confidence_interval=ConfidenceInterval(error))
            db.commit()
```

This sets the value of the parameter `p1` associated with qubit `q1` to `value` and adds a confidence interval with
value `error`. 
You can also add confidence intervals using positional argument notation 

```python 
    with QpuDatabaseConnection(testdb) as db:
            db.set("q1", "p1", value, CalState.FINE, ConfidenceInterval(error))
            db.commit()
```

A confidence interval has two fields: `error` which is a some number and `confidence_level` which 
is meant to hold the certainty with which you determine the error (e.g. 95%).

Getting the stored error from the db is done as follows: 

```python 
    with QpuDatabaseConnection(testdb) as db:
            val = db.get("q1", "p1")
            db.get("q_new", "p_new").confidence_interval.error
             
```

