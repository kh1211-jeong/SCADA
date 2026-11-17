"""workspace/AGENTS.md, SOUL.md를 goclaw DB(agent_context_files)의 scada-diag 지침으로 반영한다. 반영 후 goclaw 재시작 필요."""
import sqlite3, pathlib
here = pathlib.Path(__file__).parent
db = sqlite3.connect(here / 'data' / 'goclaw.db')
aid = db.execute("select id from agents where agent_key='scada-diag'").fetchone()[0]
for f in ('AGENTS.md', 'SOUL.md'):
    txt = (here / 'workspace' / f).read_text(encoding='utf-8')
    n = db.execute("update agent_context_files set content=? where agent_id=? and file_name=?", (txt, aid, f)).rowcount
    print(f, 'updated' if n else 'NOT FOUND', len(txt))
db.commit()
