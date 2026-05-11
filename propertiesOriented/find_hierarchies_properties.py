""" find hierarchies using only properties """

## import
import itertools
import copy
import json 
import re
import ast # to convert string to dict

from format_utils import label_format

###############################"
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
        dicts = prop[indexBracketl : indexBracketr+1].strip("'")
        if "+" in prop[indexBracketl : indexBracketr+1].strip("'"):
            dictList = dicts.split(" + ")
            dictelem = dictList[0]
            for x in dictList[1:]:
                dicts = merge_data_types(dictelem,x)
        propdicts.append(ast.literal_eval(dicts))
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
            
        if "+" in prop1 or "+" in prop2:
            return " + ".join([prop1, prop2])
        
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
        print("{} is not a recognized data type. The merged data type is set as 'Null'.".format(type(prop1)))
        propMerged = "Null"
        
    return propMerged

def types_intersections(tab):
    """ Get the pairwise intersections of all types """
    inters = [] 
    intersYes = [] 
    intersNo = [] 
    intersPairs = [] 
    intersPropsList = [] 
    
    groupedbyx=[]

    for i in range(len(tab)):
        x = tab[i]
        xkeys = set([k for k in x.keys() if not re.search("meta", k)]) 
        noInters_x = True 
        
        xinters=[x]
        for j in range(len(tab[i:])-1):
            y = tab[j+i+1]
            ykeys = set([k for k in y.keys() if not re.search("meta", k)]) 
            xintersy = xkeys & ykeys 
            
            if xintersy != set():
                noInters_x = False
                if xintersy not in inters:
                    inters.append(xintersy)
                    intersProps = {}
                    for key in xintersy:
                        intersProps[key]= merge_data_types(x[key],y[key]) 
                    intersPropsList.append(intersProps)
                xinters.append(y)
                intersYes.append(x)
                intersYes.append(y)
                intersPairs.append((x,y))
            
        groupedbyx.append(xinters)
        if noInters_x and x not in intersYes:
            intersNo.append(x)
            
    intersLists = list(map(list, inters))  
    intersLists.sort() 
    inters = list(map(set, list(elem for elem,_ in itertools.groupby(intersLists)))) 
    
    return intersPropsList

def get_labels(props):
    """ get labels from dict of property types props """
    labels = set() 
    for key, value in props.items():
        if value == "Void":
            labels.add(key)
    if not labels:
        labels = set()
    return labels

def crt_inheritance_edge_unlabeled(elem0, elem1, edges, nodes):
    """ Procedure that creates the inheritance edge between two nodes of properties """
    lab0, lab1 = get_labels(elem0), get_labels(elem1) 
    
    if elem0 != elem1:
        if set(elem1.keys()).issubset(set(elem0.keys())):      
            subprops, supprops = elem0, elem1 
            lab0, lab1 = get_labels(elem0), get_labels(elem1) 
            sublabprop, superlabprop = label_format(lab0), label_format(lab1)
            edges[str(elem0['meta_id']) + "::SubtypeOf::" + str(elem1['meta_id'])]={}
 
        elif set(elem0.keys()).issubset(set(elem1.keys())):
            subprops, supprops = elem1, elem0
            lab0, lab1 = get_labels(elem0), get_labels(elem1) 
            sublabprop, superlabprop = label_format(lab1), label_format(lab0)
            edges[str(elem1['meta_id']) + "::SubtypeOf::" + str(elem0['meta_id'])]={}

        else:
            sublabprop, superlabprop = "False", "False" 
            
        if sublabprop == "":
                sublabprop = str(subprops['meta_id'])
        if superlabprop == "":
            superlabprop = str(supprops['meta_id'])          

def infer_unlabeled_node_hierarchies(schema, filename):
    """ infers node hierarchies in the provided schema """
    edges = copy.deepcopy(schema['Edges'])
    nodes = copy.deepcopy(schema['Nodes'])
    
    propKeys = [] 
    for elem in nodes:
        if set(elem.keys()) != set():
            propKeys.append(set([x for x in list(elem.keys()) if 'meta_' not in x]))
    
    supertypes = types_intersections(nodes)
    
    i = -1 
    for stype in supertypes:
        if stype.keys() not in propKeys:
            stype['meta_id'] = i
            i -= 1
            nodes.append(stype)
    
    for i in range(len(nodes)):
        elem0 = nodes[i]
        for j in range(len(nodes[i:])):
            elem1 = nodes[j+i]
            if elem0 != {} and elem1 != {}:
                crt_inheritance_edge_unlabeled(elem0, elem1, edges, nodes)
    
    out = open(filename,'w')
    schema = {}
    schema['nodes'] = nodes
    schema['edges'] = edges
    out.write(json.dumps(schema))
    out.close()
    return nodes, edges

###### Native Neo4j schema graph creator (Replaces regraph dependency)
def create_Neo4j_pgschema_unlabeled(Nodes, Edges, driver, all_edges=True, dbname="neo4j"):
    """ creates a Neo4j schema graph from the list of nodes and edges natively. """
    nodes = copy.deepcopy(Nodes)
    edges = copy.deepcopy(Edges)
  
    propKeys = [] 
    for elem in nodes:
        if set(elem.keys()) != set():
            propKeys.append([set([x for x in list(elem.keys()) if 'meta_' not in x])] + [elem['meta_id']])
    
    schemaEdges = [] 
    for keyVal, value in edges.items():
        unlabSource = False 
        unlabTarget = False 
        for key, prop in value.items():
            if key == 'meta_source_unlabeled':
                unlabSource = True
            if key == 'meta_target_unlabeled':
                unlabTarget = True
            
            if type(prop) == dict:
                prop = str(json.dumps(prop))
            value[key] = str(prop)
            
        source, etype, target = keyVal.lstrip(":").split("::")
        value['type']=etype
        
        if unlabSource:
            for nkeys in propKeys:
                if set(str(source).split(":")) == nkeys[0]:
                    source = nkeys[1]       
        if unlabTarget:
            for nkeys in propKeys:
                if set(str(target).split(":")) == nkeys[0]:
                    target = nkeys[1]
        
        schemaEdges.append((source, target, value))
        
    schemaNodes = []
    for ntype in nodes:
        labels = get_labels(ntype) 
        if ntype != {}:
            if "id" in ntype.keys(): 
                ntype['ID'] = ntype.pop("id")
            for keyVal, value in ntype.items():
                ntype[keyVal] = str(ntype[keyVal])
            
        if labels == set():
            lab = ntype['meta_id']
        else:
            lab = label_format(labels)
        
        ntype["Label"]=lab
        schemaNodes.append((ntype['meta_id'],ntype))
        
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