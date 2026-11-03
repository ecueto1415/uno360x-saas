import pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.shared_adapter import SharedHostAdapter
from deployment.reserve_pool import Pool
if __name__=='__main__':
 with Pool(SharedHostAdapter()) as pool:pool.ensure()
