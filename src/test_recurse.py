from app import recurse 
results = []
results.append(recurse({}, ["test", "a"], "val1")                      == { "test": {"a": "val1"} } )
results.append(recurse({}, ["test", "b"], "val2")                      == { "test": {"b": "val2"} } )
results.append(recurse({}, ["test", "c", "inner"], "val3")             == { "test": { "c": {"inner": "val3"} } } )
results.append(recurse({}, ["test", "d[0]"], "val4")                   == { "test": { "d": [ "val4" ] } } )
results.append(recurse({}, ["test", "d[1]"], "val5")                   == { "test": { "d": [ None, "val5" ] } } )
results.append(recurse({}, ["test", "e[0]", "a"], "val6")              == { "test": { "e": [ {"a": "val6" } ] } } )
results.append(recurse({}, ["test", "e[0]", "a"], "val6")              == { "test": { "e": [ {"a": "val6" } ] } } )
results.append(recurse({}, ["test", "e[0]", "b"], "val7")              == { "test": { "e": [ {"b": "val7" } ] } } )
results.append(recurse({}, ["test", "e[1]", "a"], "val8")              == { "test": { "e": [ None, {"a": "val8" } ] } } )
results.append(recurse({}, ["test", "e[1]", "c"], "val9")              == { "test": { "e": [ None, {"c": "val9" } ] } } )

results_p2 = []
collection = {}
results_p2.append(recurse(collection, ["test", "a"], "val1")              == { "test": {"a": "val1"} } )
results_p2.append(recurse(collection, ["test", "b"], "val2")              == { "test": {"a": "val1", "b": "val2"} } )
results_p2.append(recurse(collection, ["test", "c", "inner"], "val3")     == { "test": {"a": "val1", "b": "val2", "c": {"inner": "val3"} } } )

collection = {}
results_p2.append(recurse(collection, ["test", "d[0]"], "val4")           == { "test": { "d": [ "val4" ] } } )
results_p2.append(recurse(collection, ["test", "d[1]"], "val5")           == { "test": { "d": [ "val4", "val5" ] } } )

collection = {}
results_p2.append(recurse(collection, ["test", "e[0]", "a"], "val6")      == { "test": { "e": [ {"a": "val6" } ] } } )
results_p2.append(recurse(collection, ["test", "e[0]", "b"], "val7")      == { "test": { "e": [ {"a": "val6", "b": "val7" } ] } } )
results_p2.append(recurse(collection, ["test", "e[1]", "a"], "val8")      == { "test": { "e": [ {"a": "val6", "b": "val7" }, {"a": "val8" } ] } } )
results_p2.append(recurse(collection, ["test", "e[1]", "c"], "val9")      == { "test": { "e": [ {"a": "val6", "b": "val7" }, {"a": "val8", "c": "val9" } ] } } )


