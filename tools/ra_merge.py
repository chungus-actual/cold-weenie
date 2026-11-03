import sys,re
base,over,out=sys.argv[1:4]
ov={}
for l in open(over,encoding='utf-8'):
    m=re.match(r'^\s*([^#\s=]+)\s*=\s*(.*)$',l)
    if m: ov[m.group(1)]=m.group(2).strip()
seen=set(); res=[]
for l in open(base,encoding='utf-8',newline=''):
    m=re.match(r'^([^#\s=]+)\s*=',l)
    if m and m.group(1) in ov:
        res.append(f'{m.group(1)} = {ov[m.group(1)]}\n'); seen.add(m.group(1))
    else: res.append(l)
for k,v in ov.items():
    if k not in seen: res.append(f'{k} = {v}\n')
open(out,'w',encoding='utf-8',newline='\n').write(''.join(res))
