from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.anpr.selection import OCRCandidate, choose_candidate

def edit_distance(a, b):
    row=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        cur=[i]
        for j,cb in enumerate(b,1): cur.append(min(cur[-1]+1,row[j]+1,row[j-1]+(ca!=cb)))
        row=cur
    return row[-1]
def metrics(rows, key):
    exact=sum(r[key]==r['ground_truth'] for r in rows)
    errors=sum(edit_distance(r[key],r['ground_truth']) for r in rows)
    chars=sum(max(1,len(r['ground_truth'])) for r in rows)
    return {'exact_match_accuracy':exact/len(rows),'character_error_rate':errors/chars}
def main():
    ap=argparse.ArgumentParser(description='Replay candidate selection without rerunning OCR.')
    ap.add_argument('--input',required=True); ap.add_argument('--output',required=True)
    ap.add_argument('--margins',nargs='+',type=float,default=[0.05,0.10,0.15,0.20,0.25])
    args=ap.parse_args(); source=ROOT/args.input; output=ROOT/args.output
    with source.open(newline='',encoding='utf-8-sig') as f: source_rows=list(csv.DictReader(f))
    results=[]
    for row in source_rows:
        details=json.loads(row['candidate_details'])
        candidates=[OCRCandidate(d['text'],float(d['score']),d['method']) for d in details]
        original=next((c for c in candidates if c.method=='upscaled original'),OCRCandidate(row['original_prediction'],float(row['original_score']),'upscaled original'))
        result={'source_image':row['source_image'],'ground_truth':row['ground_truth'],'original_prediction':original.text}
        for margin in args.margins:
            selected,reason=choose_candidate(original,candidates,margin)
            key=f'margin_{margin:.2f}'
            result[key+'_prediction']=selected.text; result[key+'_exact_match']=selected.text==row['ground_truth']
            result[key+'_edit_distance']=edit_distance(selected.text,row['ground_truth']); result[key+'_reason']=reason
        results.append(result)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=results[0].keys());writer.writeheader();writer.writerows(results)
    summary={'samples':len(results),'original':metrics(results,'original_prediction'),'by_margin':{f'{m:.2f}':metrics(results,f'margin_{m:.2f}_prediction') for m in args.margins}}
    output.with_suffix('.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
