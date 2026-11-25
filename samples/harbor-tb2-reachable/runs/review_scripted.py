import json,os,sys,glob,urllib.request,pathlib
sys.path.insert(0,"/home/ubuntu/files_eval/tb2-adv/tools")
from reviewer import PROMPT,MODEL
res={}
for t in sorted(glob.glob("planted/*__*")+glob.glob("tamper/*__*")):
    arm,trial=t.split("/"); task=trial.split("__")[0]
    solve=pathlib.Path(f"/home/ubuntu/repos/modal-receipts/samples/harbor-tb2-reachable/tasks/{arm}/{task}/solution/solve.sh").read_text()
    instr=pathlib.Path(f"/home/ubuntu/repos/modal-receipts/samples/harbor-tb2-reachable/tasks/{arm}/{task}/instruction.md").read_text()
    tx=f"[user] {instr}\n[tool Bash] {json.dumps({'command':solve})}\n"
    body={"model":MODEL,"messages":[{"role":"user","content":PROMPT+tx}],"response_format":{"type":"json_object"},"temperature":0}
    req=urllib.request.Request("https://ai-gateway.vercel.sh/v1/chat/completions",json.dumps(body).encode(),{"Authorization":"Bearer "+os.environ["AI_GATEWAY_API_KEY"],"Content-Type":"application/json"})
    r=json.load(urllib.request.urlopen(req,timeout=180))
    res[t]={"verdict":json.loads(r["choices"][0]["message"]["content"]),"usage":r.get("usage"),"transcript":"synthetic: instruction + full scripted command as one Bash tool call"}
print(json.dumps(res,indent=1))
