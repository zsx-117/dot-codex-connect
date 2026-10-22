"""Writable account-private state and self-execution for the compiled client."""
import os,sys
from pathlib import Path
DATA=Path(os.environ.get('DOT_CONNECT_HOME',str(Path.home()/'Library/Application Support/DotCodexConnect'))).expanduser().resolve()
DATA.mkdir(parents=True,mode=0o700,exist_ok=True)
def child_command(action,*args):
 if hasattr(sys.modules.get('__main__'),'__compiled__'):
  return [str(Path(sys.argv[0]).resolve()),action,*args]
 return [sys.executable,str(Path(__file__).with_name('connector.py')),action,*args]
