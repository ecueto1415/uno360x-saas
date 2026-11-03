"""Prepare pristine logical/SQL templates before switching the common release."""
import pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from control.template_cache import verified_cache
from deployment.shared_adapter import SharedHostAdapter
from deployment.reserve_pool import Pool,profiles

def prepare():
 a=SharedHostAdapter();wanted=profiles()
 if any(verified_cache(profile,a.images) is None for _,profile,_ in wanted):
  subprocess.run([sys.executable,str(ROOT/'deployment/build_templates.py')],check=True)
 with Pool(a) as pool,pool.builder_lock():
  pool.ensure()
  for _,profile,_ in wanted:pool.seed(profile)
if __name__=='__main__':prepare()
