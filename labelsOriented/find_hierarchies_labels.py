""" find hierarchies """

##### Imports
from itertools import starmap, combinations
import itertools
from operator import itemgetter
from itertools import groupby
import numpy as np
import copy
import json
import ast # to convert string to dict

from neo4j import GraphDatabase

from format_utils import label_format

def list_intersections(tab):
    """ Get the pairwise intersections of all sets in the list tab 
    and the list of sets that do not intersect any of the other sets.
    """
    inters = [] # list of pairwise intersections
    for i in range(len(tab)):
        x = tab[i]
        for j in range(len(tab[i:])-1):
            y = tab[j+i+1]
            xintersy = x & y # intersection between x and y
            if xintersy != set() and xintersy!=x:
                inters.append(xintersy)
                
    ## remove duplicates  
    intersLists = list(map(list, inters))  
    intersLists.sort() 
    inters = list(map(set, list(elem for elem,_ in itertools.groupby(intersLists)))) 
    return inters

def prop_intersections(labels, nodes):
    """ returns the intersection of the properties of the labeled nodes listed in labels. """
    listPropKeys = list(map(lambda x: set(nodes[x].keys()), labels))
    propKeyInters = set.intersection(*listPropKeys)
    
    propInters = {}
    for prop in propKeyInters:   
        dataType = set()
        for labPair in list(combinations(labels, 2)):
            lab0, lab1 = labPair[0], labPair[1]
            merged = merge_data_types(str(nodes[lab0][prop]), str(nodes[lab1][prop]))
            dataType.add(merged)
        
        sep = " + " 
        propInters[prop] = sep.join(dataType) 
        
    return propInters

def get_list_content(prop):
    """ Get the content of the lists contained in the string prop. """
    proplists = [] 
    propelems = [] 
    
    indexBracketl = prop.find("[") 
    indexBracketr = prop.rfind("]") 
    if indexBracketl > -1:
        proplists.append(prop[indexBracketl+1 : indexBracketr].strip("'"))
        propNotlist = prop[: indexBracketl] + prop[indexBracketr+1 : ] 
        propelems += list(filter(lambda x: x != "", propNotlist.split(' + ')))
    else:
        propelems += prop.split(" + ")
    return proplists, propelems

def get_dict_content(prop):
    """ Get the content of the dict contained in the string prop. """
    propdicts = [] 
    propelems = [] 
    
    indexBracketl = prop.find("{") 
    indexBracketr = prop.rfind("}") 
    if indexBracketl > -1:
        propdicts.append(ast.literal_eval(prop[indexBracketl : indexBracketr+1].strip("'")))
        propNotdict = prop[: indexBracketl] + prop[indexBracketr+1 : ] 
        propelems += list(filter(lambda x: x != "", propNotdict.split(' + ')))
    else:
        propelems += prop.split(" + ")
    return propdicts, propelems
    
def merge_data_types(prop1, prop2):
    """ Merges two data types: prop1 and prop2. """
    if type(prop1) != type(prop2):
        sep = " + " 
        propMerged = sep.join({str(prop1), str(prop2)})
        
    elif type(prop1) == list:
        propMerged = ""
        prop1dicts = [] 
        prop2dicts = [] 
        prop1lists = [] 
        prop2lists = [] 
        prop1elems = [] 
        for elem in prop1:
            if type(elem) == dict:
                prop1dicts.append(elem)
            elif type(elem) == list:
                prop1lists += elem
            else:
                prop1lst, prop1elems = get_list_content(elem)
                prop1lists += prop1lst
                
        prop2elems = [] 
        for elem in prop2:
            if type(elem) == dict:
                prop2dicts.append(elem)
            elif type(elem) == list:
                prop2lists += elem
            else:
                prop2lst, prop2elems = get_list_content(elem)
                prop2lists += prop2lst
        
        proplistSet = set()
        if prop1lists and prop2lists:
            for pair in list(itertools.product(prop1lists, prop2lists)):
                mergedPair = merge_data_types(pair[0], pair[1]) 
                proplistSet.update(set(mergedPair.split(" + ")))
            proplistSet = {str([" + ".join(proplistSet)])}
        else:
            if prop1lists:
                prop1elems.append(str(prop1lists)) 
            elif prop2lists:
                prop2elems.append(str(prop2lists))
                    
        propdictList = []
        if prop1dicts and prop2dicts:
            for pair in list(itertools.product(prop1dicts, prop2dicts)):
                mergedPair = merge_data_types(pair[0], pair[1]) 
                propdictList.append(json.dumps(mergedPair))
        else:
            propdictList += list(map(json.dumps, prop1dicts))
            propdictList += list(map(json.dumps, prop2dicts))
        
        propMerged = " + ".join(set(prop1elems) | set(prop2elems) | set(propdictList) | proplistSet)
        propMerged = str([propMerged])
        propMerged = [merge_data_types(prop1[0], prop2[0])]
        
    elif type(prop1) == dict:
        propMerged = {}
        propKeyInters = set(prop1.keys()) & set(prop2.keys()) 
        for key in propKeyInters:
            propMerged[key] = merge_data_types(prop1[key], prop2[key]) 
            
        prop1KeyOther = set(prop1.keys()) - propKeyInters 
        for key in prop1KeyOther:
            prop1other = prop1[key]
            if type(prop1other) == str and "?" not in prop1other:
                prop1other += " ?"
            elif type(prop1other) == list and "?" not in prop1other[0]:
                prop1other= [str(prop1other[0]) + " ?"]
            elif type(prop1other) == dict:
                prop1other["meta_mandatory"] = False
            propMerged[key] = prop1other 
            
        prop2KeyOther = set(prop2.keys()) - propKeyInters 
        for key in prop2KeyOther:
            prop2other = prop2[key]
            if type(prop2other) == str and "?" not in prop2other:
                prop2other += " ?"
            elif type(prop2other) == list and "?" not in prop2other[0]:
                prop2other= [str(prop2other[0]) + " ?"]
            elif type(prop2other) == dict:
                prop2other["meta_mandatory"] = False    
            propMerged[key] = prop2other 
            
        propMerged = propMerged
           
    elif type(prop1) == str:
        optional = False
        if "?" in prop1 or "?" in prop2:
            optional = True
            prop1 = prop1.replace(" ?",'')
            prop2 = prop2.replace(" ?",'')
            if prop1 == prop2:
                propMerged = prop1 + " ?"
                return propMerged
        
        prop1dicts = [] 
        prop2dicts = [] 
        prop1dicts, prop1elems = get_dict_content(prop1)
        prop2dicts, prop2elems = get_dict_content(prop2)
        if prop1dicts and prop2dicts:
            propdictList = []
            for pair in list(itertools.product(prop1dicts, prop2dicts)):
                mergedPair = merge_data_types(pair[0], pair[1]) 
                propdictList.append(mergedPair)
            sep = " + " 
            propMerged = " + ".join([" + ".join(set(prop1elems) | set(prop2elems)), str([" + ".join(propdictList)])])
        else:
            if prop1dicts:
                prop1elems.append(str(prop1dicts)) 
            elif prop2dicts:
                prop2elems.append(str(prop2dicts))
            propMerged = " + ".join(set(prop1elems) | set(prop2elems))
            
        prop1lists, prop1elems = get_list_content(prop1)
        prop2lists, prop2elems = get_list_content(prop2)   

        if prop1lists and prop2lists:
            proplistSet = set()
            for pair in list(itertools.product(prop1lists, prop2lists)):
                mergedPair = merge_data_types(pair[0], pair[1]) 
                proplistSet.update(set(mergedPair.split(" + ")))
            sep = " + " 
            if not prop1elems and not prop2elems:
                propMerged = [" + ".join(proplistSet)]
                if optional:
                    propMerged = str([propMerged[0].replace(" ?",'') + " ?"])
            else:
                propMerged = " + ".join([" + ".join(set(prop1elems) | set(prop2elems)), str([" + ".join(proplistSet)])])
        else:
            if prop1lists:
                prop1elems.append(str(prop1lists)) 
            elif prop2lists:
                prop2elems.append(str(prop2lists))
            propMerged = " + ".join(set(prop1elems) | set(prop2elems))
            if optional:
                propMerged = propMerged.replace(" ?",'') + " ?"
            
    elif type(prop1) == bool:
        propMerged = " + ".join({str(prop1), str(prop2)})
    else:
        propMerged = "Null"
        
    return propMerged

def supertype_prop(supertype, subtype, nodes):
    """ returns the properties of the supertype node. """
    propInters = prop_intersections([label_format(supertype), label_format(subtype)], nodes)
    superProps = propInters
    
    optSuperProps = set(nodes[label_format(supertype)].keys()) - set(propInters.keys()) 
    for opt in optSuperProps:
        optProp = nodes[label_format(supertype)][opt]        
        if type(optProp) == str:
            optProp += ' ?'
        elif type(optProp) == list:
            optProp.append('?')
            optProp = json.dumps(optProp)
        else:
            optProp['meta_mandatory'] = False
            optProp = json.dumps(optProp)
        superProps[opt] = optProp
   
    return superProps

def crt_inheritance_edge(elem0, elem1, edges, nodes):
    """ Procedure that creates the inheritance edge between elem0 and elem1 """
    if elem0 != elem1:
        if elem1.issubset(elem0):      
            sublab, superlab = label_format(elem0), label_format(elem1)
            edges[sublab + "::SubtypeOf::" + superlab]={}
        elif elem0.issubset(elem1):      
            sublab, superlab = label_format(elem1), label_format(elem0)
            edges[sublab + "::SubtypeOf::" + superlab]={}

def infer_node_hierarchies(schema, filename):
    """ infers node hierarchies in the provided schema and writes it in a JSON file. """
    edges = copy.deepcopy(schema['Edges'])
    nodes = copy.deepcopy(schema['Nodes'])

    nodeLabels = list(map(lambda s: s.lstrip(":").split(":"), nodes.keys()))
    setNLabels = list(map(set, nodeLabels))
    
    supertypes = list_intersections(setNLabels)
    
    for stype in supertypes:
        lab = label_format(stype)
        nodes.setdefault(lab, {})
    
    nodeLabels = list(map(lambda s: s.lstrip(":").split(":"), nodes.keys()))
    setNLabels = list(map(set, nodeLabels))
    
    for i in range(len(setNLabels)-1):
        elem0 = setNLabels[i]
        for j in range(len(setNLabels[i:])-1):
            elem1 = setNLabels[j+i+1]
            crt_inheritance_edge(elem0, elem1, edges, nodes)
                                       
    out = open(filename,'w')
    schema = {}
    schema['nodes'] = nodes
    schema['edges'] = edges
    out.write(json.dumps(schema))
    out.close()
    return nodes, edges
    
def open_semantic_schema(Nodes, Edges, driver, filename, dbname="neo4j"):
    """ Transforms a closed-semantics schema into an open-semantics one """
    nodes = copy.deepcopy(Nodes)
    edges = copy.deepcopy(Edges)  
    constraints = set()
    
    create_Neo4j_pgschema(nodes, edges, driver, False, dbname=dbname)
    
    # Target specific DB
    with driver.session(database=dbname) as session:
        overlaps = session.execute_read(lambda tx: tx.run(
            "MATCH p=(n)<-[e:edge {type:['SubtypeOf']}]-(m) "
            "-[r:edge {type:['SubtypeOf']}]->(o) "
            "RETURN DISTINCT m, n"
        ).data())
    
    inheritEdgeList = [e.split("::") for e in edges.keys() if e.split("::")[1]=="SubtypeOf"]
    inheritEdgeList.sort()
    
    inheritEdges={}
    for subtype, etypes in  groupby(inheritEdgeList,key=itemgetter(0)):
        inheritEdges[subtype]=[]
        for subtype,label,supertype in etypes:
            inheritEdges[subtype].append(supertype)
    
    for types in overlaps:
        sublab = types['m']['id'] 
        superlab = types['n']['id'] 
        
        for suptype in inheritEdges[sublab]:
            if suptype in nodes and sublab in nodes:
                nodes[suptype] = merge_data_types(nodes[sublab], nodes[suptype])
            edges.pop("::".join([sublab, "SubtypeOf", suptype]), None) 
        
        constraints.add(tuple(sublab.split(":")))
        nodes.pop(sublab, None) 
                   
    openSchema={}
    openSchema['Nodes'] = nodes
    openSchema['Edges'] = edges
    
    out = open(filename,'w')
    out.write('{"Nodes":' + str(nodes) + '},\n "Edges":' + str(edges) +'}') 
    out.close()
    
    outConstraints = open(filename.split('.')[0] + '_constraints.txt','w')
    outConstraints.write(str(constraints)) 
    outConstraints.close()   
        
    return nodes, edges, constraints

###### Native Neo4j schema graph creator (Replaces regraph dependency)
def create_Neo4j_pgschema(Nodes, Edges, driver, all_edges=True, dbname="neo4j"):
    """ creates a Neo4j schema graph from the list of nodes and edges natively. """
    nodes = copy.deepcopy(Nodes)
    edges = copy.deepcopy(Edges)
    
    # 'id' key renamed to 'ID'                
    for x in nodes.items():
        if "id" in x[1]: 
            x[1]['ID'] = x[1].pop("id")
    # property values converted to string     
    for keyVal, value in nodes.items():
        for key, prop in value.items():
            nodes[keyVal][key] = str(nodes[keyVal][key])
                  
    schemaNodes = list(nodes.items())
    
    schemaEdges = [] 
    for keyVal, value in edges.items():
        for key, prop in value.items():
            if type(prop) == dict:
                prop = str(json.dumps(prop))
            value[key] = str(prop)
        source, etype, target = keyVal.split("::")
        value['type'] = etype
        schemaEdges.append((source, target, value))
    
    # Write native Cypher using driver v6 execution logic targeting specific DB
    with driver.session(database=dbname) as session:
        # Clear existing regraph-style schema
        session.execute_write(lambda tx: tx.run("MATCH (n:node) DETACH DELETE n"))
        
        # Add schema nodes
        for node_id, attrs in schemaNodes:
            session.execute_write(lambda tx, n_id, props: tx.run(
                "CREATE (n:node {id: $n_id}) SET n += $props", 
                n_id=n_id, props=props
            ), node_id, attrs)
            
        # Add schema edges
        for source, target, attrs in schemaEdges:
            if 'type' in attrs:
                attrs['type'] = [attrs['type']] 
            
            session.execute_write(lambda tx, src, tgt, props: tx.run(
                "MATCH (s:node {id: $src}), (t:node {id: $tgt}) "
                "CREATE (s)-[r:edge]->(t) SET r += $props", 
                src=src, tgt=tgt, props=props
            ), source, target, attrs)
    
    ### remove superfluous edges
    if not all_edges:
        with driver.session(database=dbname) as session:
            session.execute_write(lambda tx: tx.run(
                "MATCH p=(n)-[s:edge{type:['SubtypeOf']}]->(m) "
                "-[r:edge*1.. {type:['SubtypeOf']}]->(o), "
                "q = (n)-[t:edge{type:['SubtypeOf']}]->(o) "
                "DELETE t"
            ))