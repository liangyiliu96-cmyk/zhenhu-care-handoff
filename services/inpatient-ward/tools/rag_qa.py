import json, os, time, urllib.request, urllib.parse

BASE = os.environ.get('INPATIENT_BASE_URL', 'http://127.0.0.1:8001').rstrip('/')
H = {'x-role': 'doctor'}

def search(q, layer=None, topk=5):
    url = f'{BASE}/inpatient/rag/search?query={urllib.parse.quote(q)}&top_k={topk}'
    if layer: url += f'&layer={layer}'
    req = urllib.request.Request(url, headers=H)
    t0 = time.time()
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    elapsed = round((time.time() - t0) * 1000, 1)
    return resp['data']['results'], elapsed

# 1. 精准查询
print('=' * 60)
print('1. 精准查询 (原话题名)')
print('=' * 60)
tests = [
    ('心衰出入量管理', 'L8'), ('静脉输液护理常规', 'L8'),
    ('低血糖处理流程', 'L8'), ('VTE预防护理', 'L8'),
    ('氧疗规范', 'L8'), ('万古霉素TDM', 'L11'),
    ('脓毒症与脓毒性休克 1h Bundle', 'L7'), ('多重耐药菌(MDRO)隔离', 'L12'),
]
hit = 0
for q, ly in tests:
    rs, _ = search(q, layer=ly, topk=3)
    ok = any(q in r['topic'] for r in rs)
    hit += ok
    top = rs[0]['topic'] if rs else 'NO RESULTS'
    sc = rs[0].get('score', 0) if rs else 0
    print(f'  {q[:25]:25s} => {top[:30]}  score={sc:.3f}  {"OK" if ok else "MISS"}')

print(f'\n  精准 Recall@1: {round(hit/len(tests)*100)}% ({hit}/{len(tests)})')

# 2. 模糊同义
print()
print('=' * 60)
print('2. 模糊同义 (口语化提问)')
print('=' * 60)
fuzzy = [
    ('心衰病人喝水太多怎么办', 'L8'), ('身上有管子怎么护理', 'L8'),
    ('输液三查七对', 'L8'), ('手术后腿肿预防', 'L8'),
    ('血糖低怎么处理', 'L8'), ('防止住院得褥疮', 'L8'),
]
for q, ly in fuzzy:
    rs, _ = search(q, layer=ly, topk=3)
    top = rs[0]['topic'] if rs else 'NO'
    sc = rs[0].get('score', 0) if rs else 0
    print(f'  {q[:28]:28s} => {top[:28]}  score={sc:.3f}')

# 3. 跨层
print()
print('=' * 60)
print('3. 跨层检索')
print('=' * 60)
for q in ['心衰患者同时有糖尿病怎么用药', '老年人跌倒风险评估和预防', '手术后感染预防和营养支持']:
    rs, _ = search(q, topk=5)
    ly = set(r.get('layer', '?') for r in rs)
    print(f'  {q[:30]:30s} => {len(rs)} results, {len(ly)} layers: {ly}')

# 4. 噪声
print()
print('=' * 60)
print('4. 噪声测试 (无关问题)')
print('=' * 60)
for q in ['今天天气怎么样', '推荐一部电影', '北京到上海高铁']:
    rs, _ = search(q, topk=3)
    s = rs[0].get('score', 0) if rs else 0
    flag = 'WARN' if s > 0.35 else 'OK'
    print(f'  {q} => score={s:.3f} [{flag}]')

# 5. 延迟
print()
print('=' * 60)
print('5. 检索延迟')
print('=' * 60)
lats = []
for _ in range(10):
    _, t = search('心衰出入量管理', layer='L8', topk=5)
    lats.append(t)
avg = sum(lats) / len(lats)
print(f'  avg={avg:.0f}ms  min={min(lats):.0f}ms  max={max(lats):.0f}ms')

# 6. 切片质量检查
print()
print('=' * 60)
print('6. 切片质量检查')
print('=' * 60)
print('  当前架构: 一条知识 = 一个完整条目(未做句子级切分)')
print('  优点: 无断句问题, 无表格/公式被切烂风险')
print('  缺点: 长文本 (>500字) 向量稀释, 检索精度下降')
import os
import json as jsonlib
kb = jsonlib.load(open('config/clinical_knowledge.json', encoding='utf-8'))
lengths = []
for section in kb:
    if isinstance(kb[section], list):
        for item in kb[section]:
            lengths.append(len(item.get('content', '')))
lengths.sort()
print(f'  条目数: {len(lengths)}')
print(f'  平均长度: {sum(lengths)//len(lengths)} 字')
print(f'  中位数: {lengths[len(lengths)//2]} 字')
print(f'  最短: {lengths[0]} 字')
print(f'  最长: {lengths[-1]} 字')
print(f'  >500字: {sum(1 for l in lengths if l>500)} 条')
print(f'  >1000字: {sum(1 for l in lengths if l>1000)} 条')

# 7. 元数据完整性
print()
print('=' * 60)
print('7. 元数据完整性')
print('=' * 60)
required = ['topic', 'category', 'content']
missing = 0
for section in kb:
    if isinstance(kb[section], list):
        for item in kb[section]:
            for f in required:
                if f not in item or not item[f]:
                    missing += 1
                    print(f'  MISSING: [{section}] {item.get("topic","?")} lacks {f}')
                    break
print(f'  缺必要字段: {missing} 条')
print(f'  元数据完整性: {"PASS" if missing==0 else "FAIL"}')
