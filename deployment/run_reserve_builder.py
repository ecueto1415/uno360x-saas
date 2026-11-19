"""Replenish at <=40 or when creation is idle, up to five per pass and 50 ready."""
import pathlib,sys,json
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.shared_adapter import SharedHostAdapter
from deployment.reserve_pool import Pool

def main():
 from deployment.prepare_reserve_version import prepare
 prepare()
 adapter=SharedHostAdapter()
 with Pool(adapter) as pool:pool.replenish()
if __name__=='__main__':main()
