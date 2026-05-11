""" Functions to query a Property Graph (PG) in order to get nodes, edges and collect statistics.
    They also preprocess the PG and serialize it in JSON format and check edge cardinalities and optionality.
    The PG needs to be already loaded in Neo4j. """

import neo4j
import itertools
import more_itertools as mit
import json
import orjson
import numpy as np
import concurrent.futures
import os
import shutil

from format_utils import label_format, convert_to_num

def Neo4jNode_to_json(labels, props):
    """ Serialize raw node data into json format. Returns bytes. """
    lab = label_format(labels)
    out = {lab:{}} if lab else {}
    
    for key, value in props.items():
        if type(value) == neo4j.spatial.CartesianPoint:
            value = {"srid": getattr(value, 'srid', None), "x": getattr(value, 'x', None), "y": getattr(value, 'y', None), "z": getattr(value, 'z', None), "_neo4j.types.spatial.CartesianPoint":"type"}
        elif type(value) == neo4j.spatial.WGS84Point:
            value = {"srid": getattr(value, 'srid', None), "x": getattr(value, 'x', None), "y": getattr(value, 'y', None), "z": getattr(value, 'z', None), "_neo4j.types.spatial.WGS84Point":"type"}
        elif type(value) == neo4j.time.DateTime:
            value = { "year": value.year, "month": value.month, "day": value.day, "hour":value.hour, "minute":value.minute,"second":value.second, "_neotime.DateTime":"type"}
        elif type(value) == neo4j.time.Date:
            value = { "year": value.year, "month": value.month, "day": value.day, "_neotime.Date":"type"}
        elif type(value) == neo4j.time.Time:
            value = {"hour":value.hour, "minute":value.minute,"second":value.second, "_neotime.Time":"type"}
        elif type(value) == neo4j.time.Duration:
            value = { "years": value.years, "months": value.months, "days": value.days, "hours":value.hours, "minutes":value.minutes,"seconds":value.seconds, "_neotime.Duration":"type"}
        elif type(value)==str:
            if value.casefold() == "nan" or value == "Infinity" or value == "Inf":
                value = 0.0 
            elif value == "":
                value = "Null"
            elif value[0] == "{" and value[-1] == "}" and value.find(':')>0:
                if (value.find("'")>0 or value.find('"')>0):
                    try:
                        value = json.loads(value) 
                    except json.decoder.JSONDecodeError:
                        value = str(value)
                else:
                    propkey, propvalue = value.split(":")
                    propkey = '"'.join([propkey[0], propkey[1:]]) + '"'
                    propvalue = '"'.join([propvalue[0], propvalue[:-1]]) + '"}'
                    try:
                        value = json.loads(":".join([propkey, propvalue]))
                    except:
                        value = str(value)
            else:
                value = convert_to_num(value)
                
        elif type(value) == float and ( np.isnan(value) or np.isinf(value) ):
            value = 0.0
        
        if lab:
            out[lab][key] = value 
        else:
            out[key] = value 
    
    return orjson.dumps(out)


def Neo4jEdge_to_json(record):
    """ Serializes raw edge data into json format. Returns bytes. """
    nlabel = record['nlabel'] or record['nkeys']
    mlabel = record['mlabel'] or record['mkeys']
    elabel = record['elabel']
    props = record['props']

    nlab = label_format(nlabel)
    mlab = label_format(mlabel)    
    lab = nlab + "::" + elabel + "::" + mlab 
    out = {lab:{}} 
    
    for key, value in props.items():
        if type(value) == neo4j.spatial.CartesianPoint:
            value = {"srid": getattr(value, 'srid', None), "x": getattr(value, 'x', None), "y": getattr(value, 'y', None), "z": getattr(value, 'z', None), "_neo4j.types.spatial.CartesianPoint":"type"}
        elif type(value) == neo4j.spatial.WGS84Point:
            value = {"srid": getattr(value, 'srid', None), "x": getattr(value, 'x', None), "y": getattr(value, 'y', None), "z": getattr(value, 'z', None), "_neo4j.types.spatial.WGS84Point":"type"}
        elif type(value) == neo4j.time.DateTime:
            value = { "year": value.year, "month": value.month, "day": value.day, "hour":value.hour, "minute":value.minute,"second":value.second, "_neotime.DateTime":"type"}
        elif type(value) == neo4j.time.Date:
            value = { "year": value.year, "month": value.month, "day": value.day, "_neotime.Date":"type"}
        elif type(value) == neo4j.time.Time:
            value = {"hour":value.hour, "minute":value.minute,"second":value.second, "_neotime.Time":"type"}
        elif type(value) == neo4j.time.Duration:
            value = { "years": value.years, "months": value.months, "days": value.days, "hours":value.hours, "minutes":value.minutes,"seconds":value.seconds, "_neotime.Duration":"type"}
        elif type(value)==str:
            if value.casefold() == "nan" or value.casefold() == "":
                value = "Null" 
            elif "{" in value:
                try:
                    value = json.loads(value)
                except:
                    value = str(value)
            else :
                value = convert_to_num(value)
        out[lab][key] = value
    
    return orjson.dumps(out)


def extraction_worker(worker_id, query_base, out_file, element_name, element_type, min_id, max_id, num_workers, uri, user, pwd, dbname, fetch_size, limit):
    """ Standalone worker using ID Range Partitioning instead of Modulo for extreme performance. """
    limit_clause = f" LIMIT {max(1, limit // num_workers)}" if limit else ""

    chunk_size = (max_id - min_id) // num_workers + 1
    start_id = min_id + (worker_id * chunk_size)
    end_id = start_id + chunk_size

    range_condition = f" AND id({element_name}) >= {start_id} AND id({element_name}) < {end_id} "
    part_query = query_base.replace(" RETURN ", range_condition + " RETURN ") + limit_clause
    part_file = f"{out_file}.part{worker_id}"
    
    c = 0
    driver = neo4j.GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        with driver.session(database=dbname, fetch_size=fetch_size) as session:
            def _tx_func(tx):
                count = 0
                with open(part_file, "wb") as f:
                    for record in tx.run(part_query):
                        if element_type == 'node':
                            f.write(Neo4jNode_to_json(record['labels'], record['props']) + b"\n")
                        elif element_type == 'edge':
                            f.write(Neo4jEdge_to_json(record) + b"\n")
                        count += 1
                return count
            c = session.execute_read(_tx_func)
    except Exception as e:
        print(f"Worker {worker_id} failed: {e}")
    finally:
        driver.close()
        
    return part_file, c


def pg_to_json(uri, user, pwd, filename, limitnodes_pct=100, limitedges_pct=100, dbname="neo4j", num_workers=4, fetch_size=25000):
    """ Serializes a PG to JSON using true multiprocessing extraction and ID ranges. """

    driver = neo4j.GraphDatabase.driver(uri, auth=(user, pwd))

    def extract_concurrently(query_base, out_file, element_type, element_name, limit=None):
        partition_files = []
        total = 0

        with driver.session(database=dbname) as session:
            if element_type == 'node':
                bounds = session.execute_read(lambda tx: tx.run(f"MATCH ({element_name}) RETURN min(id({element_name})) as min_id, max(id({element_name})) as max_id").single())
            else:
                bounds = session.execute_read(lambda tx: tx.run(f"MATCH ()-[{element_name}]->() RETURN min(id({element_name})) as min_id, max(id({element_name})) as max_id").single())
            
            min_id = bounds["min_id"] if bounds["min_id"] is not None else 0
            max_id = bounds["max_id"] if bounds["max_id"] is not None else 0

        if num_workers > 1:
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(extraction_worker, i, query_base, out_file, element_name, element_type, min_id, max_id, num_workers, uri, user, pwd, dbname, fetch_size, limit) for i in range(num_workers)]
                for future in concurrent.futures.as_completed(futures):
                    pfile, c = future.result()
                    if c > 0: partition_files.append(pfile)
                    elif os.path.exists(pfile): os.remove(pfile)
                    total += c
        else:
            pfile, c = extraction_worker(0, query_base, out_file, element_name, element_type, min_id, max_id, 1, uri, user, pwd, dbname, fetch_size, limit)
            if c > 0: partition_files.append(pfile)
            elif os.path.exists(pfile): os.remove(pfile)
            total += c

        with open(out_file, "wb") as outfile:
            for pfile in partition_files:
                with open(pfile, "rb") as infile:
                    shutil.copyfileobj(infile, outfile)
                os.remove(pfile)

        return total

    with driver.session(database=dbname) as session:
        
        # 1. Unlabeled Nodes
        unlabeled_file = filename.split('.')[0] + "_unlabeled.jsonlines"
        query_unlab = "MATCH (n) WHERE size(labels(n)) = 0 RETURN labels(n) AS labels, properties(n) AS props"
        
        c = extract_concurrently(query_unlab, unlabeled_file, 'node', 'n')
        if c == 0:
            with open(unlabeled_file, "wb") as f: f.write(b"{}\n")
        
        nodeTypes = session.execute_read(lambda tx: tx.run(
            "MATCH (n) WITH labels(n) AS nlabel, size(collect(distinct n)) as nbn RETURN nlabel, nbn"
        ).data())
                
        nodeProperties = session.execute_read(lambda tx: tx.run(
            "call db.schema.nodeTypeProperties"
        ).data())
        
        nodesNoProp = [] 
        labels = []                      
        for prop in nodeProperties:
            if (None in prop.values()):
                if prop['nodeType'] != "":
                    ntype = {} 
                    nlabel = label_format(prop['nodeLabels'])
                    ntype[nlabel]={}
                    nodesNoProp.append(ntype)   
                else:
                    nodesNoProp.append({})        
            else:
                if prop['nodeType'] != "":
                    labels.append(prop['nodeLabels'])
                
        nodeLabels = list(labels for labels,_ in itertools.groupby(labels)) 
        
        nodesPropLabels = "False" 
        for ntype in nodeLabels:
            lab = label_format(ntype)
            nodesPropLabels += " OR n:" + lab
            
        # 2. Labeled Nodes
        node_file = filename.split('.')[0] + "_nodes.jsonlines"
        query_nodes = "MATCH (n) WHERE {} RETURN labels(n) AS labels, properties(n) AS props".format(nodesPropLabels)
        
        limitnodes = None
        if limitnodes_pct < 100:
            total_nodes = session.execute_read(lambda tx: tx.run("MATCH (n) WHERE {} RETURN count(n)".format(nodesPropLabels)).single()[0])
            limitnodes = max(1, int(total_nodes * (limitnodes_pct / 100.0)))
            
        c = extract_concurrently(query_nodes, node_file, 'node', 'n', limitnodes)
        if c == 0:
            with open(node_file, "wb") as f: f.write(b"{}\n")
        
        # 3. Edges
        edgeTypes = session.execute_read(lambda tx: tx.run(
            "MATCH p=(n)-[e]->(m) "
            "WITH labels(n) AS nlabel, size(collect(distinct n)) AS nbn, "
            "type(e) AS elabel, labels(m) AS mlabel, size(collect(distinct m)) AS nbm, "
            "count(e) AS nbedges ,properties(n) AS nprop, properties(m) AS mprop "
            "RETURN DISTINCT nlabel, elabel, mlabel, nbn, nbm, nbedges, nprop, mprop"
        ).data())
        
        edgeProperties = session.execute_read(lambda tx: tx.run(
            "call db.schema.relTypeProperties"
        ).data())
        
        elabels = [] 
        for prop in edgeProperties:
            if not (None in prop.values()):
                elabels.append([prop['relType'].strip(':`')])
                
        edgeLabels = list(elabels for elabels,_ in itertools.groupby(elabels)) 
        
        edgesPropLabels = "False"   
        for etype in edgeLabels:
            edgesPropLabels += " OR type(e)='" + etype[0] + "'"
        
        edge_file = filename.split('.')[0] + "_edges.jsonlines"
        query_edges = "MATCH (n)-[e]->(m) WHERE {} RETURN labels(n) AS nlabel, type(e) AS elabel, labels(m) AS mlabel, properties(e) AS props, keys(n) AS nkeys, keys(m) AS mkeys".format(edgesPropLabels)
        
        limitedges = None
        if limitedges_pct < 100:
            total_edges = session.execute_read(lambda tx: tx.run("MATCH ()-[e]->() WHERE {} RETURN count(e)".format(edgesPropLabels)).single()[0])
            limitedges = max(1, int(total_edges * (limitedges_pct / 100.0)))
            
        c = extract_concurrently(query_edges, edge_file, 'edge', 'e', limitedges)
        if c == 0:
            with open(edge_file, "wb") as f: f.write(b"{}\n")

    driver.close()
    return edgeTypes, nodeTypes, nodesNoProp


def get_edges_card(edgeTypes, nodeTypes):
    """ Returns edge cardinalities and optionality metadata. """
    edgesCard = {} 
    for etype in edgeTypes:
        
        edge = {} 
        
        nlabel = etype['nlabel'] 
        if nlabel:
            nlab = label_format(nlabel) 
        else:
            nlab = label_format(set(etype['nprop'].keys()))
            edge['meta_source_unlabeled'] = True
            
        mlabel = etype['mlabel'] 
        if mlabel:
            mlab = label_format(mlabel) 
        else:
            mlab = label_format(set(etype['mprop'].keys()))
            edge['meta_target_unlabeled'] = True
            
        elabel = etype['elabel']          
        
        nbSource =  etype['nbn']
        nbTarget =  etype['nbm']
        nbEdges =  etype['nbedges']
        
        nbnIndex = list(mit.locate(nodeTypes, pred = lambda d: d['nlabel'] == nlabel))
        nbn = nodeTypes[nbnIndex[0]]['nbn']
        nbnIndex = list(mit.locate(nodeTypes, pred = lambda d: d['nlabel'] == mlabel))
        nbm = nodeTypes[nbnIndex[0]]['nbn']
                 
        edge['meta_mandatory'] = not (nbSource < nbn or nbTarget < nbm)
        mandatorySource = not (nbSource < nbn)
        mandatoryTarget = not (nbTarget < nbm)
            
        if nbSource == nbTarget == nbEdges:
            edge['meta_cardinality'] = "1 : 1"
            edge['meta_cardinality'] = "1 : " if mandatorySource else "0..1 : "
            edge['meta_cardinality'] += "1" if mandatoryTarget else "0..1"
            
        elif nbSource > nbTarget and nbEdges == nbSource:
            edge['meta_cardinality'] = "M:1"
            edge['meta_cardinality'] = "1..* : " if mandatorySource else "0..* : "
            edge['meta_cardinality'] += "1" if mandatoryTarget else "0..1"
            
        elif nbSource < nbTarget and nbEdges == nbTarget:
            edge['meta_cardinality'] = "1:N"
            edge['meta_cardinality'] = "1 : " if mandatorySource else "0..1 : "
            edge['meta_cardinality'] += "1..*" if mandatoryTarget else "0..*"
            
        else:
            edge['meta_cardinality'] = "M:N"
            edge['meta_cardinality'] = "1..* : " if mandatorySource else "0..* : "
            edge['meta_cardinality'] += "1..*" if mandatoryTarget else "0..*"
            
        edgesCard[nlab + "::" + elabel + "::" + mlab] = edge
        
    return edgesCard