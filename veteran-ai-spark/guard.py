# guard.py
from dataclasses import dataclass

@dataclass
class GuardCfg:
    TOP_K:int=5
    ALPHA:float=0.7       # weight for rel (dense sim in [0,1])
    BETA:float=0.3        # weight for cross-encoder score in [0,1]
    MIN_FINAL:float=0.28  # per-chunk cutoff (start here)
    MIN_CONF:float=0.35   # aggregate cutoff (start here)
    SAFE_MSG:str="I don't have enough grounded info in the retrieved sources to answer."

CFG=GuardCfg()

def score(rel:float, cross:float)->float:
    return CFG.ALPHA*float(rel or 0)+CFG.BETA*float(cross or 0)

def select_and_gate(hits):
    """
    hits: [{'text':..., 'rel':0..1, 'cross':0..1, 'meta':{'url':...}}, ...]
    returns: (selected_hits_with_final, agg_conf)
    """
    for h in hits:
        h['final']=score(h.get('rel',0), h.get('cross',0))
    hits.sort(key=lambda x:x['final'], reverse=True)
    top=hits[:CFG.TOP_K]
    gated=[h for h in top if h['final']>=CFG.MIN_FINAL]
    pool=gated if gated else top
    agg=sum(h['final'] for h in pool)/max(len(pool),1) if pool else 0.0
    return gated, agg

SYSTEM_GUARDED=(
 "You are careful and must use ONLY the provided Sources. "
 "If they do not support an answer, say: "
 "\"I don't have enough information to answer from the provided sources.\" "
 "Rules: no invented facts; add [S1],[S2] citations after claims."
)

def build_user_prompt(q, selected):
    lines=[]
    for i,h in enumerate(selected,1):
        h['sid']=f"S{i}"
        url=h.get('meta',{}).get('url','')
        lines.append(f"[{h['sid']}] {url}\n{h['text']}\n")
    src="\n".join(lines) or "(none)"
    return f"Question:\n{q}\n\nSources:\n{src}\n\nAnswer with citations like [S1]. If not answerable, refuse."

