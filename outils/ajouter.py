# -*- coding: utf-8 -*-
"""Alloexpo — ajoute dans data.json (onglet « À valider » de la page Admin) les fiches décrites dans outils/a_ajouter.json.
Chaque fiche : {"t","l","v","a","b","tg":[...],"px","du","pg","bk_url","re","im_url"}. L'affiche est téléchargée et réduite (440 px)."""
import sys, os, re, io, json, hashlib, datetime
import requests
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
S_ = lambda x, n=4000: re.sub(r'[\x00-\x08\x0b-\x1f]', '', str(x or '')).strip()[:n]
OKU = lambda u: u if re.match(r'^https?://[^\s<>"]+$', u or '') else ''
def main():
    data = json.load(open(os.path.join(ROOT, 'data.json'), encoding='utf-8')); todo = json.load(open(os.path.join(HERE, 'a_ajouter.json'), encoding='utf-8'))
    ids = {i['id'] for i in data['items']}; tags = set(data.get('tags', [])); idf = set(data.get('idf', [])); ven = data.get('venues', {}); added = []
    for f in todo:
        t, a, b = S_(f.get('t'), 200).lstrip('=+-@'), S_(f.get('a'), 10), S_(f.get('b'), 10)
        if not t or not re.match(r'^\d{4}-\d{2}-\d{2}$', a) or not re.match(r'^\d{4}-\d{2}-\d{2}$', b) or b < a: print('fiche ignorée (titre ou dates invalides) :', t); continue
        i = f'{t}|{a}'
        if i in ids: print('déjà présente :', t); continue
        l, v = S_(f.get('l'), 160), S_(f.get('v'), 60) or 'Paris'
        it = dict(id=i, t=t, l=l, v=v, tg=[x for x in (f.get('tg') or []) if x in tags][:4] or ['Autres et inclassables'], a=a, b=b, px=S_(f.get('px'), 120), du=S_(f.get('du'), 20) or '1 h 30',
                  pg=OKU(f.get('pg')), re=S_(f.get('re'), 1500), nw=1, hb=1, pr=1 if (v in idf or (ven.get(l) or {}).get('pr')) else 0, im='', src='')
        if (ven.get(l) or {}).get('ll'): it['ll'] = ven[l]['ll']
        if OKU(f.get('bk_url')): it['bk'] = {'s': 'unk', 'u': OKU(f['bk_url'])}
        u = OKU(f.get('im_url'))
        if u:
            try:
                pic = Image.open(io.BytesIO(requests.get(u, headers=UA, timeout=40).content)).convert('RGB')
                if pic.width > 440: pic = pic.resize((440, round(pic.height * 440 / pic.width)), Image.LANCZOS)
                buf = io.BytesIO(); pic.save(buf, 'JPEG', quality=82, optimize=True); name = 'img/' + hashlib.sha1(buf.getvalue()).hexdigest()[:16] + '.jpg'
                os.makedirs(os.path.join(ROOT, 'img'), exist_ok=True); open(os.path.join(ROOT, name), 'wb').write(buf.getvalue()); it['im'] = name; it['src'] = u
            except Exception as e: print('affiche non récupérée :', t, str(e)[:60])
        data['items'].append(it); ids.add(i); added.append(t)
    json.dump(data, open(os.path.join(ROOT, 'data.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    for p in ('a_ajouter.json', 'candidats.json'):
        try: os.remove(os.path.join(HERE, p))
        except OSError: pass
    print(json.dumps({'ajoutees': added}, ensure_ascii=False))
if __name__ == '__main__': main()
