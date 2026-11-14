#!/usr/bin/env python3
"""Build an ignored demo DB from the official CSVs, streaming each source."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scoach.db import connect, import_csvs, DEFAULT_CUSTOMERS

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='junction-dataset')
    parser.add_argument('--output',default='var/scoach.sqlite3')
    parser.add_argument('--customers',nargs='+',default=list(DEFAULT_CUSTOMERS))
    args=parser.parse_args()
    with connect(args.output) as conn:
        print(json.dumps(import_csvs(conn,args.source,args.customers),indent=2))
