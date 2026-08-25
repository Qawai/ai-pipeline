import os
import sys

os.environ.setdefault("PORT", "7860")
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_BIN = os.path.join(HERE, "bin")
os.environ["PATH"] = LOCAL_BIN + os.pathsep + os.environ.get("PATH", "")

sys.path.insert(0, HERE)
import server
server.main()
