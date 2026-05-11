""" Functions to call the MapReduce algorithm [1]_, parse its output,
    merge it with information about edge cardinality and optionality and with other nodes and edges.

References
---------
.. [1] Baazizi, Mohamed-Amine & Colazzo, Dario & Ghelli, Giorgio & Sartiani, Carlo. (2019).
        "Parametric schema inference for massive JSON datasets". 
        The VLDB Journal. 28. 10.1007/s00778-018-0532-7. 
"""

##### Imports
import json
import subprocess
import argparse

try:
    import resource
except ImportError:
    resource = None

# Graceful fallback for ijson and its C backends
try:
    import ijson.backends.yajl2_c as ijson
except ImportError:
    try:
        import ijson.backends.yajl2 as ijson
    except ImportError:
        try:
            import ijson
        except ImportError:
            ijson = None

def reset_memory_limit():
    """Resets the soft memory limit to the hard limit for the child process so Java/Spark can run."""
    if resource is not None:
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            resource.setrlimit(resource.RLIMIT_AS, (hard, hard))
        except Exception:
            pass

def call_mapreduce(pgfilename, equiv="l", driver_memory="4g", master="local[*]"):
    """ Calls the MapReduce algorithm from [1]_ """
    valid = {"k","l"}
    if equiv not in valid:
        raise ValueError("call_mapreduce: equiv must be either 'k' or 'l'.")

    cmd = "spark-submit --driver-memory {memory} --jars ./MapReduce/play-json_2.11-2.7.4.jar \
     --class 'testing.testRunInference'  --master {master} ./MapReduce/jsonschemainference_2.11-1.1.jar \
     -equiv {equiv} -path {pgfilename}".format(memory=driver_memory, master=master, equiv=equiv, pgfilename=pgfilename) 
     
    try:
        cmd_output = subprocess.check_output(cmd, shell=True, preexec_fn=reset_memory_limit)
        cmd_output = cmd_output.decode('utf-8')
        MRfilename = cmd_output.split()[-1] 
        return MRfilename
    except subprocess.CalledProcessError as e:
        print(f"\nFatal Error: Spark JAR crashed on {pgfilename}! Error code: {e.returncode}")
        exit(1)

def find_data_type(prop):
    """ Find the data type of a json record 
        with the following format: {key: {'__Content':{...}, '__Kind':{...}}}
        it handles optional elements.
    """
    if not prop:
        propType = 'Null'

    else:
        propKind = prop['__Kind']
        
        if propKind == 'ArrayType':
            if prop['__Content']['__Kind'] == 'RecordType' or prop['__Content']['__Kind'] == 'union' :
                propType = [find_data_type(prop['__Content'])]
            else:
                propType = [prop['__Content']['__Kind']]
                            
        elif propKind == 'RecordType':
            record = {}          
            for nprop in prop['__Content'].items():
                key = nprop[0]
                value = nprop[1]
                
                mandatory = True 
                if '__Optional' in value.keys():
                    value = value['__Optional']
                    mandatory = False
                    
                if value['__Kind'] == 'ArrayType':
                    propType = find_data_type(value) 
                    
                elif value['__Kind'] == 'RecordType':
                    valueContent = value['__Content']
                    propType = valueContent 
                    for subkey in valueContent.keys():
                        if '__Optional' in valueContent[subkey].keys():
                            if valueContent[subkey]['__Optional']['__Kind'] == 'RecordType':
                                valueContent[subkey]['__Optional']['__Content']['meta_mandatory']= {'__Kind':False}
                    propType = find_data_type(value) 
                    
                elif value['__Kind'] =='union':
                    propList = []
                    for elem in value['__Content']:
                        propList.append(str(find_data_type(elem)))
                    
                    propType = " + "
                    propType = propType.join(propList)
                
                else:
                    propType = value['__Kind']
                
                if not mandatory:
                    if type(propType) == str:
                        record[key] = propType + " ?"
                    elif type(propType) == list:
                        record[key] = [str(propType[0]) + " ?"]
                    else:
                        record[key] = propType
                            
                else:
                    record[key]=propType
                    
            propType = record 
        
        elif propKind =='union':
            propList = []
            for elem in prop['__Content']:
                propList.append(str(find_data_type(elem)))
            
            propType = " + "
            propType = propType.join(propList)
        
        else:
            propType = propKind
            
    return propType


def parse_mapreduce_schema(MRfilename, allLabels=True):
    """ Parses the output schema of the MapReduce algorithm [1]_.
        All node types must be labeled.
    """
    try:
        if ijson is not None:
            with open(MRfilename, 'rb') as fileMRschema:
                objects = ijson.items(fileMRschema, '')
                for obj in objects:
                    MRschema = obj
        else:
            with open(MRfilename, 'r') as fileMRschema:
                MRschema = json.load(fileMRschema) 
    except FileNotFoundError:
        print(f"File {MRfilename} not found.")
        return 'Null'
    except Exception as e:
        print(f"Error decoding JSON from {MRfilename}: {e}")
        return 'Null'
    
    schema = find_data_type(MRschema) 
        
    return schema

def merge_nodes_edges(schemaNodes, schemaEdges):
    """ Merges nodes and edges dicts to form the schema dict."""
    schema = {}
    schema['Nodes'] = schemaNodes
    schema['Edges'] = schemaEdges
    return schema
    
def parse_mapreduce_unlabeled(MRfilename):
    """Parses the output unlabeled node list of the MapReduce algorithm [1]_.
    """
    try:
        if ijson is not None:
            with open(MRfilename, 'rb') as fileMRoutput:
                objects = ijson.items(fileMRoutput, '')
                for obj in objects:
                    MRoutput = obj
        else:
            with open(MRfilename, 'r') as fileMRoutput:
                MRoutput = json.load(fileMRoutput) 
    except FileNotFoundError:
        print(f"File {MRfilename} not found.")
        return []
    except Exception as e:
        print(f"Error decoding JSON from {MRfilename}: {e}")
        return []
    
    unlabNodes = [] 
    if '__Content' in MRoutput:
        for elem in MRoutput['__Content']:
            unlabNodes.append(find_data_type(elem))
        
    return unlabNodes

def merge_schema_infos(schema, nodesNoProp, edgesCard):
    """ Procedure to merge the schema with the nodes and edges with no properties 
        and the information about edge cardinalities and optionality.
    """
    schema['Nodes'].update(nodesNoProp)

    for key in schema['Edges'].keys():
        edgesCard[key].update(schema['Edges'][key])
    schema['Edges'] = edgesCard
    
def merge_unlabeled_nodes(schema, unlabNodes):
    """ Procedure to merge the schema with the unlabeled nodes.
    """
    i = 0 
    
    labNodes = [] 
    for elem in list(schema['Nodes'].items()):
        if isinstance(elem[1], dict):
            for label in elem[0].split(":"):
                elem[1][label]="Void"
            elem[1]['meta_id'] = i
            i += 1
            labNodes.append(elem[1])
        
    for elem in unlabNodes:
        elem['meta_id'] = i
        i += 1
            
    schema['Nodes'] = labNodes + unlabNodes