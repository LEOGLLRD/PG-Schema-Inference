# SchemI - Schema Inference for Property Graphs (PG)

This project is a fork from a 2020 project of [Hanâ LBATH - Property Graph Schema Inference ](https://gitlab.com/Hgit/pgsinference). The aim of this work is to make it compatible with Neo4J 6.x.x

## About the Project
This end-to-end Python pipeline infers PG schemas from input PG stored in Neo4j. Our method leverages a MapReduce type inference method (by [Baazizi et al.](https://doi.org/10.1007/s00778-018-0532-7)) and introduces a node hierarchy inference technique to output PG schemas that handle complex and nested property values, multi-labeled nodes, node hierarchies and overlapping node types, in addition to containing information about edge cardinality constraints and optionality of properties. We proposed two implementations: a *labels-oriented* and a *properties-oriented* variant.

It was developed by Hanâ Lbath in the context of her Master's thesis in Computer Science (at ENS Lyon)/Bioinformatics and Modeling (at INSA Lyon) under the supervision of Angela Bonifati and Russ Harmer.

## Code
The code is organized as follows:
 - *labels-oriented* variant: run **SchemI\_labels\_oriented.py** to infer a PG schema. The functions called in this script are stored in the **labelsOriented** folder.

 - *properties-oriented* variant: run **SchemI\_properties\_oriented.py** to infer a PG schema. The functions called in this script are stored in the **propertiesOriented** folder

 - the **MapReduce** folder contain the binaries of the MapReduce type inference algorithm.

## Improvements with the fork

- Now works with Neo4J 6.x.x
- Managing ressources usage (ijson + CPU and RAM limitations on Python and Map Reduce)
- Quicker with ijson usage


## Environment
(It might work with other Python and Java version, but it hasn't been tested)
Python 3.14, Neo4J 6 + APOC Core and APOC Extended (recommended), Java 8. 
APOC Extended can be found at : https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases
### IJSON backend requierements
This project uses `ijson` for streaming large JSON files. To maximize performance, it is highly recommended to use the C backend based on YAJL (Yet Another JSON Library). 

#### Windows:
Pre-compiled wheels for Windows already include the C backend. No system dependencies are required. Activate your virtual environment and run:
```bash
pip install ijson
```
#### Mac
You need to install the YAJL library using Homebrew. The C compiler (Clang) is provided by the Apple Command Line Tools.
```bash
brew install yajl
```
Activate your virutal environment and run : 
```bash
pip install --force-reinstall --no-binary ijson ijson
```

#### Linux
You need to install the C compiler, Python headers, and the YAJL library. For Debian/Ubuntu-based distributions:

```bash
sudo apt update
sudo apt install libyajl-dev gcc python3-dev
```
Once the system dependencies are installed, activate your virtual environment and force the local compilation:
```bash
pip install --force-reinstall --no-binary ijson ijson
```

#### Verification
To ensure the C backend is correctly installed and active, run the following command within your virtual environment:

```bash
python -c 'import ijson.backends.yajl2 as ijson; print("The ijson C backend (yajl2) is installed and functional.")'
```

