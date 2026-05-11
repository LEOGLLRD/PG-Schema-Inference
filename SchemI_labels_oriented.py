import argparse
import json
import time
import os
import gc
import resource

# Import the preprocessing function
from labelsOriented.preprocessing_labels import pg_to_json, get_edges_card
# Import the MapReduce inference module
import labelsOriented.mapreduce_labels as mr

def set_memory_limit(gb_limit):
    """ Restricts the RAM available to the Python process (in Gigabytes). """
    if gb_limit > 0:
        bytes_limit = int(gb_limit * 1024 * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
        print(f"  -> Python memory limit set to {gb_limit} GB")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Infer PG schema (Labels-oriented)")
    parser.add_argument('-c', '--config', help="Path to the JSON configuration file", required=True)
    args = parser.parse_args()

    print("\nLabels-oriented PG schema inference (Automated Mode)\n")

    # 1. READ CONFIGURATION
    with open(args.config, 'r') as config_file:
        config = json.load(config_file)

    URI = config["neo4j"]["uri"]
    USER = config["neo4j"]["user"]
    PWD = config["neo4j"]["password"]
    DBname = config["neo4j"]["database"]

    ext_config = config.get("extraction", {})
    limitnodes_pct = ext_config.get("limitnodes_pct", 100)
    limitedges_pct = ext_config.get("limitedges_pct", 100)
    num_workers = ext_config.get("num_workers", 4)
    fetch_size = ext_config.get("fetch_size", 25000)

    gen_config = config.get("general", {})
    python_mem_limit = gen_config.get("python_memory_limit_gb", -1)

    mr_config = config.get("mapreduce", {})
    spark_driver_memory = mr_config.get("driver_memory", "2g")
    spark_master = mr_config.get("master", "local[*]")
    equiv_labels = mr_config.get("equiv_labels", "k")

    set_memory_limit(python_mem_limit)

    # 2. NEO4J EXTRACTION (STEP 1)
    PGfilename = f"pg_data_{DBname}.jsonlines"

    print("Step 1: Extracting Graph from Neo4j...")
    start_time_ext = time.time()

    # Pass credentials directly to support true multiprocessing worker connections
    edgeTypes, nodeTypes, nodesNoProp = pg_to_json(
        URI, USER, PWD, PGfilename, 
        limitnodes_pct=limitnodes_pct, limitedges_pct=limitedges_pct, 
        dbname=DBname, num_workers=num_workers, fetch_size=fetch_size
    )
    
    print("Calculating edge cardinalities...")
    edgesCard = get_edges_card(edgeTypes, nodeTypes)

    ext_duration = time.time() - start_time_ext
    print(f"Extraction completed in {ext_duration:.2f} seconds.\n")

    # 3. SPARK MAP-REDUCE & FUSION (STEP 2)
    print("Step 2: Starting Spark MapReduce Schema Inference...")
    start_time_mr = time.time()

    base_name = PGfilename.split('.')[0]
    nodes_file = f"{base_name}_nodes.jsonlines"
    edges_file = f"{base_name}_edges.jsonlines"
    unlab_file = f"{base_name}_unlabeled.jsonlines"

    # 3.1 Process Nodes
    print(" -> Inferring Nodes schema...")
    MR_nodes_file = mr.call_mapreduce(nodes_file, equiv=equiv_labels, driver_memory=spark_driver_memory, master=spark_master)
    schemaNodes = mr.parse_mapreduce_schema(MR_nodes_file)
    if schemaNodes == 'Null': schemaNodes = {}

    # 3.2 Process Edges
    print(" -> Inferring Edges schema...")
    MR_edges_file = mr.call_mapreduce(edges_file, equiv=equiv_labels, driver_memory=spark_driver_memory, master=spark_master)
    schemaEdges = mr.parse_mapreduce_schema(MR_edges_file)
    if schemaEdges == 'Null': schemaEdges = {}

    # 3.3 Process Unlabeled Nodes
    print(" -> Inferring Unlabeled Nodes schema...")
    MR_unlab_file = mr.call_mapreduce(unlab_file, equiv=equiv_labels, driver_memory=spark_driver_memory, master=spark_master)
    unlabNodes = mr.parse_mapreduce_unlabeled(MR_unlab_file)

    print("\nStep 3: Compiling final schema...")
    
    # Merge everything together
    schema = mr.merge_nodes_edges(schemaNodes, schemaEdges)
    mr.merge_schema_infos(schema, nodesNoProp, edgesCard)
    mr.merge_unlabeled_nodes(schema, unlabNodes)

    # Serialize the final schema into a JSON file
    schema_output_file = f"schema_{DBname}_labels.json"
    with open(schema_output_file, "w") as f:
        json.dump(schema, f, indent=4)

    mr_duration = time.time() - start_time_mr
    print(f"MapReduce completed in {mr_duration:.2f} seconds.\n")

    # 4. CLEANUP 
    for file in ["edgesCard.json", "nodesNoProp.json"]:
        if file and os.path.exists(file): os.remove(file)

    print(f"Total execution time: {ext_duration + mr_duration:.2f} seconds.")