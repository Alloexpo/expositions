# -*- coding: utf-8 -*-
"""Veille des expositions en région (Lille, Nantes, Aix-en-Provence, Marseille…), même principe que pour Paris :
les pages listées dans l'onglet « Sources » sont relues ; chaque nouvelle exposition trouvée (titre, dates, visuel,
description, lien) est ajoutée « À valider ». Les lieux et sources se gèrent dans l'onglet « Sources »."""
import re, datetime, urllib.parse, requests, html as _h
import scan
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36', 'Accept-Language': 'fr-FR,fr;q=0.9'}
M = {'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8, 'aout': 8,
     'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12, 'decembre': 12}
MP = '|'.join(M)
RX = re.compile(rf"(\d{{1,2}})(?:er)?\s*({MP})?\s*(\d{{4}})?\s*(?:au|–|-|>|jusqu'au)\s*(?:[a-zéû]+\s)?(\d{{1,2}})(?:er)?\s*({MP})\s*(\d{{4}})", re.I)
RX2 = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})\s*(?:au|–|-|>|→)\s*(\d{1,2})[./](\d{1,2})[./](\d{2,4})")
def dates(txt):
    for m in RX.finditer(txt):
        d0, m0, y0, d1, m1, y1 = m.groups(); m1 = M[m1.lower()]; y1 = int(y1); m0 = M[m0.lower()] if m0 else m1
        y0 = int(y0) if y0 else (y1 if m0 <= m1 else y1 - 1)
        try:
            a, b = datetime.date(y0, m0, int(d0)), datetime.date(y1, m1, int(d1))
            if 7 <= (b - a).days <= 500: return a, b
        except ValueError: pass
    for m in RX2.finditer(txt):
        g = [int(x) for x in m.groups()]; y0 = g[2] + 2000 if g[2] < 100 else g[2]; y1 = g[5] + 2000 if g[5] < 100 else g[5]
        try:
            a, b = datetime.date(y0, g[1], g[0]), datetime.date(y1, g[4], g[3])
            if 7 <= (b - a).days <= 500: return a, b
        except ValueError: pass
    return None, None
def fetch(u):
    try:
        r = requests.get(u, headers=UA, timeout=25)
        if r.status_code == 200 and 'html' in r.headers.get('content-type', ''):
            if not r.encoding or r.encoding.lower() == 'iso-8859-1': r.encoding = r.apparent_encoding
            return r.text
    except Exception: pass
    return None
def _meta(t, p):
    m = re.search(rf'<meta[^>]+(?:property|name)="{p}"[^>]+content="([^"]*)"', t) or re.search(rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{p}"', t)
    return _h.unescape(m.group(1)).strip() if m else ''
def _text(t):
    t = re.sub(r'(?is)<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>', ' ', t)
    return re.sub(r'\s+', ' ', _h.unescape(re.sub(r'<[^>]+>', ' ', t)))
def detail(u):
    t = fetch(u)
    if not t: return None
    h1 = re.search(r'(?is)<h1[^>]*>(.*?)</h1>', t); h1 = re.sub(r'\s+', ' ', _h.unescape(re.sub(r'<[^>]+>', ' ', h1.group(1)))).strip() if h1 else ''
    title = h1 or re.split(r'\s+[|–-]\s+', _meta(t, 'og:title'))[0]
    txt = _text(t); desc = _meta(t, 'og:description') or _meta(t, 'description')
    a, b = dates(desc + ' ' + txt[:6000])
    img = _meta(t, 'og:image'); img = urllib.parse.urljoin(u, img) if img else ''
    m = re.search(r'(aHR0[A-Za-z0-9+/=]{20,})', img or '')          # offices de tourisme : vignette recadrée -> image d'origine (Apidae)
    if m:
        try:
            import base64; o = base64.b64decode(m.group(1) + '==').decode('utf-8', 'ignore')
            if o.startswith('http'): img = o
        except Exception: pass
    return dict(url=u, title=title.strip(' «»"'), desc=desc, text=txt, img=img, d0=a, d1=b)
def read_sources(wb):
    if 'Sources' not in wb.sheetnames: return []
    ws = wb['Sources']; out = []
    for r in ws.iter_rows(min_row=5, values_only=True):
        if r and r[0] and len(r) > 2 and r[2] and str(r[2]).startswith('http') and not str((r[4] if len(r) > 4 else '') or '').startswith('('):
            out.append(dict(ville=str(r[0]).split('(')[0].strip(), nom=r[1], url=str(r[2]), lieu=(r[3] if len(r) > 3 else None), motif=(r[4] if len(r) > 4 else None)))
    return out
def scan_sources(wb, today=None, max_links=30):
    today = today or datetime.date.today(); venues, known, rej = scan.known_and_rejected(wb)
    by_city = {}
    for sh in ('Expositions', 'Archives'):
        ws = wb[sh]; h, heads = scan.table_rows(ws); cL, cV = scan.col(heads, 'Lieu'), scan.col(heads, 'Ville')
        for r in ws.iter_rows(min_row=h + 1, values_only=True):
            if r and r[0] and r[cL - 1] and r[cV - 1]: by_city.setdefault(str(r[cV - 1]), set()).add(str(r[cL - 1]))
    new, stats = [], dict(sources=0, pages=0, ajoutees=0, sans_dates=0, lieu_inconnu=0, deja_connues=0, hors_fenetre=0)
    seen = set()
    for s in read_sources(wb):
        html = fetch(s['url']); stats['sources'] += 1
        if not html: continue
        try: motif = re.compile(s['motif'] or r'expo', re.I)
        except re.error: continue
        dom = urllib.parse.urlparse(s['url']).netloc
        links = []
        for m in re.finditer(r'href="([^"#]+)"', html):
            u = urllib.parse.urljoin(s['url'], _h.unescape(m.group(1)))
            if u.startswith('http') and motif.search(u) and u.rstrip('/') != s['url'].rstrip('/') and u not in links: links.append(u)
        for u in links[:max_links]:
            if u in seen: continue
            seen.add(u); d = detail(u); stats['pages'] += 1
            if not d or not d['title']: continue
            if not d['d0']: stats['sans_dates'] += 1; continue
            a, b = d['d0'], d['d1']
            if b < today + datetime.timedelta(days=10) or a > today + datetime.timedelta(days=420) or (b - a).days < 14: stats['hors_fenetre'] += 1; continue
            ven = s['lieu']
            if not ven:
                cands = [v for v in by_city.get(s['ville'], set()) | ({v for v in venues} if False else set()) if v and v.lower() in d['text'].lower()]
                ven = max(cands, key=len) if cands else None
            if not ven: stats['lieu_inconnu'] += 1; continue
            title = re.sub(r'^(Exposition|Expo)\s*:?\s*', '', d['title'], flags=re.I).strip()
            if re.fullmatch(r"(?i)(les )?(év[èée]nements?|expositions?( en cours| à venir| temporaires)?|agenda|programme|programmation|accueil|actualités?|à venir|en ce moment)", title) or len(title) < 4: continue
            ent = (scan.toks(title), a.isoformat(), ven)
            if any(scan.same(ent, k) for k in known) or any(scan.same(ent, k, 400) for k in rej) or any(scan.same(ent, (scan.toks(n['t']), n['a'], n['l'])) for n in new):
                stats['deja_connues'] += 1; continue
            new.append(dict(t=title, l=ven, v=s['ville'], a=a.isoformat(), b=b.isoformat(), tag='Autres et inclassables', re=scan.words(d['desc'] or d['text'][:900], 150),
                            px=None, pg=u, im=d['img'], bk=None, src=s['nom']))
    stats['ajoutees'] = len(new)
    return new, stats

# — Flux open data (moins coûteux que la lecture de pages) —
NANTES_API = 'https://data.nantesmetropole.fr/api/explore/v2.1/catalog/datasets/244400404_agenda-evenements-nantes-metropole_v2/records'
MUSEUM_RX = re.compile(r"mus[ée]e|ch[âa]teau des ducs|lieu unique|hab galerie|frac|chapelle de l.oratoire|passage sainte-croix|fondation|centre d.art|temple du go[ûu]t|maison de la poésie|atelier de l.imprimerie|mémorial", re.I)
def scan_api_nantes(wb, today, known, rej, tracked):
    """Expositions de l'agenda officiel de Nantes Métropole (une ligne par date : on regroupe par manifestation)."""
    out, seen = [], {}
    try:
        off = 0
        while off < 2000:
            r = requests.get(NANTES_API, params={'limit': 100, 'offset': off, 'where': f"types_libelles='Exposition' and date>='{today.isoformat()}'",
                                                 'select': 'id_manif,nom,description_evt,lieu,ville,date,lien_agenda,media_url,lieu_siteweb,gratuit,precisions_tarifs_evt'}, headers=UA, timeout=40).json()
            res = r.get('results', [])
            for x in res:
                k = x['id_manif']; d = datetime.date.fromisoformat(x['date'][:10])
                if k not in seen: seen[k] = dict(x, d0=d, d1=d)
                else: seen[k]['d0'] = min(seen[k]['d0'], d); seen[k]['d1'] = max(seen[k]['d1'], d)
            if len(res) < 100: break
            off += 100
    except Exception: return out
    for x in seen.values():
        lieu = (x.get('lieu') or '').strip(); ville = (x.get('ville') or 'Nantes').strip()
        if ville.lower() != 'nantes' or not (MUSEUM_RX.search(lieu) or lieu in tracked): continue
        a, b = x['d0'], x['d1']
        desc = x.get('description_evt') or ''
        m = dates(desc)                                  # la description donne souvent la vraie période (« du 8 mai au 8 novembre »)
        if m[0] and m[1] and m[1] >= b: a, b = min(a, m[0]), m[1]
        if (b - a).days < 14 or b < today + datetime.timedelta(days=10): continue
        title = re.sub(r'\s*[-–]\s*Exposition\s*$|^Exposition\s*:?\s*', '', x.get('nom') or '', flags=re.I).strip()
        if len(title) < 6 or title[0].islower() or re.search(r'\(\s*\+|^flash\b', title, re.I): continue
        ven = next((v for v in tracked if v.lower()[:12] in lieu.lower() or lieu.lower()[:12] in v.lower()), lieu)
        ent = (scan.toks(title), a.isoformat(), ven)
        if any(scan.same(ent, k) for k in known) or any(scan.same(ent, k, 400) for k in rej): continue
        px = 'Gratuit' if str(x.get('gratuit')).lower() == 'oui' else (x.get('precisions_tarifs_evt') or None)
        out.append(dict(t=title, l=ven, v='Nantes', a=a.isoformat(), b=b.isoformat(), tag='Autres et inclassables', re=scan.words(desc, 150), px=px,
                        pg=x.get('lien_agenda') or x.get('lieu_siteweb'), im=x.get('media_url'), bk=None, src='Agenda open data de Nantes Métropole'))
    return out
_scan_pages = scan_sources
def scan_sources(wb, today=None, max_links=30):
    """Pages des musées et offices de tourisme (onglet « Sources ») + flux open data quand il en existe (Nantes)."""
    today = today or datetime.date.today()
    new, stats = _scan_pages(wb, today, max_links)
    venues, known, rej = scan.known_and_rejected(wb)
    tracked = set()
    for s in read_sources(wb) + [dict(ville='Nantes', lieu=None)]:
        if s.get('lieu') and s['ville'] == 'Nantes': tracked.add(s['lieu'])
    known = known + [(scan.toks(n['t']), n['a'], n['l']) for n in new]
    api = scan_api_nantes(wb, today, known, rej, tracked)
    stats['api_nantes'] = len(api); stats['ajoutees'] += len(api)
    return new + api, stats
